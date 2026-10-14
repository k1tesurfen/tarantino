"""One facade over the projector's control channels.

- Bluetooth remote (separate daemon): wakes the projector from any standby and opens
  Jellyfin with the shortcut key (primary, once paired)
- Android TV Remote protocol: power state, current app, launching apps
- Chromecast: waking from network standby
- ADB: fallback for state and app launch when it happens to be available
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from tarantino.btremote.client import BtRemote, BtRemoteError
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
REMOTE_CONNECT_TIMEOUT = 60.0  # the remote service comes back some seconds after a wake (seen: ~45 s)
# The remote connects only on demand. An awake projector answers at once; a sleeping one
# does not, and then Cast wakes it.
REMOTE_PROBE_TIMEOUT = 3.0
APP_INFO_TIMEOUT = 2.0  # right after connecting, the projector reports its foreground app
BT_WAKE_TIMEOUT = 10.0  # a sleeping projector connects to the remote 1-2 s after the wake advert
# After a wake the projector swallows keys for a moment. The Android TV remote (back within
# a second of the wake) tells when it is on and which app is in front; without it there
# is no feedback, and the shortcut key is pressed twice (harmless once Jellyfin is open).
BT_READY_TIMEOUT = 15.0  # wait for the Android TV remote to report the projector on
BT_KEY_SETTLE = 1.0  # after the projector reports on, before the first shortcut key
BT_SHORTCUT_ATTEMPTS = 3
BT_SHORTCUT_CONFIRM = 4.0  # per attempt: Jellyfin in front?

log = logging.getLogger(__name__)


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
        bt: BtRemote | None = None,
    ):
        self.settings = settings
        self.remote = remote
        self.adb_factory = adb_factory
        self.waker = waker
        self.bt = bt

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
        if self.bt is not None:
            try:
                result = await self._prepare_via_bluetooth(address, poll)
            except BtRemoteError as exc:
                log.warning("Bluetooth remote failed (%s); using Cast and the Android TV remote", exc)
                actions.append(f"Bluetooth failed ({exc})")
            else:
                if result:
                    return result

        await self.remote.ensure_connected(REMOTE_PROBE_TIMEOUT, REMOTE_PROBE_TIMEOUT)
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

        if not self.remote.connected and await self.remote.ensure_connected(REMOTE_CONNECT_TIMEOUT):
            actions.append("remote connected")
        if self.remote.connected:

            async def app_known() -> bool:
                return self.remote.current_app is not None

            try:
                await self._wait(app_known, APP_INFO_TIMEOUT, "", poll)
            except ProjectorError:
                pass  # unknown counts as "not Jellyfin": opening it again is harmless

        launched = False
        if await self.current_app(address) != JELLYFIN_PACKAGE:
            await self.launch_jellyfin(address, poll, store_settle)
            launched = True

            async def in_front() -> bool:
                return await self.current_app(address) == JELLYFIN_PACKAGE

            await self._wait(in_front, launch_timeout, "Jellyfin app did not open", poll)
            actions.append("opened Jellyfin")
        return PrepareResult(", ".join(actions) or "Projector on, Jellyfin open", launched)

    async def _prepare_via_bluetooth(self, address: str, poll: float) -> PrepareResult | None:
        """Wake via the Bluetooth remote and open Jellyfin with the shortcut key.

        None when no Bluetooth remote is paired (or its service is not running). Raises
        BtRemoteError when it fails, so the caller falls back to Cast and the Play Store.
        """
        state = await self.bt.status()
        if not state.get("paired"):
            return None
        actions = []
        woke = not state.get("connected")
        if woke:
            if not await self.bt.wake(BT_WAKE_TIMEOUT):
                raise BtRemoteError("the projector did not connect after the wake advert")
            actions.append("woke projector (Bluetooth)")

        feedback = await self.remote.ensure_connected(
            BT_READY_TIMEOUT if woke else REMOTE_PROBE_TIMEOUT, REMOTE_PROBE_TIMEOUT
        )
        if feedback:
            try:
                await self._wait(self._reports_on, BT_READY_TIMEOUT, "", poll)
            except ProjectorError:
                pass  # try the key anyway; the check below tells whether it worked
        if not woke and await self.current_app(address) == JELLYFIN_PACKAGE:
            return PrepareResult("Projector on, Jellyfin open", False)
        if woke:
            await asyncio.sleep(BT_KEY_SETTLE)

        async def jellyfin_in_front() -> bool:
            return self.remote.current_app == JELLYFIN_PACKAGE

        presses = BT_SHORTCUT_ATTEMPTS if feedback else 2
        for press in range(1, presses + 1):
            await self.bt.key("star")
            try:
                await self._wait(jellyfin_in_front, BT_SHORTCUT_CONFIRM, "", poll)
            except ProjectorError:
                continue  # without feedback this is just the pause before the second press
            note = "" if press == 1 else f", {press} presses"
            actions.append(f"opened Jellyfin (shortcut key{note})")
            return PrepareResult(", ".join(actions), True)
        if feedback:
            raise BtRemoteError(f"Jellyfin did not come to the front after {presses} shortcut key presses")
        actions.append("pressed the shortcut key (no feedback)")
        return PrepareResult(", ".join(actions), True)

    async def _reports_on(self) -> bool:
        return self.remote.is_on is True

    async def _wait(self, check, timeout: float, error: str, poll: float) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while await check() is not True:
            if asyncio.get_running_loop().time() > deadline:
                raise ProjectorError(error)
            await asyncio.sleep(poll)

    async def status(self) -> dict:
        bluetooth = await self.bt.status() if self.bt else None
        address = self.connect()
        if not address:
            return {"state": "unconfigured", "message": "Set the projector address in settings", "bluetooth": bluetooth}
        if self.remote.state in ("disconnected", "unreachable"):  # not while a show is connecting
            await self.remote.ensure_connected(REMOTE_PROBE_TIMEOUT, REMOTE_PROBE_TIMEOUT)
        adb = await self._adb(address)
        status = {
            "address": address,
            "remote": self.remote.state,
            "adb": "device" if adb else "unavailable",
            "power": _power(await self.is_on(address)),
            "foreground": await self.current_app(address),
            "bluetooth": bluetooth,
        }
        status["jellyfin_in_front"] = status["foreground"] == JELLYFIN_PACKAGE
        if self.remote.state == "connected":
            return status | {"state": "ok", "message": None}
        if bluetooth and bluetooth.get("paired"):
            # In standby the Android TV remote is unreachable; the Bluetooth remote wakes it.
            message = None if bluetooth.get("connected") else "Bluetooth remote paired, not connected (standby?)"
            return status | {"state": "ok", "message": message}
        if self.remote.state in ("unpaired", "pairing"):
            return status | {"state": "warning", "message": "Pair the Android TV remote below"}
        if adb:
            return status | {"state": "warning", "message": f"Remote {self.remote.state}; using ADB fallback"}
        return status | {"state": "error", "message": f"Remote {self.remote.state}: {self.remote.error or ''}".strip()}


def _power(value: bool | None) -> str:
    return "unknown" if value is None else "on" if value else "standby"

