#!/usr/bin/env bash
# commit-msg guard: no AI attribution and no private words in commit messages.
set -euo pipefail

msg_file="$1"
ROOT="$(git rev-parse --show-toplevel)"
DENYLIST="$ROOT/.private-words"
body="$(grep -v '^#' "$msg_file" || true)"

if printf '%s\n' "$body" | grep -iqE 'co-authored-by:.*(claude|anthropic)|generated with .*claude|noreply@anthropic\.com'; then
    echo "check-commit-msg: commit message contains AI attribution; remove it." >&2
    exit 1
fi

if [[ -f "$DENYLIST" ]]; then
    patterns="$(grep -vE '^[[:space:]]*(#|$)' "$DENYLIST" || true)"
    if [[ -n "$patterns" ]] && printf '%s\n' "$body" | grep -iqF -f <(printf '%s\n' "$patterns"); then
        echo "check-commit-msg: commit message contains a word from .private-words." >&2
        exit 1
    fi
fi
