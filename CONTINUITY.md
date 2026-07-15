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
- iOS P4a launch performance complete (2026-07-15): verified Scout players/leaderboards were already concurrent; added schema-v1 SWR disk caches, independent cached-data refresh indicators, app-start health warm-up, and DEBUG launch timings. Simulator time-to-first-row improved from 29.716s network-cold to 1.953s from disk cache; XcodeGen/build and all 51 tests pass; cached-launch screenshot captured.
- iOS physical-device first look confirmed working by MJ; automatic signing committed/pushed as `a28d5df` (2026-07-15).
- iOS `feat/ios-app` review fix round complete (2026-07-15): all 11 verified findings fixed; XcodeGen + build + unsigned archive pass; 45 tests pass; two dark-mode screenshots visually verified.
- iOS `feat/ios-app` adversarial review complete (2026-07-15): baseline build + 35 tests pass; verdict FIX-FIRST with 9 major and 2 minor confirmed findings; app source unchanged.
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
- Match Video Analysis feature ("Film Room") — design complete (2026-06-10)
  - Upload match video → GPU CV pipeline → human tag review → per-player reports; pay-per-match credits
  - Stack: RF-DETR + BoT-SORT (roboflow/trackers) + SigLIP team clustering + own pitch-keypoint model
    (Apache/MIT only — ultralytics YOLOv8 is AGPL, banned from serving path)
  - Infra: ACA serverless GPU (T4) Jobs + Service Bus; COGS ≤$3.50/match; price $25/match, floor $13
  - v1 = own-team player reports only (minors/GDPR); opposition stays anonymous
  - Phase 0 validation spike is the gate; task 0.1 (acquire grassroots footage) is `ready`
  - **See `ledgers/CONTINUITY_video-analysis.md`**
- Global Talent Platform — Scout discovery + footprint expansion (2026-06-12)
  - Goal set via /goal: #1 resource for up-and-coming talent worldwide
  - Supported-league config now global (16 leagues, 4 regions) with separate
    `CRAWL_LEAGUE_IDS` control so API quota stays explicit (default top-5)
  - New public Scout API: `/api/scout/players` (browse/filter/sort),
    `/api/scout/leaderboards`, `/api/scout/compare` — SQL-aggregated stats
  - New `/scout` frontend page ("The Scout Desk"): leaderboards, filterable
    ranked table with last-5 form bars, up-to-4-player comparison
  - Injury/availability tracking (API-Football injuries endpoint, previously
    unused): `/api/players/<id>/availability` + PlayerPage card + compare
  - Region-aware Teams page (league_api_id-keyed grouping); Home copy global
  - Scout workspace (slice 3, migration aw15): per-user watchlists with notes,
    weekly digest email (admin-triggered, cursor-paged, dry-run previews),
    CSV export, /pricing page with scout_tier entitlement scaffold (billing
    wiring deferred to MJ's pricing decisions)
  - Newsletter rebuild (slice 4, migration aw16): academy players in the
    weekly report for the first time (payload + agent instructions); email
    rewritten — 132KB→77KB (Gmail clip-safe), Outlook-safe HTML/CSS data-viz,
    Squad Watch with real injury reasons, Academy Watch from season stats;
    operator must set EMAIL_POSTAL_ADDRESS (CAN-SPAM)
  - Academy provenance enforcement (slice 5): prior-senior-career rule —
    clubs only track their OWN academy products (Malacia fixed); owning-club
    rows removed; repair endpoints (recompute-academy, backfill-names) ran
    locally: 221 misattributed rows deactivated, 1,128 placeholder names
    fixed; PROD: run both repair endpoints (dry_run first) after merge
  - Final-form provenance (slice 6): typing-layer precedence bug fixed
    (integration checks before development shield; buy-back + teenage
    guards); recompute re-types stored entries; profile completeness
    backfill (position/birth/age/nationality) + opt-in capped API fetch
    mode. Malacia entry now honestly 'integration', 0 active rows.
  - Academy tracking window (slice 7, 2026-06-13, migration aw18): platform
    now only tracks players in an academy NOW or within the past 4 seasons
    (utils/academy_window.py), enforced at journey upsert, recompute repair,
    rebuild/seed/GOL creation; scout API drops owning-club rows and derives
    age from birth_date in SQL (fixes U18/U21/U23 = 0 players in prod);
    recompute-academy now cursor-paged (fixes prod statement_timeout 500s)
  - Live-validated: 16 leagues + 335 teams synced; PR #419 green, awaiting MJ
  - Side-fix: PR #420 (merged) repaired Dependabot-corrupted pnpm-lock.yaml
    that was failing ALL frontend CI; react-hooks v7 rules pinned to warn
  - Branch `feature/global-scout-discovery`
  - **See `ledgers/CONTINUITY_global-talent-platform.md`**
- Talent Showcase — two-sided vision slice SHIPPED to branch (2026-07-02, /goal)
  - Vision: players worldwide get showcase profile pages (YouTube highlights,
    commentary, verified stats) for discoverability; clubs upload footage and
    get per-player stats (Film Room). Roadmap: P0→F0→P1→X sequencing.
  - This slice: P0 (Showcase section on PlayerPage: highlight reel from
    PlayerLink + newsletter yt merge) + P1 (claim & curate: user claims,
    admin approves, owner curates reel/bio — ALL owner content pre-moderated,
    self-reported vs verified hard-separated) + X (Film Room finalized
    reports → "Club-verified" appearance evidence on profiles; roster→player
    linking admin UI; only human_confirmed identities surface)
  - Migration aw19 (merge cs01+vid02 → single head restored; claims +
    showcase-profile tables + player_links.sort_order). aw19 upgrade verified
    on real Postgres clone; downgrade across merges needs explicit target.
  - Security: shared https-only URL validator; pre-existing
    submit_player_link javascript:-URL hole closed; newsletter yt merge
    filtered server-side.
  - Built multi-agent (Fable 5 orchestrator + Opus 4.8 builders), 6-surface
    recon, adversarial review (23 agents: 8 confirmed findings ALL fixed,
    1 refuted), 40 backend tests, live-verified end-to-end incl. UI screenshot
    (demo: player 403064 H. Amass — reel + profile + verified appearance).
  - Branch `feature/talent-showcase` (worktree) — PR opened, awaiting MJ
  - PROD OPERATOR STEPS after merge: flask db upgrade (aw19); vid03 (still
    uncommitted in the video branch) must rebase onto aw19 before it lands
  - Known pre-existing (NOT this slice): full migration chain cannot replay
    on an EMPTY DB (old unguarded supplemental_loans migration)
  - **See `ledgers/ROADMAP_talent-showcase-vision.md` + `docs/showcase.md`**
- Follow Graph + Shadow Tracking — Phase 1 SHIPPED to branch (2026-07-02)
  - Scouts organize tracking into named LISTS of FOLLOWS (kinds: player |
    academy_club | geo playing_in/nationality | saved query) — one resolver
    over the scout query engine; digest generalized ADDITIVELY (legacy
    watchlist section byte-identical; non-default lists render as grouped
    sections, watchlist-wins dedup; default lists are the watchlist's mirror
    twin and never route)
  - SHADOW TRACKING: following any untracked player worldwide mints a
    PlayerShadow (players/profiles fetch, seed fallback offline) + dedicated
    PlayerShadowStats (NOT PlayerStatsCache — unowned legacy, kept isolated);
    /players/<id> profile + season-stats shadow fallbacks; worldwide name
    search via new client method search_player_profiles_global; caps via env
    (10 lists / 50 follows / 10 shadows per user — billing later)
  - Migration aw20 (chains aw19, single head preserved). Watchlist backfill is
    a cursor-paged admin endpoint + dual-write mirrors, not a data migration
  - Adversarial review (21 agents): 8 confirmed findings ALL fixed — headline:
    the dual-write mirror was silently rerouting watchlist users onto the list
    digest path (grouped layout + ASC order + cap-40 truncation); redesigned to
    additive semantics with a REAL-API-path regression test (old test was
    blind: it seeded entries directly)
  - 164 backend tests green (test_scout_watchlist UNMODIFIED); ruff clean;
    lint 0 errors; live-verified incl. real worldwide search (Endrick shadow
    mint), digest dry-run (legacy user unchanged + grouped sections + "Now
    tracking worldwide" card), ListsPage screenshots
  - Branch `feature/follow-graph` STACKED on feature/talent-showcase —
    PR based on the showcase branch until #565 merges
  - LOCAL DEV DB note: cs01 columns (player_journeys.current_status etc.) were
    missing locally (never applied — DB stamped on vid chain); applied manually
    2026-07-02. Local scout browse had been broken since #514 merged.
  - **See `ledgers/research/talent-platform/` (design panel) + `docs/follow-graph.md`**

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
  └─ ledgers/CONTINUITY_plan-ios-adversarial-review.md (complete, report-only)
  └─ ledgers/CONTINUITY_plan-ios-review-fix-round.md (complete)
  └─ ledgers/CONTINUITY_ios-device-install.md (complete: MJ confirmed launch)
  └─ ledgers/CONTINUITY_ios-p4a-launch-performance.md (complete)
  └─ ledgers/CONTINUITY_cohort-dynamic-resolution.md (in-progress)
  └─ ledgers/CONTINUITY_video-analysis.md (design complete — Phase 0 ready)
  └─ ledgers/CONTINUITY_global-talent-platform.md (implementation complete — PR review)
```

## Active Ledgers

| Ledger | Status | Owner | Blockers |
|--------|--------|-------|----------|
| ACADEMY_WATCH_REFACTOR_PLAN.md | complete | — | Phases 1-4 done |
| ACADEMY_WATCH_IMPLEMENTATION_PLAN.md | in-progress | — | Phases 1-5 done, Phase 6 ready |
| ACADEMY_WATCH_JOURNEY_REDESIGN.md | complete | — | Design doc for journey feature |
| CONTINUITY_plan-ios-adversarial-review.md | complete | codex | 9 major and 2 minor findings reported; fixes not in scope |
| CONTINUITY_plan-ios-review-fix-round.md | complete | codex | none |
| CONTINUITY_ios-device-install.md | complete | /root | none; MJ confirmed launch |
| CONTINUITY_ios-p4a-launch-performance.md | complete | /root | none; deliver on PR #634 |
| CONTINUITY_cohort-dynamic-resolution.md | in-progress | codex | pending live Full Rebuild validation |
| CONTINUITY_video-analysis.md | design complete | — | Phase 0 blocked on footage acquisition (0.1) + MJ decisions (pricing, footage source) |
| CONTINUITY_global-talent-platform.md | implementation complete | claude | awaiting PR review/merge |
| CONTINUITY_admin-interface.md | shipped (PR #432, prod 2026-06-14) | claude | manual click-through QA recommended |

## Cross-task Blockers / Handoffs

- None for iOS P4a; PR #634 remains the delivery target on `feat/ios-app`.

## Trivial Log

- 2026-07-08: Scout Desk phase-of-play views (feat/scout-phase-views). `?phase=all|attack|midfield|defense|gk` ToggleGroup on `/scout` swaps stat columns, sort options, default sort, and leaderboard cards per phase (filters to the matching position). Backend: `_fixture_stats_subquery` widened with 17 phase aggregates + derived duel-win%/Tkl-90/KP-90/GA-90/save%; 13 new sort keys (rate keys get the 270' floor); `?phase=` board sets on `/scout/leaderboards` (GK boards clamp to Goalkeeper). **GK stats (saves/GA/CS/pen-saved) are gated to per-fixture position='G' rows** — API-Football reports `conceded:0` for OUTFIELD appearances (87k prod rows), so ungated aggregates mint a phantom clean sheet per 60'+ outfield app (caught by 31-agent adversarial review; regression tests pin it). Phase stats are null (dash) for no-coverage players, never fake zeros. Companion PR `fix/fps-full-stat-block`: all 5 trimmed FPS writers unified on `utils/fixture_stats_mapper.py` so interceptions/blocks/pass-accuracy/dribbles (0% populated in prod — writer gap, raw_json only on 131 rows so NOT backfillable) start accruing; historical backfill would need an API re-sync (quota + invariants §7 — not scheduled).
- 2026-06-25: Scout page now reflects a player's ACTUAL current situation (matches PlayerPage). `scout.py._base_scout_query` outer-joins `player_journeys` (on unique `player_api_id`, ≤1 row) and exposes `effective_status = coalesce(journey.current_status, tracked_player.status)`; the status filter uses it so it never disagrees with the displayed badge. `_row_to_dict` + `scout_compare` override `status` and add `owner_team_id`/`owner_team_name` when `current_status` is set. `ScoutPage.jsx` CLUB column "from X" now prefers `owner_team_name` (e.g. Rijkhoff → "from Ajax", not "from Borussia Dortmund"). Tests: `TestCurrentSituationOverride` in `test_scout_blueprint.py` (38 pass).
- 2026-04-08: Added admin-only newsletter PDF download (WeasyPrint) — endpoint `GET /newsletters/<id>/download.pdf`, reuses existing `newsletter_email.html` template with injected print CSS (`@page`, `break-inside: avoid` on `.item`/`.highlights`/`.toc`/`.matches-section`, `break-before: page` on section `<h2>`s). Dockerfile gains libpango/libcairo/libgdk-pixbuf/shared-mime-info (~80MB). Download buttons in `AdminNewsletters.jsx` row actions and `NewsletterPreviewDialog.jsx` control panel. Plan file at `.claude/plans/staged-wibbling-cocoa.md`.
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
