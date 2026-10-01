# Phase 2 B3 — admin control room

Draft, stacked on A2 #1109. No production switch-on is part of this lane.

- `ADMIN_PROGRAMS_ENABLED`, `ADMIN_PEOPLE_ENABLED`, `ADMIN_SAFETY_ENABLED`,
  `ADMIN_BUSINESS_ENABLED` are independent and default OFF. New endpoints/pages
  return unavailable while off; existing admin routes and navigation remain.
- GET `/api/features` adds only enabled `admin_programs`, `admin_people`,
  `admin_safety`, `admin_business` keys. Every new admin API requires the existing
  admin bearer plus API key. Responses are `Cache-Control: no-store`.
- Web routes: `/admin/programs`, `/admin/people`, `/admin/safety`, `/admin/business`.
- Migration `p2b3` → **`p2b2`**, after real B1/B2 migrations. No placeholder revisions
  are shipped. Guarded DDL, all four new tables use RLS. Downgrade refuses retained
  cases/events/cash/deployment observations or changed account standing.

## Programs

- GET `/api/admin/programs?q=&limit=&offset=`; GET `/api/admin/programs/<id>`.
- Allowlisted program/manager standing, origin, bounded roster/manager/match/claim
  counts; no private roster notes, feedback, photos or film-derived details.
- UI calls A1 POST `/admin/programs/<id>/emergency-hide|emergency-lift` with reason
  (`P2_FOUNDATION_ENABLED`), and A2 POST `/admin/programs/<id>/owner` with
  `{user_account_id,reason}` (`CLUB_STAFF_ACCESS_ENABLED`). Neither is reimplemented.
- Owner selection is an explicit admin action. Current verified managers are the
  candidates; A2 validates claim standing authoritatively.

## People and suspension

- GET `/api/admin/people?q=&role=all|players|clubs|scouts|admins&limit=&offset=`;
  GET `/api/admin/people/<id>`.
- Roles are derived from current writer/editor/curator flags, approved player/guardian
  claims, claim-backed managers, live A2 access and scout-verification state. Admin
  provenance is the environment allowlist. These labels never grant access.
- POST `/api/admin/users/<id>/suspend|restore` with `{reason}` is audited and locks
  the account. Self-suspension from the current admin session is refused. Tombstones
  cannot be restored. Pending login codes are removed; repeated same-state actions
  are idempotent.
- `account_status`/`auth_epoch` are separate from personas and grants. Suspension
  checks are **persistent even after the page flag is switched OFF**. Active users
  keep their existing access. OTP requests remain neutral; correct-code suspended verification grants only
  restricted subscription/account rights, central bearer serializer covers optional-auth/curator/admin consumers,
  and `resolve_bearer_user` continues its existing identity-generation checks.
- User/admin media tokens and legacy email-bound media capabilities recheck live
  standing. Newly minted media tokens carry the account epoch. Restore requires
  fresh login; old bearers/media capabilities remain revoked.
- Approved one-line B3 checks in A2 `resolve_club_access` and `club_actor_allowed`
  protect service grants. Signed courtesy-consent links reject a registry recipient
  mapped to a suspended account; legacy non-account recipients keep their behavior.
  These anonymous courtesy links follow current standing on restore; authenticated
  bearer/media tokens retain epoch revocation and need fresh login.
- Existing direct Azure upload/read SAS already handed out retain A2's documented
  lifetime; downloaded bytes cannot be recalled. B3 adds no new SAS mechanism.
- People responses are allowlists: no claim notes, scout statements/evidence,
  coach feedback, private club notes or messages. Scout/writer actions link to
  existing moderation tools. Exports remain authenticated self-service.

## Safeguarding

- GET `/api/admin/safety/cases?status=open|all&limit=&offset=`, GET `cases/<id>`,
  POST `cases/<id>/actions` with `{action,reason,version}`, GET `safety/hidden`.
- `safeguarding_cases` references original reports/suppressions and preserves typed
  target, receipt, first-action deadline/time, closure, resolver and version.
  `safeguarding_case_events` retains actions; PostgreSQL forbids UPDATE/DELETE/TRUNCATE
  except exact identity erasure. A1 audit records each decision/evidence read.
- ORM intake creates the case/event in the original report/takedown transaction
  while enabled. Migration imports prior requests; enabled application startup
  reconciles requests received during a dark period without resetting existing cases.
  The deadline always uses original receipt + 24h.
- `hide` activates the existing player suppression (including web `local:<id>` and
  signed IDs), or applies the existing derived program hold. Showcase-photo reports
  resolve to their owning player. Existing active suppressions are never owned/lifted
  by another case. No public serialization is added, and no adult rule is weakened.
- `investigate`, `club_contact`, `close` record actions. Version conflicts return 409.
  Closing a case **does not lift any hold**. The case restore action lifts only its own hold, even with Foundation OFF.
  A later independent moderation decision prevents case restore; unsupported content targets link to existing
  moderation and refuse automatic hide, rather than pretending they are hidden.
- Detail exposes only its reported statement/reason and its action history; unrelated
  feedback/notes/messages are never queried. Evidence reads are audited.
- A1 outbox `safeguarding_update` sends generic, PII-free hidden/closed updates and
  rechecks authoritative recipient/source/hold state. Payload carries only case ID,
  version and registered enum. Reporters use their account ID; anonymous
  takedowns never select a notification recipient, and duplicates preserve original evidence.
  No account is created for anonymous intake. Missing recipient/foundation-disabled
  states are shown honestly; email providers are not called from requests.
- Hidden inventory has separate paginated player suppressions and program holds.
  A complete legacy under-18-public audit is unavailable and is shown as such.
  Guardian applications remain a teaser; no invented zero-minors claim is displayed.

## Business

- GET `/api/admin/business/summary?from=YYYY-MM-DD&to=YYYY-MM-DD&limit=&offset=`.
  Inclusive UTC days, maximum 366; currency totals cover the full filter independently
  of pagination. Film Room credit returns and MRR are never counted as cash.
- `billing_cash_events` is a durable projection runs after the verified webhook commits, in its own transaction. Receipts use individual invoice-payment amounts (modern Stripe) or
  payment-backed zero-balance legacy invoice totals; paid GOL checkout receipts
  survive account deletion. Refunds use successful individual refund IDs and dates,
  never repeated cumulative `amount_refunded`. Unique source keys handle duplicate
  and out-of-order webhook delivery. Modern payments/truncated refunds are paged
  via Stripe read APIs; provider reads happen before the projection transaction; failures are logged and never roll back billing. Signed webhook replay repairs missing rows. Run `python -m src.jobs.reconcile_business_cash` periodically to repair the latest 50 provider events (bounded, idempotent); older gaps require signed event replay.
- Historical GOL grants supplement receipts only when no matching cash projection
  exists. Earlier subscription receipts/refund timestamps cannot be reconstructed
  from price/MRR or mutable cumulative settlements. Coverage is explicit in the UI.
- Amount fields retain existing `*_cents` naming but contain Stripe minor units;
  the UI handles zero-decimal charge currencies correctly.
- Refunds link to `dashboard.stripe.com/payments/<payment-intent>`; there is no refund
  initiation API or in-app freeze toggle. Effective and configured newsletter freeze
  are distinguished; football freeze still implies newsletter freeze, stored reads remain.
- `business_deployment_states` observes immutable `CONTAINER_APP_REVISION` (or
  `AW_DEPLOYMENT_ID`) on the first authenticated Business read (at most once every five minutes per worker), deduplicated across workers. Startup only registers hooks and never queries the DB. Optional
  command: `python -m src.jobs.record_business_deployment`. It records env truth only.
  No deployment identity means no invented deployment log row.

## Privacy and rollout

- B3 adapters are additive, schema-aware account export/erasure hooks. Export only
  own safe case status and cash records; redact case-event/resolver identities;
  anonymize purchaser/user scope in retained cash. Foundation outbox erasure handles
  account-bound pending intents. No credentials or child PII enter outbox payloads.
- Apply A2's latest p2a2 and B1/B2 before p2b3; pre-apply on production is the
  orchestrator's responsibility. Four shared migration-head pins remain p2a2 per BUS;
  integration updates them once to the final chain head.
- Schema-only SQL for orchestrator review: `~/codex-runs/aw-redesign/p2b3_preapply.sql`.
  Generated from the migration operations/constants and reapplied twice on the scratch DB.
  It changes no flags and does not stamp Alembic.


## RB3 safe defaults and rollback

- Wrong-code verification has identical 400 status/body and query count for unknown,
  active and suspended accounts. Correct code is consumed before a neutral unavailable
  response gives a separately salted, epoch-bound, 15-minute account-access token.
  It authenticates only account export/delete and the billing portal. Login UI exposes
  those actions; normal bearer/admin/media/checkout access remains blocked. Suspended
  users can still cancel subscriptions, export their data and delete their account.
- Suspend, emergency hide, case hide and case close require a reason and a confirmation
  naming the target. Suspending the last active owner warns that nobody remains to
  manage staff or billing. A clip report continues to hide the whole player page.
- People/program pages escape LIKE wildcards, cap search at 120 characters and debounce
  typing by 300ms. Page sizes cap at 100; counts and people metadata use grouped/batched
  queries rather than one query per row/grant. The clubs filter requires an approved
  source claim, matching the club-manager badge.
- Safety reconciliation is lazy on authenticated admin reads, at most once per five
  minutes per worker and 500 missing rows per source per pass; absent schema/DB errors
  are caught/logged. Existing moderation decisions update linked cases transactionally.
  Reconciliation excludes case-owned suppressions and intake deduplicates by source ID.
- **Rollback is application/flag rollback while retaining the additive schema.** Migration
  backfill creates retained cases on real data; destructive Alembic downgrade refuses
  them, cash/history/deployment rows and changed account standing. This is deliberate.
  Do not delete evidence or reset auth epochs to force a downgrade. Empty scratch
  installations may downgrade. Keep safety recovery available and restore accounts
  through audited administration if policy calls for it; flags OFF preserve standing.
