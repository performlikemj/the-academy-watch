# S3-P0 — Billing foundation (backend only)

Worktree: __WT__ (branch `feat/s3-p0-billing`, base `origin/main`). Common brief: __COMMON__. Contracts: __CONTRACTS__ (authoritative for every name and shape).

## Requirements (numbered; each must be done or reported as not done)
1. `src/config/stripe_config.py`: add `billing_enabled()`, `PRODUCT_CATALOG`, `offered_products()`, `resolve_price()`,
   `product_for_price_id()`, `configure_stripe()` per the contracts. Remove the import-time `print` and the import-time
   `stripe.api_key` assignment (keys are read at call time). Keep `get_stripe_keys`, `calculate_platform_fee`,
   `validate_stripe_config` importable (nothing calls them; do not delete).
2. `src/models/billing.py` (new): the four models exactly as specified. Register them the same way the S2 model
   `src/models/player_fan.py` is registered (find how `PlayerFan` becomes visible to `create_all` and Alembic — follow that).
3. Migration `migrations/versions/s3b1_billing_foundation.py`: revision `s3b1`, down_revision `cb01`. Guard every DDL
   with inspector checks (see `s2f1_fans_reach.py` for the pattern), enable RLS on each new table (no policies), guarded
   downgrade. `flask db heads` must print exactly `s3b1`.
4. `src/services/stripe_billing.py` (new): the full module contract — `BillingError`, `ACTIVE_STATUSES`, `ensure_customer`,
   `active_subscription`, `subscriptions_for_user`, `create_checkout`, `create_portal_session`, `handle_webhook`,
   `upsert_subscription`, `project_entitlements`, status emails, `admin_summary`, `cancel_subscriptions_for_account_deletion`.
   Every Stripe call goes through module-level `stripe.*` functions so tests can `monkeypatch` them. The webhook path must:
   verify BEFORE any DB write; insert the event row under a savepoint (`db.session.begin_nested()`), catch `IntegrityError`
   → duplicate; apply; ONE commit; on apply failure rollback and record `failed` in a fresh transaction; return 500.
   Out-of-order guard via `last_event_created`. Scope resolution order per the contract. Emails are collected as intents
   during apply and sent after commit via `email_service` (reuse the wrapper pattern of
   `src/services/trust_decision_email_service.py`; plain factual copy, no marketing).
5. `src/routes/billing.py` (new, `billing_bp`, register in `src/main.py` under `/api` next to `contact_bp`): all six routes
   from the contracts with the exact auth decorators, rate limits (reuse the scout/contact `limiter` + per-user key pattern),
   the dark gate (`require_billing_rail` decorator + a `before_app_request` hiding every `/api/billing/` AND `/api/admin/billing/` path while off —
   the exact pattern of `require_contact_rail` (`src/services/contact.py:87-97`) and `src/routes/contact.py:81-88`), and `Cache-Control: no-store` on `/api/billing/config`. The webhook route must read
   `request.get_data()` (raw bytes) and must be excluded from any JSON-body parsing or rate limiting that would touch the body.
6. `src/services/account.py`: export gains `billing`; delete calls `cancel_subscriptions_for_account_deletion` FIRST and
   aborts on `BillingError`; the delete route in `src/routes/account.py` maps that error to 503 `{"error": "billing_cancel_failed"}`.
   Count the three billing tables under `counts["deleted"]`. Keep the legacy Stripe-row deletion as is. The POST checkout route
   commits once after the service flushes (see contracts). P2a (built concurrently, must NOT edit account.py) adds
   `club_program_updates.author_user_id` (FK user_accounts, SET NULL) and a `reviewed_by` identity string: predeclare compatibility
   with schema guards — before the fail-closed surviving-FK scan (`account.py:572-603`), set `club_program_updates.author_user_id = NULL`
   for the deleting user when that table/column exists, and add `(club_program_updates, reviewed_by)` to the identity-string
   redaction list (`account.py:450-468`) guarded the same way.
7. `src/routes/events.py`: `ALLOWED_EVENTS` += `checkout_started`, `checkout_completed` (nothing else).
8. Hygiene: `src/services/stripe_connect.py` — the recon claimed unreachable validation around lines 40–46; verify. If real,
   fix minimally; if not, leave it and say so. Delete the two stale docs `STRIPE_IMPLEMENTATION_SUMMARY.md` and
   `STRIPE_QUICK_START.md` (find them; they describe a rail that no longer exists).
9. Tests `tests/test_billing.py` (new). `tests/conftest.py` registers only a few blueprints — define module-local `billing_app`/`client`
   fixtures following `tests/test_account.py:50-68` (init db + the shared limiter, register `billing_bp` and `account_bp` under `/api`,
   import the billing models before `create_all`); reuse only the Bearer/`X-API-Key` header style from `tests/test_scout_watchlist.py:227-234`. Sign test events with the SDK's own helper
   (`stripe.WebhookSignature._compute_signature` or equivalent) using a fake secret set via `monkeypatch.setenv`. Required cases:
   a) every billing route (incl. OPTIONS and a wrong method) → 404 with `BILLING_ENABLED` unset, and the same 404 with the flag on but no routes matched is NOT required — just assert 404 while dark;
   b) bad signature → 400 and zero `stripe_webhook_events` rows; missing secret → 400;
   c) `customer.subscription.created` (active, metadata scope user/scout_pro) → one subscription row, `scout_tier == "pro"`,
      one event row `processed`; replay of the SAME event → 200 `duplicate: true`, still one row each, no email sent twice;
   d) out-of-order: an OLDER `customer.subscription.updated` (status `canceled`, smaller `event.created`) after a newer active one → row stays active;
   e) `customer.subscription.deleted` → status canceled, `scout_tier == "free"`, `subscription_ended` email intent sent after commit;
   f) an apply exception (monkeypatch `upsert_subscription` to raise) → 500, event row `failed`; the same event again → reprocessed and `processed`;
   f2) `checkout.session.expired` flips the checkout row to `expired`, and a new checkout with the same `client_key` then calls Stripe again;
   g) `create_checkout` with `stripe.checkout.Session.create` mocked → row + returned url; second call with the same `client_key` returns
      the same url WITHOUT calling Stripe (assert call count); a different `client_key` creates a new session; `already_subscribed` 409;
      `product_not_available` 403 for `club_bundle`; `unknown_product` 400 when no price env is set; `invalid_client_key` 400;
   h) `/api/billing/config` with `stripe.Price.retrieve` mocked → amounts; with it raising → keys omitted; `no-store` header;
   i) `/api/billing/me` shape; `/api/billing/portal` 409 then 200 with the mocked portal call;
   j) `/api/admin/billing/summary` MRR math (one monthly 900 + one yearly 9600 → 900 + 800 = 1700), admin auth required;
   k) account delete with an active sub: `stripe.Subscription.cancel` called; when it raises → 503 and the account still exists;
   l) `ALLOWED_EVENTS` contains the two new names and NOT `billing_checkout_started`.
   Also run `tests/test_account.py` (expect only the 1 documented pre-existing failure) and `tests/test_contact.py` (must stay green).

## ALLOWED
`academy-watch-backend/src/config/stripe_config.py`, `academy-watch-backend/src/services/stripe_billing.py` (new),
`academy-watch-backend/src/models/billing.py` (new), the model registration file that `player_fan.py` uses (report which),
`academy-watch-backend/migrations/versions/s3b1_billing_foundation.py` (new), `academy-watch-backend/src/routes/billing.py` (new),
`academy-watch-backend/src/main.py` (blueprint registration lines only), `academy-watch-backend/src/services/account.py`,
`academy-watch-backend/src/routes/account.py` (503 mapping only), `academy-watch-backend/src/routes/events.py`,
`academy-watch-backend/src/services/stripe_connect.py` (hygiene only), the two stale docs (delete),
`academy-watch-backend/tests/test_billing.py` (new). Nothing else. No frontend. No other migration.

## Commit (exactly one)
`feat(billing): S3-P0 Stripe billing foundation — checkout, portal, idempotent webhook, dark behind BILLING_ENABLED`

## Risks to call out in your report
Webhook body parsing, savepoint semantics on SQLite vs Postgres, email-after-commit ordering, the account-delete abort path,
and any place where the flag being OFF changes existing behaviour.
