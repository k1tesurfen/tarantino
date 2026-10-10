"""Mirror the user's Jellyfin movies and series into the local database."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import sessionmaker

from tarantino.jellyfin.client import JellyfinClient, JellyfinError
from tarantino.models import LibraryItem

log = logging.getLogger(__name__)

FIELDS = [
    "Genres", "Tags", "Studios", "People", "Overview", "Taglines", "ProviderIds", "RemoteTrailers",
    "DateCreated", "SortName", "OriginalTitle", "RecursiveItemCount", "ChildCount",
]  # fmt: skip
ITEM_TYPES = {"Movie": "movie", "Series": "series"}
MAX_ACTORS = 10
TICKS_PER_MINUTE = 600_000_000


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).astimezone(UTC).replace(tzinfo=None)
    except ValueError:
        return None


def _parse_date(value: str | None) -> date | None:
    parsed = _parse_datetime(value)
    return parsed.date() if parsed else None


def _people(people: list[dict]) -> list[dict]:
    directors = [p for p in people if p.get("Type") == "Director"]
    actors = [p for p in people if p.get("Type") == "Actor"][:MAX_ACTORS]
    return [{"name": p.get("Name"), "role": p.get("Role"), "type": p.get("Type")} for p in directors + actors]


def item_to_row(item: dict, synced_at: datetime) -> dict:
    user_data = item.get("UserData") or {}
    image_tags = dict(item.get("ImageTags") or {})
    if item.get("BackdropImageTags"):
        image_tags["Backdrop"] = item["BackdropImageTags"][0]
    ticks = item.get("RunTimeTicks")
    is_series = item["Type"] == "Series"
    return {
        "id": item["Id"],
        "type": ITEM_TYPES[item["Type"]],
        "name": item.get("Name") or "",
        "sort_name": item.get("SortName"),
        "original_title": item.get("OriginalTitle"),
        "year": item.get("ProductionYear"),
        "premiere_date": _parse_date(item.get("PremiereDate")),
        "overview": item.get("Overview"),
        "tagline": (item.get("Taglines") or [None])[0],
        "genres": item.get("Genres") or [],
        "tags": item.get("Tags") or [],
        "studios": [s.get("Name") for s in item.get("Studios") or []],
        "people": _people(item.get("People") or []),
        "official_rating": item.get("OfficialRating"),
        "community_rating": item.get("CommunityRating"),
        "critic_rating": item.get("CriticRating"),
        "runtime_minutes": round(ticks / TICKS_PER_MINUTE) if ticks else None,
        "date_added": _parse_datetime(item.get("DateCreated")),
        "provider_ids": item.get("ProviderIds") or {},
        "trailer_urls": [t["Url"] for t in item.get("RemoteTrailers") or [] if t.get("Url")],
        "image_tags": image_tags,
        "played": bool(user_data.get("Played")),
        "favorite": bool(user_data.get("IsFavorite")),
        "play_count": user_data.get("PlayCount") or 0,
        "last_played_at": _parse_datetime(user_data.get("LastPlayedDate")),
        "unplayed_count": user_data.get("UnplayedItemCount") if is_series else None,
        "episode_count": item.get("RecursiveItemCount") if is_series else None,
        "synced_at": synced_at,
    }


@dataclass
class SyncResult:
    movies: int
    series: int
    removed: int


class LibrarySync:
    def __init__(self, client: JellyfinClient, session_factory: sessionmaker, user_name: str | None):
        self.client = client
        self.session_factory = session_factory
        self.user_name = user_name
        self.user_id: str | None = None
        self.last_sync_at: datetime | None = None
        self.last_result: SyncResult | None = None
        self.last_error: str | None = None
        self._lock = asyncio.Lock()

    @property
    def running(self) -> bool:
        return self._lock.locked()

    async def resolve_user(self) -> str:
        if self.user_id is None:
            if not self.user_name:
                raise JellyfinError("TARANTINO_JELLYFIN_USER is not set")
            self.user_id = (await self.client.find_user(self.user_name))["Id"]
        return self.user_id

    async def run(self) -> SyncResult | None:
        """Sync once; errors are recorded on the instance instead of raised."""
        if self.running:
            return None
        async with self._lock:
            try:
                result = await self._sync()
            except JellyfinError as exc:
                self.last_error = str(exc)
                log.warning("Library sync failed: %s", exc)
                return None
            self.last_error = None
            self.last_result = result
            self.last_sync_at = datetime.now(UTC)
            log.info("Library sync: %d movies, %d series, %d removed", result.movies, result.series, result.removed)
            return result

    async def _sync(self) -> SyncResult:
        user_id = await self.resolve_user()
        synced_at = datetime.now(UTC).replace(tzinfo=None)
        rows = [
            item_to_row(item, synced_at)
            async for item in self.client.iter_items(user_id, list(ITEM_TYPES), FIELDS)
        ]
        if not rows:
            # Never wipe the cache because of a misconfigured library or user.
            raise JellyfinError("Jellyfin returned no movies or series for this user")
        removed = await asyncio.to_thread(self._store, rows, synced_at)
        return SyncResult(
            movies=sum(r["type"] == "movie" for r in rows),
            series=sum(r["type"] == "series" for r in rows),
            removed=removed,
        )

    def _store(self, rows: list[dict], synced_at: datetime) -> int:
        with self.session_factory.begin() as session:
            stmt = insert(LibraryItem)
            update_cols = {c.name: stmt.excluded[c.name] for c in LibraryItem.__table__.columns if c.name != "id"}
            upsert = stmt.on_conflict_do_update(index_elements=["id"], set_=update_cols)
            for start in range(0, len(rows), 500):
                session.execute(upsert, rows[start : start + 500])
            result = session.execute(delete(LibraryItem).where(LibraryItem.synced_at < synced_at))
            return result.rowcount

    def counts(self) -> dict[str, int]:
        with self.session_factory() as session:
            rows = session.execute(select(LibraryItem.type, func.count()).group_by(LibraryItem.type)).all()
        return {item_type: count for item_type, count in rows}
