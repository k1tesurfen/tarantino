import json

import pytest
from sqlalchemy import delete, select

from tarantino.configio import schema
from tarantino.configio.backups import KEEP_PER_REASON, BackupStore
from tarantino.configio.transfer import apply_import, export_config, parse_export, preview_import
from tarantino.db import Base
from tarantino.models import LibraryItem, ProgrammeEntry, Room, SeriesAssignment, Setting
from tarantino.programme.rules import MovieFilters, Weights
from tarantino.settings import AppSettings, SettingsStore
from test_programme import item, room_id, standard_library, world  # noqa: F401 (fixture)


def configured(w):
    """A world with custom settings, an edited room, a sticky series and some history."""
    standard_library(w)
    store = SettingsStore(w.session_factory)
    store.update({"theme_modern_name": "Odeon", "rollover_hour": 6, "media_paths": ["/media/a"]})
    with w.session_factory.begin() as session:
        room = session.scalar(select(Room).where(Room.number == 4))
        room.name, room.filters = "Grindhouse", {"watched": "unwatched", "genres_any": ["Horror"], "year_max": 1990}
    w.programme.ensure_day()
    series_id = w.entries()[8]
    w.programme.mark_playing(room_id(w, 8), series_id)
    w.clock.next_day()
    w.programme.ensure_day()
    return store


def snapshot(w) -> dict:
    """The effective configuration and state (normalised, independent of storage details)."""
    with w.session_factory() as session:
        return {
            "settings": SettingsStore(w.session_factory).get().model_dump(),
            "rooms": sorted(
                (r.number, r.name, r.kind, r.active,
                 MovieFilters.model_validate(r.filters).model_dump_json(),
                 Weights.model_validate(r.weights).model_dump_json())
                for r in session.scalars(select(Room))
            ),  # fmt: skip
            "assignments": sorted((a.series_id, a.started_at) for a in session.scalars(select(SeriesAssignment))),
            "programme": sorted((str(e.cinema_date), e.room_id, e.item_id or "", tuple(e.showtimes))
                                for e in session.scalars(select(ProgrammeEntry))),  # fmt: skip
        }


def wipe(w) -> None:
    with w.session_factory.begin() as session:
        for model in (ProgrammeEntry, SeriesAssignment, Room, Setting):
            session.execute(delete(model))


def test_every_table_is_classified_for_export():
    tables = set(Base.metadata.tables) | {"alembic_version"}
    classified = [schema.CONFIG_TABLES, schema.STATE_TABLES, schema.REBUILDABLE_TABLES]
    assert set().union(*classified) == tables, "classify new tables in tarantino/configio/schema.py"
    assert sum(len(c) for c in classified) == len(tables), "a table is classified twice"


def test_export_covers_every_room_column_and_setting():
    room_columns = {c.name for c in Room.__table__.columns} - {"id"}
    assert room_columns == set(schema.RoomExport.model_fields)
    assert schema.ConfigExport.model_fields["settings"].annotation is AppSettings


def test_roundtrip_restores_identical_configuration(world):
    store = configured(world)
    before = snapshot(world)
    document = json.loads(export_config(world.session_factory, store).model_dump_json())
    assert "password" not in json.dumps(document).lower() and "token" not in json.dumps(document).lower()

    wipe(world)
    apply_import(world.session_factory, parse_export(document))
    assert snapshot(world) == before


def test_export_without_state(world):
    store = configured(world)
    export = export_config(world.session_factory, store, include_state=False)
    assert export.state is None
    before = snapshot(world)
    apply_import(world.session_factory, export)
    assert snapshot(world) == before  # existing state is kept when the export has none


def test_preview_lists_changes(world):
    store = configured(world)
    export = export_config(world.session_factory, store)
    export.settings.theme_retro_name = "Grindhouse Palace"
    export.rooms = [r for r in export.rooms if r.number != 10]
    export.rooms[0].name = "Premiere Deluxe"
    export.rooms.append(schema.RoomExport(number=11, name="Midnight Movies", kind="movie"))

    preview = preview_import(world.session_factory, store, export)
    assert preview.settings_changed == {"theme_retro_name": {"from": "Red Apple Cinema", "to": "Grindhouse Palace"}}
    assert preview.rooms_added == ["11 · Midnight Movies"]
    assert preview.rooms_removed == ["10 · Series Lounge IV"]
    assert preview.rooms_changed == ["1 · Premiere Deluxe"]
    assert preview.state_included and preview.series_assignments == 1
    assert preview.unresolved_titles == []


def test_titles_are_remapped_after_a_library_rebuild(world):
    store = configured(world)
    export = export_config(world.session_factory, store)
    series_id = export.state.series_assignments[0].series.id
    sticky = export.state.series_assignments[0].series

    # Jellyfin rebuilt: the sticky series has a new id but the same TMDB id; another title vanished.
    with world.session_factory.begin() as session:
        old = session.get(LibraryItem, series_id)
        session.delete(old)
    world.add(item(9000, "series", name=sticky.name, provider_ids={"Tmdb": "424242"}))
    sticky.provider_ids = {"Tmdb": "424242"}
    gone = next(e.item for e in export.state.programme if e.item and e.item.type == "movie")
    gone.id, gone.name, gone.year, gone.provider_ids = "f" * 32, "Lost Film", 1971, {}

    preview = preview_import(world.session_factory, store, export)
    assert preview.remapped_titles >= 1
    assert preview.unresolved_titles == ["Lost Film (1971)"]

    apply_import(world.session_factory, export)
    with world.session_factory() as session:
        assert session.scalar(select(SeriesAssignment.series_id)) == f"{9000:032x}"
        assert "f" * 32 not in {e.item_id for e in session.scalars(select(ProgrammeEntry))}


def test_rooms_are_updated_in_place(world):
    store = configured(world)
    export = export_config(world.session_factory, store, include_state=False)
    ids_before = {r.number: room_id(world, r.number) for r in export.rooms}
    export.rooms[0].name = "Renamed"
    apply_import(world.session_factory, export)
    assert {n: room_id(world, n) for n in ids_before} == ids_before


def test_rejects_foreign_or_future_documents(world):
    with pytest.raises(ValueError, match="missing schema_version"):
        parse_export({"hello": "world"})
    with pytest.raises(ValueError, match="newer tarantino"):
        parse_export({"schema_version": schema.SCHEMA_VERSION + 1})


def test_backups_rotate_per_reason(world, tmp_path, monkeypatch):
    store = BackupStore(tmp_path / "backups", world.session_factory, SettingsStore(world.session_factory))
    stamps = iter(range(100))

    import tarantino.configio.backups as backups_module

    class FakeDatetime(backups_module.datetime):
        @classmethod
        def now(cls, tz=None):
            return backups_module.datetime(2026, 1, 1, 0, 0, next(stamps))

    monkeypatch.setattr(backups_module, "datetime", FakeDatetime)
    for _ in range(KEEP_PER_REASON + 3):
        store.create("nightly")
    store.create("manual")
    listed = store.list()
    assert [b.reason for b in listed].count("nightly") == KEEP_PER_REASON
    assert [b.reason for b in listed].count("manual") == 1
    assert parse_export(store.read(listed[0].name)).rooms

    with pytest.raises(FileNotFoundError):
        store.path("../secret.key")
    with pytest.raises(ValueError):
        store.create("whenever")


def test_config_api_roundtrip(client):
    client.post("/api/admin/library/sync")
    client.patch("/api/admin/settings", json={"theme_retro_name": "Pulp Playhouse"})
    exported = client.get("/api/admin/config/export")
    assert "attachment" in exported.headers["content-disposition"]
    document = exported.json()

    client.patch("/api/admin/settings", json={"theme_retro_name": "Something Else"})
    preview = client.post("/api/admin/config/import/preview", json=document).json()
    assert preview["settings_changed"]["theme_retro_name"]["to"] == "Pulp Playhouse"

    result = client.post("/api/admin/config/import", json=document).json()
    assert result["backup"].endswith("-pre-import.tarantino.json")
    assert client.get("/api/admin/settings").json()["theme_retro_name"] == "Pulp Playhouse"

    backups = client.get("/api/admin/backups").json()
    assert backups[0]["reason"] == "pre-import"
    assert client.get(f"/api/admin/backups/{backups[0]['name']}").json()["settings"]["theme_retro_name"] == (
        "Something Else"
    )
    assert client.post(f"/api/admin/backups/{backups[0]['name']}/restore").status_code == 200
    assert client.get("/api/admin/settings").json()["theme_retro_name"] == "Something Else"
    assert client.get("/api/admin/backups/..%2Fsecret.key").status_code == 404
    assert client.post("/api/admin/config/import", json={"nope": 1}).status_code == 422
