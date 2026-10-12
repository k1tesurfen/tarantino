"""Admin: franchises (TMDb collections watched in order) and their runs."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from tarantino.models import Franchise as FranchiseOverride
from tarantino.models import FranchiseRun
from tarantino.programme import franchises
from tarantino.programme.franchises import Franchise, Part
from tarantino.services import Services, get_services

router = APIRouter(prefix="/api/admin/franchises", tags=["franchises"])

ServicesDep = Annotated[Services, Depends(get_services)]
CollectionId = Annotated[str, Path(pattern=r"^[0-9A-Za-z]{1,32}$")]


def _part_view(part: Part, franchise: Franchise, index: int | None, today: dict[str, int]) -> dict:
    started = set(franchise.started_keys)
    return {
        "key": part.key,
        "item_id": part.item.id,
        "name": part.item.name,
        "year": part.item.year,
        "premiere_date": part.release.isoformat() if part.release.year < 9999 else None,
        "poster_tag": part.item.image_tags.get("Primary"),
        "played": any(i.played for i in part.items),
        "copies": len(part.items),
        "started": part.key in started,
        "next": index is not None and franchise.ordered and index == franchise.next_index,
        "today": next((today[i] for i in part.item_ids if i in today), None),
    }


def _view(franchise: Franchise, today: dict[str, int]) -> dict:
    run = franchise.run if franchise.state != "fresh" else None
    return {
        "collection_id": franchise.collection_id,
        "name": franchise.name,
        "default_name": franchise.default_name,
        "any_order": franchise.any_order,
        "custom_order": franchise.custom_order,
        "ordered": franchise.ordered,
        "state": franchise.state if franchise.ordered else "off",
        "progress": franchise.next_index if franchise.state == "started" else (
            len(franchise.parts) if franchise.state == "resting" else 0
        ),
        "started_at": run.started_at.isoformat() if run else None,
        "last_advanced_at": run.last_advanced_at.isoformat() if run else None,
        "resting_until": franchise.resting_until.isoformat() if franchise.resting_until else None,
        "parts": [_part_view(p, franchise, i, today) for i, p in enumerate(franchise.parts)],
        "excluded": [_part_view(p, franchise, None, today) for p in franchise.excluded],
    }


_STATE_ORDER = {"started": 0, "resting": 1, "fresh": 2, "off": 3}


def _today(services: Services) -> dict[str, int]:
    """Item id -> room number, for titles on today's programme (including offered next parts)."""
    today = {}
    for room in services.programme.day_view()["rooms"]:
        for offered in (room["item"], room["next"]):
            if offered:
                today[offered["id"]] = room["number"]
    return today


def _get(services: Services, collection_id: str) -> Franchise:
    franchise = services.programme.franchise_index().franchises.get(collection_id)
    if franchise is None:
        raise HTTPException(status_code=404, detail="No such franchise")
    return franchise


@router.get("")
def list_franchises(services: ServicesDep) -> list[dict]:
    today = _today(services)
    views = [_view(f, today) for f in services.programme.franchise_index().franchises.values()]
    return sorted(views, key=lambda v: (_STATE_ORDER[v["state"]], v["name"].casefold()))


class FranchiseChanges(BaseModel):
    name: str | None = Field(None, max_length=80, description="Empty: the collection's own name.")
    any_order: bool | None = None
    order: list[str] | None = Field(None, description="Part keys in viewing order; empty: by premiere date.")
    excluded: list[str] | None = Field(None, description="Part keys that behave as standalones.")


def _changed(services: Services, collection_id: str) -> dict:
    services.events.publish("programme", {"date": services.programme.today().isoformat()})
    return _view(_get(services, collection_id), _today(services))


@router.patch("/{collection_id}")
def update_franchise(services: ServicesDep, collection_id: CollectionId, body: FranchiseChanges) -> dict:
    franchise = _get(services, collection_id)
    keys = {p.key for p in franchise.parts + franchise.excluded}
    for field in ("order", "excluded"):
        unknown = set(getattr(body, field) or []) - keys
        if unknown:
            raise HTTPException(status_code=422, detail=f"Not parts of {franchise.name}: {', '.join(sorted(unknown))}")
    with services.session_factory.begin() as session:
        override = session.scalar(select(FranchiseOverride).where(FranchiseOverride.collection_id == collection_id))
        override = override or FranchiseOverride(collection_id=collection_id, order=[], excluded=[], any_order=False)
        changes = body.model_dump(exclude_unset=True)
        if "name" in changes:
            name = (body.name or "").strip()
            override.name = name if name and name != franchise.default_name else None
        if body.any_order is not None:
            override.any_order = body.any_order
        if body.order is not None:
            by_date = [p.key for p in sorted(franchise.parts + franchise.excluded, key=Part.sort_key)]
            order = list(dict.fromkeys(body.order))
            override.order = [] if [k for k in by_date if k in order] == order else order
        if body.excluded is not None:
            override.excluded = sorted(set(body.excluded))
        if override.name or override.any_order or override.order or override.excluded:
            session.add(override)
        elif override.id is not None:
            session.delete(override)
    return _changed(services, collection_id)


@router.post("/{collection_id}/reset")
def reset_run(services: ServicesDep, collection_id: CollectionId) -> dict:
    """Start the franchise over at part 1 (also ends a rest)."""
    _get(services, collection_id)
    with services.session_factory.begin() as session:
        session.execute(delete(FranchiseRun).where(FranchiseRun.collection_id == collection_id))
    return _changed(services, collection_id)


class NextPart(BaseModel):
    key: str


@router.post("/{collection_id}/next")
def set_next_part(services: ServicesDep, collection_id: CollectionId, body: NextPart) -> dict:
    """Make a part the next one (the parts before it count as started)."""
    franchise = _get(services, collection_id)
    if not franchise.ordered:
        raise HTTPException(status_code=409, detail=f"{franchise.name} has no order (any order, or too few parts)")
    clock = services.programme.clock
    with services.session_factory.begin() as session:
        run = session.scalar(select(FranchiseRun).where(FranchiseRun.collection_id == collection_id))
        try:
            updated = franchises.set_next(franchise, run, body.key, clock())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        if updated is None:
            if run is not None:
                session.delete(run)
        else:
            session.add(updated)
    return _changed(services, collection_id)
