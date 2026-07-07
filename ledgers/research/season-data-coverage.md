# Season Data Coverage — Phase B synthesis (input to Phase C design panel)

Written 2026-07-07 by season-discovery synthesis agent. Inputs: Sweep 1 (season assumptions),
Sweep 2 (stats surfaces), Sweep 3 (API-Football capability), prod coverage audit (read-only
SELECTs against snqwamzutbcbjgusubsa). Season values = START YEARS (2025 = 2025-26).
`[UNIFY]` = already in Phase A scope (`feat/season-foundation`): `utils/academy_window.py`,
`routes/players.py:75,:438`, `transfer_heal_service.py:265` + P0 read-path season-scoping.

## 1. Data availability matrix (source × seasons × granularity × trust)

| Source | Seasons (prod) | Granularity | Trust / caveats |
|---|---|---|---|
| `fixtures` + `FixturePlayerStats` | **2025 ONLY** (20,349 fx / 211 comps, 2025-08-01→2026-06-10; 98,565 FPS rows, 4,726 players, 4.75M min) | Per-match, rich fields | Best where covered, but: 34 comps ≥75% covered (77% of minutes), 43 partial (domestic cups: FA Cup 80/270 fx), **134 comps zero coverage** (all youth/reserve + lower/foreign divisions). `Fixture.season` column exists; almost no read path filters on it |
| `PlayerStatsCache` | **0 rows (EMPTY)** | (per-player season cache, by design) | **Vestigial.** 100% of active tracked rows are `data_depth='full_stats'` → nothing routes to it. The 3-tier provenance model in code/docs is a 2-tier model in prod. Do NOT design around it being populated |
| `PlayerJourneyEntry` | **2007–2027** (77,355 rows, 5,916 journeys; 2025 = 8,781 entries / 3,244 players / 3.58M min; 2026 = 740 pre-season noise) | Season totals per (club, league, season) — **4 fields only**: apps/goals/assists/minutes; `is_youth` flag | Sole pre-2025 source. Per covered player it is MORE complete than fixtures (cups + uncovered leagues) but **lags the just-ended season** (sync gap). Club IDs corrected from transfers at sync time |
| `AcademyAppearance` | **0 rows (EMPTY)** | (per-youth-match, by design) | **Exclude from design.** CLAUDE.md/architecture.md still describe it as the youth-stats source — stale; `/players/<id>/academy-stats` actually reads APSS with AA as unused fallback |
| `AcademyPlayerSeasonStats` | 2023 (2,640 rows/1,664p/1.13M min), 2024 (2,607/1,572/737k), **2025 near-empty** (363/728 min); table STALE (updated 2026-04-01/02) | Per-season/competition youth, rich extended fields (shots/passes/tackles) | Additive, not redundant (only 101 of its 2025 players overlap fixtures). Needs fresh 2025-26 sync before usable for current season |
| `PlayerShadowStats` | Per-season (worldwide shadow) | Season totals | Latest-season picked via `max(season)`; digest + season-stats fallback |
| **API-Football backfill options (unused/under-used)** | | | Rough call cost (Sweep 3; quota-gated by optional `API_FOOTBALL_DAILY_LIMIT`; cache hits free) |
| — Wider extraction of `players?id&season` | any career season | Per (club, league, season): rating, position, shots, passes, tackles, duels, dribbles, cards, penalties, saves, GC | **ZERO new calls** — payload already fetched every journey sync; `_create_entry_from_stat` currently discards all but 4 fields |
| — Journey re-sync / totals backfill | any career season | Season totals | **~N+2 live calls/player** (players/seasons + transfers + 1/season; N≈2–5 young, 8–15 senior). `api_cache` player TTL only 7 days + pg_cron purge → NOT a durable archive; durable store = PJE rows |
| — Per-match historical crawl | any past season | Full FPS-grade per-match | **~40–60 calls per team-season** (`fixtures?team&season` + `fixtures/players` per fixture), amortized across roster; 10-yr immutable cache once fetched. Fixtures-2025-only is a coverage state, not a client limit |
| — Never called (UNVERIFIED from docs knowledge) | | | `players/topscorers|topassists`, `sidelined`, `trophies`, `players/teams`. Discovery endpoints already in place: `players/seasons`, `teams/seasons`, `leagues?id&season` coverage flags — use to gate backfills |

**Cross-input conflicts, stated explicitly:**
- Docs (CLAUDE.md, architecture.md) vs prod: AcademyAppearance and PlayerStatsCache are described as live tiers; both are **empty**. Docs need correction; design is fixtures+journey (+APSS for youth).
- Aggregate vs per-player 2025 completeness: headline says fixtures > journey for 2025 (4,726 vs 3,244 players) while Q4 says journey ≥ fixtures for most players — **both true, different scopes**: FPS includes non-tracked players and journey 2025 sync lags; per active-player-with-data, journey is usually the bigger, more complete number. Provenance must therefore be per-player-per-season, not global.

## 2. What each product view can honestly show

**25/26 vs 26/27 compare (fixtures-fed going forward).** Honest per-match comparison only once
26/27 fixtures land (per-match sync continues). Requires `Fixture.season` filters (Phase A P0) +
explicit `?season` params. The 25/26 side from fixtures **understates** ~40% of players (cup gap)
and misses 375 players entirely (§3) — for season-total minutes the honest 25/26 number is journey
(after re-sync). Before 26/27 fixtures exist, the compare must render "season not started", never
blanks (Aug-1 bomb, Phase A P4 fallback = "latest season with fixtures", GOL `max(season)` pattern).

**Past-X-years development (journey-fed).** Real depth among 3,544 distinct active tracked players
(all have a journey): **≥2 seasons 3,121 (88%) · ≥3 2,575 (73%) · ≥4 1,956 (55%) · ≥5 1,266 (36%)**.
(All journeys: 5,916 / 5,309 / 4,595 / 3,791 / 2,850.) Granularity is season totals, 4 fields; a
richer development view (rating/shots/cards trends) costs zero extra API calls via wider extraction
on re-sync. Per-match history pre-2025 exists only via team-season crawl (40–60 calls/team-season).
Journey 2025 must be re-synced before it is authoritative for the season just ended (26 players
currently have fixtures > journey = under-sync marker).

**Youth overlay (AcademyAppearance reality).** AA is empty — the overlay CANNOT use it. Honest
sources: (a) journey `is_youth` entries — broad, 2016–2024 substantial (2023=7,971, 2024=6,861,
2025=1,920 entries so far), apps/goals/minutes per youth club-season; (b) APSS — deep stats but
**2023 + 2024 only**, stale, 2025 near-zero pending fresh sync. Today's honest youth overlay =
journey youth season totals for all years + deep APSS panels for 23/24 & 24/25 only, labeled.

## 3. Consistency findings → provenance-labeling requirement

Fixture-vs-journey minutes, season 2025, active players (journey club entries, internationals
excluded). Of **1,071** active players with any 2025 senior minutes in either source:

| Bucket | Players | Σ fixture min | Σ journey min |
|---|---|---|---|
| equal ±5% | 232 (22%) | 193,823 | 194,808 |
| journey higher 5–25% (cup gap) | 215 | 297,401 | 355,317 |
| journey higher >25% | 219 | 134,187 | 246,826 |
| **journey-only (fixtures-invisible)** | **375 (35%)** | 0 | 225,169 |
| fixture higher >5% (journey under-synced) | 26 | 29,042 | 21,933 |
| fixture-only | 4 | 172 | 0 |

Plus 2,473 active players both-zero (deep academy / departed; their only football is in
zero-coverage youth leagues). Anchor case: Gore 303010 = 2,583 fixture min vs 2,936 journey
(matches scout ledger exactly).

**Requirement (non-negotiable for Phase C):** for **~78% of players-with-data the two sources
materially disagree** — provenance is not cosmetic. Every season figure must carry a per-season,
per-source provenance tag (`fixtures-full` | `journey-totals` | `apss-youth` | `shadow` |
`cache-limited`), stored in the rollup and surfaced in the UI. `/players/<id>/season-stats`
already returns a `source` field — extend that contract platform-wide. Never silently COALESCE
(scout `_base_scout_query` does fps→cache today). Display policy: per-match views = fixtures;
season-total minutes = journey where journey ≥ fixtures; fixtures>journey = re-sync flag, not a
preference flip. Where both exist, consider surfacing the delta ("2,583 tracked / 2,936 incl. cups").

## 4. Season-assumption debt (beyond the Phase A unification)

From Sweep 1; semantics: AUG=`month>=8`, JUL=`month>=7`, RAWYR=`now().year` no guard, NONE=no scoping,
MAX=implicit latest. Phase A already covers academy_window / players.py:75,:438 / transfer_heal:265 + P0.

| Category | Sites | Semantic | Multi-season failure |
|---|---|---|---|
| Stat aggregation, no season filter | `tracked_player.py:132-147` compute_stats; `scout.py:160-174,301-315`; `teams.py:392-403` loans agg; `api.py:12373-12388,12438-12453` team-players agg; `journalist.py:2551-2557`; `graph_service.py` | NONE | Silent cross-season double-count the day 2026 fixtures land |
| Latest-only cache reads | `tracked_player.py:104-114`; `scout.py:177-205` | MAX | No way to request a specific season |
| Calendar/split-year league blindness | `supported_leagues.py:29-51` (no season_type field; Brazil 71, Argentina 128, MLS 253, Liga MX 262, J1 98); `api_football_client.py:356,366,378,2745`; `weekly_newsletter_agent.py:2454,2643,2918,1843`; `api.py:1511,5027,5434,6076` | AUG hardwired | Aug1–Jun30 window straddles two calendar-year seasons, misses Feb–Jul matches worldwide |
| Jul-vs-Aug epoch split (~30 sites) | AUG: `api_football_client.py:348` (central default), `teams.py:506,963`, `journalist.py:2507`, `gol_service.py:441`, `player_shadow_service.py:57-62`, `weekly_agent.py:856`, `weekly_newsletter_agent.py:3497`, `api.py:4597,4998,5292,5999,11795,11903,12033`, `academy_sync_service.py:19-28` · JUL: `gameweeks.py:19-26`, `team_verify.py:37-40`, `radar_stats_service.py:580,712`, `journalist.py:1149,1886`, `api.py:3775` | AUG/JUL | June–Aug split-brain: profile vs radar vs chart vs academy disagree by one season |
| Journey vs stats boundary | `journey_sync.py:508-531,514-515,732,1072` uses Jul 1; stats paths use Aug 1 | JUL vs AUG | July transfers/loans land in different seasons per code path |
| Raw-year proxies | `journey_sync.py:189`; `academy_classifier.py:889` (feeds released-mislabel bug); `cohort_service.py:250`, `cohort.py:179`; `big6_seeding_service.py:328`, `api.py:10267,10291` | RAWYR | Off-by-one season Jan–Jul |
| Implicit-latest Team/season resolution | `gol_dataframes.py:61,126`; `api.py:9734`; `players.py:518`, `scout_digest_service.py:83`; team_resolver/slug/gol_player_lookup/journey_sync latest-Team lookups; `rebuild_runner.py:179,270,294` | MAX | Hides older seasons; needs explicit-season variants |
| Open-ended date ranges | `players.py:439,572,689,721` (`date_utc >= season_start`, no upper bound) `[UNIFY-adjacent]`; `weekly_newsletter_agent.py:2930` | AUG, one-sided | Sums 2025+2026 once new fixtures land — upper bound is a separate defect from P4 |
| Hardcoded literals | `big6_seeding_service.py:38` SEASONS=[2020..2024]; `league.py:28` Team.season default=2024; `api_football_client.py:1799,1862,2061` season=2025 defaults; `api.py:5797,6812`; `data/transfer_windows.py:16-22` **stops at 2025-26** (26/27 heal has no window data); `backfill_tracked_player_stats.py:113` | literal | Caps the season horizon; must become data-driven |
| Mutation-on-read | `academy_sync_service.py:42-52` overwrites `AcademyLeague.season` to current | AUG | Historical sync silently re-labels stored season |

## 5. Surface inventory summary (endpoints/pages needing a season parameter)

**Backend — must gain `?season` + season-scoped SQL:** `/players/<id>/stats` (players.py:54);
`/players/<id>/season-stats` (:427 — cleanest template, currently hard-wired current);
`/scout/players`, `/scout/leaderboards`, `/scout/compare`, `/scout/export.csv` (all all-time-at-CCAI);
`/teams/<id>/players` (api.py:12323 — TeamDetailPage squad); `/teams/<id>/loans` (season param read
but UNUSED for stats) + `/teams/<id>/loans/season/<season>` (slug only, never filters);
`/journalists/chart-data` (date_range=season wall-clock only) + `/journalists/players/<id>/stats`;
`/teams/<id>/trajectory` (has `?years` but no season anchor). Already parameterized (extend, don't
break): teams.py:113,150,353,963; players.py:757 radar; availability :757; feeder (required);
cohort :250; academy :75,256; several api.py admin routes. `journalist._get_season_stats:738-771`
is the one internal helper already accepting a season — generalize it.

**api.js:** only `getPlayerAvailability` forwards a season today. Need season args through:
`getPublicPlayerStats`, `getPublicPlayerSeasonStats`, `getScoutPlayers/Leaderboards`,
`compareScoutPlayers`, `downloadScoutCsv`, `getChartData`, `getPlayerStats`, `getTeamPlayers`,
`getTeamLoans`, `getPlayerAcademyStats`.

**Frontend pages needing a season selector / provenance labels:** PlayerPage (seasonTotals mixes
season-scoped + all-time fallback under one heading), ScoutPage (compare section **labeled
"Season", is all-time-at-CCAI**), TeamDetailPage (squad stats all-time; `?season` only reaches the
constellation), WatchlistPage, GOL PlayerPreviewDrawer (**"Season stats" heading over all-time
array**), writer PlayerStatsDrawer ("Season Totals" over all-time log), newsletter chart chain.
Eight "lying" surfaces enumerated in Sweep 2 Part 4 — fixing the label is part of the season work,
not polish. Season-native already (build on): journey map/SeasonStatsPanel, cohort pages, GOL
dataframes (`f.season` joined — the only natively season-aware analytics).

## 6. Open questions for the Phase C design panel

1. **Rollup grain:** per (player, team, season) or (player, team, season, competition)? Journey is
   per-league already; cup-vs-league splits are where provenance diverges.
2. **Provenance precedence & display:** when fixtures and journey disagree for the same
   player-season, which is primary, and is the delta shown? Per-surface policy (per-match vs totals)?
3. **Canonical boundary:** Jul 1 vs Aug 1 vs per-league `season_start_month`? What migrates the
   Jul-journey/Aug-stats split, and do we ship Euro-only first with calendar-year leagues
   (Brazil/MLS/Argentina/Liga MX/J1) explicitly deferred or modeled now?
4. **Current-season resolution:** wall-clock vs "latest season with fixtures" fallback — one global
   policy or per-surface (e.g., compare wants wall-clock, scout wants latest-with-data)?
5. **Season API contract:** `?season=<int start-year>` everywhere — how do split-season leagues
   (Apertura/Clausura) and the `YYYY-YY::WINDOW` transfer-key format fit?
6. **Journey 2025 re-sync:** required before journey is authoritative for 25/26 (fixtures currently
   richer; 26 players fixtures>journey). Sequence vs rollup backfill? Off-container prod op — MJ gate.
7. **Wider extraction:** add rich per-season fields to PJE columns vs a new rollup table fed from
   the same `players?id&season` payload? (Zero extra calls either way; schema choice matters.)
8. **Per-match historical backfill:** wanted at all (~40–60 calls/team-season, durable 10-yr cache)?
   If so, which teams/seasons (e.g., tracked-club top leagues 2022–2024)?
9. **PlayerStatsCache tier:** delete from the design (empty, nothing routes to it) or keep as a
   future limited-league ingest path? Same question for reviving vs removing AcademyAppearance.
10. **Youth in the rollup:** unified table with `is_youth`/level, or separate youth rollup? Fresh
    APSS 2025-26 sync is a prerequisite for deep youth stats either way.
11. **Hardcoded horizon debt:** who owns making SEASONS lists, Team.season default, season=2025
    defaults, and `transfer_windows` (missing 2026-27) data-driven — Phase C schema or Phase D chores?
12. **Open-ended `date_utc >=` upper bounds** (players.py:439 etc.): fold into Phase A P0 or track
    as separate Phase D items? They double-count the moment 26/27 fixtures land even if labeled.
