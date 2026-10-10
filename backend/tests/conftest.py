"""Shared fixtures: an in-process fake Jellyfin and app factories."""

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tarantino.config import Settings
from tarantino.main import create_app

USER_ID = "0123456789abcdef0123456789abcdef"  # public-ok (fake)


def movie(n: int, **overrides) -> dict:
    item = {
        "Id": f"{n:032x}",
        "Type": "Movie",
        "Name": f"Movie {n}",
        "SortName": f"movie {n}",
        "ProductionYear": 1990 + n,
        "PremiereDate": f"{1990 + n}-05-01T00:00:00.0000000Z",
        "DateCreated": "2025-01-02T03:04:05.1234567Z",
        "Overview": "A film.",
        "Taglines": ["Tagline."],
        "Genres": ["Horror"] if n % 2 else ["Comedy"],
        "Tags": [],
        "Studios": [{"Name": "Studio"}],
        "People": [
            {"Name": "Director Person", "Type": "Director"},
            *({"Name": f"Actor {i}", "Role": f"Role {i}", "Type": "Actor"} for i in range(15)),
        ],
        "OfficialRating": "R",
        "CommunityRating": 7.5,
        "CriticRating": 80,
        "RunTimeTicks": 165 * 600_000_000,
        "ProviderIds": {"Tmdb": str(n)},
        "RemoteTrailers": [{"Url": "https://www.youtube.com/watch?v=abc", "Name": "Trailer"}],
        "ImageTags": {"Primary": f"p{n}"},
        "BackdropImageTags": [f"b{n}"],
        "UserData": {"Played": n % 3 == 0, "IsFavorite": n == 3, "PlayCount": 1 if n % 3 == 0 else 0},
    }
    return item | overrides


def series(n: int, unplayed: int = 5) -> dict:
    return {
        "Id": f"{n:032x}",
        "Type": "Series",
        "Name": f"Series {n}",
        "ProductionYear": 2010,
        "Genres": ["Drama"],
        "ImageTags": {"Primary": f"s{n}"},
        "RecursiveItemCount": 20,
        "UserData": {"Played": unplayed == 0, "UnplayedItemCount": unplayed},
    }


class FakeJellyfin:
    """Minimal fake of the Jellyfin endpoints tarantino calls."""

    def __init__(self, items: list[dict], api_key: str = "test-key"):
        self.items = items
        self.api_key = api_key
        self.requests: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if f'Token="{self.api_key}"' not in request.headers.get("Authorization", ""):
            return httpx.Response(401)
        path = request.url.path
        if path == "/System/Info":
            return httpx.Response(200, json={"Version": "12.1.0", "ServerName": "fake"})
        if path == "/Users":
            return httpx.Response(200, json=[{"Name": "Viewer", "Id": USER_ID}])
        if path == "/Items":
            start = int(request.url.params["startIndex"])
            limit = int(request.url.params["limit"])
            return httpx.Response(
                200, json={"Items": self.items[start : start + limit], "TotalRecordCount": len(self.items)}
            )
        if path.startswith("/Items/") and "/Images/" in path:
            if any(path.startswith(f"/Items/{i['Id']}/") for i in self.items):
                return httpx.Response(200, content=b"\x89PNG fake", headers={"content-type": "image/png"})
            return httpx.Response(404)
        return httpx.Response(404)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        data_dir=tmp_path / "data",
        frontend_dir=tmp_path / "build",
        jellyfin_api_key=SecretStr("test-key"),
        jellyfin_user="viewer",
    )


@pytest.fixture
def fake_jellyfin() -> FakeJellyfin:
    return FakeJellyfin([movie(n) for n in range(1, 8)] + [series(100), series(101, unplayed=0)])


@pytest.fixture
def client(settings, fake_jellyfin):
    app = create_app(settings, jellyfin_transport=fake_jellyfin.transport, run_jobs=False)
    with TestClient(app) as test_client:
        yield test_client
