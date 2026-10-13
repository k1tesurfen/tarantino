"""Android TV Remote protocol (v2): power state, current app, launching apps.

This is the protocol of Google's TV remote app. It needs a one-time pairing (the
projector shows a code on screen).

The link connects only on demand, when a show or the admin page needs it. It stays
open while the projector keeps it alive; once it drops (standby), it is not retried
in the background, so a sleeping projector is left alone.
"""

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

from androidtvremote2 import AndroidTVRemote, CannotConnect, ConnectionClosed, InvalidAuth

log = logging.getLogger(__name__)

CLIENT_NAME = "tarantino"
# Retry interval while someone waits for the connection (e.g. right after a wake): the
# remote service comes back some seconds after the wake.
RETRY_SECONDS = 2.0
# A projector in deep standby can accept the TCP connection without starting the remote
# service, or drop the packets; without a limit one attempt could block for minutes.
CONNECT_TIMEOUT = 10.0


class RemoteError(Exception):
    pass


class RemoteLink:
    """An on-demand connection to the projector's remote service.

    state: unconfigured | disconnected | connecting | connected | unreachable | unpaired | pairing
    """

    def __init__(self, cert_dir: Path, factory: Callable[..., AndroidTVRemote] = AndroidTVRemote):
        self.cert_dir = cert_dir
        self.factory = factory
        self.host: str | None = None
        self.state = "unconfigured"
        self.error: str | None = None
        self._remote: AndroidTVRemote | None = None
        self._lock = asyncio.Lock()
        self.retry_seconds = RETRY_SECONDS

    # -- lifecycle ----------------------------------------------------------

    def configure(self, host: str | None) -> None:
        """Use `host` from now on; a no-op if the host did not change. Does not connect."""
        if host == self.host and self.state != "unconfigured":
            return
        self.stop()
        self.host = host
        if host:
            self._remote = self._new_remote(host)
            self._set_state("disconnected")

    def stop(self) -> None:
        if self._remote:
            self._remote.disconnect()
        self._remote = None
        self._set_state("unconfigured")

    def _new_remote(self, host: str) -> AndroidTVRemote:
        self.cert_dir.mkdir(parents=True, exist_ok=True)
        remote = self.factory(CLIENT_NAME, str(self.cert_dir / "cert.pem"), str(self.cert_dir / "key.pem"), host)
        remote.add_is_available_updated_callback(self._on_available)
        return remote

    async def ensure_connected(self, timeout: float, attempt_timeout: float = CONNECT_TIMEOUT) -> bool:
        """Connect now if needed, retrying every few seconds until connected or `timeout`."""
        if self.connected:
            return True
        if self.state in ("unconfigured", "unpaired", "pairing"):
            return False  # waiting cannot fix these
        async with self._lock:  # one connection attempt at a time
            remote = self._remote
            await remote.async_generate_cert_if_missing()
            loop = asyncio.get_running_loop()
            deadline = loop.time() + timeout
            while not self.connected:
                self._set_state("connecting")
                limit = max(0.01, min(attempt_timeout, deadline - loop.time()))
                try:
                    await asyncio.wait_for(remote.async_connect(), limit)
                except InvalidAuth:
                    self._set_state("unpaired", "Pair the projector in the admin page")
                    return False
                except (CannotConnect, ConnectionClosed, TimeoutError) as exc:
                    remote.disconnect()  # drop a half-open attempt
                    self._set_state("unreachable", str(exc) or "Cannot connect")
                    if loop.time() + self.retry_seconds > deadline:
                        return False
                    await asyncio.sleep(self.retry_seconds)
                    continue
                self._set_state("connected")
                # Only so the library tells us when the connection drops (see _on_available).
                remote.keep_reconnecting(self._on_invalid_auth)
                log.info("Android TV remote connected to %s", self.host)
        return self.connected

    def _on_available(self, available: bool) -> None:
        if available:
            return  # only ensure_connected connects
        # The library would now retry forever; stop it, the next show connects again.
        log.info("Android TV remote lost the connection to %s", self.host)
        if self._remote:
            self._remote.disconnect()
        self._set_state("disconnected")

    def _on_invalid_auth(self) -> None:
        self._set_state("unpaired", "Pairing was revoked; pair again")

    def _set_state(self, state: str, error: str | None = None) -> None:
        self.state, self.error = state, error

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
        self._set_state("disconnected")
        await self.ensure_connected(CONNECT_TIMEOUT)

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
