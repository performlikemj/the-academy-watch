#!/bin/bash
# P0-A0 — shipped step 2 (run from the worktree root: bash briefs/assets/P0-A0/step-2.sh)
T=$(grep -n 'assert striker\["primary_team_name"\] == "Manchester United"' academy-watch-backend/tests/test_scout_blueprint.py | cut -d: -f1); echo "T=$T"; sed -i '' "${T}r briefs/assets/P0-A0/test_method.py" academy-watch-backend/tests/test_scout_blueprint.py && echo TEST-METHOD-INSERTED
