#!/bin/bash
# P0-A5 — shipped step 1 (run from the worktree root: bash briefs/assets/P0-A5/step-1.sh)
N=$(grep -n "^import { ClaimAccount } from '@/pages/ClaimAccount'" academy-watch-frontend/src/App.jsx | cut -d: -f1); echo "import anchor N=$N"; sed -i '' "${N}r briefs/assets/P0-A5/import-line.jsx" academy-watch-frontend/src/App.jsx && echo IMPORT-INSERTED
