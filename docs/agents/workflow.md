# Git / CI / deploy workflow

The rules and the traps for shipping. The user expects the full PR → merge →
watch-deploy sequence on **every** change — never a direct push to main.

## Branching

- `main` is **unprotected** at the GitHub level, but the team runs strictly PR-based
  (every commit on main is a `(#NNN)` merge). Branch from main: `feat/` `fix/` `chore/`
  `refactor/` `docs/`.
- **Dirty tree → use a worktree**: `git worktree add .claude/worktrees/<name> -b <branch> origin/main`.
  Never `git checkout` away from a dirty tree.
- Stage specific files by path. `git add -A` / `git add .`, `--no-verify`, and
  force-push-main are blocked by the global git hook (`~/.claude/hooks/git_guard.sh`).

## Pre-push checklist (each maps to a CI gate a plain local run does NOT cover)

1. **`ruff format --check academy-watch-backend`** — the `CI` and `Deploy` workflows run this
   as a **separate, stricter gate** from `ruff check`. The on-edit hook auto-formats, but
   verify before push. (`ruff check academy-watch-backend` is the other gate.)
2. **`cd academy-watch-frontend && pnpm build`** — CI runs `pnpm lint` **and** `pnpm build`;
   a build/type failure reddens CI even when lint is clean. Run the build, not just lint.
3. **`pnpm install --frozen-lockfile`** — CI installs frozen; a `package.json` change without
   a matching `pnpm-lock.yaml` update fails install. Never regen the whole lockfile to fix a
   Dependabot break (debugging.md) — patch surgically.
4. **Adding a migration that `CREATE TABLE`s?** Enable RLS in the same migration
   (`ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;`) — the Deploy `security-checks` job fails the
   deploy otherwise (invariants.md §2). And guard all DDL with `_migration_helpers` (§8).
5. **Changing `requirements.txt`?** `pip install --dry-run --ignore-installed -r requirements.txt`
   from a worktree — `Backend Lint` CI is ruff-only and never installs deps, so the deploy
   container build is otherwise the first install test.
6. Local `.loan` venv is **Python 3.11** (matches the prod image) while CI lint runs on 3.12
   and ruff config targets py312. When CI fails on something that passes locally, suspect the
   version gap, not your diff.

## Dependabot

- **Backend** bumps all edit the one `requirements.txt` → merging individually triggers a
  rebase cascade + one deploy each. Combine into a single hand-authored
  `chore(deps): batch backend bumps` PR, then close the superseded ones (squash drops
  `Closes #N` for all but the first). **Never merge a standalone `pydantic_core` bump**
  (pydantic pins it exactly — breaks the deploy; debugging.md). **numpy stays <2.5**
  (needs py≥3.12; the image is 3.11) — `dependabot.yml` already ignores it, don't override.
- **Frontend** bumps (`package.json`/`pnpm-lock.yaml`) are independent — merge directly.
- Dependabot PRs auto-merge (`dependabot-auto-merge.yml`, squash). The only red check is
  usually the non-gating `auto-merge` job; real CI (Lint+Build) is green.

## Merging & watching

```bash
gh pr create --fill                 # or with a why-focused body
gh pr merge <n> --squash            # match the repo's squash-merge convention
gh run watch                        # BARE — no pipe, no trailing `; echo` (steals the exit code)
```

Read the watch output, don't trust `$?` through a pipe.

## Deploy pipeline (push to main)

Two workflows split by path:
- **`Deploy` (deploy.yml)** — backend or mixed changes. Jobs: `security-checks` (RLS on all
  public tables) → `lint-backend` (ruff check + format) → `deploy-backend` (ACR build →
  Container App single-revision update, tag `prod`, + updates the 5 scheduled jobs) →
  `deploy-frontend` (builds with `VITE_API_BASE` from backend FQDN → Azure SWA).
- **`Deploy Frontend (fast)` (deploy-frontend.yml)** — triggered by `academy-watch-frontend/**`
  only. Skips the ~6-min backend rebuild + RLS check; deploys just the SPA (~1–2 min). It
  fetches the backend FQDN for `VITE_API_BASE` and refuses to ship with an empty one.

**Manual frontend deploy** must set `VITE_API_BASE` (the FQDN) or every API call 404s on SWA:
`VITE_API_BASE="https://ca-loan-army-backend.<...>.azurecontainerapps.io/api" pnpm build`.

## Verify a deploy is live

`gh run watch` the run to completion, then hit `/api/health`:
`curl -s https://ca-loan-army-backend.<fqdn>/api/health`. A `000`/timeout usually means
capacity, not a bad deploy (debugging.md). Scheduled scaling toggles minReplicas 1↔0 at
02:00/10:00 UTC — an off-peak cold start can mask as a deploy problem.

## Commit convention

Scoped Conventional Commits: `feat(scope):` `fix(scope):` `chore(deps):` `refactor(scope):`
`docs(scope):`. Concise, focused on the why. Complex work gets a `ledgers/` planning ledger
first and a `CONTINUITY.md` update (AGENTS.md).
