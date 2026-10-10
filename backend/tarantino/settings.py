"""Admin settings: one typed schema, stored as key/value rows.

Every user-configurable setting must be a field on AppSettings, so the config
export (M4) covers everything by construction. Secrets never belong here.
"""

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from tarantino.models import Setting


class AppSettings(BaseModel):
    projector_address: str | None = Field(
        None, description="Projector host or IP for network ADB, optionally with :port (default 5555)."
    )
    projector_device_id: str | None = Field(
        None, description="Jellyfin DeviceId of the projector's Jellyfin app session."
    )

    @field_validator("projector_address", "projector_device_id")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        value = (value or "").strip()
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
