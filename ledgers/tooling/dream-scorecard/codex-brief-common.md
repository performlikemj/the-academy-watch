# S1 — "One player universe + a games grain" (The Academy Watch / loanarmy) — COMMON CONTEXT

You are codex, implementing ONE work package of S1 in a dedicated git worktree. Read this whole
brief before touching code. Then read, in order: `CLAUDE.md`, `docs/agents/backend.md` (if backend
work), `docs/agents/frontend.md` (if frontend work), `docs/agents/invariants.md`, `docs/agents/workflow.md`.

## Why S1 exists (context, do not re-audit)
A 2026-09-02 scorecard graded the platform at 52% (54% after S0) with ~0 real users. S1 makes self-made players FINDABLE and gives players and clubs a way to enter games and stats. S1 fixes
the two biggest blockers: local players are invisible to scouts, and nobody can enter games. Each package is bounded,
surgical, and must not widen scope. Prod facts you can rely on: `CONTACT_RAIL_ENABLED=1` in prod;
decision D1 = 18+ only for participation (accounts, claims, contact, media); unknown age = minor.

## Hard fences (all packages)
- Work ONLY inside your worktree (given below). Never touch the main checkout or other worktrees.
- Edit ONLY the files/dirs listed as ALLOWED in your package. If you believe another file must
  change, STOP and say so in the final report instead of editing it.
- No `git push`. No ledger/CONTINUITY edits. No secrets in code, logs, or the report. No new
  dependencies. No migrations unless your package says so (S0 has none).
- Smallest correct mechanism on top of what exists. Cite the real functions you extend.
- Never reference the deleted `AcademyPlayer`/`SupplementalLoan` models. Use `TrackedPlayer`.
- Finish with exactly ONE commit using the exact message given, staged by path (`git add <paths>`),
  never `git add -A`/`.`. Never `--no-verify`.

## Gates (run all that apply; paste real output summaries in the report)
- Backend: `cd academy-watch-backend && ../.loan/bin/ruff check . && ../.loan/bin/ruff format --check .`
  (if `../.loan/bin/ruff` is missing use `../.loan/bin/python -m ruff`). Python is
  `/Users/michaeljones/Projects/loanarmy/.loan/bin/python` (3.11). Run ONLY the named tests you
  touched/added plus their file: `cd academy-watch-backend && ../.loan/bin/python -m pytest tests/<file>.py -q`.
  Main has some import-broken legacy test files — do not try to make the whole suite green.
- Frontend: first `./scripts/setup_frontend.sh` from the repo root (OSV gate + frozen install, only
  installs if missing/stale), then `cd academy-watch-frontend && pnpm lint && pnpm build`. Build
  failure blocks. If you add UI, add or extend ONE Playwright spec under
  `academy-watch-frontend/tests/` mirroring existing mocked-API specs (see `tests/*.spec.mjs`) and run
  just that spec: `pnpm exec playwright test tests/<file>.spec.mjs`.

## Final report contract (last message, plain text, ≤60 lines)
1. What changed (files + the mechanism, 5–10 lines). 2. Commit hash + message. 3. Gate outputs
(ruff / pytest counts / lint / build / spec pass counts). 4. Anything you could NOT do and why.
5. Any file outside ALLOWED you think must change (not changed). 6. Risks a reviewer should attack.
Be honest: a failed gate is reported as failed, never hidden.

## S1 decisions (ratified — do not reopen)
- D1: approved local players NOT linked to API-Football get `player_api_id = -local_player_id` (negative, reserved) and a
  `PlayerShadow` row; `< 0` ⇒ local. Never call API-Football for a negative id.
- D2: self-reported and club-entered stats are SHOWN on the scout desk with a provenance chip (`api` / `club` / `self`) and a
  `source` filter; totals never sum across sources (existing rollup rule).
- D3: minors may have stats entered but are never public; the existing minor bridges apply to negative ids exactly as to positive ones.
- Base: origin/main after S0 (Alembic head `lp01`). Migrations allowed ONLY where a package says so, guarded, RLS-enabled for new
  tables, single head; the orchestrator pre-applies DDL to prod before merge.

## PORT FENCE (mandatory)
Ports **5001** and **5173** belong to another session's live app. Never start, kill, or reuse anything on them. Playwright:
start your own Vite from YOUR worktree on 5180+ (`pnpm dev --host 127.0.0.1 --port 5180 --strictPort`), set
`E2E_BASE_URL=http://127.0.0.1:5180`, mock every `**/api/**` with `page.route`, put specs under `e2e/`, run
`E2E_BASE_URL=... pnpm exec playwright test e2e/<spec>.mjs`, stop Vite by PID. Do not run `sim/run.mjs`.
