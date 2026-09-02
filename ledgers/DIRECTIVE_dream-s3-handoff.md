# DIRECTIVE — Dream roadmap handoff: S0–S2 shipped (61.0%), S3 "money rails" next

Written 2026-09-03 (early JST) by the orchestrating Fable session (`loanarmy-d9`) for the NEXT session. `loanarmy-d9` stays open for
questions for a while (message it by name via SendMessage; MJ asked it to help). Read in this order: this file →
`ledgers/GRADING_dream-scorecard-2026-09-02.md` (rubric, every row, the S3 stage line) → `ledgers/CONTINUITY_dream-s2.md` (what shipped, how,
gotchas, debts) → `ledgers/DIRECTIVE_dream-s2-handoff.md` §2 (the method, unchanged) → `ledgers/tooling/dream-scorecard/README.md` + `s2/`.

## 1. Where things stand (verified 2026-09-03, not remembered)

- **Score:** baseline 51.9% → S0 54.1% → S1 59.8% → **S2 61.0%** (computed by `score.py`; S2 projection = actual). Lived adoption is still
  ~0: 9 accounts (5 team), 1 approved player claim, 0 clubs, 0 funding leagues, 0 fans, 0 paid scouts, $0. Scorecard page (republish to THIS
  url with the Artifact tool's `url` param; favicon 📊): https://claude.ai/code/artifact/1ac9cfc9-9540-4a41-80a6-1e3846fbb8d9.
  QA walkthrough MJ uses to experience S2: https://claude.ai/code/artifact/2c44ca84-b5bd-4b5c-bb5c-6c8697c65373 (favicon ✅).
- **S2 merged + live (all 2026-09-03):** #978 P0 foundation (`player_fans`, `resolve_public_adult_subject` gate, `reach_metrics`, migration
  `s2f1`), #983 P1 fan follow/counts/`profile_view`/owner signals/email opt-in, #980 P2 share pages + Pillow card + sitemap + robots,
  #984 P4 weekly opt-in activity email (ACA job `job-profile-activity`, Mon 07:30 UTC, dry-run proven, live env), #979 P3 web, #986 re-score,
  #987 `PUBLIC_SHARE_BASE_URL`, #988 site robots line. MJ deployed a **Cloudflare Worker** (`ledgers/tooling/dream-scorecard/s2/cloudflare-share-worker.js`) that forwards `theacademywatch.com/p/*` and `/sitemap.xml` (+www) to the API host.
- **Prod (RG `rg-nbhd-prod`, app `ca-loan-army-backend`, custom domain `api.theacademywatch.com`, ACR `acrbwmj`):** latest revision healthy;
  env `CONTACT_RAIL_ENABLED=1`, `SCOUT_INCLUDE_LOCAL_PLAYERS=1`, `SHOWCASE_TRUST_MIN_ACCOUNT_AGE_DAYS=14`, `PUBLIC_BASE_URL=https://theacademywatch.com`,
  `PUBLIC_API_BASE_URL=https://api.theacademywatch.com`, `PUBLIC_SHARE_BASE_URL=https://theacademywatch.com`. **Alembic head `cb01`**
  (chain … pm01 → s2f1 → cb01; cb01 belongs to the coach's-brief work of session `go-cb01`/`video-analysis`) — any S3 migration chains from
  the CURRENT head at dispatch time (re-verify with `flask --app src.main db heads`; coordinate with whoever else has a migration in flight:
  never two heads from one parent; whoever merges second re-chains). Secrets are `kvref:` pointers into `kv-loan-army`; DB via `supabase-db-*`
  + session pooler; never print values. **Stripe in prod is LIVE mode** (`STRIPE_SECRET_KEY` = sk_live…, `STRIPE_PUBLISHABLE_KEY` = pk_live…,
  `STRIPE_WEBHOOK_SECRET` set) — real money. ACA jobs: sync-fixtures 05:00, transfer-heal 03:00, video-maintenance 03:00, scout-digest Mon 07:00,
  profile-activity Mon 07:30 UTC (create jobs with `az containerapp job create`, secrets copied vault→vault, `PYTHONPATH=/app`; `--args`/`--env-vars`
  on `job start` do NOT reach the container — set env on the job and flip it back).
- **Prod counts (read-only, 2026-09-03):** stripe_subscriptions 0, user_subscriptions 8 (newsletter), stripe_connected_accounts 0,
  stripe_platform_revenue 0, club_connect_accounts 0, video_credit_ledger 2, club_programs 0, funding_leagues 0, scout_tier≠free 0,
  player_fans 0, profile_view events 16.
- **Repo:** primary checkout `/Users/michaeljones/Projects/loanarmy` = integration station (keep clean; `git stash push CONTINUITY.md && git pull
  --ff-only && git stash pop` because `CONTINUITY.md` is TRACKED and other sessions edit it; `ledgers/CONTINUITY*.md` are gitignored → `git add -f`).
  Worktrees under `.worktrees/` (`local-app` = MJ's live dev app on ports **5001/5173 — never touch**, session `loanarmy-ac`).
- **Peers (ListAgents):** `go-cb01` (coach's brief C-series; owns the deploy lane in turns — EVERY merge incl. docs runs the full Deploy and
  locks ACA ~5 min; announce before merging, wait for their Deploy, they announce theirs), `loanarmy-ac` (5001/5173), `loanarmy-1b`/`loanarmy-d9`
  (previous orchestrators, questions only), sautai sessions (codex account load; ~8 concurrent codex runs is the practical ceiling). Basecamp:
  SSH `mjjones@100.82.160.117` (`ssh-add --apple-load-keychain`); `pgrep -f "qwen_match_analysis|run_bench"` before heavy use; only ONE web sim
  at a time (`basecamp_sim.sh` aborts with "ANOTHER SIM IS RUNNING" — re-queue with an until-loop on `pgrep -f sim/run.mjs`).
- **PR review bot (`chatgpt-codex-connector`)** reviews within ~4 min of `gh pr ready` when it has quota (it caught 5 real defects on S2); when it
  says nothing in 4 min, merge on checker + CI + sim. Branch protection `strict` OFF (keep it). Backend CI has NO pytest step (ruff only) — the
  named test files run by codex + the checker ARE the gate; main has ~4 documented pre-existing failures (`test_local_clubs.py
  TestAffiliationVisibility` ×3, `test_account.py` delete-erases ×1) — report separately, never "fix" fixtures for them.

## 2. The method (unchanged from S2 — reuse exactly; new gotchas at the end)

recon (codex read-only, JSON via `-o`, detached worktree at `refs/remotes/origin/main`) → **brief critique** (codex read-only over the
assembled briefs BEFORE dispatch; S2's found 40 issues, most real) → briefs (`s2/s2-brief-common.md` header pattern + package body: numbered
requirements with path:line anchors, ALLOWED list, gates with absolute interpreters, ONE commit with exact message, report contract) →
launch codex from a foreground Bash (`nohup caffeinate -is codex exec --cd <wt> --sandbox danger-full-access -o <report> "$(cat brief)"
< /dev/null > <log> 2>&1 &`; `--skip-git-repo-check` when `--cd` is not a git dir) → persistent Monitor (report file / pgrep / death strings,
exclude `chatgpt-codex-connector`) → **check** (`model:'fable'` general-purpose subagent per package with `s2/s2-checker-template.md`; JSON verdict
to a file — messages truncate at ~4 KB; keep concurrent Fable checkers ≤3: one died on an account credit limit) → fix rounds
(`codex exec resume <session id> "<numbered fix brief>"`; same checker via SendMessage) → land (push → draft PR → CI → basecamp sim 9/9 → bot
window 4 min → `gh pr ready` → lane idle + peer told → `gh pr merge --squash` → prod DDL pre-apply BEFORE merge / stamp AFTER → watch Deploy
(frontend-only = "Deploy Frontend (fast)") → verify the user-facing symptom live → cleanup gated on MERGED with `&&`) → re-score (codex runs the
tooling; orchestrator writes the verdicts; republish artifact with `url`; `CONTINUITY.md` §Now, `~/Projects/FEATURES.md`, memory).

**Rules MJ restated 2026-09-03:** codex does ALL grunt work (recon, critique, builds, fix rounds, screenshots, re-score); Fable subagents ONLY
for the deliberate adversarial check pass; main Fable only arbitrates, moves things along, and talks to MJ. Product questions to MJ: max 2
options + a recommendation; he answers fast. Never pip-compile on macOS. Never print secrets.

**New gotchas from S2 (not in the S2 directive):**
- The static web app cannot proxy anything to the backend; dynamic public URLs live on the API host and the Cloudflare Worker is the only
  proxy path (Cloudflare has no API token on this machine → MJ does dashboard work).
- Verification scripts: the scout list's `id` field is NOT `player_api_id`; pick adults straight from `tracked_players` (birth_date < 2004) when probing.
- Public rate limits key on the ingress address (one bucket for everyone) — do not add per-route limits to cheap anonymous reads.
- The sitemap cold-builds in a background thread after every deploy (503 + Retry-After ~2 min); Cloudflare edge-caches `.txt` (use `?v=` to
  read the origin robots).
- Prod scales to zero: every deploy starts cold; `az containerapp logs show` is flaky mid-rollout.
- Timestamp columns are naive UTC; tests run on SQLite (no `ON CONFLICT`, no `@>`); dialect-neutral code only.
- `gh pr update-branch` when main moved a lot; strict is off so it is optional but keeps `mergeable` clean.
- Two checkers in a row can time-share one codex session's fix rounds fine; never TaskStop a Monitor while a codex run launched in the same
  minute is alive (S0 incident).
- Old artifact URLs can vanish (the S1 scorecard page did) — `Artifact action:list` before assuming a `url` republish will work.

## 3. S3 — "money rails" (next stage; wait for MJ's "go S3" — recon and briefs are fine before that)

**Scorecard target rows → 3:** 3.6 Pay for Scout Pro (now 1), 5.5 Revenue rails (now 2), 4.1 club funding registry / program editing (now 2),
4.4 external platform connection (now 0), 4.6 supporter-facing club page (now 2). Projected after S3 ≈ 66.1% (compute, never type).
4.2 money movement (donations) is **NOT in S3** unless counsel signs off (see P4). Recon evidence: `ledgers/research/s3-recon-2026-09-03.json`
(codex read-only at origin/main `b220ea1`, 2026-09-03; inventory A–G, packages, decisions, risks, acceptance) — every anchor below comes from it.

**What the code has today (verified anchors):**
- Stripe SDK pinned (`academy-watch-backend/requirements.txt:80`); only two users: `src/config/stripe_config.py:11-69` (reads `STRIPE_SECRET_KEY`,
  `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PLATFORM_FEE_PERCENT`; getters + fee calc; nothing calls it) and
  `src/services/stripe_connect.py:1-108` (test-only Express US Connect scaffold: `Account.create`/`AccountLink.create`/`Account.retrieve`,
  rejects live keys; its URL validator has unreachable code at :40-46). **No Checkout Session, Billing Portal, Customer, Subscription,
  PaymentIntent, Refund or `Webhook.construct_event` exists on main**; no billing blueprint is registered (`src/main.py:32-61,118-149`).
- Four DEPRECATED journalist-era tables/models (`StripeConnectedAccount`, `StripeSubscriptionPlan`, `StripeSubscription`, `StripePlatformRevenue`,
  `src/models/league.py:999-1142`; migration `s1t2r3i4p5e6_add_stripe_models.py`, no RLS statements) — prod rows: 0/0/0/0 except nothing; the only
  reachable route is read-only `GET /api/user/all-subscriptions`; account deletion deletes their rows (`src/services/account.py:830-845`).
  `user_subscriptions` (8 rows) and `journalist_subscriptions` are FREE newsletter/follow relations, not billing. Stale docs:
  `STRIPE_IMPLEMENTATION_SUMMARY.md`, `STRIPE_QUICK_START.md`; orphan e2e helper `academy-watch-frontend/e2e/helpers/stripe.js`; `@stripe/stripe-js` unused.
- Scout Pro: `UserAccount.scout_tier` String(20) default `free`, no enum, no writer except deletion reset (`src/models/league.py:493-530`,
  `src/services/account.py:640-654`); readers = watchlist response (`src/routes/scout.py:1630-1658`) + export; `/auth/me` omits it
  (`src/routes/auth_routes.py:408-435`). NOTHING is gated on Pro today: watchlist (cap 200), notes, CSV export (1,000 rows), digest settings,
  custom lists (10 lists / 50 follows) are auth-only (`scout.py:1630-1906,2203-2374`). `PricingPage.jsx:7-52,69-97,178-196`: The Stand free,
  Scout Pro "free during beta, pricing to be announced" (CTA → watchlist/sign-in), Film Room "later". iOS decodes `scoutTier` but no view uses it.
  `is_verified_scout` is trust, never payment (`src/services/trust.py:14-30`).
- Clubs/funding (`src/models/funding.py`): `FundingLeague` :19-111, `ClubProgram` :114-170 (`platform_status`, `donations_enabled`,
  `emergency_hidden`, `is_fundable` **hard-coded false** in `to_public_dict` :191-216), `ClubProgramClaim`/`ClubProgramManager` :219-303,
  `ClubProgramProfileRevision` :305-335 (summary, age range, activities, funding purpose, official URL, safeguarding URL, media — **no manager
  writer**; routes only read the approved revision), `ClubConnectAccount` :412-423 (test-only readiness), `FundingAdminEvent` :426-442 (audit,
  not a ledger). Routes `src/routes/funding.py`: public leagues :382-389, exact-slug program :1079-1122 (approved + not hidden + approved league),
  claim submit/mine :563-605,619-782, "Save this program" :1125-1181 (Follow + demand signal, no money), dual-admin :392-560,785-1064,1184-1228.
  Manager auth pattern: `src/services/club_registry.py:138-190`. Web: `ProgramPage.jsx:34-152` ("Support is not live yet"), `MyClubConsole.jsx:1762-1847`
  (read-only Program tab), `ProgramClaimPage.jsx`, `AdminFunding.jsx`; `api.js:1859-1936` funding wrappers. BuyMeACoffee exists ONLY as the
  platform-wide button (`components/bmcButtonConfig.js:1-29`, footer + newsletter templates) — no per-program link-out, no supporter model.
- Credits: `VideoCreditLedger` (`src/models/video.py:371-405`; reasons purchase/debit/refund/grant; unused unique `stripe_session_id`); admin-only
  routes `src/routes/video.py:305-350,694-781` (`require_api_key`); club processing requests do not debit; refund does not require a prior debit.
- Legal: `LegalPages.jsx:48-66,107-176` (Terms 2025-06-26, New York law; no subscription/renewal/refund/donation language; Privacy still says Stripe
  pays writers; "never pay to be scouted"). Paper prerequisites: `ledgers/ROADMAP_vision-gaps.md:35-60,82-99,131-142,160-161,193-203,216-218`
  (data-licence confirmation, Scout price + grandfathering, donation regulatory scope incl. CA AB 488, donor-tip model, dispute runbook, link-out
  before native money, accessibility before donation GA).
- Reusable: `email_service.send_email` (+ `trust_decision_email_service.py` wrapper pattern; `profile_activity_notification_service.py:197-249`
  watermark-after-success pattern for receipts), signed-token replay tests `tests/test_contact.py:2828-2858,2928-2945` (closest webhook-idempotency
  precedent), `product_events` allowlist `src/routes/events.py:22-34` (analytics only — never entitlement truth), admin stats `src/routes/api.py:10057-10099`.
- Tests today: `test_funding_registry.py`, `test_club_console_bridge.py`, `test_scout_watchlist.py`, `test_account.py:1299-1313` (legacy Stripe row
  deletion). No test covers Checkout, webhooks, entitlements, portal, revisions, imports or bundles.
- **Prod (verified by d9, names only):** `STRIPE_SECRET_KEY` (sk_live…), `STRIPE_PUBLISHABLE_KEY` (pk_live…), `STRIPE_WEBHOOK_SECRET` (whsec…) exist
  as `kvref:` secrets on the container app (KV `stripe-secret-key`, `stripe-publishable-key`, `stripe-webhook-secret`); `deploy.yml` does not manage
  them. The webhook secret predates any current endpoint — treat it as STALE: a new endpoint (`/api/billing/stripe/webhook`) must be created in the
  Stripe dashboard (MJ, or the `stripe` skill/CLI with his key) and its signing secret stored via the `rotate-keys` pattern (never printed).
  `STRIPE_PLATFORM_FEE_PERCENT`, `STRIPE_CONNECT_*` are NOT set in prod.

**Ratified by MJ so far (from the roadmap/scorecard; re-confirm the price):** Scout Pro at the committed price; club bundle subscription;
club-editable programs; Patreon/BuyMeACoffee link-out + supporter import as the cheap first bridge; donation checkout only after regulatory scoping.

**Design decisions d9 recommends (the next orchestrator arbitrates; ask MJ only the product ones, max 2 options + a recommendation):**
1. **Ship dark.** Every S3 backend route sits behind `BILLING_ENABLED` (default off → neutral 404, exactly like `CONTACT_RAIL_ENABLED`). Merge and
   deploy freely; flip in prod only after the Stripe endpoint + prices exist. Local/basecamp acceptance uses a **test-mode** key set in the worktree
   `.env` (`sk_test…`, `whsec…` from `stripe listen`); never put test keys in prod, never test-charge the live keys. Prod acceptance = MJ buys Scout Pro
   with a real card at the committed price and refunds himself in the dashboard (recommend this over faking test mode in prod).
2. **One billing foundation, one webhook.** New tables (guarded migration from the current head, RLS on, no policies): `stripe_webhook_events`
   (unique `event_id`, payload hash, `processed_at`), `billing_customers` (user ↔ Stripe customer), `billing_subscriptions` (`scope_type` user|club_program,
   `scope_id`, `product_code`, Stripe ids, `status`, `current_period_end`, `cancel_at_period_end`), `billing_checkout_sessions` (idempotency: unique
   (scope, product, purchaser, client key)). Entitlement = derived from `billing_subscriptions`; `scout_tier` becomes a projection updated in the same
   transaction. Webhook: raw body + `Stripe-Signature` → insert event row FIRST (unique) → apply → commit; replay = `{"received":true,"duplicate":true}`.
   Server-side product→price map from env (`STRIPE_PRICE_SCOUT_PRO_MONTHLY`, `…_YEARLY`, `STRIPE_PRICE_CLUB_BUNDLE_*`); never accept a price or
   amount from the browser; Billing Portal for cancel/reactivate (this also closes the S0 "paid-subscriber cancel/billing-portal" debt).
3. **Scout Pro = one monthly SKU (+ optional yearly), gate the FEW things that cost us:** recommend CSV export and custom lists beyond 3 (watchlist,
   notes, digest stay free). Grandfather every account created before launch for 90 days (env `SCOUT_PRO_GRANDFATHER_UNTIL`). Entitlement helper
   `require_scout_entitlement(feature)` → 403 `{"error":"scout_pro_required","feature":…,"upgrade_path":"/pricing"}`; `/auth/me` + `GET /api/scout/entitlements`
   expose `tier`, `subscription_status`, `features`. iOS: web-link only, no purchase UI (avoids App Store IAP rules) — confirm with MJ.
4. **Clubs: profile editing + link-out FIRST (no money), bundle SECOND, import THIRD.** P2a: manager `GET/PUT /api/club/<program_id>/profile` creating a
   PENDING `ClubProgramProfileRevision` (approved revision untouched until dual-admin review `POST /api/admin/funding/programs/<id>/profile-revisions/<rid>/review`);
   editable fields = the revision's existing fields + a moderated `external_support {provider: patreon|buy_me_a_coffee, url}` (allowlisted hosts, no
   userinfo/javascript/redirect tricks); moderated `club_program_updates` (title/body/impact) shown on `ProgramPage`. P2b: club bundle Checkout keyed to
   `ClubProgram.id` (purchaser = any active manager; recorded), only after MJ sets the bundle price and what it includes — recommend DEFERRING the bundle
   until one real club exists (prod has 0 programs). Supporter import: only after MJ approves fields/consent/retention (Privacy must change) — recommend
   deferring to S6 when a real club asks.
5. **Donations (P4) stay out.** Keep `is_fundable` hard-coded false; no donation CTA; no Connect promotion. Counsel first (`ROADMAP_vision-gaps.md:131-142`).
6. **Hygiene inside S3:** fix the unreachable validation in `stripe_connect.py:40-46`; delete or clearly label the stale Stripe docs; update Privacy's
   writer-payment sentence and add subscription/renewal/cancellation/refund terms (MJ approves wording); add `checkout_started/completed`, `subscription_canceled`
   to the product-events allowlist for funnel analytics ONLY (never entitlement truth); admin revenue tile from `billing_subscriptions`, not events.

**Package split (disjoint files; contracts first; frontend builds against mocks):**
| Pkg | Scope | Depends |
|---|---|---|
| S3-P0 | billing foundation: config/price map, `services/stripe_billing.py` (Checkout, Portal, webhook apply), `models/billing.py`, migration `s3b1` (from the current head), `routes/billing.py` (`POST /api/billing/stripe/webhook`, `GET /api/billing/me`, `POST /api/billing/portal`, `GET /api/admin/billing/summary`), receipts via email_service, account export/delete extension, `BILLING_ENABLED` gate, tests with signed test events (replay, out-of-order, bad signature) | — |
| S3-P1 | Scout Pro: `services/scout_entitlements.py`, `POST /api/scout-pro/checkout`, `GET /api/scout/entitlements`, `/auth/me` fields, `require_scout_entitlement` on the MJ-selected features, grandfather env, tests | P0 |
| S3-P2a | club profile editing + external link-out + updates (+ review route; migration `s3c1` for `club_program_updates` + revision columns) | — (P0 only for the bundle) |
| S3-P2b | club bundle Checkout keyed to `ClubProgram.id` (+ `POST /api/club/<id>/billing/checkout`) — only if MJ prices it now | P0, P2a |
| S3-P3 | web: PricingPage real CTA + return/cancel states, `AccountBillingPage` (status + Portal), MyClubConsole Program editor + updates + link, ProgramPage updates/link/`is_fundable` guard, AdminDashboard revenue tile, `e2e/` mocked spec | contracts of P0/P1/P2a |
| S3-P4 | GATED donations — do not start | counsel |
Order: P0 → (P1 ∥ P2a) → P3 (→ P2b if priced). Merge one at a time; migrations chain from the head at dispatch (P0 then P2a).

**Acceptance (live, dark → lit):** dark deploy: every billing route → neutral 404 with `BILLING_ENABLED` unset. Then, with the new Stripe endpoint +
prices configured: `curl -X POST …/api/billing/stripe/webhook` with a bad signature → 400 and zero rows; a Stripe CLI test event replayed twice → one
`stripe_webhook_events` row; MJ buys Scout Pro at the committed price → `/api/scout/entitlements` shows `pro`, CSV export succeeds, a free
non-grandfathered account gets the 403 shape; Billing Portal opens from Account; a manager's profile edit appears on `/programs/<slug>` only after
admin approval; Patreon link renders with `rel="noopener noreferrer"`; `is_fundable` still false everywhere. Re-score rows 3.6/5.5/4.1/4.4/4.6.

**Questions the next orchestrator must put to MJ before dispatching P1/P2b (2 options + recommendation each):** the committed Scout Pro price and
interval(s); which features Pro gates (rec: CSV + lists >3); grandfather window (rec: 90 days for pre-launch accounts); iOS web-link-only (rec: yes);
whether API-Football's licence allows paid features (he confirms; blocker if not); club bundle now or after the first real club (rec: after); Terms/Privacy
wording for subscriptions (rec: draft, he approves). Everything else is engineering judgement.

## 4. Debts / queue (do not lose)
- **S2 hygiene (ledger `CONTINUITY_dream-s2.md` "Debts / hygiene queue"):** batched public-adult gate + sitemap index (sitemap lists only the
  first 500 players; `SITEMAP_MAX_PLAYER_CANDIDATES`); P0 gate query-count timing differs by subject class (constant-work denial path);
  Postgres-compile assertion for the CASE-guarded JSON cast; neutral-404 regression set (local-namespace suppressed, bridged-suppressed, 2^31
  ids); `profile_view` re-emit on a 42→43→42 revisit; AdminDashboard skeleton count; `budget_exhausted` cosmetic; one-way vs bidirectional
  block exclusion (align owner card + weekly email via `block_related_user_ids`); capped-run starvation ordering for the weekly job;
  sitemap hung-build watchdog; iOS has no fan surface; local player pages have no comments; newsletter pages are still crawler-blind.
- **S1:** partial unique index on club result rows + persisted `player_match_entries.video_match_id` (migration; dedupe first); iOS add-a-game /
  birth_date on local create; `lock_player_refresh` public name; club dialog re-open pre-fill; pre-existing failing tests (4).
- **S0:** iOS local-create birth_date; upload attestation (5.1); paid-subscriber cancel/billing-portal route (S3 covers this); default
  `playwright.config.js` webServer targets 5173 (use `E2E_BASE_URL` + own Vite).
- **Roadmap after S3:** S4 Film Room self-serve + club tools, S5 part-ownership (counsel first), S6 ten real participants (the multiplier;
  arguably start it in parallel with S3 — nothing in S3 needs it, and Lived adoption is the number that is still ~0).

## 5. Questions worth asking `loanarmy-d9` (while it is open)
Only what this file and the ledgers do not answer: why a checker finding was accepted/deferred, where a scratchpad-only artefact lived,
the exact `az` incantations used for job creation / env flips (all in `ledgers/tooling/dream-scorecard/s2/` and the S2 ledger log), or a
judgement call behind an S3 decision below. Everything else is in the ledgers and the evidence bundle
(`ledgers/research/dream-scorecard-2026-09-02.json` → `post_s2`).
