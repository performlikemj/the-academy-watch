# Phase 2 foundation contracts

`P2_FOUNDATION_ENABLED` defaults OFF. It gates emergency actions, notification
enqueue/dispatch. Derived holds always reflect the existing emergency flag,
including after a rollout is switched off. Existing public program
reads respect `ClubProgram.emergency_hidden`; existing public player surfaces
now consult the derived hold too, independently of rollout. Legacy age rules stay unchanged. No frontend changes in this lane.

Migration `p2a1` extends `fl01`, adding `notification_outbox` and
`admin_action_events`. Both tables enable RLS with no anonymous policies.
The orchestrator's guarded SQL is `~/codex-runs/aw-redesign/p2a1_preapply.sql`;
it does not stamp the revision. Apply/verify before stamping `p2a1`.

## Notification intents

Import `enqueue` and `register_template` from `src.services.notification_outbox`.

```python
enqueue(*, dedupe_key, recipient_user_id, event_type, entity_type, entity_id,
        template, payload=None)  # NotificationOutbox, or None with flag OFF
register_template(name, *, eligible, render, payload_enums=None)
dispatch_due(*, limit=100, now=None, send=None)  # worker only; owns commits
```

- Enqueue in the business transaction; it flushes but never commits. The global
  dedupe key identifies an event version and recipient. Reusing a key with a
  different intent raises `ValueError`. A rollback removes the intent too.
- Account recipients only. The worker resolves the current address and rejects
  missing/tombstone accounts and referenced account subjects. The worker commits
  `sending` plus a five-minute lease/token before provider delivery. There is no
  open transaction or account lock across the provider call. Finalization uses
  a fresh transaction and rechecks tombstones; an erased intent stays erased.
- Payload keys are `*_id`, `state`, `version`, `decision`; at most 16 scalar
  fields and 2KB. ID values must be integers (not booleans) or canonical UUID
  strings. Other strings must be declared in `payload_enums`, for example
  `{"state": {"approved", "rejected"}}`; only integer `version` is otherwise
  allowed. Declare enums in both web and worker startup registrations. No child PII, credentials, free text, names,
  addresses or token links. Opaque dedupe/entity IDs also carry no PII.
- A later lane registers a trusted template during application startup:
  `eligible(row, current_user) -> bool` rechecks current entity state, ownership,
  permissions, preferences and applicable public-adult/club holds;
  Templates must cancel when a referenced subject is missing or tombstoned;
  use `entity_type="user_account", entity_id=<uid>` for applicant/account subjects
  so erasure can remove their queued intents to other recipients too. The worker
  enforces this account convention itself.
  `render(row, current_user) -> {subject, html, text}` builds a neutral email
  from current state. Never include child PII. Callbacks must not commit or
  perform external side effects; they run in a savepoint that is rolled back
  before delivery. SQL callback errors retry only that row and the batch continues.
  Unknown templates retry with backoff through `MAX_ATTEMPTS`, then fail.
- Statuses: `pending`, `retry`, `sending`, `sent`, `cancelled`, `failed`. At most five
  attempted deliveries, backoff 60/120/240/480 seconds. Eligibility/provider
  exceptions retry; false eligibility cancels. Errors persist machine codes
  only. Provider and message ID are recorded on success.
- Delivery is at-least-once: a crash after provider success before DB commit can
  duplicate an email. UI decisions must come from authoritative entity state.
  Expired sending leases are reclaimable; a fresh token fences late workers.
  Provider time beyond the lease can also duplicate delivery. Erasure may race
  an already-started send (a submitted email cannot be recalled), but no retained
  row or recipient data is resurrected.
- No template or producer is shipped by A1; registration is required before a
  lane enqueues its template. No job scheduler/deployment changes in this lane.

Run from the backend root with the rollout flag enabled:

```sh
python -m src.jobs.run_notification_outbox --limit 100
# Packaged direct-script entrypoint also works:
python src/jobs/run_notification_outbox.py --limit 100
```

Stdout contains one JSON summary (`sent/retry/cancelled/failed/errors/disabled`).
Retry/failure/infrastructure errors exit 1; disabled/clean runs exit
0. Account erasure deletes every recipient intent, including sent history,
and pending/retry/sending intents referencing that account as their subject.
Account export includes only the recipient's delivery metadata. Privacy export
and erasure still run if the rollout is later switched off; empty foundation
exports and zero deletion counts add no keys to existing responses.

## Admin actions and emergency holds

`src.services.admin_audit.record_admin_event(actor, action, target_type,
target_id, reason, meta=None) -> AdminActionEvent` adds to the caller's
transaction without committing. Actor is an authenticated email or account.
Reason is required, plain text, 1–2000 characters. Metadata is bounded scalar
IDs/booleans/machine codes; never copy private messages, names or secrets.
Target IDs are strings. ORM and PostgreSQL prohibit mutation/deletion;
PostgreSQL also blocks TRUNCATE and downgrade refuses any retained audit rows
or delivery intents. The sole
database update exception scrubs actor/reason/metadata during account erasure,
preserving action/target/time. Already-redacted rows cannot be rewritten. Export includes only the actor's own action
metadata and omits reason/JSON metadata to protect third parties.

Both endpoints use existing admin Bearer **and** API key authentication:

```text
POST /api/admin/programs/<id>/emergency-hide  {"reason": "..."}
POST /api/admin/programs/<id>/emergency-lift  {"reason": "..."}
200 {"program_id": id, "emergency_hidden": boolean}
```

Flag OFF or missing program returns 404; invalid/missing reason returns 400.
The program row is locked; the flag and audit persist atomically. Repeated
actions remain audited with `before_hidden`/`after_hidden`. Individual
`PlayerSuppression` rows and publication approvals remain untouched.

`src.services.club_publication_hold` exposes:

- `club_publication_held(program_id) -> bool`
- `subject_publication_held(signed_id_or_PlayerSubject) -> bool`
- `held_subject_ids(signed_ids) -> set[int]` for a bounded batch
- `club_publication_hold_filter(program_id_expression)` and
  `subject_publication_hold_filter(signed_id_expression)` for correlated SQL.

For public reads, hold the whole player page when **any** linked program
is hidden. Links include local origin, API/local roster, approved claim club
routing, approved team affiliation, tracked parent/current club. Bridges are
resolved across API/local aliases. Local-only program slugs
`console-local-club-<id>` match approved affiliations, including single-hop
merged source/target clubs. Lifting only removes this derived hold; all
other adult/consent/suppression checks still apply. Later lanes must consult
these helpers for directory, opportunities, public clips and related bytes.

## One new-public adult rule

`src.services.public_adult.is_public_adult(signed_id_or_PlayerSubject) -> bool`
mirrors the canonical `resolve_public_adult_subject` identity/bridge rules
using batched current source rows, checks current suppression and
club holds, and requires adult DOB evidence (all known DOBs must be adult) or a
conservatively adult local birth year (at least 19 years before current year).
Missing DOB/year and stored API age alone fail closed. A stale resolved subject
does not bypass a newly applied hold. Club-created private identities remain
private until a later consent/publication lane extends the canonical resolver.

`filter_public_adults(query, signed_id_column, *, max_candidates=100, after=None)`
returns a filtered SQLAlchemy Query for at most 100 distinct candidates (maximum
100). Apply ordinary search constraints first. Source tables use batched IN
lookups and one hold query: eight SQL queries including candidate selection and
final rows for a positive-ID page, independent of candidate count. Scalar and
batch evaluation share `public_adult_ids(signed_ids) -> set[int]`.

Page candidates in signed-ID order using `after`. Read
`query.get_execution_options()["p2_adult_next_cursor"]`; pass it as `after`
until it is None. Empty eligible pages can still have a cursor. Apply display
ordering after this helper, then revalidate final reads/bytes with
`is_public_adult` because eligibility can change after list creation.

## Existing public surfaces wired to emergency holds

- Player profile, stats, season stats, availability, journey and decorated
  player detail routes; API and local-player showcase payloads.
- Local-player identity pages, including requested merged aliases.
- Public showcase photo URLs and `/api/media/published/...` bytes (before
  storage access or conditional cache responses). Private authorized previews
  keep their existing access rules.
- `/p/<signed-id>` share HTML and `/p/<signed-id>/card.png` share bytes.
- Public/scout search and browse, team rosters, cards, leaderboards, comparison
  queries, journey lists and sitemap discovery using the shared suppression
  query filter; upstream global search results use a batched hold filter.
- Other existing public-adult resolver consumers inherit the same neutral
  unavailable response. Actual `is_player_suppressed`, suppression rows and
  legacy age policy remain separate and unchanged.
