# Phase 2 B3 — Admin control room

## Goal
- Programs, People, Safeguarding, Business night pages; draft PR to main stacked on #1109.

## Constraints
- Four page flags default OFF; preserve existing destinations when OFF.
- Reuse A1 audit/holds/outbox and A2 owner/access endpoints.
- Migration p2b3 → p2b2; guarded DDL/RLS, privacy export/erasure.
- Scratch aw_p2_b3 only, ports 5142/5198, foreground commands; no production/provider sends.

## State
- Done: four pages/backend flows, standing/audit, case intake/actions/outbox, authoritative cash/deployment views, tests, 14 reviewed screenshots and schema-only SQL.
- Done: latest A2 ef005e35 stack (includes c576762e snapshots); only B3 marked additive shared blocks, permitted narrow standing hooks.
- Done: draft PR #1115 to main, stacked on #1109: https://github.com/performlikemj/the-academy-watch/pull/1115
- Now: B3F3 complete (RB3V2 two LOWs fixed; all gates green); prior RB3V fix round 2 complete (all 3 MED/6 LOW fixed); latest A2 30ae5f4a incl main/N2 merged. Prior RB3 fix round 1 complete; all 6 MED/10 LOW fixed and safe policy defaults implemented. Hand-back `~/codex-runs/aw-redesign/logs/B3F1.final.md`; push/PR #1115, no merge.
- Next: orchestrator review/integration; four head pins now p2b3 per12:50, B1/B2 precede B3. No flag switch-on authorized.

## Validation
- OSV: no findings; frozen restore, no lockfile changes.
- Ruff/check/format pass; frontend lint0 errors/186 warnings, build pass. JavaScript repository has no separate typecheck command.
- Node193/193 pass after A2 ef005e35 corrected its two inherited stale source assertions. Earlier baseline reproduction retained in logs.
- Playwright8/8 (7 B3 + existing media pagination); desktop1440/mobile390 empty/flags/actions/privacy/safety/business.
- Full backend3509 pass/47 skip/4 expected p2a2 head pins. Orchestrator reserved the four assertions (BUS10:14); no other failures after restoring original auth error semantics.
- Latest focused201 pass, includes B3 24 + auth + match entries + contact (including consent after restore); no old bearer/media revival.
- Real HTTP16 auth negatives + suspend/restore checks pass; suspended OTP creates no code, old bearer denied after restore/fresh token succeeds; no provider sends.
- PostgreSQL localhost/aw_p2_b3 real chain ch02→fl01→p2a1→p2a2→p2b1→p2b2→p2b3 pass. Latest A2 reapply + B3 twice + preapply SQL twice; RLS4 true; case event UPDATE/DELETE/TRUNCATE rejected, retained-data downgrade refuses.
- Screenshots shots/B3:14 reviewed PNGs, live local-template DB API, fixtures labelled in INDEX.md. No overflow/errors/alerts.

## Cleanup / evidence
- Own Flask/Vite stopped; aw_p2_b3 dropped and absence verified; copied env/auth/scripts/baseline worktree/browser reports/scratch migration copy and borrowed B1/B2 removed.
- Retained screenshots, logs/B3.*, p2b3_preapply.sql; worktree retained for review.
- Limits: anonymous courtesy links follow current standing on restore; authenticated bearer/media epochs still require fresh login. Direct SAS lifetimes retain A2 bounds. Earlier subscription/refund dates and complete legacy public-minor audit unavailable, clearly shown.

## RB3 fix round 1 — complete
- Merged A2 bdbae2be; both marked standing guards precede access resolution and stay intact. All-squads roles remain squad-scoped; 12 A2 regressions pass.
- Cash projection runs after authoritative commit, provider fetches before projection transaction, catches/logs failures; signed replay + bounded recent-event job repair missing projections.
- Startup registers hooks without DB work; authenticated lazy Safety/Business reconciliation is bounded/throttled and catches missing-schema/DB errors.
- Case holds restore independently of Foundation, preserve source identity after restore, never lift independent/renewed holds. Existing tools sync linked cases; anonymous duplicates preserve evidence and never select recipients; owner moderation events shared.
- Wrong-code verification identical status/body/query count; correct code grants separately salted, epoch-bound 15-min subscription/account rights. Suspended users can cancel/export/delete; normal actions/checkout remain blocked.
- UI reason+target confirmation, last-owner warning, escaped/capped/batched/debounced search; dark OPTIONS and oversized IDs guarded. Retained-schema rollback documented.
- Final full pytest:3545 pass/47 skip/4 expected unchanged head pins; focused123 incl2 real PostgreSQL +12 A2; Node193, Playwright11, Ruff/format, lint0 errors/187 warnings/build pass. No separate JS typecheck command.
- PostgreSQL real chain upgrade with Safety/Business ON before B3 tables, DB-down CLI boot, invalid-SQL/provider projection isolation + replay, case idempotency, source timestamp/backfill twice, retained downgrade guard and preapply SQL twice pass.
- shots/B3 refreshed:22 visually reviewed PNGs (20 live +2 labelled account-access browser fixtures). All live page journeys200, no errors/overflow; confirmations cancelled.
- Cleanup: owned5142/5198 stopped, aw_p2_b3 dropped/absence verified, own credentials/scripts/reports/montages and borrowed B1/B2 migrations removed; tracked legacy report restored. No production/provider writes or flag changes.

## RB3V fix round 2 — complete
- Nine findings accepted for regression-driven fixes; no schema change planned beyond merged A2 owner index.
- A2 lock order: program row before grant rows; latest p2a2 preapply required twice on scratch DB.
- Next: PR #1115 review/integration; no merge or production enablement.

- Decision: retain verbatim committed B1/B2 migration prerequisites in B3 so a clean checkout has a resolvable p2b3 graph; supersedes earlier borrowed-file cleanup. No B1/B2 feature merge. Full final3642 pass/50 skip/4 reserved head pins; all graph-chain checks now pass.

- N1: version omitted from key/payload; notification savepoint/collision cannot abort moderation, including legacy intents. Player/club repeat cycles and old-tool lift/report resolution pass SQLite/PG.
- N2: real Stripe15.5 recursive to_dict boundaries incl list/reconcile; signed invoice/refund/replay/reversed-order cash rows pass SQLite/PG. Subscription emails precede projection I/O.
- N3: private suspension reason excluded from full OTP/account export; neutral standing/date only; sensitive sentinel remains admin-private.
- L4–L9: Safety OFF skips enqueue/delivery but syncs cases; original evidence/suppression source reused; sibling source sync/no takeover; exact dark wrong-method404+bounded offset; original auth401bytes; claim-verified manager warning when staff OFF. owns_hold DTO/UI explains protected holds.
- Final foreground gates: Ruff/format567 clean; full pytest3642 pass/50 skip/exactly4 reserved pins (cb01/pm01/s2/sea01); focused186 incl13 realPG (3 optional A2 PG skips); Node205; lint0err185warn/build pass; Playwright12/12. No separate JS typecheck command.
- Fresh scratch migration s4d1→ch01→ch02→fl01→p2a1→p2a2→p2b1→p2b2→p2b3; latest A2+B3 preapply each twice; one-active-owner index and4RLS verified. No B3 schema edit.
- shots/B3:26 reviewed PNGs (22 refreshed+4 new); real OTP verification/export at both widths excludes private reason; only request-code intercepted to avoid email. Staff-OFF last-manager warning and protected requester hold live captured.
- Cleanup complete: owned foreground services stopped, aw_p2_b3 dropped/absent, temp/auth/browser reports removed. Actual B1/B2 graph dependencies intentionally retained; hashes match their committed lane files.
- Decisions for MJ updated: deletion+same-email re-registration bypasses account-level suspension; whether to retain an address marker needs a policy/retention decision. Existing cancellation/ownership/whole-player-hide defaults retained.
- Delivery: fix2efda789 + latest A2 merge09056eb7 + real prerequisite/docs commit aa87d572 pushed; PR body verified with final gates/Decisions for MJ. Report ~/codex-runs/aw-redesign/logs/B3F2.final.md; no merge. Closing ledger-only commit follows.

## B3 fix round 3 — complete
- RB3V2 READY; fix two LOWs: real-app dark-method parity and early refund metadata backfill.
- Set four migration-head tests to p2b3 per orchestrator12:50; refresh origin A2/main and compare local B1/B2 prerequisite bytes.
- Next: orchestrator review/integration; merge order B1 → B2 → B3, no lane PR merge.
- Milestone: both LOWs fixed; 88 new real-app/receipt regressions pass. Dark map preserves SPA, Allow/405 and sibling routes; metadata backfill repairs new and already-deduplicated receipts.
- Base: main812be68d merged as ac37fbfd; A2 30ae5f4a already included. B1 14b26fbc/B2 ec569859 migration bytes unchanged; no re-copy needed. All four pins p2b3.
- Gates: OSV no findings/frozen deps unchanged; Ruff+format568 clean, Node205, lint0err185warn/build and Playwright13 pass. Full/PG running; initial fixture missing ADMIN_API_KEY corrected (88/88 pass).
- Dedicated PostgreSQL gate16/16 pass (incl legacy/modern/GOL early-refund backfill); real-app88/88 pass under default and hashseed37. Full corrected suite running without failures.
- Cleanup: own frontend stopped; browser reports/temp PR snapshot removed; aw_p2_b3 dropped and absence count0 verified.
- Final foreground gates: full pytest3721 pass/66 skip/0 fail; PG16 pass; real-app88 pass (also hashseed37); Node205; Playwright13; Ruff/format568; OSV/lint0err185warn/build pass. No separate JS typecheck script.
- Initial full/combined runs found only missing ADMIN_API_KEY in the new positive-route fixture; corrected fixture and full/dedicated PG gates pass. Logs retain attempts and final results.
- Final refresh: main9f329ea5 (A2 squash) merged8e099b92; latest A2d1eb66ad mergedcf12ab26. Both merge trees equal first parent49206302, no implementation change after gates; B3 standing guards and p2b3 pins retained.
- Final local prerequisites: B1 14b26fbc/B2 5cd45b0b migrations byte-identical (same SHA256 as prior round); neither re-copied. No schema/lockfile changes.
- Delivery: fix3242113a; PR1115 body includes exact merge order B1 → B2 → B3 and final gates. Hand-back ~/codex-runs/aw-redesign/logs/B3F3.final.md; no merge/deploy/flag changes/provider sends. Cleaned owned foreground services/aw_p2_b3/temp/browser outputs.
