"""M8: restarts, Jellyfin outages and logging."""

import logging
from datetime import datetime

from fastapi.testclient import TestClient

from conftest import FAST
from tarantino.logs import JournalFormatter
from tarantino.main import create_app
from tarantino.models import Show
from tarantino.services import Services


def make_app(settings, fake_jellyfin, fake_projector):
    return create_app(
        settings, jellyfin_transport=fake_jellyfin.transport, adb_factory=fake_projector.adb_factory,
        remote=fake_projector, waker=fake_projector.wake, timing=FAST, run_jobs=False,
    )  # fmt: skip


def test_show_running_during_a_restart_is_marked_failed(settings, fake_jellyfin, fake_projector):
    with TestClient(make_app(settings, fake_jellyfin, fake_projector)) as client:
        services: Services = client.app.state.services
        with services.session_factory.begin() as session:
            session.add(Show(trigger="vhs", item_id="x", item_name="Movie", state="running",
                             steps=[{"step": "projector", "status": "running"}], created_at=datetime.now()))  # fmt: skip

    with TestClient(make_app(settings, fake_jellyfin, fake_projector)) as client:
        show = client.get("/api/admin/shows").json()[0]
        assert show["state"] == "failed" and "restart" in show["error"]
        assert show["steps"][0]["status"] == "cancelled"


def test_programme_survives_a_restart(settings, fake_jellyfin, fake_projector):
    with TestClient(make_app(settings, fake_jellyfin, fake_projector)) as client:
        client.post("/api/admin/library/sync")
        before = client.get("/api/cinema/programme").json()["rooms"]

    fake_jellyfin.api_key = "rotated"  # Jellyfin unusable after the restart
    with TestClient(make_app(settings, fake_jellyfin, fake_projector)) as client:
        assert client.get("/api/cinema/programme").json()["rooms"] == before
        status = client.get("/api/admin/status").json()["jellyfin"]
        assert status["state"] == "error" and status["counts"]["movie"] == 7


def test_failed_sync_is_retried_soon_with_backoff(client, fake_jellyfin):
    services: Services = client.app.state.services
    fake_jellyfin.api_key = "wrong"  # Jellyfin is down or still booting
    delays = []
    for _ in range(5):
        client.portal.call(services._sync_and_programme)
        job = services.scheduler.get_job("library-retry")
        if job:
            delays.append(round((job.next_run_time.replace(tzinfo=None) - datetime.now()).total_seconds() / 60))
            job.remove()
    assert delays == [1, 2, 4, 8]  # then the regular 15-minute sync takes over

    fake_jellyfin.api_key = "test-key"
    client.portal.call(services._sync_and_programme)
    assert services._sync_failures == 0 and services.scheduler.get_job("library-retry") is None


def test_journal_lines_carry_syslog_priorities():
    formatter = JournalFormatter("%(name)s: %(message)s")
    line = lambda level: formatter.format(logging.LogRecord("t", level, "", 0, "msg", None, None))  # noqa: E731
    assert [line(lvl)[:3] for lvl in (logging.ERROR, logging.WARNING, logging.INFO, logging.DEBUG)] == [
        "<3>", "<4>", "<6>", "<7>"
    ]
