"""The public cinema API: no login, read-only apart from starting a room's show."""

import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from tarantino import status
from tarantino.models import LibraryItem
from tarantino.programme.engine import ProgrammeError
from tarantino.services import Services, get_services

router = APIRouter(prefix="/api/cinema", tags=["cinema"])

ServicesDep = Annotated[Services, Depends(get_services)]
ItemId = Annotated[str, Path(pattern=r"^[0-9a-f]{32}$")]

YOUTUBE_ID = re.compile(r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/)|youtu\.be/)([\w-]{11})")


def youtube_ids(urls: list[str]) -> list[str]:
    ids = []
    for url in urls:
        match = YOUTUBE_ID.search(url)
        if match and match.group(1) not in ids:
            ids.append(match.group(1))
    return ids


def _cinema_info(services: Services) -> dict:
    settings = services.settings.get()
    return {
        "names": {"modern": settings.theme_modern_name, "retro": settings.theme_retro_name},
        "default_theme": settings.default_theme,
    }


def _public_item(item: dict | None) -> dict | None:
    if item is None:
        return None
    return {k: v for k, v in item.items() if k != "trailer_urls"} | {"trailers": youtube_ids(item["trailer_urls"])}


def _public_room(room: dict) -> dict:
    return room | {"item": _public_item(room["item"]), "next": _public_item(room["next"])}


@router.get("/programme")
async def programme(services: ServicesDep) -> dict:
    await services.ensure_programme()
    view = services.programme.day_view()
    return {
        "date": view["date"],
        "cinema": _cinema_info(services),
        "rooms": [_public_room(r) for r in view["rooms"]],
    }


@router.get("/titles/{item_id}")
def title(services: ServicesDep, item_id: ItemId) -> dict:
    with services.session_factory() as session:
        item = session.get(LibraryItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Unknown title")
    screenings = [
        {"room": r["number"], "name": r["name"], "showtimes": r["showtimes"], "sold_out": r["sold_out"], "next": is_next}
        for r in services.programme.day_view()["rooms"]
        for is_next, offered in ((False, r["item"]), (True, r["next"]))
        if offered and offered["id"] == item_id
    ]
    return {
        "id": item.id,
        "type": item.type,
        "name": item.name,
        "original_title": item.original_title,
        "year": item.year,
        "premiere_date": item.premiere_date.isoformat() if item.premiere_date else None,
        "overview": item.overview,
        "tagline": item.tagline,
        "genres": item.genres,
        "studios": item.studios,
        "people": item.people,
        "official_rating": item.official_rating,
        "community_rating": item.community_rating,
        "critic_rating": item.critic_rating,
        "runtime_minutes": item.runtime_minutes,
        "unplayed_count": item.unplayed_count,
        "episode_count": item.episode_count,
        "poster_tag": item.image_tags.get("Primary"),
        "backdrop_tag": item.image_tags.get("Backdrop"),
        "logo_tag": item.image_tags.get("Logo"),
        "trailers": youtube_ids(item.trailer_urls),
        "franchise": services.programme.franchise_badge(item.id),
        "screenings": screenings,
    }


@router.post("/rooms/{number}/play", status_code=202)
async def play(
    services: ServicesDep, number: int, next: Annotated[bool, Query(description="The next franchise part.")] = False
) -> dict:
    try:
        show_id = await services.start_room(number, trigger="cinema", part="next" if next else "current")
    except ProgrammeError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return services.shows.get_show(show_id)


@router.get("/now")
async def now(services: ServicesDep) -> dict:
    """What the projector is doing: the latest show and the session's now-playing title."""
    if services.shows is None:
        return {"show": None, "now_playing": None}
    latest = services.shows.recent_shows(limit=1)
    session = await status.session_status(services)
    return {
        "show": latest[0] if latest else None,
        "now_playing": session.get("now_playing"),
        "paused": session.get("paused"),
    }
