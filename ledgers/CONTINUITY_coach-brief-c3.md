# Task Ledger: Coach's Brief C3 + Camera Preflight P1

Parent: CONTINUITY.md
Root: CONTINUITY.md
Related: ledgers/DIRECTIVE_coach-brief.md, ledgers/CONTINUITY_coach-brief-c2.md
Owner: /root

## Goal

- Ship the MyClub brief editors, expected-vs-evidence reel display, honest limits, and capture-meta camera preflight fields.
- Preserve brief privacy and existing capture metadata across admin and club APIs.
- Deliver a tested review-fix commit to open PR #989 without merging it.

## Constraints / Assumptions

- No spike edits; the worker change is limited to consuming the shared backend brief helper.
- Brief text is club-only; admin payloads contain hash/index/verdict only.
- Sim screenshots may use only the synthetic club fixture and synthetic brief text.
- Stage explicit paths only; no `git add -A` and no `--no-verify`.

## Key decisions

- Reuse backend brief normalization/hash helper so the roster GET supplies the canonical hash.
- Merge only allowlisted preflight keys plus `attack_direction_first_half` into existing `capture_meta`.
- Seed and select only the dedicated `-sim-fixture` program; refuse any non-synthetic brief before club-console steps.
- Admin leak E2E proof is a DOM assertion after opening the AI read; backend sentinel tests remain the payload proof.

## State

- Done: Applied review fix round 2; persisted real system/coach briefs are refused before mutation, seed refusal becomes a club-console journey error, and failed program switches blank the page before capture. Focused backend 82, sim pure 20, Ruff, syntax checks, and synthetic sim 11/11 pass.
- Now: Commit and push the single requested review-round commit to PR #989.
- Next: Await review; do not merge.

## Links

- Upstream: CONTINUITY.md
- Downstream: none
- Related: ledgers/DIRECTIVE_coach-brief.md

## Open questions (UNCONFIRMED)

- None.

## Working set

- `academy-watch-backend/src/services/`
- `academy-watch-backend/scripts/dev/seed_sim_club_fixture.py`
- `academy-watch-backend/src/workers/vision_worker.py`
- `academy-watch-backend/src/routes/video.py`
- `academy-watch-backend/src/routes/club.py`
- `academy-watch-backend/tests/`
- `academy-watch-frontend/src/lib/api.js`
- `academy-watch-frontend/src/pages/MyClubConsole.jsx`
- `academy-watch-frontend/src/components/video/PlayerReel.jsx`
- `academy-watch-frontend/tests/player-reels.test.mjs`
- `academy-watch-frontend/e2e/club-reels.spec.mjs`
- `sim/journeys/club-console.mjs`
- `sim/run.mjs`
- `sim/test/sim-lane.test.mjs`

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
- 2026-09-03: Review round isolates sims onto `academy-watch-synthetic-sim-fixture`; the guard refuses bridge programs and any non-synthetic roster/system brief before the first club-console step.
- 2026-09-03: Synthetic post-C2 analysis uses the shared brief hash, one `evidence_found` plus one `no_evidence` check, all brief counters, and the coach's-brief honest-limit line; schema validation passed.
- 2026-09-03: `pytest tests/test_capture_meta.py tests/test_club_console.py tests/test_video_reels.py tests/test_coach_brief.py -q` — 118 passed.
- 2026-09-03: `ruff check . && ruff format --check .` — passed; 467 files formatted.
- 2026-09-03: `pnpm lint` and `pnpm build` — passed; build retains the existing large-chunk advisory.
- 2026-09-03: Focused frontend unit tests — 24 passed. Full `pnpm test` — 128 passed / 15 unrelated baseline failures (legacy paths/setup plus existing newsletter/nav expectations).
- 2026-09-03: `pnpm exec playwright test e2e/club-reels.spec.mjs --config=playwright.club-reels.config.js` — 3 passed; admin brief-leak assertion now checks rendered body text after opening the AI read.
- 2026-09-03: `node --test sim/test/sim-lane.test.mjs` plus syntax checks — 18 passed.
- 2026-09-03: Final self-boot live sim used backend `5099` and frontend `5277` with `SIM_GRADE=0`: 11/11 steps OK after explicitly selecting the guarded sim program; report `sim/report/2026-09-02T21-39-13-222Z/report.json`.
- 2026-09-03: Review round 2 retains the accepted worker delegation to `coach_brief.brief_payload`; no worker normalization change is needed.
- 2026-09-03: `/Users/michaeljones/Projects/loanarmy/.loan/bin/python -m pytest tests/test_dev_bridge_match_to_club.py tests/test_club_console.py -q` — 82 passed, including real system/coach brief refusal with no row changes and synthetic reset success.
- 2026-09-03: `ruff check . && ruff format --check .` — passed; 467 files already formatted.
- 2026-09-03: `node --test sim/test/sim-lane.test.mjs` plus `node --check sim/run.mjs` and `node --check sim/journeys/club-console.mjs` — 20 passed; syntax checks passed.
- 2026-09-03: Fresh self-boot synthetic sim used backend `5108` and frontend `5288` with `SIM_GRADE=0`: 11/11 steps OK; report `sim/report/2026-09-02T21-49-26-343Z/report.json`.
