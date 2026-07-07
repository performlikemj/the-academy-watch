# Data model — player-tracking semantics

Most data bugs here come from violating one of these semantics. Read before
touching player tracking, stats, journeys, or status classification.

## TrackedPlayer (`src/models/tracked_player.py`)

- One row per player **per parent academy club**. `team_id` = parent academy
  club (origin); `current_club_api_id` / `current_club_db_id` = where he plays
  now (loan destination or buying club).
- Pathway status (academy → on_loan → first_team → released/sold) is computed by
  `classify_tracked_player()` in `src/utils/academy_classifier.py` from journey +
  transfer history. For sold/released players the destination club is preserved
  in `current_club_api_id`.
- `data_source='owning-club'` rows are **deprecated and auto-deactivated**: a
  club only tracks players whose journey shows academy formation there
  (prior-senior-career rule in `JourneySyncService._compute_academy_club_ids`).
  Repair endpoint: `POST /api/admin/journeys/recompute-academy`.
- **Academy window** (`src/utils/academy_window.py`): only players in an academy
  now or within the past `ACADEMY_WINDOW_YEARS` (default 4) seasons are tracked.
  `last_academy_season` records the evidence; journey upsert, recompute repair,
  rebuild stage 4, seed-team, and GOL all enforce `is_within_academy_window()`.
  Older alumni rows are deactivated (pinned/manual rows survive).
- `player_name` must be a real name. A placeholder `Player NNNN` must **never
  overwrite a real name** — resolve via `resolve_player_name()` in
  `src/utils/player_names.py`. Backfill: `POST /api/admin/players/backfill-names`.
- `first_team` rows often have **NULL `current_club_api_id`** (internal
  promotions have no transfer event) — consumers must degrade gracefully, never
  assume the parent club. If a feature needs it populated, fix the classifier,
  not the consumer.
- **Two status axes**: `TrackedPlayer.status` is RELATIVE to the tracked academy
  (sold/left = left *that* club). The player's ACTUAL situation lives in stored
  `player_journeys.current_status` / `current_owner_*` (set by
  `JourneySyncService._set_current_status`; backfill:
  `POST /api/admin/journeys/backfill-current-status`). Player-page headline uses
  the journey axis; team/academy views use the per-academy axis. A sixth status
  `left` = at another club with no recorded parent departure. Affiliates
  (Jong Ajax → Ajax etc.) resolve via `src/utils/affiliates.py`.

## Stats — three sources; know which one you're reading

- **Full coverage** (top leagues): aggregate `FixturePlayerStats`
  (`src/models/weekly.py`) via `TrackedPlayer.compute_stats()`.
- **Limited coverage** (lower leagues): `PlayerStatsCache` rows, read by the same
  `compute_stats()`.
- **Youth leagues**: `AcademyAppearance`, served by `/players/<id>/academy-stats`.

When stats "look wrong", establish ground truth first: aggregate
`FixturePlayerStats` per season for that player, then compare against what each
serving path returns. Season values are the **start year** of a European season
(2025 = 2025-26); mind the July/August rollover when defaulting "current season".

## Journey (`src/models/journey.py`, `src/services/journey_sync.py`)

- `PlayerJourney` + `PlayerJourneyEntry` = full career history from API-Football.
- `_correct_club_ids_from_transfers()` fixes API-Football returning the *current*
  team for historical seasons; `_merge_corrected_duplicates()` dedups afterwards.
- Bulk journey re-syncs are expensive and have caused prod outages — see
  `docs/agents/invariants.md` before running any bulk sync.

## Deleted models — never reference

`AcademyPlayer` (table `loaned_players`) and `SupplementalLoan` (table
`supplemental_loans`) were permanently deleted and their tables dropped. Any code
path referencing them is a bug. Use `TrackedPlayer`.
