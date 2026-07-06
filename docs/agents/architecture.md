# Architecture — system map + the player data model

Read this before touching player tracking, journey sync, stats, or the pipelines
that feed them. `ARCHITECTURE.md` at the repo root has the exhaustive wiring
(API-Football modes, CSP/auth, every endpoint); this is the shape you must hold
in your head so you don't optimize the wrong thing.

## The planes

```
academy-watch-frontend/ (React 19 + Vite 6 + Tailwind 4 + Radix)
  Admin dashboard (14 pages) · Writer interface · public Player/Team pages · journey maps
        │  dev: Vite proxies /api/* → http://localhost:5001 (vite.config.js)
        │  prod: VITE_API_BASE baked in at build time (Azure SWA has no proxy)
        ▼
academy-watch-backend/src/ (Flask 3.1 + SQLAlchemy 2.0)
  main.py           app init, 19 blueprints (registration order matters — below)
  routes/           api.py (admin+core, /health), players.py, teams.py, journalist.py,
                    academy.py, journey.py, cohort/curator/gol/formation/feeder/showcase/…
  services/         journey_sync.py, academy_sync_service.py, radar_stats_service.py, email/reddit/stripe/gol
  models/           league.py (30+ core), tracked_player.py, journey.py, weekly.py
  agents/           AI newsletter generation
  utils/            academy_classifier.py, academy_window.py, player_names.py, team resolution
        ▼
Supabase Postgres (snqwamzutbcbjgusubsa, us-west-1) — RLS on all public tables, Alembic migrations
        │  reached via IPv4 pooler + postgresql+psycopg:// (see invariants.md §1)
External: API-Football (all football data) · Stripe Connect (10% platform fee) · Mailgun · Reddit · OpenAI
```

## Blueprint registration order (main.py) is load-bearing

`players_bp`, `journey_bp`, `scout_bp`, `showcase_bp` are all registered **before**
`api_bp` (all under `/api`). Flask resolves the first-registered match, so those
specific `/api/players/*` etc. routes win over `api_bp`'s catch-alls. Adding a
route to `api.py` that collides with a public path will silently never fire —
register the specific blueprint earlier, don't reorder blindly.

## The core object: `TrackedPlayer` (models/tracked_player.py)

One row **per player per parent academy club**. This is the spine of the product.

- `team_id` = the parent academy club (origin). `current_club_api_id` /
  `current_club_db_id` = where the player plays now (loan destination or buying club).
  First-team `TrackedPlayer`s often have **NULL `current_club_api_id`** — consumers
  must degrade gracefully, never assume the parent club.
- Pathway status (`academy → on_loan → first_team → released → sold`) is assigned by
  `classify_tracked_player()` (utils/academy_classifier.py) from journey + transfer data.
- `compute_stats()` aggregates from `FixturePlayerStats` (full coverage, top leagues)
  or falls back to `PlayerStatsCache` (limited-coverage lower leagues). Academy/youth
  stats live separately in `AcademyAppearance` (served by `/players/<id>/academy-stats`).
- `player_name` must always be a real name — placeholder `Player NNNN` is resolved via
  `resolve_player_name()` (utils/player_names.py) and a placeholder must NEVER overwrite
  a real name (invariants.md §5).

## The pipelines (all fed by API-Football)

1. **Player tracking**: API-Football → `TrackedPlayer` records.
2. **Stats sync**: fixtures → `FixturePlayerStats` → `TrackedPlayer.compute_stats()`.
3. **Academy stats**: youth-league fixtures (U18/U21/U23) → `AcademyAppearance`.
4. **Journey sync** (`services/journey_sync.py`): transfers/seasons →
   `PlayerJourney` + `PlayerJourneyEntry` (full career). `_correct_club_ids_from_transfers()`
   fixes API-Football returning the *current* team for historical seasons;
   `_merge_corrected_duplicates()` dedupes afterward. This sync is what decides
   academy-club membership and the academy window (invariants.md §3, §4).
5. **Newsletters**: admin creates → writers add commentary → Mailgun delivery.
6. **Payments**: Stripe Connect for writer monetization (10% platform fee).

## Cost/shape you must respect

Prod runs on **0.5 CPU / 1Gi / 1–2 replicas** — see invariants.md §7 before any
bulk sync/recompute/backfill; the live container cannot absorb background work.
The API-Football `api_cache` table dominates DB size; a pg_cron job purges it daily
(debugging.md covers DB bloat).
