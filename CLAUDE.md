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
# Full deployment to Azure Container Apps
./deploy_aca.sh
```

## Architecture

### Tech Stack
- **Frontend**: React 19 + Vite 6 + Tailwind CSS 4 + Radix UI
- **Backend**: Flask 3.1 + SQLAlchemy 2.0 + Alembic
- **Database**: PostgreSQL
- **Deployment**: Azure Container Apps (backend), Azure Static Web App (frontend)

### Directory Structure
```
academy-watch-backend/src/
├── main.py                 # Flask app initialization
├── routes/
│   ├── api.py              # Main API endpoints (50+)
│   ├── journalist.py       # Writer/journalist endpoints
│   └── stripe_*.py         # Stripe payment routes
├── models/
│   ├── league.py           # Core domain models (35+)
│   └── weekly.py           # Fixture/stats models
├── services/               # Business logic (email, reddit, stripe)
├── agents/                 # AI newsletter generation
└── utils/                  # Team resolution, markdown, sanitization

academy-watch-frontend/src/
├── pages/admin/            # Admin dashboard (14 pages)
├── pages/writer/           # Writer interface
├── components/ui/          # Radix-based UI components
└── lib/api.js              # API service wrapper
```

### Key Data Flow
1. **Player Tracking**: API-Football → `AcademyPlayer` records
2. **Stats Sync**: Fixtures → `FixturePlayerStats` → aggregated player stats
3. **Newsletters**: Admin creates → Writers add commentaries → Email delivery via Mailgun
4. **Payments**: Stripe Connect for writer monetization (10% platform fee)

### API Proxy
Frontend dev server proxies `/api/*` requests to `http://localhost:5001` (see `vite.config.js`).

## Important Patterns

### Database Models
Core models in `academy-watch-backend/src/models/league.py`:
- `Team`, `AcademyPlayer`, `TrackedPlayer`, `Newsletter` - core domain
- `UserAccount`, `UserSubscription` - users and email subscriptions
- `JournalistTeamAssignment` - writer assignments to teams
- `StripeConnectedAccount`, `StripeSubscription` - payments

Weekly models in `models/weekly.py`:
- `Fixture`, `FixturePlayerStats` - match and performance data

### Team Name Resolution
`resolve_team_name_and_logo()` in `api.py` handles team ID → name resolution with caching to `TeamProfile`.

### Player Stats
- **Full coverage** (top leagues): Aggregated from `FixturePlayerStats`
- **Limited coverage** (lower leagues): Denormalized columns on `AcademyPlayer`


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

### Ralph Autonomous Mode

When running via `./scripts/ralph/ralph.sh`:
- Pick ONLY `ready` tasks from the active planning ledger
- Complete ONE task per iteration
- Update ledger status and commit after each task
- Output `<ralph>COMPLETE</ralph>` when all tasks done
- Output `<ralph>STOP</ralph>` when blocked
