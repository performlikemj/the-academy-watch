# CONTINUITY.md

> Master ledger — canonical project state. Read this first every turn.

## Goal

The Academy Watch — Football academy tracking platform with AI-powered newsletters and journalist content management.

## Constraints / Assumptions

- Backend runs on Flask (port 5001)
- Frontend runs on React/Vite (port 5173, proxies /api to backend)
- PostgreSQL database
- Deployed to Azure Container Apps

## Key Decisions

- **CODEX DISPATCH PROTOCOL (ALL SESSIONS — effective 2026-07-17):** NEVER run
  `pkill -f "codex exec"` (or any codex-killing sweep). It has been destroying
  OTHER sessions' in-flight codex runs (confirmed: full-circle FC-B1/I1/I2
  runs killed by the seasons session's pkill-before-dispatch habit; nbhd's run
  too). Correct protocol: non-destructive guard `pgrep -f "codex[ ]exec"` —
  if busy, WAIT for the account to free (poll ~45s), never kill. One codex run
  per ACCOUNT at a time. Wrap dispatches in `caffeinate -is`. If a run looks
  orphaned/stuck, verify with its ledger owner before killing.

- Using AGENTS.md + Ralph workflow for autonomous task execution
- Planning ledgers track task status for handoff between interactive and autonomous modes
- Frontend dependency installation is a supply-chain boundary: use the frozen
  lockfile and run the repository security gate; never treat `pnpm install` as
  an unconditional development step.

## State

### Done
- Grounded caption label/claim fault isolation complete (2026-09-02): grounded-only unknown labels coerce to `unclear`, malformed claims drop independently, sampling reports three fault counters, and legacy validation remains strict. Mock-only spike suite: 131 passed; both spike files pass bare Ruff check/format. See `ledgers/CONTINUITY_grounded-caption-lenient-enums.md`.
- Grounded Qwen caption/read truncation fix complete (2026-09-02): complete JSON returned at `done_reason=length` is accepted with a warning, while invalid JSON raises an explicit truncation error; grounded caption/read contracts use 900-token initial caps and one bounded 1800-token retry; prompts request at most three prioritized items; legacy caps and ordinary retries remain unchanged. Mock-only spike suite: 127 passed. Both changed spike files pass bare `ruff check` and bare `ruff format --check`. See `ledgers/CONTINUITY_grounded-num-predict.md`.
- Full Circle incident-response runbook FC-TF3 complete (2026-07-23): added the operator playbook at `docs/runbooks/incident-response.md` with FC-B1/B2/B3/TF1/TF2 scenario coverage, PII-safe evidence queries, Azure containment/immutable rollback, suppression gap and reactivation handling, controlled recovery, and known operational gaps. Validation: 95 focused backend tests, Ruff check/format, one Alembic `tf02` head, shell syntax, Markdown links, and adversarial account/suppression/operations reviews all pass.
- iOS crash/cold-start diagnostic complete (2026-07-15): no AcademyWatch crash artifact exists locally, in synced phone reports, or in the connected device crash-log domain; the prior Xcode device run also completed successfully. Confirmed UX cause was the known 29.716s first-run backend wait presented as generic loading, amplified under LLDB (1.516s standalone-cached versus 5.180s debug-cached). Added delayed server-wake/elapsed feedback including the empty-cache edge; schema-mismatch cache and unavailable-Keychain regressions pass; XcodeGen/build and all 55 tests pass; fresh-install waiting screenshot captured; signed device reinstall succeeded, with best-effort launch blocked only because MJ's iPhone was locked. PR #634 delivery follows from `ledgers/CONTINUITY_ios-coldstart-diagnostic.md`.
- iOS P4b branding + device refresh complete (2026-07-15): replaced the placeholder with a cropped full-bleed winged-boot icon; added the matching storyboard-free launch screen; fixed decision-free standard-XXL truncation; XcodeGen/build and all 51 tests pass; simulator icon/launch evidence captured; signed physical-device build/install succeeded, with launch blocked only because MJ's iPhone was locked. This closes iOS P4 implementation for PR #634.
- iOS P4a launch performance complete (2026-07-15): verified Scout players/leaderboards were already concurrent; added schema-v1 SWR disk caches, independent cached-data refresh indicators, app-start health warm-up, and DEBUG launch timings. Simulator time-to-first-row improved from 29.716s network-cold to 1.953s from disk cache; XcodeGen/build and all 51 tests pass; cached-launch screenshot captured.
- iOS physical-device first look confirmed working by MJ; automatic signing committed/pushed as `a28d5df` (2026-07-15).
- iOS `feat/ios-app` review fix round complete (2026-07-15): all 11 verified findings fixed; XcodeGen + build + unsigned archive pass; 45 tests pass; two dark-mode screenshots visually verified.
- iOS `feat/ios-app` adversarial review complete (2026-07-15): baseline build + 35 tests pass; verdict FIX-FIRST with 9 major and 2 minor confirmed findings; app source unchanged.
- Grassroots Program Funding F2 (2026-07-15): guarded `gf01`, league admission,
  club claim/verification grants, test-only US Connect scaffold, save/demand, and
  admin/public web surfaces shipped on `feat/funding-registry` at `d53b3c4`; PR #636
  is open with 143 focused backend tests plus all local and GitHub CI gates green. See
  `ledgers/CONTINUITY_grassroots-funding.md`.
- Native iOS app P3 (2026-07-15): public player-detail Talent Showcase with horizontal in-app YouTube reel, separate `Self-reported` profile and `Club-verified` Film Room evidence tiers, serializer-shape fixture decoding, 35/35 tests, and fixture-labeled simulator evidence because production returned no showcase content; no public discovery/list endpoint exists. Commit `b26af57` on `feat/ios-app`. See `ledgers/CONTINUITY_ios-app.md`.
- Native iOS app P1a (2026-07-14): phase-of-play browse, server-side filters/sorts, per-phase stats and leaderboard boards, debounced search, cancellation-safe pagination, live GK fixture and state-reset tests, five-phase simulator validation, four screenshots; commit `7873c2b` on `feat/ios-app`. See `ledgers/CONTINUITY_ios-app.md`.
- Native iOS app P0 (2026-07-14): iOS 17 SwiftUI/XcodeGen project, injectable Scout API client/models, live paginated Scout Desk, real-response fixture test, simulator screenshot; commit `488ed6b` on `feat/ios-app`. See `ledgers/CONTINUITY_ios-app.md`.
- PR #615 `fix(stats)` guarded merge/deploy (2026-07-14): squash `ab55d0a`; Deploy run `29327051534` succeeded; backend health healthy; Azure revision `r327-1` Running/Healthy with 100% traffic.
- Frontend dependency security (2026-07-16): PR #641 merged as `9daa0c1`;
  dependency restores are frozen-lockfile and OSV gated, both post-merge deploy
  workflows succeeded, Azure revision `r331-1` is ready, and live health is
  healthy. See `ledgers/CONTINUITY_frontend-dependency-security.md`.
- Agent workflow setup (AGENTS.md, Ralph scripts, ledger structure)
- Agent protocol integration into CLAUDE.md
- "The Academy Watch" refactor planning and analysis
- Phase 1: Foundation (Stripe removal, branding, pathway columns)
- Phase 2: Community Takes (complete)
  - CommunityTake and QuickTakeSubmission models + migration
  - Public submission API with rate limiting
  - Admin curation endpoints (approve/reject/create/stats)
  - AdminCuration dashboard page
  - QuickTakeForm component and /submit-take page
  - Newsletter template integration (shows approved takes)
  - Submit take CTA in newsletter footer
- Phase 3: Reddit Integration (skipped - no API access)
- Phase 4: Academy Tracking (complete)
  - AcademyLeague and AcademyAppearance models + migration
  - Academy sync service (fetches fixtures, lineups, events)
  - Admin API endpoints for league management and sync
  - AdminAcademy dashboard page
  - Academy section in newsletter template
  - Limited data handling (Started/Sub badges, G+A when available)
  - 4.8: Pathway progression UI in AdminLoans (status/level editing, badges, filters)
- Phase 5: Polish & Launch (in progress)
  - 5.1: E2E tests for Academy Watch features (complete)
    - `e2e/academy-watch.spec.js` - tests for SubmitTake, AdminCuration, AdminAcademy, pathway status
    - Database helpers in `e2e/helpers/db.js` for test cleanup
  - 5.4: Security review for `/community-takes/submit` (complete)
    - Flask-Limiter decorators (10/min, 30/hour)
    - Input sanitization via bleach
    - Email format validation
    - Duplicate content detection (24h window)
- Cohort ingestion remediation (implementation complete)
  - Dynamic API-Football youth league resolution with static fallback defaults
  - Dynamic parent-club -> youth-team ID resolution for seeding combos
  - Full Rebuild stage-2 academy league rows now seeded/updated from dynamic resolver
  - Cohort discovery now supports separate query team ID (`query_team_api_id`)
  - Sync-state hardening for `journey_synced` and cohort `complete/partial/failed/no_data`
  - Phase 2 journey sync timeout isolation added (`PLAYER_SYNC_TIMEOUT=90`) with per-player skip on timeout
  - Constrained live rebuild smoke run passed (`team=49`, `league=696`, `season=2022`): 1 cohort, 40/40 players synced
  - Targeted tests passed (`test_youth_competition_resolver.py`)

### Now
- **2026-09-02 Coach's brief B1 fixture bridge delivered in PR #975 (open, unmerged):** guarded/idempotent backend CLI + SQLite harness complete; requested bridge/club-console tests 53 passed; backend-wide Ruff check/format clean. No basecamp/prod execution. See `ledgers/CONTINUITY_dev-club-fixture-bridge.md`.
- **2026-09-02 grounded Ollama JSON Schema delivered in PR #972; review round complete:** schemas build once outside retries and inline definitions; bench schema is JSON-mode-parity; docs/tests/ledger tightened. Mock-only spike suite: 155 passed; six spike files pass bare Ruff check/format. See `ledgers/CONTINUITY_grounded-json-schema-format.md`.
- **2026-09-02 grounded caption enum prompt review fix applied; PR #970 awaiting merge:** grounded-only placeholder examples/instructions plus set-based deterministic single-choice recovery; 138 spike tests and both bare Ruff checks pass. See `ledgers/CONTINUITY_grounded-caption-enum-prompt.md`.
- **2026-09-02 S1 SHIPPED (evening) — "one player universe + a games grain" → 59.8%.** Five PRs live: #963 P1 games grain
  (`player_match_entries` + `showcase_moderation_events`, migration `pm01` pre-applied + stamped; owner CRUD; user/club rollup feeders),
  #965 P2 local players join the universe (negative synthetic ids, approval mint, signed routes, no-upstream guards, scout union +
  `source` filter + provenance, link-api), #968 P3 club results + lineups (program-scoped identity), #964 P4 web (add a game, provenance
  chips, scout source filter, club record-result dialog), #969 P5 trust-tiered auto-approval + graduation re-key + backfill. Prod env:
  `SCOUT_INCLUDE_LOCAL_PLAYERS=1`, `SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS=14`. MJ: rotated Mailgun (synced to KV), approved deleting the 3
  orphan negative players rows (done). Hygiene sweep S1-E in flight. Ledger `ledgers/CONTINUITY_dream-s1.md`. NEXT: S2 fans + reach.
- **2026-09-02 DREAM SCORECARD + S0 SHIPPED (Fable orchestrating; codex ultra builds; Fable-subagent adversarial checks; bot reviews read).**
  Scorecard `ledgers/GRADING_dream-scorecard-2026-09-02.md`: baseline **Built 51.9% / Lived ~0%** (prod: 9 accounts [5 team], 1 claim, 0 clubs,
  0 intros, $0). Evidence `ledgers/research/dream-scorecard-2026-09-02.json` (baseline + post_s0). **S0 'unbreak the front door' DONE + LIVE
  same day → 54.1%**: #957 A (web self-claim 400 fixed, D1 adult gate, `local_players.birth_date` lp01 pre-applied+stamped), #958 C (weekly
  scout digest job + API budget; ACA `job-scout-digest` Mon 07:00 UTC created, boot-proven; deploy loop now refreshes job-video-maintenance),
  #960 D (web account delete/export + report controls; dead journalist Stripe box removed), #961 E (hygiene: minor-DOB minimisation,
  SCOUT_DIGEST_DRY_RUN, dynamic head test, playwright cwd, dead /stripe calls, docs RG/FQDN, playwright-report untracked), #959 B (club-official
  approval → console grant bridge; hijack guard; console league locked; self-serve funding adoption; merged-club identity). Prod r409-1 healthy.
  Ledger `ledgers/CONTINUITY_dream-s0.md` (incl. incident: TaskStop cascade killed a codex run — resumed from WIP). MJ TO-DOs: rotate the
  inline MAILGUN_API_KEY (exposed to a local codex log, scrubbed) then update KV `job-scout-digest-mailgun-api-key`; decide S1 D2 (show
  self-reported stats on the scout desk with a provenance chip? recommended yes). Follow-ups: MyClub 'funding review pending' notice; adoption
  for proposed leagues + local console programs; iOS local-create birth_date; paid-subscriber cancel/billing-portal route; upload attestation.
  NEXT: S1 one player universe + games grain (`ledgers/DIRECTIVE_phase1-user-fed-data.md`).
- **2026-09-01 (day) W4 PROOF LOOP + EVIDENCE BENCH (Fable orchestrating; codex building).**
  Basecamp battery died overnight (hard power-off ~00:10; MJ confirmed) → back 07:22; launchd
  agents self-restored; nightly script hardened with pg_isready retries (basecamp `40aae65`).
  **PR #924 `fix/analysis-hollow-notes` OPEN, merge HELD for live proof** — commits: W4(c) hollow
  notes rejected (`95be741`), separate aggregation timeout (`498027a`), **W4(d) per-player reads**
  (`a644a21`: one bounded call per uploader-side player w/ ≤3 frame images + that player's evidence,
  team pass on compacted stream, num_predict+repeat_penalty on every call, `QWEN_NOTES_SCOPE=ours|all`
  default ours — MJ-aligned product call), transient-connection retry (`737ab96`). Regen history on
  match 4: r2 succeeded w/ HOLLOW notes (25×`observations: []`) → r3/r4 failed honestly (monolithic
  aggregation: ~23k-token prompt at ~6 tok/s can't emit 25 grounded reads in 20 min; ollama log
  proved it, no truncation) → r5 killed by an ollama SIGTERM at 15:51 (a human-side LaunchAgent
  reload ended a days-long port fight between Ollama.app and launchd `ollama serve`; now ONE server,
  launchd, NUM_PARALLEL=2, MAX_LOADED=2, n_ctx 65536) → **r6 RUNNING** (job `4cb9edd1`, started
  15:54, frames healthy). Captions proven at the data layer: 53/150 reel windows match a caption
  under the exact client rule, all 13 players. **Evidence Bench**: directive
  `ledgers/DIRECTIVE_evidence-bench.md` (MJ D1=YES: `qwen3-vl:8b` pulled, `~/mlx-vlm-venv` +
  `mlx-community/Qwen3-VL-8B-Instruct-4bit` installed on basecamp); **PR #925 `feat/evidence-bench`
  OPEN** (E0: frozen 20-clip set from match 4 [gitignored `bench/frozen/`, 357 MB, synced to basecamp
  `~/Projects/loanarmy-bench-frozen/`], grounded-claim scorer, baseline + qwen3vl_ollama adapters,
  anchor-first anti-echo `08a6c79`, review round `dcf585f`: no truth interpolation across tracking
  gaps [10/20 tracks have gaps] + resume fingerprint). Research: `ledgers/research/hf-scouting-models-2026-09-01.md`.
  **r7 SUCCEEDED 20:02 JST (2h36m): 7 player notes, 0 hollow, all t=-grounded; red #9/#12 recorded as
  'no read produced' in honest_limits (model dropped the t= format twice) — PR #924 MERGED `3a22867`,
  PR #925 MERGED `254d13e` (review bot only ever reviews a PR's first commit — don't wait on re-reviews).
  Slowdown root cause (local-flows-20 diagnosis, confirmed): loanarmy callers omit num_ctx → auto 16k;
  PM flows ask 64k → runner reloads each switch; proposed server-side OLLAMA_CONTEXT_LENGTH=65536
  after E1. **E1 RUNNING on basecamp** (run_bench.py baseline → qwen3vl_ollama anchor-first, reports in
  `~/Projects/loanarmy-bench-reports/`, logs `~/e1-baseline.log` `~/e1-qwen3vl.log`; gemma held idle
  by local-flows-20 — MESSAGE IT when E1 is done).
  **E1 DONE 2026-09-02 ~00:30 JST: Qwen3-VL-8B 70% box-grounded (14/20 claims) at 16.5 s/clip vs
  today's flow 0% (no boxes) at 145 s** — record `ledgers/research/evidence-bench-2026-09-01.json`,
  review page https://claude.ai/code/artifact/ab0a131b-8c31-48c0-b889-d0eef56d845f. Four bench faults
  fixed first (PRs #927 thinking-field, #928 coord space, #929 0–1000 boxes, #930 box_t) after four
  wasted passes; #926 num_ctx pin merged; basecamp ollama now server-side 65536 (local-flows-20).
  D3 RECOMMENDATION pending MJ: adopt qwen3-vl for clip claims/captions with the box-grounded gate;
  keep qwen3.8 for per-player reads until benchmarked. Regen-7 analysis was also loaded into the
  LAPTOP dev DB (match 4) so MJ's app at :5173 shows the reads (backup in session scratchpad).
  **D3 = YES (MJ, 2026-09-02 ~01:00 JST: "i'm cool with qwen vl… tie this all together").** TIE-TOGETHER in
  flight — three parallel codex builds from e5dd581: A `.worktrees/tie-pipeline` feat/grounded-vl-pipeline
  (grounding.py shared with the bench; Qwen3-VL captions + reads, unverified claims withheld), B
  `.worktrees/tie-backend` feat/persisted-box-tracks (boxes blob at CV completion, video_boxes service, prod
  bbox route, context.json box_track/player_tracks/frame_size; migration after jk01 → PRE-APPLY to prod via
  pooler before merging B), C `.worktrees/tie-frontend` feat/verified-reel-notes. Shared contract text lives
  in the session briefs (scratchpad tie-*.md). ACCEPTANCE: merge A+B (+C) → pull basecamp → regen match 4 →
  sampling.grounding counters + reels show verified notes → deploy → MJ eyeballs one player. THEN: E2/E3,
  Xcode/S3a (W7).
  **02:xx JST: builds landed — B PR #936 (bx01 PRE-APPLIED to prod: jk01→bx01 ✓), A PR #937, C in
  `.worktrees/tie-frontend` (8f697bd + hygiene commit untracking test-results PNGs). NEW BLOCKER: OSV gate
  red for every PR — browserslist 4.28.2 (GHSA-73wf-gq98-2v4g, GHSA-c83g-rgw3-j3cx, fix 4.28.7) — surgical
  lockfile fix in flight on `fix/osv-browserslist` (mirror of #810's nanoid pin); merge it FIRST, then B → A → C.
  **02:4x–03:1x JST: ALL MERGED — #939 OSV fix `111e332`, B #936 `d0399a3`, A #937 `e559c88`, C #938
  `851d35e` (C also untracks test-results PNGs, gitignored). Deploys red on 'Build backend image in ACR':
  Dependabot #933 pydantic 2.13.5 w/o matching core → `pydantic_core` 2.46.4→2.46.5 fix **PR #940** (auto-merge
  armed; prod stuck on last good revision until it deploys). **Regen 8 RUNNING on basecamp** (job `8c2f470c`,
  main 851d35e: qwen3.8 frames → Qwen3-VL gated captions+reads; dev box tracks from tracks.npz).
  **07:5x JST: PR #940 MERGED `1a34505` → Deploy SUCCESS → prod r402-1 healthy (health/site 200, bbox route
  401-gated) — prod now carries B+A+C. Regen 8 had died at 05:48 on claim: basecamp seeded DB was at jk01
  while code expected bx01 (`UndefinedColumn boxes_blob_path`) — basecamp DB upgraded to bx01; nightly script
  now runs `flask db upgrade` before boot (basecamp `1da0bc7`); **regen 9 RUNNING** (job `7344c095`, 07:53).
  Nightly sim 03:30 JST ran fine (9/9 ok, 8 pass). A 07:41 qwen3.8 image call at num_ctx 16384 was NOT ours
  (flagged to local-flows-20 — likely their visual-QA grader).
  **09:00–10:00 JST DEPLOY-BROKEN INCIDENT (peer session loanarmy-ac flagged it):** stale Dependabot #832
  (standalone pydantic_core→2.48.0, Aug-10) auto-merged 20:58Z — 4 min after #940 — via auto-rebase + the
  always-armed `dependabot-auto-merge.yml` → main b537f78 unbuildable (pydantic 2.13.5 needs core 2.46.5).
  Prod untouched (GITHUB_TOKEN merges never trigger Deploy; the break would have surfaced on the next human
  merge). Fixed: **#941** (re-pin 2.46.5 + Dependabot `ignore` pydantic-core + py3.11 `pip install --dry-run`
  resolver step inside the REQUIRED "Backend Lint" check, 8–13 s cold) → deploy green, r403-1 Healthy;
  **#948** (same gate in deploy.yml `lint-backend`; `deploy-backend` now requires lint-backend success; ruff
  before resolver) merged 48d32ea. Fable-subagent reviewer + connector both clean. 14 open Dependabot PRs
  audited: none armed. Memory: `project_dependabot_backend_batch.md` (recurrence 3 mechanics).
  **REGEN 9 FINDING (09:50 JST, caption stage):** grounded captions on qwen3-vl:8b truncate at ~707–710 chars
  = `CAPTION_NUM_PREDICT=300` (set pre-grounding in #924); the grounded prompt asks an UNBOUNDED claims list
  (~200 tok/claim) and `ollama_chat` ignores Ollama's `done_reason: "length"`, so the single retry fails
  identically (3 of the first ~6 windows failed). Fix dispatched to codex (`.worktrees/caption-cap`,
  `fix/grounded-num-predict`: `OllamaOutputTruncated` + contract-sized caps + retry-once-bigger + "at most 3
  claims" bound; mocked tests only). Regen 9 SUCCEEDED 10:03 JST (2h10m): grounding 33/56 captions + 10/15 read
  observations verified, 4 captions failed (3 truncations + 1 bad action_type), 7 reads (qwen3-vl:8b) all with evidence,
  red #5/#7 'no read produced'; loaded into MJ's laptop match 4 (backup `scratchpad/mj-review/laptop-match4-qwen_analysis.backup-before-regen9.json`),
  Playwright-verified: #3 reel shows CARRY · RIGHT ZONE · VERIFIED ON PLAYER and NO VERIFIED NOTE marks. **PR #956 MERGED 9bb4f67**
  (Fable-subagent review: 3 SHOULD-FIX → fix round 5c4ace4: parse-before-truncation guard, pinned legacy caps, bare-ruff format; 127 spike tests).
  **regen 10 RUNNING** (job `8095562a`, launched 11:01 JST via `~/regen10-launch.sh` on basecamp — pulls main, `flask db upgrade`,
  enqueues a qwen_analysis job for match 4, pinned one-shot worker `VIDEO_JOB_ID`; log `~/regen10-grounded.log`). **Regen 10 SUCCEEDED 13:47 JST (2h46m — slower + 8 dropped frames vs 2: basecamp ollama reloaded the qwen3.8 runner ~29× in the
  window, one foreign caller at num_ctx=16384 vs our 65536 → reload thrash; NOT loanarmy-1b's sims, which ran SIM_GRADE=0):** 0 truncations (#956 proven), but 8/56 caption windows failed on VALIDATION
  (7× action_type not in vocabulary, 1× malformed claim) → 28/56 captions + 9/15 reads verified (regen 9: 33 + 10). Laptop match 4
  stays on regen 9 (richer). Fix dispatched to codex (`.worktrees/caption-enum`, fix/grounded-caption-lenient-enums: coerce unknown
  labels to 'unclear' + drop only the malformed claim + counters) → **PR #962 MERGED bea9ec6** (Fable-subagent review: no blockers;
  3 NITs logged as follow-ups: truncate `raw_value` in the label-coercion warnings like the claim path; add a negative test that
  `validate_analysis_schema` rejects a missing fault counter; fault counters can exceed persisted captions when a window fails
  AFTER parse — informational). Deploy 33592961596. **Regen 11 RUNNING** (job `e0c2a6c6`, 14:01 JST, `~/regen11-launch.sh`, log
  `~/regen11-grounded.log`) — expect 0 truncations, 0 validation failures, new `sampling.captions_*_coerced/claims_dropped` counters;
  **Regen 11 SUCCEEDED 16:41 JST (2h40m): 0 caption failures, 0 truncations, 7 labels coerced, 2 claims dropped singly → 32/56 captions
  + 9/15 reads verified, ALL 56 windows persisted (regen 9: 33 + 10 with 4 windows lost).** The 'invalid' labels were the model
  ECHOING the prompt's option string ('pass|carry|duel|…', 'carry|pass') → PR #970 (vocabularies as prose from the constants,
  concrete example values, exact-one-token recovery + `captions_action_type_recovered`). Laptop match 4 = regen 11; review page
  rebuilt with regens 9/10/11: https://claude.ai/code/artifact/f8dc710a-b4ba-495b-9665-da5cde7882c9. **Coach's-brief directive
  MERGED #966** (`ledgers/DIRECTIVE_coach-brief.md`, revised after a codex critique: 21 findings/11 blockers); decisions B1–B5
  pending MJ; nothing built yet. Ollama tax root cause (local-flows-20): a laptop-side image caller at num_ctx=16384 ~8/h
  alternated the qwen3.8 runner with ours (28 reloads/2h45m) → portfolio rule in ~/Projects/CLAUDE.md (omit num_ctx or pin 65536).
  then load into laptop match 4 + refresh the review artifact. Review page REBUILT from regen 9/10 (generator
  `scratchpad/mj-review/build_review.py <latest.json> [older.json]`): the old artifact ab0a131b was DELETED — new URL
  https://claude.ai/code/artifact/f8dc710a-b4ba-495b-9665-da5cde7882c9 (republish same path to update).
  **DIRECTION (MJ 2026-09-02 ~14:30 JST, "lets go with 1"): Coach's brief FIRST (club-scoped per-player/per-role expectations
  text → the question the read answers, reported expected-vs-seen under the same evidence gate; private by scope, never trains a
  shared model), positioning/calibration (E3) as the parallel long pole, merge signals (E2) as research alongside. Codex read-only
  recon in flight (`.worktrees/brief-recon`, log scratchpad/brief-recon-run.log) → Fable authors `ledgers/DIRECTIVE_coach-brief.md`. Ollama tax (local-flows-20 diagnosis): a laptop-side image caller
  sends qwen3.8 requests with num_ctx=16384 ~8/h all day → runner alternates 65536/16384 and reloads (28×/2h45m); portfolio
  convention proposed to MJ ('omit num_ctx or pin 65536'); not a loanarmy caller. Frames stage alone is ~1h47m — no resume support yet.
  NEXT (pre-D3 note): E2 merge challengers, E3 pitch keypoints (directive §4); Xcode/S3a still parked (W7).
  NEXT (superseded plan kept for context): r6 lands → verify non-hollow reads → post on #924 → merge #924 + #925 → E1 on basecamp
  (`run_bench.py --adapter baseline` then `--adapter qwen3vl_ollama`, 20 clips) → numbers into
  `ledgers/research/evidence-bench-<date>.json` → D3 decision. basecamp repo: filmroom-worker
  service committed `85a1a4e`.
- **2026-08-31 (night) DIRECTIVE EXECUTED: scouting-viewer completion — W1–W6 SHIPPED, W7/W8
  remain (Fable orchestrating; `ledgers/DIRECTIVE_scouting-viewer-completion.md`).**
  FIVE PRs merged + deployed same night, each with codex build → connector review → verified
  fix round → pre-merge sim regression (9/9) → deploy green (two deploy races resolved by
  rerunning the tip run after ContainerAppOperationInProgress — a known two-merge pattern):
  **#916 W1** (stall root-caused: spinner held by in-request `journey/map?sync=true` + sim
  screenshot race; render unblocked, journey hydrates async single-flight per player; sim step
  waits for the loaded-only marker, records load_ms), **#915 W2** (migration `jk01`
  pipeline_kind — PRE-APPLIED to prod via pooler before merge; kind-fenced claims; admin
  `/analyze`; fix round closed retention-race/provenance/failed-job-UX findings), **#917 W3**
  (club-scoped media tokens w/ club_program_id claim + serving-time check, club reel endpoint,
  read-only PlayerReel in MyClub, reopen re-fetch fix; Playwright allowed+denied), **#918 W4**
  (python-enforced recurring-pair player notes + dup rejection, boilerplate trim,
  strong-fragment thumbnails), **#919** (sim honesty: ok=false caps verdict at fail — found by
  the W6 seeded-defect drill which the OLD grader passed off a pretty screenshot).
  **W6 basecamp DONE** (sudo-free ~/homebrew route; launchd com.mj.postgres16 +
  com.mj.sim-loanarmy 03:30 JST; final acceptance: clean graded self-boot run 8 pass/0 fail,
  seeded-defect drill 2 caught as FAIL, basecamp repo 84c7cdf). **W5 LIVE on basecamp**
  (local-flows `sim-report-ingest` merged 55fcca1, launchd 04:15; real W1 concern = open
  docket event w/ report+screenshot paths; "app sim" card on the live dashboard; brief cites
  at 07:00). **W2 ops**: always-on `com.mj.filmroom-worker` installed (env chmod 600,
  KeepAlive+300s throttle); hands-free prod claim PROVEN (job 688d3d19 claimed+attempted 3×
  honestly). **⚠️ FOUND+REPAIRED: Azure consolidation deleted `stvideospike0610` (rg-video-spike)
  WITH the live prod video blobs** — matches 1–2 footage LOST (DB rows + analysis artifacts
  survive); repaired same night: `video-matches` container in `stnbhdprod`, `video-storage-conn`
  repointed, revision restarted, health 200; MJ option: Azure deleted-account recovery ~14-day
  window (see `~/Projects/CONTINUITY_azure-consolidation.md` regression note). Full worker E2E
  awaits fresh footage (next real upload just works). **W4(b) regen**: match-4 analysis job
  re-run on basecamp under the new prompt (job e73c214f; MJ eyeballs a reel when convenient).
  **Hygiene**: 56 verified-merged branches deleted; today's worktrees removed (reel-moments
  KEPT — MJ's servers, now behind main); sim reports preserved in checkout sim/report/; prod
  test match 2 KEPT as smoke fixture (footage gone, see above). REMAINING: W7 (S2 sautai/nbhd,
  S3 iOS, S4 harness pack), W8 R3 ladder (entry: a club actively using reels), cosmetic —
  #917 committed 2 Playwright PNGs (test-results/ not gitignored), /analyze 405s via SWA proxy
  (admin tooling hits the backend FQDN directly, works). Codex ops notes: account saturates
  ~5-6 concurrent runs; unquoted Azure conn strings break `source`-style env files (semicolons).
  Old checkpoint (superseded, kept for detail):
  **W1 stall triage DONE+PR'd**: root cause = PlayerPage held the full-page spinner through the
  on-demand `journey/map?sync=true` (a synchronous in-request API-Football journey sync,
  api.py:10550) whenever the cached journey-map call returned null, PLUS the sim step
  screenshotted before content (race both ways — one graded run "passed" in 20ms with the
  spinner still up). Fix: render after the 6 core calls; journey hydrates async;
  sim `open-player` waits for the loaded-only marker (flag button), fails on error state,
  records player_url+load_ms. **PR #916**; connector review found 1 real P1 (duplicate syncs
  across season changes — sync now single-flight per player), fix round in flight.
  **W2 pipeline-kind DONE+PR'd**: migration `jk01` (sw01→jk01, guarded) adds
  `video_analysis_jobs.pipeline_kind` default cv; process/requeue/load_artifacts stamp it;
  claims kind-filtered both paths; loop-mode analysis workers unlocked; new admin
  `POST /video/matches/<id>/analyze` (needs_tagging|finalized, no debit, 409 dup) + admin UI
  button. **PR #915**; connector found 3 real P2s (retention sweeps footage under active
  analysis jobs; finalize stamps qwen version into CV report provenance; failed analysis
  invisible in UI) — fix round in flight. Sim regression on the W2 stack: 9/9 ok.
  **W3 club-scoped reels**: codex building in `.worktrees/w3-club-reels` per Fable auth design
  (media token gains club_program_id claim; club-console mint+reel endpoints via
  require_club_manager+_club_match; bbox/crops accept admin OR match token w/ club check;
  read-only PlayerReel variant in MyClub). **W5 PM ingest**: codex building
  `flows/sim-report-ingest` in local-flows `.worktrees/sim-ingest` per
  `specs/DIRECTIVE_sim_report_ingest.md` (authored today). **W6 basecamp (D1 executed,
  sudo-free variant)**: Homebrew at ~/homebrew (box's no-sudo philosophy; /opt needs sudo) +
  postgresql@16 + corepack pnpm@10.4.1 + osv-scanner + real frontend deps (shim deleted) +
  playwright chromium; laptop `soccer_newsletter` seeded to basecamp pg16 (plain-SQL dump —
  PG17→16 needs --format=plain; dump taken mid-W2-test so it already carries jk01);
  minimal chmod-600 backend `.env` (dev SECRET_KEY/ADMIN_API_KEY + local DB + stub mode; NO
  mail/LLM keys so sims can't send real mail); **full self-boot GRADED sim run on basecamp
  PASSED: 6 pass/1 concern/0 fail** (concern = reel playhead — laptop-absolute artifact paths
  in capture_meta['local']; footage+v8 artifacts rsyncing to basecamp, then SQL path rewrite);
  launchd `com.mj.postgres16` (KeepAlive) + `com.mj.sim-loanarmy` (nightly 03:30 JST) LOADED,
  committed to basecamp repo `84c7cdf`. **Hygiene DONE**: 56 branches deleted (each verified
  tip==merged-PR-head via gh), stale worktrees removed (reel-moments KEPT — MJ's servers),
  sim reports preserved to main checkout sim/report/. Prod test match 2: KEEP as standing
  smoke fixture (directive recommendation adopted). W4 brief ready (scratchpad), dispatch
  next slot. Codex capacity note: account saturates ~5-6 concurrent runs (one kill+resume).
- **2026-08-31 FULL-CIRCLE WAVE AUDIT + QWEN-ANALYSIS FLOW (Fable orchestrating).**
  (1) MJ asked to "merge the full-circle wave" — audit found EVERY wave branch already
  squash-merged (17/19 branch tips == merged PR heads; `fix/transfer-resolver` `4127971`
  stays frozen/salvage-only per its ledger). One genuinely unmerged commit found:
  `fd37486` on `feat/season-d3` (the D3 reviewer's tie-break test, never PR'd) —
  salvaged as **PR #909, merged, Deploy green, health 200** (mutation-verified: flipping
  `_SOURCE_PRIORITY` fails only the new test). Stale wave branches left in place
  (deletion not requested). (2) **Basecamp qwen video-analysis flow IN FLIGHT** — see
  `ledgers/CONTINUITY_video-analysis.md` §basecamp-analysis: existing VideoAnalysisJob
  queue → basecamp worker → sandbox-exec'd ffmpeg decode → qwen3.8-27B vision (ollama,
  proven 13.1s/frame, honest empty jersey reads) → fenced `capture_meta['qwen_analysis']`
  persistence. codex building on `feat/qwen-video-analysis` (`.worktrees/qwen-analysis`);
  basecamp prepped (SSH `mjjones@100.82.160.117` via `ssh-add --apple-load-keychain`,
  clone pulled, `.loan` venv built); local dev DB repaired to head `sw01` (tre01 table
  was missing — created by hand, PG14 so no NULLS-NOT-DISTINCT; noted).
- **2026-08-10 C2 CLUB-CONSOLE HARDENING SHIPPED (Fable orchestrating; role
  split per MJ — codex develops + runs adversarial reviews, a Fable SUBAGENT
  checks, main Fable only ships once adversarial is clear; see memory
  feedback_fable_orchestration_division).** C2 (#822 `e5c5438`) was merged +
  deployed by the prior session WITH review gaps still open. This session ran an
  INDEPENDENT two-adversary review (codex + Fable) that caught them; codex fixed
  over 3 rounds; shipped as **PR #823 `a5acb80`**, Deploy success, revision
  **r365-1 Healthy/100%**, health 200, public showcase 200. Closed LIVE: F1
  public `_verified_footage` leak (club-console footage now excluded — a club
  could publish "verified footage" onto ANY tracked player's public profile
  incl. minors), F2 null/boundary-DOB minor (fail-closed private, both py+SQL
  branches), F5 emergency kill-switch on the CONSOLE (`platform_status='approved'`
  AND `emergency_hidden=false` AND claim approved), F6b media-approve suppression
  check, F4 upload/etag integrity (club+admin+requeue+worker `If-Match` pin, with
  null-legacy fallback so legacy null-etag jobs aren't bricked), F8 timeline
  bounds. No new migration (c201 already applied). **contact-rail kill-switch
  SHIPPED** (PR #824 `d3e6139`, deploy in progress) — 6 codex-attack + Fable-check
  rounds converged; an emergency-hidden OR suspended club is now frozen out of
  EVERY contact surface (participation, routing, inbox `box=club`, account export,
  consent tokens GET+POST, blocks, notices, courtesy) with `program_is_operational`
  (approved + not emergency_hidden) FOR-UPDATE lock+recheck inside each request
  txn; account display unchanged; no migration. Two LOW-severity irreducibles
  filed as follow-up (task #8): email transactional outbox for the ~ms notice
  check→send gap; `UserBlock` program-key migration for exact block provenance. **QUEUED: post-deploy prod audit** for bridged
  null-DOB local players (F2 fail-closed can hide a real player's public
  showcase — AUDIT DONE 2026-08-10: 0 affected (in fact 0 approved local players
  in prod), benign); **O3 web onboarding SHIPPED** (PR #825 `8d9aaa8`,
  fast-frontend deploy success, site + `/onboarding/player` = 200 — club_name on
  local-player create + "I'm a player"/"We're a club" entry points + first-sign-in
  prompt mirroring iOS); **C3 MyClub console web UI = SHIPPED + LIVE (2026-08-10)** — **PR #826
  squash-merged `b44fb0d`**, Deploy Frontend (fast) success, site + `/my-club`
  200, C3 strings confirmed in the live JS bundle. Full role-split loop ran:
  codex build (`ea5d6de`) → independent codex review (FIX-FIRST: 4 MAJOR incl.
  >5 GB single-Put-Blob upload defect + stale-draft `kickoff_s:null` clobber)
  → codex fix rounds `c73964d` + `c38f8ed` → Fable checker CLEAN (10 mocked
  Playwright visual scenarios incl. minor-privacy zero-anchors, no console
  flash on 403, per-program fall-through/switcher, preflight retry). Console:
  Roster / Matches & Reports / Club profile (read-only v1); eligibility
  preflight via manager-gated roster call; created match ids kept per browser
  in localStorage (`club-console:matches:v1:<program_id>`) because C2 has no
  match-list endpoint — **follow-up candidates**: backend match-list endpoint,
  console-flash-scope nuance (one errored program hidden from switcher while
  another renders — reload recovers). Ledger:
  `ledgers/CONTINUITY_club-console-c3.md`. **Task #9 SHIPPED same day — PR #827
  squash-merged `7daa26c`**, Deploy success, revision **r367-1 Running/100%**
  (ACR `:prod` digest 06:35 → revision 06:36 chain verified), health 200, logs
  clean. Adds the previously-MISSING club-claim decision email (approvals were
  silent!): approve/reject only, after-commit failure-tolerant hook mirroring
  the player-claim pattern, approval links `<PUBLIC_BASE_URL>/my-club`, autouse
  mail stub keeps local pytest from real Mailgun sends + commit-before-send
  ordering test (`45dd275`). iOS: "Manage your club on the web" CTA on approved
  claims via `LegalDestination.clubConsole` (excluded from Legal list,
  CaseIterable dropped), 2 stale "console coming" copy fixes, DEBUG-only
  `-onboardingFixture` fixture — **rides the next TestFlight build**. Review:
  codex SHIP + Fable checker CLEAN (iOS 135/135, backend 45/45, simulator CTA
  screenshot). Both club worktrees/branches cleaned up. **CLUB-PERSPECTIVE WAVE
  COMPLETE** (C2 #822/#823, kill-switch #824, O3 #825, C3 #826, connectors
  #827). Known LOW follow-ups filed in the C3 ledger + task #8 (email outbox,
  UserBlock migration): backend match-list endpoint, errored-program switcher
  nuance, email-service layering (imports `_club_reference_name` from routes).
- **2026-08-10 APP STORE SUBMISSION AUDIT (evidence-based, same session).**
  VERIFIED DONE in repo/prod: rail ON, EMAIL_POSTAL_ADDRESS set, privacy
  manifest 35F9.1 wired, ITSAppUsesNonExemptEncryption=false, in-app delete
  (double-confirm), 18+ copy, block+report on contact surfaces, legal links,
  icon/launch, metadata files ASO-clean (name 29c / subtitle 27c / keywords
  81c, zero repeats), 3.1.1 IAP exposure ZERO, zero goonloan refs in iOS.
  GAPS FOUND: (1) **NO ASC app record exists** (only nbhd/sautai/yardtalk;
  bundle id com.theacademywatch.app IS registered; creation = web-UI only,
  MJ manual); (2) **B4 residual** — no report affordance on PUBLIC showcase/
  profile content (reports only via contact surfaces; UGC 1.2 risk — MJ to
  decide fix-before-submit vs risk); (3) **review_notes.md inaccuracy** —
  claims report controls in Account (Account has only blocked-user mgmt) +
  credentials placeholder still unfilled; (4) prod `PUBLIC_BASE_URL` still
  `goonloan.com` (301s correctly to theacademywatch.com — cosmetic email fix);
  (5) REVIEW_LOGIN_ACCOUNTS unset — arming sequence mapped: env JSON
  `{"scout":{email,code},"player":{email,code}}` (auth.py:59) → idempotent
  `POST /api/auth/admin/review-accounts/seed` w/ admin key (auth_routes.py:258;
  seeds approved scout + demo team 2147160000 + demo player 2147160001 +
  approved free-agent claim) → verify codes → paste creds into review_notes.md.
  Review tokens: 24h TTL, reusable static codes, role forced to "user".
  docs/ios-app-store-readiness.md is STALE (predates #814/#816/#819/#821/#827).
  Remaining ASC-side: app record, category (Sports), age rating (17+/18+ per
  D1), privacy labels, screenshots, EU trader status decision, TestFlight
  build + two-role rehearsal, submit (manual release).
- **2026-08-10 SUBMISSION EXECUTION (Opus session; codex executes per
  [[feedback-codex-for-all-work]]).** DONE: prod env (PUBLIC_BASE_URL→
  theacademywatch.com, REVIEW_LOGIN_ACCOUNTS armed+seeded, both codes 200 vs
  /auth/verify-code); ASC app record created (id **6799866798**, sku
  academywatch-ios-001); metadata pushed (subtitle/desc/keywords/URLs/copyright);
  category **Sports**; age rating **18+** (messaging+UGC declared, ageAssurance
  false); price **Free**; availability **148 territories, EU-27 excluded** (no
  DSA trader blocker); **profile-report PR #828 `4a5e3a4` merged** (guideline
  1.2 — report affordance on public player profiles, iOS-only, backend already
  supported player_profile); **8 App Store screenshots uploaded** to the
  APP_IPHONE_67 6.9" set (id 6c118738…), all COMPLETE, conservatively
  regenerated so NO real player FACE photos + age-checked (all adults) — final
  PNGs in session scratchpad appstore-final/. **BLOCKED ON MJ (UI-only, cannot
  be API-driven):** (a) **privacy labels** — the ASC appDataUsages API does NOT
  exist (404, absent from official OpenAPI 4.4.1); MJ sets 3 in UI: Email
  Address / User ID / Other User Content, each Linked-to-user, NOT tracking,
  App Functionality; (b) **Xcode Cloud** — build can only run on Xcode Cloud
  (MJ), but the GitHub App can't see performlikemj/the-academy-watch (only
  nbhd-ios+sautai); MJ must grant the App Store Connect GitHub App repo access,
  THEN Opus creates ciProduct+workflow+build-run via API (first product may
  need one Xcode click). .xcodeproj IS committed; add ci_post_clone.sh
  (xcodegen, mirror nbhd) only if the first build needs it. Then: two-role
  rehearsal (MJ phone) + submit (MJ go, manual release).
- **2026-08-10 XCODE CLOUD LIVE.** MJ signed into Xcode + created the Xcode
  Cloud product (**AcademyWatch**, id 33fc042c…) + Default workflow (id
  6756B20E…). Build #1 SUCCEEDED but was a BUILD-only action (compile check) →
  0 TestFlight builds. Opus fixed via API: PATCHed the workflow BUILD→ARCHIVE
  with `buildDistributionAudience=APP_STORE_ELIGIBLE` (mirrored nbhd's proven
  action shape), triggered build run **#2** (id 6a50c729…, archives+delivers).
  Monitoring run→TestFlight VALID. NOTE: `/v1/apps/{id}/builds` rejects the
  `sort` param (400) — query without it. Repo is Xcode-Cloud-ready (shared
  scheme committed, .xcodeproj in sync). PRIVACY LABELS still MJ-UI (API has
  no appDataUsages): Email/Name/User ID/Other User Content, all Linked +
  not-tracking + App Functionality; codex data-inventory audit offered to
  confirm Name + email-marketing purpose.
- **FOLLOW-UP (MJ-approved 2026-08-10): iOS player photo upload gap.** Backend
  has a full pre-moderated player-photo pipeline (`PlayerShowcaseMedia`,
  "private until moderation") AND the WEB claim/curate UI uploads photos
  (`ShowcaseSection.jsx`: createShowcasePhoto→uploadPhotoToUrl→complete, +
  reorder/primary/delete). **iOS has NO photo-upload UI** (verified: no
  picker/camera/file import) — an iOS player must use the web to add a headshot;
  iOS only displays photos. Not a submission blocker (iOS binary collects no
  photos → "Photos or Videos" correctly UNCHECKED in the privacy label). Two
  options for later: (a) small iOS "add your photo on the web" CTA (mirror the
  club-console connector), or (b) native iOS upload reusing the moderated
  backend — (b) would add "Photos or Videos" to the iOS label + lean on the
  new profile-report path (#828) for moderation.
- **PRIVACY LABEL — codex data-inventory audit DONE 2026-08-10.** App collects
  MORE than the initial 3 (my first pass under-declared). Verified: NO
  analytics/diagnostics/crash SDK (zero 3rd-party iOS deps), NO device/ad id,
  NO tracking, NO iOS photo/video/audio/location-service/contacts/health.
  Recommended ASC set (all Tracking=No, Linked=Yes): Name, Email Address
  (+Developer's Marketing — Scout Digest newsletter default opt-in,
  scout_digest_service.py), User ID, Other User Content, Customer Support
  (reports/takedowns), Product Interaction, Search History (queries sent to
  backend+API-Football), Other Data Types (birth year/nationality/position/
  height/consent attestations). Two codex-conservative entries Fable flagged as
  judgment calls to SKIP: Coarse Location (manually-typed city ≠ device
  location; covered by Other Data) and Emails-or-Text-Messages (in-app DMs =
  Other User Content, not the user's external mail). Full report:
  scratchpad privacy-audit.log.
- **2026-08-10/11 SUBMISSION FIELDS DONE via API.** App Review Info written
  (detail id 0ff1ae07…): contact Michael Jones / 9082222528 /
  mj@bywayofmj.com, sign-in = scout review account + static code, 1105-char
  notes w/ both reviewer logins + test loop (codes live ONLY in ASC, not git).
  Promotional text set (145c, "Track academy players out on loan…reach players
  the right way"). Content Rights = YES. Build 6 (4c4a8c6f…, VALID,
  iOS-identical to build 2 — zero iOS diff, only Dependabot backend/frontend
  bumps between) attached to 1.0. **Xcode Cloud auto-build churn stopped**:
  Default workflow (6756B20E…) trigger repointed from `main` to sentinel branch
  `xcodecloud-manual-only` (ASC ignores branchStartCondition null-out;
  filesAndFoldersRule path-filter schema is JS-gated + unused by nbhd/sautai so
  not guessed — sentinel is the known-shape fix; workflow still enabled for
  manual/API build runs). REMAINING BEFORE SUBMIT (MJ): finish App Privacy
  labels (fuller list above) + save; phone rehearsal on TF build 6; then "Add
  for Review" (or Fable submits via API, manual release).
- **2026-08-11 WING LIFT LOADING SCREEN + REVIEW-DEBT ROUND.** MJ asked for a
  branded first-launch screen (empty Scout Desk read as broken). Design done by
  an **Opus subagent** (MJ explicitly requested Opus; design = brains work, not
  codex's lane): 3 logo-motion alternates → MJ picked **A "Wing Lift"**. Key
  finding: the app ALREADY ships a dark launch screen (`LaunchBackground`
  #1C1C1C + centered boot), so the card reuses the same color/size/position —
  launch image and first animated frame are one picture. MJ rejected recoloring
  the mark (claret) — logo stays white-on-dark in BOTH themes (also removes a
  luminance jump light-mode users already suffer). Shipped **PR #840 `6111b3d`**
  (launch art split into LaunchBootBody + WingA/B so feathers beat; staged copy
  via existing `initialLoadFeedback()`; light status bar; Reduce Motion).
  **⚠️ PROCESS FIX (MJ pointed it out): the `chatgpt-codex-connector` posts
  automated PR reviews on GitHub and Fable was NOT reading them — READ THEM
  BEFORE MERGING from now on.** They caught 4 real defects in already-merged
  work: (P1, was LIVE) the C3 console early-return hid club officials'
  affiliation-confirm/reject + vouch controls entirely; (P2) `new Date(YYYY-MM-DD)`
  showed match dates a day early west of UTC; (P2) one errored program hid the
  retry + switcher for a manager's other clubs (Fable's own checker had graded
  this a non-defect — codex was right); (P2) Wing Lift card also fired on
  mid-session filter changes, hiding nav+tab bars and trapping the user.
  ALL FIXED: **PR #841 `c9b3b90`** (card gated on a true-first-load flag that
  disarms on cached content too; + a duplicate-`initial-load-feedback` VoiceOver
  fix the review caught on the fix itself, read BEFORE merging; 140 tests) and
  **PR #842 `8b5f6b3`** (moderation restored as a 4th "Affiliations & vouches"
  console tab w/ pending badge, local date parsing, in-console retry for errored
  programs; Playwright-verified). Both deploys green; live bundle confirms the
  affiliations tab. NOTE: the connector does NOT review every PR (#827/#828/#842
  drew none) — don't block indefinitely, but always check.
- **2026-08-11 FULL WAVE RE-REVIEW (MJ-ordered: Codex Sol attacks, Fable
  subagent checks, main Fable arbitrates).** Two-lane verdict on the merged
  #840/#841/#842 wave: the 4 GitHub findings were ALL real and their fixes
  correct (checker: CHECK CLEAN, 140 tests + 5 Playwright scenarios), but the
  adversarial pass found **7 more defects (4 MAJOR/3 MINOR)** → both fixed and
  shipped same-day: **PR #843 `46a18ef`** (web: shared `src/lib/dateOnly.js` +
  full `new Date(` sweep — ShowcaseSection/TeamDetailPage/AdminShowcase/
  WriterDashboard/UniversalDatePicker converted, ~60 sites classified vs
  backend serializers; moderation tab hidden when `clubs:[]`; badge dedupe by
  unique ids; + micro-round `9fdb9a0` for the checker's 2 LOWs — newsletter
  field names `published_date`/`issue_date`, local-date picker presets) and
  **PR #844 `9cda8dc`** (iOS: card armed from first frame incl. before season
  fetch; 2.5s grace then tab-bar reveal — cold-start trap gone, design intact,
  card also gated on empty nav path; a11y modality via accessibilityHidden +
  hit-test disable; native @2x/@3x boot layers — recomposed union vs
  LaunchBoot@3x = 0/153,090 differing pixels, independently reproduced; season
  -delay hook fully #if DEBUG; 141 tests). Both deploys green, site 200.
  GitHub reviewer fired on neither round-2 PR (full window given). All wave
  worktrees cleaned. iOS improvements (Wing Lift + both fix rounds) ride the
  NEXT Xcode Cloud build — trigger one before TestFlight rehearsal/submission.
- **2026-08-11 🚀 APP STORE 1.0 SUBMITTED — WAITING_FOR_REVIEW with build 7,
  MANUAL release.** Sequence: MJ had self-submitted with build 6 (privacy
  labels done — ASC requires them to submit; that submission locked the
  version, explaining attach 409s). MJ chose the swap: canceled submission
  `e991e42f` → version unlocked (DEVELOPER_REJECTED) → attached **build 7**
  (`a5866626…`, Xcode Cloud run #7 off main `9cda8dc`, includes Wing Lift +
  both round-2 fix waves) → releaseType corrected AFTER_APPROVAL→**MANUAL**
  (MJ's recorded decision) → new submission `0e589eaf` submitted 13:59:30Z
  (first PATCH 500'd — Apple transient; retry succeeded). Workflow config now
  proper: auto-trigger = sentinel branch (Dependabot merges never build),
  `manualBranchStartCondition` = main (API-triggered builds allowed; needed —
  Apple 409s manual runs from branches not in a start condition). Local
  review-credential copy deleted (armed in prod env + ASC review detail).
  Ops note: `/v1/apps/{id}/builds` list is NOT date-sorted and rejects `sort`
  — match on version explicitly (a monitor false-fired on build 2). WATCH:
  App Review outcome; on approval MJ releases manually. Rehearsal on TF
  build 7 still worthwhile pre-approval (scout↔player loop).
- **⏸️ SESSION HANDOFF 2026-08-09 (break point — pick up in a new agent
  session).** Nothing half-merged; all work is on branches/PRs/disk.
  RESUME CHECKLIST for the next session:
  0. **C2 SHIPPED 2026-08-10** — PR #822 merged (main `e5c5438`), c201
     pre-applied to prod (RLS on club_roster_members), deploy green, health
     200, `/club/<id>/roster` 401-gated. Independent adversarial review
     (defensive-QA framing — the red-team wording tripped codex's guardrail,
     rephrase if reused) found 4 real gaps the author's tests missed →
     fixed + orchestrator-verified: **child-safety minor-bridge leak**
     (shared query-layer `without_minor_local_bridge` NOT-EXISTS across
     browse/leaderboards/compare/showcase/worldwide-search + conservative
     `birth_year >= current_year-18` boundary), suppression-recreate block,
     program-standing auth, capture_meta bound. Consent invariant + tenant
     isolation CONFIRMED. BACKLOG (not a C2 regression): real per-tenant RLS
     policies + non-superuser DB role — whole-DB posture, own project.
     NEXT in this wave: O3 web onboarding entry points; C3 MyClub console
     tabs (roster · matches & reports · club profile).
  1. ~~C2 club-console backend — COMMITTED + SELF-VERIFIED, needs
     independent review.~~ (DONE — see item 0) Resume completed clean (exit 0): commit
     `8d39814` on `feat/club-console-backend` (worktree
     `.claude/worktrees/club-console`, session
     `019fe6af-ecca-7a83-8534-127694e2190b`). Verified from its log: ruff
     check + format clean; failure set held at baseline (25 failed + 12
     errors, +17 NEW passing → 1526 vs 1509); migration `ob01→c201`
     (roster + club match video + local takedowns) applied AND downgrade
     proven on local pg (guarded, RLS enabled, subject-XOR constraint,
     downgrade-refusal guards); defense tests present + passing incl.
     `test_minor_local_player_is_flagged_private_and_hidden_from_public_and_scout`
     and `test_require_club_manager_denies_cross_program_pending_revoked_and_removed`.
     **STILL OWED (MJ quality bar): an INDEPENDENT adversarial review round**
     (a fresh codex/agent attacking C2's claimed defenses — Fence C
     consent-invariant, minor-privacy, cross-club IDOR, SAS/upload/quota
     race, report leakage) BEFORE it gets a PR. Then PR → pre-apply c201
     via aws-1 pooler → merge. Brief: scratchpad
     `club-console-backend-brief.md`; full self-report in
     `club-console-resume.log`.
  2. **O3 web onboarding** — NOT STARTED: web "I'm a player" / "We're a
     club" entry points + `club_name` on LocalPlayerCreate.jsx. Mirror O2.
  3. **C3 Club Console web UI** — after C2 merges (MyClub tabs: Roster ·
     Matches & Reports · Club profile).
  4. **E1 journey re-sync — ✅ DONE 2026-08-10 (execution ukw7mpg
     Succeeded).** 🚫 DO NOT start `job-status-refresh` again — this is
     complete. Verified: O. Harrison 394167 flipped stale "academy/no club"
     → AFC Wimbledon (loan captured, matches chelseafc.com); Gore 303010 +
     Amass 403064 hold first_team @ Man United (re-synced 08-10); ~2,481
     journeys refreshed. Minor follow-up (not blocking): Harrison's multiple
     parent-club rows split on_loan/left @ AFC Wimbledon — eyeball the
     multi-row status logic later; not a mislabel.
  5. **Secret rotation ROUND 2** (queued, do coordinated): Supabase pw +
     app secret-key + all 7 job envs leaked into Log Analytics via the
     corrupted job URI; MJ rotates API-Football key on the dashboard.
     VERIFY every job env value after (last rotation caused the sync-job
     corruption). See DATA-SOUNDNESS WAVE below.
  6. **App Store**: all code blockers done; remaining = flip nothing (rail
     already ON), arm REVIEW_LOGIN_ACCOUNTS + seed, TestFlight two-role
     rehearsal, screenshots, `asc` metadata push (files in
     `AppStore/metadata/`), submit.
  Handoff hygiene done: cached admin bearer/key deleted; phone build
  installed (dev-signed, 7-day). Build tokens minted from CONTAINER inline
  secrets (KV copies STALE, invariants §9); prod pooler host is **aws-1**.
- **2026-08-09 SELF-ONBOARDING WAVE (MJ during phone test: players must be
  able to say "I'm this player from this club/country and you're not
  tracking me"; clubs must announce themselves; scouts must be able to add
  untracked players). Fable design; the mechanics mostly EXIST buried:
  worldwide shadow follows (web Lists), LocalPlayer profiles w/ auto-claims
  (web LocalPlayerCreate), club claims (`POST /clubs/claim` + funding-F2
  registry/verification). Gaps: LocalPlayer has NO club field; iOS has NO
  creation UI for any of it; no identity-first entry points ("I'm a
  player" / "We're a club"). **O1 backend IN FLIGHT** (codex,
  `feat/self-onboarding-backend`, session `019fe698-d66b…`): lp-migration
  club_name on local_players + serializers/admin surfaces + verbatim
  contract audit of the 4 self-serve flows for the client rounds. THEN O2
  iOS (scout worldwide-add + local-player create + "I'm a player" routing
  incl. claim, + "We're a club" claim form) and O3 web (onboarding entry
  points + club_name on LocalPlayerCreate). A narrower ios-add-players run
  was stopped seconds in (no WIP) when MJ expanded scope; its brief is
  superseded.
- **2026-08-09 DATA-SOUNDNESS WAVE (MJ: "this year's data working" for prod
  phone test; quota refreshed — Pro 7.5k/day). AUDIT: 2026 fixtures were 31
  rows/1 FPS (vs 21k for 2025) — new season NEVER seeded + `job-sync-fixtures`
  FAILED daily since ~Aug 5. ROOT CAUSE: its SQLALCHEMY_DATABASE_URI was
  CORRUPTED during the 07-23 rotation (multiple KEY=value pairs swallowed
  into one env value → libpq "invalid sslmode"). **FIXED**: URI rebuilt
  clean (single quoted var), verified. Other 6 jobs scanned: clean.
  ⚠️ **SECRET EXPOSURE**: the corrupted value echoed into Log Analytics on
  every failed run — embedded API_FOOTBALL_KEY, **prod DB_PASSWORD (the
  rotated one)**, job SECRET_KEY (inert — app signs with the kvref literal,
  invariants §9). Azure-tenant-private, not public. ROTATION ROUND 2 needed
  AFTER this wave (coordinated: Supabase pw + app secret + 7 jobs, verify
  every job env value post-update — last rotation caused this). DONE SO
  FAR: leagues 2026 synced (16), teams 2026 synced (328 via admin
  endpoint, bearer minted from container inline secrets — KV copies are
  STALE per invariants §9), `job-sync-fixtures` manual run IN PROGRESS
  (execution glm5bl4). **glm5bl4 SUCCEEDED**: 2026 fixtures 31→843 (current
  through Aug 9), FPS 1→285, 2026 rollup totals 527→632 (hooks live); live
  Scout Desk now defaults to season 2026 with real leaders; the daily 05:00
  job is healthy again for continuous catch-up. **job-status-refresh
  (=E1/P3) RUNNING** (execution pjkyqju, watcher armed).
  **CONTACT_RAIL_ENABLED=1 LIVE ON PROD** (revision 0000508 healthy;
  /contact/requests 404→401) — first production enablement of the
  full-circle loop; ToS precondition satisfied. **E1 RUN 1 PARTIAL**:
  execution pjkyqju synced ~599 journeys in 1h then was killed by
  replicaTimeout=3600 (NOT an app error — logs healthy to the end); quota
  then ~7,333/7,500 spent (fixtures catch-up + E1). **replicaTimeout
  raised to 21600 (6h)**. **E1 RUN 2 ✅ SUCCEEDED 2026-08-10** (execution
  `job-status-refresh-ukw7mpg`; finished in one pass — API-Football ceiling
  now 150k/day, was 7.5k). 🚫 E1 COMPLETE — do NOT re-run job-status-refresh.
  CANARY VERIFIED: O. Harrison 394167 flipped stale "academy/no club" → AFC
  Wimbledon (loan now captured, matches chelseafc.com — full sync→classify→
  serve pipeline proven on a real correction); Gore 303010 + Amass 403064
  re-synced 08-10, still first_team @ Man United (deals not completed).
  ~2,481 journeys refreshed (E1 targets the active cohort, not all 5,916).
  Data is sound for MJ's prod phone test. Minor follow-up: Harrison's
  multi parent-club rows split on_loan/left @ Wimbledon — review multi-row
  status logic later (not a mislabel). **MJ PHONE: installed + launched** (Release build of
  main `a5ccce3`, prod backend, dev-signed 7 days; NOTE: must build with
  `DEVELOPER_DIR=~/Downloads/Xcode-beta.app/...` — stable Xcode 26.6 cannot
  drive the iOS 27-beta phone).
  CANARIES (web-cross-referenced 2026-08-09): **O. Harrison 394167
  (Chelsea) = stale "academy", reality = completed loan to AFC Wimbledon
  (chelseafc.com)** — must flip to on_loan; Gore/Amass/Collyer first_team @
  United = correct per Aug-7 reporting; H. Sands → Dulwich Hamlet likely
  below API coverage (honest gap OK). Admin session cached at scratchpad
  `.admin-session` (chmod 600, delete at wrap).
- **2026-08-09 iOS App Store readiness wave (Fable orchestrating, codex
  executing, ACTIVE):** MJ gave the GO on the code-blocker wave from the
  IR-1 audit (`docs/ios-app-store-readiness.md`, merged with #716).
  **Backend SHIPPED**: PR #716 merged `739c37e` (App Review login + user
  blocks + account-delete hardening + readiness doc; Fable-directed fix
  round `8ea4231` closed all 5 adversarial-review findings — bidirectional
  block enforcement, missing-table tolerance, revocation-at-token-load +
  24h review TTL, neutral 204 anti-enumeration). `ug01` pre-applied to prod
  via pooler BEFORE merge (alembic td01→ug01, RLS verified); deploy r356-1
  verified (health 200, /api/blocks 401-gated, review login inert until
  `REVIEW_LOGIN_ACCOUNTS` is set). NOTE: prod pooler host is
  **aws-1**-us-west-1 (not aws-0); container inline secret holds the
  rotated DB password (KV copy is STALE). **3-persona simulator QA DONE**
  (casual fan / scout / player, local stack, rail on): **17 PASS / 5 FAIL /
  2 BLOCKED** — full evidence-backed report at
  `ledgers/research/ios-persona-qa-2026-08-09.md` (screenshots in the ios-qa
  worktree scratchpad). Core loops PROVEN working: claim→approve→"scouts
  are watching"→introduction→accept→thread→report→outcome. FAILs: watchlist
  null-stats decode error, no compare availability toggle, attestation
  branch untested (free-agent path taken), no report-submitted feedback, no
  delete-account control (known B1). Also: Sent-Requests staleness,
  "Scout unverified" mislabel on player accounts, stale age render, QA env
  sent real Mailgun mails (2 admin notifications — harmless; future QA
  blanks email keys). **iOS blockers SHIPPED**: PR #814 merged `9ba2246`
  (all 12 items: B1 in-app delete w/ double-confirm, B6 privacy manifest
  reason 35F9.1, B7 18+ copy, attestation present-tense copy, S4
  encryption key, block UI on #716 backend, + all 6 QA defects; 124/124
  tests; simulator evidence reviewed incl. the delete flow). App-side
  punch list from the readiness audit is now CLOSED except the
  club-protection round. **Club-protection round SHIPPED**: PR #815
  merged `dec99f8`, deployed, health 200, rail verified still dark (MJ
  directive "scouts go through clubs wherever possible"). Fail-closed
  routing: direct contact ONLY when platform belief AND claim both say
  free agent (9-cell matrix pinned by tests; contradiction NEVER routes
  direct — closes the QA hole); contradiction + platform snapshot
  persisted schema-free in the created audit event; club_notified now
  sends a real club-registry notice + always-on admin audit notice;
  club_included operable via signed one-time grant/decline manager email
  links (14d expiry, single-use via request-state, neutral 404s; grant
  still requires player acceptance before messaging). Resolves audit
  precondition S2 for a rail-on submission. **CODE-BLOCKER WAVE
  COMPLETE.** **TRUST-DESK WAVE IN FLIGHT (MJ: "fill all these gaps"; Fable
  designed, codex executing):** T1 backend (`feat/trust-desk-backend`,
  session `019fe5c3-3391…`) — NEW admin contact-oversight endpoints
  (paginated list + detail w/ audit trail, NOT rail-gated), decision emails
  for scout verification + claims (failure-tolerant), uniform admin notice
  incl. ROUTING_DIRECT, reports serialization completeness. T2 iOS
  (`feat/player-story-completion`, session `019fe5c3-363a…`) — anti-scam
  banner on all threads, Account data-export via share sheet, in-app
  profile takedown request (neutral outcome). **TRUST-DESK WAVE COMPLETE
  2026-08-09**: T1 backend PR #817 merged `bd8238c` + deployed (health 200,
  oversight endpoint 401-gated); T2 iOS PR #816 merged `3eaa6fd` (128
  tests; takedown neutrality screenshot-verified); T3 web PR #818 merged
  `dc33990` + fast-frontend deploy success (Fable visual review with
  mocked admin: 3 tabs render, red Contradiction badge +
  contradictions-only filter, pending badge live). Backend requires
  non-empty notes on verification decisions + report resolutions (UI marks
  them required). Every verification queue now has a screen; decisions
  email applicants; all contact routes have admin oversight incl. audit
  timelines.
  **LEGAL LAYER SHIPPED + LIVE-VERIFIED 2026-08-09 (PR #819 `a5ccce3`)**:
  MJ decisions captured — entity **By Way of MJ LLC** (418 Broadway, Ste R,
  Albany, NY 12207), **New York law**, support **mj@bywayofmj.com**, report
  SLA **48h**, ASC name **"Football Scout: Academy Watch"**, **RAIL-ON
  submission scope confirmed**. Fable authored all four documents (July
  scratchpad draft was gone); codex built. LIVE + browser-verified on
  theacademywatch.com: /terms /privacy /community-rules /support render,
  footer links + cross-links navigate; iOS Account → Legal section
  screenshot-verified (rides TestFlight). `AppStore/metadata/` files
  committed (subtitle 27c, keywords 81c, zero overlaps; review_notes.md has
  a credentials placeholder). **EMAIL_POSTAL_ADDRESS set on prod (rev
  0000507)** — CAN-SPAM closed. REMAINING TO SUBMISSION (operator): flip
  `CONTACT_RAIL_ENABLED=1`, set REVIEW_LOGIN_ACCOUNTS + seed, TestFlight
  build + two-role rehearsal, screenshots, asc metadata push, submit
  (manual release). MJ: optional lawyer skim of the pages.
- **2026-08-09 seasons D5 wave (Fable orchestrating, codex executing, ACTIVE):**
  MJ re-activated seasons ("separate player data by season", admins + users,
  web AND iOS); web-first-then-iOS. **W1a backend SHIPPED + prod-verified**
  (PR #809 `64a33a8`, r353-1; /api/seasons live with 2007–2027 bounds;
  historical leaderboards/compare live; Gore compare canary matches anchor).
  Prereq **PR #810** (`c7485e8`) fixed the 2 HIGH OSV advisories (nanoid,
  brace-expansion) that had reddened ALL PR CI since 08-07. **W1b web
  frontend SHIPPED** (PR #811 `919648d`, fast-frontend deploy green) and
  **ALL FOUR `SEASON_ROLLUP_READS` flags now LIVE on prod** (revision
  0000505; stats envelope + teams envelope verified; prod-site Playwright
  check: Gore ?season=2024 renders totals + journey badge, no empty state).
  **Web side of the seasons vision is DONE**, then MJ-triggered UX polish
  round ALSO shipped (PR #812 `702ac54`: header-level Scout picker +
  "viewing X" subtitle, trigger truncation fix, cross-page season continuity
  via sessionStorage store, team roster per-season stat lines —
  prod-verified). **W2 iOS SHIPPED** (PR #813 `5b57545`: SeasonPicker, scout
  cache isolation, stats-envelope decoding w/ fallback, historical totals
  states; 116 tests; simulator evidence vs live prod reviewed) — rides the
  next TestFlight build. main = `5b57545`, prod backend rev 0000505 (all 4
  SEASON_ROLLUP_READS flags), health 200. Follow-ups queued in the seasons
  ledger: admin season lifecycle, E1/E2, /scout/players season echo, picker
  resolved-default cosmetic. Primary checkout fast-forwarded to origin/main
  this session. **See `ledgers/CONTINUITY_seasons-system.md` (D5 wave
  section).**
- **2026-07-24 season-prep wave (Fable orchestrating, codex executing):**
  MJ directive — two parallel codex tracks, Fable monitors. (A) **W1
  transfer-cadence** on `feat/transfer-cadence` (wt transfer-cadence, session
  019f9433-f774): replace the quota-killing DAILY in-window full resync
  (job-transfer-heal cron 03:00 UTC — confirmed cause of 07-23 quota
  exhaustion) with delta-first ingestion: daily ~1-call/team transfers diff →
  flag → budget-capped targeted resync (TRANSFER_SYNC_DAILY_BUDGET), weekly
  Mon/Wed/Fri tranche sweeps, deadline-week escalation; az cron change
  proposed-not-executed (Fable runs it post-merge). (B) **IR-1 iOS App Store
  readiness** on `docs/ios-readiness` (wt ios-readiness, session
  019f9433-fb46): evidence-based assessment → docs/ios-app-store-readiness.md
  — user-story completeness matrix (scout + player, live vs dark vs missing),
  guideline gaps (5.1.1(v) in-app account deletion, UGC block, privacy
  labels, passwordless-login REVIEW ACCOUNT problem, dark-rail submission
  timing), ordered punch list. Dual watchdog armed. STANDING: P3 status
  re-sync awaits quota headroom (do NOT run alongside W1 testing; fold into
  new cadence once W1 merges); PRs #698 (Transfer Desk) + #699 (P5 tests)
  await MJ review; ToS wiring queued; email/LLM key rotation awaiting MJ.
- **2026-07-23 close-out wave RESULTS (Fable):** password rotation DONE+verified
  (app secret + 7 jobs incl. URI-embedded copies; NEW exposure flagged by TF3
  research: Mailgun/SMTP/OpenRouter values seen in local tool output — rotation
  pending MJ authorization). Runbook merged (#696 → main; MJ to fill 2 contact
  placeholders). **ALL FEATURE PRs MERGED**: #635 roles → #636 funding F2
  (fix-round + account_roles superset resolution + PR-sync close/reopen lever)
  → #637 showcase P2 (round-2 merge, shp01→gf01). Prod migrations applied by
  Fable via pooler: head **shp05**. All 3 deploys green; r344-1 100% traffic;
  smoke 200/200/202. ToS draft APPROVED by MJ ("looks good"); LLC formation
  contemplated — wiring task queued (entity name via config placeholder, page
  ships dark until LLC papers). IN FLIGHT: FC-T1 Transfer Desk build
  (transfer-desk wt), contact-suite test-isolation hygiene (funding-f2 wt,
  branch test/contact-suite-isolation), P1 dry-run e6mrpzi (watcher armed).
  GitHub quirk logged: PR head-sync sticks after external branch pushes —
  close/reopen re-fires it (#654, #636, #637 all needed it). API-Football
  daily quota EXHAUSTED today — SKIP_API_HANDSHAKE=1 required for off-container
  flask commands until reset.
- **Close-out ops wave (2026-07-23, Fable)** — MJ directives executed: ToS
  DRAFT v1 authored (scratchpad `tos-draft-v1.md`, awaiting MJ/counsel pass →
  then codex wires page+acceptance → then flag flip); funding-stack
  integration round 1 dispatched to codex (fix #635 main-conflicts, merge
  main + re-point gf01→tf02 on #636; round 2 = shp01→gf01 on #637 AFTER #636
  merges); **P1 prod repair APPROVED by MJ ("fully remediated")** — ACA job
  `job-data-fix` Phase 3 dry-run execution `6c53xp9` running (gauge=126
  confirmed pre-repair), real run + P3 (`job-status-refresh`) + P5 tests to
  follow; TF3 runbook codex run active in full-circle worktree.
  CORRECTIONS from grounding: **Aug-1 rollover guard ALREADY SHIPPED** (seasons
  PR #589, 2026-07-07) — deadline met; **released-status mislabel ALREADY
  FIXED+repaired** (PRs #508–#514, June 2026) — both memory/ledger entries
  were stale, now corrected. NEW: `ledgers/CONTINUITY_transfer-desk.md` (FC-T1
  incremental manual transfer entry — spec ready, dispatch queued). Password
  rotation: staging commands handed to MJ, awaiting his staged file.
- **Full Circle build (2026-07-16, ACTIVE)** — MJ directive: marketplace loop
  (scout verification → intro requests → player response → outcomes) with the
  iOS app built out as the full-circle surface; **executor = actual Codex CLI
  (Sol), Fable orchestrates/reviews at intervals**. **SHIPPED TO PROD
  2026-07-20**: merge train landed — #645 (trust prereqs), #660 (contact rail,
  recreated from #651 after GitHub closed it on base deletion), #653 (D6
  routing), #654 (TF1 DSR + TF2 takedown/suppression), #634 (iOS app
  P0→FC-I3a). main `be02736`, revision r339-1 healthy, image==main verified.
  Prod migrations tre01→**tf02** applied via pooler by Fable; live smoke:
  health 200, takedown 202, contact 404 (dark), verification/export 401.
  `CONTACT_RAIL_ENABLED` stays OFF until ToS (MJ). REMAINING: TF3 runbook PR
  (queued, branch docs/incident-runbook), **#636 MUST re-point gf01
  down_revision → tf02 before merge**, ToS (MJ), password rotation (MJ-awake),
  Aug 1 rollover guard (ownership call). ⚠️ local dev Postgres now at tf02.
  @owner:Fable — see **`ledgers/CONTINUITY_full-circle.md`**.
- **Platform priorities roadmap (2026-07-16)** — six-perspective vision-gap
  panel (48 findings) arbitrated into **`ledgers/ROADMAP_vision-gaps.md`**:
  adults-only-participation launch (D1, confirmed in principle), Film Room
  club-attestation posture (D2, confirmed in principle), donation fee →
  optional tip (D3, open), club-bundle beachhead (D4, open), iOS-paused D5
  superseded — iOS full-circle build is active. Raw panel evidence in
  `ledgers/research/vision-gap-panel-2026-07-16.json`.
- **Transfer resolver remediation (2026-07-16)** — Hall-class stale-loan bug is
  shipped through PR #642 as authoritative `main` `f043c27`. The separate local
  scratch commit `4127971` contains a larger post-ship audit/test delta; it is
  frozen, must not be force-pushed, and is salvage-only evidence for a clean
  follow-up based on `f043c27`. Fable is the sole resolver-domain orchestrator
  for that extraction. `/root` will not edit the scratch worktree further. See
  `ledgers/CONTINUITY_transfer-resolver.md`.
- **Seasons system (2026-07-07, MJ-approved)** — multi-season stats + player-development views; Phase A (foundation, absorbs P0/P4/P2 below) + Phase B (discovery) running as subagent workflows — **see `ledgers/CONTINUITY_seasons-system.md`** (master ledger; pickup instructions inside)
- **Scout/profile stat-attribution bug (2026-07-07)** — diagnosed systemically (126 zero-compute / 141 wrong-club / 1,264 NULL current-club active rows; Gore = orphaned inactive academy row + loan-return override + reads keyed on current_club_api_id). Remediation designed — P0/P4/P2 in-progress under seasons Phase A; P1/P3 prod repair awaiting MJ go-ahead — **see `ledgers/CONTINUITY_scout-data-attribution.md`**. P4 rollover guard needed **before Aug 1**.
- Player Journey feature (complete - needs migration and testing)
  - Interactive map showing career path from academy to first team
  - `PlayerJourney`, `PlayerJourneyEntry`, `ClubLocation` models
  - `JourneySyncService` - fetches from API-Football, classifies levels
  - 50+ major club coordinates seeded
  - `JourneyMap.jsx` component with Leaflet
  - `JourneyTimeline.jsx` fallback component
  - Integrated into PlayerPage with new "Journey" tab
  - E2E tests: `e2e/journey.spec.js`
  - Backend tests: `tests/test_journey.py`
- **See `ledgers/ACADEMY_WATCH_IMPLEMENTATION_PLAN.md` for detailed status**
- Cohort ingestion remediation (in progress)
  - Validate full multi-team Full Rebuild in deployed container with timeout telemetry
  - **See `ledgers/CONTINUITY_cohort-dynamic-resolution.md`**
- Match Video Analysis feature ("Film Room") — design complete (2026-06-10)
  - Upload match video → GPU CV pipeline → human tag review → per-player reports; pay-per-match credits
  - Stack: RF-DETR + BoT-SORT (roboflow/trackers) + SigLIP team clustering + own pitch-keypoint model
    (Apache/MIT only — ultralytics YOLOv8 is AGPL, banned from serving path)
  - Infra: ACA serverless GPU (T4) Jobs + Service Bus; COGS ≤$3.50/match; price $25/match, floor $13
  - v1 = own-team player reports only (minors/GDPR); opposition stays anonymous
  - Phase 0 validation spike is the gate; task 0.1 (acquire grassroots footage) is `ready`
  - **See `ledgers/CONTINUITY_video-analysis.md`**
- Global Talent Platform — Scout discovery + footprint expansion (2026-06-12)
  - Goal set via /goal: #1 resource for up-and-coming talent worldwide
  - Supported-league config now global (16 leagues, 4 regions) with separate
    `CRAWL_LEAGUE_IDS` control so API quota stays explicit (default top-5)
  - New public Scout API: `/api/scout/players` (browse/filter/sort),
    `/api/scout/leaderboards`, `/api/scout/compare` — SQL-aggregated stats
  - New `/scout` frontend page ("The Scout Desk"): leaderboards, filterable
    ranked table with last-5 form bars, up-to-4-player comparison
  - Injury/availability tracking (API-Football injuries endpoint, previously
    unused): `/api/players/<id>/availability` + PlayerPage card + compare
  - Region-aware Teams page (league_api_id-keyed grouping); Home copy global
  - Scout workspace (slice 3, migration aw15): per-user watchlists with notes,
    weekly digest email (admin-triggered, cursor-paged, dry-run previews),
    CSV export, /pricing page with scout_tier entitlement scaffold (billing
    wiring deferred to MJ's pricing decisions)
  - Newsletter rebuild (slice 4, migration aw16): academy players in the
    weekly report for the first time (payload + agent instructions); email
    rewritten — 132KB→77KB (Gmail clip-safe), Outlook-safe HTML/CSS data-viz,
    Squad Watch with real injury reasons, Academy Watch from season stats;
    operator must set EMAIL_POSTAL_ADDRESS (CAN-SPAM)
  - Academy provenance enforcement (slice 5): prior-senior-career rule —
    clubs only track their OWN academy products (Malacia fixed); owning-club
    rows removed; repair endpoints (recompute-academy, backfill-names) ran
    locally: 221 misattributed rows deactivated, 1,128 placeholder names
    fixed; PROD: run both repair endpoints (dry_run first) after merge
  - Final-form provenance (slice 6): typing-layer precedence bug fixed
    (integration checks before development shield; buy-back + teenage
    guards); recompute re-types stored entries; profile completeness
    backfill (position/birth/age/nationality) + opt-in capped API fetch
    mode. Malacia entry now honestly 'integration', 0 active rows.
  - Academy tracking window (slice 7, 2026-06-13, migration aw18): platform
    now only tracks players in an academy NOW or within the past 4 seasons
    (utils/academy_window.py), enforced at journey upsert, recompute repair,
    rebuild/seed/GOL creation; scout API drops owning-club rows and derives
    age from birth_date in SQL (fixes U18/U21/U23 = 0 players in prod);
    recompute-academy now cursor-paged (fixes prod statement_timeout 500s)
  - Live-validated: 16 leagues + 335 teams synced; PR #419 green, awaiting MJ
  - Side-fix: PR #420 (merged) repaired Dependabot-corrupted pnpm-lock.yaml
    that was failing ALL frontend CI; react-hooks v7 rules pinned to warn
  - Branch `feature/global-scout-discovery`
  - **See `ledgers/CONTINUITY_global-talent-platform.md`**
- Talent Showcase — two-sided vision slice SHIPPED to branch (2026-07-02, /goal)
  - Vision: players worldwide get showcase profile pages (YouTube highlights,
    commentary, verified stats) for discoverability; clubs upload footage and
    get per-player stats (Film Room). Roadmap: P0→F0→P1→X sequencing.
  - This slice: P0 (Showcase section on PlayerPage: highlight reel from
    PlayerLink + newsletter yt merge) + P1 (claim & curate: user claims,
    admin approves, owner curates reel/bio — ALL owner content pre-moderated,
    self-reported vs verified hard-separated) + X (Film Room finalized
    reports → "Club-verified" appearance evidence on profiles; roster→player
    linking admin UI; only human_confirmed identities surface)
  - Migration aw19 (merge cs01+vid02 → single head restored; claims +
    showcase-profile tables + player_links.sort_order). aw19 upgrade verified
    on real Postgres clone; downgrade across merges needs explicit target.
  - Security: shared https-only URL validator; pre-existing
    submit_player_link javascript:-URL hole closed; newsletter yt merge
    filtered server-side.
  - Built multi-agent (Fable 5 orchestrator + Opus 4.8 builders), 6-surface
    recon, adversarial review (23 agents: 8 confirmed findings ALL fixed,
    1 refuted), 40 backend tests, live-verified end-to-end incl. UI screenshot
    (demo: player 403064 H. Amass — reel + profile + verified appearance).
  - Branch `feature/talent-showcase` (worktree) — PR opened, awaiting MJ
  - PROD OPERATOR STEPS after merge: flask db upgrade (aw19); vid03 (still
    uncommitted in the video branch) must rebase onto aw19 before it lands
  - Known pre-existing (NOT this slice): full migration chain cannot replay
    on an EMPTY DB (old unguarded supplemental_loans migration)
  - **See `ledgers/ROADMAP_talent-showcase-vision.md` + `docs/showcase.md`**
- Follow Graph + Shadow Tracking — Phase 1 SHIPPED to branch (2026-07-02)
  - Scouts organize tracking into named LISTS of FOLLOWS (kinds: player |
    academy_club | geo playing_in/nationality | saved query) — one resolver
    over the scout query engine; digest generalized ADDITIVELY (legacy
    watchlist section byte-identical; non-default lists render as grouped
    sections, watchlist-wins dedup; default lists are the watchlist's mirror
    twin and never route)
  - SHADOW TRACKING: following any untracked player worldwide mints a
    PlayerShadow (players/profiles fetch, seed fallback offline) + dedicated
    PlayerShadowStats (NOT PlayerStatsCache — unowned legacy, kept isolated);
    /players/<id> profile + season-stats shadow fallbacks; worldwide name
    search via new client method search_player_profiles_global; caps via env
    (10 lists / 50 follows / 10 shadows per user — billing later)
  - Migration aw20 (chains aw19, single head preserved). Watchlist backfill is
    a cursor-paged admin endpoint + dual-write mirrors, not a data migration
  - Adversarial review (21 agents): 8 confirmed findings ALL fixed — headline:
    the dual-write mirror was silently rerouting watchlist users onto the list
    digest path (grouped layout + ASC order + cap-40 truncation); redesigned to
    additive semantics with a REAL-API-path regression test (old test was
    blind: it seeded entries directly)
  - 164 backend tests green (test_scout_watchlist UNMODIFIED); ruff clean;
    lint 0 errors; live-verified incl. real worldwide search (Endrick shadow
    mint), digest dry-run (legacy user unchanged + grouped sections + "Now
    tracking worldwide" card), ListsPage screenshots
  - Branch `feature/follow-graph` STACKED on feature/talent-showcase —
    PR based on the showcase branch until #565 merges
  - LOCAL DEV DB note: cs01 columns (player_journeys.current_status etc.) were
    missing locally (never applied — DB stamped on vid chain); applied manually
    2026-07-02. Local scout browse had been broken since #514 merged.
  - **See `ledgers/research/talent-platform/` (design panel) + `docs/follow-graph.md`**

### Next
- Run migration: `flask db upgrade`
- Restore frontend deps only when required, from the frozen lockfile, and run
  the dependency-security gate described in
  `ledgers/CONTINUITY_frontend-dependency-security.md`.
- Seed club locations: `POST /api/admin/journey/seed-locations`
- Test journey sync: `POST /api/admin/journey/sync/284324` (Garnacho)
- Run E2E tests: `pnpm test:e2e`

## Task Map

```
CONTINUITY.md
  └─ ledgers/CONTINUITY_coach-brief.md (Track C/P/M directive workstream)
       └─ ledgers/CONTINUITY_dev-club-fixture-bridge.md (B1 complete; PR #975 open, @owner:/root)
  └─ ledgers/CONTINUITY_grounded-json-schema-format.md (review round complete; PR #972 open, @owner:/root)
  └─ ledgers/CONTINUITY_grounded-caption-enum-prompt.md (verified; PR delivery next, @owner:/root)
  └─ ledgers/CONTINUITY_grounded-caption-lenient-enums.md (complete; 131 tests + both spike files bare-Ruff clean, @owner:/root)
  └─ ledgers/CONTINUITY_grounded-num-predict.md (complete; 127 tests + both spike files bare-Ruff clean, @owner:/root)
  └─ ledgers/CONTINUITY_plan-incident-response-runbook.md (complete)
       ├─ ledgers/CONTINUITY_runbook-account-incidents.md (@owner:account-audit)
       ├─ ledgers/CONTINUITY_runbook-suppression-incidents.md (@owner:suppression-audit)
       └─ ledgers/CONTINUITY_runbook-operations-context.md (@owner:ops-context)
  └─ ledgers/CONTINUITY_seasons-system.md (Phase D3 merge/deploy complete; D4 next)
       └─ ledgers/CONTINUITY_merge-pr-615.md (@owner:/root; complete)
  └─ ledgers/CONTINUITY_plan-example.md (template - rename for actual work)
  └─ ledgers/CONTINUITY_cohort-dynamic-resolution.md (in-progress)
  └─ ledgers/CONTINUITY_video-analysis.md (design complete — Phase 0 ready)
  └─ ledgers/CONTINUITY_global-talent-platform.md (implementation complete — PR review)
```

## Active Ledgers

| Ledger | Status | Owner | Blockers |
|--------|--------|-------|----------|
| CONTINUITY_dev-club-fixture-bridge.md | B1 complete; PR #975 open | /root | none |
| CONTINUITY_grounded-json-schema-format.md | review round complete; PR #972 open | /root | none |
| CONTINUITY_grounded-caption-enum-prompt.md | verified; PR delivery next | /root | none |
| CONTINUITY_grounded-caption-lenient-enums.md | complete; both spike files bare-Ruff clean | /root | none |
| CONTINUITY_grounded-num-predict.md | complete; both spike files bare-Ruff clean | /root | none |
| CONTINUITY_plan-incident-response-runbook.md | complete | /root | none |
| ACADEMY_WATCH_REFACTOR_PLAN.md | complete | — | Phases 1-4 done |
| ACADEMY_WATCH_IMPLEMENTATION_PLAN.md | in-progress | — | Phases 1-5 done, Phase 6 ready |
| ACADEMY_WATCH_JOURNEY_REDESIGN.md | complete | — | Design doc for journey feature |
| CONTINUITY_seasons-system.md | Phase D3 merge/deploy complete; D4 next | MJ / Fable | D4 pilot/cutover gate |
| CONTINUITY_merge-pr-615.md | complete | /root | none |
| CONTINUITY_cohort-dynamic-resolution.md | in-progress | codex | pending live Full Rebuild validation |
| CONTINUITY_video-analysis.md | Phase A review loop SHIPPED (PR #567, prod 2026-07-02, vid03 applied) | claude | prod crop/bbox persistence + SWA CSP media-src follow-ups |
| CONTINUITY_global-talent-platform.md | shipped | claude | superseded by talent-platform-next |
| CONTINUITY_talent-platform-next.md | ACTIVE — #565/#566, analytics #568, pulse+cards #569 ALL LIVE (prod head aw22, r319-1) | claude | password rotation + Journalists-nav + Ecuador/Colombia quota + Phase-3 pricing pending MJ |
| CONTINUITY_admin-interface.md | shipped (PR #432, prod 2026-06-14) | claude | manual click-through QA recommended |

## Cross-task Blockers / Handoffs

- iOS cold-start diagnostic complete; scoped fix delivered with PR #634 (merged to main `be02736`).

## Trivial Log

- 2026-08-09: primary checkout fast-forwarded 167 commits (31f7dce Jul-16 → 809ca92 Aug-7). CONTINUITY.md reconciled: local uncommitted ledger state (Jul-16→Jul-24 sessions) kept as base, origin-only runbook/iOS-P4 entries folded in; pre-merge local copy backed up in the 2026-08-09 session scratchpad. NOTE: `ledgers/CONTINUITY_seasons-system.md` is still untracked/local-only — no other machine has it.
- 2026-07-08: Scout Desk phase-of-play views (feat/scout-phase-views). `?phase=all|attack|midfield|defense|gk` ToggleGroup on `/scout` swaps stat columns, sort options, default sort, and leaderboard cards per phase (filters to the matching position). Backend: `_fixture_stats_subquery` widened with 17 phase aggregates + derived duel-win%/Tkl-90/KP-90/GA-90/save%; 13 new sort keys (rate keys get the 270' floor); `?phase=` board sets on `/scout/leaderboards` (GK boards clamp to Goalkeeper). **GK stats (saves/GA/CS/pen-saved) are gated to per-fixture position='G' rows** — API-Football reports `conceded:0` for OUTFIELD appearances (87k prod rows), so ungated aggregates mint a phantom clean sheet per 60'+ outfield app (caught by 31-agent adversarial review; regression tests pin it). Phase stats are null (dash) for no-coverage players, never fake zeros. Companion PR `fix/fps-full-stat-block`: all 5 trimmed FPS writers unified on `utils/fixture_stats_mapper.py` so interceptions/blocks/pass-accuracy/dribbles (0% populated in prod — writer gap, raw_json only on 131 rows so NOT backfillable) start accruing; historical backfill would need an API re-sync (quota + invariants §7 — not scheduled).
- 2026-06-25: Scout page now reflects a player's ACTUAL current situation (matches PlayerPage). `scout.py._base_scout_query` outer-joins `player_journeys` (on unique `player_api_id`, ≤1 row) and exposes `effective_status = coalesce(journey.current_status, tracked_player.status)`; the status filter uses it so it never disagrees with the displayed badge. `_row_to_dict` + `scout_compare` override `status` and add `owner_team_id`/`owner_team_name` when `current_status` is set. `ScoutPage.jsx` CLUB column "from X" now prefers `owner_team_name` (e.g. Rijkhoff → "from Ajax", not "from Borussia Dortmund"). Tests: `TestCurrentSituationOverride` in `test_scout_blueprint.py` (38 pass).
- 2026-04-08: Added admin-only newsletter PDF download (WeasyPrint) — endpoint `GET /newsletters/<id>/download.pdf`, reuses existing `newsletter_email.html` template with injected print CSS (`@page`, `break-inside: avoid` on `.item`/`.highlights`/`.toc`/`.matches-section`, `break-before: page` on section `<h2>`s). Dockerfile gains libpango/libcairo/libgdk-pixbuf/shared-mime-info (~80MB). Download buttons in `AdminNewsletters.jsx` row actions and `NewsletterPreviewDialog.jsx` control panel. Plan file at `.claude/plans/staged-wibbling-cocoa.md`.
- 2026-02-12: Academy data audit — all Big 6 teams show 0% conversion due to journey sync never completing
- 2026-02-12: Fixed Full Rebuild journey sync: added RateLimiter, quota-exceeded break, non-fatal Stage 3, empty-journey bug fix
- 2026-02-12: Added Phase 2 journey sync timeout guard (`PLAYER_SYNC_TIMEOUT=90`) and verified a live constrained rebuild completes without hangs
- 2026-01-10: Fixed agent protocol - made AGENTS.md reading mandatory in CLAUDE.md

## Open Questions

- UNCONFIRMED: prior worker restarts were caused by health probe failure, OOM kill, or external restart policy.

## Working Set

**Key files:**
- `CLAUDE.md` - Claude Code instructions (auto-loaded)
- `AGENTS.md` - Agent operating protocol
- `scripts/ralph/` - Autonomous execution scripts
- `ledgers/` - Planning and task ledgers

**Useful commands:**
```bash
# Backend
cd academy-watch-backend && python src/main.py

# Frontend
cd academy-watch-frontend && pnpm dev

# Tests
cd academy-watch-frontend && pnpm test:e2e

# Ralph autonomous mode
./scripts/ralph/ralph.sh 25
```
