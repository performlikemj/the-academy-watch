#!/bin/bash
# P0-A0 — shipped step 1 (run from the worktree root: bash briefs/assets/P0-A0/step-1.sh)
L=$(grep -n "^from src.models.league import League, PlayerStatsCache, Team, db" academy-watch-backend/tests/test_scout_blueprint.py | cut -d: -f1); echo "L=$L"; sed -i '' "${L}d" academy-watch-backend/tests/test_scout_blueprint.py && sed -i '' "$((L-1))r briefs/assets/P0-A0/test_imports.py" academy-watch-backend/tests/test_scout_blueprint.py && echo TEST-IMPORTS-REPLACED
