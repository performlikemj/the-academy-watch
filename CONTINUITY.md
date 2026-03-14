# CONTINUITY.md

> Master ledger — canonical project state. Read this first every turn.

## Goal

The Academy Watch — Football academy tracking platform with AI-powered newsletters and journalist content management.

## Constraints / Assumptions

- Backend runs on Flask (port 5001)
- Frontend runs on React/Vite (port 5173, proxies /api to backend)
- PostgreSQL database
- Deployed to Azure Container Apps

## Key Decisions

- Using AGENTS.md + Ralph workflow for autonomous task execution
- Planning ledgers track task status for handoff between interactive and autonomous modes

## State

### Done
- Agent workflow setup (AGENTS.md, Ralph scripts, ledger structure)
- Agent protocol integration into CLAUDE.md
- "The Academy Watch" refactor planning and analysis
- Phase 1: Foundation (Stripe removal, branding, pathway columns)
- Phase 2: Community Takes (complete)
  - CommunityTake and QuickTakeSubmission models + migration
  - Public submission API with rate limiting
  - Admin curation endpoints (approve/reject/create/stats)
  - AdminCuration dashboard page
  - QuickTakeForm component and /submit-take page
  - Newsletter template integration (shows approved takes)
  - Submit take CTA in newsletter footer
- Phase 3: Reddit Integration (skipped - no API access)
- Phase 4: Academy Tracking (complete)
  - AcademyLeague and AcademyAppearance models + migration
  - Academy sync service (fetches fixtures, lineups, events)
  - Admin API endpoints for league management and sync
  - AdminAcademy dashboard page
  - Academy section in newsletter template
  - Limited data handling (Started/Sub badges, G+A when available)
  - 4.8: Pathway progression UI in AdminLoans (status/level editing, badges, filters)
- Phase 5: Polish & Launch (in progress)
  - 5.1: E2E tests for Academy Watch features (complete)
    - `e2e/academy-watch.spec.js` - tests for SubmitTake, AdminCuration, AdminAcademy, pathway status
    - Database helpers in `e2e/helpers/db.js` for test cleanup
  - 5.4: Security review for `/community-takes/submit` (complete)
    - Flask-Limiter decorators (10/min, 30/hour)
    - Input sanitization via bleach
    - Email format validation
    - Duplicate content detection (24h window)
- Cohort ingestion remediation (implementation complete)
  - Dynamic API-Football youth league resolution with static fallback defaults
  - Dynamic parent-club -> youth-team ID resolution for seeding combos
  - Full Rebuild stage-2 academy league rows now seeded/updated from dynamic resolver
  - Cohort discovery now supports separate query team ID (`query_team_api_id`)
  - Sync-state hardening for `journey_synced` and cohort `complete/partial/failed/no_data`
  - Phase 2 journey sync timeout isolation added (`PLAYER_SYNC_TIMEOUT=90`) with per-player skip on timeout
  - Constrained live rebuild smoke run passed (`team=49`, `league=696`, `season=2022`): 1 cohort, 40/40 players synced
  - Targeted tests passed (`test_youth_competition_resolver.py`)

### Now
- Player Journey feature (complete - needs migration and testing)
  - Interactive map showing career path from academy to first team
  - `PlayerJourney`, `PlayerJourneyEntry`, `ClubLocation` models
  - `JourneySyncService` - fetches from API-Football, classifies levels
  - 50+ major club coordinates seeded
  - `JourneyMap.jsx` component with Leaflet
  - `JourneyTimeline.jsx` fallback component
  - Integrated into PlayerPage with new "Journey" tab
  - E2E tests: `e2e/journey.spec.js`
  - Backend tests: `tests/test_journey.py`
- **See `ledgers/ACADEMY_WATCH_IMPLEMENTATION_PLAN.md` for detailed status**
- Cohort ingestion remediation (in progress)
  - Validate full multi-team Full Rebuild in deployed container with timeout telemetry
  - **See `ledgers/CONTINUITY_cohort-dynamic-resolution.md`**

### Next
- Run migration: `flask db upgrade`
- Install frontend deps: `cd academy-watch-frontend && pnpm install`
- Seed club locations: `POST /api/admin/journey/seed-locations`
- Test journey sync: `POST /api/admin/journey/sync/284324` (Garnacho)
- Run E2E tests: `pnpm test:e2e`

## Task Map

```
CONTINUITY.md
  └─ ledgers/CONTINUITY_plan-example.md (template - rename for actual work)
  └─ ledgers/CONTINUITY_cohort-dynamic-resolution.md (in-progress)
```

## Active Ledgers

| Ledger | Status | Owner | Blockers |
|--------|--------|-------|----------|
| ACADEMY_WATCH_REFACTOR_PLAN.md | complete | — | Phases 1-4 done |
| ACADEMY_WATCH_IMPLEMENTATION_PLAN.md | in-progress | — | Phases 1-5 done, Phase 6 ready |
| ACADEMY_WATCH_JOURNEY_REDESIGN.md | complete | — | Design doc for journey feature |
| CONTINUITY_cohort-dynamic-resolution.md | in-progress | codex | pending live Full Rebuild validation |

## Trivial Log

- 2026-02-12: Academy data audit — all Big 6 teams show 0% conversion due to journey sync never completing
- 2026-02-12: Fixed Full Rebuild journey sync: added RateLimiter, quota-exceeded break, non-fatal Stage 3, empty-journey bug fix
- 2026-02-12: Added Phase 2 journey sync timeout guard (`PLAYER_SYNC_TIMEOUT=90`) and verified a live constrained rebuild completes without hangs
- 2026-01-10: Fixed agent protocol - made AGENTS.md reading mandatory in CLAUDE.md

## Open Questions

- UNCONFIRMED: prior worker restarts were caused by health probe failure, OOM kill, or external restart policy.

## Working Set

**Key files:**
- `CLAUDE.md` - Claude Code instructions (auto-loaded)
- `AGENTS.md` - Agent operating protocol
- `scripts/ralph/` - Autonomous execution scripts
- `ledgers/` - Planning and task ledgers

**Useful commands:**
```bash
# Backend
cd academy-watch-backend && python src/main.py

# Frontend
cd academy-watch-frontend && pnpm dev

# Tests
cd academy-watch-frontend && pnpm test:e2e

# Ralph autonomous mode
./scripts/ralph/ralph.sh 25
```
