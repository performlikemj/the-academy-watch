# The Academy Watch

Football academy tracking platform: monitors academy players out on loan,
generates AI newsletters, and lets journalists write about loaned players.
React SPA + Flask API + PostgreSQL on Azure; integrates API-Football, Stripe,
Mailgun. Two structural facts to hold at all times: (1) the player-tracking
domain has strict semantics (`TrackedPlayer` = one row per player per parent
academy club) that most data bugs trace back to, and (2) **every push to `main`
deploys production**.

## How to use this file

This file is a router, not the manual. Deep context lives in `docs/agents/` —
each doc encodes hard-won lessons; skipping them repeats old incidents.
**Read the matching doc BEFORE starting work in its area:**

| When you are... | Read first |
|---|---|
| Starting ANY task (ledger protocol — mandatory) | `AGENTS.md` + `CONTINUITY.md`, check `ledgers/` |
| Touching player tracking, stats, journeys, classification | `docs/agents/data-model.md` |
| Changing load-bearing mechanisms, or unsure if something is safe | `docs/agents/invariants.md` — permanent rules; each broke something once |
| Debugging a live/prod issue | `docs/agents/debugging.md` |
| Committing, pushing, merging, deploying, migrating | `docs/agents/workflow.md` |
| Writing backend (Flask) code | `docs/agents/backend.md` |
| Writing frontend (React) code | `docs/agents/frontend.md` |
| Running Ralph, scheduled jobs, or sub-agent fan-outs | `docs/agents/loops.md` |
| Needing the full system map / ops-job reference | `ARCHITECTURE.md` / `OPERATIONS.md` |

## Tech stack

- **Frontend**: React 19 + Vite 6 + Tailwind 4 + Radix UI — `academy-watch-frontend/`, pnpm 9, Node 20
- **Backend**: Flask 3.1 + SQLAlchemy 2.0 + Alembic — `academy-watch-backend/`, Python 3.12, venv at `.loan/`
- **Data**: PostgreSQL (prod = Supabase)
- **Infra**: Azure Container Apps (backend + 5 scheduled jobs), Azure Static Web App (frontend), ACR; GitHub Actions CI/CD
- **Integrations**: API-Football, Stripe Connect, Mailgun, Reddit

```
React SPA (SWA) ──/api──▶ Flask (ACA: ca-loan-army-backend) ──▶ Supabase Postgres
                            ▲ 5 scheduled ACA jobs (fixture/status/newsletter syncs)
                            ◀▶ API-Football · Stripe · Mailgun
```

## Key commands

```bash
cd academy-watch-backend && python src/main.py     # backend dev server :5001
cd academy-watch-frontend && pnpm dev              # frontend dev :5173 (proxies /api)
pnpm lint && pnpm build                            # frontend CI gates (in frontend dir)
ruff check academy-watch-backend && ruff format --check academy-watch-backend   # backend CI gates (repo root)
pnpm exec playwright test tests/<file>.test.mjs    # one e2e file (in frontend dir)
flask db upgrade                                   # apply migrations (backend dir)
```

## Iron rules (always active — rationale in docs/agents/)

- `main` deploys prod on push: never commit to `main` directly — branch → PR →
  merge → **watch the deploy run finish**.
- Stage by explicit path (`git add -A`/`.` are hook-blocked); never `--no-verify`;
  never force-push `main`; cross-branch work via `git worktree add`.
- CI-only gates to run before push: `ruff format --check academy-watch-backend`,
  `pnpm build`; `pnpm-lock.yaml` must satisfy `--frozen-lockfile` — repair it
  surgically, never regenerate wholesale.
- Never reference the deleted models `AcademyPlayer` / `SupplementalLoan`; never
  let a `Player NNNN` placeholder overwrite a real player name.
- Prod DB connections: IPv4 pooler host + `postgresql+psycopg://` only. Never
  rotate prod `SECRET_KEY` without a token-revocation plan. No bulk journey
  re-syncs against the prod container.
- Migration DDL must be idempotent via `migrations/_migration_helpers.py`.
- Never print secrets or dump env vars. Never fabricate demo/social content —
  real sources only. Destructive cloud ops need explicit user confirmation.

## Commit convention

`type(scope): summary` — feat / fix / chore / docs / refactor; message says why.
Ledger-first: non-trivial work updates `CONTINUITY.md` / the active planning
ledger in `ledgers/` (statuses: pending → ready → in-progress → complete);
trivial tasks (<15 min, single file) get a one-liner in the Trivial Log.
