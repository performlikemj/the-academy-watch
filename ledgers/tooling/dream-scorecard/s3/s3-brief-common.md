# S3 — "Money rails" (The Academy Watch / loanarmy) — COMMON CONTEXT

You are codex, implementing ONE work package of S3 in a dedicated git worktree. Read this whole brief, then the
contracts file, then your package brief before touching code. Then read, in order: `CLAUDE.md`,
`docs/agents/backend.md` (backend work), `docs/agents/frontend.md` (frontend work), `docs/agents/invariants.md`,
`docs/agents/workflow.md`.

## Why S3 exists (context, do not re-audit)
A 2026-09-02 scorecard graded the platform at 61.0% after S0–S2 with ~0 real users and $0 revenue. S3 adds the
money rails: Scout Pro as a real Stripe subscription, a club-editable program profile with a Patreon / Buy Me a
Coffee link-out (no money moves through us), and the pages for both. Prod facts: Stripe keys in prod are LIVE
(`sk_live…`) — you will NEVER see or use them; local acceptance uses a TEST key set (`sk_test…`, `whsec…` from
`stripe listen`) that the orchestrator may put in the worktree `.env`, or, more often, no key at all: your tests
MUST pass with NO Stripe environment (mock every `stripe.*` network call with monkeypatch). `PUBLIC_BASE_URL=https://theacademywatch.com`
(website origin), `PUBLIC_API_BASE_URL=https://api.theacademywatch.com` (API origin). Alembic head is `s3c1` (chain … pm01 → s2f1 → cb01 → s3b1 → s3c1); always re-verify with `flask db heads`.
Backend tests run on SQLite in-memory (JSONB→JSON; no `ON CONFLICT`, no `@>`) — write dialect-neutral code.
Timestamp columns are timezone-NAIVE UTC; normalise any aware `now` to naive UTC before comparing or storing.
Stripe SDK: prod builds `stripe==15.6.0` from requirements.txt; the shared test venv `.loan` has 14.0.1 and SQLAlchemy 2.0.41
(prod 2.0.52) — do NOT touch dependencies; use only the module-level API below, identical in both versions (module-level API: `stripe.Webhook.construct_event`, `stripe.SignatureVerificationError`,
`stripe.checkout.Session.create`, `stripe.billing_portal.Session.create`, `stripe.Subscription.retrieve/cancel`,
`stripe.Price.retrieve`, `stripe.Customer.create`). Stripe API versions from 2025 put `current_period_start/end`
on subscription ITEMS, not on the subscription — read the first item first, fall back to the subscription.

## Ratified decisions (do not reopen)
- D1 (dark ship): every S3 billing route is behind `BILLING_ENABLED` (default off → Flask `abort(404)`, exactly the contact-rail
  pattern: `require_contact_rail` in `src/services/contact.py:87-97` + the `before_app_request` prefix hide in
  `src/routes/contact.py:81-88`; reuse that shape, do not invent a body).
  Non-billing routes that gain fields (`/auth/me`, `/programs/<slug>`) keep working with the flag off. Scout gates are
  NO-OPS with the flag off: nothing that works today may stop working when `BILLING_ENABLED` is unset.
- D2 (one foundation, one webhook): all Stripe state lives in the four `billing_*`/`stripe_webhook_events` tables from
  the contracts. Entitlement is DERIVED from `billing_subscriptions`; `UserAccount.scout_tier` is only a projection
  written in the same transaction. The webhook verifies the signature on the RAW body, inserts the event row FIRST
  (unique `event_id`), applies, commits once; replays answer `{"received": true, "duplicate": true}`.
- D3 (server-side prices): the product→Stripe-price map comes from env (`STRIPE_PRICE_*`). The browser sends
  `product_code` + `price_code` + `client_key` only. Never accept a price id, amount, currency, or success URL from a request.
- D4 (Scout Pro gates only what costs us): CSV export and custom lists beyond 3. Watchlist, notes, digest stay free.
  Pre-launch accounts are grandfathered via `SCOUT_PRO_LAUNCHED_AT` + `SCOUT_PRO_GRANDFATHER_UNTIL`. The 403 shape is
  `{"error": "scout_pro_required", "feature": "<feature>", "upgrade_path": "/pricing"}`. iOS gets no purchase UI.
- D5 (clubs: no money): managers edit a PENDING profile revision; the approved revision changes only through the
  admin review route. The external support link is a moderated field on the revision, allowlisted to patreon.com /
  buymeacoffee.com hosts. `is_fundable` stays hard-coded `false`; no donation CTA anywhere; no Connect promotion;
  no club bundle checkout in S3 (`product_not_available` 403).
- D6 (audit + analytics): admin decisions write `FundingAdminEvent` rows (existing `_audit`). Product events are
  analytics only, never entitlement truth; server-written billing events use `billing_*` names outside the public allowlist.
- D7 (emails): status emails via `email_service` are sent AFTER commit; a send failure never fails a webhook or a route.
- D8 (account deletion): active Stripe subscriptions are canceled at Stripe BEFORE any row is deleted; a Stripe failure aborts the deletion.

## Hard fences (all packages)
- Work ONLY inside your worktree. Never touch the main checkout or other worktrees.
- Edit ONLY the files/dirs listed as ALLOWED in your package. If another file must change, STOP and say so in the
  final report instead of editing it.
- No `git push`. No ledger/CONTINUITY edits. No secrets in code, logs, tests, or the report (no `sk_`/`whsec_`
  values — use obviously fake placeholders like `whsec_test_placeholder`). No new dependencies (no lockfile edits).
  No migrations unless your package says so.
- Smallest correct mechanism on top of what exists. Cite the real functions you extend.
- Never reference the deleted `AcademyPlayer`/`SupplementalLoan` models. Use `TrackedPlayer`.
- Finish with exactly ONE commit using the exact message given, staged by path (`git add <paths>`), never
  `git add -A`/`.`. Never `--no-verify`.

## Gates (run all that apply; paste real output summaries in the report)
- Backend: `cd academy-watch-backend && ruff check . && ruff format --check .` (`ruff` 0.15 is on PATH at
  `/opt/homebrew/bin/ruff`; the venv has no ruff). Python is the shared venv of the MAIN checkout:
  `PY=/Users/michaeljones/Projects/loanarmy/.loan/bin/python` (3.11; your worktree has no `.loan`). Run
  ONLY the named tests you touched/added plus their files:
  `cd academy-watch-backend && PYTHONDONTWRITEBYTECODE=1 $PY -m pytest -p no:cacheprovider -q tests/<file>.py`.
  Migrations: `cd academy-watch-backend && $PY -m flask --app src.main db heads` must print ONE head.
  Main has import-broken legacy test files — do not try to make the whole suite green. FOUR tests fail on
  main before S3 and are NOT yours: `tests/test_local_clubs.py::TestAffiliationVisibility` (3) and
  `tests/test_account.py::...test_delete_erases_owned_data_and_tombstones_shared_integrity` (1) — report
  them separately, never "fix" unrelated fixtures for them.
- Frontend: first `./scripts/setup_frontend.sh` from the repo root (OSV gate + frozen install, only
  installs if missing/stale), then `cd academy-watch-frontend && pnpm lint && pnpm build`. Build
  failure blocks. UI work adds ONE Playwright spec under `academy-watch-frontend/e2e/` mirroring the
  mocked-API specs there (`account-rails.spec.mjs` is the pattern), and runs just that spec (see PORT FENCE).

## Final report contract (last message, plain text, ≤60 lines)
1. What changed (files + the mechanism, 5–10 lines). 2. Commit hash + message. 3. Gate outputs
(ruff / pytest counts / lint / build / spec pass counts). 4. Anything you could NOT do and why.
5. Any file outside ALLOWED you think must change (not changed). 6. Risks a reviewer should attack.
Be honest: a failed gate is reported as failed, never hidden.

## PORT FENCE (mandatory)
Ports **5001** and **5173** belong to another session's live app. Never start, kill, or reuse anything on
them. Playwright: start your own Vite from YOUR worktree on the port your package names (`pnpm dev --host 127.0.0.1
--port <port> --strictPort`), set `E2E_BASE_URL=http://127.0.0.1:<port>`, mock every `**/api/**` with `page.route`,
put specs under `e2e/`, run `E2E_BASE_URL=... pnpm exec playwright test e2e/<spec>.mjs`, stop Vite by PID.
Do not run `sim/run.mjs`. Never start a Flask server.
