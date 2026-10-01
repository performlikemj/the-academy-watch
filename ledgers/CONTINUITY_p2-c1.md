# Phase 2 C1 — club adult publication and introductions

## Goal
- Private club-created adults claim their identity, independently consent to publication, receive moderated approval, and use strict club-first introductions.

## Constraints
- p2/c1-club-publication stacked on #1115; PR to main created draft, ready only after full checks.
- Flag CLUB_PLAYER_PUBLICATION_ENABLED default OFF; no minors/guardian path or birthday publication.
- p2c1 -> p2b3; guarded table/RLS/export/erasure; retained consent prevents downgrade.
- Reuse canonical adult, derived club holds, directory listability, staff capability, audit and trusted outbox contracts.
- Own local aw_p2_c1 and foreground ports5150/5201; no provider sends/prod writes.

## State
- Done: RC1 focused218 pass (includes original C1 + N3), main baseline provider8 parity checks green; seven-private-state compact sweep + published control green. Fixes/evidence and nullable-email/index p2c1 CONTRACT posted; full gates next.
- Done: main/B2 squash784b1490 included with zero application delta vs360628dc refresh; B3 d49ec794 current. PostgreSQL5 and exact preapply twice/upgrade schema parity green; Node219/OSV547/lint0err191warn/build/Ruff594, focused browser22 green. Reviewed new moderation/self-invite mobile shots.
- Now: fix round 1 RC1 F1–F11 in progress; merge main/B2/B3, regression evidence per finding, full foreground gates, push only.
- Decision: admin evidence exposes masked emails + adult yes/no/source; same inviter/claimant approval blocked by default. Flag OFF preserves provider read/query parity with main.
- Done: read master continuity, Phase2/design/BUS/evidence/repo guidance and mockup feature map.
- Done: real B1 811fabca, B2 16540e03, B3 d49ec794 and main/N3 adea5177 integrated; p2c1 upgraded actual scratch PostgreSQL. Shared adult policy retains N3 trusted DOB/journeys and B2 hold reconciliation.
- Done: independent recipient claim/consent/moderation, live canonical visibility including saved/cached aliases, club-first inbox/notifications/messages/revocation, export/erasure and real API web handoff.
- Done: final full backend4342 pass89skip0fail; real PostgreSQL4; selected browser92; real HTTP/PG browser1; Node219. OSV547 clean; Ruff/format590; lint0errors191 inherited warnings; build passes (no separate TypeScript target).
- Done: 20 reviewed desktop/mobile PNGs, six from the actual isolated HTTP/PG workflow. Evidence index ~/codex-runs/aw-redesign/shots/C1/INDEX.md.
- Done: final full modern offline browser240 pass5skip0fail; raw legacy browser limitation documented separately.
- Done: owned servers5150/5201 stopped, aw_p2_c1 dropped (pg_database count0), private env/auth/temp/browser outputs removed; pre-existing tracked browser report restored.
- Done: PR #1121 created draft against main with stacked-on #1115 body, then marked ready after full local gates.
- Done: main B1 release e82bb4e3 refresh resolves only duplicated stack registrations/features/routes and head pins; retained validated C1 code. Application diff vs 29c4dc54 is empty; B1 ledger refreshed. Full gates repeated before refresh push: backend4342pass89skip0fail, modern browser240pass5skip0fail, Node219/Ruff-format590/OSV547/lint-build green. Exact logs in external hand-back.
- Now: PR #1121 ready for orchestrator review; exact final SHA/CI and final owned-resource cleanup recorded in external logs/C1.final.md.
- Next: orchestrator adversarial review and prerequisite merges before C1; flag activation separate. PR created draft against main then marked ready after all local checks.
- Validation limitation: raw full browser234pass16fail6skip16notrun; seven older suites lack live ADMIN_API_KEY setup, nine older Journey tests target retired singular route/stale API. Same debt recorded in baseline INT.report.md. Optional old live radar contracts fail on base when DB configured; final CI-equivalent full suite leaves their documented opt-in unset, alongside separate real C1 PostgreSQL tests.
- Integration: B2 counts-None contract replaces earlier empty-map workaround; ON empty counts remains valid. Four migration-head assertions pin p2c1. Exact Rule.methods set preserved in C1/B3 dark maps per agreed C4/C2 integration fix.

## Acceptance
- Known adult private invite binds authenticated matching recipient; self-claim independent of public consent; moderation and live club association required.
- Missing consent/private or withdrawn/revoked subjects absent from resolver/showcase/scout/follow/compare/search/export/digest/share.
- Club-origin introductions hidden from player until club grant; both keys required for messages; either side can revoke.
- Modern full checks and relevant negative cases pass; legacy browser prerequisite/retired-route failures explicitly retained as limitations.
