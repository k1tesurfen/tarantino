"""The daily programme: one title per room per cinema day.

Generation is idempotent: `ensure_day` only fills rooms that have no entry for
the day yet, so it can run at the rollover, at startup and on every request.
"""

import logging
import math
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from tarantino.models import LibraryItem, ProgrammeEntry, Room, SeriesAssignment
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
    used: set[str] = field(default_factory=set)  # taken by another room on `day` (hard exclusion)
    avoid: set[str] = field(default_factory=set)  # steer away from these (soft; e.g. the title being rerolled)

    def in_cooldown(self, item_id: str, days: int) -> bool:
        last = self.last_shown.get(item_id)
        return last is not None and (self.day - last).days < days


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
            ctx.used |= {e.item_id for e in existing.values() if e.item_id}
            for room in self._generation_order(session, ctx, missing):
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
            for room_id, entry in entries.items():
                if entry.item_id:
                    if any(r.id == room_id for r in rooms):
                        ctx.avoid.add(entry.item_id)
                    else:
                        ctx.used.add(entry.item_id)
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
            if any(e.item_id == item_id and e.room_id != room.id for e in entries):
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
        """A show from this room started playing: sold out (movies) / sticky (series)."""
        day = self.today()
        with self.session_factory.begin() as session:
            room = session.get(Room, room_id)
            entry = session.scalar(
                select(ProgrammeEntry).where(ProgrammeEntry.cinema_date == day, ProgrammeEntry.room_id == room_id)
            )
            if room is None or entry is None or entry.item_id != item_id:
                return
            if entry.first_started_at is None:
                entry.first_started_at = self.clock()
            if room.kind == "series" and self._active_assignment(session, room_id) is None:
                session.add(SeriesAssignment(room_id=room_id, series_id=item_id, started_at=self.clock()))
                log.info("Series %s is now sticky in %s", item_id, room.name)

    # -- reading ------------------------------------------------------------

    def entry_for_room(self, room_number: int, day: date | None = None) -> tuple[Room, ProgrammeEntry | None]:
        day = day or self.today()
        with self.session_factory() as session:
            room = self._room(session, room_number)
            entry = session.scalar(
                select(ProgrammeEntry).where(ProgrammeEntry.cinema_date == day, ProgrammeEntry.room_id == room.id)
            )
            return room, entry

    def day_view(self, day: date | None = None) -> dict:
        day = day or self.today()
        with self.session_factory() as session:
            entries = {e.room_id: e for e in self._entries(session, day)}
            rooms = []
            for room in self._active_rooms(session):
                entry = entries.get(room.id)
                item = session.get(LibraryItem, entry.item_id) if entry and entry.item_id else None
                assignment = self._active_assignment(session, room.id) if room.kind == "series" else None
                rooms.append({
                    "number": room.number,
                    "name": room.name,
                    "kind": room.kind,
                    "item": _item_view(item) if item else None,
                    "showtimes": entry.showtimes if entry else [],
                    "source": entry.source if entry else None,
                    "sold_out": bool(room.kind == "movie" and entry and entry.first_started_at),
                    "sticky": bool(assignment and item and assignment.series_id == item.id),
                })  # fmt: skip
        return {"date": day.isoformat(), "rooms": rooms}

    # -- internals ----------------------------------------------------------

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
        history = session.execute(
            select(ProgrammeEntry.item_id, ProgrammeEntry.cinema_date).where(
                ProgrammeEntry.cinema_date < day, ProgrammeEntry.item_id.is_not(None)
            )
        )
        for item_id, shown_on in history:
            if item_id not in last_shown or shown_on > last_shown[item_id]:
                last_shown[item_id] = shown_on
        return _Context(
            day=day,
            settings=self.settings.get(),
            now=self.clock(),
            movies=[i for i in items if i.type == "movie"],
            series={i.id: i for i in items if i.type == "series"},
            last_shown=last_shown,
        )

    def _generate(self, session: Session, ctx: _Context, room: Room) -> ProgrammeEntry:
        item = self._pick_movie(ctx, room) if room.kind == "movie" else self._pick_series(session, ctx, room)
        if item is None:
            log.warning("Programme %s: %s has nothing to show", ctx.day, room.name)
            return ProgrammeEntry(cinema_date=ctx.day, room_id=room.id, item_id=None, showtimes=[],
                                  source="generated", created_at=ctx.now)  # fmt: skip
        ctx.used.add(item.id)
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
        pool = [m for m in ctx.movies if m.id not in ctx.used and filters.matches(m)]
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


def _relax(pool: list[LibraryItem], ctx: _Context, cooldown_days: int) -> list[LibraryItem]:
    """Strictest non-empty candidate set: fresh and not avoided, then not avoided, then anything."""
    not_avoided = [i for i in pool if i.id not in ctx.avoid]
    fresh = [i for i in not_avoided if not ctx.in_cooldown(i.id, cooldown_days)]
    return fresh or not_avoided or pool


def _item_view(item: LibraryItem) -> dict:
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
    }
