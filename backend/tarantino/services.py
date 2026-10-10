"""Long-lived objects shared by the API routes, created in the app lifespan."""

from collections.abc import Callable
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
from tarantino.projector.adb import Adb
from tarantino.settings import SettingsStore
from tarantino.shows.orchestrator import ShowOrchestrator, Timing

LIBRARY_SYNC_MINUTES = 15


@dataclass
class Services:
    settings_env: Settings
    engine: Engine
    session_factory: sessionmaker
    settings: SettingsStore
    scheduler: AsyncIOScheduler
    events: EventBus
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
    ) -> "Services":
        engine = create_db_engine(env.data_dir)
        migrate(engine)
        session_factory = make_session_factory(engine)
        services = cls(
            env, engine, session_factory, SettingsStore(session_factory), AsyncIOScheduler(), EventBus(), adb_factory
        )
        if env.jellyfin_api_key:
            services.jellyfin = JellyfinClient(
                env.jellyfin_url, env.jellyfin_api_key.get_secret_value(), transport=jellyfin_transport
            )
            services.library = LibrarySync(services.jellyfin, session_factory, env.jellyfin_user)
            services.shows = ShowOrchestrator(
                services.jellyfin, services.library, session_factory, services.settings,
                services.events, adb_factory, timing,
            )  # fmt: skip
        return services

    def start(self, run_jobs: bool = True) -> None:
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
        if self.jellyfin:
            await self.jellyfin.aclose()
        self.engine.dispose()


def get_services(request: Request) -> Services:
    return request.app.state.services
