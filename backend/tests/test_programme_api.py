import time

MOVIE_ROOMS = (1, 2, 3, 4, 5, 6)


def synced(client):
    client.post("/api/admin/library/sync")
    return client


def test_programme_is_generated_on_request(client):
    view = synced(client).get("/api/admin/programme").json()
    assert len(view["rooms"]) == 10
    horror = next(r for r in view["rooms"] if r["number"] == 4)
    assert "Horror" in horror["item"]["genres"]
    assert horror["showtimes"]


def test_play_room_marks_it_sold_out(client, fake_jellyfin):
    from conftest import projector_session

    fake_jellyfin.sessions.append(projector_session())
    synced(client).get("/api/admin/programme")
    show = client.post("/api/admin/rooms/1/play").json()
    assert show["room_id"] is not None
    for _ in range(100):
        shows = client.get("/api/admin/shows").json()
        if shows[0]["state"] != "running":
            break
        time.sleep(0.02)
    assert shows[0]["state"] == "playing"
    room = next(r for r in client.get("/api/admin/programme").json()["rooms"] if r["number"] == 1)
    assert room["sold_out"]


def test_play_closed_room_is_409(client):
    synced(client)
    # Only one unwatched series exists in the fake library, so some lounges are closed.
    rooms = client.get("/api/admin/programme").json()["rooms"]
    closed = next(r["number"] for r in rooms if r["item"] is None)
    response = client.post(f"/api/admin/rooms/{closed}/play")
    assert response.status_code == 409
    assert "Nothing is showing" in response.json()["detail"]


def test_reroll_and_swap_endpoints(client):
    synced(client).get("/api/admin/programme")
    assert client.post("/api/admin/programme/reroll", json={"room": 1}).status_code == 200
    assert client.post("/api/admin/programme/reroll", json={"room": 42}).status_code == 409
    response = client.post("/api/admin/programme/swap", json={"room": 1, "item_id": f"{100:032x}"})
    assert response.status_code == 409  # a series cannot run in a movie room


def test_room_crud(client):
    rooms = client.get("/api/admin/rooms").json()
    assert [r["number"] for r in rooms] == list(range(1, 11))

    new = {"number": 11, "name": "Grindhouse", "kind": "movie",
           "filters": {"watched": "unwatched", "genres_any": ["Horror"], "year_max": 1985}}  # fmt: skip
    created = client.post("/api/admin/rooms", json=new).json()
    assert created["filters"]["year_max"] == 1985
    assert client.post("/api/admin/rooms", json=new).status_code == 409

    updated = client.put("/api/admin/rooms/11", json=new | {"name": "Grindhouse Double Bill"}).json()
    assert updated["name"] == "Grindhouse Double Bill"
    assert client.put("/api/admin/rooms/11", json=new | {"kind": "series"}).status_code == 409

    series_room = client.put("/api/admin/rooms/7", json={"number": 7, "name": "TV", "kind": "series",
                                                          "filters": {"watched": "watched"}}).json()  # fmt: skip
    assert series_room["filters"]["watched"] == "any"  # series rooms stay random

    assert client.delete("/api/admin/rooms/11").status_code == 204
    assert client.delete("/api/admin/rooms/11").status_code == 404


def test_preview_and_facets(client):
    synced(client)
    preview = client.post("/api/admin/rooms/preview", json={"filters": {"genres_any": ["Horror"]}}).json()
    assert preview["count"] == 4  # movies 1, 3, 5, 7 are horror in the fake library
    facets = client.get("/api/admin/library/facets").json()
    assert facets["genres"] == ["Comedy", "Horror"]
    assert facets["official_ratings"] == ["R"]
