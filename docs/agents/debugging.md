# Debugging — real failure modes, exact commands

One playbook per symptom you'll actually see in logs, CI, or prod. Each was hit for real.

## Playbook: frontend CI red at "Install dependencies" on an unrelated PR

PR CI runs on the merge ref with `main`, so a broken **main** `pnpm-lock.yaml` reddens
*every* PR regardless of its own changes. On 2026-06-12 sequential Dependabot auto-merges
left a duplicated `@radix-ui/react-dialog` snapshot block → `ERR_PNPM_BROKEN_LOCKFILE:
duplicated mapping key` on every run (fixed PR #420). Git merges YAML without detecting
duplicate keys.

```bash
git worktree add /tmp/wt origin/main && cd /tmp/wt/academy-watch-frontend && pnpm install --frozen-lockfile
```

Fix the duplicate block **surgically** by hand. Do NOT run `pnpm install --lockfile-only`
to regenerate — the broken file can't be parsed, so pnpm re-resolves every `^` range from
scratch and silently jumps dep versions (this is how eslint-plugin-react-hooks 5→7 nearly
snuck in; its v7 rules are pinned to `warn` in `eslint.config.js` pending a migration).

## Playbook: "Deploy Frontend" job fails with MCR 403

`Azure/static-web-apps-deploy@v1` intermittently can't pull *its own* base image:
`mcr.microsoft.com/appsvc/staticappsclient:stable: ... 403 Forbidden`. Transient Microsoft
Container Registry issue, NOT your code or bundle. The action's built-in 3× retry often
isn't enough.

```bash
gh run rerun <run_id> --failed   # usually green on the next try
```

Don't chase it as a code bug; `Deploy Backend` is a separate job and succeeds independently,
so don't block a backend-only change on it.

## Playbook: prod `/api/health` returns 000 / site unresponsive

Almost always **capacity saturation**, not a code crash — prod is 0.5 CPU / ~1–2 workers
(invariants.md §7). Triggered by bulk journey syncs, recomputes, or even concurrent
read-only roster fetches (`/api/teams/<id>/players` computes stats for ~80 players). Stop
the load; prod self-heals ~1 min after. If you must run the op, scale up first or move it
off-container. Check current scale:

```bash
az containerapp show -n ca-loan-army-backend -g rg-loan-army-westus2 \
  --query 'properties.template.scale.{min:minReplicas,max:maxReplicas}' -o table
```

## Playbook: data "isn't showing" on a page

Don't assume the data is wrong. Time the API call AND check the payload size — a slow or
oversized response can block rendering even when the data is correct (season-stats endpoints
time out under load for this reason — same root cause as §7, too few workers). Also: a
manually-built frontend with no `VITE_API_BASE` falls back to `/api`, which 404s on Azure
SWA (no proxy) and surfaces as "SyntaxError: The string did not match the expected pattern"
— rebuild with the backend FQDN (workflow.md).

## Playbook: `Deploy` fails at the Security Checks job

A `public` table lacks Row Level Security (invariants.md §2). The job prints the offending
`schema.table`. Add `ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;` — ideally in the migration
that created the table — and redeploy.

## Playbook: deploy's pip install fails on a Dependabot bump

`pydantic` pins `pydantic-core==X.Y.Z` exactly, but Dependabot opens standalone
`pydantic_core` bump PRs — merging one alone fails the container build. Close it (needs a
coordinated `pydantic` upgrade). Backend `Backend Lint` CI is **ruff only** — it doesn't
install deps, so the deploy build is the first real install test. Dry-run first from a
worktree: `pip install --dry-run --ignore-installed -r requirements.txt`. See workflow.md
for the batching rule.

## Playbook: need an admin/diagnostic op against prod from a local shell

`az containerapp exec` needs a TTY, and the direct DB host is IPv6-only (no local route).
Use the prod HTTP admin endpoints — auth is two-factor: `Authorization: Bearer <token>`
AND `X-API-Key`. Mint the Bearer locally with itsdangerous:
`URLSafeTimedSerializer(secret_key=<inline secret-key>, salt='user-auth').dumps({'email': <admin email>, 'role': 'admin', 'iat': <now>})`.
Read CURRENT inline secrets — the Key Vault copies are stale (invariants.md §9) — and
never echo the values into the transcript:

```bash
az containerapp secret show -g rg-loan-army-westus2 -n ca-loan-army-backend \
  --secret-name secret-key --query value -o tsv
```

Raw SQL: the pooler host, with `PGOPTIONS='-c default_transaction_read_only=on'` for
read-only work.

## Playbook: a POST 405s on theacademywatch.com but the route looks right

The SWA front door can 405 POSTs at the custom domain. Test against the container-app
FQDN (`https://ca-loan-army-backend.<env>.azurecontainerapps.io/api/...`) before
debugging the backend.

## Playbook: exercising Film Room locally (no cloud GPU)

Runs against the LOCAL DB (`soccer_newsletter`), never prod. Load real spike artifacts:
`python src/scripts/load_video_artifacts.py --match-id N --artifacts-dir spike/video-analysis/results/...`.
Media routes need a match-scoped token (`utils/auth.py::mint_media_token`, salt
`video-media`). Known prod gaps: crop serving 501s (no blob persistence yet); SWA CSP
lacks `media-src blob:`.

## DB bloat (context, not usually an incident)

`api_cache` (API-Football TTL cache) dominates DB size; a pg_cron job
`purge-expired-api-cache` runs daily 03:30 UTC (`academy-watch-backend/migrations/maintenance/
api_cache_purge_cron.sql`, PR #499). `DELETE` doesn't shrink disk (freed space is reused);
`VACUUM FULL` is a one-time hand op, never a timer. Inspect: `select * from cron.job;`.
Prod Supabase is `snqwamzutbcbjgusubsa` — a *different* account owns it than the default
`nbhd-united` one, so connect the right account to manage it.
