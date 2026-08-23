#!/bin/bash
# P0-B2 Step 2e — replace the whole loadMatches function with the shipped snippet. Run: bash briefs/assets/P0-B2/step2e.sh
F=${1:-academy-watch-frontend/src/pages/MyClubConsole.jsx}
L=$(grep -n '^  const loadMatches = useCallback(async () => {' "$F" | cut -d: -f1)
Z=$(awk -v s="$L" 'NR>s && /^  }, \[onAccessDenied, programId\]\)$/ {print NR; exit}' "$F")
echo "L=$L Z=$Z"
[ -n "$L" ] && [ -n "$Z" ] || { echo "STEP2E-BLOCKED (start or end line not found)"; exit 1; }
sed -i '' "${L},${Z}d" "$F" && sed -i '' "$((L-1))r briefs/assets/P0-B2/load-matches.jsx" "$F" && echo LOADMATCHES-REPLACED
