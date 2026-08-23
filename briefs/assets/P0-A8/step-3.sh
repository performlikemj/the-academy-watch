#!/bin/bash
# P0-A8 — shipped step 3 (run from the worktree root: bash briefs/assets/P0-A8/step-3.sh)
TL=$(grep -n "sm:grid-cols-4 lg:min-w-\[44rem\]" academy-watch-frontend/src/pages/MyClubConsole.jsx | cut -d: -f1); echo "TL=$TL"; sed -i '' "${TL}d" academy-watch-frontend/src/pages/MyClubConsole.jsx && sed -i '' "$((TL-1))r briefs/assets/P0-A8/tabslist-line.jsx" academy-watch-frontend/src/pages/MyClubConsole.jsx && echo TABSLIST-REPLACED
