#!/bin/bash
# P0-A0 — shipped step 3 (run from the worktree root: bash briefs/assets/P0-A0/step-3.sh)
I=$(grep -n "^from src.models.showcase import without_minor_local_bridge" academy-watch-backend/src/routes/scout.py | cut -d: -f1); echo "I=$I"; sed -i '' "${I}d" academy-watch-backend/src/routes/scout.py && sed -i '' "$((I-1))r briefs/assets/P0-A0/import_line.py" academy-watch-backend/src/routes/scout.py && echo IMPORT-REPLACED
