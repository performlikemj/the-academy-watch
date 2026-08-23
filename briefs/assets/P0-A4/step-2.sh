#!/bin/bash
# P0-A4 — shipped step 2 (run from the worktree root: bash briefs/assets/P0-A4/step-2.sh)
O=$(grep -n "^  const { openLoginModal } = useAuthUI()" academy-watch-frontend/src/pages/ScoutPage.jsx | cut -d: -f1); echo "O=$O"; sed -i '' "${O}r briefs/assets/P0-A4/state-line.jsx" academy-watch-frontend/src/pages/ScoutPage.jsx && echo STATE-INSERTED
