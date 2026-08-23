#!/bin/bash
# P0-A10 — shipped step 3: ScoutPage.jsx — import + hook, gate the Introductions header button and the Introduce cell. Run: bash briefs/assets/P0-A10/step-3.sh
F=academy-watch-frontend/src/pages/ScoutPage.jsx
I=$(grep -n "^import { IntroduceDialog } from '@/components/contact/IntroduceDialog'$" "$F" | cut -d: -f1); echo "I=$I"
[ -n "$I" ] || { echo "STEP3-BLOCKED (import anchor not found)"; exit 1; }
sed -i '' "${I}r briefs/assets/P0-A10/import-hook.jsx" "$F" && echo SCOUT-IMPORT-INSERTED
U=$(grep -n '^  const auth = useAuth()$' "$F" | cut -d: -f1); echo "U=$U"
[ -n "$U" ] || { echo "STEP3-BLOCKED (useAuth anchor not found)"; exit 1; }
sed -i '' "${U}r briefs/assets/P0-A10/hook-line.jsx" "$F" && echo SCOUT-HOOK-INSERTED
LI=$(grep -n '^              <Link to="/introductions" className="no-underline hover:no-underline">$' "$F" | cut -d: -f1); echo "LI=$LI"
[ -n "$LI" ] || { echo "STEP3-BLOCKED (Introductions link not found)"; exit 1; }
A=$(sed -n "$((LI-1))p" "$F"); B=$(sed -n "$((LI+4))p" "$F")
[ "$A" = '            <Button variant="outline" size="sm" asChild>' ] && [ "$B" = '            </Button>' ] || { echo "STEP3-BLOCKED (header button shape unexpected: [$A] [$B])"; exit 1; }
sed -i '' "$((LI-1)),$((LI+4))d" "$F" && sed -i '' "$((LI-2))r briefs/assets/P0-A10/header-gated.jsx" "$F" && echo HEADER-GATED
sed -i '' 's#{player.contactable ? (#{contactRail === true \&\& player.contactable ? (#' "$F"
grep -c '{contactRail === true && player.contactable ? (' "$F" | sed 's/^/introduce cell gated (expect 1): /'
