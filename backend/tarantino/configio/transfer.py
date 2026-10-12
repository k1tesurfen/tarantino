"""Export, preview and import of the whole admin configuration."""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from tarantino import __version__
from tarantino.configio.schema import (
    CassetteExport,
    ConfigExport,
    FranchiseExport,
    FranchiseRunExport,
    ItemRef,
    ProgrammeEntryExport,
    RoomExport,
    SeriesAssignmentExport,
    StateExport,
    migrate_document,
)
from tarantino.models import (
    Cassette,
    Franchise,
    FranchiseRun,
    LibraryCollection,
    LibraryItem,
    ProgrammeEntry,
    Room,
    SeriesAssignment,
    Setting,
)
from tarantino.programme.franchises import part_key
from tarantino.settings import SettingsStore

log = logging.getLogger(__name__)

PROVIDERS = ("Tmdb", "Imdb", "Tvdb")


def _ref(item: LibraryItem | None, item_id: str, item_type: str) -> ItemRef:
    if item is None:  # no longer in the library; keep the id so it can still match later
        return ItemRef(id=item_id, type=item_type, name="(unknown)")
    return ItemRef(id=item.id, type=item.type, name=item.name, year=item.year, provider_ids=item.provider_ids or {})


def _part_refs(library: dict[str, LibraryItem]) -> dict[str, LibraryItem]:
    """Franchise part key -> a library item of that part."""
    refs: dict[str, LibraryItem] = {}
    for item in sorted(library.values(), key=lambda i: i.id):
        if item.type == "movie":
            refs.setdefault(part_key(item), item)
    return refs


def _part_ref(key: str, refs: dict[str, LibraryItem]) -> ItemRef:
    if key in refs:
        return _ref(refs[key], key, "movie")
    if key.startswith("item:"):
        return ItemRef(id=key.removeprefix("item:"), type="movie", name="(unknown)")
    return ItemRef(id="", type="movie", name="(unknown)", provider_ids={"Tmdb": key})


def _franchise_export(f: Franchise, refs: dict[str, LibraryItem]) -> FranchiseExport:
    return FranchiseExport(
        collection_id=f.collection_id, name=f.name, any_order=f.any_order,
        order=[_part_ref(k, refs) for k in f.order], excluded=[_part_ref(k, refs) for k in f.excluded],
    )  # fmt: skip


def export_config(session_factory: sessionmaker, settings: SettingsStore, include_state: bool = True) -> ConfigExport:
    with session_factory() as session:
        rooms = session.scalars(select(Room).order_by(Room.number)).all()
        numbers = {r.id: r.number for r in rooms}
        kinds = {r.id: r.kind for r in rooms}
        library = {i.id: i for i in session.scalars(select(LibraryItem))}
        refs = _part_refs(library)
        state = None
        if include_state:
            state = StateExport(
                series_assignments=[
                    SeriesAssignmentExport(
                        room_number=numbers[a.room_id], series=_ref(library.get(a.series_id), a.series_id, "series"),
                        started_at=a.started_at, finished_at=a.finished_at, dropped_at=a.dropped_at,
                    )  # fmt: skip
                    for a in session.scalars(select(SeriesAssignment).order_by(SeriesAssignment.id))
                ],
                programme=[
                    ProgrammeEntryExport(
                        cinema_date=e.cinema_date, room_number=numbers[e.room_id],
                        item=_ref(library.get(e.item_id), e.item_id, kinds[e.room_id]) if e.item_id else None,
                        showtimes=e.showtimes, source=e.source, first_started_at=e.first_started_at,
                        marathon=[_ref(library.get(i), i, "movie") for i in e.marathon],
                        last_started_at=e.last_started_at, created_at=e.created_at,
                    )  # fmt: skip
                    for e in session.scalars(select(ProgrammeEntry).order_by(ProgrammeEntry.cinema_date))
                ],
                franchise_runs=[
                    FranchiseRunExport(
                        collection_id=r.collection_id, started_parts=[_part_ref(k, refs) for k in r.started_parts],
                        started_at=r.started_at, last_advanced_at=r.last_advanced_at, finished_at=r.finished_at,
                    )  # fmt: skip
                    for r in session.scalars(select(FranchiseRun).order_by(FranchiseRun.collection_id))
                ],
            )
        return ConfigExport(
            tarantino_version=__version__,
            exported_at=datetime.now(),
            settings=settings.get(),
            rooms=[RoomExport.model_validate(r, from_attributes=True) for r in rooms],
            cassettes=[
                CassetteExport(uid=c.uid, target=c.target, room_number=numbers.get(c.room_id), learned_at=c.learned_at)
                for c in session.scalars(select(Cassette).order_by(Cassette.uid))
            ],
            franchises=[
                _franchise_export(f, refs) for f in session.scalars(select(Franchise).order_by(Franchise.collection_id))
            ],
            state=state,
        )


def parse_export(document: dict) -> ConfigExport:
    return ConfigExport.model_validate(migrate_document(dict(document)))


class ItemResolver:
    """Finds titles of an export in the current library: by id, provider id, or name and year."""

    def __init__(self, session: Session):
        self.by_id: dict[str, LibraryItem] = {i.id: i for i in session.scalars(select(LibraryItem))}
        self.by_provider: dict[tuple[str, str, str], str] = {}
        self.by_name: dict[tuple[str, str, int | None], str] = {}
        for item in self.by_id.values():
            for provider in PROVIDERS:
                if value := (item.provider_ids or {}).get(provider):
                    self.by_provider[(item.type, provider, value)] = item.id
            self.by_name.setdefault((item.type, item.name.casefold(), item.year), item.id)

    def resolve(self, ref: ItemRef) -> str | None:
        if ref.id in self.by_id:
            return ref.id
        for provider in PROVIDERS:
            if (value := ref.provider_ids.get(provider)) and (found := self.by_provider.get((ref.type, provider, value))):
                return found
        return self.by_name.get((ref.type, ref.name.casefold(), ref.year))

    def part_key(self, ref: ItemRef) -> str | None:
        """The franchise part key of a movie reference (its TMDb id when known)."""
        if tmdb := ref.provider_ids.get("Tmdb"):
            return str(tmdb)
        if found := self.resolve(ref):
            return part_key(self.by_id[found])
        return f"item:{ref.id}" if ref.id else None

    def part_keys(self, refs: list[ItemRef]) -> list[str]:
        return [k for k in (self.part_key(r) for r in refs) if k]


@dataclass
class ImportPreview:
    settings_changed: dict[str, dict] = field(default_factory=dict)  # key -> {"from", "to"}
    rooms_added: list[str] = field(default_factory=list)
    rooms_removed: list[str] = field(default_factory=list)
    rooms_changed: list[str] = field(default_factory=list)
    cassettes_changed: list[str] = field(default_factory=list)  # "UID: room a -> room b"
    franchises_changed: list[str] = field(default_factory=list)
    state_included: bool = False
    series_assignments: int = 0
    programme_entries: int = 0
    franchise_runs: int = 0
    unresolved_titles: list[str] = field(default_factory=list)
    remapped_titles: int = 0
    exported_at: str = ""
    tarantino_version: str = ""


def _room_label(number: int, name: str) -> str:
    return f"{number} · {name}"


def _cassette_target(target: tuple[str, int | None] | None) -> str:
    if target is None:
        return "none"
    return "franchise" if target[0] == "franchise" else f"room {target[1]}"


def _franchise_state(f: Franchise | FranchiseExport, resolver: "ItemResolver") -> tuple:
    if isinstance(f, FranchiseExport):
        return (f.name or None, f.any_order, resolver.part_keys(f.order), resolver.part_keys(f.excluded))
    return (f.name or None, f.any_order, list(f.order), list(f.excluded))


def preview_import(session_factory: sessionmaker, settings: SettingsStore, export: ConfigExport) -> ImportPreview:
    preview = ImportPreview(
        state_included=export.state is not None,
        exported_at=export.exported_at.isoformat(),
        tarantino_version=export.tarantino_version,
    )
    current = settings.get().model_dump()
    for key, value in export.settings.model_dump().items():
        if current.get(key) != value:
            preview.settings_changed[key] = {"from": current.get(key), "to": value}

    with session_factory() as session:
        existing = {r.number: r for r in session.scalars(select(Room))}
        incoming = {r.number: r for r in export.rooms}
        for number, room in sorted(incoming.items()):
            if number not in existing:
                preview.rooms_added.append(_room_label(number, room.name))
            elif RoomExport.model_validate(existing[number], from_attributes=True) != room:
                preview.rooms_changed.append(_room_label(number, room.name))
        preview.rooms_removed = [_room_label(n, r.name) for n, r in sorted(existing.items()) if n not in incoming]

        numbers = {r.id: r.number for r in existing.values()}
        current_cassettes = {
            c.uid: (c.target, numbers.get(c.room_id)) for c in session.scalars(select(Cassette))
        }
        incoming_cassettes = {
            c.uid: (c.target, c.room_number if c.target == "room" else None) for c in export.cassettes
        }
        for uid in sorted(current_cassettes.keys() | incoming_cassettes.keys()):
            before, after = current_cassettes.get(uid), incoming_cassettes.get(uid)
            if before != after:
                preview.cassettes_changed.append(f"{uid}: {_cassette_target(before)} → {_cassette_target(after)}")

        resolver = ItemResolver(session)
        names = dict(session.execute(select(LibraryCollection.id, LibraryCollection.name)).all())
        current_franchises = {f.collection_id: f for f in session.scalars(select(Franchise))}
        incoming_franchises = {f.collection_id: f for f in export.franchises}
        for cid in sorted(current_franchises.keys() | incoming_franchises.keys()):
            before, after = current_franchises.get(cid), incoming_franchises.get(cid)
            if (before and _franchise_state(before, resolver)) != (after and _franchise_state(after, resolver)):
                name = (after and after.name) or (before and before.name) or names.get(cid) or f"collection {cid}"
                preview.franchises_changed.append(name)

        if export.state:
            preview.series_assignments = len(export.state.series_assignments)
            preview.programme_entries = len(export.state.programme)
            preview.franchise_runs = len(export.state.franchise_runs)
            refs = [a.series for a in export.state.series_assignments]
            refs += [e.item for e in export.state.programme if e.item]
            refs += [m for e in export.state.programme for m in e.marathon]
            unresolved = set()
            for ref in refs:
                found = resolver.resolve(ref)
                if found is None:
                    unresolved.add(f"{ref.name} ({ref.year})" if ref.year else ref.name)
                elif found != ref.id:
                    preview.remapped_titles += 1
            preview.unresolved_titles = sorted(unresolved)
    return preview


def apply_import(session_factory: sessionmaker, export: ConfigExport) -> None:
    """Replace the configuration with the export, in one transaction.

    Rooms are matched by number and updated in place, so their history survives.
    State (if the export has it) replaces the current state; titles that cannot be
    found in the library are skipped.
    """
    with session_factory.begin() as session:
        session.execute(delete(Setting))
        for key, value in export.settings.model_dump().items():
            session.add(Setting(key=key, value=value))

        existing = {r.number: r for r in session.scalars(select(Room))}
        incoming = {r.number for r in export.rooms}
        for number, room in existing.items():
            if number not in incoming:
                session.delete(room)
        for data in export.rooms:
            room = existing.get(data.number) or Room(number=data.number)
            room.name, room.kind, room.active = data.name, data.kind, data.active
            room.filters, room.weights = data.filters.model_dump(), data.weights.model_dump()
            session.add(room)
        session.flush()

        room_ids = {r.number: r.id for r in session.scalars(select(Room))}
        session.execute(delete(Cassette))
        for c in export.cassettes:
            if c.target == "franchise":
                session.add(Cassette(uid=c.uid, target="franchise", room_id=None, learned_at=c.learned_at))
            elif c.room_number in room_ids:
                session.add(Cassette(uid=c.uid, room_id=room_ids[c.room_number], learned_at=c.learned_at))

        resolver = ItemResolver(session)
        session.execute(delete(Franchise))
        for f in export.franchises:
            session.add(Franchise(
                collection_id=f.collection_id, name=f.name, any_order=f.any_order,
                order=resolver.part_keys(f.order), excluded=resolver.part_keys(f.excluded),
            ))  # fmt: skip

        if export.state is None:
            return
        session.execute(delete(SeriesAssignment))
        session.execute(delete(ProgrammeEntry))
        session.execute(delete(FranchiseRun))
        for r in export.state.franchise_runs:
            session.add(FranchiseRun(
                collection_id=r.collection_id, started_parts=resolver.part_keys(r.started_parts),
                started_at=r.started_at, last_advanced_at=r.last_advanced_at, finished_at=r.finished_at,
            ))  # fmt: skip
        for a in export.state.series_assignments:
            series_id = resolver.resolve(a.series)
            if series_id and a.room_number in room_ids:
                session.add(SeriesAssignment(
                    room_id=room_ids[a.room_number], series_id=series_id, started_at=a.started_at,
                    finished_at=a.finished_at, dropped_at=a.dropped_at,
                ))  # fmt: skip
        for e in export.state.programme:
            if e.room_number not in room_ids:
                continue
            item_id = resolver.resolve(e.item) if e.item else None
            if e.item and item_id is None:
                continue
            marathon = [resolver.resolve(m) for m in e.marathon]
            session.add(ProgrammeEntry(
                cinema_date=e.cinema_date, room_id=room_ids[e.room_number], item_id=item_id,
                showtimes=e.showtimes, source=e.source, first_started_at=e.first_started_at,
                marathon=[m for m in marathon if m], last_started_at=e.last_started_at, created_at=e.created_at,
            ))  # fmt: skip
    log.info("Imported configuration exported at %s", export.exported_at)

