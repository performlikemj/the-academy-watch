#!/bin/bash
# P0-C2 — shipped step 1 (run from the worktree root: bash briefs/assets/P0-C2/step-1.sh)
C1=$(grep -n '^    # No standalone indexes: the composite unique below leads on$' academy-watch-backend/src/models/scout_watchlist.py | cut -d: -f1); echo "C1=$C1"; sed -i '' "${C1},$((C1+1))d" academy-watch-backend/src/models/scout_watchlist.py && sed -i '' "$((C1-1))r briefs/assets/P0-C2/model_comment.py" academy-watch-backend/src/models/scout_watchlist.py && echo COMMENT-REPLACED
