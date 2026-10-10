#!/usr/bin/env bash
# Update a running installation: pull, rebuild, restart, health check.
# Run as the deploy user (no sudo needed after install.sh).
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "==> git pull"
git pull --ff-only

"$APP_DIR/deploy/build.sh"

echo "==> restart"
sudo /usr/bin/systemctl restart tarantino.service

for _ in $(seq 1 20); do
    if curl -fsS http://localhost/api/health; then
        echo
        exit 0
    fi
    sleep 1
done
echo "tarantino did not become healthy; see: sudo journalctl -u tarantino.service -n 100" >&2
exit 1
