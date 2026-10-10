"""Process-level settings from the environment.

Only secrets and deployment paths live here. Everything a user configures
(rooms, cassettes, device addresses, theme names, ...) lives in the database
and is covered by the config export.
"""

import secrets
from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TARANTINO_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    data_dir: Path = REPO_ROOT / "data"
    frontend_dir: Path = REPO_ROOT / "frontend" / "build"

    jellyfin_url: str = "http://localhost:8096"
    jellyfin_api_key: SecretStr | None = None
    jellyfin_user: str | None = None

    admin_password: SecretStr | None = None
    ha_token: SecretStr | None = None


def load_secret(data_dir: Path) -> bytes:
    """Per-installation signing key, created on first start."""
    path = data_dir / "secret.key"
    if not path.exists():
        data_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(secrets.token_hex(32))
        path.chmod(0o600)
    return bytes.fromhex(path.read_text().strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
