#!/bin/bash
# P0-A4 — shipped step 1 (run from the worktree root: bash briefs/assets/P0-A4/step-1.sh)
N=$(grep -n "^import { SeasonSelect } from '@/components/ui/SeasonSelect'" academy-watch-frontend/src/pages/ScoutPage.jsx | cut -d: -f1); echo "N=$N"; sed -i '' "${N}r briefs/assets/P0-A4/import-line.jsx" academy-watch-frontend/src/pages/ScoutPage.jsx && echo IMPORT-INSERTED
