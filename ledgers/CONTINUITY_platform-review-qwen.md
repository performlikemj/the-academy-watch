# CONTINUITY — Platform review 2026-08-23 build-out (qwen lane)

Parent: `CONTINUITY.md` · Plan: `docs/platform-review-2026-08-23.md` (untracked in the primary checkout
on 2026-08-23; copy lives with MJ) · Orchestrator: Fable · Executor: qwen3.8:27b on basecamp.

## Goal

Build out the platform review, Phase 0 first (unblockers), then Phases 1–4 + the frontend performance
workstream, with qwen doing ALL implementation from surgical briefs and Fable authoring briefs, verifying
every hand-back (diff + gate, own eyes), committing by path, and shipping PRs per coherent group.

## Constraints & assumptions

- Executor runtime: harness dsh 0.1.0-rc.7 headless + `~/Projects/harness/adapters/dsh/qwen-forge.patch.yml`
  → ollama on basecamp (`192.168.86.96:11434`, tailscale name `basecamp`), model `qwen3.8:27b-mlx-bf16`
  (262K ctx resident, keep-alive forever; ~17 tok/s). ONE qwen run at a time. Laptop must be on AC
  (runner refuses battery).
- Lane worktree: `.claude/worktrees/platform-review-qwen`, branch `feat/platform-review-p0-qwen`, based on
  `origin/main` `b90b180` (2026-08-23). The primary checkout's `main` is 37 commits behind origin (all
  dependabot) and dirty (CONTINUITY.md has ~600 lines of local-only ledger edits) — leave it alone.
- Runner: `./run-qwen.sh <TASK> [think=off]` (copied from the nbhd-ios constellation lane, adapted:
  forge patch default, loanarmy activity paths, prompt points at `briefs/QWEN.md` — NOT CLAUDE.md, whose
  router would send a small model into docs/agents). Budget 5400 s, first nudge 1800 s, then 900 s.
- Gate: `make gate TASK=<id>` → `lane-gate.sh`: `ruff check` + `ruff format --check` (CI mirrors) + the
  brief's NAMED tests from `briefs/<id>.gate` (+ `pnpm lint` + `pnpm build` for frontend briefs).
  `make integrate-gate` = every brief's tests + lint/build (lane gate before push).
  PROVEN 2026-08-23 to run INSIDE dsh's exact Seatbelt profile (`(allow default)(deny file-write*)
  (allow file-write* (literal "/dev/null"))(allow file-write* (subpath <worktree>)…)`): backend pair
  147 tests in 12 s; `node --test` + `pnpm lint` + `pnpm build` in 15 s. So qwen runs the gate itself;
  the runner re-runs it after dsh exits and exits non-zero on red.
- WHY named tests: on main, 12 backend test files fail at import (`LoanedPlayer`, `src.utils.brave_loans`,
  `wikipedia_loans`, `youth_competition_resolver.resolve_team_name`, `_enforce_loanee_metadata`) and
  `pnpm test` has 14 red source-grep tests (external-writers feature, seed-top5, navbar). Blanket suites
  are not a gate here. `tests/test_contact.py` CANNOT run alone (`NoReferencedTableError
  video_matches.club_program_id → club_programs`); always run it AFTER `tests/test_club_console.py`.
- Backend tests use the PRIMARY checkout's venv by absolute path
  (`/Users/michaeljones/Projects/loanarmy/.loan/bin/python`, 3.11.14, pytest 8.4.1). Frontend deps in the
  worktree came from `./scripts/setup_frontend.sh` (OSV gate + frozen lockfile; pnpm store hit, 3.6 s).
- qwen never commits (the sandbox cannot write the parent `.git` index). Fable stages by path.

## Key decisions

- 2026-08-23 MJ: "we will use qwen 27b to do the implementation. fable orchestrates and checks the work" —
  directions laid out clearly, no heavy thinking for the executor. Overrides the codex-executor default
  for this lane.
- Brief ids: `P0-<group><n>` per the review's Phase 0: A = contact-rail web surface (0.1), B = club
  match-list endpoint (0.2), C = small fixes (0.3), D = retention/sweeper (0.4). Patterns: copy-adapt or
  surgical, think=off, ≤60–90 min, verbatim anchors, failing test first, enumerated failure branches.
- Recon findings that shaped Phase 0 (verified in code on 2026-08-23):
  1. Club-consent emails link to `{PUBLIC_BASE_URL}/api/contact/club-consent/<token>`
     (`services/contact.py:238-245`); PUBLIC_BASE_URL is the SWA site, whose `navigationFallback`
     rewrites unknown paths to the SPA → the link is DEAD in prod (no React route). Even on the API host,
     GET returns JSON and nothing POSTs. → P0-A1 (link path) + a public consent page (A3).
  2. Web has ZERO contact-rail UI: `api.js` has only admin list/get; no scout verification submit either
     (backend `POST/GET /api/scout/verification` exists in `routes/trust.py`). iOS has the whole scout loop.
  3. `/api/scout/players` rows carry no claim info → an "Introduce" button cannot know claimability;
     probably a small backend brief (A0: `contactable` flag) before the ScoutPage button.
  4. Prod `CONTACT_RAIL_ENABLED`: the 2026-08-10 audit says ON; code default is false. UNCONFIRMED live
     (curl to the ledger FQDN returned 000 — off-peak scale-to-zero).
  5. `club_registry._table_columns` introspects on every call (13 call sites); a per-app-context memo
     must keep `test_contact.py:2124`'s monkeypatch of `_table_columns` working.
  6. `scout_watchlist_entries` has only the (user, player) unique; new migration must chain from head
     `c201` using `create_index_safe` (copy `ug01_user_blocks.py`).
  7. Retention: `RAW_RETENTION_DAYS=90`, `VideoMatch.expires_at` stamped at upload-complete, status
     `expired` exists in the model's list but no code sets it and `video_storage.py` has no delete;
     reaper `video_queue.reap_stale_jobs()` is only behind `POST /admin/video/reap-stale-jobs`; scheduled
     ACA jobs run `python -m src.jobs.run_*` with `from src.main import app` + `app.app_context()`.
  8. Read SAS for the admin media redirect is 6 h (`READ_SAS_HOURS`) vs a 30-min media token
     (`routes/video.py:677-716`).

## State

- Done (2026-08-23): full recon; lane scaffolding committed `56bf789` (runner, gate, Makefile, QWEN.md,
  BACKLOG, 4 briefs); sandbox proof; baseline gates green (backend pair 147/147, frontend lint/build ok).
- Now: SMOKE run `qwen-SMOKE-20260822T2230` (proves brief → file → gate → handback on basecamp).
- Next (in order): P0-C1 → P0-A1 → P0-B1 → author A-group briefs (A0 contactable flag, A2 api.js
  methods, A3 consent page + route, A5 scout verification page, A4 Introduce dialog on ScoutPage, A6
  introductions page + thread, A7 player inbox, A8 club inbox tab, A9 nav), B2 (console switch to the
  list endpoint + delete localStorage index), C2 (watchlist index `sw01`), C3 (memoize), C4
  (`run_video_maintenance.py` job), D1 (`expire_raw_footage` + `delete_blob`), D2 (30-min read SAS +
  `Cache-Control: private, no-store` on the redirect). Infra (Fable, MJ-gated): ACA job for maintenance,
  Azure lifecycle rules (Hot→Cool→delete @90d).
- PR plan: one PR per group (C, A1+A3, B, D…) from this branch via `gh pr create`; merge squash; watch
  deploy; re-base the lane on main between groups.


### 2026-08-23 03:05Z — PR-1 merged; step scripts everywhere

- PR #887 squash-merged → main `5af2ab5` (C1, A1, A2, A3, A3b, B1). Deploy run 32614375785 = success (all jobs). Live smoke 03:12Z:
  `GET /api/contact/club-consent/<bogus>` → 404 `invalid_consent_link` ✓; `GET /api/club/1/matches` unauth → 401 ✓; SPA route 200 ✓;
  Playwright on theacademywatch.com/contact/club-consent/<bogus> renders 'This link is no longer valid' (no Retry — correct for a 404) ✓.
- Lesson (second whitespace failure): qwen cannot reproduce leading spaces even when COPYING a command from the brief.
  Every block containing `grep -n` / `sed -i` / `awk` in the remaining briefs is now a shipped `briefs/assets/<TASK>/step-N.sh`
  (36 scripts, byte-identical to the former blocks, no cross-block variables); the brief says `bash …/step-N.sh`; QWEN.md rule added (ad82b2f).
- PR #888 (B2) opened 03:16Z; codex P1 (list rows carry no roster → MatchDetail could save an empty roster and wipe entries) → P0-B2b brief (hydrate via getClubMatch before rendering; proven, eslint clean). PR-2 will be B2 + B2b (cherry-pick onto the PR branch), PR-3 = A-group.
- Lane REBASED onto origin/main 5af2ab5 at 03:15Z (6 commits replayed clean; B2 = 6352091). Original plan note: squash-merge leaves the lane based on b90b180; rebase with `git rebase --onto origin/main cbe5a1e` at a quiet
  moment (finish scripts honour `$S/PAUSE_LANE`: commit but do not launch). Next PR branches can also be built by cherry-pick onto origin/main in a separate worktree.

## Run log

| Session | Task | Result | Verified by Fable | Notes |
|---|---|---|---|---|
| qwen-SMOKE-20260822T2230 | SMOKE | pipe proven; budget-stopped (900 s) before handback | file byte-exact; gate event green in telemetry | 155K input / 3K output tokens over 13 tool calls — prefill-bound (~35 s/step); real briefs need ≥60 min |
| qwen-P0-C1-20260822T2246 | P0-C1 | DONE — gate green twice (red→green), handback filed, runner post-gate green (153 s) | diff byte-exact to brief; commit `84369d1` | 44 min wall; ~30 min between test write and App.jsx edit (reading the 4,300-line file); no nudge fired |
| qwen-P0-A1-20260822T2330 | P0-A1 | DONE — gate red→green (test-first), handback filed, runner post-gate green | diff exactly as briefed (1 line + 2 asserts); commit `e54a750` | 34 min wall; in-sandbox gate 88–135 s and runner post-gate 370 s (vs 12 s in the proof) because the LAPTOP was at load avg ~47 — nine codex runs + two opencode processes from other sessions; not a lane defect |
| qwen-P0-A2-20260823T0002 | P0-A2 (brief v1) | BUDGET-STOPPED at 3605 s, 2 nudges, test file written only in the last minutes | test file REJECTED: qwen retyped the brace pattern as `'\n     }\n'` (5 spaces) → every assertion would pass vacuously; deleted | ROOT CAUSE found in the transcript: 1,337 reasoning chunks vs 35 text chunks — qwen3.8 ignores ` /no_think`; 97% of output was hidden thinking at ~5 tok/s |
| qwen-PROBE-20260823T0106 | boot smoke | PONG in 1 step, 2 output tokens, ZERO reasoning chunks | config change verified by BOOTING (harness rule) | proves `reasoning_effort: "none"` via the patched forge route |
| qwen-P0-A2-20260823T0111 | P0-A2 (brief v2) | STOPPED by Fable at ~5 min (convention change) | test file written in 2 min (thinking-off works) but AGAIN `'\n     }\n'` (5 spaces) — a systematic retype of whitespace inside string literals; vacuous test | NEW CONVENTION: files a brief ships go under `briefs/assets/<TASK>/` and qwen COPIES them (`cp`); qwen's job is the edits inside existing files; the orchestrator byte-checks shipped files at commit. Lesson: never use whitespace-sensitive string patterns in source-assert tests |
| qwen-P0-A2-20260823T0118 | P0-A2 (brief v3: shipped test + two pastes) | STOPPED by Fable at 52 min; paste 1 KEPT (line-exact); paste 2 never landed. TRANSCRIPT PROOF: every `edit` old_string qwen sent had the closing brace over-indented (`\n     }` / `\n      }` vs the file's 4 spaces) — a systematic bias; it never matched, it spent 20+ min on whitespace forensics and finally wrote its own python apply script (that is how paste 1 landed). NEW CONVENTION (QWEN.md): insertions into existing files are `grep -n` + `sed -i '' "Nr briefs/assets/<TASK>/<snippet>"`; qwen copies commands, never code. The test-file brace slip was the same bias | (replaced by v4 below) |
| qwen-P0-A2-20260823T0211 | P0-A2 (brief v4: copy + sed) | DONE in 9 min — test copied, gate RED, `sed Nr` insertion, gate GREEN (12 s), handback, runner post-gate green | test byte-identical to asset; api.js insert-only/exact/placed/each-once (70 lines); commit `b0690df` | the new normal: thinking off at the wire + copy/sed recipe |
| qwen-P0-A3-20260823T0221 | P0-A3 (consent page; 3 shipped files + 2 sed lines) | DONE in 8 min — gate RED→GREEN (12 s), handback, runner post-gate green | 3 copied files byte-identical to assets; App.jsx +2 asset lines, insert-only; commit `aedad98` | |
| qwen-P0-B1-20260823T0229 | P0-B1 (club match-list route; snippets + sed/cat) | completed, gate green 1st try (ruff+148 tests), 0 nudges, ~12 min | bdae27f | route + test byte-exact vs assets |
| qwen-P0-A3b-20260823T0241 | P0-A3b (consent page transient-error fix; one cp) | completed, gate green 1st try, 0 nudges, ~10 min (mostly pnpm build) | cbe5a1e | page identical to asset |
| qwen-P0-B2-20260823T0252 | P0-B2 (console uses listClubMatches; localStorage index removed) | HELP at 585s (step 2e: retyped awk regex lost 2 leading spaces; 2a–2d + api.js correct) → step2e.sh shipped, resumed 03:04Z → completed, gate green, ~22 min wall incl. pause | 6352091 (post-rebase) | file byte-identical to the brief's recipe re-run on HEAD; finish-b2's added-lines check was the wrong shape for a replacement |
| qwen-P0-A0-20260823T0315 | P0-A0 (scout contactable flag: 3 placements + 2 tests, step scripts) | completed, gate green (attempt 3 = after placements), 0 nudges, ~9 min | 95a70f9 | rederive (step scripts replayed on HEAD) IDENTICAL for both files + finish checks |
| qwen-P0-B2b-20260823T0325 | P0-B2b (roster editor hydrates the selected match first — codex P1 on PR #888) | running | — | |
| — | **PR-1 #887** `feat/p0-contact-foundation` (snapshot of lane HEAD c4b98af: tooling + C1 + A1 + A2 + A3) | OPEN 02:31Z; lane full gate green (26 s) before push | CI watch in progress; read codex-connector reviews before merging (MJ 2026-08-11 rule) | https://github.com/performlikemj/the-academy-watch/pull/887 |
| qwen-P0-A2-20260823T0118 (v3, earlier note) | — | test copied in 2 min, gate RED as predicted, first paste (36 lines) LINE-EXACT to the brief; then a 30-min stall → nudge → restart re-read brief, hit dsh's "edit requires reading the file first" rule, read the anchor with offset/limit, re-applied, working on paste 2 | — | dsh facts learned: `edit` refuses unread files (read the anchor range first); restart prompt works; zero reasoning chunks now | — test copied in 2 min, gate RED as predicted, first paste (36 lines) LINE-EXACT to the brief; then a 30-min stall → nudge → restart re-read brief, hit dsh's "edit requires reading the file first" rule, read the anchor with offset/limit, re-applied, working on paste 2 | pending | dsh facts learned: `edit` refuses unread files (read the anchor range first); restart prompt works; zero reasoning chunks now |

## Executor performance notes (measured)

- SMOKE: 835 s wall, 13 tool calls, 155K input / 3K output tokens, 7.5 tok/s streaming.
- P0-C1: 2402 s wall, 26 tool calls, **600K input / 12K output**, 7.3 tok/s streaming, 0 compactions.
  Generation (not prefill) dominates: ~28 min of the 40 were output at ~7 tok/s. The box benchmarked
  17 tok/s for this tag on 2026-08-22; `/api/ps` during the lane shows qwen 64 GiB + gemma4 48 GiB
  resident (= 112 GiB on a 128 GB Mac) → likely memory pressure from co-residency. A concurrent probe
  queued behind the in-flight request (ollama serves one at a time) — measure at IDLE between runs.
  If idle speed is still ~7 tok/s, propose to MJ: unload gemma during lane hours
  (`OLLAMA_MAX_LOADED_MODELS=1`) — his family-server call, not mine.
- Brief hygiene that pays: verbatim old/new blocks, exact line ranges to read (`sed -n 'a,bp'`), never
  "read the file"; big files (App.jsx 4,300 lines) cost ~30 min of re-reading in C1.
- **RESOLVED 2026-08-23 01:06Z — the slowness was THINKING, not the box.** Idle probe with gemma
  unloaded: 45.8 tok/s generation. Transcript of the stalled A2 run: 1,337 reasoning chunks vs 35 text
  chunks — qwen3.8 ignores the ` /no_think` prompt switch on ollama's /v1 route. Probes on basecamp:
  `/v1/chat/completions` baseline = 46 completion tokens + `reasoning` field; with
  `reasoning_effort: "none"` = 2 tokens, no reasoning, 0.5 s; raw `think: false` on /v1 is ignored;
  `/api/chat think:false` works (control). FIX (harness `adapters/dsh/qwen-forge.patch.yml`, backup
  `.bak-20260823`): provider `reasoning: "off"`, `compat.supportsReasoningEffort: true`, model
  `reasoningEfforts: {"off": none, low: low, high: high}`. Verified by BOOTING (PROBE session: zero
  reasoning chunks). Expect tasks to drop from ~40 min to ~10 min.
- 2026-08-23 00:20Z MJ ("horses for courses"): gemma4 UNLOADED from basecamp for lane hours
  (`keep_alive: 0`; reloads on the next family request, ~15 s). Before: qwen 63 GiB + gemma 48 GiB =
  111 GiB resident on 128 GB (GPU wired cap ~96 GiB) → paging hypothesis. Idle-speed probe runs in the gap
  before P0-A3; if it reads ~15–17 tok/s the harness directive's "MAX_LOADED_MODELS=2 — qwen + one more
  fit" needs the footnote "fits at boot, not at 262K context". Re-load gemma after the lane if wanted:
  any request to `gemma4:26b-a4b-it-bf16`.

## Open questions (UNCONFIRMED)

- Live value of prod `CONTACT_RAIL_ENABLED` (see decision 4).
- Whether the web should gate "Introduce" on an A0 `contactable` flag vs. letting the 403
  `player_not_claimable` response explain it (recommendation: A0 — never show an action that always fails).
