#!/bin/bash
# P0-A9 — shipped step 3 (run from the worktree root: bash briefs/assets/P0-A9/step-3.sh)
LP=$(grep -n "items.push({ path: '/scout/lists', label: 'Lists', icon: ListChecks })" academy-watch-frontend/src/App.jsx | cut -d: -f1); echo "LP=$LP"; sed -i '' "${LP}r briefs/assets/P0-A9/nav-item-line.jsx" academy-watch-frontend/src/App.jsx && echo NAV-INSERTED
