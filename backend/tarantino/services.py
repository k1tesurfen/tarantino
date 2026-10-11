"""Long-lived objects shared by the API routes, created in the app lifespan."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Request
from sqlalchemy import Engine
from sqlalchemy.orm import sessionmaker

from tarantino.cassettes import Cassettes
from tarantino.config import Settings, load_secret
from tarantino.configio.backups import BackupStore
from tarantino.db import create_db_engine, make_session_factory, migrate
from tarantino.events import EventBus
from tarantino.jellyfin.client import JellyfinClient
from tarantino.jellyfin.library import LibrarySync
from tarantino.projector.adb import Adb, AdbError, run_adb
from tarantino.projector.cast import cast_wake
from tarantino.projector.projector import Projector
from tarantino.programme.engine import Programme, ProgrammeError
from tarantino.projector.remote import RemoteLink
from tarantino.settings import SettingsStore
from tarantino.shows.orchestrator import ShowOrchestrator, Timing

LIBRARY_SYNC_MINUTES = 15
SYNC_RETRY_SECONDS = 60  # first retry after a failed sync (Jellyfin down); doubles up to the sync interval

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
    programme: Programme
    secret: bytes
    backups: BackupStore
    cassettes: Cassettes
    adb_factory: Callable[[str], Adb] = Adb
    jellyfin: JellyfinClient | None = None
    library: LibrarySync | None = None
    shows: ShowOrchestrator | None = None
    _sync_failures: int = field(default=0, init=False)

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
        programme = Programme(session_factory, settings)
        programme.ensure_rooms()
        events = EventBus()
        services = cls(
            env, engine, session_factory, settings, AsyncIOScheduler(), events, projector, programme,
            load_secret(env.data_dir), BackupStore(env.data_dir / "backups", session_factory, settings),
            Cassettes(session_factory, events), adb_factory,
        )  # fmt: skip
        if env.jellyfin_api_key:
            services.jellyfin = JellyfinClient(
                env.jellyfin_url, env.jellyfin_api_key.get_secret_value(), transport=jellyfin_transport
            )
            services.library = LibrarySync(services.jellyfin, session_factory, env.jellyfin_user)
            services.shows = ShowOrchestrator(
                services.jellyfin, services.library, session_factory, services.settings,
                services.events, projector, timing,
            )  # fmt: skip
            services.shows.on_playing = services._on_room_playing
            services.shows.recover_interrupted()
        return services

    def start(self, run_jobs: bool = True) -> None:
        if run_jobs and self.adb_factory is Adb:
            # Warm up the adb server so the first status check or show is not slowed down.
            self._adb_warmup = asyncio.create_task(_start_adb_server())
        self.projector.connect()
        if run_jobs and self.library:
            # Sync first (immediately, then every LIBRARY_SYNC_MINUTES), then make sure today exists.
            self.scheduler.add_job(
                self._sync_and_programme, "interval", minutes=LIBRARY_SYNC_MINUTES, id="library-sync",
                next_run_time=datetime.now(), coalesce=True, max_instances=1,
            )  # fmt: skip
            self.scheduler.add_job(
                self.backups.create, "cron", hour=3, minute=30, args=["nightly"], id="nightly-backup",
                coalesce=True, max_instances=1,
            )  # fmt: skip
            # Hourly check catches the rollover hour (whatever it is set to) without rescheduling.
            self.scheduler.add_job(
                self.ensure_programme, "cron", minute=1, id="programme", coalesce=True, max_instances=1
            )
        self.scheduler.start()

    async def _sync_and_programme(self) -> None:
        await self.library.run()
        if self.library.last_error:
            self._schedule_sync_retry()
        else:
            self._sync_failures = 0
        await self.ensure_programme()

    def _schedule_sync_retry(self) -> None:
        """Retry soon when Jellyfin is down (e.g. still booting), backing off to the normal interval."""
        self._sync_failures += 1
        delay = min(SYNC_RETRY_SECONDS * 2 ** (self._sync_failures - 1), LIBRARY_SYNC_MINUTES * 60)
        if delay >= LIBRARY_SYNC_MINUTES * 60:
            return  # the regular job comes round just as soon
        self.scheduler.add_job(
            self._sync_and_programme, "date", run_date=datetime.now() + timedelta(seconds=delay),
            id="library-retry", replace_existing=True,
        )  # fmt: skip
        log.info("Retrying the library sync in %d s", delay)

    async def ensure_programme(self) -> None:
        if await asyncio.to_thread(self.programme.ensure_day):
            self.events.publish("programme", {"date": self.programme.today().isoformat()})

    def _on_room_playing(self, room_id: int, item_id: str) -> None:
        self.programme.mark_playing(room_id, item_id)
        self.events.publish("programme", {"date": self.programme.today().isoformat()})

    async def start_room(self, room_number: int, trigger: str) -> int:
        """Start today's title of a room (cinema site, cassette, admin)."""
        if self.shows is None:
            raise ProgrammeError("Jellyfin is not configured")
        await self.ensure_programme()
        room, entry = self.programme.entry_for_room(room_number)
        if not room.active:
            raise ProgrammeError(f"{room.name} is closed")
        if entry is None or entry.item_id is None:
            raise ProgrammeError(f"Nothing is showing in {room.name} today")
        return await self.shows.start(entry.item_id, trigger, room_id=room.id)

    async def insert_cassette(self, uid: str) -> dict:
        """A cassette went into the VHS recorder: learn it, or start its room's show.

        Returns the logged event; raises ProgrammeError if the room cannot play.
        """
        if learn := self.cassettes.take_learn():
            note = self.cassettes.bind(uid, learn.room_number)
            return self.cassettes.record("insert", uid, "learned", learn.room_number, note)
        room_number = self.cassettes.room_for(uid)
        if room_number is None:
            return self.cassettes.record("insert", uid, "unknown", message="Not learned; ignored")
        if self.cassettes.is_repeat(uid):
            return self.cassettes.record("insert", uid, "ignored", room_number, "Repeated read; show already started")
        try:
            show_id = await self.start_room(room_number, trigger="vhs")
        except ProgrammeError as exc:
            self.cassettes.record("insert", uid, "failed", room_number, str(exc))
            raise
        return self.cassettes.record("insert", uid, "played", room_number, show_id=show_id)

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
        log.info("adb server not started (%s); ADB is only a fallback", exc)


def get_services(request: Request) -> Services:
    return request.app.state.services
