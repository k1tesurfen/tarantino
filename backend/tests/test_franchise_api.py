"""M9 through the API: franchise cassette, read guard, admin page, cinema site, export schema 3."""

import time
from datetime import datetime, timedelta

from typer.testing import CliRunner

from conftest import movie, projector_session
from tarantino import cli
from test_vhs import wait_for_show

T = "900"


def franchise_movie(n: int, year: int, **overrides) -> dict:
    return movie(
        n, Name=f"Saga {year}", ProductionYear=year, PremiereDate=f"{year}-06-01T00:00:00.0000000Z",
        Genres=["Comedy"], ProviderIds={"Tmdb": str(n), "TmdbCollection": T},
        UserData={"Played": False, "IsFavorite": False, "PlayCount": 0}, **overrides,
    )  # fmt: skip


def item_id(n: int) -> str:
    return f"{n:032x}"


def setup(client, fake_jellyfin, part_one_in: int = 1):
    """Three parts in the library; part 1 on in room `part_one_in`; the projector is ready."""
    fake_jellyfin.items += [franchise_movie(501, 1984), franchise_movie(502, 1991), franchise_movie(503, 2003)]
    fake_jellyfin.items.append({"Id": "b" * 32, "Type": "BoxSet", "Name": "The Saga Collection",
                                "ProviderIds": {"Tmdb": T}})  # fmt: skip
    fake_jellyfin.sessions.append(projector_session())
    client.post("/api/admin/library/sync")
    assert client.post("/api/admin/programme/swap", json={"room": part_one_in, "item_id": item_id(501)}).is_success
    return client.get("/api/admin/programme").json()


def room(client, number: int, path: str = "/api/admin/programme") -> dict:
    return next(r for r in client.get(path).json()["rooms"] if r["number"] == number)


def insert(client, uid: str) -> dict:
    event = client.post("/api/vhs/insert", json={"uid": uid}).json()
    if event["outcome"] == "played":
        assert wait_for_show(client, event["show_id"])["state"] == "playing"
    return event


def test_franchise_cassette_alternates_with_the_room_cassette(client, fake_jellyfin):
    setup(client, fake_jellyfin)
    client.put("/api/admin/cassettes/FAKE0001", json={"room": 1})
    client.put("/api/admin/cassettes/FAKE00FF", json={"franchise": True})

    idle = insert(client, "FAKE00FF")
    assert (idle["outcome"], idle["message"]) == ("ignored", "No franchise running today")

    assert insert(client, "FAKE0001")["outcome"] == "played"  # part 1
    assert room(client, 1)["next"]["id"] == item_id(502)
    assert insert(client, "FAKE0001")["outcome"] == "ignored"  # the reader fired again

    played = insert(client, "FAKE00FF")  # part 2, in the franchise's room
    assert (played["outcome"], played["room"]) == ("played", 1)
    assert client.get("/api/admin/shows").json()[0]["item_id"] == item_id(502)
    assert insert(client, "FAKE00FF")["outcome"] == "ignored"

    assert insert(client, "FAKE0001")["outcome"] == "played"  # the room offers part 3 now
    assert client.get("/api/admin/shows").json()[0]["item_id"] == item_id(503)
    finale = room(client, 1)
    assert finale["sold_out"] and finale["next"] is None

    done = insert(client, "FAKE00FF")
    assert (done["outcome"], done["message"]) == ("ignored", "The Saga: no next part today")


def test_read_guard_releases_after_another_cassette_or_the_day(client, fake_jellyfin):
    setup(client, fake_jellyfin)
    client.put("/api/admin/cassettes/FAKE0001", json={"room": 1})
    client.put("/api/admin/cassettes/FAKE0002", json={"room": 2})
    assert insert(client, "FAKE0001")["outcome"] == "played"
    assert insert(client, "FAKE0001")["outcome"] == "ignored"
    insert(client, "FAKE0099")  # unknown cassettes do not release the guard
    assert insert(client, "FAKE0001")["outcome"] == "ignored"
    assert insert(client, "FAKE0002")["outcome"] == "played"
    assert insert(client, "FAKE0001")["outcome"] == "played"  # a different cassette was read in between

    cassettes = client.app.state.services.cassettes
    assert cassettes.is_guarded("FAKE0001", datetime.now() - timedelta(hours=1))
    assert not cassettes.is_guarded("FAKE0001", datetime.now() + timedelta(seconds=1))  # a new cinema day


def test_cinema_site_shows_the_badge_and_plays_the_next_part(client, fake_jellyfin):
    setup(client, fake_jellyfin)
    cinema = room(client, 1, "/api/cinema/programme")
    assert cinema["item"]["franchise"] == {"name": "The Saga", "part": 1, "parts": 3, "ordered": True}
    assert client.post("/api/cinema/rooms/1/play?next=true").status_code == 409

    wait_for_show(client, client.post("/api/cinema/rooms/1/play").json()["id"])
    cinema = room(client, 1, "/api/cinema/programme")
    assert cinema["next"]["id"] == item_id(502) and "trailer_urls" not in cinema["next"]
    title = client.get(f"/api/cinema/titles/{item_id(502)}").json()
    assert title["franchise"]["part"] == 2
    assert title["screenings"] == [{"room": 1, "name": "Premiere I", "showtimes": cinema["showtimes"],
                                    "sold_out": False, "next": True}]  # fmt: skip

    show = wait_for_show(client, client.post("/api/cinema/rooms/1/play?next=true").json()["id"])
    assert show["item_id"] == item_id(502)
    assert room(client, 1, "/api/cinema/programme")["item"]["id"] == item_id(502)


def franchise(client) -> dict:
    return next(f for f in client.get("/api/admin/franchises").json() if f["collection_id"] == T)


def test_admin_franchise_page(client, fake_jellyfin):
    setup(client, fake_jellyfin)
    saga = franchise(client)
    assert saga["name"] == "The Saga" and saga["state"] == "fresh"
    assert [p["key"] for p in saga["parts"]] == ["501", "502", "503"]
    assert saga["parts"][0]["next"] and saga["parts"][0]["today"] == 1

    renamed = client.patch(f"/api/admin/franchises/{T}", json={"name": "Saga"}).json()
    assert renamed["name"] == "Saga" and renamed["default_name"] == "The Saga"
    reordered = client.patch(f"/api/admin/franchises/{T}", json={"order": ["502", "501", "503"]}).json()
    assert [p["key"] for p in reordered["parts"]] == ["502", "501", "503"] and reordered["custom_order"]
    excluded = client.patch(f"/api/admin/franchises/{T}", json={"order": [], "excluded": ["503"]}).json()
    assert [p["key"] for p in excluded["parts"]] == ["501", "502"] and excluded["excluded"][0]["key"] == "503"
    assert client.patch(f"/api/admin/franchises/{T}", json={"excluded": ["nope"]}).status_code == 422

    nexted = client.post(f"/api/admin/franchises/{T}/next", json={"key": "502"}).json()
    assert nexted["state"] == "started" and nexted["progress"] == 1 and nexted["parts"][1]["next"]
    assert client.post(f"/api/admin/franchises/{T}/reset").json()["state"] == "fresh"

    off = client.patch(f"/api/admin/franchises/{T}", json={"any_order": True}).json()
    assert off["state"] == "off"
    assert client.post(f"/api/admin/franchises/{T}/next", json={"key": "502"}).status_code == 409

    # Back to the defaults: the override disappears.
    client.patch(f"/api/admin/franchises/{T}", json={"name": "", "any_order": False, "excluded": []})
    assert client.get("/api/admin/config/export").json()["franchises"] == []


def test_franchises_survive_export_and_import(client, fake_jellyfin):
    setup(client, fake_jellyfin)
    client.put("/api/admin/cassettes/FAKE00FF", json={"franchise": True})
    client.patch(f"/api/admin/franchises/{T}", json={"name": "Saga", "excluded": ["503"]})
    wait_for_show(client, client.post("/api/cinema/rooms/1/play").json()["id"])
    wait_for_show(client, client.post("/api/cinema/rooms/1/play?next=true").json()["id"])

    document = client.get("/api/admin/config/export").json()
    assert document["schema_version"] == 3
    assert document["franchises"][0] | {"order": []} == {
        "collection_id": T, "name": "Saga", "any_order": False, "order": [],
        "excluded": [{"id": item_id(503), "type": "movie", "name": "Saga 2003", "year": 2003,
                      "provider_ids": {"Tmdb": "503", "TmdbCollection": T}}],
    }  # fmt: skip
    assert [r["started_parts"][-1]["name"] for r in document["state"]["franchise_runs"]] == ["Saga 1991"]
    entry = next(e for e in document["state"]["programme"] if e["room_number"] == 1)
    assert [m["id"] for m in entry["marathon"]] == [item_id(502)]
    assert document["cassettes"] == [{"uid": "FAKE00FF", "target": "franchise", "room_number": None,
                                      "learned_at": document["cassettes"][0]["learned_at"]}]  # fmt: skip

    client.post(f"/api/admin/franchises/{T}/reset")
    client.patch(f"/api/admin/franchises/{T}", json={"name": "", "excluded": []})
    client.delete("/api/admin/cassettes/FAKE00FF")
    preview = client.post("/api/admin/config/import/preview", json=document).json()
    assert preview["franchises_changed"] == ["Saga"] and preview["franchise_runs"] == 1
    assert preview["cassettes_changed"] == ["FAKE00FF: none → franchise"]

    client.post("/api/admin/config/import", json=document)
    saga = franchise(client)
    assert saga["name"] == "Saga" and [p["key"] for p in saga["excluded"]] == ["503"]
    assert saga["state"] == "resting"  # part 2 is the finale without part 3
    assert client.get("/api/admin/cassettes").json()["franchise"][0]["uid"] == "FAKE00FF"
    assert room(client, 1)["item"]["id"] == item_id(502)


def test_schema_2_exports_still_import(client):
    document = client.get("/api/admin/config/export").json()
    document["schema_version"] = 2
    for key in ("franchises",):
        document.pop(key)
    document["state"].pop("franchise_runs")
    document["cassettes"] = [{"uid": "FAKE0001", "room_number": 1, "learned_at": "2026-10-01T10:00:00"}]
    for entry in document["state"]["programme"]:
        entry.pop("marathon"), entry.pop("last_started_at")
    assert client.post("/api/admin/config/import", json=document).is_success
    assert client.get("/api/admin/cassettes").json()["rooms"][0]["cassettes"][0]["uid"] == "FAKE0001"


def test_cli_learns_and_plays_the_franchise_cassette(client, fake_jellyfin, monkeypatch):
    setup(client, fake_jellyfin)
    monkeypatch.setattr(cli.httpx, "post", client.post)
    monkeypatch.setattr(cli.Context, "client", lambda self: client)
    monkeypatch.setattr(cli.time, "sleep", lambda _: time.sleep(0.01))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["play", "franchise"])
    assert result.exit_code == 1 and "no franchise cassette yet" in result.output
    result = runner.invoke(cli.app, ["learn", "franchise", "--uid", "FAKE00FF"])
    assert "FAKE00FF: learned as the franchise cassette" in result.output, result.output
    result = runner.invoke(cli.app, ["play", "franchise"])
    assert "ignored (No franchise running today)" in result.output, result.output

    wait_for_show(client, client.post("/api/cinema/rooms/1/play").json()["id"])
    result = runner.invoke(cli.app, ["play", "franchise"])
    assert result.exit_code == 0 and "starting room 1 (franchise cassette)" in result.output, result.output
    assert "playing:" in result.output
    assert "Franchise cassette" in runner.invoke(cli.app, ["cassettes"]).output
