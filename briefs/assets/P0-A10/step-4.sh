#!/bin/bash
# P0-A10 — shipped step 4: MyClubConsole.jsx — import + hook, gate the Introductions tab trigger and content. Run: bash briefs/assets/P0-A10/step-4.sh
F=academy-watch-frontend/src/pages/MyClubConsole.jsx
I=$(grep -n "^import { ClubIntroductionsPanel } from '@/components/contact/ClubIntroductionsPanel'$" "$F" | cut -d: -f1); echo "I=$I"
[ -n "$I" ] || { echo "STEP4-BLOCKED (import anchor not found)"; exit 1; }
sed -i '' "${I}r briefs/assets/P0-A10/import-hook.jsx" "$F" && echo CONSOLE-IMPORT-INSERTED
P=$(grep -n '^  const program = programClaim.program$' "$F" | cut -d: -f1); echo "P=$P"
[ -n "$P" ] && [ "$(sed -n "$((P+1))p" "$F")" = '  const programId = program.id' ] || { echo "STEP4-BLOCKED (program anchor shape unexpected)"; exit 1; }
sed -i '' "$((P+1))r briefs/assets/P0-A10/hook-line.jsx" "$F" && echo CONSOLE-HOOK-INSERTED
sed -i '' 's#^            <TabsTrigger value="introductions" className="py-2"><Send className="h-4 w-4" /> Introductions</TabsTrigger>$#            {contactRail === true ? <TabsTrigger value="introductions" className="py-2"><Send className="h-4 w-4" /> Introductions</TabsTrigger> : null}#' "$F"
sed -i '' 's#^          <TabsContent value="introductions"><ClubIntroductionsPanel programId={programId} onAccessDenied={onAccessDenied} /></TabsContent>$#          {contactRail === true ? <TabsContent value="introductions"><ClubIntroductionsPanel programId={programId} onAccessDenied={onAccessDenied} /></TabsContent> : null}#' "$F"
grep -c '{contactRail === true ? <TabsTrigger value="introductions"' "$F" | sed 's/^/trigger gated (expect 1): /'; grep -c '{contactRail === true ? <TabsContent value="introductions">' "$F" | sed 's/^/content gated (expect 1): /'
