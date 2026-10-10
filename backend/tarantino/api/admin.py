from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, select

from tarantino import status
from tarantino.models import LibraryItem
from tarantino.services import Services, get_services

# TODO(M4): protect with the admin login.
router = APIRouter(prefix="/api/admin", tags=["admin"])

ServicesDep = Annotated[Services, Depends(get_services)]


@router.get("/status")
async def get_status(services: ServicesDep) -> dict:
    return {"jellyfin": await status.jellyfin_status(services)}


@router.post("/library/sync", status_code=202)
async def trigger_library_sync(services: ServicesDep, background: BackgroundTasks) -> dict:
    if services.library is None:
        raise HTTPException(status_code=503, detail="Jellyfin is not configured")
    if not services.library.running:
        background.add_task(services.library.run)
    return {"started": True}


@router.get("/library/sample")
def library_sample(services: ServicesDep, count: Annotated[int, Query(ge=1, le=48)] = 12) -> list[dict]:
    """A random handful of titles with posters, to eyeball the sync and image proxy."""
    with services.session_factory() as session:
        items = session.scalars(select(LibraryItem).order_by(func.random()).limit(count * 2)).all()
    return [
        {"id": i.id, "type": i.type, "name": i.name, "year": i.year, "poster_tag": i.image_tags["Primary"]}
        for i in items
        if i.image_tags.get("Primary")
    ][:count]
