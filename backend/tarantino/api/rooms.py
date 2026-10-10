from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from tarantino.models import LibraryItem, Room
from tarantino.programme.rules import PRESETS, MovieFilters, Weights
from tarantino.services import Services, get_services

# TODO(M4): protect with the admin login.
router = APIRouter(prefix="/api/admin", tags=["rooms"])

ServicesDep = Annotated[Services, Depends(get_services)]
RoomNumber = Annotated[int, Path(ge=1, le=99)]


class RoomIn(BaseModel):
    number: int = Field(ge=1, le=99, description="Also the cassette number.")
    name: str = Field(min_length=1, max_length=60)
    kind: Literal["movie", "series"]
    filters: MovieFilters = Field(default_factory=MovieFilters)
    weights: Weights = Field(default_factory=Weights)
    active: bool = True

    @model_validator(mode="after")
    def _series_rooms_have_no_rules(self) -> "RoomIn":
        if self.kind == "series":  # series rooms are random by design
            self.filters, self.weights = MovieFilters(), Weights()
        return self


def _room_view(room: Room) -> dict:
    return {
        "number": room.number,
        "name": room.name,
        "kind": room.kind,
        "filters": MovieFilters.model_validate(room.filters or {}).model_dump(),
        "weights": Weights.model_validate(room.weights or {}).model_dump(),
        "active": room.active,
    }


@router.get("/rooms")
def list_rooms(services: ServicesDep) -> list[dict]:
    with services.session_factory() as session:
        return [_room_view(r) for r in session.scalars(select(Room).order_by(Room.number))]


@router.get("/rooms/presets")
def presets() -> dict:
    return {name: filters.model_dump() for name, filters in PRESETS.items()}


@router.post("/rooms", status_code=201)
def create_room(services: ServicesDep, body: RoomIn) -> dict:
    try:
        with services.session_factory.begin() as session:
            room = Room(**body.model_dump())
            session.add(room)
            session.flush()
            view = _room_view(room)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=f"Room {body.number} already exists")
    return view


@router.put("/rooms/{number}")
def update_room(services: ServicesDep, number: RoomNumber, body: RoomIn) -> dict:
    try:
        with services.session_factory.begin() as session:
            room = session.scalar(select(Room).where(Room.number == number))
            if room is None:
                raise HTTPException(status_code=404, detail=f"No room {number}")
            if room.kind != body.kind:
                raise HTTPException(status_code=409, detail="A room cannot change between movies and series")
            for key, value in body.model_dump().items():
                setattr(room, key, value)
            session.flush()
            view = _room_view(room)
    except IntegrityError:
        raise HTTPException(status_code=409, detail=f"Room {body.number} already exists")
    return view


@router.delete("/rooms/{number}", status_code=204)
def delete_room(services: ServicesDep, number: RoomNumber) -> None:
    with services.session_factory.begin() as session:
        room = session.scalar(select(Room).where(Room.number == number))
        if room is None:
            raise HTTPException(status_code=404, detail=f"No room {number}")
        session.delete(room)


class PreviewRequest(BaseModel):
    filters: MovieFilters


@router.post("/rooms/preview")
def preview_filters(services: ServicesDep, body: PreviewRequest) -> dict:
    """How many movies a filter matches (live pool size in the room editor)."""
    with services.session_factory() as session:
        movies = session.scalars(select(LibraryItem).where(LibraryItem.type == "movie")).all()
    matches = [m for m in movies if body.filters.matches(m)]
    return {"count": len(matches), "sample": sorted(m.name for m in matches)[:10]}


@router.get("/library/facets")
def facets(services: ServicesDep) -> dict:
    """Distinct genres, tags and age ratings of the movies, for the filter editor."""
    with services.session_factory() as session:
        movies = session.scalars(select(LibraryItem).where(LibraryItem.type == "movie")).all()
    return {
        "genres": sorted({g for m in movies for g in m.genres}),
        "tags": sorted({t for m in movies for t in m.tags}),
        "official_ratings": sorted({m.official_rating for m in movies if m.official_rating}),
    }
