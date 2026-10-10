"""One facade over the projector's control channels.

- Android TV Remote protocol: power state, current app, launching apps (primary)
- Chromecast: waking from network standby (the only channel that works there)
- ADB: fallback for state and app launch when it happens to be available
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from tarantino.projector.adb import JELLYFIN_PACKAGE, Adb, AdbError
from tarantino.projector.cast import CastError, cast_wake
from tarantino.projector.remote import RemoteLink
from tarantino.settings import SettingsStore


# The Jellyfin Android TV app declares no deep links, and the remote protocol only
# opens links, so open its Play Store page and press OK on the focused "Open" button.
JELLYFIN_STORE_LINK = f"https://play.google.com/store/apps/details?id={JELLYFIN_PACKAGE}"
PLAY_STORE_PACKAGE = "com.android.vending"
STORE_OPEN_TIMEOUT = 10.0
STORE_SETTLE = 3.0  # let the details page render and focus its primary button
STORE_LEAVE_TIMEOUT = 8.0


class ProjectorError(Exception):
    pass


@dataclass
class PrepareResult:
    message: str
    launched_app: bool


class Projector:
    def __init__(
        self,
        settings: SettingsStore,
        remote: RemoteLink,
        adb_factory: Callable[[str], Adb] = Adb,
        waker: Callable[[str], Awaitable[bool]] = cast_wake,
    ):
        self.settings = settings
        self.remote = remote
        self.adb_factory = adb_factory
        self.waker = waker

    def connect(self) -> str | None:
        """Return the configured address; (re)connects the remote when it changed in admin."""
        address = self.settings.get().projector_address
        self.remote.configure(address)
        return address

    async def _adb(self, address: str) -> Adb | None:
        """An ADB connection if one is available right now, else None."""
        adb = self.adb_factory(address)
        try:
            if await adb.reachable(timeout=1) and await adb.connect() == "device":
                return adb
        except AdbError:
            pass
        return None

    async def is_on(self, address: str) -> bool | None:
        if self.remote.is_on is not None:
            return self.remote.is_on
        adb = await self._adb(address)
        return await adb.screen_on() if adb else None

    async def current_app(self, address: str) -> str | None:
        if self.remote.connected:
            return self.remote.current_app
        adb = await self._adb(address)
        return await adb.foreground_package() if adb else None

    async def launch_jellyfin(self, address: str, poll: float = 0.5, store_settle: float = STORE_SETTLE) -> None:
        if self.remote.connected:
            await self._launch_via_play_store(poll, store_settle)
            return
        adb = await self._adb(address)
        if adb is None:
            raise ProjectorError("Cannot open Jellyfin: remote not paired/connected and ADB unavailable")
        await adb.launch_jellyfin()

    async def _launch_via_play_store(self, poll: float, store_settle: float) -> None:
        self.remote.launch_app(JELLYFIN_STORE_LINK)

        async def store_in_front() -> bool:
            return self.remote.current_app == PLAY_STORE_PACKAGE

        await self._wait(store_in_front, STORE_OPEN_TIMEOUT, "Play Store page for Jellyfin did not open", poll)
        await asyncio.sleep(store_settle)
        self.remote.send_key("KEYCODE_DPAD_CENTER")

        async def store_left() -> bool:
            return self.remote.current_app != PLAY_STORE_PACKAGE

        try:
            await self._wait(store_left, STORE_LEAVE_TIMEOUT, "", poll)
        except ProjectorError:
            self.remote.send_key("KEYCODE_BACK")
            raise ProjectorError(
                "Play Store did not open Jellyfin (is an app update pending? Open Jellyfin once manually)"
            ) from None

    async def prepare_for_jellyfin(
        self, poll: float, wake_timeout: float, launch_timeout: float, store_settle: float = STORE_SETTLE
    ) -> PrepareResult:
        """Make sure the projector is on and the Jellyfin app is in front."""
        address = self.connect()
        if not address:
            return PrepareResult("No projector address configured; assuming Jellyfin is already open", False)

        actions = []
        if await self.is_on(address) is not True:
            try:
                woke = await self.waker(address)
            except CastError as exc:
                raise ProjectorError(str(exc)) from exc
            if woke:
                # Cast only reports success once the device left standby, so an
                # unobservable power state (None) counts as on.
                async def awake() -> bool:
                    return await self.is_on(address) in (True, None)

                await self._wait(awake, wake_timeout, "Projector did not wake up", poll)
                actions.append("woke projector (Cast)")

        launched = False
        if await self.current_app(address) != JELLYFIN_PACKAGE:
            await self.launch_jellyfin(address, poll, store_settle)
            launched = True

            async def in_front() -> bool:
                return await self.current_app(address) == JELLYFIN_PACKAGE

            await self._wait(in_front, launch_timeout, "Jellyfin app did not open", poll)
            actions.append("opened Jellyfin")
        return PrepareResult(", ".join(actions) or "Projector on, Jellyfin open", launched)

    async def _wait(self, check, timeout: float, error: str, poll: float) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while await check() is not True:
            if asyncio.get_running_loop().time() > deadline:
                raise ProjectorError(error)
            await asyncio.sleep(poll)

    async def status(self) -> dict:
        address = self.connect()
        if not address:
            return {"state": "unconfigured", "message": "Set the projector address in settings"}
        adb = await self._adb(address)
        status = {
            "address": address,
            "remote": self.remote.state,
            "adb": "device" if adb else "unavailable",
            "power": _power(await self.is_on(address)),
            "foreground": await self.current_app(address),
        }
        status["jellyfin_in_front"] = status["foreground"] == JELLYFIN_PACKAGE
        if self.remote.state == "connected":
            return status | {"state": "ok", "message": None}
        if self.remote.state in ("unpaired", "pairing"):
            return status | {"state": "warning", "message": "Pair the Android TV remote below"}
        if adb:
            return status | {"state": "warning", "message": f"Remote {self.remote.state}; using ADB fallback"}
        return status | {"state": "error", "message": f"Remote {self.remote.state}: {self.remote.error or ''}".strip()}


def _power(value: bool | None) -> str:
    return "unknown" if value is None else "on" if value else "standby"

