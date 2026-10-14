#!/usr/bin/env bash
# Update a running installation: pull, rebuild, restart, health check.
# Run as the deploy user (no sudo needed after install.sh).
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo "==> config backup"
# Needs read access to the signing key (deploy user in the tarantino group, see install.sh).
if ! "$APP_DIR/.venv/bin/tarantino" backup --reason pre-update; then
    echo "WARNING: pre-update backup failed (is tarantino running? is $(id -un) in the tarantino group?)" >&2
fi

echo "==> git pull"
before="$(git rev-parse HEAD)"
git pull --ff-only

"$APP_DIR/deploy/build.sh"

for unit in tarantino.service tarantino-mdns.service tarantino-btremote.service; do
    if ! sed "s|@APP_DIR@|$APP_DIR|g" "deploy/$unit" | cmp -s - "/etc/systemd/system/$unit"; then
        echo "WARNING: $unit changed. Re-run: sudo $APP_DIR/deploy/install.sh" >&2
    fi
done

echo "==> restart"
sudo /usr/bin/systemctl restart tarantino.service
# Restarting the Bluetooth remote drops the projector's connection to it until the
# projector's next standby, so only when its code changed.
if ! git diff --quiet "$before" HEAD -- backend/tarantino/btremote; then
    echo "    Bluetooth remote changed; restarting it"
    sudo -n /usr/bin/systemctl restart tarantino-btremote.service ||
        echo "WARNING: could not restart tarantino-btremote.service (re-run: sudo $APP_DIR/deploy/install.sh)" >&2
fi

for _ in $(seq 1 20); do
    if curl -fsS http://localhost/api/health 2>/dev/null; then
        echo
        exit 0
    fi
    sleep 1
done
echo "tarantino did not become healthy; see: sudo journalctl -u tarantino.service -n 100" >&2
exit 1
