"""Config backups on the mini-PC: nightly, before updates and imports, and on demand."""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from tarantino.configio.transfer import export_config
from tarantino.settings import SettingsStore

SUFFIX = ".tarantino.json"
KEEP_PER_REASON = 14
REASONS = ("nightly", "pre-update", "pre-import", "manual")
NAME = re.compile(r"^tarantino-(\d{8}-\d{6})-([a-z-]+)\.tarantino\.json$")


@dataclass
class Backup:
    name: str
    reason: str
    created_at: datetime
    size: int


class BackupStore:
    def __init__(self, directory: Path, session_factory: sessionmaker, settings: SettingsStore):
        self.directory = directory
        self.session_factory = session_factory
        self.settings = settings

    def create(self, reason: str) -> Backup:
        if reason not in REASONS:
            raise ValueError(f"Unknown backup reason {reason!r}")
        self.directory.mkdir(parents=True, exist_ok=True)
        self.directory.chmod(0o750)  # readable by the deploy user via the service group
        export = export_config(self.session_factory, self.settings, include_state=True)
        name = f"tarantino-{datetime.now():%Y%m%d-%H%M%S}-{reason}{SUFFIX}"
        path = self.directory / name
        path.write_text(export.model_dump_json(indent=2))
        path.chmod(0o640)
        self._rotate(reason)
        return self._describe(path)

    def list(self) -> list[Backup]:
        if not self.directory.exists():
            return []
        backups = [self._describe(p) for p in self.directory.iterdir() if NAME.match(p.name)]
        return sorted(backups, key=lambda b: b.name, reverse=True)

    def read(self, name: str) -> dict:
        return json.loads(self.path(name).read_text())

    def path(self, name: str) -> Path:
        if not NAME.match(name):  # also rules out path traversal
            raise FileNotFoundError(name)
        path = self.directory / name
        if not path.is_file():
            raise FileNotFoundError(name)
        return path

    def _rotate(self, reason: str) -> None:
        for old in [b for b in self.list() if b.reason == reason][KEEP_PER_REASON:]:
            (self.directory / old.name).unlink(missing_ok=True)

    def _describe(self, path: Path) -> Backup:
        stamp, reason = NAME.match(path.name).groups()
        return Backup(path.name, reason, datetime.strptime(stamp, "%Y%m%d-%H%M%S"), path.stat().st_size)
