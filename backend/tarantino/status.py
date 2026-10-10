"""Health checks of the subsystems shown on the admin dashboard."""

import asyncio
import os

import httpx

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


async def home_assistant_status(services: Services) -> dict:
    url = services.settings.get().ha_url
    token = services.settings_env.ha_token
    if not url:
        return {"state": "unconfigured", "message": "Set the Home Assistant URL in settings"}
    if token is None or not token.get_secret_value():
        return {"state": "unconfigured", "message": "TARANTINO_HA_TOKEN is not set", "url": url}
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(
                f"{url}/api/", headers={"Authorization": f"Bearer {token.get_secret_value()}"}
            )
    except httpx.HTTPError as exc:
        return {"state": "error", "message": f"Unreachable: {exc.__class__.__name__}", "url": url}
    if response.status_code == 401:
        return {"state": "error", "message": "Home Assistant rejected the token", "url": url}
    if response.is_error:
        return {"state": "error", "message": f"HTTP {response.status_code}", "url": url}
    return {"state": "ok", "message": None, "url": url}


NFS_TIMEOUT = 5.0


def _probe_mount(path: str) -> int:
    # Listing triggers the systemd automount; a dead NFS server makes this hang,
    # which is why it runs in a thread with a timeout.
    return len(os.listdir(path))


async def media_status(services: Services) -> dict:
    paths = services.settings.get().media_paths
    if not paths:
        return {"state": "unconfigured", "message": "Add media paths in settings", "mounts": []}
    mounts = []
    for path in paths:
        try:
            entries = await asyncio.wait_for(asyncio.to_thread(_probe_mount, path), NFS_TIMEOUT)
        except TimeoutError:
            mounts.append({"path": path, "ok": False, "message": "Timed out (NFS server down?)"})
        except OSError as exc:
            mounts.append({"path": path, "ok": False, "message": exc.strerror or str(exc)})
        else:
            ok = entries > 0
            mounts.append({"path": path, "ok": ok, "message": f"{entries} entries" if ok else "Empty (not mounted?)"})
    failed = [m for m in mounts if not m["ok"]]
    if failed:
        return {"state": "error", "message": f"{len(failed)} of {len(mounts)} mounts unavailable", "mounts": mounts}
    return {"state": "ok", "message": None, "mounts": mounts}
