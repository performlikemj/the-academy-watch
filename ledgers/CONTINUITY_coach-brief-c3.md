# Task Ledger: Coach's Brief C3 + Camera Preflight P1

Parent: CONTINUITY.md
Root: CONTINUITY.md
Related: ledgers/DIRECTIVE_coach-brief.md, ledgers/CONTINUITY_coach-brief-c2.md
Owner: /root

## Goal

- Ship the MyClub brief editors, expected-vs-evidence reel display, honest limits, and capture-meta camera preflight fields.
- Preserve brief privacy and existing capture metadata across admin and club APIs.
- Deliver a tested commit and open PR from `feat/coach-brief-c3` without merging it.

## Constraints / Assumptions

- No worker or spike edits.
- Brief text is club-only; admin payloads contain hash/index/verdict only.
- Sim screenshots may use only the synthetic club fixture and synthetic brief text.
- Stage explicit paths only; no `git add -A` and no `--no-verify`.

## Key decisions

- Reuse backend brief normalization/hash helper so the roster GET supplies the canonical hash.
- Merge only allowlisted preflight keys plus `attack_direction_first_half` into existing `capture_meta`.

## State

- Done: Implemented C3/P1 frontend and backend, privacy/preservation coverage, synthetic-only sim guard and steps, and all requested local gates.
- Now: Commit, push `feat/coach-brief-c3`, and open the PR without merging.
- Next: Regenerate the synthetic fixture analysis after C2 is available, then rerun `brief-in-reel` for the remaining live acceptance check.

## Links

- Upstream: CONTINUITY.md
- Downstream: none
- Related: ledgers/DIRECTIVE_coach-brief.md

## Open questions (UNCONFIRMED)

- None.

## Working set

- `academy-watch-backend/src/services/`
- `academy-watch-backend/src/routes/video.py`
- `academy-watch-backend/src/routes/club.py`
- `academy-watch-backend/tests/`
- `academy-watch-frontend/src/lib/api.js`
- `academy-watch-frontend/src/pages/MyClubConsole.jsx`
- `academy-watch-frontend/src/components/video/PlayerReel.jsx`
- `academy-watch-frontend/tests/player-reels.test.mjs`
- `academy-watch-frontend/e2e/club-reels.spec.mjs`
- `sim/journeys/club-console.mjs`

## Notes

- 2026-09-03: Worktree started clean on `feat/coach-brief-c3` tracking `origin/main`.
- 2026-09-03: Added the shared worker-compatible brief hash helper to the roster response; frontend compares the server hash and never reimplements normalization.
- 2026-09-03: Added shared preflight validation/merge to admin and club POST/PATCH; route tests prove existing `qwen_analysis` and `local` metadata survive PATCH.
- 2026-09-03: `pytest tests/test_capture_meta.py tests/test_video_reels.py tests/test_club_console.py tests/test_club_console_bridge.py tests/test_vision_worker.py tests/test_qwen_analysis_store.py -q` — 155 passed.
- 2026-09-03: `node --test tests/player-reels.test.mjs tests/club-console-match-list.test.mjs` — 23 passed; dedicated `club-reels` Playwright config — 3 passed.
- 2026-09-03: `ruff check . && ruff format --check .` passed; `pnpm lint` passed with 0 errors/169 pre-existing warnings; `pnpm build` passed.
- 2026-09-03: `node --test sim/test/sim-lane.test.mjs && node --check sim/journeys/club-console.mjs` — 15 passed.
- 2026-09-03: External synthetic-fixture sim report `sim/report/2026-09-02T21-04-28-259Z/report.json` — 10/11 steps. `brief-edit` saved and survived reload; `brief-in-reel` failed honestly because the fixture's stored analysis predates C2 and has no `brief_checks`. No real brief was captured.
- 2026-09-03: Full frontend unit suite retains an unrelated baseline failure in `admin-newsletters-api.test.mjs`: `buildSeedTop5Request` expects `/admin/loans/seed-top5` but current code returns `/admin/tracked-players/seed-team`.
