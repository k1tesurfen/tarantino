"""Room rules: which titles a room may show (filters) and how picks are biased (weights)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from tarantino.models import LibraryItem


class MovieFilters(BaseModel):
    watched: Literal["any", "unwatched", "watched"] = "any"
    favorite: Literal["any", "yes", "no"] = "any"
    genres_any: list[str] = Field(default_factory=list, description="At least one of these genres.")
    genres_none: list[str] = Field(default_factory=list, description="None of these genres.")
    tags_any: list[str] = Field(default_factory=list)
    tags_none: list[str] = Field(default_factory=list)
    official_ratings: list[str] = Field(default_factory=list, description="Only these age ratings (empty: all).")
    year_min: int | None = None
    year_max: int | None = None
    min_community_rating: float | None = Field(None, ge=0, le=10)
    min_critic_rating: float | None = Field(None, ge=0, le=100)
    runtime_min: int | None = Field(None, ge=0)
    runtime_max: int | None = Field(None, ge=0)

    def matches(self, item: LibraryItem) -> bool:
        if self.watched != "any" and item.played != (self.watched == "watched"):
            return False
        if self.favorite != "any" and item.favorite != (self.favorite == "yes"):
            return False
        genres = {g.casefold() for g in item.genres}
        if self.genres_any and not genres & {g.casefold() for g in self.genres_any}:
            return False
        if genres & {g.casefold() for g in self.genres_none}:
            return False
        tags = {t.casefold() for t in item.tags}
        if self.tags_any and not tags & {t.casefold() for t in self.tags_any}:
            return False
        if tags & {t.casefold() for t in self.tags_none}:
            return False
        if self.official_ratings and item.official_rating not in self.official_ratings:
            return False
        if not _in_range(item.year, self.year_min, self.year_max):
            return False
        if not _in_range(item.runtime_minutes, self.runtime_min, self.runtime_max):
            return False
        if self.min_community_rating is not None and (item.community_rating or 0) < self.min_community_rating:
            return False
        if self.min_critic_rating is not None and (item.critic_rating or 0) < self.min_critic_rating:
            return False
        return True


def _in_range(value: int | None, low: int | None, high: int | None) -> bool:
    if low is None and high is None:
        return True
    if value is None:
        return False
    return (low is None or value >= low) and (high is None or value <= high)


class Weights(BaseModel):
    """Bias of the random pick; each boost adds up to its value to a base weight of 1."""

    community_rating: float = Field(0, ge=0, le=10)
    critic_rating: float = Field(0, ge=0, le=10)
    recently_added: float = Field(0, ge=0, le=10, description="Favour titles added in the last year.")
    never_shown: float = Field(0, ge=0, le=10, description="Favour titles never programmed before.")

    def weight(self, item: LibraryItem, now: datetime, ever_shown: bool) -> float:
        weight = 1.0
        weight += self.community_rating * (item.community_rating or 0) / 10
        weight += self.critic_rating * (item.critic_rating or 0) / 100
        if item.date_added:
            age_days = max((now - item.date_added).days, 0)
            weight += self.recently_added * max(0.0, 1 - age_days / 365)
        if not ever_shown:
            weight += self.never_shown
        return weight


PRESETS: dict[str, MovieFilters] = {
    "unwatched": MovieFilters(watched="unwatched"),
    "unwatched_horror": MovieFilters(watched="unwatched", genres_any=["Horror"]),
    "favourites": MovieFilters(watched="watched", favorite="yes"),
}

# (number, name, kind, filters, weights) for a fresh installation; editable in admin.
DEFAULT_ROOMS: list[tuple[int, str, str, MovieFilters | None, Weights]] = [
    (1, "Premiere I", "movie", PRESETS["unwatched"], Weights(recently_added=3)),
    (2, "Premiere II", "movie", PRESETS["unwatched"], Weights(community_rating=3)),
    (3, "Premiere III", "movie", PRESETS["unwatched"], Weights()),
    (4, "Horror Hall", "movie", PRESETS["unwatched_horror"], Weights(community_rating=1)),
    (5, "Repertory", "movie", PRESETS["favourites"], Weights()),
    (6, "Discovery", "movie", PRESETS["unwatched"], Weights(never_shown=5)),
    (7, "Series Lounge I", "series", None, Weights()),
    (8, "Series Lounge II", "series", None, Weights()),
    (9, "Series Lounge III", "series", None, Weights()),
    (10, "Series Lounge IV", "series", None, Weights()),
]
