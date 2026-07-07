#!/bin/bash
# PostToolUse(Edit|Write): auto-fix lint + format at edit time, mirroring the CI
# gates exactly (ci.yml: `ruff check` + `ruff format --check` on
# academy-watch-backend; `pnpm lint` (eslint) on academy-watch-frontend).
# Always exits 0 — a formatter must never block an edit.

FILE=$(jq -r '.tool_input.file_path // .tool_input.filePath // empty' 2>/dev/null)
[ -n "$FILE" ] && [ -f "$FILE" ] || exit 0

case "$FILE" in
  */node_modules/*|*/dist/*) exit 0 ;;
esac

case "$FILE" in
  "$CLAUDE_PROJECT_DIR"/academy-watch-backend/*.py)
    command -v ruff >/dev/null 2>&1 || exit 0
    cd "$CLAUDE_PROJECT_DIR/academy-watch-backend" || exit 0
    ruff check --fix --quiet "$FILE" 2>/dev/null
    ruff format --quiet "$FILE" 2>/dev/null
    ;;

  "$CLAUDE_PROJECT_DIR"/academy-watch-frontend/*.js | \
  "$CLAUDE_PROJECT_DIR"/academy-watch-frontend/*.jsx | \
  "$CLAUDE_PROJECT_DIR"/academy-watch-frontend/*.mjs)
    cd "$CLAUDE_PROJECT_DIR/academy-watch-frontend" || exit 0
    npx --no-install eslint --fix --quiet "$FILE" >/dev/null 2>&1
    ;;
esac
exit 0
