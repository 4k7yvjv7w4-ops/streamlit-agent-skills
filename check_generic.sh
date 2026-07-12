#!/usr/bin/env bash
# Pre-publish guardrail: fail if any identifier from the private source project
# leaks into this public repo.
#
# The identifier list is intentionally NOT stored in this repo — it lives in a
# local, gitignored file so the terms themselves never ship:
#
#   .check_generic.local   one extended-regex term per line; blank lines and
#                          lines starting with '#' are ignored.
#
# A fresh clone without that file simply skips the check (exit 0).
#
# Run before committing/pushing; the .githooks/pre-commit hook runs it too.
set -u

TERMS_FILE="$(dirname "$0")/.check_generic.local"
if [ ! -f "$TERMS_FILE" ]; then
  echo "ℹ️  no local blocklist (.check_generic.local); skipping guardrail."
  exit 0
fi

PATTERN=$(grep -vE '^[[:space:]]*(#|$)' "$TERMS_FILE" | paste -sd'|' -)
if [ -z "$PATTERN" ]; then
  echo "ℹ️  local blocklist is empty; nothing to check."
  exit 0
fi

hits=$(grep -rInE "$PATTERN" --include='*.md' --include='*.py' . \
        --exclude-dir=.git --exclude=check_generic.sh 2>/dev/null)
if [ -n "$hits" ]; then
  echo "❌ private identifiers found — must not ship in the public repo:"
  echo "$hits"
  exit 1
fi
echo "✅ clean: no private identifiers in public repo."
