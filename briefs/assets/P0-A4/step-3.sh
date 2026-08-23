#!/bin/bash
# P0-A4 — shipped step 3 (run from the worktree root: bash briefs/assets/P0-A4/step-3.sh)
T=$(grep -n '^                        <td className="px-2 py-2.5">$' academy-watch-frontend/src/pages/ScoutPage.jsx | cut -d: -f1); echo "T=$T; line T+9 is: [$(sed -n "$((T+9))p" academy-watch-frontend/src/pages/ScoutPage.jsx)]"
