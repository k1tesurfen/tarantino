"""Shared fixtures: an in-process fake Jellyfin and app factories."""

from datetime import UTC, datetime

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
        self.dropped_plays = 0  # PlayNow commands a slow client ignores before reacting
        self.activity_after_polls: int | None = None  # session becomes fresh after N /Sessions polls

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
            types = request.url.params["includeItemTypes"].split(",")
            items = [i for i in self.items if i["Type"] in types]
            return httpx.Response(200, json={"Items": items[start : start + limit], "TotalRecordCount": len(items)})
        if path == "/Sessions":
            if self.activity_after_polls is not None:
                self.activity_after_polls -= 1
                if self.activity_after_polls <= 0:
                    for session in self.sessions:
                        session["LastActivityDate"] = now_iso()
                    self.activity_after_polls = None
            return httpx.Response(200, json=self.sessions)
        if path.startswith("/Sessions/") and path.endswith("/Playing"):
            session_id = path.split("/")[2]
            params = request.url.params
            item_ids = params["itemIds"].split(",")
            self.plays.append({"session": session_id, "item_ids": item_ids,
                               "start": int(params.get("startPositionTicks", 0))})
            if self.dropped_plays > 0:
                self.dropped_plays -= 1
            elif self.playback_starts:
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


def now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def projector_session(device_id: str = "projector-device", last_activity: str | None = None) -> dict:
    return {
        "LastActivityDate": last_activity or now_iso(),
        "Id": "session-1",
        "DeviceId": device_id,
        "DeviceName": "Projector",
        "Client": "Android TV",
        "SupportsRemoteControl": True,
        "RemoteEndPoint": "192.0.2.50",
    }


class FakeProjector:
    """A fake Android TV projector.

    Plays three roles: the RemoteLink (Android TV remote protocol), the Cast waker,
    and the ADB fallback (via `adb_factory`).
    """

    def __init__(self, jellyfin: FakeJellyfin):
        self.jellyfin = jellyfin
        self.on = False
        self.foreground = "com.google.android.tvlauncher"
        self.state = "connected"  # remote state
        self.error = None
        self.host = None
        self.cast_works = True
        self.adb_available = False
        self.store_opens_app = True  # False simulates an "Update" button having focus
        self.reconnect_after_wake: float | None = None  # remote comes back this many seconds after a wake
        self.calls: list[str] = []

    # -- RemoteLink interface --
    def configure(self, host):
        self.host = host

    def stop(self):
        pass

    @property
    def connected(self):
        return self.state == "connected"

    @property
    def is_on(self):
        return self.on if self.connected else None

    @property
    def current_app(self):
        return self.foreground if self.connected else None

    def launch_app(self, link):
        # Like the real device: no deep link for Jellyfin, but the store page opens.
        self.calls.append("remote-launch")
        if link == "https://play.google.com/store/apps/details?id=org.jellyfin.androidtv":
            self.foreground = "com.android.vending"

    def send_key(self, key):
        self.calls.append(key)
        if key == "KEYCODE_DPAD_CENTER" and self.foreground == "com.android.vending" and self.store_opens_app:
            self._open("org.jellyfin.androidtv")
        elif key == "KEYCODE_BACK":
            self.foreground = "com.google.android.tvlauncher"

    async def ensure_connected(self, timeout, attempt_timeout=None):
        import asyncio

        if self.state in ("unconfigured", "unpaired", "pairing"):
            return False  # like RemoteLink: waiting cannot fix these
        deadline = asyncio.get_running_loop().time() + timeout
        while not self.connected and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.005)
        return self.connected

    async def start_pairing(self):
        self.state = "pairing"

    async def finish_pairing(self, code):
        from tarantino.projector.remote import RemoteError

        if code != "ABC123":
            raise RemoteError("Wrong code; start pairing again")
        self.state = "connected"

    # -- Cast waker --
    async def wake(self, host):
        from tarantino.projector.cast import CastError

        if not self.cast_works:
            raise CastError("Cast connection failed: timed out")
        if self.on:
            return False
        self.calls.append("cast-wake")
        self.on = True
        if self.reconnect_after_wake is not None:
            import asyncio

            asyncio.get_running_loop().call_later(self.reconnect_after_wake, setattr, self, "state", "connected")
        return True

    # -- shared --
    def _open(self, package):
        self.foreground = package
        if not self.jellyfin.sessions:  # the app registers its session with the server
            self.jellyfin.sessions.append(projector_session())
        else:  # an old session exists; the app refreshes it after a while
            self.jellyfin.activity_after_polls = 3

    def adb_factory(self, address: str) -> "FakeAdb":
        return FakeAdb(self, address)


class FakeAdb:
    def __init__(self, projector: FakeProjector, address: str):
        self.p = projector
        self.address = address

    async def reachable(self, timeout: float = 2) -> bool:
        return self.p.adb_available

    async def connect(self) -> str:
        return "device" if self.p.adb_available else "disconnected"

    async def screen_on(self) -> bool:
        return self.p.on

    async def foreground_package(self) -> str | None:
        return self.p.foreground

    async def launch_jellyfin(self) -> None:
        self.p.calls.append("adb-launch")
        self.p._open("org.jellyfin.androidtv")


@pytest.fixture(autouse=True)
def fast_remote_probe(monkeypatch):
    from tarantino.projector import projector

    monkeypatch.setattr(projector, "REMOTE_PROBE_TIMEOUT", 0.02)
    monkeypatch.setattr(projector, "APP_INFO_TIMEOUT", 0.02)


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
              session_settle=0, launch_settle=0, store_settle=0, play_attempts=3, play_attempt_timeout=0.05)  # fmt: skip


@pytest.fixture
def client(settings, fake_jellyfin, fake_projector):
    app = create_app(
        settings, jellyfin_transport=fake_jellyfin.transport, adb_factory=fake_projector.adb_factory,
        remote=fake_projector, waker=fake_projector.wake, timing=FAST, run_jobs=False,
    )  # fmt: skip
    with TestClient(app) as test_client:
        yield test_client
