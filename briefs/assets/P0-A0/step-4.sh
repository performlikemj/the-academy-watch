#!/bin/bash
# P0-A0 — shipped step 4 (run from the worktree root: bash briefs/assets/P0-A0/step-4.sh)
D=$(grep -n '@scout_bp.route("/scout/players", methods=\["GET"\])' academy-watch-backend/src/routes/scout.py | cut -d: -f1); echo "D=$D"; sed -i '' "$((D-1))r briefs/assets/P0-A0/attach_contactable.py" academy-watch-backend/src/routes/scout.py && echo HELPER-INSERTED
