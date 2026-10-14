#!/usr/bin/env bash
# One-time installation of tarantino on the mini-PC (Debian).
#
#   sudo git clone <repo-url> /opt/tarantino
#   sudo chown -R "$USER": /opt/tarantino
#   sudo /opt/tarantino/deploy/install.sh
#
# The user who runs this via sudo becomes the deploy user: it owns the checkout,
# runs deploy/update.sh and may restart the tarantino services without a password.
# Safe to re-run.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER=tarantino
DATA_DIR=/var/lib/tarantino
ETC_DIR=/etc/tarantino
ENV_FILE="$ETC_DIR/tarantino.env"

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo." >&2
    exit 1
fi
DEPLOY_USER="${SUDO_USER:-}"
if [[ -z "$DEPLOY_USER" || "$DEPLOY_USER" == root ]]; then
    echo "Run via sudo from your normal user account (that user becomes the deploy user)." >&2
    exit 1
fi
if [[ "$(stat -c %U "$APP_DIR")" != "$DEPLOY_USER" ]]; then
    echo "$APP_DIR must be owned by $DEPLOY_USER (sudo chown -R $DEPLOY_USER: $APP_DIR)." >&2
    exit 1
fi

echo "==> packages"
# Output goes to /dev/null, so nothing may ask questions (needrestart restarts daemons itself).
export DEBIAN_FRONTEND=noninteractive NEEDRESTART_MODE=a
apt-get update -qq
apt-get install -y -qq python3 python3-venv nodejs npm adb avahi-daemon avahi-utils bluez iproute2 curl git >/dev/null

echo "==> service user and directories"
if ! id "$SERVICE_USER" &>/dev/null; then
    useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$SERVICE_USER"
fi
install -d -o "$SERVICE_USER" -g "$SERVICE_USER" -m 0750 "$DATA_DIR"
# The deploy user may read backups and the signing key (CLI, pre-update backups).
usermod -aG "$SERVICE_USER" "$DEPLOY_USER"
install -d -o root -g "$SERVICE_USER" -m 0750 "$ETC_DIR"
if [[ ! -f "$ENV_FILE" ]]; then
    install -o root -g "$SERVICE_USER" -m 0640 "$APP_DIR/deploy/env.example" "$ENV_FILE"
    echo "    created $ENV_FILE — fill in the secrets there."
fi
if ! sudo -u "$SERVICE_USER" test -r "$APP_DIR/backend/pyproject.toml"; then
    echo "The service user cannot read $APP_DIR. Install under /opt (not a home directory)." >&2
    exit 1
fi

echo "==> build (as $DEPLOY_USER)"
sudo -u "$DEPLOY_USER" -H "$APP_DIR/deploy/build.sh"

echo "==> systemd units"
for unit in tarantino.service tarantino-mdns.service tarantino-btremote.service; do
    sed "s|@APP_DIR@|$APP_DIR|g" "$APP_DIR/deploy/$unit" >"/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable --now avahi-daemon.service
systemctl enable --now bluetooth.service
systemctl enable tarantino.service tarantino-mdns.service tarantino-btremote.service
systemctl restart tarantino.service tarantino-mdns.service tarantino-btremote.service

echo "==> sudo rule for $DEPLOY_USER (restart/status of tarantino only)"
SUDOERS=/etc/sudoers.d/tarantino
cat >"$SUDOERS.tmp" <<EOF
$DEPLOY_USER ALL=(root) NOPASSWD: /usr/bin/systemctl restart tarantino.service, /usr/bin/systemctl restart tarantino-mdns.service, /usr/bin/systemctl restart tarantino-btremote.service, /usr/bin/systemctl status tarantino.service, /usr/bin/systemctl status tarantino-mdns.service, /usr/bin/systemctl status tarantino-btremote.service, /usr/bin/journalctl -u tarantino.service *, /usr/bin/journalctl -u tarantino-mdns.service *, /usr/bin/journalctl -u tarantino-btremote.service *
EOF
visudo -cf "$SUDOERS.tmp" >/dev/null
install -m 0440 "$SUDOERS.tmp" "$SUDOERS"
rm -f "$SUDOERS.tmp"

echo "==> health check"
for _ in $(seq 1 20); do
    if curl -fsS http://localhost/api/health 2>/dev/null; then
        echo
        echo "tarantino is running: http://tarantino.local"
        exit 0
    fi
    sleep 1
done
echo "tarantino did not become healthy; see: journalctl -u tarantino.service" >&2
exit 1
