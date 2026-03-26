# Operations Guide

How the automated maintenance jobs work and when to use them.

## Scheduled Jobs (run automatically)

### job-transfer-heal — Daily 3 AM UTC
**Purpose:** Keeps player statuses current by detecting transfers and loan changes.

**What it does:**
- During transfer windows (Jan 1–Feb 7, Jun 1–Sep 7): full journey resync from API-Football for every tracked player
- Outside windows: lighter status refresh using cached data
- Cross-references transfers to update current club for players who moved but haven't played yet
- Auto-deactivates stale duplicate TrackedPlayer rows

**When you'd manually trigger it:** After a major transfer (e.g., deadline day) and you want data updated immediately instead of waiting for 3 AM.

### job-sync-fixtures — Daily 5 AM UTC
**Purpose:** Keeps match stats and formation data current.

**What it does:**
- Fetches new fixture results from API-Football for all tracked players
- Populates FixturePlayerStats (goals, assists, minutes, rating, etc.)
- Captures formation and tactical position (e.g., "LB in a 4-3-3")
- Updates aggregated season stats

**When you'd manually trigger it:** After a busy matchday if you want stats updated before the next morning.

## Manual Jobs (triggered on demand)

### job-full-rebuild — Nuclear option
**Purpose:** Wipes all academy/journey/tracked data and rebuilds from scratch.

**What it does (7 stages):**
1. Clean slate — deletes all TrackedPlayers, journeys, cohorts
2. Seed academy leagues from API-Football
3. Discover cohorts + sync all player journeys (longest stage — hours)
4. Create TrackedPlayer records for all tracked teams
5. Link orphaned journeys
6. Refresh statuses via transfer classifier
7. Seed club locations

**Runtime:** 6–12+ hours. Has an 18-hour timeout.

**When to use:** After major code changes to the classification algorithm, or when accumulated data drift makes incremental fixes impractical. Shows a "building database" banner on the frontend while running.

**⚠️ Caution:** Wipes all player data. The site will show empty/partial data during the rebuild.

### job-data-fix — Incremental repair
**Purpose:** Fixes specific data gaps without wiping anything.

**What it does (5 phases, all idempotent):**
1. Backfill team_profiles for teams missing names (fixes "Team 419" in GOL)
2. Backfill player records for players missing names (fixes numeric IDs in GOL)
3. Recompute academy_club_ids from journey entries (no API calls — DB only)
4. Refresh statuses using existing journey data + fresh transfers
5. Backfill formation data for fixture stats gaps

**Runtime:** 1–2 hours.

**When to use:** After a full rebuild to clean up remaining gaps, or periodically when you notice data quality issues.

### job-status-refresh — Force reclassify
**Purpose:** Re-runs the status classifier for all players with full journey resync.

**Runtime:** 1–4 hours.

**When to use:** When you suspect statuses are wrong (e.g., players showing as on_loan when they've been permanently sold).

## Key Concepts

### Academy Product Filter
`is_academy_product()` is the single gate that determines whether a player appears on a team's page or in its newsletter. A player is an academy product of a team if:
- Their `academy_club_ids` (from journey analysis) includes that team, OR
- They have no academy data but were discovered through academy pipelines (not bought)

Bought players (owning-club rows) are excluded from academy views but exist in the DB so the GOL bot can show correct parent clubs for loan display.

### TrackedPlayer Row Types
Each player can have multiple rows:
- **Academy-origin** (`data_source: journey-sync`): Links player to their youth academy. This is how they appear on the academy's Teams page.
- **Owning-club** (`data_source: owning-club`): Links player to their current contract holder. Used for GOL bot parent club display.

The stale row cleanup (runs automatically in transfer-heal) deactivates academy-origin rows when they're superseded by an owning-club row.

### Transfer Classification
- `"Loan"` → player is on loan, status = `on_loan`
- `"Transfer"`, `"€ 22.5M"`, `"Free"` → permanent move, status = `sold`
- No transfer record for current club → assumed permanent, status = `sold`
- `"N/A"` → treated as released

### GOL Bot Cache
The GOL Analytics bot caches DataFrames for 5 minutes. After data fixes, you can force a refresh via:
- Admin endpoint: `POST /api/admin/gol/refresh-cache`
- Or wait 5 minutes for auto-refresh

## How to Check Job Status

### From Azure CLI
```bash
# List recent executions
az containerapp job execution list --name JOB_NAME \
  --resource-group rg-loan-army-westus2 -o table

# Check specific execution
az containerapp job execution show --name JOB_NAME \
  --resource-group rg-loan-army-westus2 \
  --job-execution-name EXECUTION_NAME \
  --query "{status:properties.status}" -o tsv
```

### From the frontend
Full rebuilds show a banner: "We're building the academy database" with stage progress.

### From the database
```sql
SELECT status, current_player, progress, total
FROM background_jobs
WHERE job_type = 'full_rebuild'
ORDER BY created_at DESC LIMIT 1;
```

## How to Trigger a Manual Job

```bash
az containerapp job start --name JOB_NAME \
  --resource-group rg-loan-army-westus2
```

Job names: `job-transfer-heal`, `job-sync-fixtures`, `job-full-rebuild`, `job-data-fix`, `job-status-refresh`
