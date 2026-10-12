import asyncio

from sqlalchemy import select

from conftest import FakeJellyfin, movie, series
from tarantino.db import create_db_engine, make_session_factory, migrate
from tarantino.jellyfin import client as client_module
from tarantino.jellyfin.client import JellyfinClient
from tarantino.jellyfin.library import LibrarySync
from tarantino.models import LibraryItem


def make_sync(tmp_path, fake: FakeJellyfin, user: str | None = "Viewer") -> LibrarySync:
    engine = create_db_engine(tmp_path / "data")
    migrate(engine)
    jellyfin = JellyfinClient("http://jellyfin", fake.api_key, transport=fake.transport)
    return LibrarySync(jellyfin, make_session_factory(engine), user)


def all_items(sync: LibrarySync) -> dict[str, LibraryItem]:
    with sync.session_factory() as session:
        return {i.id: i for i in session.scalars(select(LibraryItem))}


def test_sync_maps_fields(tmp_path, fake_jellyfin):
    sync = make_sync(tmp_path, fake_jellyfin)
    result = asyncio.run(sync.run())
    assert (result.movies, result.series, result.removed) == (7, 2, 0)

    items = all_items(sync)
    m3 = items[f"{3:032x}"]
    assert m3.type == "movie"
    assert m3.year == 1993
    assert m3.premiere_date.isoformat() == "1993-05-01"
    assert m3.runtime_minutes == 165
    assert m3.genres == ["Horror"]
    assert m3.played and m3.favorite and m3.play_count == 1
    assert m3.image_tags == {"Primary": "p3", "Backdrop": "b3"}
    assert m3.trailer_urls == ["https://www.youtube.com/watch?v=abc"]
    assert m3.provider_ids == {"Tmdb": "3"}
    assert m3.tagline == "Tagline."
    assert m3.people[0] == {"name": "Director Person", "role": None, "type": "Director"}
    assert len(m3.people) == 11  # director + 10 actors

    finished = items[f"{101:032x}"]
    assert finished.type == "series" and finished.played and finished.unplayed_count == 0
    assert finished.episode_count == 20


def test_sync_paginates(tmp_path, monkeypatch):
    monkeypatch.setattr(client_module, "PAGE_SIZE", 3)
    fake = FakeJellyfin([movie(n) for n in range(1, 11)])
    sync = make_sync(tmp_path, fake)
    assert asyncio.run(sync.run()).movies == 10
    item_pages = [r for r in fake.requests if r.url.path == "/Items" and "BoxSet" not in r.url.params["includeItemTypes"]]
    assert len(item_pages) == 4


def test_sync_updates_and_removes(tmp_path):
    fake = FakeJellyfin([movie(1), movie(2), series(5)])
    sync = make_sync(tmp_path, fake)
    asyncio.run(sync.run())

    fake.items = [movie(1, Name="Renamed", UserData={"Played": True}), series(5, unplayed=0)]
    result = asyncio.run(sync.run())
    assert result.removed == 1

    items = all_items(sync)
    assert set(items) == {f"{1:032x}", f"{5:032x}"}
    assert items[f"{1:032x}"].name == "Renamed"
    assert items[f"{1:032x}"].played
    assert items[f"{5:032x}"].unplayed_count == 0


def test_empty_response_never_wipes_cache(tmp_path):
    fake = FakeJellyfin([movie(1)])
    sync = make_sync(tmp_path, fake)
    asyncio.run(sync.run())
    fake.items = []
    assert asyncio.run(sync.run()) is None
    assert "no movies or series" in sync.last_error
    assert len(all_items(sync)) == 1


def test_wrong_api_key_is_recorded(tmp_path):
    fake = FakeJellyfin([movie(1)])
    sync = make_sync(tmp_path, fake)
    sync.client = JellyfinClient("http://jellyfin", "wrong", transport=fake.transport)
    assert asyncio.run(sync.run()) is None
    assert "rejected the API key" in sync.last_error


def test_unknown_user_is_recorded(tmp_path):
    sync = make_sync(tmp_path, FakeJellyfin([movie(1)]), user="nobody")
    assert asyncio.run(sync.run()) is None
    assert "user 'nobody' not found" in sync.last_error


def test_status_and_sample_and_images(client):
    status = client.get("/api/admin/status").json()["jellyfin"]
    assert status["state"] == "ok"
    assert status["version"] == "12.1.0"
    assert status["counts"] == {}

    assert client.post("/api/admin/library/sync").status_code == 202
    status = client.get("/api/admin/status").json()["jellyfin"]
    assert status["counts"] == {"movie": 7, "series": 2}
    assert status["sync"]["last_sync_at"]

    sample = client.get("/api/admin/library/sample?count=5").json()
    assert len(sample) == 5
    first = sample[0]
    response = client.get(f"/api/img/{first['id']}/Primary?w=300&tag={first['poster_tag']}")
    assert response.status_code == 200
    assert response.content.startswith(b"\x89PNG")
    assert "immutable" in response.headers["cache-control"]


def test_image_proxy_validation(client):
    assert client.get("/api/img/not-an-id/Primary").status_code == 422
    assert client.get(f"/api/img/{1:032x}/Banner").status_code == 422
    assert client.get(f"/api/img/{999:032x}/Primary").status_code == 404
