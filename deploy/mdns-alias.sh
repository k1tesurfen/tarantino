#!/usr/bin/env bash
# Publish an extra mDNS name (default tarantino.local) for this host's LAN IPv4
# address, without changing the host's own name. The address is detected at
# runtime from the default route, so nothing machine-specific is stored.
set -euo pipefail

NAME="${1:-tarantino.local}"

ip_addr=""
for _ in $(seq 1 30); do
    ip_addr="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}')"
    [[ -n "$ip_addr" ]] && break
    sleep 2
done
if [[ -z "$ip_addr" ]]; then
    echo "No IPv4 default route found" >&2
    exit 1
fi

echo "Publishing $NAME -> $ip_addr"
exec avahi-publish --address --no-reverse "$NAME" "$ip_addr"
