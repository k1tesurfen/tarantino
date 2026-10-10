"""Admin settings: one typed schema, stored as key/value rows.

Every user-configurable setting must be a field on AppSettings, so the config
export (M4) covers everything by construction. Secrets never belong here.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from tarantino.models import Setting


class AppSettings(BaseModel):
    projector_address: str | None = Field(
        None, description="Projector host or IP (Cast, Android TV remote, ADB fallback)."
    )
    projector_device_id: str | None = Field(
        None, description="Jellyfin DeviceId of the projector's Jellyfin app session."
    )

    rollover_hour: int = Field(5, ge=0, le=23, description="Hour at which the cinema day changes.")
    movie_cooldown_days: int = Field(30, ge=0, le=365, description="Days before a movie may be programmed again.")
    series_cooldown_days: int = Field(
        7, ge=0, le=365, description="Days before a non-sticky series may be offered again."
    )

    theme_modern_name: str = Field("apLex", min_length=1, max_length=40, description="Name of the modern cinema.")
    theme_retro_name: str = Field(
        "Red Apple Cinema", min_length=1, max_length=40, description="Name of the retro cinema."
    )
    default_theme: Literal["modern", "retro"] = Field("modern", description="Theme for first-time visitors.")

    ha_url: str | None = Field(None, description="Home Assistant base URL, e.g. http://homeassistant.local:8123.")
    media_paths: list[str] = Field(
        default_factory=list, description="Media mount points on the mini-PC to monitor (NFS)."
    )

    @field_validator("projector_address", "projector_device_id", "ha_url")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        value = (value or "").strip().rstrip("/")
        return value or None


class SettingsStore:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def get(self) -> AppSettings:
        with self.session_factory() as session:
            rows = session.scalars(select(Setting)).all()
        stored = {row.key: row.value for row in rows if row.key in AppSettings.model_fields}
        return AppSettings.model_validate(stored)

    def update(self, changes: dict) -> AppSettings:
        unknown = set(changes) - set(AppSettings.model_fields)
        if unknown:
            raise ValueError(f"Unknown settings: {', '.join(sorted(unknown))}")
        merged = AppSettings.model_validate(self.get().model_dump() | changes)
        with self.session_factory.begin() as session:
            for key in changes:
                session.merge(Setting(key=key, value=getattr(merged, key)))
        return merged
