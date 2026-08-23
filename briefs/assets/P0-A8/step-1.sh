#!/bin/bash
# P0-A8 — shipped step 1 (run from the worktree root: bash briefs/assets/P0-A8/step-1.sh)
S1=$(grep -n '^  Search,$' academy-watch-frontend/src/pages/MyClubConsole.jsx | cut -d: -f1); echo "S1=$S1"; sed -i '' "${S1}r briefs/assets/P0-A8/send-icon-line.jsx" academy-watch-frontend/src/pages/MyClubConsole.jsx && echo ICON-INSERTED
