# Backend — Flask / SQLAlchemy / Alembic gotchas

Code-level notes for `academy-watch-backend/`. Architecture and the data model are in
`architecture.md`; permanent rules in `invariants.md`.

## Toolchain reality

- The prod image is **`python:3.11-slim`** and the local venv `.loan/bin/python` is 3.11.
  Ruff config (`academy-watch-backend/pyproject.toml`) targets **py312** and CI lints on 3.12.
  So a `UP`/syntax feature that lints clean can still break the 3.11 runtime — mind the gap.
- Ruff is **not** in the `.loan` venv; use the system `ruff` (the on-edit hook falls back to it).
  Config: line-length 120, `select = E,F,I,UP,B,SIM` with a long `ignore` list (E501/E402/… —
  E402 is ignored on purpose because Flask deferred imports are a pattern). Run gates from repo
  root: `ruff check academy-watch-backend && ruff format --check academy-watch-backend`.
- The on-edit lint hook runs `ruff check --fix` then `ruff format` on `.py` saves. `check --fix`
  strips imports with **no call site yet** — when adding an import mid-refactor, add the import
  and its first use in the **same** edit.

## Migrations (Alembic)

- **Always guard DDL** with `migrations/_migration_helpers.py` (`column_exists`, `table_exists`,
  …) — prod schema has drifted out-of-band, so unguarded `op.add_column`/`op.create_table`
  crashes `flask db upgrade` on deploy (invariants.md §8).
- **New public table → enable RLS in the same migration** or the deploy's security-check fails
  (invariants.md §2).
- Generate migrations (`flask db migrate -m "..."`), review the autogen, then `flask db upgrade`.
  The head is a long chain with merge nodes (e.g. `… aw18 → cs01 → aw19 (merge cs01,vid02) →
  aw20 → vid03 → aw22`); check `alembic heads` before adding one so you branch from the real tip.
- Maintenance SQL (non-schema, e.g. the api_cache pg_cron purge) lives in
  `migrations/maintenance/`, not the version chain.

## Database connection

Prod reaches Supabase via the IPv4 pooler + `postgresql+psycopg://` (psycopg v3 only, no
psycopg2) — see invariants.md §1. Locally the `DB_*` component vars or a `postgresql+psycopg://`
URI both work; a bare `postgresql://` will fail the same way prod does.

## Docker packaging trap

The `Dockerfile` copies only `src/` and `migrations/` into the image — **scripts at the repo
root are NOT in the container**. A runnable one-off (backfill, repair) must live in
`src/scripts/` to be invokable in prod (`az containerapp exec ... python src/scripts/<x>.py`).
The image also bundles Pango/Cairo/fonts for WeasyPrint PDF newsletters.

## Blueprints & routing

19 blueprints register under `/api` in `main.py`; **order matters** — specific public
blueprints (`players_bp`, `journey_bp`, `scout_bp`, `showcase_bp`) register before `api_bp`
so their routes win. A new `api.py` route that collides with a public path silently never
fires (architecture.md). `/api/health` lives in `api.py`.

## Player-data gotchas (the ones that bite)

- First-team `TrackedPlayer`s frequently have **NULL `current_club_api_id`** — degrade
  gracefully, never assume the parent club.
- Stats have two coverage tiers: `FixturePlayerStats` (full) vs `PlayerStatsCache` (limited);
  `TrackedPlayer.compute_stats()` reads both. Youth stats are separate (`AcademyAppearance`).
- Never let a placeholder `Player NNNN` overwrite a real `player_name` (invariants.md §5); the
  owning-club and academy-window rules (§3, §4) constrain what the journey sync may create.

## Verify a backend change before shipping

Don't rely on ruff alone — exercise the endpoint. Run locally (`python src/main.py`), mint an
admin Bearer if the route needs it, and curl `/api/health` plus the changed route. For anything
touching journey/stats, remember prod can't take a bulk run (invariants.md §7) — validate against
local/spike data.
