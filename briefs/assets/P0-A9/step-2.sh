#!/bin/bash
# P0-A9 — shipped step 2 (run from the worktree root: bash briefs/assets/P0-A9/step-2.sh)
LC=$(grep -n "^} from 'lucide-react'" academy-watch-frontend/src/App.jsx | cut -d: -f1); sed -i '' "$((LC-1))d" academy-watch-frontend/src/App.jsx && sed -i '' "$((LC-2))r briefs/assets/P0-A9/lucide-tail.jsx" academy-watch-frontend/src/App.jsx && echo ICON-ADDED
