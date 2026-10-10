from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from tarantino.db import Base


class LibraryItem(Base):
    """Cached Jellyfin movie or series, including the user's watch state.

    Rebuilt by the library sync; never part of the config export.
    """

    __tablename__ = "library_item"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    type: Mapped[str] = mapped_column(String(16), index=True)  # "movie" | "series"
    name: Mapped[str] = mapped_column(String)
    sort_name: Mapped[str | None] = mapped_column(String)
    original_title: Mapped[str | None] = mapped_column(String)
    year: Mapped[int | None] = mapped_column(Integer)
    premiere_date: Mapped[date | None] = mapped_column(Date)
    overview: Mapped[str | None] = mapped_column(Text)
    tagline: Mapped[str | None] = mapped_column(String)
    genres: Mapped[list] = mapped_column(JSON, default=list)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    studios: Mapped[list] = mapped_column(JSON, default=list)
    people: Mapped[list] = mapped_column(JSON, default=list)
    official_rating: Mapped[str | None] = mapped_column(String)
    community_rating: Mapped[float | None] = mapped_column(Float)
    critic_rating: Mapped[float | None] = mapped_column(Float)
    runtime_minutes: Mapped[int | None] = mapped_column(Integer)
    date_added: Mapped[datetime | None] = mapped_column(DateTime)
    provider_ids: Mapped[dict] = mapped_column(JSON, default=dict)
    trailer_urls: Mapped[list] = mapped_column(JSON, default=list)
    image_tags: Mapped[dict] = mapped_column(JSON, default=dict)

    played: Mapped[bool] = mapped_column(Boolean, default=False)
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    play_count: Mapped[int] = mapped_column(Integer, default=0)
    last_played_at: Mapped[datetime | None] = mapped_column(DateTime)
    unplayed_count: Mapped[int | None] = mapped_column(Integer)  # series only
    episode_count: Mapped[int | None] = mapped_column(Integer)  # series only

    synced_at: Mapped[datetime] = mapped_column(DateTime, index=True)
