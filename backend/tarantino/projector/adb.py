"""Control the projector (Android TV) over network ADB using the `adb` binary."""

import asyncio
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

JELLYFIN_PACKAGE = "org.jellyfin.androidtv"
DEFAULT_PORT = 5555

Runner = Callable[[list[str], float], Awaitable[tuple[int, str]]]


class AdbError(Exception):
    pass


async def run_adb(args: list[str], timeout: float) -> tuple[int, str]:
    try:
        process = await asyncio.create_subprocess_exec(
            "adb", *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
        )
    except FileNotFoundError as exc:
        raise AdbError("adb is not installed") from exc
    try:
        output, _ = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError as exc:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        raise AdbError(f"adb {args[0]} timed out") from exc
    return process.returncode or 0, output.decode(errors="replace")


@dataclass
class AdbStatus:
    reachable: bool
    adb_state: str  # device | unauthorized | offline | disconnected
    screen_on: bool | None = None
    foreground_package: str | None = None


def serial_for(address: str) -> str:
    return address if re.search(r":\d+$", address) else f"{address}:{DEFAULT_PORT}"


class Adb:
    def __init__(self, address: str, runner: Runner = run_adb):
        self.serial = serial_for(address)
        self.host, port = self.serial.rsplit(":", 1)
        self.port = int(port)
        self._run = runner

    async def reachable(self, timeout: float = 2) -> bool:
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(self.host, self.port), timeout)
        except (OSError, TimeoutError):
            return False
        writer.close()
        return True

    async def connect(self) -> str:
        """Connect and return the adb device state (device, unauthorized, offline)."""
        _, output = await self._run(["connect", self.serial], 10)
        if "unable" in output or "failed to connect" in output or "cannot" in output:
            return "disconnected"
        return await self.state()

    async def state(self) -> str:
        code, output = await self._run(["-s", self.serial, "get-state"], 5)
        if code == 0:
            return output.strip() or "device"
        if "unauthorized" in output:
            return "unauthorized"
        if "offline" in output:
            return "offline"
        return "disconnected"

    async def shell(self, command: str, timeout: float = 10) -> str:
        code, output = await self._run(["-s", self.serial, "shell", command], timeout)
        if code != 0:
            raise AdbError(f"adb shell failed: {output.strip()[:200]}")
        return output

    async def screen_on(self) -> bool:
        output = await self.shell("dumpsys power")
        match = re.search(r"mWakefulness=(\w+)", output)
        if match:
            return match.group(1) == "Awake"
        match = re.search(r"Display Power: state=(\w+)", output)
        return bool(match and match.group(1) == "ON")

    async def foreground_package(self) -> str | None:
        # Filter in Python: a `| grep` without matches exits 1, which adb reports as failure.
        output = await self.shell("dumpsys activity activities")
        match = re.search(r"(?:mResumedActivity|topResumedActivity|ResumedActivity).*?\s([\w.]+)/[\w.$]+", output)
        if match:
            return match.group(1)
        output = await self.shell("dumpsys window")
        match = re.search(r"mCurrentFocus=.*?\s([\w.]+)/[\w.$]+", output)
        return match.group(1) if match else None

    async def wake(self) -> None:
        await self.shell("input keyevent KEYCODE_WAKEUP")

    async def launch_jellyfin(self) -> None:
        await self.shell(f"monkey -p {JELLYFIN_PACKAGE} -c android.intent.category.LEANBACK_LAUNCHER 1")

    async def status(self) -> AdbStatus:
        if not await self.reachable():
            return AdbStatus(reachable=False, adb_state="disconnected")
        state = await self.connect()
        if state != "device":
            return AdbStatus(reachable=True, adb_state=state)
        return AdbStatus(
            reachable=True,
            adb_state=state,
            screen_on=await self.screen_on(),
            foreground_package=await self.foreground_package(),
        )
