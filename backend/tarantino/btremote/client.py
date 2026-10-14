"""Talk to the Bluetooth remote daemon over its Unix socket (one JSON line each way)."""

import asyncio
import json
from pathlib import Path

CONNECT_TIMEOUT = 2.0
UNAVAILABLE = {"available": False, "paired": False, "connected": False, "pairing": False}


class BtRemoteError(Exception):
    pass


class BtRemoteUnavailable(BtRemoteError):
    """The daemon is not running (or not installed)."""


class BtRemote:
    def __init__(self, socket_path: Path):
        self.socket_path = socket_path

    async def request(self, cmd: str, *, reply_timeout: float = 5.0, **args) -> dict:
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(str(self.socket_path)), CONNECT_TIMEOUT
            )
        except (OSError, TimeoutError) as exc:
            raise BtRemoteUnavailable(f"Bluetooth remote service not reachable ({exc.__class__.__name__})") from exc
        try:
            writer.write(json.dumps({"cmd": cmd, **args}).encode() + b"\n")
            await writer.drain()
            line = await asyncio.wait_for(reader.readline(), reply_timeout)
        except (OSError, TimeoutError) as exc:
            raise BtRemoteError(f"Bluetooth remote did not answer {cmd!r} ({exc.__class__.__name__})") from exc
        finally:
            writer.close()
        try:
            response = json.loads(line)
        except ValueError as exc:
            raise BtRemoteError(f"Bluetooth remote sent an invalid reply to {cmd!r}") from exc
        if not response.get("ok"):
            raise BtRemoteError(response.get("error") or f"Bluetooth remote: {cmd} failed")
        return response

    async def status(self) -> dict:
        """The daemon's state; `available` is False when it is not running."""
        try:
            return {"available": True} | await self.request("status")
        except BtRemoteUnavailable:
            return dict(UNAVAILABLE)

    async def wake(self, timeout: float) -> bool:
        """Send the wake advert until the projector connects; True once it is connected."""
        response = await self.request("wake", reply_timeout=timeout + 5, timeout=timeout)
        return bool(response.get("connected"))

    async def key(self, name: str) -> None:
        await self.request("key", key=name)

    async def pair(self, seconds: float) -> dict:
        """Forget the old pairing and be discoverable for `seconds`."""
        return await self.request("pair", seconds=seconds)

    async def stop_pairing(self) -> dict:
        return await self.request("stop")

    async def unpair(self) -> dict:
        return await self.request("unpair")
