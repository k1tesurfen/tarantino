import asyncio
import re
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from tarantino import status
from tarantino.jellyfin.client import JellyfinError
from tarantino.models import LibraryItem
from tarantino.projector.remote import RemoteError
from tarantino.services import Services, get_services
from tarantino.settings import AppSettings
from tarantino.shows.orchestrator import find_projector_session

# TODO(M4): protect with the admin login.
router = APIRouter(prefix="/api/admin", tags=["admin"])

ServicesDep = Annotated[Services, Depends(get_services)]


def _require_jellyfin(services: Services) -> None:
    if services.jellyfin is None or services.library is None or services.shows is None:
        raise HTTPException(status_code=503, detail="Jellyfin is not configured")


@router.get("/status")
async def get_status(services: ServicesDep) -> dict:
    jellyfin, projector, session = await asyncio.gather(
        status.jellyfin_status(services), status.projector_status(services), status.session_status(services)
    )
    return {"jellyfin": jellyfin, "projector": projector, "session": session}


# -- settings ---------------------------------------------------------------


@router.get("/settings")
def get_settings(services: ServicesDep) -> AppSettings:
    return services.settings.get()


@router.patch("/settings")
def update_settings(services: ServicesDep, changes: Annotated[dict, Body()]) -> AppSettings:
    try:
        return services.settings.update(changes)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# -- library ----------------------------------------------------------------


@router.post("/library/sync", status_code=202)
async def trigger_library_sync(services: ServicesDep, background: BackgroundTasks) -> dict:
    _require_jellyfin(services)
    if not services.library.running:
        background.add_task(services.library.run)
    return {"started": True}


def _item_summary(item: LibraryItem) -> dict:
    return {
        "id": item.id,
        "type": item.type,
        "name": item.name,
        "year": item.year,
        "poster_tag": item.image_tags.get("Primary"),
        "played": item.played,
    }


@router.get("/library/sample")
def library_sample(services: ServicesDep, count: Annotated[int, Query(ge=1, le=48)] = 12) -> list[dict]:
    """A random handful of titles with posters, to eyeball the sync and image proxy."""
    with services.session_factory() as session:
        items = session.scalars(select(LibraryItem).order_by(func.random()).limit(count * 2)).all()
    return [_item_summary(i) for i in items if i.image_tags.get("Primary")][:count]


@router.get("/library/search")
def library_search(services: ServicesDep, q: Annotated[str, Query(min_length=1, max_length=100)]) -> list[dict]:
    pattern = f"%{q.strip()}%"
    with services.session_factory() as session:
        items = session.scalars(
            select(LibraryItem)
            .where(or_(LibraryItem.name.ilike(pattern), LibraryItem.original_title.ilike(pattern)))
            .order_by(LibraryItem.sort_name)
            .limit(20)
        ).all()
    return [_item_summary(i) for i in items]


# -- projector & sessions ---------------------------------------------------


def _host_of(remote_end_point: str | None) -> str | None:
    if not remote_end_point:
        return None
    host = remote_end_point.removeprefix("::ffff:")
    return re.sub(r":\d+$", "", host) if host.count(":") == 1 else host


@router.get("/sessions")
async def list_sessions(services: ServicesDep) -> list[dict]:
    """Recent Jellyfin sessions, so the admin can pick the projector's device."""
    _require_jellyfin(services)
    try:
        sessions = await services.jellyfin.sessions(active_within_seconds=3600)
    except JellyfinError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
    selected = services.settings.get().projector_device_id
    projector = find_projector_session(sessions, selected)
    return [
        {
            "device_id": s.get("DeviceId"),
            "device_name": s.get("DeviceName"),
            "client": s.get("Client"),
            "version": s.get("ApplicationVersion"),
            "user": s.get("UserName"),
            "host": _host_of(s.get("RemoteEndPoint")),
            "last_activity": s.get("LastActivityDate"),
            "remote_control": bool(s.get("SupportsRemoteControl")),
            "now_playing": (s.get("NowPlayingItem") or {}).get("Name"),
            "selected": s.get("DeviceId") == selected,
            "is_projector": projector is not None and s.get("Id") == projector.get("Id"),
        }
        for s in sessions
        if s.get("DeviceId") != "tarantino-core"
    ]


@router.post("/projector/pairing/start")
async def start_pairing(services: ServicesDep) -> dict:
    """Ask the projector to show a pairing code on screen."""
    services.projector.connect()
    try:
        await services.projector.remote.start_pairing()
    except RemoteError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"state": services.projector.remote.state}


class PairingCode(BaseModel):
    code: str


@router.post("/projector/pairing/finish")
async def finish_pairing(services: ServicesDep, body: PairingCode) -> dict:
    try:
        await services.projector.remote.finish_pairing(body.code)
    except RemoteError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return {"state": services.projector.remote.state}


# -- shows ------------------------------------------------------------------


class ShowRequest(BaseModel):
    item_id: str


@router.post("/shows", status_code=202)
async def start_show(services: ServicesDep, request: ShowRequest) -> dict:
    _require_jellyfin(services)
    try:
        show_id = await services.shows.start(request.item_id, trigger="admin")
    except LookupError:
        raise HTTPException(status_code=404, detail="Unknown item")
    return services.shows.get_show(show_id)


@router.get("/shows")
def recent_shows(services: ServicesDep) -> list[dict]:
    _require_jellyfin(services)
    return services.shows.recent_shows()
