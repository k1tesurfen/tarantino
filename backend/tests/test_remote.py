"""The Android TV remote link: connects only on demand, never retries in the background."""

import asyncio

from androidtvremote2 import CannotConnect

from tarantino.projector.remote import RemoteLink


class SlowBootRemote:
    """Refuses connections until `ready_after` seconds after it was created (the projector booting)."""

    def __init__(self, ready_after: float):
        self.ready_at = asyncio.get_running_loop().time() + ready_after
        self.attempts = 0
        self.on_available = None
        self.library_reconnecting = False

    async def async_generate_cert_if_missing(self):
        return False

    async def async_connect(self):
        self.attempts += 1
        if asyncio.get_running_loop().time() < self.ready_at:
            raise CannotConnect("Connection refused")

    def add_is_available_updated_callback(self, callback):
        self.on_available = callback

    def keep_reconnecting(self, callback):
        self.library_reconnecting = True  # would retry forever with a back-off of up to 30 s

    def disconnect(self):
        self.library_reconnecting = False

    def go_to_standby(self, ready_after: float):
        """The connection drops; the remote service comes back `ready_after` seconds later."""
        self.ready_at = asyncio.get_running_loop().time() + ready_after
        self.on_available(False)


class HangingRemote(SlowBootRemote):
    """Accepts the TCP connection but never starts the remote service."""

    async def async_connect(self):
        self.attempts += 1
        await asyncio.Event().wait()


def link_for(fake, tmp_path) -> RemoteLink:
    link = RemoteLink(tmp_path, factory=lambda *args: fake)
    link.retry_seconds = 0.05
    link.configure("192.0.2.50")
    return link


def test_configuring_does_not_connect(tmp_path):
    async def scenario():
        fake = SlowBootRemote(ready_after=0)
        link = link_for(fake, tmp_path)
        await asyncio.sleep(0.1)
        return link.state, fake.attempts

    assert asyncio.run(scenario()) == ("disconnected", 0)


def test_connects_on_demand_and_retries_until_the_projector_is_up(tmp_path):
    async def scenario():
        fake = SlowBootRemote(ready_after=0.3)
        link = link_for(fake, tmp_path)
        connected = await link.ensure_connected(timeout=2)
        return connected, link.state, fake.attempts, fake.library_reconnecting

    connected, state, attempts, watching = asyncio.run(scenario())
    assert connected and state == "connected"
    assert attempts >= 3  # retried every few seconds (here: 0.05 s)
    assert watching  # the library reports drops of this connection


def test_gives_up_at_the_timeout(tmp_path):
    async def scenario():
        fake = SlowBootRemote(ready_after=10)
        link = link_for(fake, tmp_path)
        return await link.ensure_connected(timeout=0.2), link.state

    assert asyncio.run(scenario()) == (False, "unreachable")


def test_a_dropped_connection_is_not_retried_in_the_background(tmp_path):
    """The projector goes to standby: the link lets go, and the next show connects again."""

    async def scenario():
        fake = SlowBootRemote(ready_after=0)
        link = link_for(fake, tmp_path)
        assert await link.ensure_connected(timeout=1)
        fake.go_to_standby(ready_after=0.2)
        attempts = fake.attempts
        await asyncio.sleep(0.3)
        idle = (link.state, fake.attempts - attempts, fake.library_reconnecting)
        reconnected = await link.ensure_connected(timeout=1)
        return idle, reconnected

    idle, reconnected = asyncio.run(scenario())
    assert idle == ("disconnected", 0, False)
    assert reconnected


def test_a_hanging_connect_attempt_times_out(tmp_path):
    async def scenario():
        fake = HangingRemote(ready_after=0)
        link = link_for(fake, tmp_path)
        link.retry_seconds = 0.01
        connected = await link.ensure_connected(timeout=0.5, attempt_timeout=0.05)
        return connected, fake.attempts

    connected, attempts = asyncio.run(scenario())
    assert not connected
    assert attempts >= 3  # each attempt gave up instead of blocking the loop
