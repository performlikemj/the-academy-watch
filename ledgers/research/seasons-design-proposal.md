# Seasons System — Final Design Proposal (Phase C synthesis)

Written 2026-07-07 by the season-design-panel SYNTHESIS agent. Inputs: 3 competing designs
(rollup-first / compute-on-read / journey-canon) × 3 judge lenses (correctness / operations /
product). Season values = START YEARS (2025 = 2025-26). Verified against main: Alembic head
= **aw23** (vid03 → aw21 → aw22 → aw23), PJE grain = `uq_journey_entry (journey_id, season,
club_api_id, league_api_id)`, `fixture_player_stats.player_api_id` has NO standalone index.

## 1. Chosen architecture and why

**Winner: the rollup-first skeleton** — a precomputed, provenance-tagged per-player-per-season
read surface (fine source-cells table + coarse totals table), written only by sync hooks and
rebuild jobs, read by every hot path. It won on fatal-flaw asymmetry, not averages. Its judged
flaws are all graftable fixes: the wrong migration head (real head is aw23), upsert-only feeders
that orphan cells after journey club-ID corrections, a precedence rule that headlined stale
journey numbers mid-season, an Aug-1 resolver keyed on noisy rollup seasons, and a cup-fold
cross-source double-count. The losers' fatal flaws are structural to their theses: compute-on-read
leaves the Scout Desk fixtures-only forever (375 fixtures-invisible players — 35% of players with
2025 data, 225k real minutes — rank at ZERO, with the fix gated behind a performance condition a
coverage defect never triggers), and journey-canon rebuilds its rollup only inside journey sync,
so every totals surface freezes for the whole live season and the new season starts empty each
August (fixable only by quota-prohibitive weekly re-syncs). On a 0.5 CPU box with a documented
read-saturation incident, "every hot surface is one indexed row" is the only shape that stays
cheap as FPS grows ~100k rows/season — and it is the only design where fixtures-invisible players,
cup-inclusive totals, and historical seasons all work on list surfaces.

**Grafted onto the skeleton** (every judge-flagged flaw resolved): (a) journey-canon's
DELETE+INSERT per-(player, source) rebuild inside the same transaction as the source write, plus
an admin rebuild-all endpoint — the rollup is a reconstructable cache, never a second truth;
(b) compute-on-read's display rule — when fixtures > journey the HEADLINE is the larger
per-match-proven fixtures figure + a visible `journey-under-sync` flag (rollup-first's rule 3 is
rejected: never show a number our own match data disproves); (c) a **never-cross-source-sum**
aggregation rule (per-source totals, larger source wins whole) that eliminates the cup-fold
double-count by construction; (d) the season default resolver stays keyed on FIXTURES via Phase
A's `stats_season_with_data` — never on MAX(rollup.season), which PJE pre-season noise (740
season-2026 stub rows) would poison; (e) PJE is widened with the free rich fields (durable
archive; api_cache TTL is 7 days) and the extraction code ships BEFORE the MJ-gated 2025 re-sync;
(f) journey-canon's `league_season_config` + `level_group` axis and semantic reconcile-flag enum;
(g) compute-on-read's zero-migration PR1 (?season plumbing + Q12 date fixes + `ix_fps_player`)
ships first so users get season-scoped, provenance-labeled data before any new table exists;
(h) rollup-first's own keepers: fixtures-fed incremental refresh (centralized at ONE choke point
— FPS is written from ≥4 code paths), the dual-number provenance columns, and the
`SEASON_ROLLUP_READS` env-flag per-surface cutover with Phase-A paths as instant rollback.

## 2. Data model (DDL sketch — all guarded via `migrations/_migration_helpers`, RLS in-migration)

**Migration `sea01`** (`down_revision = "aw23"`) — widen PJE + missing indexes. No new tables.
```
ALTER player_journey_entries ADD (all nullable; add_column_safe):
  player_api_id INT,                      -- denormalized from journey; backfilled off-path
  rating FLOAT, position VARCHAR(10), lineups INT,
  shots_total INT, shots_on INT, passes_total INT, passes_key INT, passes_accuracy INT,
  tackles_total INT, tackles_blocks INT, tackles_interceptions INT,
  duels_total INT, duels_won INT, dribbles_attempts INT, dribbles_success INT,
  fouls_drawn INT, fouls_committed INT, cards_yellow INT, cards_red INT,
  penalty_scored INT, penalty_missed INT, penalty_saved INT, goals_conceded INT, saves INT,
  stats_source VARCHAR(24) DEFAULT 'legacy-basic',  -- 'journey-api'|'legacy-basic'|'manual'
  stats_synced_at TIMESTAMPTZ, season_phase VARCHAR(12)  -- dormant Apertura/Clausura hook
CREATE INDEX ix_fps_player ON fixture_player_stats (player_api_id);   -- verified missing
CREATE INDEX ix_pje_player_season ON player_journey_entries (player_api_id, season);
```
`player_api_id` backfill (77k rows) runs as a batched admin endpoint post-deploy, NOT inside the
migration (ops-judge requirement). PJE already has RLS; ADD COLUMN doesn't touch it.

**Migration `sea02`** (`down_revision = "sea01"`) — the rollup pair + league config.
```
player_season_cells                       -- fine grain: one row per SOURCE-contributed cell
  id BIGINT PK, player_api_id INT NOT NULL, season INT NOT NULL,
  source VARCHAR(12) NOT NULL,            -- 'fixtures'|'journey'|'apss'|'shadow'|'cache'
  club_api_id INT NOT NULL, club_name VARCHAR(200),
  competition_tier VARCHAR(20) NOT NULL,  -- league|domestic_cup|league_cup|continental|other|youth
  level_group VARCHAR(13) NOT NULL,       -- 'senior'|'youth'|'international'
  appearances INT, goals INT, assists INT, minutes INT, yellows INT, reds INT,
  saves INT, goals_conceded INT,
  avg_rating NUMERIC(4,2),                -- minutes-weighted WITHIN this source only
  detail JSONB,                           -- shots/passes/tackles/duels/dribbles (rich fields)
  synced_at TIMESTAMPTZ NOT NULL,
  UNIQUE (player_api_id, season, source, club_api_id, competition_tier),
  INDEX ix_psc_player_season (player_api_id, season); RLS ENABLED

player_season_totals                      -- coarse grain: the single hot-read row
  id BIGINT PK, player_api_id INT NOT NULL, season INT NOT NULL,
  level_group VARCHAR(13) NOT NULL,       -- senior|youth|international (Q10)
  appearances INT, goals INT, assists INT, minutes INT, yellows INT, reds INT,
  saves INT, goals_conceded INT,
  avg_rating NUMERIC(4,2),                -- ALWAYS fixtures-sourced, minutes-weighted
  primary_source VARCHAR(12) NOT NULL,    -- source whose totals won the headline
  fixtures_minutes INT, journey_minutes INT,   -- both raw values, always
  reconcile_flag VARCHAR(20),             -- NULL|'cup-gap'|'journey-under-sync'|'fixtures-invisible'
  source_breakdown JSONB, clubs JSONB,    -- per-source minutes; compact per-club render array
  computed_at TIMESTAMPTZ NOT NULL,
  UNIQUE (player_api_id, season, level_group),
  INDEX ix_pst_season_group (season, level_group), INDEX ix_pst_player (player_api_id, season);
  RLS ENABLED

league_season_config                      -- "what season is NOW" per league (Q3)
  league_api_id INT PK, season_type VARCHAR(12), rollover_month INT; RLS ENABLED
  seed: (71,'calendar',1),(128,'calendar',1),(253,'calendar',1),(262,'calendar',1),(98,'calendar',1)
```
**Aggregation rule (the double-count guard, non-negotiable):** totals NEVER sum across sources.
Per (player, season, level_group): compute each source's own total; headline = the source with
larger minutes, taken WHOLE (journey wins ties/≥ — cup-inclusive convention; fixtures wins when
strictly larger → `journey-under-sync`). Flags: journey > fixtures > 0 → `cup-gap`; fixtures = 0 →
`fixtures-invisible`. Rich fields + per-90s always pair fixtures numerators with fixtures_minutes.
**Noise filter:** feeders skip source rows with 0 apps AND 0 minutes AND 0 goals (kills the 740
PJE 2026 pre-season stubs); selectors list only seasons with an active totals row.
Anchor test (gates everything): Gore 303010 season 2025 senior → minutes 2,936, primary_source
journey, fixtures_minutes 2,583, flag cup-gap; per-match log unchanged.

## 3. Sync / backfill plan (write path + sequencing of MJ-gated ops)

**Steady state — two hooks + one safety net, all pure-DB per-player (sub-second, container-safe):**
1. `season_rollup_service.refresh_player(player_api_id, season=None)` — DELETE+INSERT that
   player's cells per source, then re-resolve totals, in one transaction. Called from:
   (a) **one FPS choke point**: a single function every FixturePlayerStats writer calls
   (api_football_client, stats_parser, weekly_newsletter_agent, api.py routes all route through
   it) — this is what keeps 26/27 fresh weekly at zero API cost and creates new-season rows the
   moment fixtures land; (b) **end of `JourneySyncService.sync_player`** (after
   `_merge_corrected_duplicates`), same transaction — club-ID corrections can never orphan cells.
2. `_create_entry_from_stat` widened to persist the rich fields + `stats_source='journey-api'` +
   `stats_synced_at` (zero extra API calls — payload already fetched, currently discarded).
3. Safety net: `POST /api/admin/season-rollup/rebuild?scope=stale|player|season|all` (batched,
   idempotent) + a rows-behind gauge (MAX(source.updated_at) vs totals.computed_at) on the admin
   sandbox. Nightly stale-only sweep scheduled against the admin endpoint — drift is measurable
   and one rebuild from fixed, because every derived row is a pure function of FPS+PJE+APSS.

**Backfill sequencing (value before spend; each step gated as marked):**
- **B0** (deploy): sea01+sea02 migrations; batched PJE `player_api_id` backfill endpoint. No API.
- **B1** (pure DB, off-container or scaled per invariants §7, no MJ quota gate): cold-build —
  journey cells from all 77k PJE rows (basic 4 fields), fixtures cells from 98,565 FPS rows
  (season 2025, rich detail + rating), shadow cells; resolve all totals. Platform-wide multi-season
  data goes live HERE, before any API spend. Then the 20-player pilot validation (incl. Gore).
- **B2 [MJ-GATED, off-container]**: journey 2025-26 re-sync (~3,544 active players × ~N+2 live
  calls). MUST run after the wider-extraction code is deployed so one pass banks corrected 25/26
  totals AND rich fields AND the P3 status repair (invariants §7 playbook: scale to 1.0 CPU/2Gi/
  min-2 or ACA job direct-to-DB; health-gate, abort on first `000`). Rollup self-updates via hook.
  Until B2 lands, the 26 under-synced players display their (larger) fixtures figure + flag — the
  system is honest without the re-sync; B2 upgrades it.
- **B3 [MJ-GATED, off-container]**: APSS 2025-26 sync → apss cells → deep youth panels. Parallel
  to / independent of B2; blocks only the deep-youth overlay, nothing senior.
- **B4 (deferred, not designed in)**: per-match historical crawl (~40–60 calls/team-season). The
  resolver auto-upgrades a season's provenance to fixtures if its FPS ever lands — zero code change.

## 4. API contract

- `?season=<int start-year>` on: `/players/<id>/stats`, `/players/<id>/season-stats`,
  `/scout/players|leaderboards|compare|export.csv`, `/teams/<id>/players|loans|trajectory`,
  `/journalists/chart-data`, `/journalists/players/<id>/stats`. Validation via new
  `academy_window.season_bounds()` → 400 outside [min season with data, current_stats_season()+1].
- Defaults via ONE resolver `resolve_stats_season(db, requested=None, surface="discovery")`:
  `discovery` → `stats_season_with_data` (fixtures-keyed — the graft; never rollup/PJE-keyed);
  `compare` → `current_stats_season` wall-clock, NO fallback (UI renders "season not started");
  sync paths keep `current_stats_season`. Aug 1: discovery stays on 25/26 until real 26/27
  fixtures land; the fixtures hook then creates 2026 totals rows the same week.
- New: `GET /players/<id>/seasons` → `{seasons:[{season, sources:[], has_senior, has_youth}]}`
  (noise-filtered); `GET /players/<id>/season-history?from&to&level_group=` → totals rows desc
  (development view, one indexed scan); `?seasons=2025,2026` on compare endpoints.
- Every season figure carries the provenance object (extends the existing `/season-stats`
  `source` field): `{source, fixtures_minutes, journey_minutes, delta_pct, reconcile_flag,
  breakdown}`. Never silently COALESCE — scout's fps→cache COALESCE is retired at cutover.
- Split-season leagues: one API-Football season int (correct today); dormant `season_phase` for a
  future `&phase=`. `YYYY-YY::WINDOW` transfer keys are a transfer-axis concern — untouched.

## 5. UI plan

- **SeasonSelector** (shared component; PlayerPage, ScoutPage, TeamDetailPage, WatchlistPage, GOL
  drawer, writer drawer): fed by `/players/<id>/seasons` (or DISTINCT totals seasons for lists),
  labels "2025/26" (calendar leagues "2025" via `league_season_config`), default = resolver.
  **URL-bound (`?season=`)** — shareable, back-button-safe (compute-on-read graft).
- **Provenance badges everywhere a figure renders**: "2,583 in league · 2,936 incl. cups" when
  `cup-gap`; chips map 1:1 to `reconcile_flag` (`journey-under-sync` → "re-sync pending", visible
  to all, not admin-only); tooltip shows `breakdown`. This retires the 8 "lying" surfaces —
  relabeling is in-scope work, not polish.
- **Compare card** (PlayerPage, ScoutPage): two columns via `?seasons=`, per-metric delta arrows,
  empty side renders "Season not started" (never blanks).
- **Development view** (PlayerPage): per-season strip from `/season-history` — minutes bars +
  goal-contribution + rating sparkline (post-B2), youth track muted (level_group), APSS deep
  panels expandable where 23/24–25/26 data exists, "rich stats syncing" hint where PJE rich = NULL.
- `api.js`: thread `season` through the 10 methods in coverage map §5; add `getPlayerSeasons`,
  `getPlayerSeasonHistory`, compare variants.

## 6. Answers to the 12 coverage-map questions

1. **Grain:** cells = (player, season, SOURCE, club, competition_tier); totals = (player, season,
   level_group). Source in the unique key means feeders never collide; PJE stays the durable
   per-(club,league) archive underneath.
2. **Precedence/display:** never cross-source sum. Larger-minutes source wins the headline whole
   (journey on ≥ — cup-inclusive; fixtures when > — with visible `journey-under-sync` flag, never
   an understated headline). Rich/per-match fields always fixtures-sourced with fixtures
   denominators. Both raw values + delta always in the provenance object.
3. **Boundary:** no third epoch. Academy window stays Jul; stats display stays Aug via the one
   resolver; storage is boundary-immune (API-Football labels). Calendar-year leagues modeled NOW
   via `league_season_config` (labels + per-league "current" resolution); Euro-first behavior.
4. **Current-season resolution:** one resolver, per-surface policy — discovery = fixtures-keyed
   latest-with-data; compare = wall-clock, no fallback; sync = wall-clock. Never rollup-keyed.
5. **API contract:** `?season=<int>` pass-through + `season_bounds()` validation; `?seasons=` for
   compare; `/seasons` + `/season-history` for multi-season. Apertura/Clausura = one int +
   dormant `season_phase`; transfer `YYYY-YY::WINDOW` keys untouched.
6. **Journey 2025 re-sync:** NOT a shipping blocker (fixtures-wins rule keeps display honest);
   sequenced first among API ops (B2), after B1 cold-build, after wider-extraction deploys.
   Off-container, MJ-gated.
7. **Wider extraction:** into PJE columns (the durable archive — api_cache purges in 7 days);
   rollup cells derive from them. Code ships before B2 so one API pass banks everything.
8. **Per-match historical backfill:** deferred (B4). Resolver auto-upgrades provenance if FPS for
   a past season ever lands — zero code change.
9. **PSC / AcademyAppearance:** demoted, not dropped. PSC stays a dormant `cache` feeder branch;
   AA excluded (youth = PJE is_youth + APSS). Docs corrected in Phase D. No schema work.
10. **Youth:** unified via `level_group` senior|youth|international (international stays visible
    in development view). APSS 2025-26 sync (B3) gates deep current-season youth panels only.
11. **Horizon debt:** this phase ships the data-driven source (`season_bounds()`,
    `league_season_config`, selector fed from totals). Literal sites (big6 SEASONS, Team.season
    default, client 2025 defaults) = Phase D chores. `transfer_windows` missing 26/27 is flagged
    as a BLOCKER for the 26/27 transfer heal — separate subsystem, raise with MJ.
12. **Open-ended `date_utc >=`:** fixed in PR1 with the `?season` plumbing (players.py:439/572/
    613/689/721/730 → `Fixture.season ==`), not deferred — they double-count the day 26/27 lands.

## 7. Rollout phases (mapped to seasons-ledger Phase D / E)

- **D1** — PR1, zero-migration: `?season` + provenance object on single-player endpoints (direct
  FPS/PJE reads), Q12 date fixes, `season_bounds()`. Verify Gore via real endpoints.
- **D2** — PR2: `sea01` (PJE widen + `ix_fps_player` + PJE indexes) + wider extraction +
  `player_api_id` backfill endpoint.
- **D3** — PR3: `sea02` (cells/totals/config, RLS) + rollup service (feeders, resolver, hooks,
  FPS choke point, noise filter) + admin rebuild + rows-behind gauge + Gore-anchored unit tests.
- **D4** — B1 cold-build + 20-player pilot → flip `SEASON_ROLLUP_READS` per surface:
  `compute_stats(season=)` → scout `_base_scout_query` (drop both subqueries + COALESCE) →
  players → teams/journalist. Rollback = flag flip.
- **D5** — PR4/5, frontend: SeasonSelector, badges, compare, development view; relabel the 8
  lying surfaces; Playwright drives PlayerPage/ScoutPage.
- **E1 [MJ gate]** — B2 journey 2025-26 re-sync (P1/P3 status repair rides along, per ledger).
- **E2 [MJ gate]** — B3 APSS 2025-26 sync → youth overlay complete.
- **E3** — nightly stale-reconcile schedule live; verification targets: Gore 2,936/2,583/cup-gap,
  zero-at-tracked-club gauge → ~0, rows-behind gauge ≈ 0; Phase D chores + doc corrections.

## 8. Decision points requiring MJ sign-off

1. **Schema** (irreversible-ish): sea01 (25 nullable PJE columns) + sea02 (2 rollup tables +
   `league_season_config`). Confirm the never-cross-source-sum totals rule and cells grain.
2. **Display flip**: headline season totals become the larger cup-inclusive figure for ~78% of
   players-with-data (e.g. Gore 2,583 → 2,936 "incl. cups"). User-visible numbers change.
3. **B1 cold-build scope**: all players × all seasons, pure DB, off-container. Cheap but
   platform-wide; pilot (20 players incl. Gore) gates the read cutover.
4. **B2 journey 2025-26 re-sync**: ~3,544 players × ~N+2 live API calls, off-container scale-up
   per invariants §7. Quota sign-off. Wider extraction MUST be deployed first (one-pass banking).
5. **B3 APSS 2025-26 sync**: off-container, MJ-gated (stale since 2026-04).
6. **Deliberately deferred** (sign off on NOT doing): per-match historical crawl (B4);
   Apertura/Clausura behavior (dormant column only); PSC/AA table drops (demote only).
7. **Flagged escalation**: `data/transfer_windows.py` stops at 2025-26 — blocks the 26/27
   transfer heal independently of this design; needs its own small data PR.
