import time

from conftest import projector_session
from tarantino.api.cinema import youtube_ids


def test_youtube_ids():
    assert youtube_ids([
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",  # duplicate
        "https://www.youtube.com/watch?feature=share&v=abcdefghijk",
        "https://vimeo.com/123",
    ]) == ["dQw4w9WgXcQ", "abcdefghijk"]  # fmt: skip


def test_public_programme(client):
    client.post("/api/admin/library/sync")
    data = client.get("/api/cinema/programme").json()
    assert data["cinema"] == {"names": {"modern": "apLex", "retro": "Red Apple Cinema"}, "default_theme": "modern"}
    room = next(r for r in data["rooms"] if r["item"])
    assert "trailer_urls" not in room["item"]
    assert isinstance(room["item"]["trailers"], list)


def test_title_detail_with_screenings(client):
    client.post("/api/admin/library/sync")
    rooms = client.get("/api/cinema/programme").json()["rooms"]
    playing = next(r for r in rooms if r["item"])
    detail = client.get(f"/api/cinema/titles/{playing['item']['id']}").json()
    assert detail["screenings"][0]["room"] == playing["number"]
    assert detail["people"][0]["type"] == "Director"
    assert client.get(f"/api/cinema/titles/{'0' * 32}").status_code == 404
    assert client.get("/api/cinema/titles/nope").status_code == 422


def test_cinema_can_play_without_login_and_now_reports_it(client, fake_jellyfin):
    fake_jellyfin.sessions.append(projector_session())
    client.post("/api/admin/library/sync")
    client.get("/api/cinema/programme")
    show = client.post("/api/cinema/rooms/1/play").json()
    assert show["trigger"] == "cinema"
    for _ in range(100):
        now = client.get("/api/cinema/now").json()
        if now["show"]["state"] != "running":
            break
        time.sleep(0.02)
    assert now["show"]["state"] == "playing"
    assert now["now_playing"] == "Now playing"
