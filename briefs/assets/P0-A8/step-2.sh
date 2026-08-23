#!/bin/bash
# P0-A8 — shipped step 2 (run from the worktree root: bash briefs/assets/P0-A8/step-2.sh)
A1=$(grep -n "^import { APIService } from '@/lib/api'" academy-watch-frontend/src/pages/MyClubConsole.jsx | cut -d: -f1); echo "A1=$A1"; sed -i '' "${A1}r briefs/assets/P0-A8/import-line.jsx" academy-watch-frontend/src/pages/MyClubConsole.jsx && echo IMPORT-INSERTED
