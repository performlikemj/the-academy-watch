#!/bin/bash
# P0-A10 — shipped step 2: App.jsx — import the hook, call it in Navigation, gate the nav item, extend the memo deps. Run: bash briefs/assets/P0-A10/step-2.sh
F=academy-watch-frontend/src/App.jsx
I=$(grep -n "^import { ScoutVerificationPage } from '@/pages/ScoutVerificationPage'$" "$F" | cut -d: -f1); echo "I=$I"
[ -n "$I" ] || { echo "STEP2-BLOCKED (import anchor not found)"; exit 1; }
sed -i '' "${I}r briefs/assets/P0-A10/import-hook.jsx" "$F" && echo APP-IMPORT-INSERTED
U=$(grep -n '^  const { token, isAdmin, hasApiKey, isJournalist, isCurator } = useAuth()$' "$F" | cut -d: -f1); echo "U=$U"
[ -n "$U" ] || { echo "STEP2-BLOCKED (useAuth anchor not found)"; exit 1; }
sed -i '' "${U}r briefs/assets/P0-A10/hook-line.jsx" "$F" && echo APP-HOOK-INSERTED
sed -i '' "s#^      items.push({ path: '/introductions', label: 'Introductions', icon: Send })\$#      if (contactRail === true) items.push({ path: '/introductions', label: 'Introductions', icon: Send })#" "$F"
sed -i '' 's#^  }, \[adminUnlocked, isJournalist, isCurator, token\])$#  }, [adminUnlocked, contactRail, isJournalist, isCurator, token])#' "$F"
grep -c "if (contactRail === true) items.push({ path: '/introductions'" "$F" | sed 's/^/nav gated lines (expect 1): /'; grep -c '}, \[adminUnlocked, contactRail, isJournalist, isCurator, token\])' "$F" | sed 's/^/deps lines (expect 1): /'
