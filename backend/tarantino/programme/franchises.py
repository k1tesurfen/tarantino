"""Franchises: TMDb collections that are watched in order, with Tarantino's own progress.

A franchise is a TMDb collection with at least two distinct movies in the library.
Copies of the same movie (same TMDb id) are one part. Each franchise has a run that
remembers which parts were started; only the run's next part may be programmed.

Everything here is pure (no database access), so it is cheap to rebuild per request.
"""

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Literal

from tarantino.models import Franchise as FranchiseOverride
from tarantino.models import FranchiseRun, LibraryItem
from tarantino.settings import AppSettings

COLLECTION = "TmdbCollection"
RunState = Literal["fresh", "started", "resting"]


def collection_of(item: LibraryItem) -> str | None:
    if item.type != "movie":
        return None
    value = (item.provider_ids or {}).get(COLLECTION)
    return str(value) if value else None


def part_key(item: LibraryItem) -> str:
    """The TMDb movie id (shared by duplicate copies), or the Jellyfin id without one."""
    tmdb = (item.provider_ids or {}).get("Tmdb")
    return str(tmdb) if tmdb else f"item:{item.id}"


@dataclass
class Part:
    key: str
    items: list[LibraryItem]  # copies; the first is the one shown in admin

    @property
    def item(self) -> LibraryItem:
        return self.items[0]

    @property
    def item_ids(self) -> set[str]:
        return {i.id for i in self.items}

    @property
    def release(self) -> date:
        dates = [i.premiere_date or (date(i.year, 1, 1) if i.year else None) for i in self.items]
        return min((d for d in dates if d), default=date.max)

    def sort_key(self) -> tuple:
        return (self.release, self.item.name.casefold(), self.key)


@dataclass
class Franchise:
    collection_id: str
    name: str
    default_name: str
    any_order: bool
    parts: list[Part]  # in viewing order, without the excluded ones
    excluded: list[Part]
    custom_order: bool
    run: FranchiseRun | None
    state: RunState = "fresh"
    next_index: int | None = 0  # None while resting
    resting_until: datetime | None = None

    @property
    def ordered(self) -> bool:
        """The order rule applies (otherwise all parts behave like standalones)."""
        return not self.any_order and len(self.parts) >= 2

    @property
    def next_part(self) -> Part | None:
        return self.parts[self.next_index] if self.next_index is not None else None

    @property
    def started_keys(self) -> list[str]:
        return list(self.run.started_parts) if self.run and self.state != "fresh" else []

    def index_of(self, key: str) -> int | None:
        return next((i for i, p in enumerate(self.parts) if p.key == key), None)

    def part_for_item(self, item_id: str) -> tuple[int, Part] | None:
        return next(((i, p) for i, p in enumerate(self.parts) if item_id in p.item_ids), None)


def run_state(
    run: FranchiseRun | None, keys: list[str], now: datetime, settings: AppSettings
) -> tuple[RunState, int | None, datetime | None]:
    """(state, index of the next part or None while resting, resting until)."""
    if run is None or not run.started_parts:
        return "fresh", 0, None
    if run.finished_at:
        until = run.finished_at + timedelta(days=settings.franchise_rest_days)
        return ("resting", None, until) if now < until else ("fresh", 0, None)
    if now - run.last_advanced_at >= timedelta(days=settings.franchise_stall_days):
        return "fresh", 0, None  # stalled: start over
    positions = [keys.index(k) for k in run.started_parts if k in keys]
    if not positions or max(positions) + 1 >= len(keys):
        return "fresh", 0, None  # the started parts left the library or the order changed
    return "started", max(positions) + 1, None


def _order(parts: dict[str, Part], manual: list[str]) -> list[Part]:
    """Premiere-date order, or the admin's order with new parts slotted in by date."""
    by_date = sorted(parts.values(), key=Part.sort_key)
    ordered = [parts[k] for k in manual if k in parts]
    if not ordered:
        return by_date
    previous = None  # a new part goes right after the part released before it
    for part in by_date:
        if part not in ordered:
            ordered.insert(ordered.index(previous) + 1 if previous else 0, part)
        previous = part
    return ordered


_TRAILING = {"and", "the", "of", "a", "an", "part", "chapter", "episode", "vol", "volume", "&", "-", "–", "presents"}
_ARTICLES = {"the", "a", "an"}
_COLLECTION_SUFFIX = re.compile(r"\s+collection$", re.IGNORECASE)


def collection_name(name: str) -> str:
    """"The Terminator Collection" -> "The Terminator"."""
    return _COLLECTION_SUFFIX.sub("", name.strip()) or name.strip()


def guess_name(titles: list[str]) -> str | None:
    """A franchise name from its titles: the longest word prefix that at least half of them share,
    e.g. "Harry Potter" or "Back to the Future". None if there is no meaningful one."""
    words = [title.split() for title in titles]

    def key(word: str) -> str:
        return word.rstrip(":,.").casefold()

    need = max(2, math.ceil(len(titles) / 2))
    best: list[str] = []
    for title in words:
        for length in range(len(best) + 1, len(title) + 1):
            prefix = [key(w) for w in title[:length]]
            if sum([key(w) for w in other[:length]] == prefix for other in words) < need:
                break
            best = title[:length]
    while best and key(best[-1]) in _TRAILING:
        best = best[:-1]
    core = [key(w) for w in best if key(w) not in _ARTICLES]
    if len(core) == 1 and not any([key(w) for w in title if key(w) not in _ARTICLES] == core for title in words):
        return None  # "Finding" (Nemo, Dory): one word is only a name if it is a whole title (Alien, Rocky)
    name = " ".join(best).rstrip(":,-–")
    return name if re.search(r"[^\W\d_]{3}", name) else None


def _copy_rank(item: LibraryItem) -> tuple:
    return (not item.image_tags.get("Primary"), item.id)


@dataclass
class FranchiseIndex:
    franchises: dict[str, Franchise] = field(default_factory=dict)
    _by_item: dict[str, Franchise] = field(default_factory=dict)

    def franchise_of(self, item_id: str) -> Franchise | None:
        """The ordered franchise an item belongs to (None for standalones, excluded and any-order parts)."""
        franchise = self._by_item.get(item_id)
        return franchise if franchise and franchise.ordered and franchise.part_for_item(item_id) else None

    def badge(self, item_id: str) -> dict | None:
        """"Terminator · Part 2 of 6" for the cinema website."""
        franchise = self._by_item.get(item_id)
        if franchise is None or len(franchise.parts) < 2:
            return None
        found = franchise.part_for_item(item_id)
        if found is None:
            return None
        ordered = franchise.ordered
        return {
            "name": franchise.name,
            "part": found[0] + 1 if ordered else None,
            "parts": len(franchise.parts),
            "ordered": ordered,
        }

    def blocked(self, item_id: str) -> bool:
        """Not the next part of its franchise: may not be programmed."""
        franchise = self.franchise_of(item_id)
        if franchise is None:
            return False
        next_part = franchise.next_part
        return next_part is None or item_id not in next_part.item_ids

    def continues(self, item_id: str) -> bool:
        """The next part of a started run (skips the movie cooldown)."""
        franchise = self.franchise_of(item_id)
        return bool(franchise and franchise.state == "started" and item_id in franchise.next_part.item_ids)

    def started(self) -> list[Franchise]:
        """Started runs, in a stable order."""
        return sorted(
            (f for f in self.franchises.values() if f.ordered and f.state == "started"), key=lambda f: f.collection_id
        )

    def siblings(self, item_id: str) -> set[str]:
        """All copies of the item's part (including the item itself)."""
        franchise = self._by_item.get(item_id)
        if franchise:
            for part in franchise.parts + franchise.excluded:
                if item_id in part.item_ids:
                    return part.item_ids
        return {item_id}

    def item_ids(self, collection_id: str) -> set[str]:
        franchise = self.franchises.get(collection_id)
        return {i for p in franchise.parts for i in p.item_ids} if franchise else set()


def build_index(
    items: Iterable[LibraryItem],
    overrides: Iterable[FranchiseOverride],
    runs: Iterable[FranchiseRun],
    collection_names: dict[str, str],
    now: datetime,
    settings: AppSettings,
) -> FranchiseIndex:
    grouped: dict[str, dict[str, list[LibraryItem]]] = {}
    for item in items:
        if collection_id := collection_of(item):
            grouped.setdefault(collection_id, {}).setdefault(part_key(item), []).append(item)
    overrides_by_id = {o.collection_id: o for o in overrides}
    runs_by_id = {r.collection_id: r for r in runs}

    index = FranchiseIndex()
    for collection_id, copies in grouped.items():
        if len(copies) < 2:
            continue  # alone in its collection: a standalone
        override = overrides_by_id.get(collection_id)
        parts = {key: Part(key, sorted(found, key=_copy_rank)) for key, found in copies.items()}
        excluded_keys = set(override.excluded) if override else set()
        ordered = _order({k: p for k, p in parts.items() if k not in excluded_keys}, override.order if override else [])
        first = min(parts.values(), key=Part.sort_key).item.name
        if collection_id in collection_names:
            default_name = collection_name(collection_names[collection_id])
        else:
            default_name = guess_name([p.item.name for p in parts.values()]) or first
        franchise = Franchise(
            collection_id=collection_id,
            name=(override.name if override and override.name else default_name),
            default_name=default_name,
            any_order=bool(override and override.any_order),
            parts=ordered,
            excluded=sorted((p for k, p in parts.items() if k in excluded_keys), key=Part.sort_key),
            custom_order=bool(override and override.order),
            run=runs_by_id.get(collection_id),
        )
        if franchise.ordered:
            franchise.state, franchise.next_index, franchise.resting_until = run_state(
                franchise.run, [p.key for p in ordered], now, settings
            )
        index.franchises[collection_id] = franchise
        for part in parts.values():
            for item in part.items:
                index._by_item[item.id] = franchise
    return index


def advance(franchise: Franchise, run: FranchiseRun | None, item_id: str, now: datetime) -> FranchiseRun | None:
    """A part of an ordered franchise started via Tarantino: move the run past it.

    Returns the run to store (a new one if there was none), or None if nothing changed.
    Restarting an earlier part changes nothing; a part beyond the pointer jumps past it;
    the last part finishes the run, which then rests.
    """
    found = franchise.part_for_item(item_id)
    if not franchise.ordered or found is None:
        return None
    index, part = found
    if franchise.state != "started":  # fresh (also after a rest or a stall), or restarted while resting
        run = run or FranchiseRun(collection_id=franchise.collection_id)
        run.started_parts, run.started_at, run.finished_at = [], now, None
    elif index < franchise.next_index:
        return None
    run.started_parts = [*run.started_parts, part.key]
    run.last_advanced_at = now
    if index == len(franchise.parts) - 1:
        run.finished_at = now
    return run


def set_next(franchise: Franchise, run: FranchiseRun | None, key: str, now: datetime) -> FranchiseRun | None:
    """Admin: make `key` the next part (the first part resets the run). Returns the run to store, or None to delete."""
    index = franchise.index_of(key)
    if index is None:
        raise ValueError("Not a part of this franchise")
    if index == 0:
        return None
    run = run or FranchiseRun(collection_id=franchise.collection_id, started_at=now)
    run.started_parts = [p.key for p in franchise.parts[:index]]
    run.last_advanced_at, run.finished_at = now, None
    return run
