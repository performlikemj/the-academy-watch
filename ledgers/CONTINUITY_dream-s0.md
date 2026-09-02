# CONTINUITY — Dream roadmap S0: "Unbreak the front door"

Parent: `CONTINUITY.md` · Source: `ledgers/GRADING_dream-scorecard-2026-09-02.md` (Built 51.9% / Lived ~0%)
Owner: MJ (product) · Orchestrator: Fable · Executor: codex CLI (gpt-5.6-sol, ultra) · Started 2026-09-02

## Goal
Make it possible for a real player and a real club to get through the door without an admin hand-holding
each step, and stop the two safety/legal gaps the scorecard found. Target after S0: ~54% built (1.1→3, 2.1→3, 3.4→3).

## Packages (one codex run per worktree, disjoint files; merge order A → B → C → D, one PR at a time)

| Pkg | Branch / worktree | What | Status | PR |
|---|---|---|---|---|
| A | `fix/s0-player-claim-door` / `.worktrees/s0-claims` | Web self-claim sends `contract_status` (api.js:1403 ↔ showcase.py:479); D1 adult gate on local self-claims (birth_date ≥18 or birth_year fail-closed ≥19); tests + LocalPlayerCreate UI | built `6b21383`; draft PR #957; basecamp sim 9/9; check-A = FIX-FIRST (P2: exact-18 adults hidden because only birth_year stored) | **MERGED 85f870c** (3 commits squashed; column pre-applied + alembic stamped lp01) | #957 |
| B | `feat/s0-club-console-bridge` / `.worktrees/s0-club-bridge` | `admin_review_club_claim` approve → new `services/club_console_bridge.py` find-or-create ClubProgram (+unlisted league if FK requires) + approved ClubProgramClaim + active ClubProgramManager; revoke → revoked; not fundable, not listed | **MERGED c764f10** (3 rounds: hijack guard, console league lock, canonical local ids, self-serve funding adoption, merged-club identity sync; 19 bridge tests) | #959 |
| C | `chore/s0-scheduled-digests` / `.worktrees/s0-ops` | `src/jobs/run_scout_digests.py` (paged, dry-run flag); deploy.yml job loop gains `job-video-maintenance` + `job-scout-digest`; README section. Orchestrator creates the ACA job (weekly Mon 07:00 UTC) after merge | **MERGED 3c52aaa** + ACA job `job-scout-digest` created (Mon 07:00 UTC) and boot-proven | #958 |
| D | `feat/s0-web-account-rails` / `.worktrees/s0-web-rails` | Retire dead journalist Stripe subscribe box; web account delete + export (existing iOS routes); Report control on PlayerPage + LocalPlayerPage; spec | **MERGED ed61a02** (delete/export/report on web, 401/429 handling, 9 Playwright cases; dead subscribe box gone) | #960 |

## Per-package acceptance (Fable verifies, never trusts the report)
- A: Playwright spec shows claim payload with `contract_status`; pytest: 2009 self-claim → 400, 2005 → 201, guardian 2009 still OK; `pnpm build` green.
- B: pytest: approve official claim → `require_club_manager` route 200 for that user; revoke → 403; idempotent; bridged program absent from public lists; live check after deploy: claim a community club with a test account → approve → /my-club shows the console.
- C: job unit test; deploy.yml diff limited to env + loop; after merge: `az containerapp job create` for `job-scout-digest`, one manual `--dry-run` execution succeeds.
- D: spec passes; no `/stripe` fetches remain in the frontend (grep); delete flow logs out; Report posts to the existing route.

## Coordination facts (2026-09-02)
- Ports 5001/5173 belong to session `loanarmy-ac` (MJ's live dev app from `.worktrees/local-app` @852d45a). Never touch. Sim regression self-boots on alternate ports.
- Session `video-analysis` has a codex run in `.worktrees/caption-cap` (PR #956); sequence Deploy runs with them.
- sautai sessions hold ~5 codex runs; keep total ≤ ~8. Stray local branch named `origin/main` (264db4d) deleted today — it made `origin/main` ambiguous.
- Gate quirks: `test_contact.py` must run after `test_club_console.py`; main has import-broken legacy test files → gate on named tests; ruff format is a separate gate; frontend `pnpm build` must pass.

## Next after S0 (from the scorecard)
S1 one player universe + games grain — start from `ledgers/DIRECTIVE_phase1-user-fed-data.md` (MJ decisions flagged there) and `ledgers/DIRECTIVE_phase2-club-fixtures-uploads.md`.

## Log
- 2026-09-02 — ledger created; A + B dispatched; C + D queued behind codex account load.
- 2026-09-02 — basecamp branch-sim machinery proven: `scratchpad/basecamp_sim.sh <ref>` runs the web sim (SIM_GRADE=0) in a separate basecamp worktree `~/Projects/loanarmy-sim` (main clone untouched — filmroom worker runs from it); baseline on ade7bbc = 9/9 ok.
- 2026-09-02 — A handed back (6b21383, gates green per report), pushed, draft PR #957 opened; basecamp sim on the branch 9/9; check-A subagent running. video-analysis merged #956 (main 9bb4f67) — wait for its Deploy before merging #957.
- 2026-09-02 — C handed back (b46fc06), draft PR #958, check-C + sim running. Codex's C log captured an inline Mailgun credential from `az` output (scrubbed from the log; never entered the conversation) → ROTATE + move to Key Vault (MJ decision, `rotate-keys` skill) before creating `job-scout-digest`.
- 2026-09-02 — A fix round 1 handed back (d77bc2c: `local_players.birth_date` + guarded `lp01` from bx01, date-aware minor helper scalar+SQL, tests 67 pass) → pushed to #957; check-A round 2 CLEAN; basecamp sim 9/9 with lp01 applied (sim script now runs `flask --app src.main db upgrade` first). C polish handed back (0600435: dry_run/would_send summary, cursor logging, tests 6+32) → pushed to #958; check-C round 2 running. video-analysis confirmed the Deploy window is open.
- 2026-09-02 — B handed back (7772534), draft PR #959, check-B running. Sim script now tolerates a DB that is ahead of the branch (basecamp DB is at lp01 after A's sim). #957 + #958 CI green on their fix commits.
- 2026-09-02 — check-C round 2 CLEAN (2×P3 follow-ups: stalled-cursor log level back to error; README sentence on creating the three job-scout-digest KV secrets) → #958 marked ready, awaiting bot review then merge. Sim B 9/9.
- 2026-09-02 — D handed back (94fde40), check-D running, draft PR + sim in flight. All four S0 packages now built; merge order C → A (prod pre-apply lp01 first) → B → D, one Deploy at a time.
- 2026-09-02 — check-A round 2 CLEAN (392-case scalar/SQL/leap-day parity matrix, 0 mismatches). P3 follow-ups for a hygiene PR: (a) do not persist a minor's exact birth_date on guardian/agent local creates (store only when it proves adulthood); (b) tests/test_player_suppression.py:1047 hardcodes head 'tf02' (already failing on main); (c) C: stalled-cursor log level back to error + README sentence on creating the job-scout-digest KV secrets. **PROD PRE-APPLIED** `ALTER TABLE public.local_players ADD COLUMN IF NOT EXISTS birth_date DATE;` (0 rows; alembic_version still bx01 → stamp lp01 right after #957 merges; nothing runs migrations automatically in prod). #957 marked ready.
- 2026-09-02 — Bot review (chatgpt-codex-connector) on #958: P2 'Bound API calls across digest pages' (no job-wide APICallBudget, fresh cache/allowance per page → could burn API-Football quota). Codex fix round 2 dispatched (job-wide budget env SCOUT_DIGEST_API_BUDGET, shared enrichment cache, honest degradation). Merge order may flip to A first if #957's bot review is clean.
- 2026-09-02 — Bot review on #957: 'move spec under e2e/' — verified the unit runner does NOT load tests/*.spec.mjs (139/125/14 identical with and without; 14 fails pre-existing on main), so no breakage; honouring the convention anyway via a codex micro-round (git mv → e2e/). D's spec gets the same move in its fix round.
- 2026-09-02 — check-B FIX-FIRST (P1 hijack, P2 funding lock-in, 3×P3) → B fix round 1 dispatched. check-D FIX-FIRST (P2 delete-401, P3s: export 429 msg, spec → e2e/, signed-out report case, local: convention comment; pre-existing App.jsx /stripe cancel/reactivate calls = separate ticket) → D fix round 1 chained after A's micro-round. Codex load dropped to 6.
- 2026-09-02 — A micro-round 86a31b0 (spec → e2e/) pushed; bot thread answered + resolved; #957 merging after CI (squash). Next: watch Deploy, stamp alembic_version → lp01 on prod, health 200, then live-verify a web self-claim.
- 2026-09-02 — **#957 MERGED → main 85f870c**; Deploy watching; prod alembic_version stamped lp01 (column already present).
- 2026-09-02 — C fix round 2 handed back (fe5e0d3: job-wide APICallBudget via SCOUT_DIGEST_API_BUDGET=200 default, shared enrichment cache, api_calls_used/api_budget_exhausted in summary; 40 tests pass) → pushed to #958; check-C round 3 running.
- 2026-09-02 — D fix round 1 handed back (296c26a: delete-401 clears session, export 429 message, spec → e2e/ with 401/429/signed-out cases, 8/8) → pushed to #960; check-D round 2 running.
- 2026-09-02 — **A LIVE**: Deploy 33584756276 success; site 200; live bundle index-Ddkr8ebM.js carries contract_status; backend FQDN is now ca-loan-army-backend.victoriousocean-5cdd2683.westus2.azurecontainerapps.io (old lemonmoss host no longer resolves — update memory/docs).
- 2026-09-02 — check-C round 3 CLEAN (P3s: seam verification guard, README env line for SCOUT_DIGEST_API_BUDGET → hygiene PR). Bot thread answered + resolved. **#958 MERGED** (see main sha above); Deploy watching. Next: create ACA job job-scout-digest after deploy (KV secrets: reuse supabase-db-password + api-football-key; mailgun copy → KV pending MJ rotation decision).
- 2026-09-02 — ACA job **job-scout-digest CREATED** in rg-nbhd-prod (cron 0 7 * * 1, image acrbwmj/loanarmy/backend:prod, identity id-loanarmy-runtime, per-job KV secrets job-scout-digest-{supabase-db-password,api-football-key,secret-key,mailgun-api-key} copied vault→vault / env→vault; MAILGUN key still needs rotation — MJ).
- 2026-09-02 — check-D round 2 CLEAN (P3 follow-up: default playwright.config webServer cwd 'loan-army-backend' is stale) → #960 marked ready; merges after C's Deploy completes and its bot review is read.
- 2026-09-02 — **C LIVE**: Deploy 33585249085 success, r407-1 healthy, health 200; job-video-maintenance image refreshed by the new loop.
- 2026-09-02 — job-scout-digest manual --dry-run execution job-scout-digest-4m4xlmq **Succeeded** (45 s) against prod config.
- 2026-09-02 — Bot review on #960: export 401 should clear the session (valid) → D micro-round 2 dispatched.
- 2026-09-02 — CORRECTION: execution job-scout-digest-4m4xlmq ran LIVE, not dry-run (`az containerapp job start --args=--dry-run` did not reach the container; summary `{"dry_run":false,"users_considered":0,"sent":0,"api_calls_used":1}`). Harmless (0 opted-in users; 1 handshake call). Proves: image boots, KV refs resolve, DB + API-Football + Mailgun config load, JSON summary emitted. FOLLOW-UP (hygiene PR): honour `SCOUT_DIGEST_DRY_RUN=1` env in the job so manual runs can be forced dry without arg overrides.
- 2026-09-02 — B fix round 1 handed back (ace0688: fail-closed ownership audits, console league locked, canonical local ids, approve pending-only, 17 bridge tests + contact/funding suites pass) → pushed to #959; check-B round 2 + sim running.
- 2026-09-02 — #959 CI green on ace0688, basecamp sim 9/9 → marked ready; merge gated on check-B round 2 + bot review.
- 2026-09-02 — D micro-round 2 handed back (17f6d15: export 401 clears session; 9/9) → pushed to #960, bot thread answered + resolved; check-D round 3 running; merge after CI + verdict.
- 2026-09-02 — check-B round 2 CLEAN (P3s accepted for S0: fail-closed ownership audits → runbook: never delete funding_admin_events / club_official_claims, repoint to tombstone; merged-club double-program needs admin merge; O(N) console scans until a migration adds an ownership column). B merge gated on bot review only.
- 2026-09-02 — check-D round 3 CLEAN → **#960 MERGED** (see sha above); Deploy watching. Hygiene add: playwright-report/ is tracked and dirtied by every spec run → git rm --cached + .gitignore.
- 2026-09-02 — Bot review on #959: (1) 409 advertises an admin adoption that does not exist → self-serve adoption carve-out in submit_program_claim; (2) merged local club identity not synced on reuse → B fix round 2 dispatched.
- 2026-09-02 — Package E (hygiene sweep) dispatched in .worktrees/s0-hygiene from origin/main (A+C+D merged): minor-DOB minimisation, SCOUT_DIGEST_DRY_RUN + log level + budget seam check + README, dynamic head test, playwright cwd, dead App.jsx /stripe calls, docs RG/FQDN, untrack playwright-report.
- 2026-09-02 — **D LIVE**: Deploy success, health 200, site 200 (bundle checked for account controls).
- 2026-09-02 — D live CONFIRMED via 'Deploy Frontend (fast)' run (ed61a02, 03:21Z; frontend-only merges take that path, not the full Deploy — my full-Deploy watcher had matched C's run): live bundle index-BNYebAu4.js carries account/export, account/delete, 'Delete my account', the 429 copy, ContentReport; no SubscribeToJournalist. Backend routes 401 unauth as expected.
- 2026-09-02 — INCIDENT: TaskStop of the stale build monitor also killed two background waiters and the codex B fix-2 run launched inside one of them (WIP survived on disk). Resumed the B session (resume, not restart). Lesson: launch codex only from foreground Bash calls; waiters separate.
- 2026-09-02 — E (hygiene) handed back (daf649d, 13 files; 90 tests, lint+build green) → pushed, draft PR opened, check-E + sim running.
- 2026-09-02 — E: PR #961 CI green, basecamp sim 9/9 (db at lp01) → marked ready; merge gated on check-E + bot review; sequence Deploy after B.
- 2026-09-02 — check-E CLEAN (P3s: env truthiness, 17y boundary test, docs wording; follow-up ticket: paid subscribers have no in-app cancel/billing-portal route) → E micro-round dispatched before merge (#961).
- 2026-09-02 — B fix round 2 (resumed) handed back (841cc53: self-serve adoption of console programs into public leagues on claim; merged-club identity sync; 19 bridge tests) → pushed to #959; check-B round 3 running with a design question (console 403 while adopted program is pending).
- 2026-09-02 — E micro-round 479ae10 pushed; **#961 MERGED** (see sha above); full Deploy watching.
- 2026-09-02 — check-B round 3 CLEAN; design verdict: keep console gate coupled to platform_status (adoption pauses console until funding approval). Follow-ups logged: adoption into proposed leagues + local console programs; MyClub 'funding review pending' notice; admin runbook: revoking an official claim during adoption also revokes the pending funding claim (recoverable). Bot threads answered + resolved; merging after E's Deploy.
- 2026-09-02 — **#961 MERGED → main e9d0240**; Deploy 33588492364 watched (result above).
- 2026-09-02 — **#959 MERGED → main c764f10** (3 commits squashed); Deploy 33588929428 watching. All five S0 PRs merged (#957 A, #958 C, #960 D, #961 E, #959 B). Worktrees/branches cleaned.
- 2026-09-02 — **S0 COMPLETE AND LIVE.** #959 Deploy 33588929428 success, prod r409-1 healthy, bridge/funding routes 401 unauth. Re-score: 1.1/2.1/3.4 → 3 → **54.1%** (baseline 51.9%). Artifact republished (label 'after S0'). Worktrees + branches removed. Next: S1.
