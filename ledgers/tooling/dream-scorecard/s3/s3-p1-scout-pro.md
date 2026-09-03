# S3-P1 — Scout Pro entitlements (backend only; depends on merged P0)

Worktree: __WT__ (branch `feat/s3-p1-scout-pro`, base `origin/main` which already contains P0). Common brief: __COMMON__. Contracts: __CONTRACTS__.

## Requirements
1. `src/services/scout_entitlements.py` (new): `FREE_LIST_LIMIT`, `scout_entitlements`, `is_pro`, `list_limit_for`,
   `require_scout_entitlement` exactly per the contracts. Do NOT move `MAX_FOLLOW_LISTS` (tests monkeypatch it as a `scout` module attribute, e.g. `tests/test_follow_graph.py:330`):
   inside the entitlement functions lazily `import src.routes.scout as scout_module` and read `scout_module.MAX_FOLLOW_LISTS` at call time. Grandfather envs parsed once per call (ISO-8601, `Z` or offset
   allowed, compared as naive UTC). Billing OFF → nothing gated (`csv_export: true`, `custom_lists_max: MAX_FOLLOW_LISTS`).
2. `src/routes/scout.py`: `GET /api/scout/entitlements` (auth; dark → `abort(404)` via `require_billing_rail` from `src/services/stripe_billing.py`, applied OUTSIDE `require_user_auth` so an anonymous probe also sees 404 while dark);
   `scout_export_csv` gated with `require_scout_entitlement("csv_export")` — exact stack top-to-bottom: `@scout_bp.route`,
   `@require_user_auth`, `@require_scout_entitlement("csv_export")`, `@limiter.limit(...)` (auth → entitlement → limiter, so a
   free user gets the 403 before touching the limiter); `scout_lists_create` applies `list_limit_for` per the contract (403 shape below the
   free limit, existing 409 at `MAX_FOLLOW_LISTS`). Do not touch other scout routes.
3. `src/routes/auth_routes.py` `/auth/me`: add `scout_tier` and `scout_pro` (always present; `scout_pro.enabled` false when dark).
4. Tests `tests/test_scout_entitlements.py` (new): derivation for each source (subscription / grandfather boundary at exactly
   `LAUNCHED_AT` and `UNTIL` / none / billing disabled); CSV export 403 shape for a free account and 200 for pro/grandfathered;
   list create: 3 lists ok, 4th → 403 `custom_lists` for free, pro proceeds to the existing 10-cap 409; `/auth/me` new fields
   both dark and lit; `/api/scout/entitlements` dark → neutral 404. Seed subscriptions by inserting `BillingSubscription` rows
   directly (no Stripe). Also run `tests/test_scout_watchlist.py` and any existing test that asserts the `/auth/me` shape
   (grep `auth/me` under `tests/`) — update ONLY shape assertions if they compare whole dicts.

## ALLOWED
`academy-watch-backend/src/services/scout_entitlements.py` (new), `academy-watch-backend/src/routes/scout.py`,
`academy-watch-backend/src/routes/auth_routes.py`, `academy-watch-backend/tests/test_scout_entitlements.py` (new),
existing test files ONLY for whole-dict `/auth/me` shape assertions (report each). No migration. No frontend.

## Commit (exactly one)
`feat(scout): S3-P1 Scout Pro entitlements — derived from billing, CSV export + lists>3 gated, grandfather window`
