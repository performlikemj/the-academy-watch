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
- Now: push branch and create draft PR to main; final hand-back.
- Next: orchestrator adversarial review and integration; four head pins updated there, B1/B2 precede p2b3. No flag switch-on authorized.

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
