# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**The Academy Watch** is a football (soccer) academy tracking platform that monitors academy players on loan, generates AI-powered newsletters, and enables journalists to write content about loaned players. It integrates with API-Football for player/fixture data, Stripe for payments, Mailgun for email delivery, and Reddit for social posting.

## Development Commands

### Backend (Flask)
```bash
cd academy-watch-backend

# Run development server (port 5001)
python src/main.py

# Run with virtual environment
../.loan/bin/python src/main.py

# Database migrations
flask db upgrade                    # Apply migrations
flask db migrate -m "description"   # Create new migration
flask db downgrade                  # Rollback one migration
```

### Frontend (React/Vite)
```bash
cd academy-watch-frontend

pnpm install          # Install dependencies
pnpm dev              # Dev server (port 5173, proxies /api to :5001)
pnpm build            # Production build
pnpm lint             # ESLint
```

### Testing
```bash
cd academy-watch-frontend

# Run all Playwright E2E tests
pnpm test:e2e

# Run a single test file
pnpm exec playwright test tests/admin-teams.test.mjs

# Run tests with UI
pnpm exec playwright test --ui
```

### Deployment
```bash
# CI auto-deploys on push to main (GitHub Actions → Azure Container Apps)
# Manual deployment (rarely needed):
./deploy_aca.sh
```

### Container Access
```bash
# Exec into production container
az containerapp exec --name ca-loan-army-backend --resource-group rg-loan-army-westus2 --command /bin/sh

# Run migrations in container
FLASK_APP=src/main.py flask db upgrade

# The Dockerfile only copies src/ and migrations/ — scripts at repo root are NOT in the image
# Place runnable scripts in src/scripts/ to include them
```

### Alembic Migrations
- All migrations use idempotent helpers from `migrations/_migration_helpers.py` (column_exists, table_exists, etc.)
- Production DB has had columns/tables added out-of-band — always guard DDL operations
- Current migration head chain: aw11 → aw12 → aw13

## Architecture

### Tech Stack
- **Frontend**: React 19 + Vite 6 + Tailwind CSS 4 + Radix UI
- **Backend**: Flask 3.1 + SQLAlchemy 2.0 + Alembic
- **Database**: PostgreSQL
- **Deployment**: Azure Container Apps (backend), Azure Static Web App (frontend)

### Directory Structure
```
academy-watch-backend/src/
├── main.py                 # Flask app init, blueprint registration
├── routes/
│   ├── api.py              # Admin + core API endpoints
│   ├── players.py          # Public player endpoints (stats, profile, season-stats)
│   ├── teams.py            # Team listings, loan data
│   ├── journalist.py       # Writer/journalist endpoints
│   ├── academy.py          # Academy league sync + stats
│   ├── journey.py          # Player career journey/map
│   └── ...                 # cohort, curator, gol, formation, feeder
├── models/
│   ├── league.py           # Core domain models (30+)
│   ├── tracked_player.py   # TrackedPlayer model (primary player tracking)
│   ├── journey.py          # PlayerJourney + PlayerJourneyEntry
│   └── weekly.py           # Fixture/stats models
├── services/
│   ├── journey_sync.py     # Career data sync from API-Football
│   ├── academy_sync_service.py  # Youth league fixture sync
│   ├── radar_stats_service.py   # Per-90 stats + radar charts
│   └── ...                 # email, reddit, stripe, gol
├── agents/                 # AI newsletter generation
├── admin/sandbox_tasks.py  # Admin diagnostic tasks
└── utils/
    ├── academy_classifier.py  # Player status classification
    └── ...                    # team resolution, markdown, sanitization

academy-watch-frontend/src/
├── pages/
│   ├── PlayerPage.jsx      # Player detail (stats, journey, academy stats)
│   ├── TeamDetailPage.jsx  # Team page with squad listing
│   ├── admin/              # Admin dashboard (14 pages)
│   └── writer/             # Writer interface
├── components/ui/          # Radix-based UI components
└── lib/api.js              # API service wrapper (all endpoint methods)
```

### Blueprint Registration Order
Blueprints are registered in `main.py` — order matters for route conflicts:
- `players_bp` is registered BEFORE `api_bp` so `/players/*` routes in `players.py` take priority

### Key Data Flow
1. **Player Tracking**: API-Football → `TrackedPlayer` records (one per player per parent academy club)
2. **Stats Sync**: Fixtures → `FixturePlayerStats` → `TrackedPlayer.compute_stats()` for aggregation
3. **Academy Stats**: Youth league fixtures → `AcademyAppearance` records (U18/U21/U23 leagues)
4. **Journey Sync**: API-Football transfers/seasons → `PlayerJourney` + `PlayerJourneyEntry` (full career history)
5. **Newsletters**: Admin creates → Writers add commentaries → Email delivery via Mailgun
6. **Payments**: Stripe Connect for writer monetization (10% platform fee)

### API Proxy
Frontend dev server proxies `/api/*` requests to `http://localhost:5001` (see `vite.config.js`).

## Important Patterns

### Database Models
Core models in `academy-watch-backend/src/models/league.py`:
- `Team`, `Newsletter`, `PlayerStatsCache` - core domain
- `UserAccount`, `UserSubscription` - users and email subscriptions
- `JournalistTeamAssignment` - writer assignments to teams
- `StripeConnectedAccount`, `StripeSubscription` - payments
- `AcademyLeague`, `AcademyAppearance` - youth league tracking

Player tracking in `models/tracked_player.py`:
- `TrackedPlayer` - one row per player per parent academy club, tracks pathway status (academy → on_loan → first_team → released → sold)
- `compute_stats()` method aggregates from `FixturePlayerStats` (full coverage) or `PlayerStatsCache` (limited coverage)
- `current_club_api_id` / `current_club_db_id` - where the player currently plays (loan destination or buying club)
- `team_id` - parent academy club (origin)

Journey models in `models/journey.py`:
- `PlayerJourney` - master career record per player
- `PlayerJourneyEntry` - individual season/club/competition entries

Weekly models in `models/weekly.py`:
- `Fixture`, `FixturePlayerStats` - match and performance data

### IMPORTANT: Deleted Models
The `AcademyPlayer` (table `loaned_players`) and `SupplementalLoan` (table `supplemental_loans`) models have been **permanently deleted** and their tables dropped. Do NOT reference these anywhere in code. Use `TrackedPlayer` for all player tracking.

### Team Name Resolution
`resolve_team_name_and_logo()` in `api.py` handles team ID → name resolution with caching to `TeamProfile`.

### Player Stats
- **Full coverage** (top leagues): Aggregated from `FixturePlayerStats` via `TrackedPlayer.compute_stats()`
- **Limited coverage** (lower leagues): Stored in `PlayerStatsCache`, read by `TrackedPlayer.compute_stats()`
- **Academy stats** (youth leagues): Stored in `AcademyAppearance`, served by `/players/<id>/academy-stats`

### Player Status Classification
`classify_tracked_player()` in `utils/academy_classifier.py` determines player status:
- Uses journey data + transfer history to classify as academy/on_loan/first_team/sold/released
- For sold/released players, preserves `current_club_api_id` (destination club)
- Prefer academy-origin TrackedPlayer rows over owning-club rows in queries (use `data_source != 'owning-club'` ordering)

### Journey Sync
`JourneySyncService` in `services/journey_sync.py`:
- `_correct_club_ids_from_transfers()` fixes API-Football returning current team for historical seasons
- `_merge_corrected_duplicates()` deduplicates entries after club ID correction


## Environment Variables

Key variables (see `academy-watch-backend/env.template` for full list):
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` - PostgreSQL
- `API_FOOTBALL_KEY`, `API_FOOTBALL_MODE` - Football data API
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` - Payments
- `MAILGUN_API_KEY`, `MAILGUN_DOMAIN` - Email delivery
- `ADMIN_API_KEY` - Admin endpoint authentication

## Agent Protocol (MANDATORY)

**CRITICAL: Before starting ANY work, you MUST:**

1. **Read `AGENTS.md`** - Contains operating principles, ledger protocol, and task flow rules
2. **Read `CONTINUITY.md`** - Master ledger with current project state and active tasks
3. **Check for active planning ledgers** in `ledgers/` directory

**This is not optional.** These files are the single source of truth for project state.

### Key Rules from AGENTS.md

- **Ledger-first:** Update CONTINUITY.md when state changes (goals, decisions, blockers)
- **Task statuses:** `pending` → `ready` → `in-progress` → `complete`
- **Quality bar:** Lint/typecheck must pass before marking work complete
- **Trivial tasks** (<15 min, single file): Log one-liner in CONTINUITY.md's Trivial Log

### Harness

Run `~/bin/harness-check --project . --scope staged` before every commit. Pre-commit hooks enforce this automatically (ruff lint, ruff format, secret scan). See `rules/harness.md` for the full protocol. Auto-fix: `~/bin/harness-check --project . --scope staged --fix`. If hooks are missing: `~/bin/harness-install .`

### Ralph Autonomous Mode

When running via `./scripts/ralph/ralph.sh`:
- Pick ONLY `ready` tasks from the active planning ledger
- Complete ONE task per iteration
- Update ledger status and commit after each task
- Output `<ralph>COMPLETE</ralph>` when all tasks done
- Output `<ralph>STOP</ralph>` when blocked
