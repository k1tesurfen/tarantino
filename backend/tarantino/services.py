"""Long-lived objects shared by the API routes, created in the app lifespan."""

from dataclasses import dataclass
from datetime import datetime

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Request
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from tarantino.config import Settings
from tarantino.db import create_db_engine, make_session_factory, migrate
from tarantino.jellyfin.client import JellyfinClient
from tarantino.jellyfin.library import LibrarySync

LIBRARY_SYNC_MINUTES = 15


@dataclass
class Services:
    settings: Settings
    engine: Engine
    session_factory: sessionmaker
    scheduler: AsyncIOScheduler
    jellyfin: JellyfinClient | None = None
    library: LibrarySync | None = None

    @classmethod
    def create(cls, settings: Settings, jellyfin_transport: httpx.AsyncBaseTransport | None = None) -> "Services":
        engine = create_db_engine(settings.data_dir)
        migrate(engine)
        session_factory = make_session_factory(engine)
        services = cls(settings, engine, session_factory, AsyncIOScheduler())
        if settings.jellyfin_api_key:
            services.jellyfin = JellyfinClient(
                settings.jellyfin_url, settings.jellyfin_api_key.get_secret_value(), transport=jellyfin_transport
            )
            services.library = LibrarySync(services.jellyfin, session_factory, settings.jellyfin_user)
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
        if self.jellyfin:
            await self.jellyfin.aclose()
        self.engine.dispose()


def get_services(request: Request) -> Services:
    return request.app.state.services
