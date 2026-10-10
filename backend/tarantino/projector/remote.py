"""Android TV Remote protocol (v2): power state, current app, launching apps.

This is the protocol of Google's TV remote app. It stays reachable in network
standby and needs a one-time pairing (the projector shows a code on screen).
"""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from androidtvremote2 import AndroidTVRemote, CannotConnect, ConnectionClosed, InvalidAuth

log = logging.getLogger(__name__)

CLIENT_NAME = "tarantino"
RETRY_SECONDS = 30


class RemoteError(Exception):
    pass


class RemoteLink:
    """A long-lived connection to the projector's remote service.

    state: unconfigured | connecting | connected | unreachable | unpaired | pairing
    """

    def __init__(self, cert_dir: Path, factory: Callable[..., AndroidTVRemote] = AndroidTVRemote):
        self.cert_dir = cert_dir
        self.factory = factory
        self.host: str | None = None
        self.state = "unconfigured"
        self.error: str | None = None
        self._remote: AndroidTVRemote | None = None
        self._task: asyncio.Task | None = None
        self._connected = asyncio.Event()
        self._retry_now = asyncio.Event()

    # -- lifecycle ----------------------------------------------------------

    def configure(self, host: str | None) -> None:
        """(Re)connect to `host`; a no-op if the host did not change."""
        if host == self.host and self.state != "unconfigured":
            return
        self.stop()
        self.host = host
        if host:
            self._remote = self._new_remote(host)
            self._start_connect()

    def stop(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
        if self._remote:
            self._remote.disconnect()
        self._remote = None
        self._set_state("unconfigured")

    def _new_remote(self, host: str) -> AndroidTVRemote:
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        return self.factory(CLIENT_NAME, str(self.cert_dir / "cert.pem"), str(self.cert_dir / "key.pem"), host)

    def _start_connect(self) -> None:
        self._task = asyncio.create_task(self._connect_loop())

    async def _connect_loop(self) -> None:
        remote = self._remote
        await remote.async_generate_cert_if_missing()
        while True:
            self._set_state("connecting")
            try:
                await remote.async_connect()
            except InvalidAuth:
                self._set_state("unpaired", "Pair the projector in the admin page")
                return
            except (CannotConnect, ConnectionClosed) as exc:
                self._set_state("unreachable", str(exc) or "Cannot connect")
                self._retry_now.clear()
                try:  # retry later, or right away when someone needs the remote
                    await asyncio.wait_for(self._retry_now.wait(), RETRY_SECONDS)
                except TimeoutError:
                    pass
                continue
            self._set_state("connected")
            remote.add_is_available_updated_callback(self._on_available)
            remote.keep_reconnecting(self._on_invalid_auth)
            log.info("Android TV remote connected to %s", self.host)
            return

    def _on_available(self, available: bool) -> None:
        self._set_state("connected" if available else "unreachable")

    def _on_invalid_auth(self) -> None:
        self._set_state("unpaired", "Pairing was revoked; pair again")

    def _set_state(self, state: str, error: str | None = None) -> None:
        self.state, self.error = state, error
        if state == "connected":
            self._connected.set()
        else:
            self._connected.clear()

    async def wait_connected(self, timeout: float) -> bool:
        """Wait for the connection (e.g. right after waking the projector); retries immediately."""
        if self.connected:
            return True
        if self.state in ("unconfigured", "unpaired", "pairing"):
            return False
        self._retry_now.set()
        try:
            await asyncio.wait_for(self._connected.wait(), timeout)
        except TimeoutError:
            return False
        return self.connected

    # -- pairing ------------------------------------------------------------

    async def start_pairing(self) -> None:
        if not self.host:
            raise RemoteError("Set the projector address first")
        self.stop()
        self._remote = self._new_remote(self.host)
        await self._remote.async_generate_cert_if_missing()
        try:
            await self._remote.async_start_pairing()
        except (CannotConnect, ConnectionClosed) as exc:
            self._set_state("unreachable", str(exc))
            raise RemoteError(f"Cannot reach the projector: {exc}") from exc
        self._set_state("pairing")

    async def finish_pairing(self, code: str) -> None:
        if self.state != "pairing" or not self._remote:
            raise RemoteError("Start pairing first")
        try:
            await self._remote.async_finish_pairing(code.strip().upper())
        except InvalidAuth as exc:
            raise RemoteError("Wrong code; start pairing again") from exc
        except (CannotConnect, ConnectionClosed) as exc:
            raise RemoteError(f"Pairing failed: {exc}") from exc
        self._start_connect()

    # -- state & commands ---------------------------------------------------

    @property
    def connected(self) -> bool:
        return self.state == "connected" and self._remote is not None

    @property
    def is_on(self) -> bool | None:
        return self._remote.is_on if self.connected else None

    @property
    def current_app(self) -> str | None:
        return self._remote.current_app if self.connected else None

    @property
    def device_name(self) -> str | None:
        if self.connected and self._remote.device_info:
            return self._remote.device_info.get("model")
        return None

    def launch_app(self, package: str) -> None:
        self._send(lambda r: r.send_launch_app_command(package))

    def send_key(self, key: str) -> None:
        self._send(lambda r: r.send_key_command(key))

    def _send(self, command: Callable[[AndroidTVRemote], None]) -> None:
        if not self.connected:
            raise RemoteError(f"Remote not connected ({self.state})")
        try:
            command(self._remote)
        except ConnectionClosed as exc:
            raise RemoteError("Remote connection closed") from exc
