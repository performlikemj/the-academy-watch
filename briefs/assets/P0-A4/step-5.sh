#!/bin/bash
# P0-A4 — shipped step 5 (run from the worktree root: bash briefs/assets/P0-A4/step-5.sh)
M=$(grep -n '^          seasonOverride={seasonOverride}$' academy-watch-frontend/src/pages/ScoutPage.jsx | cut -d: -f1); echo "M=$M; line M+1 is: [$(sed -n "$((M+1))p" academy-watch-frontend/src/pages/ScoutPage.jsx)]"; sed -i '' "$((M+1))r briefs/assets/P0-A4/dialog-mount.jsx" academy-watch-frontend/src/pages/ScoutPage.jsx && echo MOUNT-INSERTED
