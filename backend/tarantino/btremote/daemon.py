"""tarantino-btremote: the mini-PC's Bluetooth adapter as a remote for the projector.

Registers a HID-over-GATT remote with BlueZ (no root needed) and serves a Unix socket
with one JSON request and one JSON reply per connection:

    {"cmd": "status"}                     paired/connected state
    {"cmd": "wake", "timeout": 8}         wake advert until the projector connects
    {"cmd": "key", "key": "star"}         press and release a key (see hid.KEYS)
    {"cmd": "pair", "seconds": 120}       forget the old pairing, be discoverable
    {"cmd": "stop"}                       end the pairing window
    {"cmd": "unpair"}                     forget the pairing

It runs as its own service so the projector keeps its connection to the remote while
the web app is redeployed. When the remote's HID service disappears while the projector
is connected, the projector stops reconnecting to it altogether (only a new pairing
helps). So on shutdown the daemon first drops the link, which the projector takes like
going out of range; after a start it advertises briefly so a projector that is on can
reconnect (a plain advert does not wake a sleeping one).
"""

import asyncio
import json
import logging
import os
import signal
import sys
from pathlib import Path

from dbus_fast import BusType, DBusError, Message, Variant
from dbus_fast.aio import MessageBus
from dbus_fast.service import PropertyAccess, ServiceInterface, dbus_method, dbus_property

from tarantino.btremote import hid

log = logging.getLogger("tarantino.btremote")

BLUEZ = "org.bluez"
ADAPTER = "/org/bluez/hci0"
ROOT = "/tarantino"
GATT_ROOT = f"{ROOT}/gatt"
AGENT_PATH = f"{ROOT}/agent"
DEFAULT_SOCKET = "/run/tarantino-btremote/remote.sock"

ADV_INTERVAL_MS = (20, 30)  # fast, like a real remote; the projector scans only briefly in standby
KEY_RELEASE_DELAY = 0.08
POLL = 0.25
RECONNECT_SECONDS = 15.0  # after a start, let a projector that is on reconnect
DISCONNECT_TIMEOUT = 3.0
WAKE_TIMEOUT_LIMITS = (1.0, 30.0)
PAIRING_LIMITS = (10.0, 300.0)


class CommandError(Exception):
    pass


def uuid16(value: int) -> str:
    return f"0000{value:04x}-0000-1000-8000-00805f9b34fb"


# -- GATT objects -------------------------------------------------------------


class GattService(ServiceInterface):
    def __init__(self, uuid: str):
        super().__init__("org.bluez.GattService1")
        self._uuid = uuid

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return self._uuid

    @dbus_property(access=PropertyAccess.READ)
    def Primary(self) -> "b":
        return True


class GattCharacteristic(ServiceInterface):
    def __init__(self, service_path: str, uuid: str, flags: list[str], value: bytes = b""):
        super().__init__("org.bluez.GattCharacteristic1")
        self._service = service_path
        self._uuid = uuid
        self._flags = flags
        self._value = value

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return self._uuid

    @dbus_property(access=PropertyAccess.READ)
    def Service(self) -> "o":
        return self._service

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":
        return self._flags

    @dbus_property(access=PropertyAccess.READ)
    def Value(self) -> "ay":
        return self._value

    @dbus_method()
    def ReadValue(self, options: "a{sv}") -> "ay":
        offset = options["offset"].value if "offset" in options else 0
        return self._value[offset:]

    @dbus_method()
    def WriteValue(self, value: "ay", options: "a{sv}"):
        self._value = bytes(value)

    @dbus_method()
    def StartNotify(self):
        pass

    @dbus_method()
    def StopNotify(self):
        pass

    def notify(self, value: bytes) -> None:
        self._value = value
        self.emit_properties_changed({"Value": value})


class GattDescriptor(ServiceInterface):
    def __init__(self, characteristic_path: str, uuid: str, value: bytes):
        super().__init__("org.bluez.GattDescriptor1")
        self._characteristic = characteristic_path
        self._uuid = uuid
        self._value = value

    @dbus_property(access=PropertyAccess.READ)
    def UUID(self) -> "s":
        return self._uuid

    @dbus_property(access=PropertyAccess.READ)
    def Characteristic(self) -> "o":
        return self._characteristic

    @dbus_property(access=PropertyAccess.READ)
    def Flags(self) -> "as":
        return ["read"]

    @dbus_method()
    def ReadValue(self, options: "a{sv}") -> "ay":
        offset = options["offset"].value if "offset" in options else 0
        return self._value[offset:]


# -- advertising and pairing --------------------------------------------------


class Advertisement(ServiceInterface):
    """Connectable advert (lets a paired projector that is on reconnect); subclasses add to it."""

    discoverable = False

    def __init__(self):
        super().__init__("org.bluez.LEAdvertisement1")

    @dbus_property(access=PropertyAccess.READ)
    def Type(self) -> "s":
        return "peripheral"

    @dbus_property(access=PropertyAccess.READ)
    def ServiceUUIDs(self) -> "as":
        return [uuid16(0x1812)]

    @dbus_property(access=PropertyAccess.READ)
    def Appearance(self) -> "q":
        return hid.APPEARANCE

    @dbus_property(access=PropertyAccess.READ)
    def Discoverable(self) -> "b":
        return self.discoverable

    @dbus_property(access=PropertyAccess.READ)
    def MinInterval(self) -> "u":
        return ADV_INTERVAL_MS[0]

    @dbus_property(access=PropertyAccess.READ)
    def MaxInterval(self) -> "u":
        return ADV_INTERVAL_MS[1]

    @dbus_method()
    def Release(self):
        pass


class PairingAdvertisement(Advertisement):
    discoverable = True

    @dbus_property(access=PropertyAccess.READ)
    def LocalName(self) -> "s":
        return hid.NAME


class WakeAdvertisement(Advertisement):
    def __init__(self, payload: bytes):
        super().__init__()
        self._payload = payload

    @dbus_property(access=PropertyAccess.READ)
    def ManufacturerData(self) -> "a{qv}":
        return {hid.WAKE_COMPANY_ID: Variant("ay", self._payload)}


class Agent(ServiceInterface):
    """Just-works pairing, accepted only while the pairing window is open."""

    def __init__(self, daemon: "RemoteDaemon"):
        super().__init__("org.bluez.Agent1")
        self.daemon = daemon

    def _check(self) -> None:
        if not self.daemon.pairing:
            raise DBusError("org.bluez.Error.Rejected", "Not in pairing mode")

    @dbus_method()
    def Release(self):
        pass

    @dbus_method()
    def RequestAuthorization(self, device: "o"):
        self._check()

    @dbus_method()
    def RequestConfirmation(self, device: "o", passkey: "u"):
        self._check()

    @dbus_method()
    def RequestPasskey(self, device: "o") -> "u":
        self._check()
        return 0

    @dbus_method()
    def RequestPinCode(self, device: "o") -> "s":
        self._check()
        return "0000"

    @dbus_method()
    def DisplayPasskey(self, device: "o", passkey: "u", entered: "q"):
        pass

    @dbus_method()
    def DisplayPinCode(self, device: "o", pincode: "s"):
        pass

    @dbus_method()
    def AuthorizeService(self, device: "o", uuid: "s"):
        pass

    @dbus_method()
    def Cancel(self):
        pass


# -- daemon ---------------------------------------------------------------------


class RemoteDaemon:
    def __init__(self, socket_path: Path):
        self.socket_path = socket_path
        self.bus: MessageBus | None = None
        self.reports: dict[int, GattCharacteristic] = {}
        self.pairing_task: asyncio.Task | None = None
        self.advert: tuple[str, str] | None = None  # (path, kind)
        self._adverts = 0
        self._adv_lock = asyncio.Lock()
        self._reconnect_task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._exit_code = 0

    @property
    def pairing(self) -> bool:
        return self.pairing_task is not None and not self.pairing_task.done()

    async def run(self) -> int:
        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        await self._watch_bluez()
        await self._setup()
        self.socket_path.unlink(missing_ok=True)
        server = await asyncio.start_unix_server(self._handle, path=str(self.socket_path))
        self.socket_path.chmod(0o660)
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._stop.set)
        log.info("Bluetooth remote ready; socket %s", self.socket_path)
        self._reconnect_task = asyncio.create_task(self._offer_reconnect())
        await self._stop.wait()
        server.close()
        for task in (self.pairing_task, self._reconnect_task):
            if task:
                task.cancel()
        if self._exit_code == 0:  # bluetoothd is still there
            await self._stop_advert()
            await self._drop_link()
        self.bus.disconnect()
        return self._exit_code

    async def _offer_reconnect(self) -> None:
        projector = await self._projector()
        if projector is None or projector["connected"]:
            return
        loop = asyncio.get_running_loop()
        deadline = loop.time() + RECONNECT_SECONDS
        async with self._adv_lock:
            await self._advertise(Advertisement(), "reconnect")
            try:
                while loop.time() < deadline:
                    await asyncio.sleep(POLL * 2)
                    projector = await self._projector()
                    if projector and projector["connected"]:
                        log.info("Projector reconnected after the start")
                        return
            finally:
                await self._stop_advert()

    async def _cancel_reconnect(self) -> None:
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

    async def _drop_link(self) -> None:
        """Disconnect the projector before our HID service goes away (see the module docstring)."""
        try:
            projector = await self._projector()
            if not (projector and projector["connected"]):
                return
            device = await self._proxy(projector["path"], "org.bluez.Device1")
            await asyncio.wait_for(device.call_disconnect(), DISCONNECT_TIMEOUT)
            log.info("Disconnected the projector before stopping")
        except (DBusError, TimeoutError) as exc:
            log.warning("Could not disconnect the projector before stopping: %s", exc)

    async def _watch_bluez(self) -> None:
        """Exit when bluetoothd restarts: our registrations are gone then; systemd restarts us."""
        rule = "type='signal',sender='org.freedesktop.DBus',member='NameOwnerChanged',arg0='org.bluez'"
        await self.bus.call(Message(
            destination="org.freedesktop.DBus", path="/org/freedesktop/DBus", interface="org.freedesktop.DBus",
            member="AddMatch", signature="s", body=[rule],
        ))  # fmt: skip

        def on_message(msg: Message) -> None:
            if msg.member == "NameOwnerChanged" and msg.body and msg.body[0] == BLUEZ:
                log.warning("bluetoothd restarted; exiting so systemd restarts the remote")
                self._exit_code = 1
                self._stop.set()

        self.bus.add_message_handler(on_message)

    async def _proxy(self, path: str, interface: str):
        introspection = await self.bus.introspect(BLUEZ, path)
        return self.bus.get_proxy_object(BLUEZ, path, introspection).get_interface(interface)

    async def _setup(self) -> None:
        self.adapter = await self._proxy(ADAPTER, "org.bluez.Adapter1")
        self.adv_mgr = await self._proxy(ADAPTER, "org.bluez.LEAdvertisingManager1")
        self.objects = await self._proxy("/", "org.freedesktop.DBus.ObjectManager")
        await self.adapter.set_powered(True)
        await self.adapter.set_alias(hid.NAME)
        await self.adapter.set_pairable(True)
        await self.adapter.set_pairable_timeout(0)

        self._export_gatt()
        gatt = await self._proxy(ADAPTER, "org.bluez.GattManager1")
        await gatt.call_register_application(GATT_ROOT, {})

        self.bus.export(AGENT_PATH, Agent(self))
        agents = await self._proxy("/org/bluez", "org.bluez.AgentManager1")
        await agents.call_register_agent(AGENT_PATH, "NoInputNoOutput")
        await agents.call_request_default_agent(AGENT_PATH)

    def _export_gatt(self) -> None:
        def service(name: str, uuid: int) -> str:
            path = f"{GATT_ROOT}/{name}"
            self.bus.export(path, GattService(uuid16(uuid)))
            return path

        def characteristic(service_path: str, name: str, uuid: int, flags: list[str], value: bytes):
            path = f"{service_path}/{name}"
            char = GattCharacteristic(service_path, uuid16(uuid), flags, value)
            self.bus.export(path, char)
            return path, char

        hid_service = service("hid", 0x1812)
        characteristic(hid_service, "info", 0x2A4A, ["read"], bytes([0x11, 0x01, 0x00, 0x02]))
        characteristic(hid_service, "map", 0x2A4B, ["encrypt-read"], hid.REPORT_MAP)
        for report_id, size in ((hid.REPORT_CONSUMER, 2), (hid.REPORT_PROGRAMMABLE, 1)):
            path, char = characteristic(hid_service, f"report{report_id}", 0x2A4D, ["encrypt-read", "notify"],
                                        bytes(size))  # fmt: skip
            self.bus.export(f"{path}/ref", GattDescriptor(path, uuid16(0x2908), bytes([report_id, 0x01])))
            self.reports[report_id] = char
        characteristic(hid_service, "control", 0x2A4C, ["write-without-response"], b"\x00")
        characteristic(hid_service, "protocol", 0x2A4E, ["read", "write-without-response"], b"\x01")
        battery = service("battery", 0x180F)
        characteristic(battery, "level", 0x2A19, ["read", "notify"], bytes([100]))
        info = service("info", 0x180A)
        characteristic(info, "pnp", 0x2A50, ["read"], bytes([0x02, 0x6B, 0x1D, 0x46, 0x02, 0x00, 0x01]))

    # -- state ----------------------------------------------------------------

    async def _projector(self) -> dict | None:
        """The paired device (the projector), if any."""
        objects = await self.objects.call_get_managed_objects()
        for path, interfaces in objects.items():
            device = interfaces.get("org.bluez.Device1")
            if device and path.startswith(ADAPTER + "/") and device["Paired"].value:
                return {
                    "path": path,
                    "address": device["Address"].value,
                    "name": device["Alias"].value if "Alias" in device else None,
                    "connected": device["Connected"].value,
                }
        return None

    async def status(self) -> dict:
        projector = await self._projector()
        return {
            "paired": projector is not None,
            "name": projector and projector["name"],
            "address": projector and projector["address"],
            "connected": bool(projector and projector["connected"]),
            "pairing": self.pairing,
            "advertising": self.advert and self.advert[1],
        }

    # -- adverts --------------------------------------------------------------

    async def _advertise(self, advert: Advertisement, kind: str) -> None:
        await self._stop_advert()
        self._adverts += 1
        path = f"{ROOT}/adv{self._adverts}"
        self.bus.export(path, advert)
        try:
            await self.adv_mgr.call_register_advertisement(path, {})
        except DBusError:
            self.bus.unexport(path)
            raise
        self.advert = (path, kind)

    async def _stop_advert(self) -> None:
        if self.advert is None:
            return
        path, _ = self.advert
        self.advert = None
        try:
            await self.adv_mgr.call_unregister_advertisement(path)
        except DBusError as exc:
            log.debug("Unregistering advert: %s", exc)
        self.bus.unexport(path)

    # -- commands -------------------------------------------------------------

    async def wake(self, timeout: float) -> dict:
        projector = await self._projector()
        if projector is None:
            raise CommandError("Not paired with the projector")
        if projector["connected"]:
            return {"connected": True, "seconds": 0}
        if self.pairing:
            raise CommandError("Pairing in progress")
        await self._cancel_reconnect()
        loop = asyncio.get_running_loop()
        started = loop.time()
        async with self._adv_lock:
            await self._advertise(WakeAdvertisement(hid.wake_payload(projector["address"])), "wake")
            try:
                while loop.time() - started < timeout:
                    await asyncio.sleep(POLL)
                    projector = await self._projector()
                    if projector and projector["connected"]:
                        seconds = round(loop.time() - started, 1)
                        log.info("Projector connected %.1f s after the wake advert", seconds)
                        return {"connected": True, "seconds": seconds}
            finally:
                await self._stop_advert()
        log.warning("Projector did not connect within %.0f s of the wake advert", timeout)
        return {"connected": False, "seconds": round(loop.time() - started, 1)}

    async def key(self, name: str) -> dict:
        try:
            report_id, press, release = hid.key_reports(name)
        except KeyError:
            raise CommandError(f"Unknown key {name!r}; known: {', '.join(hid.KEYS)}") from None
        projector = await self._projector()
        if not (projector and projector["connected"]):
            raise CommandError("The projector is not connected to the Bluetooth remote")
        report = self.reports[report_id]
        report.notify(press)
        await asyncio.sleep(KEY_RELEASE_DELAY)
        report.notify(release)
        log.info("Key %s sent", name)
        return {}

    async def pair(self, seconds: float) -> dict:
        await self._cancel_reconnect()
        await self.stop_pairing()
        await self.unpair()
        async with self._adv_lock:
            await self._advertise(PairingAdvertisement(), "pairing")
        self.pairing_task = asyncio.create_task(self._pairing_window(seconds))
        log.info("Pairing window open for %.0f s", seconds)
        return await self.status()

    async def _pairing_window(self, seconds: float) -> None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + seconds
        try:
            while loop.time() < deadline:
                await asyncio.sleep(POLL * 2)
                projector = await self._projector()
                if projector:
                    device = await self._proxy(projector["path"], "org.bluez.Device1")
                    await device.set_trusted(True)
                    log.info("Paired with %s (%s)", projector["name"], projector["address"])
                    return
            log.info("Pairing window closed without a pairing")
        finally:
            if self.advert and self.advert[1] == "pairing":
                await self._stop_advert()

    async def stop_pairing(self) -> dict:
        if self.pairing:
            self.pairing_task.cancel()
            try:
                await self.pairing_task
            except asyncio.CancelledError:
                pass
        return await self.status()

    async def unpair(self) -> dict:
        while projector := await self._projector():
            await self.adapter.call_remove_device(projector["path"])
            log.info("Forgot the pairing with %s (%s)", projector["name"], projector["address"])
        return await self.status()

    # -- socket ---------------------------------------------------------------

    async def _dispatch(self, request: dict) -> dict:
        cmd = request.get("cmd")
        if cmd == "status":
            return await self.status()
        if cmd == "wake":
            return await self.wake(_clamp(request.get("timeout", 8), WAKE_TIMEOUT_LIMITS))
        if cmd == "key":
            return await self.key(str(request.get("key")))
        if cmd == "pair":
            return await self.pair(_clamp(request.get("seconds", 120), PAIRING_LIMITS))
        if cmd == "stop":
            return await self.stop_pairing()
        if cmd == "unpair":
            return await self.unpair()
        raise CommandError(f"Unknown command {cmd!r}")

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            request = json.loads(await reader.readline())
            response = {"ok": True} | await self._dispatch(request)
        except CommandError as exc:
            response = {"ok": False, "error": str(exc)}
        except DBusError as exc:
            log.warning("BlueZ error: %s", exc)
            response = {"ok": False, "error": f"BlueZ: {exc}"}
        except Exception as exc:  # noqa: BLE001 - always answer the client
            log.exception("Command failed")
            response = {"ok": False, "error": f"{exc.__class__.__name__}: {exc}"}
        try:
            writer.write(json.dumps(response).encode() + b"\n")
            await writer.drain()
        except OSError:
            pass  # the client gave up waiting
        finally:
            writer.close()


def _clamp(value, limits: tuple[float, float]) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise CommandError(f"Not a number: {value!r}") from None
    return min(max(number, limits[0]), limits[1])


def main() -> None:
    logging.basicConfig(
        level=os.environ.get("TARANTINO_LOG_LEVEL", "INFO"), format="%(name)s: %(message)s", stream=sys.stdout
    )
    socket_path = Path(os.environ.get("TARANTINO_BTREMOTE_SOCKET", DEFAULT_SOCKET))
    sys.exit(asyncio.run(RemoteDaemon(socket_path).run()))


if __name__ == "__main__":
    main()
