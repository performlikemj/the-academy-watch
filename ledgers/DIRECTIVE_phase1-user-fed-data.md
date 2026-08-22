# DIRECTIVE (DRAFT) — Phase 1: one player universe + a user-fed stats grain

Status: DRAFT 2026-08-23 (Fable, from code reads during the Phase 0 lane). Not ratified. Three decisions
are MJ's (§4). Source plan: `docs/platform-review-2026-08-23.md` Part 2-D and Phase 1.
Executor when ratified: qwen lane (`briefs/P1-*.md`), same rules as Phase 0.

## 1. What the code already has (read 2026-08-23, worktree b90b180)

- **API universe:** `TrackedPlayer` (one row per player per parent club; `player_api_id`), `PlayerJourney`,
  `FixturePlayerStats`, `AcademyPlayerSeasonStats` (`apss`, per player-season-league), and the season
  rollup: `player_season_cells` (fine grain, one row per SOURCE-contributed cell: `source` ∈
  `fixtures|journey|apss|shadow|cache`, keyed on `player_api_id`) → `player_season_totals` (the hot-read
  row). `services/season_rollup_service.py` is the SOLE writer; feeders are plain functions
  `_fixture_cells/_journey_cells/_apss_cells/_shadow_cells` in `_FEEDERS`; `refresh_player(player_api_id)`
  re-derives cells+totals. Totals never sum across sources (headline = larger-minutes source whole).
- **Lightweight identity already exists:** `PlayerShadow` (unique `player_api_id`, minted by
  `player_shadow_service.mint_shadow` for any API-Football player someone follows) + `PlayerShadowStats`
  (per player/team/season: appearances/goals/assists/minutes) → feeds the rollup as `source='shadow'`.
  Scout discovery (`routes/scout.py::_base_scout_query`) reads `TrackedPlayer` only (active, not
  owning-club, not suppressed, not minor-bridged, preferred row).
- **User universe:** `LocalPlayer` (display_name, birth_year, position, country, city, club_name, status
  pending/approved, `api_player_id` NULLABLE link to an API identity, `merged_into_local_player_id`,
  provenance user|club, created_by), `PlayerProfileClaim` (`player_api_id` OR `local_player_id`, relationship
  type, status, contract_status, club_program_id), `PlayerShowcaseProfile/Media`, `PlayerClubAffiliation`.
  Admin tools exist: `admin_merge_local_player` (local→local), `admin_merge_local_club`,
  `admin_link_local_club_api`. There is NO local→API player link tool, and NO user-fed stats table.
- Club console: `ClubRosterMember` (program ↔ tracked OR local player), `VideoMatch` (match rows exist
  only for footage), squads via `VideoRosterEntry`.

## 2. The shape of the smallest correct mechanism

**2a. One subject id for the read side.** Every discovery/watchlist/follow/contact surface keys on
`player_api_id` (int). Rather than teach ~30 query sites a polymorphic (kind, id) pair, give every
approved `LocalPlayer` a place in the SAME integer space:

- If the local player IS an API-Football player → link (`LocalPlayer.api_player_id`), mint a `PlayerShadow`
  for that id (existing service), and the local profile becomes the human-entered layer over a real id.
  New admin tool: `POST /api/admin/local-players/<id>/link-api {player_api_id}` (copy-adapt of
  `admin_link_local_club_api`).
- If the local player is NOT in API-Football (the whole point of "players outside covered leagues") →
  allocate a **synthetic id in a reserved negative range**: `player_api_id = -local_player_id`. Negative
  ids never collide with API-Football (positive), pass every `int` check, index the same, and are trivially
  recognisable (`< 0` ⇒ local). Mint a `PlayerShadow` row for it (name/position/nationality/birth_date
  copied from the LocalPlayer; `requested_by_user_id` = creator) so the player has a profile row in the
  universe discovery can see. [MJ decision D1 below — alternative is a polymorphic key.]
- Scout discovery then gets ONE new row source: a UNION of `TrackedPlayer` rows with active shadow rows
  whose id is negative OR whose shadow is flagged `showcase_local=true` — behind a flag
  (`SCOUT_INCLUDE_LOCAL_PLAYERS`, default off until the grain exists), with the same suppression/minor
  filters (`without_active_suppression`, `without_minor_local_bridge` already take a `player_api_id`).

**2b. The user-fed stats grain = one table + one feeder.**
- New table `player_match_entries` (RLS enabled in the same migration): `id, player_api_id (int, may be
  negative), season (start-year), source ('player'|'club'), reported_by_user_id, club_program_id NULL,
  match_date, competition (text), opponent (text), home_away, result_for/result_against NULL,
  minutes, goals, assists, yellows, reds, saves NULL, goals_conceded NULL, note, status
  ('self_reported'|'club_confirmed'|'disputed'), created_at, updated_at`. Unique on
  `(player_api_id, match_date, opponent, source, reported_by_user_id)` to make re-submits idempotent.
- One new rollup feeder `_user_cells(player_api_id, season, session, now)` that groups entries per
  (season, club_program/club_name, competition_tier='user', level_group by birth_year/competition) and
  emits cells with `source='user'` (club-confirmed rows could be `source='club'`). Append to `_FEEDERS`.
  Provenance is then automatic: `player_season_totals.primary_source`, `source_breakdown`, `clubs`. The
  public payload already marks self-reported content; add `source` to the player-page stats block.
- Write paths: `POST /api/players/<player_api_id>/matches` (owner of an approved player claim, or an
  active club manager for a rostered player → `source='club'`, `status='club_confirmed'`), `PATCH/DELETE`
  by the author, list for the profile. Each write calls `season_rollup_service.refresh_player(id, season)`
  in the same transaction (it participates in the caller's session by design).
- Clubs get the same grain through the console: "Add a fixture" (no video) = create a lightweight
  `ClubFixture` (program_id, date, opponent, competition, score) and N `player_match_entries` rows for
  rostered players — Phase 2 item 1 of the review; the table above is designed so Phase 2 only adds the
  fixture header, not a second stats store.

**2c. Graduation.** `LocalPlayer.status` approved → shadow minted (negative or linked id) → appears in
discovery (flag) → admin may link to an API id later (`link-api`): the tool re-keys the player's
`player_match_entries` and claims from `-local_id` to the real id, merges shadows, and refreshes the rollup.
Tracked status (a `TrackedPlayer` row) stays what it is: API-derived academy membership. Local players
are first-class in discovery WITHOUT becoming TrackedPlayers.

**2d. Trust-tiered auto-approval (A3 of the review).** `PUT /players/<id>/showcase/profile` flips the
profile to pending on every edit. Add a per-field allow-list (bio, languages, preferred_foot, height,
availability, positions) that stays approved when the claim is approved and the account is ≥N days old
with no rejected moderation events; contract/club/agent fields keep the pending→admin path.

## 3. What this deliberately does NOT do

- No polymorphic `(subject_kind, subject_id)` column migration across 30 tables (the negative-id space
  buys the same outcome with zero schema churn on the read side). Reversible: a later migration can map
  negative ids to a `player_subjects` table if the space ever needs more than ints.
- No change to `TrackedPlayer` semantics, journey sync, or `classify_tracked_player` (invariants §3/§4/§10).
- No API-Football calls for local players (shadow service is stub-safe; negative ids skip sync).

## 4. MJ decisions needed before briefs are written

- **D1 id space:** negative synthetic `player_api_id` for unlinked locals (recommended: smallest change,
  reversible) vs. a polymorphic subject table (cleaner on paper, touches every surface).
- **D2 who may enter stats:** player self-reports always allowed (status `self_reported`); club-entered
  rows for rostered players (`club_confirmed`); do we show self-reported minutes/goals on the SCOUT DESK
  (flagged) or only on the profile until a club confirms? Recommended: desk shows them with a provenance
  chip, filterable (`source=api|club|self`).
- **D3 minors:** local players under 18 stay publicly invisible today (`without_minor_local_bridge`);
  stats entry for minors = allowed but never public (D1 adults-only launch stands) — confirm.

## 5. Brief plan once ratified (each ≤75 min, qwen)

P1-A1 migration `pm01` (`player_match_entries` + RLS, chained from the then-head) · P1-A2 model +
serializer · P1-A3 write/list routes + tests (claim-owner path) · P1-A4 club-manager path · P1-A5 rollup
feeder `_user_cells` + tests (D3b test style) · P1-B1 shadow mint for approved locals (negative id) +
`link-api` admin tool · P1-B2 scout union behind flag + tests · P1-C1 player-side "add my game" form ·
P1-C2 profile stats block shows provenance · P1-D1 trust-tiered auto-approval allow-list + tests.
