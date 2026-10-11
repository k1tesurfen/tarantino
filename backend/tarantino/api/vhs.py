"""The VHS recorder API: cassette insert and eject (no login, LAN only).

Unknown cassettes are logged and ignored. In learn mode the next insert binds
the cassette to the armed room instead of playing it.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from tarantino.cassettes import CassetteError, normalise_uid
from tarantino.programme.engine import ProgrammeError
from tarantino.services import Services, get_services

router = APIRouter(prefix="/api/vhs", tags=["vhs"])

ServicesDep = Annotated[Services, Depends(get_services)]


class Insert(BaseModel):
    uid: str = Field(description="RFID UID of the cassette, e.g. 04A1B2C3 or 04:a1:b2:c3.")


class Eject(BaseModel):
    uid: str | None = None


def _uid(raw: str) -> str:
    try:
        return normalise_uid(raw)
    except CassetteError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/insert")
async def insert(services: ServicesDep, body: Insert) -> dict:
    """Returns the logged event; `outcome` is played, learned, unknown or ignored."""
    try:
        return await services.insert_cassette(_uid(body.uid))
    except ProgrammeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.post("/eject")
def eject(services: ServicesDep, body: Eject | None = None) -> dict:
    """Logged only: ejecting does not stop the show."""
    uid = _uid(body.uid) if body and body.uid else None
    return services.cassettes.record("eject", uid, "ignored", services.cassettes.room_for(uid) if uid else None)
