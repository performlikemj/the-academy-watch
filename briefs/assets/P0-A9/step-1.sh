#!/bin/bash
# P0-A9 — shipped step 1 (run from the worktree root: bash briefs/assets/P0-A9/step-1.sh)
LC=$(grep -n "^} from 'lucide-react'" academy-watch-frontend/src/App.jsx | cut -d: -f1); echo "LC=$LC; line before: [$(sed -n "$((LC-1))p" academy-watch-frontend/src/App.jsx)]"
