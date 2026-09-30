# Phase 2 A1 foundation

- Goal: transactional notification outbox, append-only admin audit, canonical new-public adult rule, reversible club publication hold.
- Branch: p2/a1-foundation; migration p2a1 → fl01; flag P2_FOUNDATION_ENABLED default OFF.
- Constraints: no A2 registry/home/club guard/access edits; no legacy public caller changes; no child PII in queued payloads; no individual suppression mutation.
- Status: in-progress.
- Done: read phase decisions, required recon sections, DESIGN 6–9, BUS, repository guidance; posted START/CLAIMs.
- Now: commit/push/draft PR handback.
- Next: draft PR + BUS DONE, final ledger handback.
- Limitation: provider delivery is at-least-once across send-success/DB-commit failure.
- Milestone: 31 foundation tests and 57 focused account/funding/foundation tests passed (before expanded hold matrix); Ruff/format pass.
- PostgreSQL: target host/database verified, ch02 → fl01 → p2a1 applied; both new tables RLS true; preapply SQL reapplied twice successfully.
- PostgreSQL/HTTP: hide/lift + public 200/404/200, DB trigger rejects UPDATE/DELETE, concurrent dedupe converges to one intent, concurrent workers send once (mock provider), erasure redacts audit/deletes intent. Direct worker flag-OFF returns disabled JSON.
- Full pytest with copied local env: 3172 passed, 35 skipped, 3 pre-existing radar failures (same tests documented by INT); no application fixes applied for these. CI-equivalent rerun without env pending.
- Clean CI-equivalent pytest: 3177 passed, 40 skipped, 115 warnings; then two final regression tests added (stored API age without DOB + overlapping holds), focused foundation 33/33 pass; final full rerun underway.
- Cleanup: own 5120 server stopped; aw_p2_a1 dropped; copied env and backup removed; no Vite/simulator/dependency install used. Evidence logs and synthetic PostgreSQL smoke script retained under ~/codex-runs/aw-redesign/.
- Decisions: account-recipient outbox only; orchestrator approved A2 synchronous invite email exception on BUS. Whole-page hold for any linked hidden club; age alone is not new-public DOB evidence. Account privacy export/erasure runs even after flag OFF, empty foundation exports preserve prior response shape.
- Final review: turning rollout OFF preserves derived existing emergency holds; regression passes. Export timestamps serialize portably; final full pytest rerun pending. No blockers or unresolved product questions.
- Final gates: 3179 passed, 40 skipped, 115 warnings in 193.22s; Ruff check + format check pass (531 files); Python 3.11 compilation pass. Evidence `~/codex-runs/aw-redesign/logs/P2A1.report.md`. Frontend untouched.
