# CONTINUITY — Coach's brief (Track C) · positioning (Track P) · merge signals (Track M)

Directive: `ledgers/DIRECTIVE_coach-brief.md` (authored 2026-09-02; MJ chose "brief first").
Parent: `CONTINUITY.md` §Now 2026-09-02. Related: `DIRECTIVE_evidence-bench.md` (E2/E3), `CONTINUITY_video-analysis.md`.

## State
- 2026-09-03: C2 implementation started on `feat/coach-brief-c2` from merged C1 commit `34f003e`; child ledger `CONTINUITY_coach-brief-c2.md`. Prerequisite model field confirmed; no Basecamp/Ollama calls and no frontend changes.
- 2026-09-03: C2 implementation verified: spike 167 passed; worker 25 passed; backend-config and bare-spike Ruff check/format pass; no-brief grounded prompt remains byte-identical. Exact backend suite retains its 12 known collection errors; collectible diagnostic 1,975 passed / 42 unrelated failures / 3 skipped. Commit/push/PR delivery next.
- 2026-09-03: C2 delivered as one scoped commit on `feat/coach-brief-c2`; PR #985 open and unmerged: https://github.com/performlikemj/the-academy-watch/pull/985.
- 2026-09-03: PR #985 CI green: Backend Lint, Frontend Dependency Security / osv-scan, and Frontend Build & Lint passed.
- 2026-09-02: directive authored from a codex read-only recon of main `bea9ec6`, then REVISED after a codex critique (21 findings, 11 blockers folded in: columns-on-owning-rows, hash+index persistence, evidence_found/no_evidence verdicts, fixture bridge for match 4, brief.json separate from the team pass, synthetic-only sims);
  decisions B1–B5 recorded from MJ. C1 storage, club routes, and sentinel leak tests are open as PR #973: https://github.com/performlikemj/the-academy-watch/pull/973.
- 2026-09-02: `cb01` now chains from main's moved single head `s2f1` (`s2f1` ← `pm01`), not as a second head from `pm01`. Six guarded columns, manager routes, roster-name validation, and requested leak coverage implemented; the prior focused command passed 80 tests.
- 2026-09-02: required `pytest -q` cannot collect because 12 legacy modules import permanently removed models/utilities. With those modules ignored, 1,860 passed / 36 failed / 3 skipped; one C1 response-shape failure was fixed, leaving 35 pre-existing failures confirmed by `--lf`. No unrelated fixes made.
- 2026-09-02: adversarial review found and closed a partial-DDL gap: `cb01` now separately guards/repairs named `ON DELETE SET NULL` FKs when audit columns already exist. Follow-up review: no blockers.
- 2026-09-02: PR #973 review round fixes 2+ character and non-Latin roster-name screening, original brief line numbers, empty-clear short-circuiting, and FK-by-column migration detection; focused 80 tests pass.
- 2026-09-02: PR #973 review round 2 complete: Latin-token boundaries now treat only adjacent Latin letters/digits/underscores as word characters, name comparison uses accent folding, and validation retains original line numbers across leading blanks. Exact focused command passes 80 tests; whole-backend Ruff check and format check pass.
- 2026-09-02: B1 dev-only fixture bridge implemented and verified on `feat/dev-club-fixture-bridge`: 53 requested backend tests pass; backend-wide Ruff check/format clean; PR #975 open and unmerged. Child ledger `CONTINUITY_dev-club-fixture-bridge.md`. No basecamp/prod execution.
- 2026-09-02: merged `origin/main`, preserved both master/task ledger updates, and re-chained `cb01` from stamped main head `s2f1`. Graph is `cb01 → s2f1 → pm01` with one `cb01` head; focused suite including `test_s2_foundation.py` passes 111 tests; whole-backend Ruff check and format check pass.

## Next
- Review PR #973, then pre-apply guarded `cb01` on prod via the pooler, verify the six columns, and stamp `cb01` before merge.
- Review/merge B1 PR #975, then Fable runs it on basecamp after C1 merges.
- Then C2 worker context + prompt/schema/gate → C3 MyClub editor + reel block
  (+ P1 camera-class fields) → match-4 regen with MJ's three briefs = acceptance.
- P2 calibration research + M1 merge scorer on basecamp in parallel (one codex brief each).

## Gotchas carried in
- Briefs are club-private: only `@require_club_manager()` routes; never in exports/manifests/sim reports.
- No negative verdicts (`evidence_found | no_evidence` only); no names to the model.
- Deploys never migrate: pre-apply `cb01` on prod via the pooler and on basecamp's seeded DB before the regen.
- backend CI has NO pytest step (ruff only); the whole suite has 35 pre-existing failures + 12 collection errors on main — the local branch-vs-main failure-set diff is the only test gate.

## Working set
- Files: `migrations/versions/cb01_coach_briefs.py`, `src/models/funding.py`, `src/routes/club.py`, `tests/test_cb01_coach_briefs.py`, `tests/test_club_console.py`, `tests/test_pm01_player_match_entries.py`, `tests/test_s2_foundation.py`.
- Verified: `pytest tests/test_cb01_coach_briefs.py tests/test_club_console.py tests/test_club_console_bridge.py tests/test_pm01_player_match_entries.py tests/test_s2_foundation.py -q` → 111 passed.
- Verified: whole-repo `ruff check academy-watch-backend` → pass; `ruff format --check academy-watch-backend` → 452 files already formatted; `alembic heads` → `cb01 (background_jobs) (head)`.
- Baseline blockers: exact `pytest -q` → 12 collection errors; collectible suite after the C1 compatibility fix retains 35 unrelated failures.
- PR: https://github.com/performlikemj/the-academy-watch/pull/973 (origin/main merge and verified re-chain included in this delivery).
