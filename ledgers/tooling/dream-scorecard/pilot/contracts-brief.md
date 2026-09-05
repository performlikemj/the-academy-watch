# Brief: write the build contracts for the one-club pilot packages (you are the architect; you will also build them next)

You are codex (gpt-6-astra), READ-ONLY, no network, at `/Users/michaeljones/Projects/loanarmy/.worktrees/pilot-contracts` (origin/main). Your final message is the
deliverable (markdown). The owner has approved building the pilot; the directive is `ledgers/DIRECTIVE_pilot-club.md`; your own plan is
`ledgers/research/pilot-direction-codex-2026-09-05.md` (Part 3, packages P0–P4). Now turn that plan into contracts precise enough that a builder (you, in a
separate danger-full-access session per package) can implement each package without re-deriving decisions, and a Fable checker can verify against them.
Read the load-bearing code for each package before writing (the plan cites it) and read `docs/agents/backend.md`, `docs/agents/invariants.md`,
`docs/agents/frontend.md`, and the S3 tooling for the money stage (`ledgers/tooling/dream-scorecard/s3/money-safety/*.md`) to match the house style
(guarded migrations, RLS on every new table, naive-UTC, dialect-neutral, SQLite tests, fences, one commit per PR, checker attack lists).

## Waves and fences (fixed by the orchestrator — design inside them)
- **Wave 1 (parallel worktrees, disjoint files):**
  - **P1 cohort register/report** — admin-only. Files: a new `src/routes/admin_cohort.py` (or extend `src/routes/events.py` if that is clearly smaller) + a new service
    module + tests + the admin web page/tab under `academy-watch-frontend/src/pages/admin/`. No migration unless a cohort register table is truly needed (prefer a
    JSON-defined register stored in one small table with RLS if the founder must edit it in-app; otherwise an env/admin-posted list — decide and justify).
  - **P2 accepted club relationship + local contact routing** — files: `src/routes/club.py` (invitation endpoints), `src/routes/showcase.py` (claimant list/accept/
    decline + local club attestation fields), `src/services/contact.py` (club_included resolution for locals), models, ONE migration `s4a1_club_invitations.py`
    (down_revision `s3e1`), tests, web: MyClubConsole roster tab (invite), ShowcaseSection (player accepts), ClubIntroductionsPanel if touched.
- **Wave 2 (sequential after wave 1 merges):**
  - **P3 private player feedback + acknowledgment** — files: NEW blueprint `src/routes/feedback.py` (do not grow club.py), new model, migration `s4b1_player_feedback.py`
    (down `s4a1`), account export/erasure hooks in `src/services/account.py`, web: manager "Publish feedback" in MyClubConsole + player inbox/detail (web + mobile web).
  - **P4 stable result corrections** — files: `src/routes/club.py` results endpoints, `src/models/player_match_entry.py`, `src/services/season_rollup_service.py`
    (refresh both seasons), migration `s4c1_club_results.py` (down `s4b1`), web result form; tests incl. a PostgreSQL concurrency test file (skips without
    `PILOT_TEST_POSTGRES_URL`; the orchestrator runs it on a local disposable DB).
- **P0 preflight** is operator work: write it as a runbook the orchestrator executes on the basecamp sim (`ledgers/tooling/dream-scorecard/basecamp_sim.sh`,
  README in that folder) and then with the real club: steps, the exact curl/psql/admin-UI checks, pass/fail criteria, and what to record.

## For EACH package produce
1. **Goal + non-goals** (2–5 lines).
2. **Data model**: tables/columns/indexes/constraints/RLS, or "none"; exact migration id and down_revision; what account export/erasure must do.
3. **API contract**: method + path, auth decorator order (auth → entitlement/authority → limiter, as the repo does), request/response JSON shapes, error codes with
   `error` strings, idempotency and locking rules, rate limits. Cite the existing helpers to reuse (`require_club_manager`, signed-id helpers, `resolve_player_subject`,
   `club_has_authority_over_player`, contact service resolution, etc.).
4. **Authorization matrix**: who can do what; explicit denials (wrong claimant, minor subject, suppressed, revoked manager, other club, expired/replayed invite).
5. **Web**: screens/components to add or change (file paths), states (empty/loading/error/denied), copy strings, analytics events (via `src/lib/track.js`, no PII).
6. **Tests the checker will demand**: named scenarios incl. negative paths, SQLite vs Postgres notes, e2e (Playwright) if web touched (free port, `E2E_BASE_URL`).
7. **Fences**: exact file list; nothing else. One commit; PR body template.
8. **Effort** (S/M/L) and the top 3 risks with the mitigation baked into the contract.
Also: a short **"decisions I made for the owner"** list per package (defaults chosen so building never blocks), and the **pre-apply DDL note** for each migration
(the orchestrator dumps exact DDL from a migrated local Postgres and pre-applies before merge; stamps after deploy).

## Output format
`## Overview` (waves, dependency notes, total effort) · `## P0 runbook` · `## P1` · `## P2` · `## P3` · `## P4` · `## Open questions for the owner` (only ones that
truly block; otherwise decide). Cite file:line for every claim about existing code; never invent files.
