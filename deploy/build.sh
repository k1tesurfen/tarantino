#!/usr/bin/env bash
# Build tarantino in place: Python venv (backend) and static frontend.
# Run as the deploy user (the owner of the repository checkout).
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "==> backend"
if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -e backend

echo "==> frontend"
cd frontend
npm ci --no-fund --no-audit --loglevel=error
npm run build --silent
