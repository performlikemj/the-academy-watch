# Invariants — permanent platform rules

Each rule exists because breaking it caused (or nearly caused) a real incident.
If a task seems to require breaking one, stop and raise it with the user.

## 1. `main` is production; the PR is the audit trail
Never push directly to `main` — branch → PR → merge → watch the deploy run to
completion. Deploy fires on ANY push to main, so the PR record is the only gate.

## 2. Prod DB: IPv4 pooler host + psycopg driver — always
Connection strings must use the Supabase **session pooler**
(`aws-1-us-west-1.pooler.supabase.com:5432`, user `postgres.<ref>`) and the
`postgresql+psycopg://` scheme. The direct `db.<ref>.supabase.co` host is
IPv6-only ("Network is unreachable" from ACA); a bare `postgresql://` scheme
selects psycopg2, which isn't installed → boot crash under gunicorn --preload.
Both bit during the 2026-06-14 password-rotation outage. If
`SQLALCHEMY_DATABASE_URI` is set it wins and must ALSO be pooler+psycopg;
recovery: `az containerapp update --remove-env-vars SQLALCHEMY_DATABASE_URI`
(falls back to DB_* components). Coercion helper: `src/main.py` `_coerce_psycopg_driver`.

## 3. `VITE_API_BASE` must be set for any manual frontend build
The `'/api'` fallback (`src/lib/api.js`) only works behind the vite dev proxy —
on SWA every call 404s ("string did not match the expected pattern"). CI sets it
from the backend FQDN; a manual `swa deploy` must too.

## 4. Backend dependency changes are untested by CI — prove installability
CI's backend job is ruff-only (no pip install); the ACR image build at deploy is
the first real install. Before merging any `requirements.txt` change:
`pip install --dry-run --ignore-installed -r academy-watch-backend/requirements.txt`.
Batch backend Dependabot bumps into ONE PR. **Never merge a standalone
pydantic_core bump** — pydantic pins it exactly. **numpy stays <2.5**: the image
is `python:3.11-slim` (CI lints on 3.12) — all deps must stay py3.11-compatible.

## 5. `pnpm-lock.yaml`: repair surgically, never regenerate
2026-06-12 (PR #420): a Dependabot auto-merge left a duplicate YAML key →
`ERR_PNPM_BROKEN_LOCKFILE` reddened EVERY open PR (CI runs the merge ref with
main). A full regen re-resolves all `^` ranges and silently jumps versions.
Delete the duplicated block by hand; verify with `pnpm install --frozen-lockfile`
in a clean worktree.

## 6. `recompute-academy` is attribution-only — status repair needs a journey RE-SYNC
PR #512: recompute handed the classifier an empty transfer list; the
empty-list→'left' rule overwrote statuses platform-wide (on_loan/sold → left).
`POST /api/admin/journeys/recompute-academy` must never re-derive
`TrackedPlayer.status`. Status flips → journey bulk re-sync (transfers
required); names → `backfill-names`; journey current-status →
`backfill-current-status`.

## 7. Migrations don't run on deploy; all DDL must be idempotent
The Dockerfile CMD is gunicorn only — no `flask db upgrade` anywhere in the
pipeline, and prod schema has out-of-band DDL (the chain can't even replay on an
empty DB). Guard everything with `migrations/_migration_helpers.py`; apply prod
schema deliberately, then reconcile the migration.

## 8. Prod `SECRET_KEY` is the literal string `kvref:http…` — do not "fix" it
Every outstanding admin/user Bearer token is signed with that exact string
(salt `user-auth`, `src/utils/auth.py`). Changing it 401s everyone instantly;
rotation needs a token-revocation + re-login plan. KV copies of
secret-key/admin-api-key are STALE — read inline values via
`az containerapp secret show`.

## 9. Bulk data ops never run against the live prod container
Prod is 0.5 CPU / 1Gi / max 2 replicas: even sequential force_full journey
syncs starve the health probe and cause outages. Scale up first, run
health-gated batches, scale back — or run out-of-band against the pooler.
Exact commands: `docs/agents/debugging.md`.

## 10. API-Football quota: crawl scope is env-controlled, never code-widened
`DEFAULT_CRAWL_LEAGUE_IDS` (`src/utils/supported_leagues.py`) = European top-5.
Widen only via the `CRAWL_LEAGUE_IDS` env var after quota sign-off — past
quota-exceeded incidents. Never hardcode league expansion.

## 11. Never fabricate content attributed to real people or outlets
28 invented "demo tweets" nearly shipped to a club stakeholder. Real
integrations exist (`services/twitter_client.py`); fetch real content, ask the
user, or flag the gap loudly. Corollary: curated stakeholder content must be
analysed for VALUE, not just authenticity — drop opposition-perspective items,
losses, in-passing mentions. Better empty than padded.

## 12. Before declaring a credential missing, read `.env`
A source-tree grep missed `TWITTER_BEARER_TOKEN` sitting in
`academy-watch-backend/.env` — which cascaded into the fabrication incident.
Check `.env`, `env.template`, AND `az containerapp secret show` first.

## 13. Local dev: the login shell exports `ADMIN_API_KEY`, overriding `.env`
Mismatched keys silently 401 local admin calls. Echo the effective env var
before debugging admin auth. (Low-confidence/machine-specific — re-confirm.)
