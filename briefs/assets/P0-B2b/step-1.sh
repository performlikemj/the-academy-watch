#!/bin/bash
# P0-B2b — shipped step 1: insert the hydrate block right after the refreshSelected function (its closing line). Run: bash briefs/assets/P0-B2b/step-1.sh
F=academy-watch-frontend/src/pages/MyClubConsole.jsx
R=$(grep -n '^  const refreshSelected = async () => {$' "$F" | cut -d: -f1)
C=$(awk -v s="$R" 'NR>s && /^  }$/ {print NR; exit}' "$F")
echo "R=$R C=$C"
[ -n "$R" ] && [ -n "$C" ] || { echo "STEP1-BLOCKED (refreshSelected not found)"; exit 1; }
sed -i '' "${C}r briefs/assets/P0-B2b/hydrate-block.jsx" "$F" && echo HYDRATE-INSERTED
