import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from tarantino.programme.engine import ProgrammeError
from tarantino.services import Services, get_services

# TODO(M4): protect with the admin login.
router = APIRouter(prefix="/api/admin", tags=["programme"])

ServicesDep = Annotated[Services, Depends(get_services)]


async def _run(services: Services, fn, *args) -> dict:
    try:
        await asyncio.to_thread(fn, *args)
    except ProgrammeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    services.events.publish("programme", {"date": services.programme.today().isoformat()})
    return services.programme.day_view()


@router.get("/programme")
async def get_programme(services: ServicesDep) -> dict:
    await services.ensure_programme()
    return services.programme.day_view()


class RerollRequest(BaseModel):
    room: int | None = None  # None: the whole day


@router.post("/programme/reroll")
async def reroll(services: ServicesDep, body: RerollRequest) -> dict:
    return await _run(services, services.programme.reroll, body.room)


class SwapRequest(BaseModel):
    room: int
    item_id: str


@router.post("/programme/swap")
async def swap(services: ServicesDep, body: SwapRequest) -> dict:
    return await _run(services, services.programme.swap, body.room, body.item_id)


@router.post("/rooms/{number}/drop-series")
async def drop_series(services: ServicesDep, number: int) -> dict:
    return await _run(services, services.programme.drop_series, number)


@router.post("/rooms/{number}/play", status_code=202)
async def play_room(services: ServicesDep, number: int) -> dict:
    try:
        show_id = await services.start_room(number, trigger="admin")
    except ProgrammeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return services.shows.get_show(show_id)
