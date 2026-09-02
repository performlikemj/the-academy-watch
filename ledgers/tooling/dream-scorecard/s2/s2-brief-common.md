# S2 — "Fans + reach" (The Academy Watch / loanarmy) — COMMON CONTEXT

You are codex, implementing ONE work package of S2 in a dedicated git worktree. Read this whole brief
before touching code. Then read, in order: `CLAUDE.md`, `docs/agents/backend.md` (if backend work),
`docs/agents/frontend.md` (if frontend work), `docs/agents/invariants.md`, `docs/agents/workflow.md`.

## Why S2 exists (context, do not re-audit)
A 2026-09-02 scorecard graded the platform at 59.8% after S0+S1 with ~0 real users. S2 makes players
"have fans" and gives the site reach: any signed-in account can follow a player, public fan counts,
an owner-only "who is watching me" card on web, share links with real og tags + a card image, a
sitemap, and an opt-in weekly activity email. Prod facts you can rely on: `CONTACT_RAIL_ENABLED=1`,
`SCOUT_INCLUDE_LOCAL_PLAYERS=1`, Alembic head `pm01`, `PUBLIC_BASE_URL=https://theacademywatch.com`
(website origin), and — REQUIRED prod config the orchestrator sets — `PUBLIC_API_BASE_URL=https://api.theacademywatch.com`
(API origin; Flask also serves the SPA shell at unknown paths on that host). There is NO ProxyFix and
the app must NEVER trust `Host`/`X-Forwarded-*` for URL building: when `PUBLIC_API_BASE_URL` is unset
(dev/tests only) fall back to `request.url_root`, otherwise use the env verbatim.
Backend tests run on SQLite in-memory (JSONB is mapped to JSON; `ON CONFLICT` and `@>` are NOT available
in tests — write dialect-neutral code). Timestamp columns are timezone-NAIVE UTC; normalise any aware
`now` to naive UTC before comparing or storing (pattern: `src/routes/showcase.py:3954-3973`).

## Ratified decisions (do not reopen)
- D1: ANY active signed-in account may follow a player. No scout verification. A user cannot follow a
  subject they own (approved player claim) — 400, not silent — AND owners are excluded from fan counts
  at read time (so a follow placed while a claim was pending never counts after approval).
- D2: Fans are a NEW table `player_fans` (one row per user × signed player id). Fans are NOT scout
  `follow_lists`/`follows` rows (scout digests iterate those; never mix).
- D3: Every subject-revealing read or create surface (fan count, follow create, share HTML, card.png, each
  sitemap player URL, profile_view persistence, notification email content) goes through ONE gate:
  `resolve_public_adult_subject(signed_id)` in `src/services/public_player_subject.py`. It returns a
  `PlayerSubject` only for a resolvable, non-suppressed (in BOTH namespaces), known-ADULT subject (unknown
  age = minor = fail closed). Anything else → the neutral 404 (`neutral_player_not_found()` from
  `src/services/player_suppression.py`) or silent omission with an UNCHANGED response shape. Never reveal
  whether a subject exists, is a minor, is suppressed or is pending — not via status, body, headers, timing,
  or an accepted-count difference. The sole exception: `DELETE /follow` never resolves the subject (cleanup).
- D4: Local players use negative synthetic ids (`player_api_id = -local_player_id`); routes take
  `<int(signed=True):player_api_id>`; never call API-Football for negative ids; never mint rows on read.
- D5: Notifications are email-only, opt-in per account (`user_accounts.profile_activity_email_opt_in`,
  default false), aggregate counts only, never a follower/viewer identity. Label the metric "profile
  views" (never "scouts viewed you") — the view event is anonymous telemetry: `profile_view` rows store
  NO user_email, session_id, path or referrer.
- D6: Share/sitemap URLs are served on the API origin (`PUBLIC_API_BASE_URL`); canonical human URLs stay
  on `PUBLIC_BASE_URL` (`/players/<id>` or `/local-players/<local id>`). Do NOT add external-host
  rewrites to `staticwebapp.config.json` (SWA cannot proxy to another host). Public share/card/sitemap
  responses are `Cache-Control: no-store` (Cloudflare fronts the API host and there is no purge path).
- D7: Server-written fan analytics use event names `fan_follow_added` / `fan_follow_removed`, which are
  NOT in the public `ALLOWED_EVENTS` allowlist (unspoofable). `follow_removed` is NOT added publicly.

## Hard fences (all packages)
- Work ONLY inside your worktree (given below). Never touch the main checkout or other worktrees.
- Edit ONLY the files/dirs listed as ALLOWED in your package. If you believe another file must change,
  STOP and say so in the final report instead of editing it.
- No `git push`. No ledger/CONTINUITY edits. No secrets in code, logs, or the report. No new
  dependencies. No migrations unless your package says so.
- Smallest correct mechanism on top of what exists. Cite the real functions you extend.
- Never reference the deleted `AcademyPlayer`/`SupplementalLoan` models. Use `TrackedPlayer`.
- Finish with exactly ONE commit using the exact message given, staged by path (`git add <paths>`),
  never `git add -A`/`.`. Never `--no-verify`.

## Gates (run all that apply; paste real output summaries in the report)
- Backend: `cd academy-watch-backend && ruff check . && ruff format --check .` (`ruff` 0.15 is on PATH at
  `/opt/homebrew/bin/ruff`; the venv has no ruff). Python is the shared venv of the MAIN checkout:
  `PY=/Users/michaeljones/Projects/loanarmy/.loan/bin/python` (3.11; your worktree has no `.loan`). Run
  ONLY the named tests you touched/added plus their files:
  `cd academy-watch-backend && PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -p no:cacheprovider -q tests/<file>.py`.
  Migrations: `cd academy-watch-backend && $PY -m flask --app src.main db heads`.
  Main has import-broken legacy test files — do not try to make the whole suite green. FOUR tests fail on
  main before S2 and are NOT yours: `tests/test_local_clubs.py::TestAffiliationVisibility` (3) and
  `tests/test_account.py::...test_delete_erases_owned_data_and_tombstones_shared_integrity` (1) — report
  them separately, never "fix" unrelated fixtures for them.
- Frontend: first `./scripts/setup_frontend.sh` from the repo root (OSV gate + frozen install, only
  installs if missing/stale), then `cd academy-watch-frontend && pnpm lint && pnpm build`. Build
  failure blocks. UI work adds/extends ONE Playwright spec under `academy-watch-frontend/e2e/`
  mirroring the mocked-API specs there, and runs just that spec (see PORT FENCE).

## Final report contract (last message, plain text, ≤60 lines)
1. What changed (files + the mechanism, 5–10 lines). 2. Commit hash + message. 3. Gate outputs
(ruff / pytest counts / lint / build / spec pass counts). 4. Anything you could NOT do and why.
5. Any file outside ALLOWED you think must change (not changed). 6. Risks a reviewer should attack.
Be honest: a failed gate is reported as failed, never hidden.

## PORT FENCE (mandatory)
Ports **5001** and **5173** belong to another session's live app. Never start, kill, or reuse anything on
them. Playwright: start your own Vite from YOUR worktree on 5180+ (`pnpm dev --host 127.0.0.1 --port 5180
--strictPort`), set `E2E_BASE_URL=http://127.0.0.1:5180`, mock every `**/api/**` with `page.route`, put
specs under `e2e/`, run `E2E_BASE_URL=... pnpm exec playwright test e2e/<spec>.mjs`, stop Vite by PID.
Do not run `sim/run.mjs`.
