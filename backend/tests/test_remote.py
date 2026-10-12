"""The Android TV remote link: reconnecting quickly while a show waits for it."""

import asyncio

from androidtvremote2 import CannotConnect

from tarantino.projector import remote as remote_module
from tarantino.projector.remote import RemoteLink


class SlowBootRemote:
    """Refuses connections until `ready_after` seconds after it was created (the projector booting)."""

    def __init__(self, ready_after: float):
        self.ready_at = asyncio.get_running_loop().time() + ready_after
        self.attempts = 0

    async def async_generate_cert_if_missing(self):
        return False

    async def async_connect(self):
        self.attempts += 1
        if asyncio.get_running_loop().time() < self.ready_at:
            raise CannotConnect("Connection refused")

    def add_is_available_updated_callback(self, callback):
        pass

    def keep_reconnecting(self, callback):
        pass

    def disconnect(self):
        pass


def test_a_waiting_show_retries_at_a_short_interval(tmp_path, monkeypatch):
    """Tonight's failure: the first attempt after a wake comes too early, and the next regular
    retry (30 s) came after the show had given up. A waiting show now retries every few seconds."""
    monkeypatch.setattr(remote_module, "RETRY_SECONDS", 30)

    async def scenario():
        fake = SlowBootRemote(ready_after=0.3)
        link = RemoteLink(tmp_path, factory=lambda *args: fake)
        link.waiting_retry_seconds = 0.05
        link.configure("192.0.2.50")
        await asyncio.sleep(0.05)
        assert link.state == "unreachable"  # in standby: now waiting for the 30 s retry
        connected = await link.wait_connected(timeout=2)
        link.stop()
        return connected, fake.attempts

    connected, attempts = asyncio.run(scenario())
    assert connected
    assert attempts >= 3  # retried while waiting instead of sleeping 30 s


def test_without_a_waiting_show_the_regular_interval_applies(tmp_path, monkeypatch):
    async def scenario():
        fake = SlowBootRemote(ready_after=10)
        link = RemoteLink(tmp_path, factory=lambda *args: fake)
        link.waiting_retry_seconds = 0.01
        link.configure("192.0.2.50")
        await asyncio.sleep(0.2)
        assert await link.wait_connected(timeout=0.1) is False
        attempts_after_wait = fake.attempts
        await asyncio.sleep(0.2)
        link.stop()
        return attempts_after_wait, fake.attempts

    during, after = asyncio.run(scenario())
    assert after <= during + 1  # back to the 30 s interval once nobody waits
