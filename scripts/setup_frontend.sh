#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/academy-watch-frontend"
LOCKFILE="$FRONTEND_DIR/pnpm-lock.yaml"
INSTALLED_LOCKFILE="$FRONTEND_DIR/node_modules/.pnpm/lock.yaml"

"$ROOT_DIR/scripts/security/check_frontend_dependencies.sh"

if [[ -f "$INSTALLED_LOCKFILE" ]] && cmp -s "$LOCKFILE" "$INSTALLED_LOCKFILE"; then
  echo "Frontend dependencies already match the frozen lockfile; skipping install."
  exit 0
fi

if ! command -v pnpm >/dev/null 2>&1; then
  echo "pnpm is required to restore frontend dependencies." >&2
  exit 127
fi

echo "Frontend dependencies are missing or stale; restoring the frozen lockfile."
cd "$FRONTEND_DIR"
exec pnpm install --frozen-lockfile
