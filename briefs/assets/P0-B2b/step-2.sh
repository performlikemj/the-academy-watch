#!/bin/bash
# P0-B2b — shipped step 2: replace the MatchDetail render line with the hydration guard. Run: bash briefs/assets/P0-B2b/step-2.sh
F=academy-watch-frontend/src/pages/MyClubConsole.jsx
G=$(grep -n '^          {selectedMatch ? ($' "$F" | cut -d: -f1)
echo "G=$G"
[ -n "$G" ] || { echo "STEP2-BLOCKED (render line not found)"; exit 1; }
sed -i '' "${G}d" "$F" && sed -i '' "$((G-1))r briefs/assets/P0-B2b/render-guard.jsx" "$F" && echo GUARD-REPLACED
