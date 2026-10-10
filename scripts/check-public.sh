#!/usr/bin/env bash
# Pre-commit guard for this public repository.
#
# Scans the lines added in the staged diff for
#   - private IPv4 addresses (10/8, 172.16/12, 192.168/16)
#   - assignments of secrets (key/token/password/secret = <value>)
#   - long hex strings that look like API keys
#   - any word listed in the local, gitignored `.private-words` file
#     (one entry per line, case-insensitive; '#' starts a comment)
#
# A line can be allowed explicitly by putting `public-ok` in it.
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
DENYLIST="$ROOT/.private-words"

# Lockfiles contain integrity hashes; they are generated, never hand-edited.
diff="$(git diff --cached --unified=0 --no-color --diff-filter=ACMR -- . \
    ':(exclude)frontend/package-lock.json' ':(exclude)*.lock')"

added="$(printf '%s\n' "$diff" | awk '
    /^\+\+\+ / { file = substr($0, 7); next }
    /^\+/ && !/public-ok/ { print file ": " substr($0, 2) }
')"

[[ -z "$added" ]] && exit 0

fail=0
report() {
    local title="$1" matches="$2"
    if [[ -n "$matches" ]]; then
        echo "check-public: $title" >&2
        printf '%s\n' "$matches" | sed 's/^/    /' >&2
        fail=1
    fi
}

report "private IP address" "$(printf '%s\n' "$added" | grep -E \
    '(^|[^0-9.])(10\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}|192\.168\.[0-9]{1,3}\.[0-9]{1,3}|172\.(1[6-9]|2[0-9]|3[01])\.[0-9]{1,3}\.[0-9]{1,3})([^0-9.]|$)' || true)"

report "possible secret assignment" "$(printf '%s\n' "$added" | grep -iE \
    '(api[_-]?key|token|passw(or)?d|secret)["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"']?[A-Za-z0-9_\-]{12,}' || true)"

report "long hex string (API key?)" "$(printf '%s\n' "$added" | grep -E '(^|[^A-Za-z0-9])[0-9a-fA-F]{32,}([^A-Za-z0-9]|$)' || true)"

if [[ -f "$DENYLIST" ]]; then
    patterns="$(grep -vE '^[[:space:]]*(#|$)' "$DENYLIST" || true)"
    if [[ -n "$patterns" ]]; then
        report "private word from .private-words" "$(printf '%s\n' "$added" | grep -iF -f <(printf '%s\n' "$patterns") || true)"
    fi
else
    echo "check-public: warning: no .private-words file — private names are not being checked" >&2
fi

if [[ $fail -ne 0 ]]; then
    echo "check-public: commit blocked. Remove the values above or mark a line with 'public-ok'." >&2
    exit 1
fi
