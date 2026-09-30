# Phase 2 foundation contracts

`P2_FOUNDATION_ENABLED` defaults OFF. It gates emergency actions, notification
enqueue/dispatch. Derived holds always reflect the existing emergency flag,
including after a rollout is switched off. Existing public program
reads already respect `ClubProgram.emergency_hidden`. Legacy public player
callers are unchanged. No frontend changes in this lane.

Migration `p2a1` extends `fl01`, adding `notification_outbox` and
`admin_action_events`. Both tables enable RLS with no anonymous policies.
The orchestrator's guarded SQL is `~/codex-runs/aw-redesign/p2a1_preapply.sql`;
it does not stamp the revision. Apply/verify before stamping `p2a1`.

## Notification intents

Import `enqueue` and `register_template` from `src.services.notification_outbox`.

```python
enqueue(*, dedupe_key, recipient_user_id, event_type, entity_type, entity_id,
        template, payload=None)  # NotificationOutbox, or None with flag OFF
register_template(name, *, eligible, render)
dispatch_due(*, limit=100, now=None, send=None)  # worker only; owns commits
```

- Enqueue in the business transaction; it flushes but never commits. The global
  dedupe key identifies an event version and recipient. Reusing a key with a
  different intent raises `ValueError`. A rollback removes the intent too.
- Account recipients only. The worker resolves the current address and rejects
  missing/tombstone accounts. It locks account then intent, matching erasure.
- Payload keys are `*_id`, `state`, `version`, `decision`; at most 16 scalar
  IDs/booleans/machine codes and 2KB. No child PII, credentials, free text, names,
  addresses or token links. Opaque dedupe/entity IDs also carry no PII.
- A later lane registers a trusted template during application startup:
  `eligible(row, current_user) -> bool` rechecks current entity state, ownership,
  permissions, preferences and applicable public-adult/club holds;
  `render(row, current_user) -> {subject, html, text}` builds a neutral email
  from current state. Never include child PII. Unknown templates cancel.
- Statuses: `pending`, `retry`, `sent`, `cancelled`, `failed`. At most five
  attempted deliveries, backoff 60/120/240/480 seconds. Eligibility/provider
  exceptions retry; false eligibility cancels. Errors persist machine codes
  only. Provider and message ID are recorded on success.
- Delivery is at-least-once: a crash after provider success before DB commit can
  duplicate an email. UI decisions must come from authoritative entity state.
  Transaction/recipient/intent locks remain held across the provider call.
- No template or producer is shipped by A1; registration is required before a
  lane enqueues its template. No job scheduler/deployment changes in this lane.

Run from the backend root with the rollout flag enabled:

```sh
python -m src.jobs.run_notification_outbox --limit 100
# Packaged direct-script entrypoint also works:
python src/jobs/run_notification_outbox.py --limit 100
```

Stdout contains one JSON summary. Retry/failure exits 1; disabled/clean runs exit
0. Account erasure deletes every notification intent, including sent history.
Account export includes only the recipient's delivery metadata. Privacy export
and erasure still run if the rollout is later switched off; empty foundation
exports add no keys to existing responses.

## Admin actions and emergency holds

`src.services.admin_audit.record_admin_event(actor, action, target_type,
target_id, reason, meta=None) -> AdminActionEvent` adds to the caller's
transaction without committing. Actor is an authenticated email or account.
Reason is required, plain text, 1–2000 characters. Metadata is bounded scalar
IDs/booleans/machine codes; never copy private messages, names or secrets.
Target IDs are strings. ORM and PostgreSQL prohibit mutation/deletion; the sole
database update exception scrubs actor/reason/metadata during account erasure,
preserving action/target/time. Export includes only the actor's own action
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
- `club_publication_hold_filter(program_id_expression)` and
  `subject_publication_hold_filter(signed_id_expression)` for correlated SQL.

For new public reads, hold the whole player page when **any** linked program
is hidden. Links include local origin, API/local roster, approved claim club
routing, approved team affiliation, tracked parent/current club. Bridges are
resolved across API/local aliases. Lifting only removes this derived hold; all
other adult/consent/suppression checks still apply. Later lanes must consult
these helpers for directory, opportunities, public clips and related bytes.

## One new-public adult rule

`src.services.public_adult.is_public_adult(signed_id_or_PlayerSubject) -> bool`
re-resolves via `resolve_public_adult_subject`, checks current suppression and
club holds, and requires adult DOB evidence (all known DOBs must be adult) or a
conservatively adult local birth year (at least 19 years before current year).
Missing DOB/year and stored API age alone fail closed. A stale resolved subject
does not bypass a newly applied hold. Club-created private identities remain
private until a later consent/publication lane extends the canonical resolver.

`filter_public_adults(query, signed_id_column, *, max_candidates=1000)` uses the
same predicate over bounded distinct candidates, then returns a filtered
SQLAlchemy Query. Apply search constraints first and this filter before
pagination. It raises if the bound is exceeded; large discovery must explicitly
page candidates. This is intentionally a bounded foundation helper, not a
bulk SQL age-policy implementation. Revalidate the final read/byte endpoint
with `is_public_adult`, since eligibility can change after list creation.
