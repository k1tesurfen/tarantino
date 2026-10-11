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
    ItemRef,
    ProgrammeEntryExport,
    RoomExport,
    SeriesAssignmentExport,
    StateExport,
    migrate_document,
)
from tarantino.models import Cassette, LibraryItem, ProgrammeEntry, Room, SeriesAssignment, Setting
from tarantino.settings import SettingsStore

log = logging.getLogger(__name__)

PROVIDERS = ("Tmdb", "Imdb", "Tvdb")


def _ref(item: LibraryItem | None, item_id: str, item_type: str) -> ItemRef:
    if item is None:  # no longer in the library; keep the id so it can still match later
        return ItemRef(id=item_id, type=item_type, name="(unknown)")
    return ItemRef(id=item.id, type=item.type, name=item.name, year=item.year, provider_ids=item.provider_ids or {})


def export_config(session_factory: sessionmaker, settings: SettingsStore, include_state: bool = True) -> ConfigExport:
    with session_factory() as session:
        rooms = session.scalars(select(Room).order_by(Room.number)).all()
        numbers = {r.id: r.number for r in rooms}
        kinds = {r.id: r.kind for r in rooms}
        library = {i.id: i for i in session.scalars(select(LibraryItem))}
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
                        created_at=e.created_at,
                    )  # fmt: skip
                    for e in session.scalars(select(ProgrammeEntry).order_by(ProgrammeEntry.cinema_date))
                ],
            )
        return ConfigExport(
            tarantino_version=__version__,
            exported_at=datetime.now(),
            settings=settings.get(),
            rooms=[RoomExport.model_validate(r, from_attributes=True) for r in rooms],
            cassettes=[
                CassetteExport(uid=c.uid, room_number=numbers[c.room_id], learned_at=c.learned_at)
                for c in session.scalars(select(Cassette).order_by(Cassette.uid))
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


@dataclass
class ImportPreview:
    settings_changed: dict[str, dict] = field(default_factory=dict)  # key -> {"from", "to"}
    rooms_added: list[str] = field(default_factory=list)
    rooms_removed: list[str] = field(default_factory=list)
    rooms_changed: list[str] = field(default_factory=list)
    cassettes_changed: list[str] = field(default_factory=list)  # "UID: room a -> room b"
    state_included: bool = False
    series_assignments: int = 0
    programme_entries: int = 0
    unresolved_titles: list[str] = field(default_factory=list)
    remapped_titles: int = 0
    exported_at: str = ""
    tarantino_version: str = ""


def _room_label(number: int, name: str) -> str:
    return f"{number} · {name}"


def _room_or_none(number: int | None) -> str:
    return f"room {number}" if number is not None else "none"


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
        current_cassettes = {c.uid: numbers[c.room_id] for c in session.scalars(select(Cassette))}
        incoming_cassettes = {c.uid: c.room_number for c in export.cassettes}
        for uid in sorted(current_cassettes.keys() | incoming_cassettes.keys()):
            before, after = current_cassettes.get(uid), incoming_cassettes.get(uid)
            if before != after:
                preview.cassettes_changed.append(f"{uid}: {_room_or_none(before)} → {_room_or_none(after)}")

        if export.state:
            resolver = ItemResolver(session)
            preview.series_assignments = len(export.state.series_assignments)
            preview.programme_entries = len(export.state.programme)
            refs = [a.series for a in export.state.series_assignments]
            refs += [e.item for e in export.state.programme if e.item]
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
            if c.room_number in room_ids:
                session.add(Cassette(uid=c.uid, room_id=room_ids[c.room_number], learned_at=c.learned_at))

        if export.state is None:
            return
        resolver = ItemResolver(session)
        session.execute(delete(SeriesAssignment))
        session.execute(delete(ProgrammeEntry))
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
            session.add(ProgrammeEntry(
                cinema_date=e.cinema_date, room_id=room_ids[e.room_number], item_id=item_id,
                showtimes=e.showtimes, source=e.source, first_started_at=e.first_started_at,
                created_at=e.created_at,
            ))  # fmt: skip
    log.info("Imported configuration exported at %s", export.exported_at)

