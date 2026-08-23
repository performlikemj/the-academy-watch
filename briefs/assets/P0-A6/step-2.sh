#!/bin/bash
# P0-A6 — shipped step 2 (run from the worktree root: bash briefs/assets/P0-A6/step-2.sh)
R=$(grep -n '<Route path="/scout/verification" element={<ScoutVerificationPage />} />' academy-watch-frontend/src/App.jsx | cut -d: -f1); echo "route anchor R=$R"; sed -i '' "${R}r briefs/assets/P0-A6/route-line.jsx" academy-watch-frontend/src/App.jsx && echo ROUTE-INSERTED
