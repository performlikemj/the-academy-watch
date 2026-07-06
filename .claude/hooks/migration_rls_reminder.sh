#!/bin/bash
# PostToolUse(Edit|Write) — remind about the code↔deploy coupling on Alembic migrations:
# the Deploy workflow's security-checks job FAILS the deploy if any new public table lacks
# Row Level Security, and prod schema has drifted out-of-band so all DDL must be guarded.
# Fires only when a migration version file is touched. See docs/agents/invariants.md §2, §8.

FILE=$(jq -r '.tool_input.file_path // .tool_input.filePath // empty' 2>/dev/null)
case "$FILE" in
  *academy-watch-backend/migrations/versions/*.py)
    cat <<'EOF'
{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"REMINDER (hook): you edited an Alembic migration. (1) If it CREATE TABLEs in the public schema, add `ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;` in the SAME migration — the Deploy security-checks job fails the deploy otherwise (invariants.md §2). (2) Guard every DDL with migrations/_migration_helpers.py (column_exists/table_exists) — prod schema drifted out-of-band, unguarded DDL crashes `flask db upgrade` on deploy (invariants.md §8). (3) Branch from the real tip: check `alembic heads` first."}}
EOF
    ;;
esac
exit 0
