#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LOCKFILE="$ROOT_DIR/academy-watch-frontend/pnpm-lock.yaml"

if ! command -v osv-scanner >/dev/null 2>&1; then
  echo "OSV-Scanner is required before restoring frontend dependencies." >&2
  echo "Install it from https://google.github.io/osv-scanner/installation/ and rerun this check." >&2
  exit 127
fi

if [[ ! -f "$LOCKFILE" ]]; then
  echo "Frontend lockfile not found: $LOCKFILE" >&2
  exit 2
fi

echo "Checking academy-watch-frontend/pnpm-lock.yaml with OSV-Scanner..."
exec osv-scanner scan source --lockfile="$LOCKFILE"
