# Workflow — git, CI, deploy, migrations

Read before committing, pushing, merging, deploying, or migrating. Every push to
`main` deploys to production — treat `main` as a deploy trigger, not a branch.

## Branching & commits

- Never commit directly to `main`. Branch → PR → merge → **watch the deploy finish**.
  Unwatched deploys have shipped broken bundles; the loop closes only when you've
  verified the run, not when you've merged.
- Cross-branch work via `git worktree add`, never checkout-switching a dirty tree.
- Stage files by explicit path. `git add -A` / `git add .` are blocked by a hook.
- Conventional commits: `type(scope): summary` — e.g. `feat(pulse): …`, `fix(admin): …`.
- Non-trivial work: update `CONTINUITY.md` / the active ledger per `AGENTS.md`.

## Pre-push checklist (mirrors CI exactly)

CI on every PR (`.github/workflows/ci.yml`) runs four gates:

```bash
# backend — from repo root; config lives in academy-watch-backend/pyproject.toml
ruff check academy-watch-backend
ruff format --check academy-watch-backend  # CI-only gate: plain `ruff check` misses format drift
# frontend
cd academy-watch-frontend && pnpm lint && pnpm build   # build is a gate too, not just lint
```

- Every CI job installs with `pnpm install --frozen-lockfile`: if you touch
  `package.json`, update `pnpm-lock.yaml` with a normal `pnpm install`. **Never
  regenerate the whole lockfile** — a full regen after a bad Dependabot auto-merge
  once corrupted it and reddened CI on every open PR. Fix lockfile conflicts
  surgically (see `docs/agents/invariants.md`).
- Changing `academy-watch-backend/requirements.txt`? CI never installs backend
  deps (lint-only) — the ACR build at deploy is the first real install. Dry-run
  first: `pip install --dry-run --ignore-installed -r academy-watch-backend/requirements.txt`
  (see `docs/agents/invariants.md` #4 for the pydantic_core / numpy rules).
- The PostToolUse hook (`.claude/hooks/lint_on_edit.sh`) auto-fixes ruff + eslint
  at edit time; this checklist is the backstop, not the first line.

## Merging

- Confirm the base first: `gh pr view <n> --json baseRefName` must be `main`.
  Stacked PRs whose base branch was deleted produce **phantom merges** — the PR
  shows MERGED but `main` never advanced.
- After merging, verify: `git fetch origin && git log origin/main --oneline -1`.
- Never pipe `gh pr checks --watch` / `gh run watch` through anything — the pipe
  steals the exit code. Read the pass/fail output itself.

## Deploy pipeline (push to main = deploy)

- Backend or mixed changes → **Deploy** (`deploy.yml`, ~6 min): RLS security check
  → ruff → ACR image build → Container App `ca-loan-army-backend` + 5 scheduled
  jobs → frontend build + SWA upload.
- Frontend-only changes → **Deploy Frontend (fast)** (`deploy-frontend.yml`,
  ~1–2 min): SWA only. Temporary fast path — delete the file and remove
  `paths-ignore` in `deploy.yml` to revert to full deploys.
- Known flake: Deploy Frontend intermittently 403s pulling its MCR base image.
  Not a code bug — `gh run rerun <id> --failed`.
- `VITE_API_BASE` is baked into the bundle at build time by the workflow. A manual
  `swa deploy` MUST set it explicitly or the frontend ships pointing at nothing.
- RLS gate: every new table needs `ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;`
  (plus policies) or the Deploy workflow fails before building anything.

## Verify the deploy (not the badge)

Green Actions ≠ working product. Drive the user-facing symptom: load the affected
page, hit the prod endpoint. Container logs via the `production-logs` skill or:

```bash
az containerapp logs show -n ca-loan-army-backend -g rg-loan-army-westus2 --tail 100
```

## Migrations

- All DDL must be idempotent via `migrations/_migration_helpers.py`
  (`column_exists`, `table_exists`, …) — prod has out-of-band schema drift.
- Apply to prod inside the container:

```bash
az containerapp exec --name ca-loan-army-backend --resource-group rg-loan-army-westus2 --command /bin/sh
FLASK_APP=src/main.py flask db upgrade
```

- The Dockerfile copies only `src/` and `migrations/` — runnable scripts must
  live in `src/scripts/` to exist in the image.
