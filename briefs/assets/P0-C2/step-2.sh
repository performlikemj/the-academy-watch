#!/bin/bash
# P0-C2 — shipped step 2 (run from the worktree root: bash briefs/assets/P0-C2/step-2.sh)
TA=$(grep -n '^    __table_args__ = (db.UniqueConstraint("user_account_id", "player_api_id", name="uq_scout_watchlist_user_player"),)$' academy-watch-backend/src/models/scout_watchlist.py | cut -d: -f1); echo "TA=$TA"; sed -i '' "${TA}d" academy-watch-backend/src/models/scout_watchlist.py && sed -i '' "$((TA-1))r briefs/assets/P0-C2/model_table_args.py" academy-watch-backend/src/models/scout_watchlist.py && echo TABLE-ARGS-REPLACED
