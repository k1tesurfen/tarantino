"""The daily programme: one title per room per cinema day.

Generation is idempotent: `ensure_day` only fills rooms that have no entry for
the day yet, so it can run at the rollover, at startup and on every request.
"""

import logging
import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from tarantino.models import (
    Franchise,
    FranchiseRun,
    LibraryCollection,
    LibraryItem,
    ProgrammeEntry,
    Room,
    SeriesAssignment,
)
from tarantino.programme import franchises
from tarantino.programme.franchises import FranchiseIndex
from tarantino.programme.rules import DEFAULT_ROOMS, MovieFilters, Weights
from tarantino.settings import AppSettings, SettingsStore

log = logging.getLogger(__name__)

SERIES_SHOWTIME_MINUTES = 60
FIRST_SHOW_EARLIEST = 14 * 60  # 14:00
LAST_SHOW_LATEST = 23 * 60 + 30  # 23:30


class ProgrammeError(Exception):
    pass


def cinema_date(now: datetime, rollover_hour: int) -> date:
    """The cinema day `now` belongs to: before the rollover hour it is still yesterday."""
    return (now - timedelta(hours=rollover_hour)).date()


def fake_showtimes(day: date, room_number: int, runtime_minutes: int | None) -> list[str]:
    """Up to three plausible, stable showtimes for a room on a day."""
    rng = random.Random(f"{day.isoformat()}/{room_number}")
    slot = math.ceil(((runtime_minutes or 100) + 30) / 15) * 15  # runtime + break, on 15-minute steps
    time = FIRST_SHOW_EARLIEST + rng.randrange(0, 13) * 15  # 14:00 - 17:00
    times = []
    while time <= LAST_SHOW_LATEST and len(times) < 3:
        times.append(f"{time // 60:02d}:{time % 60:02d}")
        time += slot
    return times


@dataclass
class _Context:
    """Everything one generation run needs, loaded once."""

    day: date
    settings: AppSettings
    now: datetime
    movies: list[LibraryItem]
    series: dict[str, LibraryItem]
    last_shown: dict[str, date]  # item id -> most recent earlier day it was programmed
    franchises: FranchiseIndex
    used: set[str] = field(default_factory=set)  # taken by another room on `day` (hard exclusion)
    avoid: set[str] = field(default_factory=set)  # steer away from these (soft; e.g. the title being rerolled)

    def in_cooldown(self, item_id: str, days: int) -> bool:
        if self.franchises.continues(item_id):
            return False  # a started franchise is paced by its daily chance, not the cooldown
        last = self.last_shown.get(item_id)
        return last is not None and (self.day - last).days < days

    def use(self, item_id: str) -> None:
        self.used |= self.franchises.siblings(item_id)  # duplicate copies are the same film

    def use_entries(self, entries: list[ProgrammeEntry]) -> None:
        for entry in entries:
            for item_id in _entry_items(entry):
                self.use(item_id)
            if entry.first_started_at:
                # A franchise running a marathon here today offers its next part only in this room.
                for item_id in _entry_items(entry):
                    if franchise := self.franchises.franchise_of(item_id):
                        self.used |= self.franchises.item_ids(franchise.collection_id)


class Programme:
    def __init__(
        self,
        session_factory: sessionmaker,
        settings: SettingsStore,
        rng: random.Random | None = None,
        clock: Callable[[], datetime] = datetime.now,
    ):
        self.session_factory = session_factory
        self.settings = settings
        self.rng = rng or random.Random()
        self.clock = clock

    def today(self) -> date:
        return cinema_date(self.clock(), self.settings.get().rollover_hour)

    def day_start(self) -> datetime:
        """When the current cinema day began."""
        return datetime.combine(self.today(), time(self.settings.get().rollover_hour))

    # -- rooms --------------------------------------------------------------

    def ensure_rooms(self) -> None:
        """Create the default rooms on a fresh installation."""
        with self.session_factory.begin() as session:
            if session.scalar(select(Room.id).limit(1)) is not None:
                return
            for number, name, kind, filters, weights in DEFAULT_ROOMS:
                session.add(Room(
                    number=number, name=name, kind=kind, active=True,
                    filters=filters.model_dump() if filters else {}, weights=weights.model_dump(),
                ))  # fmt: skip
        log.info("Created %d default rooms", len(DEFAULT_ROOMS))

    # -- generation ---------------------------------------------------------

    def ensure_day(self, day: date | None = None) -> int:
        """Generate entries for active rooms that have none on `day`; returns how many were added."""
        day = day or self.today()
        with self.session_factory.begin() as session:
            if session.scalar(select(LibraryItem.id).limit(1)) is None:
                return 0  # library not synced yet; generating now would close every room
            rooms = self._active_rooms(session)
            existing = {e.room_id: e for e in self._entries(session, day)}
            missing = [r for r in rooms if r.id not in existing]
            if not missing:
                return 0
            ctx = self._context(session, day)
            ctx.use_entries(list(existing.values()))
            continued = self._continue_franchises(ctx, [r for r in missing if r.kind == "movie"])
            for entry in continued:
                session.add(entry)
            rest = [r for r in missing if r.id not in {e.room_id for e in continued}]
            for room in self._generation_order(session, ctx, rest):
                session.add(self._generate(session, ctx, room))
        log.info("Programme %s: generated %d rooms", day, len(missing))
        return len(missing)

    def reroll(self, room_number: int | None = None, day: date | None = None) -> None:
        """Pick new titles for one room (or the whole day), avoiding the titles they had."""
        day = day or self.today()
        with self.session_factory.begin() as session:
            entries = {e.room_id: e for e in self._entries(session, day)}
            rooms = [r for r in self._active_rooms(session) if room_number is None or r.number == room_number]
            if room_number is not None and not rooms:
                raise ProgrammeError(f"No active room {room_number}")
            ctx = self._context(session, day)
            rerolled = {r.id for r in rooms}
            ctx.use_entries([e for room_id, e in entries.items() if room_id not in rerolled])
            for room_id, entry in entries.items():
                if room_id in rerolled:
                    ctx.avoid |= set(_entry_items(entry))
            for room in rooms:
                if room.id in entries:
                    session.delete(entries[room.id])
            session.flush()
            for room in self._generation_order(session, ctx, rooms):
                session.add(self._generate(session, ctx, room))

    def swap(self, room_number: int, item_id: str, day: date | None = None) -> None:
        """Override: show a specific title in a room today."""
        day = day or self.today()
        with self.session_factory.begin() as session:
            room = self._room(session, room_number)
            item = session.get(LibraryItem, item_id)
            if item is None:
                raise ProgrammeError("Unknown title")
            if item.type != room.kind:
                raise ProgrammeError(f"{room.name} shows {room.kind}, not {item.type}")
            entries = self._entries(session, day)
            if any(item_id in _entry_items(e) and e.room_id != room.id for e in entries):
                raise ProgrammeError(f"{item.name} already runs in another room today")
            for entry in entries:
                if entry.room_id == room.id:
                    session.delete(entry)
            session.flush()
            session.add(self._entry(day, room, item, "override"))

    def drop_series(self, room_number: int) -> None:
        """Release a sticky series from its room and pick something else for today."""
        with self.session_factory.begin() as session:
            room = self._room(session, room_number)
            assignment = self._active_assignment(session, room.id)
            if assignment is None:
                raise ProgrammeError(f"{room.name} has no sticky series")
            assignment.dropped_at = self.clock()
        self.reroll(room_number)

    def mark_playing(self, room_id: int, item_id: str) -> None:
        """A show from this room started playing: sold out (movies) / sticky (series).

        A franchise part advances its run; if the room offered it as the next part,
        the room's marathon moves on to it.
        """
        day = self.today()
        now = self.clock()
        with self.session_factory.begin() as session:
            room = session.get(Room, room_id)
            entry = session.scalar(
                select(ProgrammeEntry).where(ProgrammeEntry.cinema_date == day, ProgrammeEntry.room_id == room_id)
            )
            if room is None or entry is None:
                return
            index = self._franchise_index(session)
            if item_id not in _entry_items(entry):
                offer = self._offer(session, index, room, entry, day)
                if offer.next is None or offer.next.id != item_id:
                    return
                entry.marathon = [*entry.marathon, item_id]
                log.info("Marathon in %s continues with %s", room.name, offer.next.name)
            if entry.first_started_at is None:
                entry.first_started_at = now
            entry.last_started_at = now
            if room.kind == "series" and self._active_assignment(session, room_id) is None:
                session.add(SeriesAssignment(room_id=room_id, series_id=item_id, started_at=now))
                log.info("Series %s is now sticky in %s", item_id, room.name)
            if franchise := index.franchise_of(item_id):
                run = franchises.advance(franchise, franchise.run, item_id, now)
                if run is not None:
                    session.add(run)
                    log.info("Franchise %s: started parts %s%s", franchise.name, run.started_parts,
                             " (finale; resting)" if run.finished_at else "")  # fmt: skip

    def franchise_room(self) -> tuple[int, str, str | None] | None:
        """The room of the franchise movie started most recently today: (room number, franchise, next item id).

        This is where the franchise cassette continues; None if no franchise movie started today.
        """
        day = self.today()
        with self.session_factory() as session:
            index = self._franchise_index(session)
            entries = session.scalars(
                select(ProgrammeEntry)
                .where(ProgrammeEntry.cinema_date == day, ProgrammeEntry.last_started_at.is_not(None))
                .order_by(ProgrammeEntry.last_started_at.desc())
            ).all()
            for entry in entries:
                room = session.get(Room, entry.room_id)
                franchise = index.franchise_of(_current_item(entry))
                if room is None or not room.active or franchise is None:
                    continue
                offer = self._offer(session, index, room, entry, day)
                return room.number, franchise.name, offer.next.id if offer.next else None
        return None

    # -- reading ------------------------------------------------------------

    def room_offer(self, room_number: int) -> tuple[Room, "Offer"]:
        """What a room offers today: its current title and, during a franchise marathon, the next part."""
        day = self.today()
        with self.session_factory() as session:
            room = self._room(session, room_number)
            entry = session.scalar(
                select(ProgrammeEntry).where(ProgrammeEntry.cinema_date == day, ProgrammeEntry.room_id == room.id)
            )
            if entry is None:
                return room, Offer(None, None)
            return room, self._offer(session, self._franchise_index(session), room, entry, day)

    def day_view(self, day: date | None = None) -> dict:
        day = day or self.today()
        with self.session_factory() as session:
            entries = {e.room_id: e for e in self._entries(session, day)}
            index = self._franchise_index(session)
            rooms = []
            for room in self._active_rooms(session):
                entry = entries.get(room.id)
                offer = self._offer(session, index, room, entry, day) if entry else Offer(None, None)
                item = offer.current
                assignment = self._active_assignment(session, room.id) if room.kind == "series" else None
                rooms.append({
                    "number": room.number,
                    "name": room.name,
                    "kind": room.kind,
                    "item": _item_view(item, index) if item else None,
                    "next": _item_view(offer.next, index) if offer.next else None,
                    "marathon": len(entry.marathon) if entry else 0,
                    "showtimes": entry.showtimes if entry else [],
                    "source": entry.source if entry else None,
                    "started": bool(entry and entry.first_started_at),
                    "sold_out": bool(room.kind == "movie" and entry and entry.first_started_at and not offer.next),
                    "sticky": bool(assignment and item and assignment.series_id == item.id),
                })  # fmt: skip
        return {"date": day.isoformat(), "rooms": rooms}

    def franchise_index(self) -> FranchiseIndex:
        with self.session_factory() as session:
            return self._franchise_index(session)

    def franchise_badge(self, item_id: str) -> dict | None:
        with self.session_factory() as session:
            return self._franchise_index(session).badge(item_id)

    # -- internals ----------------------------------------------------------

    def _franchise_index(self, session: Session, items: list[LibraryItem] | None = None) -> FranchiseIndex:
        if items is None:  # only movies in a collection matter
            collection = func.json_extract(LibraryItem.provider_ids, f"$.{franchises.COLLECTION}")
            items = session.scalars(
                select(LibraryItem).where(LibraryItem.type == "movie", collection.is_not(None))
            ).all()
        return franchises.build_index(
            items,
            session.scalars(select(Franchise)).all(),
            session.scalars(select(FranchiseRun)).all(),
            dict(session.execute(select(LibraryCollection.id, LibraryCollection.name)).all()),
            self.clock(),
            self.settings.get(),
        )

    def _offer(self, session: Session, index: FranchiseIndex, room: Room, entry: ProgrammeEntry, day: date) -> "Offer":
        current_id = _current_item(entry)
        current = session.get(LibraryItem, current_id) if current_id else None
        if current is None or room.kind != "movie" or entry.first_started_at is None or day != self.today():
            return Offer(current, None)
        franchise = index.franchise_of(current.id)
        if franchise is None or franchise.state != "started":
            return Offer(current, None)  # not a franchise, or the finale: sold out
        filters = MovieFilters.model_validate(room.filters or {})
        follow_up = next((i for i in franchise.next_part.items if filters.matches(i)), None)
        return Offer(current, follow_up)

    def _continue_franchises(self, ctx: _Context, rooms: list[Room]) -> list[ProgrammeEntry]:
        """Before the normal picks: each started franchise rolls its daily chance to continue,
        in a random free movie room whose filters accept its next part."""
        free = list(rooms)
        chance = ctx.settings.franchise_continue_chance
        runs = ctx.franchises.started()
        self.rng.shuffle(runs)
        added = []
        for franchise in runs:
            if not free or self.rng.random() * 100 >= chance:
                continue
            fits = []
            for room in free:
                filters = MovieFilters.model_validate(room.filters or {})
                copy = next((i for i in franchise.next_part.items if i.id not in ctx.used and filters.matches(i)), None)
                if copy:
                    fits.append((room, copy))
            if not fits:
                continue
            room, item = self.rng.choice(fits)
            free.remove(room)
            ctx.use(item.id)
            added.append(self._entry(ctx.day, room, item, "franchise"))
            log.info("Programme %s: %s continues with %s in %s", ctx.day, franchise.name, item.name, room.name)
        return added

    def _active_rooms(self, session: Session) -> list[Room]:
        return list(session.scalars(select(Room).where(Room.active).order_by(Room.number)))

    def _room(self, session: Session, number: int) -> Room:
        room = session.scalar(select(Room).where(Room.number == number))
        if room is None:
            raise ProgrammeError(f"No room {number}")
        return room

    def _entries(self, session: Session, day: date) -> list[ProgrammeEntry]:
        return list(session.scalars(select(ProgrammeEntry).where(ProgrammeEntry.cinema_date == day)))

    def _active_assignment(self, session: Session, room_id: int) -> SeriesAssignment | None:
        return session.scalar(
            select(SeriesAssignment).where(
                SeriesAssignment.room_id == room_id,
                SeriesAssignment.finished_at.is_(None),
                SeriesAssignment.dropped_at.is_(None),
            )
        )

    def _generation_order(self, session: Session, ctx: _Context, rooms: list[Room]) -> list[Room]:
        """Sticky series first (their series are reserved), then the most restrictive rooms,
        so broad rooms cannot use up the few titles a narrow room (e.g. horror) can show."""
        sticky = {r.id for r in rooms if r.kind == "series" and self._active_assignment(session, r.id)}

        def pool_size(room: Room) -> int:
            if room.kind != "movie":
                return len(ctx.series)
            filters = MovieFilters.model_validate(room.filters or {})
            return sum(filters.matches(m) for m in ctx.movies)

        return sorted(rooms, key=lambda r: (r.id not in sticky, pool_size(r), r.number))

    def _context(self, session: Session, day: date) -> _Context:
        items = session.scalars(select(LibraryItem)).all()
        last_shown: dict[str, date] = {}
        history = session.scalars(
            select(ProgrammeEntry).where(ProgrammeEntry.cinema_date < day, ProgrammeEntry.item_id.is_not(None))
        )
        for entry in history:
            for item_id in _entry_items(entry):
                if item_id not in last_shown or entry.cinema_date > last_shown[item_id]:
                    last_shown[item_id] = entry.cinema_date
        movies = [i for i in items if i.type == "movie"]
        return _Context(
            day=day,
            settings=self.settings.get(),
            now=self.clock(),
            movies=movies,
            series={i.id: i for i in items if i.type == "series"},
            last_shown=last_shown,
            franchises=self._franchise_index(session, movies),
        )

    def _generate(self, session: Session, ctx: _Context, room: Room) -> ProgrammeEntry:
        item = self._pick_movie(ctx, room) if room.kind == "movie" else self._pick_series(session, ctx, room)
        if item is None:
            log.warning("Programme %s: %s has nothing to show", ctx.day, room.name)
            return ProgrammeEntry(cinema_date=ctx.day, room_id=room.id, item_id=None, showtimes=[],
                                  source="generated", created_at=ctx.now)  # fmt: skip
        ctx.use(item.id)
        return self._entry(ctx.day, room, item, "generated")

    def _entry(self, day: date, room: Room, item: LibraryItem, source: str) -> ProgrammeEntry:
        runtime = SERIES_SHOWTIME_MINUTES if item.type == "series" else item.runtime_minutes
        return ProgrammeEntry(
            cinema_date=day, room_id=room.id, item_id=item.id, source=source,
            showtimes=fake_showtimes(day, room.number, runtime), created_at=self.clock(),
        )  # fmt: skip

    def _pick_movie(self, ctx: _Context, room: Room) -> LibraryItem | None:
        filters = MovieFilters.model_validate(room.filters or {})
        weights = Weights.model_validate(room.weights or {})
        # The order rule is never relaxed: only the next part of a franchise is ever a candidate.
        pool = [
            m for m in ctx.movies if m.id not in ctx.used and filters.matches(m) and not ctx.franchises.blocked(m.id)
        ]
        candidates = _relax(pool, ctx, ctx.settings.movie_cooldown_days)
        if not candidates:
            return None
        bias = [weights.weight(m, ctx.now, m.id in ctx.last_shown) for m in candidates]
        return self.rng.choices(candidates, weights=bias)[0]

    def _pick_series(self, session: Session, ctx: _Context, room: Room) -> LibraryItem | None:
        assignment = self._active_assignment(session, room.id)
        if assignment:
            series = ctx.series.get(assignment.series_id)
            if series is None or series.played:
                assignment.finished_at = ctx.now  # watched to the end (or gone from the library)
                log.info("Series %s finished in %s", assignment.series_id, room.name)
            elif series.id not in ctx.used:
                return series

        sticky_elsewhere = set(session.scalars(
            select(SeriesAssignment.series_id).where(
                SeriesAssignment.room_id != room.id,
                SeriesAssignment.finished_at.is_(None),
                SeriesAssignment.dropped_at.is_(None),
            )
        ))  # fmt: skip
        pool = sorted(  # stable order, so seeded tests are deterministic
            (s for s in ctx.series.values() if not s.played and s.id not in ctx.used | sticky_elsewhere),
            key=lambda s: s.id,
        )
        candidates = _relax(pool, ctx, ctx.settings.series_cooldown_days)
        return self.rng.choice(candidates) if candidates else None


@dataclass
class Offer:
    current: LibraryItem | None  # the room's title (during a marathon: the part started last)
    next: LibraryItem | None  # the next franchise part, offered after `current` started today


def _entry_items(entry: ProgrammeEntry) -> list[str]:
    return ([entry.item_id] if entry.item_id else []) + list(entry.marathon or [])


def _current_item(entry: ProgrammeEntry) -> str | None:
    return entry.marathon[-1] if entry.marathon else entry.item_id


def _relax(pool: list[LibraryItem], ctx: _Context, cooldown_days: int) -> list[LibraryItem]:
    """Strictest non-empty candidate set: fresh and not avoided, then not avoided, then anything."""
    not_avoided = [i for i in pool if i.id not in ctx.avoid]
    fresh = [i for i in not_avoided if not ctx.in_cooldown(i.id, cooldown_days)]
    return fresh or not_avoided or pool


def _item_view(item: LibraryItem, index: FranchiseIndex | None = None) -> dict:
    return {
        "id": item.id,
        "type": item.type,
        "name": item.name,
        "year": item.year,
        "runtime_minutes": item.runtime_minutes,
        "genres": item.genres,
        "overview": item.overview,
        "tagline": item.tagline,
        "official_rating": item.official_rating,
        "community_rating": item.community_rating,
        "poster_tag": item.image_tags.get("Primary"),
        "backdrop_tag": item.image_tags.get("Backdrop"),
        "logo_tag": item.image_tags.get("Logo"),
        "played": item.played,
        "favorite": item.favorite,
        "unplayed_count": item.unplayed_count,
        "trailer_urls": item.trailer_urls,
        "franchise": index.badge(item.id) if index else None,
    }
