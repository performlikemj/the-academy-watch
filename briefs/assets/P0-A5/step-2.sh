#!/bin/bash
# P0-A5 — shipped step 2 (run from the worktree root: bash briefs/assets/P0-A5/step-2.sh)
R=$(grep -n '<Route path="/scout/lists" element={<ListsPage />} />' academy-watch-frontend/src/App.jsx | cut -d: -f1); echo "route anchor R=$R"; sed -i '' "${R}r briefs/assets/P0-A5/route-line.jsx" academy-watch-frontend/src/App.jsx && echo ROUTE-INSERTED
