#!/bin/bash
# P0-A9 — shipped step 4 (run from the worktree root: bash briefs/assets/P0-A9/step-4.sh)
LL=$(grep -n '^                Lists$' academy-watch-frontend/src/pages/ScoutPage.jsx | cut -d: -f1); echo "LL=$LL; line LL+2 is: [$(sed -n "$((LL+2))p" academy-watch-frontend/src/pages/ScoutPage.jsx)]"; sed -i '' "$((LL+2))r briefs/assets/P0-A9/header-buttons.jsx" academy-watch-frontend/src/pages/ScoutPage.jsx && echo HEADER-INSERTED
