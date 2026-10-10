from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from tarantino.services import Services, get_services

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events")
async def events(services: Annotated[Services, Depends(get_services)]) -> StreamingResponse:
    """Server-sent events: `show` (show progress); more event types follow."""
    return StreamingResponse(
        services.events.stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
