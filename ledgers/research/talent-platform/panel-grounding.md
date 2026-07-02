I have a complete picture. Here is the grounded inventory.

# Repo Grounding: Exact Substrate for the Three Designs

## (1) Email subscriptions & newsletter recipient resolution

**`UserSubscription`** (`models/league.py:310-339`) — the ONLY team-subscription primitive. Keyed by **email string, not user_account_id**:
- Fields: `email` (str, required), `team_id` FK→`teams.id` (required, **exactly one team per row** — no grouping), `preferred_frequency` (default `"weekly"`), `active`, `unsubscribe_token` (unique), `last_email_sent`, `bounce_count`, `email_bounced`.
- Consequence for MJ's ask #1: **there is no "group of teams" or "group of players" subscription object.** A "custom-tailored newsletter" today can only be expressed as N rows (one per team) sharing an email. Player-level and cross-country grouping has no home in this table.

**`UserAccount`** (`models/league.py:490-590`) carries the real preference columns the personalized-newsletter design would extend:
- `email_delivery_preference` = `'individual' | 'digest'` (`:512-514`, default `individual`)
- `scout_digest_opt_in` (bool, default true, `:517`)
- `scout_tier` (`'free'` default, `:518`) — **the entitlement column for billing; not wired to Stripe.**
- Note: `UserSubscription` links by email, `UserAccount` by id — they are **joined only by matching `email`** (see `api.py:260`, `:631`). No FK between them.

**Newsletter send path** — per-team, via n8n webhook, not the Mailgun `email_service`:
- Route `send_newsletter(newsletter_id)` at `api.py:4387` → `_deliver_newsletter_via_webhook` at `api.py:3998`.
- Recipient resolution: `api.py:4044-4071` — `UserSubscription.query.filter(active).filter(team_id.in_(team_ids))`, drops `email_bounced`, dedupes case-insensitively. **Recipients are derived purely from `team_id`.** `recipients=None` → fetch all active team subs (`:4070`).
- Sent-marking + `last_email_sent` fan-out: `api.py:4475-4500`.
- A **second, separate digest path** exists: `services/newsletter_deadline_service.py` — `NewsletterDigestQueue` model + `queue_newsletter_for_digest` (`:21`), `send_digest_emails` (`:56`), `_send_single_digest` (`:109`) bundles a week's newsletters per user whose `email_delivery_preference='digest'`. **This also goes out via `N8N_EMAIL_WEBHOOK_URL`** (`:238-264`), not `email_service`.

⚠️ **Contradiction with the brief:** the brief says "Mailgun delivery." The team-newsletter and digest paths actually deliver through an **n8n webhook** (`N8N_EMAIL_WEBHOOK_URL`); the Mailgun-backed `services/email_service.py` (`send_email`, SMTP fallback) is used by the **scout digest** path, not by team newsletters.

## (2) Scout digest send path — the pattern personalized newsletters generalize

`services/scout_digest_service.py` is the closest existing template for per-user, player-set emails and is the natural thing to generalize:
- `send_scout_digests(dry_run, limit, api_client, cursor)` (`:225`): SQL-filters eligible users (`UserAccount.email NOT NULL AND scout_digest_opt_in IS TRUE`, `:250-263`), **cursor-paged by `user_account_id`** with `next_cursor` (`:338-344`), bounded by `MAX_DIGEST_USERS=200` / `MAX_DIGEST_ENTRIES=2000` (`:21-24`) to keep a synchronous admin request finite.
- Per-user content: `build_user_digest` (`:218`) → `_entry_update` (`:97`) per watchlist entry. Cross-user **player-state memoisation** (`_player_state`, `:84-94`) computes `TrackedPlayer.compute_stats()` + injuries **once per player** across all users — the key cost pattern to reuse when many users follow the same player.
- **Delta engine:** compares live stats vs `ScoutWatchlistEntry.last_snapshot` JSON, emits chips (`+goals/+assists/+apps/+mins`), status-change headlines (`_STATUS_LABELS`, `:30-36`), best-effort new-absence counts. Persists `last_snapshot`/`last_digest_at` only on successful non-dry-run send (`:330-333`).
- Uses `email_service.send_email(..., tags=["scout-digest"])` (`:311`, Mailgun) and template `scout_digest_email.html` (`:203`).
- **This function already IS a "newsletter for an arbitrary set of players a user chose."** The gap is only *which set* — today it's hardcoded to `ScoutWatchlistEntry` rows for that user. A grouping primitive (see §6) would slot in at `:285-289` where entries are fetched.

## (3) AI newsletter generation entry points & data shape

Two agents: `agents/weekly_agent.py` (2519 lines, the live OpenAI-Agents-SDK orchestrator) and `agents/weekly_newsletter_agent.py` (3966 lines, Groq-based enrichment/scoring/player-metadata).

Entry points (`weekly_agent.py`):
- `generate_weekly_newsletter(team_db_id, target_date, force_refresh)` (`:1235`)
- `generate_weekly_newsletter_with_mcp(...)` (`:1550`) and sync wrapper `generate_weekly_newsletter_with_mcp_sync` (`:2516`)
- Agent built by `build_weekly_agent()` (`:1223`) with two tools: `fetch_weekly_report_tool` (`:1200`) and `persist_newsletter_tool`.

Input data shape (`fetch_weekly_report`, `weekly_agent.py:829-872`):
- Args: `{parent_team_db_id, target_date}` — **the generator is inherently team-scoped and week-windowed** (`monday_range(tdate)`, `:849`). Season is inferred European-style (`season_start_year = year if month>=8 else year-1`, `:856`).
- Report payload from `api_client.summarize_parent_loans_week(...)` (`:860`) contains: `loanees` (per-player weekly match data), `academy_watch` (season snapshots: `player_api_id, player_name, level, competition, season totals`), `academy_appearances_week` (youth fixtures in window). Docstring at `:833-839`.
- Output persisted by `persist_newsletter` (`:875`) as `content_json` with `{title, summary, sections:[{title, items:[player items]}]}` (`:917`). Player items enriched/deduped/untracked-filtered by `_enforce_player_metadata` (`weekly_newsletter_agent.py:189`), key normalization via `_normalize_player_key`.

Cost-relevant structure for MJ's ask: the token cost scales with **players in the report**, and the whole pipeline assumes **one parent team**. A cross-country/custom-group newsletter would need a new report-assembler that unions per-player data (the `loanees`/`academy_watch` item shape) without the single-team `summarize_parent_loans_week` call — then it can reuse the same `content_json` sections schema and `_enforce_player_metadata` enrichment.

## (4) League/region footprint & Ecuador/Colombia coverage

`utils/supported_leagues.py`:
- `SUPPORTED_LEAGUES` (`:29-51`) = **16 leagues** across 4 regions, keyed by API-Football league ID. Regions at `:24-27`.
- ⚠️ **Ecuador and Colombia are NOT in the map.** South America contains only Brazil Serie A (71) and Argentina Liga Profesional (128) (`:43-44`). MJ's example "random players I follow in Ecuador + Colombia" is **not coverable today** — those leagues (Ecuador Serie A = API-Football 242; Colombia Primera A = 239) would first need adding to `SUPPORTED_LEAGUES`.
- Two-tier mechanics: `get_supported_leagues()` (`:71`, overridable via `SUPPORTED_LEAGUE_IDS` env — can only *narrow*, unknown IDs ignored `:78-81`) drives metadata/browse. `get_crawl_league_ids()` (`:85`) defaults to **European top-5 only** (`DEFAULT_CRAWL_LEAGUE_IDS = (39,140,135,78,61)`, `:55`); expensive fixture/stat/loan crawls only run on `CRAWL_LEAGUE_IDS`.
- **What widening to Ecuador/Colombia takes:** (a) add the two league dicts to `SUPPORTED_LEAGUES`; (b) add their IDs to `CRAWL_LEAGUE_IDS` env for actual stat ingestion (the costly step gated per the memory note about crawl quota). Adding to the map alone gives browse/metadata but no verified stats.

## (5) Stripe surface — what's actually wired

⚠️ **Contradiction with the brief:** the brief implies Stripe Connect writer payouts are integrated. **They are not live.** Grep for real Stripe API calls (`stripe.checkout`, `Session.create`, `construct_event`, `AccountLink`, `stripe.Subscription`) across all routes returns **zero hits**. What exists:
- `config/stripe_config.py` — key loading, `PLATFORM_FEE_PERCENT` (default 10, `:16`), `calculate_platform_fee` (`:35`), `validate_stripe_config` (`:47`). Config only.
- Models `StripeConnectedAccount` (`league.py:986`), `StripeSubscriptionPlan` (`:1020`), `StripeSubscription` (`:1055`) — **all three docstring-marked `DEPRECATED`.**
- **Video credits** (`models/video.py:338` `VideoCreditLedger`): append-only ledger, `balance(team_id)=SUM(delta)` (`:355-360`), `reason ∈ CREDIT_REASONS`, and a **reserved `stripe_session_id` unique column (`:349-350`) explicitly designed so a replayed Stripe webhook cannot double-credit.** Debit path is live (`routes/video.py:277`, 402 on empty balance). Grant path is **admin-only** (`grant_credits`, `video.py:558`) — docstring: *"Stripe purchases arrive via the webhook in **Phase B**; concierge sales are recorded here."*
- **Reusable seam for billing:** the credit-ledger + reserved `stripe_session_id` is the cleanest place to attach the *first real* Stripe checkout+webhook. `scout_tier` on `UserAccount` is the equivalent unwired entitlement hook for subscriptions. Both are designed-for but greenfield.

## (6) Grouping primitives beyond watchlist + team subscription

- **`ScoutWatchlistEntry`** (`models/scout_watchlist.py:12-24`): `user_account_id` + `player_api_id` + `note` + snapshot fields. **This is the only per-user player-set.** No tags, no folders, no named lists — flat list per user (200 cap per brief). Grouping ("players in Ecuador + Colombia") would need either a `list_id`/tag column here or a new `WatchlistGroup` table.
- **`AcademyCohort` / `CohortMember`** (`models/cohort.py`): a cohort = `(team_api_id, league_api_id, season)` (`:19-25`) with aggregate counts; `CohortMember` (`:81`) holds `player_api_id`, per-cohort stats, and `journey_id`. **This is a system-defined grouping (a club's academy intake for a season), not user-defined** — but it directly answers MJ's "all players in club X's academy" example. Service: `cohort_service.py`, route `routes/cohort.py`.
- **`TeamFormation`** (`models/formation.py:6`): `team_id` + `positions` JSON — tactical board, **not a player-group for newsletters.** Not relevant.
- **`FeederService`** (`services/feeder_service.py:31`, route `feeder.py`): feeder-club relationships (pathway analysis), not a subscribable group.
- **`JournalistTeamAssignment`** (writer↔team) and `UserSubscription` (email↔team) are the only other team-scoped groupings.

**Bottom line on grouping:** the only user-owned set is the flat watchlist; the only rich player-collection is the system-owned cohort. Neither is subscribable/deliverable. Custom-tailored newsletters need a **new user-owned grouping object** (e.g. a named "list" of `player_api_id`s, or a saved Scout Desk filter) that the generalized scout-digest send path (§2) would iterate instead of raw watchlist entries.

## Key seams the synthesis should cite
- Generalize `send_scout_digests` (`scout_digest_service.py:225`) + its per-player memoisation as the personalized-newsletter engine; feed it a grouping object instead of raw `ScoutWatchlistEntry`.
- Reuse `content_json` `{sections:[{items}]}` schema + `_enforce_player_metadata` (`weekly_newsletter_agent.py:189`) for AI copy, but replace the single-team `summarize_parent_loans_week` assembler.
- Add Ecuador (242) / Colombia (239) to `SUPPORTED_LEAGUES` + `CRAWL_LEAGUE_IDS` before those can be followed with real stats.
- Attach the first live Stripe checkout+webhook to `VideoCreditLedger.stripe_session_id` (already idempotency-ready) and `UserAccount.scout_tier` — both currently unwired.
- New grouping table needed; nothing existing (watchlist is flat, cohort is system-owned, formation/feeder are unrelated).