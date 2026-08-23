#!/bin/bash
# P0-A4 — shipped step 4 (run from the worktree root: bash briefs/assets/P0-A4/step-4.sh)
T=$(grep -n '^                        <td className="px-2 py-2.5">$' academy-watch-frontend/src/pages/ScoutPage.jsx | cut -d: -f1); sed -i '' "${T}d" academy-watch-frontend/src/pages/ScoutPage.jsx && sed -i '' "$((T-1))r briefs/assets/P0-A4/td-open.jsx" academy-watch-frontend/src/pages/ScoutPage.jsx && sed -i '' "$((T+9))r briefs/assets/P0-A4/introduce-button.jsx" academy-watch-frontend/src/pages/ScoutPage.jsx && echo CELL-DONE
