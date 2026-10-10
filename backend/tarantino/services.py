"""Long-lived objects shared by the API routes, created in the app lifespan."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Request
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from tarantino.config import Settings
from tarantino.db import create_db_engine, make_session_factory, migrate
from tarantino.events import EventBus
from tarantino.jellyfin.client import JellyfinClient
from tarantino.jellyfin.library import LibrarySync
from tarantino.projector.adb import Adb, AdbError, run_adb
from tarantino.projector.cast import cast_wake
from tarantino.projector.projector import Projector
from tarantino.projector.remote import RemoteLink
from tarantino.settings import SettingsStore
from tarantino.shows.orchestrator import ShowOrchestrator, Timing

LIBRARY_SYNC_MINUTES = 15

log = logging.getLogger(__name__)


@dataclass
class Services:
    settings_env: Settings
    engine: Engine
    session_factory: sessionmaker
    settings: SettingsStore
    scheduler: AsyncIOScheduler
    events: EventBus
    projector: Projector
    adb_factory: Callable[[str], Adb] = Adb
    jellyfin: JellyfinClient | None = None
    library: LibrarySync | None = None
    shows: ShowOrchestrator | None = None

    @classmethod
    def create(
        cls,
        env: Settings,
        jellyfin_transport: httpx.AsyncBaseTransport | None = None,
        adb_factory: Callable[[str], Adb] = Adb,
        timing: Timing | None = None,
        remote: RemoteLink | None = None,
        waker: Callable[[str], Awaitable[bool]] = cast_wake,
    ) -> "Services":
        engine = create_db_engine(env.data_dir)
        migrate(engine)
        session_factory = make_session_factory(engine)
        settings = SettingsStore(session_factory)
        remote = remote or RemoteLink(env.data_dir / "androidtv")
        projector = Projector(settings, remote, adb_factory, waker)
        services = cls(
            env, engine, session_factory, settings, AsyncIOScheduler(), EventBus(), projector, adb_factory
        )
        if env.jellyfin_api_key:
            services.jellyfin = JellyfinClient(
                env.jellyfin_url, env.jellyfin_api_key.get_secret_value(), transport=jellyfin_transport
            )
            services.library = LibrarySync(services.jellyfin, session_factory, env.jellyfin_user)
            services.shows = ShowOrchestrator(
                services.jellyfin, services.library, session_factory, services.settings,
                services.events, projector, timing,
            )  # fmt: skip
        return services

    def start(self, run_jobs: bool = True) -> None:
        if run_jobs and self.adb_factory is Adb:
            # Warm up the adb server so the first status check or show is not slowed down.
            self._adb_warmup = asyncio.create_task(_start_adb_server())
        self.projector.connect()
        if run_jobs and self.library:
            # First run happens immediately, then every LIBRARY_SYNC_MINUTES.
            self.scheduler.add_job(
                self.library.run, "interval", minutes=LIBRARY_SYNC_MINUTES, id="library-sync",
                next_run_time=datetime.now(), coalesce=True, max_instances=1,
            )  # fmt: skip
        self.scheduler.start()

    async def close(self) -> None:
        self.scheduler.shutdown(wait=False)
        if self.shows:
            await self.shows.cancel_current()
        self.projector.remote.stop()
        if self.jellyfin:
            await self.jellyfin.aclose()
        self.engine.dispose()


async def _start_adb_server() -> None:
    try:
        await run_adb(["start-server"], 20)
    except AdbError as exc:
        log.warning("Could not start the adb server: %s", exc)


def get_services(request: Request) -> Services:
    return request.app.state.services
