"""Health checks of the subsystems shown on the admin dashboard."""

from tarantino.jellyfin.client import JellyfinError
from tarantino.services import Services
from tarantino.shows.orchestrator import find_projector_session


async def jellyfin_status(services: Services) -> dict:
    library = services.library
    if services.jellyfin is None or library is None:
        return {"state": "unconfigured", "message": "TARANTINO_JELLYFIN_API_KEY is not set"}

    status: dict = {
        "counts": library.counts(),
        "user": library.user_name,
        "sync": {
            "running": library.running,
            "last_sync_at": library.last_sync_at.isoformat() if library.last_sync_at else None,
            "last_error": library.last_error,
        },
    }
    try:
        info = await services.jellyfin.system_info()
        await library.resolve_user()
    except JellyfinError as exc:
        return status | {"state": "error", "message": str(exc)}

    status |= {"version": info.get("Version"), "server_name": info.get("ServerName")}
    if library.last_error:
        return status | {"state": "warning", "message": f"Last library sync failed: {library.last_error}"}
    return status | {"state": "ok", "message": None}


async def projector_status(services: Services) -> dict:
    return await services.projector.status()


async def session_status(services: Services) -> dict:
    if services.jellyfin is None or services.library is None:
        return {"state": "unconfigured", "message": "Jellyfin is not configured"}
    device_id = services.settings.get().projector_device_id
    try:
        user_id = await services.library.resolve_user()
        sessions = await services.jellyfin.sessions(controllable_by_user_id=user_id, active_within_seconds=120)
    except JellyfinError as exc:
        return {"state": "error", "message": str(exc)}
    session = find_projector_session(sessions, device_id)
    if session is None:
        message = "Projector's Jellyfin app is not running" if device_id else "Select the projector's device below"
        return {"state": "warning" if device_id else "unconfigured", "message": message}
    now_playing = session.get("NowPlayingItem") or {}
    return {
        "state": "ok",
        "message": None,
        "device_name": session.get("DeviceName"),
        "now_playing": now_playing.get("Name"),
        "paused": (session.get("PlayState") or {}).get("IsPaused"),
    }
