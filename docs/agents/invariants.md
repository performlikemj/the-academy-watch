# Invariants — permanent rules

Each rule here exists because breaking it caused a real production incident or maps
to a hard platform constraint. They are not style preferences. If a change needs to
break one, stop and raise it with the user first.

## 1. Prod DB: IPv4 pooler host + `postgresql+psycopg://` only

Two hard requirements, both learned from a 2026-06-14 outage during a password rotation:
- **Driver scheme**: the backend image ships **psycopg v3 only** (no psycopg2). A bare
  `postgresql://` URI (Supabase's default copy string) routes SQLAlchemy to psycopg2 →
  `ModuleNotFoundError` → the app crashes on boot under `gunicorn --preload`. Use
  `postgresql+psycopg://`. `src/main.py::_coerce_psycopg_driver` (PR #434) auto-coerces
  a bare scheme, but any `SQLALCHEMY_DATABASE_URI` override you set must already be right.
- **Host = IPv4 pooler, NOT direct**: the direct host `db.<ref>.supabase.co:5432` resolves
  to **IPv6**, and ACA has **no IPv6 egress** → "Network is unreachable". Use the pooler
  `aws-1-us-west-1.pooler.supabase.com:5432`, user `postgres.<ref>`. The working prod
  config is the `DB_*` component vars (secret `supabase-db-password`).
- **Recovery**: `az containerapp update --remove-env-vars SQLALCHEMY_DATABASE_URI` falls
  the app back to the DB_* pooler config. Password-free, reversible.

## 2. Every public table needs Row Level Security — or the deploy fails

The `Deploy` workflow's `security-checks` job queries `pg_tables` for any `public` table
with `relrowsecurity = false` (excluding `alembic_version`, `schema_migrations`) and
**fails the deploy** if one exists. A migration that `CREATE TABLE`s in `public` without
`ALTER TABLE <t> ENABLE ROW LEVEL SECURITY;` will block prod for everyone. Enable RLS in
the same migration that creates the table. (The check only runs when `SUPA_DB_PASSWORD`
is set; treat it as always-on.)

## 3. `owning-club` TrackedPlayer rows are deprecated and auto-deactivated

Clubs only track players whose **journey shows academy formation at that club**
(prior-senior-career rule in `JourneySyncService._compute_academy_club_ids`). The journey
upsert never creates `data_source='owning-club'` rows and deactivates any active row at the
owning (buying) club unless it is pinned or manual. Don't reintroduce owning-club ordering
in queries or recreate these rows. Admin repair: `POST /api/admin/journeys/recompute-academy`.

## 4. Academy tracking window: now or within `ACADEMY_WINDOW_YEARS` (default 4)

The platform only tracks players in an academy **now or within the past N seasons**
(`utils/academy_window.py::is_within_academy_window`). `last_academy_season` (and the
per-club `academy_last_seasons` map on `PlayerJourney`) hold the evidence. The journey
upsert, recompute-academy repair, rebuild stage 4, seed-team, and GOL lookup all enforce
this; older alumni rows are deactivated (pinned/manual survive). Don't add a code path
that tracks a player outside the window.

## 5. A placeholder name must never overwrite a real `player_name`

`Player NNNN` placeholders are resolved by `resolve_player_name()` (utils/player_names.py:
CohortMember → AcademyPlayerSeasonStats → Player → PlayerJourney). Any write to
`player_name` must guard against clobbering a real name with a placeholder.
Backfill: `POST /api/admin/players/backfill-names`.

## 6. The `AcademyPlayer` and `SupplementalLoan` models are permanently deleted

Tables `loaned_players` and `supplemental_loans` were dropped. Do NOT reference these
models anywhere in code — use `TrackedPlayer` for all player tracking. (Docstrings/scripts
that mention the historical migration are fine; live model references are not.)

## 7. Never run bulk data ops against the live prod container

Prod (`ca-loan-army-backend`) runs on **0.5 CPU / 1Gi / minReplicas=1 / maxReplicas=2**
(~1–2 gunicorn workers). On 2026-06-20 even a **single sequential** `force_full` journey
re-sync flapped `/api/health` to `000` after ~2 players, and concurrent read-only roster
fetches saturated it. Each `force_full` holds a worker ~7s (CPU + API-Football I/O),
starving the health probe. For any re-sync/recompute/backfill: scale up first
(`--cpu 1.0 --memory 2Gi --min-replicas 2 --max-replicas 4`), or run it as a separate ACA
job / out-of-band script hitting the DB directly, then scale back. Health-gate and abort
on the first `000`; prod self-heals once load stops.

## 8. Every migration guards its DDL — prod schema drifted out-of-band

Production has had columns/tables added outside Alembic. Migrations MUST use the idempotent
helpers in `migrations/_migration_helpers.py` (`column_exists`, `table_exists`, …) so a
re-applied or partially-applied DDL doesn't crash `flask db upgrade` on deploy. Never write
a bare `op.add_column` / `op.create_table` without a guard.

## 9. Prod `SECRET_KEY` is a `kvref:` literal — do not "fix" it casually

The prod container's inline `secret-key` is the 61-char literal string `kvref:http...`
(a failed Key Vault reference — ACA doesn't parse that syntax). Flask signs every admin/user
Bearer token with it via `itsdangerous`. Changing it 401s **every outstanding token** the
instant it changes. The KV copy `kv-loan-army/secret-key` is stale and differs — do not mint
tokens from it. Rotation needs a planned window + user re-login. Read live truth via
`az containerapp secret show`. Same inline-vs-KV divergence applies to `admin-api-key`.
