"""Health checks of the subsystems shown on the admin dashboard."""

from tarantino.jellyfin.client import JellyfinError
from tarantino.services import Services


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
