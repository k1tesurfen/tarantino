from datetime import date, datetime

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
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


class Setting(Base):
    """One admin setting (see tarantino.settings.AppSettings); part of the config export."""

    __tablename__ = "setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[object] = mapped_column(JSON)


class Show(Base):
    """One attempt to start something on the projector, with its step log."""

    __tablename__ = "show"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    trigger: Mapped[str] = mapped_column(String(16))  # "admin" | "cinema" | "vhs"
    room_id: Mapped[int | None] = mapped_column(ForeignKey("room.id", ondelete="SET NULL"))
    item_id: Mapped[str] = mapped_column(String(32))
    item_name: Mapped[str] = mapped_column(String)
    state: Mapped[str] = mapped_column(String(16), index=True)  # running | playing | failed | cancelled
    steps: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class Room(Base):
    """An auditorium (movies) or lounge (series); `number` is also the cassette number."""

    __tablename__ = "room"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    number: Mapped[int] = mapped_column(Integer, unique=True)
    name: Mapped[str] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String(16))  # "movie" | "series"
    filters: Mapped[dict] = mapped_column(JSON, default=dict)
    weights: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class ProgrammeEntry(Base):
    """What a room shows on one cinema day."""

    __tablename__ = "programme_entry"
    __table_args__ = (UniqueConstraint("cinema_date", "room_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cinema_date: Mapped[date] = mapped_column(Date, index=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id", ondelete="CASCADE"))
    item_id: Mapped[str | None] = mapped_column(String(32))  # None: room closed today
    showtimes: Mapped[list] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(16))  # "generated" | "override"
    first_started_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class SeriesAssignment(Base):
    """A series that sticks to a series room until it is finished or dropped."""

    __tablename__ = "series_assignment"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id", ondelete="CASCADE"), index=True)
    series_id: Mapped[str] = mapped_column(String(32))
    started_at: Mapped[datetime] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    dropped_at: Mapped[datetime | None] = mapped_column(DateTime)


class Cassette(Base):
    """An RFID-tagged VHS cassette, bound to a room by learn mode; part of the config export."""

    __tablename__ = "cassette"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uid: Mapped[str] = mapped_column(String(32), unique=True)  # normalised: uppercase, no separators
    room_id: Mapped[int] = mapped_column(ForeignKey("room.id", ondelete="CASCADE"), index=True)
    learned_at: Mapped[datetime] = mapped_column(DateTime)


class VhsEvent(Base):
    """Raw log of what the VHS recorder reported, including unknown cassettes."""

    __tablename__ = "vhs_event"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(16))  # "insert" | "eject"
    uid: Mapped[str | None] = mapped_column(String(32), index=True)
    room_number: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(String(16))  # played | learned | unknown | failed | ignored
    message: Mapped[str | None] = mapped_column(String)
    show_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, index=True)
