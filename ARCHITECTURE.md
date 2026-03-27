# Architecture & Configuration

How everything in The Academy Watch is wired together.

## System Overview

```
┌─────────────────────────────────────────────────────────┐
│           Frontend (React 19 + Vite 6 + Tailwind 4)     │
│                                                         │
│  Admin Dashboard (14 pages)  ·  Writer Interface        │
│  Public Player Pages  ·  Journey Timeline  ·  Maps      │
│  Radix UI components  ·  Stripe.js payments             │
└──────────────────────────┬──────────────────────────────┘
                           │  /api/* proxy (dev → :5001)
                           │  VITE_API_BASE (prod)
┌──────────────────────────▼──────────────────────────────┐
│           Backend (Flask 3.1 + SQLAlchemy 2.0)          │
│                                                         │
│  13 Blueprints  ·  50+ API endpoints                    │
│  Talisman (CSP/HSTS)  ·  Flask-Limiter  ·  CORS        │
│  require_api_key + Bearer token (dual-factor admin)     │
│                                                         │
│  ┌─────────────┐ ┌──────────┐ ┌───────────┐            │
│  │ API-Football │ │ Mailgun  │ │  Stripe   │            │
│  │   Client     │ │ + SMTP   │ │  Connect  │            │
│  └──────┬───────┘ └────┬─────┘ └─────┬─────┘            │
│         │              │             │                   │
│  ┌──────┴───┐   ┌──────┴──┐   ┌─────┴──────┐           │
│  │ Reddit   │   │ OpenAI  │   │ Brave MCP  │           │
│  │ Posting  │   │ (AI     │   │ (enriched  │           │
│  │          │   │  news)  │   │  context)  │           │
│  └──────────┘   └─────────┘   └────────────┘           │
└──────────────────────────┬──────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────┐
│             PostgreSQL (Supabase)                        │
│                                                         │
│  35+ models  ·  RLS enabled  ·  Alembic migrations      │
│  Connection pooling (pre-ping, 300s recycle)             │
└─────────────────────────────────────────────────────────┘
```

## API-Football Integration

The core data pipeline. All football data (players, fixtures, stats, transfers) comes from [API-Football v3](https://www.api-football.com/documentation-v3).

**Client:** `academy-watch-backend/src/api_football_client.py`

### Authentication Modes

| Mode | Base URL | Header | When to use |
|------|----------|--------|-------------|
| `direct` | `v3.football.api-sports.io` | `x-apisports-key` | Production (default) |
| `rapidapi` | `api-football-v1.p.rapidapi.com/v3` | `X-RapidAPI-Key` + `X-RapidAPI-Host` | Alternative billing |
| `stub` | None | None | Offline testing only |

Set via `API_FOOTBALL_MODE` env var. Stub mode requires explicit `API_USE_STUB_DATA=true`.

### Endpoints Used

| Endpoint | Purpose | Cache TTL |
|----------|---------|-----------|
| `status` | Health check, quota info | Never cached |
| `players?id=X&season=Y` | Player profile, position, season totals | 7-30 days |
| `players/seasons?player=X` | Available seasons for a player | 7 days |
| `transfers?player=X` | Transfer history (includes fee in `type` field) | 24h (in-season), 7d (off-season) |
| `fixtures?team=X&season=Y&from=D&to=D` | Team fixtures in date range | 10 years (completed), 6h (upcoming) |
| `fixtures/players?fixture=X` | Per-player stats for a fixture (full coverage) | 10 years |
| `fixtures/lineups?fixture=X` | Starting XI + substitutes (limited coverage fallback) | 10 years |
| `fixtures/events?fixture=X` | Goals, cards, substitutions (limited coverage fallback) | 10 years |
| `teams?id=X` | Team info (name, logo, venue) | 30 days |
| `leagues?id=X` | League info + coverage flags | 30 days |

### Caching Strategy (3 Layers)

**Layer 1 — In-memory (per-process, 24hr TTL):**
- Transfer cache: `{player_id: (data, timestamp)}`
- Player stats cache: `{(player_id, season): (data, timestamp)}`
- Player-team-season totals: `{(player_id, team_id, season): (data, timestamp)}`
- Team name/profile cache (no expiry, populated lazily)

**Layer 2 — Database (`APICache` table):**
- Keyed by endpoint + params hash
- TTL varies by data type (see table above)
- Completed fixtures cached for 10 years (immutable data)
- Empty responses cached for 5 minutes (retry soon)

**Layer 3 — Fixture records:**
- Completed fixtures stored in `Fixture` table with `raw_json`
- `get_fixtures_for_team_cached()` checks DB first, then API for new/upcoming games
- Deduplicates by `fixture_id_api`

### Rate Limiting & Quota

- Tracks `X-RateLimit-Remaining` header from API responses
- Optional daily limit via `API_FOOTBALL_DAILY_LIMIT` env var
- Tracked per-endpoint in `APIUsageDaily` table
- Exceeding quota raises `RuntimeError`, blocking further calls
- Batch sync uses configurable `delay` parameter between fixture API calls (default 0.1s)

### Season Calculation

Season is derived dynamically, never hardcoded:
- Aug-Dec → season = current year (e.g., 2025 = "2025-2026")
- Jan-Jul → season = previous year (e.g., Jan 2026 = "2025-2026")
- For players with a `window_key` (e.g., `"2025-26::SUMMER"`), season is extracted from the key

### Data Sync Pipeline

```
API-Football                    Database                      Frontend
───────────                     ────────                      ────────

/fixtures?team=X ──────────► Fixture table
                               (fixture_id_api, date,
                                home/away teams, score)
                                        │
/fixtures/players?fixture=X ──► FixturePlayerStats table
                               (player_api_id, team_api_id,
                                minutes, goals, assists,
                                position, rating, ...)
                                        │
/fixtures/lineups?fixture=X ────► formation, grid, formation_position
                                  (team formation + player tactical role)
                                        │
                              _compute_stats() aggregates ──► Player stats
                               COUNT(*) as appearances        on page
                               SUM(goals), SUM(assists)...
```

### Sync Triggers

| Trigger | Scope | When |
|---------|-------|------|
| Page visit | Single player | User views `/players/{id}/stats` — compares API totals vs local count |
| Admin single sync | Single player | `POST /admin/players/{id}/sync-fixtures` |
| Admin team sync | All players at one academy | `POST /admin/teams/{id}/sync-all-fixtures` |
| Batch sync | All tracked players | `POST /admin/sync-all-player-fixtures` |

The batch sync groups players by their current team to minimize API calls — `O(teams × fixtures)` not `O(players × fixtures)`. For sold/released players with no team on record, it discovers their current team via the `/players` endpoint and backfills `TrackedPlayer.current_club_api_id`.

### Team Squad Seeding

Each tracked team's full squad is populated via `get_team_players(team_api_id, season)` which calls the API-Football `/players?team=X&season=Y` endpoint. This returns the complete roster (25-50 players per team) with profile info (name, photo, position, nationality, age, birth date).

**Seeding process:**
1. For each `is_tracked=true` team, fetch the current season squad
2. Create a `TrackedPlayer` record for each player with `status='first_team'` and `data_source='api-football'`
3. The unique constraint `(player_api_id, team_id)` prevents duplicates — existing players are skipped
4. Status classification (`classify_tracked_player()` in `academy_classifier.py`) refines statuses later: academy, on_loan, first_team, sold, released

**Admin endpoint:** `POST /admin/tracked-players/seed-team` — seeds a single team with optional journey sync.

**Important:** The `Team` table must have exactly one row per `team_id` (API-Football ID). Duplicate records cause players to be created under the wrong team and become invisible on the frontend. The `teams.team_id` column should be treated as a unique identifier even though it's not enforced at the DB level.

### Club-First Default (National Team Filtering)

API-Football's `/players` endpoint returns statistics for **all teams** a player appeared for — including national teams (e.g., Argentina, England U21). When discovering teams for sold/released players, both the batch sync and on-demand stats endpoint **filter out national teams** using `is_national_team()` from `utils/academy_classifier.py`, then pick the **club with the most appearances**.

This ensures:
- **Default view** (header stats, Performance Analysis charts) shows club data
- **International data** is preserved in the journey timeline and accessible by clicking the national team node
- `TrackedPlayer.current_club_api_id` is always a club, never a national team

The position fallback chain also prioritizes club data: `Player.position` → `TrackedPlayer.position` → most recent `FixturePlayerStats.position` (from club matches). The frontend uses the backend profile position as the initial value, overridden by stats-inferred position if match data exists.

### Coverage Tiers

| Tier | Source | Leagues | Stats available |
|------|--------|---------|----------------|
| **Full** | `/fixtures/players` | Top 5 (PL, La Liga, Serie A, Bundesliga, Ligue 1) | Minutes, rating, shots, passes, tackles, duels, dribbles, cards, saves |
| **Limited** | `/fixtures/lineups` + `/fixtures/events` | Lower leagues | Appearances, goals, assists, cards only |
| **None** | Manual entry | Uncovered leagues | Whatever is entered manually |

Determined by `stats_coverage` field on `AcademyPlayer` and validated via `check_league_stats_coverage()` which checks the league's `coverage.fixtures.statistics_players` flag.

### Transfer Detection

Transfer types from the API `type` field:
- `"Loan"` → new loan (player going out)
- `"Back from Loan"` / `"End of Loan"` etc. → loan return
- `"Free"` / `"Free Transfer"` / `"Free agent"` → permanent, no fee
- `"€ 50M"` / `"€ 25.5M"` → permanent with fee amount
- `"Transfer"` → permanent, fee undisclosed
- `"N/A"` → treated as `released` (free departure)

The `extract_transfer_fee()` function returns the raw fee string for non-loan transfers, stored on `TrackedPlayer.sale_fee`.

### Player ID Verification

API-Football sometimes uses different player IDs across endpoints (squad/transfer vs fixture). `verify_player_id_via_fixtures()` checks recent fixture lineups to find the correct ID by matching player name, and auto-corrects `AcademyPlayer.player_id` if a mismatch is found.

## Data Model Relationships

```
Team (club — one row per API-Football team_id)
  │
  ├── TrackedPlayer (two row types per player)
  │     ├── Academy-origin rows (data_source: journey-sync | api-football | cohort-seed)
  │     │     team_id points to the academy club
  │     ├── Owning-club rows (data_source: owning-club)
  │     │     team_id points to current contract holder (for bought players)
  │     ├── status: academy | on_loan | first_team | sold | released
  │     ├── current_club_api_id (loan club, buying club, or new club)
  │     ├── sale_fee (transfer fee if sold, raw string e.g. "€50M")
  │     ├── position (Goalkeeper, Defender, Midfielder, Attacker)
  │     └── journey_id → PlayerJourney (lazy — synced on first page visit)
  │                         └── PlayerJourneyEntry[] (career stops)
  │                               ├── club, season, level, entry_type
  │                               ├── appearances, goals, assists
  │                               └── transfer_fee, transfer_date
  │
  ├── AcademyPlayer (one row per loan spell)
  │     ├── player_id (API-Football ID)
  │     ├── primary_team_id → Team (parent club)
  │     ├── loan_team_id → Team (loan club)
  │     ├── window_key ("2025-26::SUMMER")
  │     ├── stats_coverage (full | limited | none)
  │     └── _compute_stats() → aggregates from FixturePlayerStats
  │
  └── Team.team_id (API-Football team ID)
        │
        └── Fixture (match records)
              ├── fixture_id_api, date_utc, season
              ├── home_team_api_id, away_team_api_id
              └── FixturePlayerStats[] (per-player per-match)
                    ├── player_api_id, team_api_id
                    ├── minutes, position, rating
                    ├── formation (team formation e.g. "4-3-3")
                    ├── grid (player grid position e.g. "2:1"), formation_position (role e.g. "LB", "CAM")
                    ├── goals, assists, saves
                    └── shots, passes, tackles, duels, dribbles, cards
```

### Academy Classification Pipeline

Determines which team's academy a player belongs to. Core logic in `services/journey_sync.py`.

**Entry classification** (`_classify_level`): Each career entry gets a `level` (U15-U23, Reserve, First Team, International, International Youth) and `entry_type`:
- `academy` — genuine youth entry, no prior senior experience
- `development` — youth entry at a club where player already had first-team appearances (promoted player getting youth minutes)
- `integration` — youth entry at a club the player was transferred to with prior senior experience elsewhere (bought player being integrated)
- `first_team`, `loan`, `international` — non-youth types

**Reclassification** (`_apply_development_classification`): Three passes refine `academy` entries:
1. **Journey-based**: first-team at same club → `development`; first-team at different club → `integration` (with age/experience gate: ≤18 years old and ≤15 apps at other club are skipped as normal academy transfers)
2. **Transfer-based**: permanent transfer TO this club → `integration`
3. **Age-based**: first youth appearance at age 21+ → `integration`

**Academy ID computation** (`_compute_academy_club_ids`): Collects youth entries with `entry_type` in (`academy`, `development`), strips youth suffix from club names, resolves to parent club API IDs, removes permanent transfer destinations. Result stored as `PlayerJourney.academy_club_ids` JSON array.

**TrackedPlayer creation**: For each academy club ID, creates a `TrackedPlayer` row linking the player to that academy team.

### Academy Product Filter (Single Source of Truth)

`is_academy_product()` in `utils/academy_classifier.py` is the **sole gate** for determining whether a player appears on a team's page or in its newsletter. Used by:
- Teams page (`routes/api.py` — `/teams/{id}/players` endpoint)
- Newsletter pipeline (`agents/weekly_newsletter_agent.py`) — A1 filter
- GOL bot dedup (`services/gol_sandbox.py`) — `_dedup_tracked()`

Rules:
1. `academy_club_ids` contains team → **include** (confirmed academy product)
2. `academy_club_ids` exists but doesn't contain team → **exclude** (different academy)
3. No/empty `academy_club_ids` + `data_source='owning-club'` → **exclude** (bought player)
4. No/empty `academy_club_ids` + other source → **include** (benefit of doubt)

### Transfer Cross-Reference (Journey Sync)

`_update_journey_aggregates()` in `services/journey_sync.py` derives `current_club` from the `/players` endpoint (season stats), then cross-references against the `/transfers` endpoint. The most recent transfer overrides stats-based current_club:

- Most recent is **permanent** (e.g., `"€ 35M"`, `"Transfer"`, `"Free"`) → set current_club to destination, status = `first_team`
- Most recent is **loan** (`"Loan"`) → set current_club to loan destination
- Most recent is **loan return** (`"Back from Loan"`) → set current_club to return destination (parent club)

This handles players who transferred but haven't played yet at their new club (stats would still show the old club).

### Transfer Classification — Unrecorded Moves

When a player is at a club that has no "Loan" type transfer record in the API data, `upgrade_status_from_transfers()` classifies them as `sold` instead of defaulting to `on_loan`. This handles API-Football gaps where permanent transfers to lower leagues aren't always recorded.

### Confirmed Loan Protection

When `classify_tracked_player()` runs the squad cross-reference (Step 2.5), it first checks if the loan has a confirmed `"Loan"` type transfer in the API data. If confirmed, the squad check is skipped — transfer data is more authoritative than squad lists, which aren't updated mid-season for loans.

### Team Name Resolution (Single Source of Truth)

`resolve_team_name()` and `resolve_team_name_and_logo()` in `utils/team_resolver.py` are the shared functions for resolving API-Football team IDs to human-readable names. Used by API endpoints, newsletter pipeline, and any code that needs a team name.

Fallback chain: Team table → TeamProfile table → API-Football `/teams` endpoint → `"Team {id}"`.

### API-Football Data Gaps

API-Football's `/transfers` endpoint does not always have complete transfer records, especially for:
- Lower league permanent transfers (e.g., a player sold to a League Two club)
- Mid-season moves in non-European leagues (e.g., MLS → European club)
- Recent transfers that haven't been indexed yet

When transfer data is missing, the system falls back to stats-based inference, which can be wrong if the player hasn't played at their new club. The daily `job-transfer-heal` re-checks transfers and self-corrects as API-Football updates its records.

**For players with genuinely missing transfer data**, manual admin correction via the admin dashboard is the only option. This is a known limitation of relying on a third-party data source.

### Stale Row Cleanup

`refresh_and_heal()` in `services/transfer_heal_service.py` auto-deactivates stale academy-origin rows when a correct owning-club row exists for the same player. This prevents duplicates from leaking into queries.

### GOL Analytics Bot

AI-powered analytics assistant using pandas DataFrames loaded from the DB. See `services/gol_service.py`, `services/gol_sandbox.py`, `services/gol_dataframes.py`.

**DataFrames** (cached 5 min, `DataFrameCache` in `gol_dataframes.py`):
- `tracked` — all active TrackedPlayers with `parent_club` from teams join
- `fixture_stats` — per-match player stats with formation/grid/formation_position
- `players` — player name/photo cache (fallback for name resolution)
- `team_profiles` — team name/logo cache (fallback for team resolution)
- `journeys`, `journey_entries` — career data
- `fixtures`, `cohorts`, `cohort_members` — match and cohort data

**Admin cache endpoint**: `POST /api/admin/gol/refresh-cache` — forces DataFrame reload after data fixes.

### Newsletter Sections

Newsletters are structured with subsections:
- **First Team** — flat items list
- **On Loan** — subsections grouped by league (e.g., "Championship", "League One")
- **Academy Rising** — subsections grouped by level (e.g., "U21", "U18")

Both `_enforce_player_metadata()` and `lint_and_enrich()` process flat items AND subsection items.

## Deployment Topology

```
Azure Container Apps              Azure Static Web App
┌────────────────────┐           ┌────────────────────┐
│ ca-loan-army-      │           │ swa-goonloan       │
│ backend            │◄──────────│                    │
│                    │  API calls│ React SPA           │
│ Flask + Gunicorn   │           │ Built by Vite       │
│ Port 5001          │           └────────────────────┘
└────────┬───────────┘
         │
         ▼
Azure Container Registry          Azure Key Vault
┌────────────────────┐           ┌────────────────────┐
│ acrloanarmy        │           │ kv-loan-army       │
│                    │           │                    │
│ loanarmy/backend   │           │ secret-key         │
│ :prod              │           │ admin-api-key      │
└────────────────────┘           │ api-football-key   │
                                 │ supabase-db-*      │
Supabase                         │ stripe-*           │
┌────────────────────┐           │ mailgun-*          │
│ PostgreSQL         │           └────────────────────┘
│ aws-1-us-west-1    │
│ .pooler.supabase   │
│ .com               │
└────────────────────┘

Scheduled Jobs (Azure Container Apps Jobs):
  - job-transfer-heal: Daily 3AM UTC — transfer detection + status refresh
    (full journey resync during transfer windows, light refresh outside)
    Auto-deactivates stale duplicate rows after each run.
  - job-sync-fixtures: Daily 5AM UTC — batch fixture + player stats sync
  - job-full-rebuild: Manual — full data wipe and rebuild from scratch (12hr timeout)
  - job-data-fix: Manual — 5-phase incremental data integrity repair
  - job-status-refresh: Manual — force full status re-classification
```

### CI/CD

- **GitHub Actions** (`.github/workflows/deploy.yml`): Triggered on push to `main`
  1. Security checks (RLS verification via psql)
  2. Build backend Docker image → push to ACR
  3. Update Container App with new image
  4. Build frontend → deploy to Static Web App
  5. Update scheduled job images

- **Manual deploy**: `./deploy_aca.sh` — same steps, run locally

### Key Vault References

Container App env vars reference Key Vault secrets via `kvref:` URIs. The Container App's managed identity has `GET` permissions on the vault. Secrets are resolved at container startup.

## Environment Variables

See `academy-watch-backend/env.template` for the full list. Grouped summary:

| Group | Variables | Purpose |
|-------|-----------|---------|
| **Database** | `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` | PostgreSQL connection |
| **API-Football** | `API_FOOTBALL_KEY`, `API_FOOTBALL_MODE` | Football data source |
| **Flask** | `SECRET_KEY`, `FLASK_ENV`, `CORS_ALLOW_ORIGINS` | App config + security |
| **Auth** | `ADMIN_API_KEY`, `ADMIN_EMAILS`, `ADMIN_IP_WHITELIST` | Admin endpoint protection |
| **Stripe** | `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET` | Payment processing |
| **Email** | `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `SMTP_*` | Newsletter + transactional email |
| **Reddit** | `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`, `REDDIT_PASSWORD` | Social posting |
| **Brave/MCP** | `BRAVE_API_KEY`, `ENABLE_BRAVE_SEARCH` | Enriched newsletter context |
| **Dev/Test** | `TEST_ONLY_MANU`, `API_USE_STUB_DATA`, `SKIP_API_HANDSHAKE` | Development shortcuts |

## Backend Blueprints

| Blueprint | Prefix | Endpoints | Purpose |
|-----------|--------|-----------|---------|
| `api_bp` | `/api` | 50+ | Core API: players, teams, leagues, newsletters, admin sync |
| `auth_bp` | `/api` | 5 | Email-code login, token verification, user info |
| `journalist_bp` | `/api` | 20+ | Writer assignments, commentaries, Stripe payouts |
| `teams_bp` | `/api` | 10+ | Squad views, academy origins, departure tracking |
| `journey_bp` | `/api` | 3 | Player career journey (map, timeline, sync) |
| `academy_bp` | `/api` | 5 | Academy appearances, league tracking |
| `cohort_bp` | `/api` | 4 | Cohort-based player grouping and analysis |
| `community_takes_bp` | `/api` | 5 | Fan community submissions |
| `newsletter_deadline_bp` | `/api` | 3 | Newsletter deadline management |
| `curator_bp` | `/api` | 4 | Content curation tools |
| `formation_bp` | `/api` | 3 | Formation analysis |
| `feeder_bp` | `/api` | 2 | Feeder club relationships |
| `gol_bp` | `/api` | 3 | GOL Analytics Wizard (AI chat + cache admin) |

## Frontend API Proxy

In development, Vite proxies `/api/*` to `http://localhost:5001` (see `vite.config.js`).

In production, the frontend is built with `VITE_API_BASE` pointing to the backend's FQDN (e.g., `https://ca-loan-army-backend.lemonmoss-23c9ec03.westus2.azurecontainerapps.io/api`).
