import asyncio
import json
from pathlib import Path

import pytest

from conftest import projector_session
from test_shows import MOVIE, configure, start, synced  # noqa: F401 - synced is a fixture
from tarantino.btremote import hid
from tarantino.btremote.client import BtRemote, BtRemoteError


@pytest.fixture
def paired(synced, fake_bt):
    configure(synced, projector_address="192.0.2.50")
    fake_bt.paired = True
    return synced


# -- show flow --------------------------------------------------------------


def test_sleeping_projector_is_woken_via_bluetooth_and_jellyfin_opened_with_the_shortcut(paired, fake_projector):
    show = start(paired, MOVIE)

    assert show["state"] == "playing", show
    assert fake_projector.calls == ["bt-wake", "bt-star"]
    assert show["steps"][1]["message"] == "woke projector (Bluetooth), opened Jellyfin (shortcut key)"


def test_projector_on_with_launcher_in_front_only_gets_the_shortcut(paired, fake_projector):
    fake_projector.on = True
    show = start(paired, MOVIE)
    assert show["state"] == "playing", show
    assert fake_projector.calls == ["bt-star"]


def test_projector_on_with_jellyfin_in_front_is_left_alone(paired, fake_jellyfin, fake_projector):
    fake_projector.on, fake_projector.foreground = True, "org.jellyfin.androidtv"
    fake_jellyfin.sessions.append(projector_session())
    show = start(paired, MOVIE)
    assert show["state"] == "playing", show
    assert fake_projector.calls == []
    assert show["steps"][1]["message"] == "Projector on, Jellyfin open"


def test_failed_bluetooth_wake_falls_back_to_cast(paired, fake_bt, fake_projector):
    fake_bt.wake_works = False
    show = start(paired, MOVIE)
    assert show["state"] == "playing", show
    assert fake_projector.calls == ["bt-wake", "cast-wake", "remote-launch", "KEYCODE_DPAD_CENTER"]
    assert show["steps"][1]["message"].startswith("Bluetooth failed (the projector did not connect")
    assert show["steps"][1]["message"].endswith("woke projector (Cast), opened Jellyfin")


def test_unpaired_or_missing_bluetooth_service_uses_cast(paired, fake_bt, fake_projector):
    fake_bt.available = False
    show = start(paired, MOVIE)
    assert show["state"] == "playing", show
    assert fake_projector.calls == ["cast-wake", "remote-launch", "KEYCODE_DPAD_CENTER"]
    assert show["steps"][1]["message"] == "woke projector (Cast), opened Jellyfin"


# -- admin ------------------------------------------------------------------


def test_status_reports_the_bluetooth_remote_and_is_ok_in_standby(paired, fake_projector):
    fake_projector.state = "unreachable"  # the Android TV remote is gone in standby
    projector = paired.get("/api/admin/status").json()["projector"]
    assert projector["bluetooth"]["paired"] is True
    assert projector["state"] == "ok"
    assert "not connected" in projector["message"]


def test_bluetooth_admin_commands(paired, fake_bt, fake_projector):
    def command(**body):
        return paired.post("/api/admin/projector/bluetooth", json=body)

    assert command(action="wake").json()["connected"] is True
    assert command(action="key", key="star").status_code == 200
    assert fake_projector.foreground == "org.jellyfin.androidtv"
    assert command(action="pair").json()["pairing"] is True
    assert command(action="stop").json()["pairing"] is False
    assert command(action="key", key="star").status_code == 409  # not paired any more
    fake_bt.available = False
    response = command(action="unpair")
    assert response.status_code == 503
    assert "not reachable" in response.json()["detail"]
    assert command(action="dance").status_code == 422


# -- protocol pieces --------------------------------------------------------


def test_wake_payload_carries_the_projector_address_reversed():
    payload = hid.wake_payload("12:34:56:78:9A:BC")
    assert payload[:7] == bytes.fromhex("00bc9a78563412")
    assert payload[7:] == hid.WAKE_SIGNATURE
    assert len(payload) == 16
    with pytest.raises(ValueError):
        hid.wake_payload("12:34")


def test_key_reports():
    assert hid.key_reports("star") == (hid.REPORT_PROGRAMMABLE, b"\x01", b"\x00")
    assert hid.key_reports("home") == (hid.REPORT_CONSUMER, bytes([0x23, 0x02]), b"\x00\x00")
    with pytest.raises(KeyError):
        hid.key_reports("dance")


def test_client_reports_a_missing_service_as_unavailable(tmp_path):
    status = asyncio.run(BtRemote(tmp_path / "missing.sock").status())
    assert status["available"] is False and status["paired"] is False


def test_client_talks_json_lines(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # a relative path keeps the socket path short enough
    path = Path("remote.sock")
    requests = []

    async def handle(reader, writer):
        request = json.loads(await reader.readline())
        requests.append(request)
        reply = {"ok": True, "connected": True} if request["cmd"] == "wake" else {"ok": False, "error": "nope"}
        writer.write(json.dumps(reply).encode() + b"\n")
        await writer.drain()
        writer.close()

    async def scenario():
        server = await asyncio.start_unix_server(handle, path=str(path))
        remote = BtRemote(path)
        try:
            assert await remote.wake(3) is True
            with pytest.raises(BtRemoteError, match="nope"):
                await remote.key("star")
        finally:
            server.close()

    asyncio.run(scenario())
    assert requests == [{"cmd": "wake", "timeout": 3}, {"cmd": "key", "key": "star"}]
