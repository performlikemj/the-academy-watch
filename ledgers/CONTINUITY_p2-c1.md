# Phase 2 C1 — club adult publication and introductions

## Goal
- Private club-created adults claim their identity, independently consent to publication, receive moderated approval, and use strict club-first introductions.

## Constraints
- p2/c1-club-publication stacked on #1115; draft PR to main, ready only after full checks.
- Flag CLUB_PLAYER_PUBLICATION_ENABLED default OFF; no minors/guardian path or birthday publication.
- p2c1 -> p2b3; all new tables guarded/RLS/export/erasure.
- Reuse canonical adult, derived club holds, directory listability, staff capability, audit and outbox contracts.
- Own local aw_p2_c1, foreground ports5150/5201; no provider sends/prod writes.

## State
- Done: read master continuity, Phase2/design/BUS/evidence/repo guidance and mockup feature map.
- Now: map visibility, claims, introduction gates and required stack dependencies.
- Next: implement schema/workflow/eligibility, UI, regression and real PostgreSQL/browser checks, screenshots, PR and hand-back.

## Acceptance
- Known adult private invite binds verified recipient; self-claim independent of public consent; moderation and live club association required.
- Missing consent/private or withdrawn/revoked subjects absent from resolver/showcase/scout/follow/compare/search/export/digest/share.
- Club-origin introductions hidden from player until club grant; both keys required for messages; either side can revoke.
- Full Ruff/format/pytest + OSV/frontend lint/build/Node/relevant Playwright pass; reviewed desktop/mobile screenshots shots/C1.
