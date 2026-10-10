#!/usr/bin/env bash
# Autogenerate an Alembic migration from the current models.
#   ./scripts/new-migration.sh "add room table"
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
.venv/bin/python - "$tmp" "$1" <<'EOF'
import sys
from alembic import command
from alembic.config import Config
from tarantino.db import MIGRATIONS_DIR

cfg = Config()
cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
cfg.set_main_option("sqlalchemy.url", f"sqlite:///{sys.argv[1]}/schema.db")
command.upgrade(cfg, "head")
command.revision(cfg, message=sys.argv[2], autogenerate=True)
EOF
