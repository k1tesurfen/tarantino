"""The config export file format (JSON), versioned.

Bump SCHEMA_VERSION and add a migrator to MIGRATIONS whenever the format changes.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

from tarantino.programme.rules import MovieFilters, Weights
from tarantino.settings import AppSettings

SCHEMA_VERSION = 3

# Every database table must be listed exactly once (enforced by a test):
CONFIG_TABLES = {"setting", "room", "cassette", "franchise"}  # always exported
STATE_TABLES = {"series_assignment", "programme_entry", "franchise_run"}  # exported unless state is excluded
REBUILDABLE_TABLES = {"library_item", "library_collection", "show", "vhs_event", "alembic_version"}  # never exported


class ItemRef(BaseModel):
    """A Jellyfin title, with enough detail to find it again if its id changes."""

    id: str
    type: Literal["movie", "series"]
    name: str
    year: int | None = None
    provider_ids: dict[str, str] = Field(default_factory=dict)


class RoomExport(BaseModel):
    number: int
    name: str
    kind: Literal["movie", "series"]
    filters: MovieFilters = Field(default_factory=MovieFilters)
    weights: Weights = Field(default_factory=Weights)
    active: bool = True


class CassetteExport(BaseModel):
    uid: str
    target: Literal["room", "franchise"] = "room"
    room_number: int | None = None  # None for the franchise cassette
    learned_at: datetime


class FranchiseExport(BaseModel):
    """Admin overrides of a franchise (TMDb collection); parts as title references."""

    collection_id: str
    name: str | None = None
    any_order: bool = False
    order: list[ItemRef] = Field(default_factory=list)
    excluded: list[ItemRef] = Field(default_factory=list)


class FranchiseRunExport(BaseModel):
    collection_id: str
    started_parts: list[ItemRef] = Field(default_factory=list)
    started_at: datetime
    last_advanced_at: datetime
    finished_at: datetime | None = None


class SeriesAssignmentExport(BaseModel):
    room_number: int
    series: ItemRef
    started_at: datetime
    finished_at: datetime | None = None
    dropped_at: datetime | None = None


class ProgrammeEntryExport(BaseModel):
    cinema_date: date
    room_number: int
    item: ItemRef | None
    showtimes: list[str] = Field(default_factory=list)
    source: Literal["generated", "franchise", "override"] = "generated"
    first_started_at: datetime | None = None
    marathon: list[ItemRef] = Field(default_factory=list)
    last_started_at: datetime | None = None
    created_at: datetime


class StateExport(BaseModel):
    series_assignments: list[SeriesAssignmentExport] = Field(default_factory=list)
    programme: list[ProgrammeEntryExport] = Field(default_factory=list)
    franchise_runs: list[FranchiseRunExport] = Field(default_factory=list)


class ConfigExport(BaseModel):
    format: Literal["tarantino-config"] = "tarantino-config"
    schema_version: int = SCHEMA_VERSION
    tarantino_version: str
    exported_at: datetime
    settings: AppSettings
    rooms: list[RoomExport]
    cassettes: list[CassetteExport] = Field(default_factory=list)
    franchises: list[FranchiseExport] = Field(default_factory=list)
    state: StateExport | None = None


def migrate_document(document: dict) -> dict:
    """Upgrade an older export to the current schema version."""
    version = document.get("schema_version")
    if not isinstance(version, int) or version < 1:
        raise ValueError("Not a tarantino config export (missing schema_version)")
    if version > SCHEMA_VERSION:
        raise ValueError(f"Export is from a newer tarantino (schema {version}); update tarantino first")
    while version < SCHEMA_VERSION:
        document = MIGRATIONS[version](document)
        version += 1
        document["schema_version"] = version
    return document


def _v1_to_v2(document: dict) -> dict:
    return document | {"cassettes": []}  # cassettes were added in schema 2


def _v2_to_v3(document: dict) -> dict:
    # Schema 3 added franchises, franchise runs, the franchise cassette and same-day marathons.
    cassettes = [c | {"target": "room"} for c in document.get("cassettes", [])]
    state = document.get("state")
    if state is not None:
        state = state | {"franchise_runs": []}
    return document | {"cassettes": cassettes, "franchises": [], "state": state}


MIGRATIONS: dict = {1: _v1_to_v2, 2: _v2_to_v3}  # {from_version: callable(document) -> document}
