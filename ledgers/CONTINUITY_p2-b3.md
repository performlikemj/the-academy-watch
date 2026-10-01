# Phase 2 B3 — Admin control room

## Goal
- Programs, People, Safeguarding, Business night pages; draft PR to main stacked on #1109.

## Constraints
- Flags default OFF, flag off preserves existing pages/behaviour.
- Reuse A1 audit/holds/outbox and A2 owner/access endpoints.
- Migration p2b3 → p2b2; guarded DDL + RLS; privacy export/erasure.
- Scratch aw_p2_b3 only, ports 5142/5198; no background commands, no production writes/emails.

## State
- Done: read phase/design/contracts/repo guidance/boards/P2R §7A–D; verified requested branch starts A2 bb126fce.
- Now: implementation complete; final validation, latest A2 stacking, screenshot review and delivery.
- Next: backend negative/security tests, frontend lint/build/browser, screenshots, scratch migration checks, cleanup, draft PR + final hand-back.

## Validation
- OSV: no findings; frozen restore complete, no lockfile changes.
- Ruff/format and frontend lint/build pass; 8 Playwright pass (7 B3 + existing media pagination).
- Focused B3: 24 passed (suspension/OTP/optional-auth/admin/grants/media/consent, privacy, transactional intake, money/date/currency/dedupe).
- Full backend with actual borrowed B1/B2 migrations: 3481 passed/47 skipped, ONLY four p2a2 head pins fail. Orchestrator explicitly reserves those for integration (BUS 10:14).
- Node: 193 pass/2 fail; both static ClubHome source assertions fail unchanged on bb126fce (baseline log).
- PostgreSQL localhost/aw_p2_b3: ch02→fl01→p2a1→p2a2→p2b1→p2b2→p2b3; reapply twice/RLS4/append-only UPDATE DELETE TRUNCATE rejection pass.
- 14 live API screenshots captured (local template contains pre-existing test fixtures), desktop1440/mobile390, no overflow/pageerrors. Final retake removing dev overlay pending.
