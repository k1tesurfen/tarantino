import time

import pytest

from conftest import projector_session

MOVIE = f"{1:032x}"
SERIES = f"{100:032x}"


@pytest.fixture
def synced(client):
    assert client.post("/api/admin/library/sync").status_code == 202
    return client


def wait_for_show(client, show_id: int, timeout: float = 3) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        show = next(s for s in client.get("/api/admin/shows").json() if s["id"] == show_id)
        if show["state"] != "running":
            return show
        time.sleep(0.02)
    raise AssertionError(f"show {show_id} still running")


def start(client, item_id: str) -> dict:
    response = client.post("/api/admin/shows", json={"item_id": item_id})
    assert response.status_code == 202, response.text
    return wait_for_show(client, response.json()["id"])


def configure(client, **settings):
    assert client.patch("/api/admin/settings", json=settings).status_code == 200


def test_movie_wakes_projector_opens_jellyfin_and_plays(synced, fake_jellyfin, fake_projector):
    configure(synced, projector_address="192.0.2.50")
    show = start(synced, MOVIE)

    assert show["state"] == "playing", show
    assert [s["step"] for s in show["steps"]] == ["resolve", "projector", "session", "play", "confirm"]
    assert all(s["status"] == "done" for s in show["steps"])
    assert fake_projector.calls == ["wake", "launch"]
    assert fake_jellyfin.plays == [{"session": "session-1", "item_ids": [MOVIE], "start": 0}]
    assert fake_jellyfin.seeks == []


def test_without_projector_address_uses_existing_session(synced, fake_jellyfin, fake_projector):
    fake_jellyfin.sessions.append(projector_session())
    show = start(synced, MOVIE)
    assert show["state"] == "playing"
    assert "No projector address" in show["steps"][1]["message"]
    assert fake_projector.calls == []


def test_configured_device_id_must_match(synced, fake_jellyfin):
    fake_jellyfin.sessions.append(projector_session(device_id="someone-elses-tv"))
    configure(synced, projector_device_id="projector-device")
    show = start(synced, MOVIE)
    assert show["state"] == "failed"
    assert "session not found" in show["error"]


def test_unauthorised_adb_fails_with_hint(synced, fake_projector):
    configure(synced, projector_address="192.0.2.50")
    fake_projector.adb_state = "unauthorized"
    show = start(synced, MOVIE)
    assert show["state"] == "failed"
    assert "accept the prompt" in show["error"]
    assert show["steps"][-1] == show["steps"][1] | {"status": "failed"}


def test_unreachable_projector_fails(synced, fake_projector):
    configure(synced, projector_address="192.0.2.50")
    fake_projector.reachable = False
    assert "not reachable" in start(synced, MOVIE)["error"]


def test_movie_resumed_by_client_is_seeked_to_start(synced, fake_jellyfin):
    fake_jellyfin.sessions.append(projector_session())
    fake_jellyfin.client_resume_ticks = 45 * 60 * 10_000_000
    show = start(synced, MOVIE)
    assert show["state"] == "playing"
    assert fake_jellyfin.seeks == [0]
    assert "seeked back" in show["steps"][-1]["message"]


def test_series_plays_next_up_with_queue_and_resume(synced, fake_jellyfin):
    fake_jellyfin.sessions.append(projector_session())
    episodes = [{"Id": f"e{n}", "ParentIndexNumber": 2, "IndexNumber": n} for n in range(3, 7)]
    episodes[0]["UserData"] = {"PlaybackPositionTicks": 1234}
    fake_jellyfin.next_up[SERIES] = episodes[0]
    fake_jellyfin.episodes[SERIES] = episodes

    show = start(synced, SERIES)
    assert show["state"] == "playing", show
    assert fake_jellyfin.plays[0]["item_ids"] == ["e3", "e4", "e5", "e6"]
    assert fake_jellyfin.plays[0]["start"] == 1234
    assert show["steps"][0]["message"] == "Series 100 S02E03 + 3 queued"
    assert fake_jellyfin.seeks == []  # series resume is intended


def test_finished_series_fails(synced, fake_jellyfin):
    fake_jellyfin.sessions.append(projector_session())
    assert "no next episode" in start(synced, SERIES)["error"]


def test_playback_not_confirmed_fails(synced, fake_jellyfin):
    fake_jellyfin.sessions.append(projector_session())
    fake_jellyfin.playback_starts = False
    assert start(synced, MOVIE)["error"] == "Playback did not start on the projector"


def test_new_show_replaces_running_one(synced):
    # No session ever appears, so the first show is still waiting when the second starts.
    first = synced.post("/api/admin/shows", json={"item_id": MOVIE}).json()
    second = start(synced, f"{2:032x}")
    first = wait_for_show(synced, first["id"])
    assert first["state"] == "cancelled"
    assert first["error"] == "Replaced by a newer show"
    assert first["steps"][-1]["status"] == "cancelled"
    assert second["state"] == "failed"  # still no session, but it ran to the end


def test_unknown_item_is_404(synced):
    assert synced.post("/api/admin/shows", json={"item_id": f"{999:032x}"}).status_code == 404


def test_settings_roundtrip_and_validation(client):
    assert client.get("/api/admin/settings").json() == {"projector_address": None, "projector_device_id": None}
    response = client.patch("/api/admin/settings", json={"projector_address": "  192.0.2.50 "})
    assert response.json()["projector_address"] == "192.0.2.50"
    assert client.patch("/api/admin/settings", json={"projector_address": ""}).json()["projector_address"] is None
    assert client.patch("/api/admin/settings", json={"nope": 1}).status_code == 422


def test_sessions_listing_marks_projector(client, fake_jellyfin):
    fake_jellyfin.sessions.append(projector_session() | {"RemoteEndPoint": "::ffff:192.0.2.50"})
    [session] = client.get("/api/admin/sessions").json()
    assert session["host"] == "192.0.2.50"
    assert session["is_projector"] and not session["selected"]


def test_status_reports_projector_and_session(synced, fake_jellyfin):
    configure(synced, projector_address="192.0.2.50")
    status = synced.get("/api/admin/status").json()
    assert status["projector"]["state"] == "ok"
    assert status["projector"]["screen_on"] is False
    assert status["session"]["state"] == "unconfigured"

    fake_jellyfin.sessions.append(projector_session())
    configure(synced, projector_device_id="projector-device")
    assert synced.get("/api/admin/status").json()["session"]["state"] == "ok"
