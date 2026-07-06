#!/bin/bash
# PostToolUse(Edit|Write) — auto-fix lint AND format at edit time so drift is fixed
# here, not at CI time. Mirrors both CI lint gates:
#   backend  — `ruff check academy-watch-backend` + `ruff format --check academy-watch-backend`
#   frontend — `pnpm lint` (eslint flat config) in academy-watch-frontend
# Ruff is not in the .loan venv, so it uses the system `ruff` (as CI does). Always exit 0.
# Sharp edge: `ruff check --fix` strips imports with no call site yet — add the import and
# its first usage in the SAME edit (docs/agents/backend.md).

FILE=$(jq -r '.tool_input.file_path // .tool_input.filePath // empty' 2>/dev/null)
[ -n "$FILE" ] && [ -f "$FILE" ] || exit 0

case "$FILE" in
  # --- Backend Python: mirror `ruff check` + `ruff format --check` ---
  *academy-watch-backend/*.py)
    RUFF="$CLAUDE_PROJECT_DIR/.loan/bin/ruff"
    [ -x "$RUFF" ] || RUFF=ruff
    cd "$CLAUDE_PROJECT_DIR" || exit 0
    "$RUFF" check --fix --quiet "$FILE" 2>/dev/null
    "$RUFF" format --quiet "$FILE" 2>/dev/null
    ;;

  # --- Frontend JS/JSX/TS/TSX: mirror `pnpm lint` (eslint flat config) ---
  *academy-watch-frontend/*.js|*academy-watch-frontend/*.jsx|*academy-watch-frontend/*.ts|*academy-watch-frontend/*.tsx)
    cd "$CLAUDE_PROJECT_DIR/academy-watch-frontend" || exit 0
    npx --no-install eslint --fix --quiet "$FILE" 2>/dev/null
    ;;
esac
exit 0
