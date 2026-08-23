#!/bin/bash
# P0-A8 — shipped step 4 (run from the worktree root: bash briefs/assets/P0-A8/step-4.sh)
PT=$(grep -n '<TabsTrigger value="profile" className="py-2">' academy-watch-frontend/src/pages/MyClubConsole.jsx | cut -d: -f1); echo "PT=$PT"; sed -i '' "${PT}r briefs/assets/P0-A8/trigger-line.jsx" academy-watch-frontend/src/pages/MyClubConsole.jsx && echo TRIGGER-INSERTED
