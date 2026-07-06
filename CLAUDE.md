# The Academy Watch

Football (soccer) academy-tracking platform: it follows academy players out on loan,
syncs their career/stats from API-Football, and generates AI newsletters that
journalists add commentary to. Monorepo — a Flask backend (`academy-watch-backend/`)
serving a React/Vite SPA (`academy-watch-frontend/`), both deployed to Azure off a
single Supabase Postgres. The load-bearing fact: the whole domain hangs off
**`TrackedPlayer`** (one row per player per parent academy club) and the **journey
sync** that classifies each player's pathway status — get those wrong and every
page lies.

## How to use this file

This file is a router, not the manual. Deep context lives in `docs/agents/` —
each doc encodes hard-won lessons, and skipping them repeats old mistakes.
**Read the matching doc BEFORE starting work in its area:**

| When you are... | Read first |
|---|---|
| Touching player tracking, journey sync, stats, or the data flow | `docs/agents/architecture.md` |
| Changing models, migrations, journey/status logic, or the DB connection | `docs/agents/invariants.md` — permanent rules; each broke prod once |
| Debugging a live issue (CI red, deploy fail, prod down, data missing) | `docs/agents/debugging.md` |
| Committing, pushing, merging, deploying, migrating, or handling Dependabot | `docs/agents/workflow.md` |
| Writing backend code (Flask / SQLAlchemy / Alembic) | `docs/agents/backend.md` |
| Writing frontend code (React / Vite / Tailwind / Radix) | `docs/agents/frontend.md` |

**Ledger protocol (this repo's own system, still in force):** before ANY work read
`AGENTS.md` + `CONTINUITY.md` and check `ledgers/` for an active planning ledger;
update `CONTINUITY.md` when state changes. Autonomous runs go through `scripts/ralph/`.

## Tech stack

- **Backend**: Flask 3.1 + SQLAlchemy 2.0 + Alembic, Python **3.11** (Docker `python:3.11-slim`; ruff config targets py312, venv `.loan` is 3.11)
- **Frontend**: React 19 + Vite 6 + Tailwind 4 + Radix UI, pnpm, ESLint flat config (`.jsx`)
- **Data**: PostgreSQL on **Supabase** (`snqwamzutbcbjgusubsa`, us-west-1); RLS on all public tables
- **Infra**: Azure Container Apps (backend `ca-loan-army-backend`) + Static Web App (frontend `swa-goonloan`), ACR `acrloanarmy`, RG `rg-loan-army-westus2`
- **Integrations**: API-Football (all football data), Stripe Connect (writer payouts), Mailgun (email), Reddit, OpenAI (AI newsletters)

```
React/Vite SPA ──/api proxy──▶ Flask (13 blueprints) ──▶ Supabase Postgres (RLS + Alembic)
                                     │
                     API-Football · Stripe · Mailgun · Reddit · OpenAI
```

## Key commands

```bash
cd academy-watch-backend && python src/main.py        # backend dev (:5001)
cd academy-watch-frontend && pnpm dev                 # frontend dev (:5173, proxies /api→:5001)
ruff check academy-watch-backend && ruff format --check academy-watch-backend   # backend CI lint gates
cd academy-watch-frontend && pnpm lint && pnpm build  # frontend CI gates (build failure blocks)
cd academy-watch-backend && flask db upgrade          # apply migrations (head chain in backend.md)
cd academy-watch-frontend && pnpm exec playwright test tests/<file>.mjs   # single E2E while iterating
```

## Iron rules (always active — rationale in docs/agents/)

- **PR flow, never push to main.** `main` is unprotected but the team runs PR → merge → watch-deploy on every change; branch (`feat/` `fix/` `chore/` `refactor/`), and use a worktree when the tree is dirty. Broad staging (`git add -A`/`.`), `--no-verify`, and force-push-main are blocked by the global git hook.
- **CI gates local defaults miss:** `ruff format --check` is a separate gate from `ruff check`; frontend `pnpm build` must succeed (not just lint); `pnpm install --frozen-lockfile` fails on a stale lockfile; the Deploy job's RLS check **fails the deploy if any new public table lacks Row Level Security**. See `workflow.md`.
- **Prod DB is reached via the IPv4 pooler + `postgresql+psycopg://` only** — the direct (IPv6) host is unreachable from ACA and a bare `postgresql://` loads the absent psycopg2. See `invariants.md`.
- **Never reference the deleted `AcademyPlayer`/`SupplementalLoan` models** — use `TrackedPlayer`. **Alembic migrations guard every DDL** (prod schema drifted out-of-band). **Never bulk-sync/recompute against the live prod container** — it's tiny and falls over. See `invariants.md`.
- **Secrets:** never print secrets or dump env; read live values via `az containerapp secret show`. Prod `SECRET_KEY` is a `kvref:` literal — do NOT "fix"/rotate it without a token-revocation plan (`invariants.md`).

## Commit convention

Scoped Conventional Commits: `feat(scope):` `fix(scope):` `chore(deps):` `refactor(scope):` `docs(scope):` — concise, focused on the why. Complex work gets a `ledgers/` planning ledger first (see `AGENTS.md`).
