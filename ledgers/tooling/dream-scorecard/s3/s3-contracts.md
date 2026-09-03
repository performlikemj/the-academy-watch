# S3 "money rails" — HTTP + module contracts (P0 provides; P1/P2a consume; P3 builds against these with mocks)

Every billing route below is DARK by default: when `BILLING_ENABLED` is unset/false the route answers with Flask's
`abort(404)` exactly like the contact rail (`require_contact_rail` in `src/services/contact.py:87-97` plus the
`before_app_request` prefix hide in `src/routes/contact.py:81-88`). P0 provides `billing_enabled()` and a
`require_billing_rail` decorator (same shape as `require_contact_rail`) in `src/services/stripe_billing.py`, and a
`before_app_request` on `billing_bp` that `abort(404)`s every path starting with `/api/billing/` OR `/api/admin/billing/`
(incl. automatic OPTIONS and wrong-method probes) while off. Error bodies are `{"error": "<snake_code>"}` unless stated.
Timestamps are ISO-8601 strings of naive UTC (`.isoformat()`), null when absent. Model timestamp convention: every bare
`created_at`, `updated_at`, `received_at` below is `DateTime NOT NULL` with a naive-UTC Python default and `server_default=db.func.now()`;
`updated_at` also has a naive-UTC `onupdate`. `processed_at`, `completed_at`, `expires_at`, `current_period_*`, `canceled_at`,
`reviewed_at`, `published_at` are nullable `DateTime` (pattern: `src/models/player_fan.py:8-26`). Money is integer minor units
(`unit_amount`, cents) + lowercase ISO currency (`"usd"`). NEVER accept a price id, amount, or currency from the browser.

## Environment (read at call time, never at import time)
- `BILLING_ENABLED` — "1"/"true"/"yes"/"on" (case-insensitive) → on. Everything else → off.
- `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` (existing names). `STRIPE_PUBLISHABLE_KEY` is not needed (hosted Checkout).
- Price map: `STRIPE_PRICE_SCOUT_PRO_MONTHLY`, `STRIPE_PRICE_SCOUT_PRO_YEARLY`, `STRIPE_PRICE_CLUB_BUNDLE_MONTHLY`,
  `STRIPE_PRICE_CLUB_BUNDLE_YEARLY` (Stripe `price_…` ids). A product is OFFERED iff ≥1 of its prices is set.
- `PUBLIC_BASE_URL` (website origin, e.g. `https://theacademywatch.com`) for success/cancel/return URLs.
- P1 only: `SCOUT_PRO_LAUNCHED_AT` (ISO datetime, UTC) and `SCOUT_PRO_GRANDFATHER_UNTIL` (ISO datetime, UTC) — both set →
  accounts created before `LAUNCHED_AT` are Pro until `GRANDFATHER_UNTIL`. Either missing, malformed, or timezone-less → no
  grandfathering; parsing must NEVER raise into `/auth/me` or an entitlement route.

## Module contract — `src/config/stripe_config.py` (P0 extends; keep existing names working)
- `billing_enabled() -> bool`
- `PRODUCT_CATALOG: dict` = `{"scout_pro": {"scope_type": "user", "name": "Scout Pro", "prices": {"monthly": "STRIPE_PRICE_SCOUT_PRO_MONTHLY", "yearly": "STRIPE_PRICE_SCOUT_PRO_YEARLY"}}, "club_bundle": {"scope_type": "club_program", "name": "Club bundle", "prices": {"monthly": "STRIPE_PRICE_CLUB_BUNDLE_MONTHLY", "yearly": "STRIPE_PRICE_CLUB_BUNDLE_YEARLY"}}}`
  (values are ENV VARIABLE NAMES; resolve at call time).
- `offered_products() -> dict[str, dict]` → `{product_code: {"scope_type", "name", "prices": {price_code: stripe_price_id}}}` (only configured prices; products with none omitted).
- `resolve_price(product_code, price_code) -> str | None`; `product_for_price_id(stripe_price_id) -> tuple[product_code, price_code] | None`.
- `configure_stripe() -> None` sets `stripe.api_key` from env (called by the service before any Stripe call). The
  module MUST NOT print at import and MUST NOT require the key at import (tests import it with no env).

## Module contract — `src/models/billing.py` (P0)
- `StripeWebhookEvent` → table `stripe_webhook_events`: `id`, `event_id String(255) UNIQUE NOT NULL`, `event_type String(120) NOT NULL`,
  `payload_hash String(64) NOT NULL` (sha256 hex of the raw body), `status String(20) NOT NULL` CHECK IN ('processed','ignored','failed'),
  `error Text`, `received_at DateTime NOT NULL`, `processed_at DateTime`.
- `BillingCustomer` → `billing_customers`: `id`, `user_account_id FK user_accounts.id ON DELETE CASCADE UNIQUE NOT NULL`,
  `stripe_customer_id String(255) UNIQUE NOT NULL`, `created_at`, `updated_at`.
- `BillingSubscription` → `billing_subscriptions`: `id`, `scope_type String(20) NOT NULL` CHECK IN ('user','club_program'), `scope_id Integer NOT NULL`,
  `product_code String(40) NOT NULL`, `price_code String(20) NOT NULL`, `purchaser_user_id FK user_accounts.id ON DELETE SET NULL`,
  `stripe_customer_id String(255) NOT NULL`, `stripe_subscription_id String(255) UNIQUE NOT NULL`, `stripe_price_id String(255) NOT NULL`,
  `status String(30) NOT NULL` (Stripe's string verbatim), `unit_amount Integer`, `currency String(3)`, `interval String(10)`,
  `current_period_start DateTime`, `current_period_end DateTime`, `cancel_at_period_end Boolean NOT NULL default false`,
  `canceled_at DateTime`, `last_event_created Integer` (Stripe `event.created` epoch of the last APPLIED event), `created_at`, `updated_at`.
  Index `ix_billing_subscriptions_scope (scope_type, scope_id, product_code)`; index on `purchaser_user_id`.
- `BillingCheckoutSession` → `billing_checkout_sessions`: `id`, `scope_type`, `scope_id`, `product_code`, `price_code`,
  `purchaser_user_id FK user_accounts.id ON DELETE CASCADE NOT NULL`, `client_key String(64) NOT NULL`, `stripe_session_id String(255) UNIQUE`,
  `checkout_url Text`, `status String(20) NOT NULL default 'open'` CHECK IN ('open','complete','expired'), `expires_at DateTime`,
  `created_at`, `completed_at`. `UniqueConstraint(scope_type, scope_id, product_code, purchaser_user_id, client_key)` named `uq_billing_checkout_idem`.
- Migration `s3b1` (down `cb01`): the four tables, each followed by `ALTER TABLE … ENABLE ROW LEVEL SECURITY` (no policies), every DDL
  guarded by inspector checks (prod schema drifts). Downgrade drops the four tables (guarded).

## Module contract — `src/services/stripe_billing.py` (P0; exact names — P1 and account.py import these)
- `class BillingError(Exception)`: attributes `code: str`, `status: int` (route returns `({"error": code}, status)`).
- `ACTIVE_STATUSES = frozenset({"active", "trialing", "past_due"})`
- `ensure_customer(user) -> BillingCustomer` — creates the Stripe Customer once (email, name=display_name, metadata `{"user_id"}`,
  idempotency key `customer:<user.id>`), stores the row; returns the existing row otherwise.
- `active_subscription(scope_type, scope_id, product_code) -> BillingSubscription | None` — status ∈ ACTIVE_STATUSES, latest `current_period_end` first.
- `subscriptions_for_user(user) -> list[BillingSubscription]` — purchaser == user OR (scope_type == "user" AND scope_id == user.id); newest first.
- `create_checkout(user, *, product_code, price_code, client_key, scope_id=None) -> dict` → `{"checkout_url": str, "session_id": str}`.
  Errors (BillingError): `unknown_product` 400 (not offered / bad price_code), `invalid_client_key` 400 (must match `^[A-Za-z0-9_-]{8,64}$`),
  `product_not_available` 403 (scope_type == "club_program" — S3 sells nothing to clubs yet), `already_subscribed` 409 (active_subscription exists).
  Idempotency: an existing `BillingCheckoutSession` row for (scope, product, purchaser, client_key) with status `open` and `expires_at > now`
  is returned WITHOUT calling Stripe. Otherwise create `stripe.checkout.Session` (mode `subscription`, `customer`, one line item qty 1,
  `success_url = <PUBLIC_BASE_URL>/account/billing?checkout=success&session_id={CHECKOUT_SESSION_ID}`, `cancel_url = <PUBLIC_BASE_URL>/pricing?checkout=canceled`,
  `client_reference_id = <row id>`, `allow_promotion_codes = True`, `metadata` AND `subscription_data.metadata` both =
  `{"scope_type", "scope_id", "product_code", "price_code", "purchaser_user_id", "app": "academy_watch"}` (strings),
  Stripe idempotency key `checkout:<scope_type>:<scope_id>:<product_code>:<user.id>:<client_key>`), then store/refresh the row
  (`stripe_session_id`, `checkout_url`, `expires_at` from `session.expires_at`, status `open`) and write a server-only
  `product_events` row `billing_checkout_started` (user_email = purchaser, props `{"product_code","price_code","scope_type"}`) in the same transaction.
  `create_checkout` FLUSHES but never commits; `POST /api/billing/checkout` commits exactly once after the service returns and
  rolls back before mapping a `BillingError` or any unexpected exception to a response.
- `create_portal_session(user) -> str` (URL) — `stripe.billing_portal.Session.create(customer=…, return_url=<PUBLIC_BASE_URL>/account/billing)`;
  BillingError `no_billing_account` 409 when the user has no `BillingCustomer`.
- `handle_webhook(raw_body: bytes, signature_header: str | None) -> tuple[dict, int]`:
  1. `stripe.Webhook.construct_event(raw_body, signature_header, STRIPE_WEBHOOK_SECRET)`; any `ValueError` / `stripe.SignatureVerificationError`
     → `({"error": "invalid_signature"}, 400)` and ZERO rows written. Missing secret → same 400.
  2. Dedupe: existing `StripeWebhookEvent` with that `event_id` and status ∈ {processed, ignored} → `({"received": true, "duplicate": true}, 200)`
     with no further writes. A `failed` row is RETRIED (updated in place). Insert the event row FIRST (savepoint + IntegrityError → duplicate).
  3. Apply by `event.type`: `checkout.session.completed` (mark the checkout row `complete` by `stripe_session_id`, else by
     `client_reference_id`; if `session.subscription` is set, `stripe.Subscription.retrieve(id, expand=["items.data.price"])` and upsert),
     `checkout.session.expired` (mark the matching checkout row `expired` by `stripe_session_id`, else `client_reference_id`),
     `customer.subscription.created|updated|deleted` (upsert the event's object), `invoice.paid` / `invoice.payment_failed`
     (if the invoice references a subscription: retrieve + upsert; `invoice.payment_failed` also triggers the `payment_failed` email).
     Any other type → row status `ignored`. Successful apply → status `processed`, `processed_at` set, ONE commit.
  4. Any exception during apply → rollback, then in a NEW transaction upsert the event row with status `failed` + `error` (≤2000 chars),
     commit, return `({"error": "processing_failed"}, 500)` so Stripe retries.
  Return `({"received": true, "duplicate": false}, 200)` on success.
- `upsert_subscription(sub, *, event_created: int | None) -> BillingSubscription | None`:
  out-of-order guard — if a row exists and `event_created` is not None and `event_created < row.last_event_created` → return the row UNCHANGED.
  Scope resolution, in order: `sub.metadata` (scope_type, scope_id, product_code, price_code, purchaser_user_id) → else `product_for_price_id`
  of the first item's price + `BillingCustomer` by `sub.customer` (scope user) → else raise BillingError `unresolvable_subscription` 500.
  Fields from the object: `status`, first item `price.id/unit_amount/currency/recurring.interval`, `current_period_start/end` from the FIRST
  ITEM when present (Stripe API 2025+ moved them onto items) else from the subscription, `cancel_at_period_end`, `canceled_at`, `last_event_created`.
  Then `project_entitlements(row)`; then queue status emails (see below). On the FIRST transition into ACTIVE_STATUSES write a
  server-only `product_events` row `billing_subscription_activated`; on a transition out of ACTIVE_STATUSES (or `deleted`) write
  `billing_subscription_ended` (user_email = purchaser's email, props `{"product_code","price_code","scope_type"}`, once per applied
  transition, in the webhook transaction). All in the caller's transaction.
- `project_entitlements(row) -> None` — for `scope_type == "user"` and `product_code == "scout_pro"`: set `UserAccount.scout_tier` to `"pro"`
  when `active_subscription("user", scope_id, "scout_pro")` exists else `"free"`, in the SAME transaction. (P1 derives features from the
  subscription rows; `scout_tier` is only a projection for old readers.)
- Emails (`email_service`): `subscription_activated` (first transition INTO an active status), `subscription_ended` (transition OUT of
  ACTIVE_STATUSES or `customer.subscription.deleted`), `payment_failed`. Send AFTER the commit (collect intents during apply, send after);
  a send failure is logged and never fails the webhook. Plain, factual copy; no amounts other than what Stripe already told the user.
- `admin_summary() -> dict` → see `GET /api/admin/billing/summary`.
- `cancel_subscriptions_for_account_deletion(user) -> int` — for every ACTIVE user-scope row of this user: `stripe.Subscription.cancel(id)`
  (runs whenever a secret key is configured, even if `BILLING_ENABLED` is off — a switched-off flag must never leave a customer paying);
  a Stripe error → BillingError `billing_cancel_failed` 503 and the account deletion ABORTS (no rows deleted). Returns the count canceled.

## P0 routes (`billing_bp`, registered under `/api`)
### POST /api/billing/stripe/webhook — no auth, no rate limit, raw body
Dark → neutral 404. Else exactly `handle_webhook(request.get_data(), request.headers.get("Stripe-Signature"))`.
### GET /api/billing/config — public
200 `{"enabled": true, "products": [{"code": "scout_pro", "name": "Scout Pro", "scope_type": "user", "prices": [{"price_code": "monthly", "interval": "month", "unit_amount": 900, "currency": "usd"}]}]}`
`interval` derives from `price_code` (monthly→month, yearly→year). `unit_amount`/`currency` come from `stripe.Price.retrieve` cached in-process
for 10 minutes per price id; when the lookup fails the two keys are OMITTED (never null, never 0). `Cache-Control: no-store`.
### GET /api/billing/me — `@require_user_auth`
200 `{"enabled": true, "has_billing_account": bool, "subscriptions": [{"id", "scope_type", "scope_id", "product_code", "price_code", "status", "is_active", "current_period_end", "cancel_at_period_end", "unit_amount", "currency", "interval"}]}`
### POST /api/billing/checkout — `@require_user_auth`, 10/minute per user
Body `{"product_code": "scout_pro", "price_code": "monthly", "client_key": "<8-64 url-safe chars>"}` → 200 `{"checkout_url", "session_id"}`.
Errors: the BillingError shapes above; 400 `{"error": "invalid_json"}` for a non-object body.
### POST /api/billing/portal — `@require_user_auth`, 10/minute
200 `{"portal_url": str}`; 409 `{"error": "no_billing_account"}`.
### GET /api/admin/billing/summary — `@require_api_key`
200 `{"active_subscriptions": n, "by_product": {"scout_pro": n}, "mrr_cents": n, "currency": "usd", "past_due": n, "canceled_last_30d": n, "webhook_events_last_24h": n, "webhook_failed_last_24h": n, "checkout_sessions_open": n}`
`mrr_cents` = Σ over ACTIVE rows of `unit_amount` (interval month) or `round(unit_amount / 12)` (interval year); rows with null amount contribute 0.
`checkout_sessions_open` counts only rows with status `open` AND `expires_at` in the future.
### Account export/delete (existing routes; P0 extends `src/services/account.py`)
Export adds `"billing": {"has_billing_account": bool, "subscriptions": [same objects as /me]}`. Delete calls
`cancel_subscriptions_for_account_deletion` FIRST (abort on `billing_cancel_failed` → the existing delete route returns 503 `{"error": "billing_cancel_failed"}`),
then counts `billing_customers`, `billing_subscriptions`, `billing_checkout_sessions` under `counts["deleted"]` (rows removed by cascade or explicitly).
### POST /api/events (existing) — allowlist += `checkout_started`, `checkout_completed` ONLY (client funnel; never entitlement truth).
Server-only names (NOT in the allowlist): `billing_checkout_started`, `billing_subscription_activated`, `billing_subscription_ended`.

## P1 module contract — `src/services/scout_entitlements.py`
- `FREE_LIST_LIMIT = 3`
- `scout_entitlements(user, *, now=None) -> dict`:
  `{"billing_enabled": bool, "tier": "pro"|"free", "source": "subscription"|"grandfather"|"billing_disabled"|"none", "subscription_status": str|null, "current_period_end": iso|null, "cancel_at_period_end": bool, "grandfathered_until": iso|null, "features": {"csv_export": bool, "custom_lists_max": int}}`
  - billing OFF → `tier = user.scout_tier or "free"`, `source = "billing_disabled"`, features `csv_export: true`, `custom_lists_max: MAX_FOLLOW_LISTS` (nothing is gated).
  - billing ON: active `scout_pro` subscription → `pro`/`subscription`; else grandfathered (both envs set, `user.created_at < LAUNCHED_AT`, `now < UNTIL`) → `pro`/`grandfather`;
    else `free`/`none` with `csv_export: false`, `custom_lists_max: FREE_LIST_LIMIT`. Pro → `csv_export: true`, `custom_lists_max: MAX_FOLLOW_LISTS`.
- `is_pro(user) -> bool`; `list_limit_for(user) -> int`
- `require_scout_entitlement(feature: str)` — decorator placed INSIDE `@require_user_auth`; when `features[feature]` is false →
  403 `{"error": "scout_pro_required", "feature": "<feature>", "upgrade_path": "/pricing"}`. No-op when billing is off.
## P1 routes
- `GET /api/scout/entitlements` — `@require_user_auth`; dark → neutral 404; 200 `{"entitlements": scout_entitlements(user)}`.
- `GET /api/scout/export.csv` — gated with `require_scout_entitlement("csv_export")`.
- `POST /api/scout/lists` — when `count >= list_limit_for(user)` and `list_limit_for(user) < MAX_FOLLOW_LISTS` → the 403 shape with `feature: "custom_lists"`; the existing 409 stays at `MAX_FOLLOW_LISTS`.
- `GET /api/auth/me` — ALWAYS adds `"scout_tier": str` and `"scout_pro": {"enabled": bool, "tier": str, "features": {...}}` (from `scout_entitlements`).
- `GET /api/scout/watchlist` keeps emitting `scout_tier` (projection) — unchanged.

## P2a contracts
### Revision object (`rev`)
`{"id", "status", "summary", "age_groups": [], "activities": [], "funding_purpose", "official_url", "safeguarding_url", "media_urls": [], "external_support": {"provider": "patreon"|"buy_me_a_coffee", "url": str}|null, "review_reason", "reviewed_at", "created_at"}`
### Update object (`upd`)
`{"id", "title", "body", "impact", "status", "review_reason", "created_at", "published_at"}`
### Manager routes (`club_bp`, `@require_club_manager()`; neutral 403 `{"error": "Club manager access denied"}` for non-managers)
- `GET /api/club/<int:program_id>/profile` → 200 `{"program": {"id", "slug", "name"}, "approved": rev|null, "pending": rev|null, "limits": {"summary_max": 2000, "funding_purpose_max": 1000, "list_items_max": 12, "list_item_max": 40, "media_urls_max": 6, "updates_pending_max": 5}}`
- `PUT /api/club/<int:program_id>/profile` — 20/hour per user. Body `{"summary", "age_groups": [], "activities": [], "funding_purpose", "official_url", "safeguarding_url", "media_urls": [], "external_support": {"provider", "url"}|null}`.
  Creates the program's pending revision or REPLACES the existing pending one in place (one pending per program; `submitted_by_user_id` = caller).
  200 `{"pending": rev}`. 400 `{"error": "validation_failed", "fields": {"<field>": "<message>"}}`.
  Validation: strings trimmed; `summary` ≤2000, `funding_purpose` ≤1000; lists ≤12 items of ≤40-char strings (deduped); `official_url`/`safeguarding_url`/`media_urls[*]`
  https-only ≤500 chars; `media_urls` ≤6. `external_support`: null OR both fields; provider ∈ {patreon, buy_me_a_coffee}; url ≤200 chars, scheme https,
  NO userinfo, NO port, NO query, NO fragment, host EXACTLY in {patreon.com, www.patreon.com} for patreon / {buymeacoffee.com, www.buymeacoffee.com}
  for buy_me_a_coffee, path non-empty (`/creatorname`). Store the URL normalised (lower-case host, no trailing slash).
- `GET /api/club/<int:program_id>/updates` → 200 `{"updates": [upd]}` (all statuses, newest first).
- `POST /api/club/<int:program_id>/updates` — 10/hour. Body `{"title", "body", "impact"}`; title 3–140, body 20–4000, impact ≤500 (optional). 201 `{"update": upd}` (status pending).
  409 `{"error": "pending_limit_reached"}` when 5 pending already exist. 400 validation shape as above.
- `DELETE /api/club/<int:program_id>/updates/<int:update_id>` → pending/rejected rows are deleted: 200 `{"deleted": true, "status": null}`; an approved row becomes
  `withdrawn` (leaves the public page): 200 `{"deleted": false, "status": "withdrawn"}`; wrong program / unknown → 404 `{"error": "update not found"}`.
### Admin routes (`funding_bp`, `@require_api_key`)
- `GET /api/admin/funding/profile-revisions?status=pending` → 200 `{"revisions": [rev + {"submitted_by_user_id", "program": {"id", "slug", "name"}}]}` (default status pending; `all` for everything; newest first, ≤200).
- `POST /api/admin/funding/programs/<int:program_id>/profile-revisions/<int:revision_id>/review` — body `{"decision": "approve"|"reject", "reason": str}` (reason required, ≤2000).
  approve → revision `approved`, `program.approved_profile_revision_id = revision.id`, `reviewed_by = g.user_email`, `review_reason`, `reviewed_at`; reject → `rejected` + same review fields.
  Both write `_audit("profile_revision_approved"|"profile_revision_rejected", "club_program_profile_revision", revision.id, reason, {"program_id"})`.
  200 `{"revision": rev}`; 404 unknown; 409 `{"error": "revision not pending"}`.
- `GET /api/admin/funding/program-updates?status=pending` → 200 `{"updates": [upd + {"program": {"id", "slug", "name"}}]}`.
- `POST /api/admin/funding/programs/<int:program_id>/updates/<int:update_id>/review` — body as above; approve sets `published_at = now`; audit
  `program_update_approved|program_update_rejected` target `club_program_update`. 200 `{"update": upd}`; 404; 409 `{"error": "update not pending"}`.
### Public (`GET /api/programs/<slug>`, existing) — payload gains
`"external_support": {"provider", "label": "Patreon"|"Buy Me a Coffee", "url"}|null` (from the APPROVED revision only) and
`"updates": [{"id", "title", "body", "impact", "published_at"}]` (status approved, newest `published_at` first, ≤10). `is_fundable` stays `false`.
### Models / migration `s3c1` (down `cb01` at dispatch; the orchestrator re-chains to `s3b1` before merge)
- `ClubProgramProfileRevision` += `external_support_provider String(30)`, `external_support_url String(500)`.
- `ClubProgramUpdate` → `club_program_updates`: `id`, `program_id FK club_programs.id ON DELETE CASCADE NOT NULL`, `author_user_id FK user_accounts.id ON DELETE SET NULL`,
  `title String(140) NOT NULL`, `body Text NOT NULL`, `impact Text`, `status String(20) NOT NULL default 'pending'` CHECK IN ('pending','approved','rejected','withdrawn'),
  `reviewed_by String(200)`, `review_reason Text`, `reviewed_at`, `published_at`, `created_at`, `updated_at`. Index `(program_id, status, published_at)`. RLS enabled, no policies.
