# DIRECTIVE — API-Football freeze ("side door") plan

Status: APPROVED by owner 2026-09-25 ("yes to your picks": decisions 1a, 2a, 3a, 4a; plan-renewal decision still open).
Live job inventory 2026-09-25: no newsletter job exists in Azure; scheduled = job-sync-fixtures 0 5 * * *,
job-transfer-heal 0 3 * * *, job-scout-digest 0 7 * * 1 (to pause); keep job-video-maintenance, job-profile-activity.
Originals saved in ledgers/tooling/freeze/.
Source: read-only codex recon of origin/main 5b363fb5 (full report kept in the session scratchpad
`freeze-recon-REPORT.md`; key evidence paths quoted inline). Related: `ledgers/CONTINUITY_club-home.md`.

## Decision already made by the owner
- Front door = clubs + players onboarding (Club Home, player profiles, Film Room).
- API-Football stays as a SIDE DOOR: an "Explore players" search over the public match data already in our database,
  labelled "Public match data — last updated …", separate from "Club-verified" and "Self-reported", with a
  "Claim your record" hook.
- Switch off: newsletters, league/team browsing, and the nightly/bulk syncs and crawls.
- Keep all code and all stored football data (freeze and hide, never delete).

## Key recon facts that shape the plan
- Pausing jobs is NOT enough: player pages (`/stats`, `/season-stats`, journey `sync=true`), availability, radar
  (league-wide crawls), team-name fallback, worldwide search/follows, and GOL's `lookup_player` all call API-Football
  on demand. A code-level "frozen mode" at the shared client is required to make Explore truly database-only.
- `CRAWL_LEAGUE_IDS` empty/invalid falls back to defaults — it is not an off switch. `API_USE_STUB_DATA` returns fake
  sample data — never use it in prod. Removing `API_FOOTBALL_KEY` crashes callers rather than freezing.
- Newsletter `dry_run` request flag still sends mail — not a safe switch.
- Mailgun/SMTP and current Stripe (Scout/club subscriptions, GOL credits, webhooks) are shared with the new front door —
  do not disable them globally.
- Installed iOS apps keep calling the old endpoints, so the backend freeze must keep response shapes compatible.
- Film Room, local profiles, claims, club invitations, video maintenance and profile-activity emails do not depend on
  ingestion and keep running.

## Plan

### F1 — No-code switches (reversible, minutes, can run right after approval)
1. Record every live Azure job's current schedule, command and env first (the repo does not hold them).
2. Pause these scheduled jobs with the repo's documented impossible cron `0 0 31 2 *` (definitions kept):
   `job-weekly-newsletters`, `job-transfer-heal`, `job-sync-fixtures`, `job-scout-digest`; pause
   `job-status-refresh` / `job-data-fix` only if they turn out to be scheduled. Never invoke `job-full-rebuild`.
3. Env switches on the backend app: `NEWSLETTER_AUTO_SEND_ON_APPROVAL=0`, `AUTO_SYNC_FIXTURES_BEFORE_NEWSLETTER=false`,
   `ENABLE_TWITTER_ENRICHMENT=0`, `TRANSFER_SYNC_DAILY_BUDGET=0`, `SCOUT_DIGEST_API_BUDGET=0`.
4. Keep running: `job-video-maintenance`, `job-profile-activity`, scheduled scaling, the api_cache purge.
Undo: restore the saved crons and env values. No application DB change.

### F2 — Frozen mode in code (one PR, flag-gated, codex on basecamp)
- C1 `API_FOOTBALL_FROZEN=1` at the shared client: no handshake, no live fetch, serve stored/cached data, predictable
  "not available" on cache miss (never overwrite stored rows with empty results).
- C2 Gate ingest launchers while frozen: admin/CLI syncs, seeding, rebuilds, tracking side-effect seeds.
- C3 Database-only reads: player stats, season stats, journeys (drop `sync=true` fallback), availability (use existing
  "unknown" contract), team-name resolution, radar (hide or DB-only), worldwide search/follows (replace with DB search
  + "can't find them? create a profile"). Response shapes unchanged for old iOS builds.
- C4 Newsletter gate: generation, sends/test sends, publication/deadline processing, digest drains, Reddit/Twitter
  posting, new subscriptions. Unsubscribe/manage and history stay working.
Undo: flip the flag off.

### F3 — New front door (one PR, web; iOS labels in the next app release)
- C5 Home = the new homepage (stock-footage Film Room hero concept, owner feedback pending) leading with clubs and
  players; nav: Club Home, Players (onboarding), Explore players; hide Teams/leagues, Newsletters, Journalists/writers,
  Academy/cohorts, Dream Team from nav, global search and sitemap; gate their direct routes.
- C6 Labels: "Public match data — last updated <date>" on retained football facts, separate from Club-verified and
  Self-reported; "Claim your record" on public player pages; leaderboards say "last season with data" instead of
  implying current form.

### F4 — Policy calls (owner decisions below, then built into F2/F3)
- C7 Scout contact routing for pro (tracked) players stops trusting frozen "contracted/free agent" beliefs.
- C8 Stats: frozen public totals vs newer club-entered results.
- C9 GOL chatbot (the only paid feature) under the freeze.
- Raw API response cache retention.

## Owner decisions (recommendations marked)
1. **Scout contact for pro players** — (a, recommended) treat their contract status as "unknown", so contact goes
   through the club unless the player has claimed their profile and said otherwise; (b) keep using the frozen data.
2. **Stats** — (a, recommended) show public match data and club-entered results as two separate, labelled panels;
   (b) keep today's rule where public data always wins.
3. **GOL chatbot** — (a, recommended) keep it, answering from our stored data only (remove its live player-lookup
   tool), credits unchanged; (b) pause chat and new credit sales, keep balances/refunds/webhooks.
4. **Raw API cache** — (a, recommended) let the daily purge keep deleting expired raw API responses (all real
   football records stay); (b) pause the purge to keep every raw response forever.
5. **API-Football plan** — decide at renewal: keep paying (so we can un-freeze quickly) or cancel. Freezing does not
   by itself lower the bill; display rights for stored data after cancelling are unverified.

## Order of work after approval
F1 immediately (with the owner's go on prod changes) → F2 PR → F3 PR (with homepage) → iOS labels in next release.
Each PR: codex builds on basecamp → Fable adversarial review → fix rounds → PR → owner go → deploy + verify.

## F2 as built

- Owner decisions 1a/2a/3a/4a implemented on `feat/api-football-frozen-mode` (2026-09-25).
- `API_FOOTBALL_FROZEN=1`: stored/cache-only API boundary, no handshake/HTTP/stubs, no cache-miss writes, one process-level freeze log. Fresh raw cache only; expiry/purge unchanged.
- `NEWSLETTERS_FROZEN=1`: independent newsletter stop; also implied by `API_FOOTBALL_FROZEN=1`. Both default OFF. Shared email, Stripe/GOL credits, profile activity and Film Room remain available.
- Ops activation: set **`API_FOOTBALL_FROZEN=1` on the backend app AND every ingestion/newsletter/scout-digest job/process**, restart/redeploy those processes, and verify `GET /api/meta/data-mode` returns both booleans true. No frontend build-time flag is needed. Set `NEWSLETTERS_FROZEN=1` alone only for a newsletter-only freeze. Undo: set the flags to `0` and restart; review queued sends before resuming.
- DB-only reads retain list/object contracts: player stats/profile/season stats, journey `sync=true`, academy stats, availability (unknown/degraded), team-name resolver, radar (unavailable), scout comparison/search/follows. Unknown external follows receive 409 plus a local-profile hint; existing tracked/shadow/local follows work.
- Stats (frozen only): additive `public_match_data`, `club_verified`, `self_reported` blocks, with source labels and public `as_of` from sync/fixture evidence, never rollup computation time. Frozen legacy season totals select club-confirmed, else public, else self-reported; flag OFF returns the previous payload bytes and performs no enrichment queries. Read-time separation performs no rebuild or schema change. Corrections/disputes are read directly from existing source feeders.
- Contact: positive public identities have unknown platform contract belief; claimant attestation still controls the existing direct/club routing path. Local identity policy unchanged.
- GOL: only `run_analysis` offered while frozen; player lookup and web search refuse direct calls. Instructions describe stored data and do not promise live lookup; billing code unchanged.
- Web: two stat panels above the existing totals/match log, last-updated date, existing claim entry renamed “Claim your record” while frozen; worldwide affordances hidden on Scout/onboarding and changed to stored search in lists. Navigation/homepage remain F3.
- DB-only repairs (manual transfers, attribution/current-status/name repair without fetch, rollup rebuilds, cohort analytics refresh) remain available. Tracking toggles save normally but skip both single/bulk auto-seeds. Full rebuild is gated before destructive cleanup.
- File fence observed: backend, frontend, this directive only; no photo-serving/media-route/photo-serializer edits, lockfile/dependency changes, iOS or workflow edits. Root CONTINUITY.md is read-only per the explicit fence.

### Gate inventory

- 32 API route gates and 16 newsletter route gates return `409` with `code: frozen` before launch.
- 37 API worker/service/CLI guards and 27 newsletter worker/service/CLI guards reject direct entry, including both newsletter generators, destructive rebuild, Reddit and Twitter enrichment.
- Conditional guards: newsletter publication update, subscription confirmation, signed-in subscription management and token management reject new enrollment but allow removal; profile repair rejects `fetch_missing`; single/bulk tracking skip auto-seed; client/reads/GOL/contact apply the policies above.

**API routes (32)**

- `routes/academy.py`: `sync_academy_league`, `sync_all_academy_leagues`, `sync_academy_player_stats`.
- `routes/api.py`: `refresh_newsletter_fixtures`, `sync_leagues`, `sync_teams`, `admin_backfill_team_leagues`, `admin_backfill_team_leagues_all`, `admin_sync_player_fixtures`, `admin_sync_team_fixtures`, `admin_sync_all_player_fixtures`, `admin_backfill_fixture_raw_json`, `admin_backfill_ages`, `admin_backfill_formations`, `admin_verify_team`, `admin_bulk_fix_team_names`, `admin_refresh_newsletter_radar_charts`, `admin_sync_player_journey`, `admin_bulk_sync_journeys`, `admin_repair_journeys`, `admin_search_api_players`, `admin_test_classify`, `admin_explain_academy`, `admin_refresh_tracked_player_statuses`, `admin_seed_tracked_players`, `admin_seed_all_tracked`, `admin_sync_tracked_player_journeys`.
- `routes/cohort.py`: `admin_seed_cohort`, `admin_seed_big6`, `admin_sync_cohort_journeys`, `admin_full_rebuild`.
- `routes/scout.py`: `scout_admin_shadow_refresh`.

**Newsletter routes (16)**

- `routes/api.py`: `generate_weekly_all`, `generate_weekly_all_mcp`, `generate_newsletter`, `create_subscription`, `bulk_create_subscriptions`, `send_newsletter`, `generate_weekly_mcp_team`, `admin_bulk_publish_newsletters`, `admin_send_digest_emails`, `admin_post_newsletter_to_reddit`.
- `routes/curator.py`: `curator_generate_newsletter`, `curator_create_tweet`, `curator_attach_tweet`.
- `routes/newsletter_deadline.py`: `process_deadline`, `test_deadline_processing`.
- `routes/scout.py`: `scout_admin_send_digests`.

**API workers/services/CLI (37)**

- `api_football_client.py`: `_upsert_player_fixture_stats`, `_upsert_fixture_team_stats`.
- `jobs/run_data_integrity_fix.py`: `phase_1_backfill_team_profiles`, `phase_2_backfill_players`, `phase_4_refresh_statuses`, `phase_5_backfill_formations`, `run`.
- `jobs/run_full_rebuild.py`: `run`.
- `jobs/run_status_refresh.py`: `run`.
- `jobs/run_transfer_window_heal.py`: `run`.
- `main.py`: `seed_teams_cmd`, `reclass_journeys_cmd`, `sync_fixtures_cmd`.
- `routes/api.py`: `_sync_season`, `_sync_player_club_fixtures`, `_run_batch_fixture_sync`, `_run_team_fixtures_sync`, `_seed_single_team`, `_run_seed_team_process`, `_run_seed_teams_process`, `_run_seed_all_tracked_process`, `_start_background_seed`.
- `routes/teams.py`: `_lazy_sync_european_teams`.
- `services/academy_sync_service.py`: `sync_league`, `sync_all_active_leagues`, `sync_academy_stats_for_players`.
- `services/big6_seeding_service.py`: `run_big6_seed`.
- `services/cohort_service.py`: `discover_cohort`, `sync_cohort_journeys`.
- `services/gol_player_lookup.py`: `lookup`.
- `services/gol_service.py`: `_tool_lookup_player`, `_tool_search_web`.
- `services/journey_sync.py`: `sync_player`.
- `services/player_shadow_service.py`: `refresh_shadows`.
- `services/transfer_heal_service.py`: `refresh_and_heal`.
- `utils/rebuild_runner.py`: `run_rebuild_process`, `_run_full_rebuild`.

**Newsletter workers/services/CLI (27)**

- `agents/weekly_agent.py`: `persist_newsletter`, `generate_weekly_newsletter`, `generate_weekly_newsletter_with_mcp`, `generate_weekly_newsletter_with_mcp_sync`.
- `agents/weekly_newsletter_agent.py`: `persist_newsletter`, `compose_team_weekly_newsletter`, `generate_team_weekly_newsletter`.
- `jobs/run_scout_digests.py`: `run`, `main`.
- `jobs/run_weekly_newsletters.py`: `run_for_date`.
- `jobs/run_weekly_newsletters_mcp.py`: `run_for_date`.
- `routes/api.py`: `_activate_subscriptions`, `_deliver_newsletter_via_webhook`, `_maybe_post_to_reddit_on_publish`, `_maybe_auto_send_on_publish`.
- `scripts/enrich_newsletter_tweets.py`: `main`.
- `services/newsletter_deadline_service.py`: `queue_newsletter_for_digest`, `send_digest_emails`, `_send_single_digest`, `process_newsletter_deadline`, `process_single_newsletter_deadline`.
- `services/reddit_service.py`: `post_newsletter_to_reddit`, `post_to_subreddit`.
- `services/scout_digest_service.py`: `send_scout_digests`.
- `services/twitter_enrichment_service.py`: `enrich_newsletter`, `search_player_tweets`, `_api_call`.

### Initial-build verification and deviations

- Artifacts/logs/scratch: `/tmp/freeze-f2-work/`; `/tmp/freeze-f2.log` preserved.
- Focused frozen suite: **99 passed**, with requests/httpx transports patched to fail, testing cache hit/miss/failure, every route gate, workers/CLI, read shapes, scout search/follows/compare, radar, stats precedence/corrections/disputes, local/tracked contact, GOL, metadata, newsletter management/history, and cache expiry/purge.
- Full backend (flags OFF): **3,002 passed, 35 skipped, only the 3 known radar failures**, in 452.39s; failures match untouched HEAD on the same disposable fixture (`backend-verified.log`, `radar-baseline.log`). Frontend: setup/OSV passed; lint passed (0 errors, 182 existing warnings), build passed, **186 tests passed**. Backend ruff check and format check passed; git whitespace check passed.
- Browser: isolated Docker Postgres `freeze-f2-pg`, synthetic source DB `freeze_f2_source` cloned to `freeze_f2_qa`. Real app/routes/database and real GOL DataFrame/sandbox analysis; LLM response mocked. Backend requests/httpx transport rejects all external HTTP during browser checks. Player/search/chat have zero console/page errors; admin has only expected 409/refusal console messages.
- Screenshots: `shots/player-panels.png`, `shots/scout.png`, `shots/gol-db-answer.png`, `shots/admin-frozen.png` under the artifact directory. Development Agentation overlay hidden only in the browser harness because it overlaps GOL's launcher; onboarding prompt dismissed normally.
- Baseline radar comparison: untouched HEAD on the same isolated fixture reproduces exactly `test_full_radar_chart_data` (`peers_count`), `test_percentile_pool_stats` (missing `compute_position_percentiles`), and `test_old_vs_new_comparison` (`player_percentile`). No radar tests changed.
- Test-only correction: six baseline manual-transfer failures came from host-local `date.today()` being one day ahead of the resolver's UTC date. Fixtures now use `datetime.now(UTC).date()`; production transfer logic unchanged.
- Initial suite deviation: the first unpinned in-worktree full run inherited the existing loopback `127.0.0.1:5432/soccer_newsletter` DB from backend `.env` for radar reads. No write was performed by those checks. Subsequent full runs explicitly pin the disposable clone; no production/Azure/Supabase access. The first archived baseline also missed a repo-relative SQL fixture; the archive was supplemented for comparison.
- Setup: installed no app dependencies beyond the existing frozen lockfile. Downloaded OSV-Scanner into the scratch directory so `./scripts/setup_frontend.sh` could run its mandatory security gate; no lockfile edits. Optional absent PRAW SDK is mocked in one refusal test; provider construction would fail that test.

- Final browser rerun passed after correcting a local server-startup race; onboarding dialog dismissal was awaited for clean screenshots. Final full suite includes the journey-map geocoding guard. Web/backend servers stopped; both disposable databases dropped and Docker container/volume removed. Screenshots/logs retained; `/tmp/freeze-f2.log` untouched.
- Changed-file inventory: `/tmp/freeze-f2-work/changed-files.txt` (43 backend, 8 frontend, this directive; 52 files total).

### Fix round 1 — complete (2026-09-25)

- P1: early OFF returns in season separation, player/journey response hooks, and academy stats. No OFF source keys or extra SQL; PlayerPage reads the shared `/api/meta/data-mode` request. Ten golden cases compare response bytes, JSON and complete SQL statement sequences against the same legacy handlers with F2 enrichment disabled, with existing caches primed equally. Rollup reads ON/OFF are both covered.
- P2-1/11: source panels precede the existing stats chain; a frontend render test verifies the real PlayerPage stats section retains its table and stored opponent in both modes.
- P2-2/5: frozen approvals mint sanitized seed-only shadows (no upstream call/sync timestamp); existing shadows reactivate locally, including inactive untracked follows. Unknown external follow creation remains refused. Negative identity collision checks remain intact.
- P2-3/4/6: preserve DB-computed clean sheets and `compute_stats()`; cohort analytics refresh is available through its admin route and service.
- P2-7: seven job entrypoints and the Twitter-enrichment script catch only `FrozenModeError`, print its message and exit 1 without traceback. Direct worker guards remain.
- P2-8: all mounted `useDataMode` consumers share one module-level promise per page load, including a cached safe-default error result.
- P2-10: Nominatim geocoding is independent of the API-Football flag again; its normal fallback is tested with a mocked provider response.
- Focused freeze suite: **126 passed**. Focused + touched suites: **282 passed**. Frontend lint passed (0 errors/182 existing warnings), build passed, **190 tests passed** (including 4 new render/cache tests). Ruff check and format check passed. Full backend (flags OFF): **3,029 passed, 35 skipped, only the same 3 known radar failures**, in 197.69s (`fix1-backend-full.log`). No radar tests changed.
- Browser: disposable Postgres source cloned to `freeze_f2_qa`; source panels plus **4 stored match rows** visible, zero console/page errors. Screenshot: `/tmp/freeze-f2-work/shots/player-panels-v2.png`. Web/backend servers stopped; both disposable databases dropped and Docker container/volume removed. Logs and screenshots retained.
- This round uses explicit disposable DB variables throughout. Initial touched-suite collection lacked dummy LLM keys; rerun passed with test keys. No app dependency/lockfile changes or edits to photo-serving/media code.
- Scratch `/tmp/freeze-f2-work/`; `/tmp/freeze-f2-fix1.log` preserved. One new commit, no amend/push.


OFF SQL counts (baseline and fixed code match; response bytes/JSON also identical):

| Endpoint | Rollups OFF | Rollups ON |
|---|---:|---:|
| season-stats | 9 | 6 |
| profile | 7 | 7 |
| stats | 9 | 12 |
| journey | 5 | 5 |
| academy-stats | 3 | 3 |

- Fix-round file inventory: `/tmp/freeze-f2-work/fix1-changed-files.txt` (19 backend, 3 frontend, this directive; 23 files). Gate inventory: `/tmp/freeze-f2-work/fix1-gates.json`. All changes remain within the original fences.
