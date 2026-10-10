"""The show orchestrator: get a title playing on the projector.

Steps: resolve the title -> wake the projector and open Jellyfin ->
wait for the Jellyfin session -> PlayNow and confirm playback (with resends).
Only one show runs at a time; a new show cancels the running one.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy.orm import sessionmaker

from tarantino.events import EventBus
from tarantino.jellyfin.client import JellyfinClient, JellyfinError
from tarantino.jellyfin.library import LibrarySync
from tarantino.models import LibraryItem, Show
from tarantino.projector.adb import AdbError
from tarantino.projector.projector import Projector, ProjectorError
from tarantino.projector.remote import RemoteError
from tarantino.settings import SettingsStore

log = logging.getLogger(__name__)

SERIES_QUEUE_LIMIT = 25
TICKS_PER_SECOND = 10_000_000
# A movie that starts later than this was resumed by the client; seek back to 0.
RESUME_TOLERANCE_TICKS = 30 * TICKS_PER_SECOND


@dataclass
class Timing:
    """Waits and timeouts (seconds); tests shrink these."""

    poll: float = 1.0
    wake_timeout: float = 10.0
    app_launch_timeout: float = 20.0
    session_timeout: float = 40.0
    session_settle: float = 2.0
    launch_settle: float = 5.0  # extra time after the app was (re)started by us
    play_attempts: int = 3
    play_attempt_timeout: float = 8.0  # resend PlayNow if playback has not started by then


class ShowFailed(Exception):
    pass


@dataclass
class Plan:
    item_ids: list[str]
    start_ticks: int
    is_movie: bool
    label: str


@dataclass
class RunningShow:
    id: int
    task: asyncio.Task | None = None
    steps: list[dict] = field(default_factory=list)
    app_launched_at: datetime | None = None  # set when we started the Jellyfin app


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _parse_jellyfin_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone(UTC).replace(tzinfo=None)
    except ValueError:
        return None


def find_projector_session(sessions: list[dict], device_id: str | None) -> dict | None:
    """The projector's Jellyfin session: the configured device, else the only Android TV client."""
    controllable = [s for s in sessions if s.get("SupportsRemoteControl")]
    if device_id:
        return next((s for s in controllable if s.get("DeviceId") == device_id), None)
    android_tv = [s for s in controllable if "android tv" in (s.get("Client") or "").lower()]
    return android_tv[0] if len(android_tv) == 1 else None


class ShowOrchestrator:
    def __init__(
        self,
        jellyfin: JellyfinClient,
        library: LibrarySync,
        session_factory: sessionmaker,
        settings: SettingsStore,
        events: EventBus,
        projector: Projector,
        timing: Timing | None = None,
    ):
        self.jellyfin = jellyfin
        self.library = library
        self.session_factory = session_factory
        self.settings = settings
        self.events = events
        self.projector = projector
        self.timing = timing or Timing()
        self.current: RunningShow | None = None

    # -- public API ---------------------------------------------------------

    async def start(self, item_id: str, trigger: str) -> int:
        """Start a show for a library item and return its id (runs in the background)."""
        item = self._get_item(item_id)
        if item is None:
            raise LookupError(f"Unknown item {item_id}")
        await self.cancel_current()
        show_id = self._create_show(item, trigger)
        running = RunningShow(id=show_id)
        running.task = asyncio.create_task(self._run(running, item))
        self.current = running
        return show_id

    async def cancel_current(self) -> None:
        current = self.current
        if current and current.task and not current.task.done():
            current.task.cancel()
            try:
                await current.task
            except asyncio.CancelledError:
                pass

    def get_show(self, show_id: int) -> dict | None:
        with self.session_factory() as session:
            show = session.get(Show, show_id)
            return _show_dict(show) if show else None

    def recent_shows(self, limit: int = 10) -> list[dict]:
        with self.session_factory() as session:
            shows = session.query(Show).order_by(Show.id.desc()).limit(limit).all()
            return [_show_dict(s) for s in shows]

    # -- the sequence -------------------------------------------------------

    async def _run(self, running: RunningShow, item: LibraryItem) -> None:
        try:
            plan = await self._step(running, "resolve", self._resolve(item))
            await self._step(running, "projector", self._prepare_projector(running))
            session = await self._step(running, "session", self._wait_for_session(running))
            await self._step(running, "play", self._play_and_confirm(session, plan))
        except asyncio.CancelledError:
            self._finish(running, "cancelled", "Replaced by a newer show")
            raise
        except ShowFailed as exc:
            self._finish(running, "failed", str(exc))
        except Exception as exc:  # noqa: BLE001 - unexpected errors must still end the show
            log.exception("Show %s crashed", running.id)
            self._finish(running, "failed", f"Unexpected error: {exc}")
        else:
            self._finish(running, "playing", None)

    async def _step(self, running: RunningShow, name: str, coro):
        step = {"step": name, "status": "running", "message": None, "at": _now().isoformat()}
        running.steps.append(step)
        self._save_steps(running)
        try:
            result = await coro
        except (JellyfinError, AdbError, ProjectorError, RemoteError) as exc:
            step |= {"status": "failed", "message": str(exc)}
            self._save_steps(running)
            raise ShowFailed(f"{name}: {exc}") from exc
        except ShowFailed as exc:
            step |= {"status": "failed", "message": str(exc)}
            self._save_steps(running)
            raise
        except asyncio.CancelledError:
            step |= {"status": "cancelled"}
            self._save_steps(running)
            raise
        if isinstance(result, Plan):
            message = result.label
        elif isinstance(result, dict):
            message = f"Found {result.get('DeviceName', 'session')}"
        else:
            message = result
        step |= {"status": "done", "message": message}
        self._save_steps(running)
        return result

    async def _resolve(self, item: LibraryItem) -> Plan:
        if item.type == "movie":
            return Plan([item.id], 0, True, item.name)
        user_id = await self.library.resolve_user()
        episode = await self.jellyfin.next_up(user_id, item.id)
        if episode is None:
            raise ShowFailed(f"{item.name} has no next episode")
        episodes = await self.jellyfin.episodes(item.id, user_id, episode["Id"], SERIES_QUEUE_LIMIT)
        ids = [e["Id"] for e in episodes] or [episode["Id"]]
        resume = (episode.get("UserData") or {}).get("PlaybackPositionTicks") or 0
        label = f"{item.name} S{episode.get('ParentIndexNumber', 0):02d}E{episode.get('IndexNumber', 0):02d} " \
                f"+ {len(ids) - 1} queued"  # fmt: skip
        return Plan(ids, resume, False, label)

    async def _prepare_projector(self, running: RunningShow) -> str:
        started = _now()
        result = await self.projector.prepare_for_jellyfin(
            self.timing.poll, self.timing.wake_timeout, self.timing.app_launch_timeout
        )
        if result.launched_app:
            running.app_launched_at = started
        return result.message

    async def _wait_for_session(self, running: RunningShow) -> dict:
        device_id = self.settings.get().projector_device_id
        user_id = await self.library.resolve_user()
        launched_at = running.app_launched_at
        deadline = asyncio.get_running_loop().time() + self.timing.session_timeout
        while True:
            sessions = await self.jellyfin.sessions(controllable_by_user_id=user_id, active_within_seconds=120)
            session = find_projector_session(sessions, device_id)
            if session and launched_at:
                # Jellyfin keeps listing the previous session for a while after the app
                # closed; only a session that was active after our launch is usable.
                last_activity = _parse_jellyfin_time(session.get("LastActivityDate"))
                if last_activity is None or last_activity < launched_at:
                    session = None
            if session:
                # A freshly started app registers before it is ready for commands.
                await asyncio.sleep(self.timing.launch_settle if launched_at else self.timing.session_settle)
                return session
            if asyncio.get_running_loop().time() > deadline:
                hint = "" if device_id else " (no projector device selected in admin)"
                raise ShowFailed(f"Projector's Jellyfin session not found{hint}")
            await asyncio.sleep(self.timing.poll)

    async def _play_and_confirm(self, session: dict, plan: Plan) -> str:
        """Send PlayNow and wait for playback; resend if a slow client dropped it."""
        for attempt in range(1, self.timing.play_attempts + 1):
            await self.jellyfin.play(session["Id"], plan.item_ids, plan.start_ticks)
            result = await self._confirm(session, plan, self.timing.play_attempt_timeout)
            if result:
                return result if attempt == 1 else f"{result} (attempt {attempt})"
        raise ShowFailed(f"Playback did not start on the projector after {self.timing.play_attempts} attempts")

    async def _confirm(self, session: dict, plan: Plan, timeout: float) -> str | None:
        device_id = session.get("DeviceId")
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            sessions = await self.jellyfin.sessions(active_within_seconds=120)
            current = next((s for s in sessions if s.get("DeviceId") == device_id), None)
            now_playing = (current or {}).get("NowPlayingItem") or {}
            if now_playing.get("Id") in plan.item_ids:
                position = ((current or {}).get("PlayState") or {}).get("PositionTicks") or 0
                if plan.is_movie and position > RESUME_TOLERANCE_TICKS:
                    await self.jellyfin.seek(current["Id"], 0)
                    return f"Playing {now_playing.get('Name')} (client resumed; seeked back to start)"
                return f"Playing {now_playing.get('Name')}"
            if asyncio.get_running_loop().time() > deadline:
                return None
            await asyncio.sleep(self.timing.poll)

    # -- persistence & events -----------------------------------------------

    def _get_item(self, item_id: str) -> LibraryItem | None:
        with self.session_factory() as session:
            return session.get(LibraryItem, item_id)

    def _create_show(self, item: LibraryItem, trigger: str) -> int:
        with self.session_factory.begin() as session:
            show = Show(trigger=trigger, item_id=item.id, item_name=item.name, state="running",
                        steps=[], created_at=_now())  # fmt: skip
            session.add(show)
            session.flush()
            show_id = show.id
        self._publish(show_id)
        return show_id

    def _save_steps(self, running: RunningShow) -> None:
        with self.session_factory.begin() as session:
            session.get(Show, running.id).steps = [dict(s) for s in running.steps]
        self._publish(running.id)

    def _finish(self, running: RunningShow, state: str, error: str | None) -> None:
        with self.session_factory.begin() as session:
            show = session.get(Show, running.id)
            show.state, show.error, show.finished_at = state, error, _now()
            show.steps = [dict(s) for s in running.steps]
        log.info("Show %s %s%s", running.id, state, f": {error}" if error else "")
        self._publish(running.id)

    def _publish(self, show_id: int) -> None:
        show = self.get_show(show_id)
        if show:
            self.events.publish("show", show)


def _show_dict(show: Show) -> dict:
    return {
        "id": show.id,
        "trigger": show.trigger,
        "item_id": show.item_id,
        "item_name": show.item_name,
        "state": show.state,
        "steps": show.steps,
        "error": show.error,
        "created_at": show.created_at.isoformat(),
        "finished_at": show.finished_at.isoformat() if show.finished_at else None,
    }
