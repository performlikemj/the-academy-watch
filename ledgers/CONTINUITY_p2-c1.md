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
- Now: C1F2 union implemented; final full flags-off + modern browser gates running foreground. Final regressions48 + real PG7 pass; affected192 earlier; lane browser30 + actual PG/HTTP-browser1, Node221, Ruff-format595, OSV547, lint0err191warn/build pass. Reverse41 failures on reviewed head, actual-main dark local parity4 pass. Main784b1490 + freshly pushed B3F5 51f30f5b included. Restart full flags-off/modern browser gates on merged tree; earlier partial flags-off run had no failures at66%, modern257pass/5skip/one403-fixture failure pending recheck; push pending.
- Contract C1F2: p2c1 SHA2567ff6c7d208d3e5f5ff2c185058f4b9e75f878eebe85c548be951415ff7c95685; new retired-claim partial uniqueness + legacy follow-name scrub; preapply twice+upgrade == direct whole public schema hash3ce8618429c17aeb4e3975042ebefe207044fe3cd68806db2b26884eaf59acdd. BUS CONTRACT posted C2/C4.
- Done (fix round 1): RC1 F1–F11 FIXED; read full RC1 and reverse probes. Flag OFF provider response/query parity vs actual main, local-only ON gate/admin unlink, export withholding + independent erasure, masked moderation/self-invite block, claimed-consented queue, revoke cooldown, permanent reject closure, invited-email purge/index, playbook/router/hand-back, normal dark SPA fallback.
- Done: main/B2 release784b1490 + B2 head55b1d3ac + latest B3 head46a4274f included; application source frozen at b01b2f0d. Later ledger-only delivery commit requires no application rerun.
- Done: final foreground flag-off pytest4385pass90skip0fail153warnings877.72s; affected C1+N3+PG186pass, PG5, final cache/RC1/parity58pass, actual-main parity8pass; Node219, modern offline browser250pass5skip0fail, focused browser22, Ruff clean/format594, OSV547/no issues, lint0err191inherited warnings/build pass. No separate TS target (JS repo).
- Done: seven-private-state compact sweep + published control624 primary requests plus saved/scout/export/digest cases; reverse new probes on reviewed4eacc2ff fail28/pass3/deselect8. Queue fix already existed at initial-final6ca888fc and now has five-state regression.
- Done: p2c1 migration SHA256 c11e36f12cbacdc62ff852d72f7686121e1a5fd4c15d2618809fe0024b84325c; repo/external preapply77beceb6db0c1b6341e53388d53f1092945d62bacaec57009ccbef6e6b7e5ec1. Guarded local-player index/nullable email, exact preapply twice+upgrade schema equality; BUS CONTRACT acknowledged by C2/C4.
- Done: reviewed moderation/self-invite desktop/mobile evidence in external shots/C1/INDEX.md; original C1.final.md restored complete actual initial SHA/CI/gates/cleanup. New docs/agents/club-player-publication.md + CLAUDE router.
- Done: owned aw_p2_c1/aw_p2_c1_pre dropped/count0; shared DB unchangedch02; temporary baseline/review worktrees removed; owned5201 server stopped; temporary config/env/auth/browser outputs removed. Logs/schema dumps/screenshots retained.
- Decision: admin evidence shows masked emails + adult yes/no/source; inviter/claimant own account/email approval blocked, including latest re-inviter. Daily dark-capable publication-retention job + outbox worker must be scheduled before separate flag activation.
- Now: RC1 fix round 1 complete; PR #1121 ready, unmerged. Exact pushed head/CI status and per-finding evidence in external logs/C1F1.final.md; BUS DONE releases all C1 claims. No feature activation/deploy/provider calls.
- Next: orchestrator independent REVIEW-DUEL on pushed head, prerequisite release then C1; preapply before deploy, separate flag approval.
- Initial delivery: ready PR #1121 stacked on #1115; full4342pass89skip0fail, PG4/real HTTP-browser1/Node219/modern browser240pass5skip/Ruff-format590/OSV547/lint-build. Initial final6ca888fc exact CI36826155752 all5jobs green; see external C1.final.md.
- Validation limitation: raw old/live browser234pass16fail6skip16notrun at initial delivery; seven suites lack live ADMIN_API_KEY setup, nine old Journey tests target retired route/API. Not rerun/claimed green in fix round. Optional old live radar suites require opt-in; full flags-off uses normal CI environment with separate real C1 PostgreSQL coverage.
- Integration: B2 counts-None contract retained; four head assertions pin p2c1. Exact Rule.methods attributes retained in C1/B3 dark maps.

## Acceptance
- Known adult private invite binds authenticated matching recipient; self-claim independent of public consent; moderation and live club association required.
- Missing consent/private or withdrawn/revoked subjects absent from resolver/showcase/scout/follow/compare/search/export/digest/share.
- Club-origin introductions hidden from player until club grant; both keys required for messages; either side can revoke.
- Modern full checks and relevant negative cases pass; legacy browser prerequisite/retired-route failures explicitly retained as limitations.
