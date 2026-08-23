#!/bin/bash
# P0-A8 — shipped step 5 (run from the worktree root: bash briefs/assets/P0-A8/step-5.sh)
PC=$(grep -n '<TabsContent value="profile"><ClubProfile program={program} claim={programClaim} /></TabsContent>' academy-watch-frontend/src/pages/MyClubConsole.jsx | cut -d: -f1); echo "PC=$PC"; sed -i '' "${PC}r briefs/assets/P0-A8/content-line.jsx" academy-watch-frontend/src/pages/MyClubConsole.jsx && echo CONTENT-INSERTED
