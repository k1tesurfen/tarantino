"""Admin: cassettes, learn mode and the VHS event log."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field

from tarantino.cassettes import LEARN_SECONDS, CassetteError, normalise_uid
from tarantino.services import Services, get_services

router = APIRouter(prefix="/api/admin/cassettes", tags=["cassettes"])

ServicesDep = Annotated[Services, Depends(get_services)]


def _overview(services: Services) -> dict:
    return {
        "rooms": services.cassettes.rooms(),
        "learn": services.cassettes.learn_state(),
        "events": services.cassettes.recent_events(),
    }


@router.get("")
def overview(services: ServicesDep) -> dict:
    return _overview(services)


class LearnRequest(BaseModel):
    room: int = Field(ge=1, le=99)
    seconds: int = Field(LEARN_SECONDS, ge=5, le=600)


@router.post("/learn")
def arm_learn_mode(services: ServicesDep, body: LearnRequest) -> dict:
    """The next cassette inserted within `seconds` is bound to `room`."""
    try:
        return services.cassettes.arm(body.room, body.seconds)
    except CassetteError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/learn", status_code=204)
def cancel_learn_mode(services: ServicesDep) -> None:
    services.cassettes.disarm()


class Assignment(BaseModel):
    room: int = Field(ge=1, le=99)


def _uid(raw: str) -> str:
    try:
        return normalise_uid(raw)
    except CassetteError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.put("/{uid}")
def assign(services: ServicesDep, uid: Annotated[str, Path()], body: Assignment) -> dict:
    """Bind a cassette to a room directly, e.g. an unknown UID from the log."""
    try:
        services.cassettes.bind(_uid(uid), body.room)
    except CassetteError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _overview(services)


@router.delete("/{uid}")
def remove(services: ServicesDep, uid: Annotated[str, Path()]) -> dict:
    try:
        services.cassettes.remove(_uid(uid))
    except CassetteError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return _overview(services)
