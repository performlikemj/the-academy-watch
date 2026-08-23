#!/bin/bash
# P0-A0 — shipped step 5 (run from the worktree root: bash briefs/assets/P0-A0/step-5.sh)
C=$(grep -n "^        players = \[_row_to_dict(row) for row in rows\]" academy-watch-backend/src/routes/scout.py | cut -d: -f1); echo "C=$C"; sed -i '' "${C}r briefs/assets/P0-A0/call_line.py" academy-watch-backend/src/routes/scout.py && echo CALL-INSERTED
