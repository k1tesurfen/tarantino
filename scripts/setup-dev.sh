#!/usr/bin/env bash
# Enable the repository's git hooks (public-repo guards) for this checkout.
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"
git config core.hooksPath .githooks
[[ -f .private-words ]] || printf '# Real hostnames, usernames, IP prefixes, brands — one per line. Never committed.\n' >.private-words
echo "Hooks enabled. Add private words to .private-words."
