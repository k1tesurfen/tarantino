import time

import pytest
from typer.testing import CliRunner

from conftest import projector_session
from tarantino import cli
from tarantino.cassettes import CassetteError, normalise_uid


def synced(client):
    client.post("/api/admin/library/sync")
    client.get("/api/admin/programme")
    return client


def wait_for_show(client, show_id):
    for _ in range(200):
        show = next(s for s in client.get("/api/admin/shows").json() if s["id"] == show_id)
        if show["state"] != "running":
            return show
        time.sleep(0.01)
    raise AssertionError("show did not finish")


def room(client, number):
    return next(r for r in client.get("/api/admin/cassettes").json()["rooms"] if r["number"] == number)


def test_uids_are_normalised():
    assert normalise_uid(" 04:a1:b2-c3 ") == "04A1B2C3"
    assert normalise_uid("fake0003") == "FAKE0003"
    for bad in ("", "x", "04/A1", "A" * 33):
        with pytest.raises(CassetteError):
            normalise_uid(bad)


def test_unknown_cassette_is_logged_and_ignored(client):
    event = client.post("/api/vhs/insert", json={"uid": "FAKE0099"}).json()
    assert event["outcome"] == "unknown"
    assert client.get("/api/admin/shows").json() == []
    assert client.get("/api/admin/cassettes").json()["events"][0]["uid"] == "FAKE0099"


def test_learn_mode_binds_the_next_insert_without_playing(client):
    armed = client.post("/api/admin/cassettes/learn", json={"room": 3}).json()
    assert armed["room"] == 3 and armed["seconds_left"] > 0
    event = client.post("/api/vhs/insert", json={"uid": "fake0003"}).json()
    assert event == event | {"outcome": "learned", "room": 3, "uid": "FAKE0003"}
    assert client.get("/api/admin/shows").json() == []
    overview = client.get("/api/admin/cassettes").json()
    assert overview["learn"] is None
    assert [c["uid"] for c in room(client, 3)["cassettes"]] == ["FAKE0003"]


def test_learning_a_known_cassette_moves_it(client):
    client.put("/api/admin/cassettes/FAKE0001", json={"room": 1})
    client.post("/api/admin/cassettes/learn", json={"room": 2})
    event = client.post("/api/vhs/insert", json={"uid": "FAKE0001"}).json()
    assert event["message"] == "moved from room 1"
    assert room(client, 1)["cassettes"] == [] and room(client, 2)["cassettes"][0]["uid"] == "FAKE0001"


def test_learned_cassette_plays_its_room(client, fake_jellyfin):
    fake_jellyfin.sessions.append(projector_session())
    synced(client).put("/api/admin/cassettes/FAKE0003", json={"room": 3})
    event = client.post("/api/vhs/insert", json={"uid": "FAKE0003"}).json()
    assert event["outcome"] == "played" and event["room"] == 3
    show = wait_for_show(client, event["show_id"])
    assert show["state"] == "playing" and show["trigger"] == "vhs"
    entry = next(r for r in client.get("/api/admin/programme").json()["rooms"] if r["number"] == 3)
    assert show["item_id"] == entry["item"]["id"] and entry["sold_out"]

    # The reader sees the same cassette again: no second show.
    again = client.post("/api/vhs/insert", json={"uid": "FAKE0003"}).json()
    assert again["outcome"] == "ignored"
    assert len(client.get("/api/admin/shows").json()) == 1


def test_cassette_for_a_closed_room_is_409(client):
    synced(client)
    closed = next(r["number"] for r in client.get("/api/admin/programme").json()["rooms"] if r["item"] is None)
    client.put("/api/admin/cassettes/FAKE0010", json={"room": closed})
    response = client.post("/api/vhs/insert", json={"uid": "FAKE0010"})
    assert response.status_code == 409
    assert client.get("/api/admin/cassettes").json()["events"][0]["outcome"] == "failed"


def test_eject_is_logged_only(client):
    assert client.post("/api/vhs/eject", json={"uid": "FAKE0001"}).json()["outcome"] == "ignored"
    assert client.post("/api/vhs/eject").json()["action"] == "eject"


def test_learn_mode_rejects_unknown_rooms_and_can_be_cancelled(client):
    assert client.post("/api/admin/cassettes/learn", json={"room": 42}).status_code == 404
    client.post("/api/admin/cassettes/learn", json={"room": 1})
    assert client.delete("/api/admin/cassettes/learn").status_code == 204
    assert client.get("/api/admin/cassettes").json()["learn"] is None
    assert client.post("/api/vhs/insert", json={"uid": "FAKE0001"}).json()["outcome"] == "unknown"


def test_removing_a_room_removes_its_cassettes(client):
    client.put("/api/admin/cassettes/FAKE0005", json={"room": 5})
    assert client.delete("/api/admin/rooms/5").status_code == 204
    assert client.post("/api/vhs/insert", json={"uid": "FAKE0005"}).json()["outcome"] == "unknown"


def test_cassettes_survive_export_and_import(client):
    client.put("/api/admin/cassettes/FAKE0002", json={"room": 2})
    document = client.get("/api/admin/config/export").json()
    assert document["cassettes"][0] | {"learned_at": None} == {"uid": "FAKE0002", "target": "room", "room_number": 2, "learned_at": None}
    client.delete("/api/admin/cassettes/FAKE0002")
    client.put("/api/admin/cassettes/FAKE0004", json={"room": 4})
    preview = client.post("/api/admin/config/import/preview", json=document).json()
    assert preview["cassettes_changed"] == ["FAKE0002: none → room 2", "FAKE0004: room 4 → none"]
    client.post("/api/admin/config/import", json=document)
    assert [c["uid"] for c in room(client, 2)["cassettes"]] == ["FAKE0002"]
    assert room(client, 4)["cassettes"] == []


def test_cli_learn_then_play_starts_the_room(client, fake_jellyfin, monkeypatch):
    """The M7 acceptance test: `tarantino learn 3 --uid FAKE0003` then `tarantino play 3`."""
    fake_jellyfin.sessions.append(projector_session())
    synced(client)
    monkeypatch.setattr(cli.httpx, "post", client.post)
    monkeypatch.setattr(cli.Context, "client", lambda self: client)
    monkeypatch.setattr(cli.time, "sleep", lambda _: time.sleep(0.01))
    runner = CliRunner()

    result = runner.invoke(cli.app, ["learn", "3", "--uid", "FAKE0003"])
    assert result.exit_code == 0, result.output
    assert "FAKE0003: learned for room 3" in result.output

    result = runner.invoke(cli.app, ["play", "3"])
    assert result.exit_code == 0, result.output
    assert "starting room 3" in result.output and "playing:" in result.output

    result = runner.invoke(cli.app, ["play", "4"])
    assert result.exit_code == 1 and "no cassette yet" in result.output
