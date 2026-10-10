"""Shared fixtures: an in-process fake Jellyfin and app factories."""

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from tarantino.config import Settings
from tarantino.main import create_app
from tarantino.shows.orchestrator import Timing

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
        self.sessions: list[dict] = []
        self.next_up: dict[str, dict] = {}
        self.episodes: dict[str, list[dict]] = {}
        self.plays: list[dict] = []
        self.seeks: list[int] = []
        self.client_resume_ticks = 0  # position the client reports after PlayNow
        self.playback_starts = True

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
        if path == "/Sessions":
            return httpx.Response(200, json=self.sessions)
        if path.startswith("/Sessions/") and path.endswith("/Playing"):
            session_id = path.split("/")[2]
            params = request.url.params
            item_ids = params["itemIds"].split(",")
            self.plays.append({"session": session_id, "item_ids": item_ids,
                               "start": int(params.get("startPositionTicks", 0))})
            if self.playback_starts:
                for session in self.sessions:
                    if session["Id"] == session_id:
                        session["NowPlayingItem"] = {"Id": item_ids[0], "Name": "Now playing"}
                        session["PlayState"] = {"PositionTicks": self.client_resume_ticks or int(params.get("startPositionTicks", 0))}
            return httpx.Response(204)
        if path.startswith("/Sessions/") and path.endswith("/Playing/Seek"):
            self.seeks.append(int(request.url.params["seekPositionTicks"]))
            return httpx.Response(204)
        if path == "/Shows/NextUp":
            episode = self.next_up.get(request.url.params["seriesId"])
            return httpx.Response(200, json={"Items": [episode] if episode else []})
        if path.startswith("/Shows/") and path.endswith("/Episodes"):
            return httpx.Response(200, json={"Items": self.episodes.get(path.split("/")[2], [])})
        if path.startswith("/Items/") and "/Images/" in path:
            if any(path.startswith(f"/Items/{i['Id']}/") for i in self.items):
                return httpx.Response(200, content=b"\x89PNG fake", headers={"content-type": "image/png"})
            return httpx.Response(404)
        return httpx.Response(404)

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def projector_session(device_id: str = "projector-device") -> dict:
    return {
        "Id": "session-1",
        "DeviceId": device_id,
        "DeviceName": "Projector",
        "Client": "Android TV",
        "SupportsRemoteControl": True,
        "RemoteEndPoint": "192.0.2.50",
    }


class FakeProjector:
    """State of a fake Android TV projector, shared by all FakeAdb instances."""

    def __init__(self, jellyfin: FakeJellyfin):
        self.jellyfin = jellyfin
        self.reachable = True
        self.adb_state = "device"
        self.screen_on = False
        self.foreground = "com.google.android.tvlauncher"
        self.calls: list[str] = []

    def factory(self, address: str) -> "FakeAdb":
        return FakeAdb(self, address)


class FakeAdb:
    def __init__(self, projector: FakeProjector, address: str):
        self.p = projector
        self.address = address

    async def reachable(self, timeout: float = 2) -> bool:
        return self.p.reachable

    async def connect(self) -> str:
        return self.p.adb_state

    async def screen_on(self) -> bool:
        return self.p.screen_on

    async def foreground_package(self) -> str | None:
        return self.p.foreground

    async def wake(self) -> None:
        self.p.calls.append("wake")
        self.p.screen_on = True

    async def launch_jellyfin(self) -> None:
        self.p.calls.append("launch")
        self.p.foreground = "org.jellyfin.androidtv"
        if not self.p.jellyfin.sessions:  # the app registers its session with the server
            self.p.jellyfin.sessions.append(projector_session())

    async def status(self):
        from tarantino.projector.adb import AdbStatus

        return AdbStatus(self.p.reachable, self.p.adb_state, self.p.screen_on, self.p.foreground)


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
def fake_projector(fake_jellyfin) -> FakeProjector:
    return FakeProjector(fake_jellyfin)


FAST = Timing(poll=0.01, wake_timeout=0.2, app_launch_timeout=0.2, session_timeout=0.2,
              session_settle=0, confirm_timeout=0.2)  # fmt: skip


@pytest.fixture
def client(settings, fake_jellyfin, fake_projector):
    app = create_app(
        settings, jellyfin_transport=fake_jellyfin.transport, adb_factory=fake_projector.factory,
        timing=FAST, run_jobs=False,
    )  # fmt: skip
    with TestClient(app) as test_client:
        yield test_client
