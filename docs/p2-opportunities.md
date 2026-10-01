# Phase 2 B2: opportunities and adult recruiting

- Ships dark: `OPPORTUNITIES_ENABLED=false`, `APPLICATIONS_ENABLED=false` by default. Applications require both flags. Rollout also requires A1's `P2_FOUNDATION_ENABLED` for notification enqueue/dispatch; A2's staff flag controls its existing permission resolver. No deployment or flag enablement is part of this PR.
- Stacked on #1109. Migration `p2b2` extends B1's `p2b1`. The four new tables have guarded DDL and RLS. Do not commit a placeholder B1 migration or deploy B2 without the real B1 migration.
- `/api/opportunities/features` returns the effective B2 booleans. The existing `/api/features` payload is unchanged. OFF preserves the opportunity, recruiting and application teasers; new business APIs return neutral 404 before authentication.

## Public opportunities

- `GET /api/opportunities?program_id=&type=&page=`: 30 per page, `has_more`; trial/open_session/position filters. `GET /api/opportunities/<uuid>` returns a published, unexpired opportunity for an approved, non-hidden club.
- Youth sessions can be advertised, but these DTOs never contain applicant identities, staff account email, claim/proof/private feedback or applicant counts. Coach attribution is “Club coaching team.”
- Capacity and places left stay absent until there is a live reservation. Reservations are pending/confirmed invitations; applications alone consume no capacity.
- Directory integration: `src.services.opportunities.open_opportunity_counts(program_ids) -> dict[int,int]`, empty while dark; published, unexpired, approved, non-hidden counts only.

## Club operations

- `GET/POST /api/club/<program_id>/opportunities`; `PATCH .../opportunities/<uuid>` requires `expected_version`; `POST .../opportunities/<uuid>/close` requires `expected_version` and `status=closed|cancelled`.
- Every club endpoint uses A2's `require_club_permission("recruiting")`, with a current inner permission/standing check before writes. Owner/manager only; coaches, analysts and viewers get no recruiting access. Foreign resources are queried through `program_id` and return neutral 404.
- Draft → published → closed/cancelled; published cannot revert to draft. Closing stops intake but allows existing recruiting. Cancelling rejects outstanding applications and releases reservations atomically.
- Trial/session dates are required; positions may omit dates. Timestamps require a UTC offset; the IANA timezone controls display. A closing date is always required and cannot extend beyond a year from creation.
- Squad must belong to the same program. Eligibility and advertised schedule stop changing once any application arrives. Per-applicant invitations can be rescheduled; capacity cannot be reduced below reservations.

## Adults only

- `GET /api/me/application-claims` returns only currently eligible approved self-claims. `POST /api/opportunities/<uuid>/applications` requires `claim_id`, position, optional current club, explicit `contact_consent=true`, and UUID `client_request_id`.
- The claim must belong to the authenticated applicant, have `relationship_type=player`, and be approved. A1's `public_adult.is_public_adult` rechecks identity/age/bridge/suppression/publication holds. Unknown/ambiguous age, club-private identities and guardian/agent claims cannot apply. The opportunity age band is rechecked.
- Profile attachment is a signed subject/claim reference, with only a live eligible display name shown inside the club pipeline. No owner DTO or proof, private feedback, photo or unapproved highlight snapshot is copied. Club-origin publication is C1's prerequisite.
- One application per opportunity/subject while retained; replaying the same client key/hash returns the same result, changed requests conflict. Withdrawal is terminal. A fresh application can be submitted once old data has expired and been purged.
- `GET /api/me/applications`, `GET .../<uuid>`, `POST .../<uuid>/withdraw`, `POST .../<uuid>/trial-response {expected_version,response:accept|decline}`. Applicant reads contain clear status/next steps and no private notes/event reasons. Withdrawal remains possible under a club hold or claim revocation.
- Guardian intake stays an InterestSignup teaser collecting only the adult email; no child details, identity or public consent are created.

## Pipeline and delivery

- `GET /api/club/<program_id>/opportunities/<uuid>/applications`, `GET .../applications/<uuid>`, `POST .../applications/<uuid>/transition`, `POST .../applications/<uuid>/notes {body}`.
- New → shortlisted → invited → attended → offer → signed; active stages can be rejected, applicants can withdraw. Expected version is mandatory for transitions, withdrawals and trial responses.
- Invite requires future `trial_at`, `trial_venue`, optional instructions. Invitation/rescheduling reserves one place; confirmation keeps it, decline withdraws/releases it. Attendance requires a confirmed trial whose date has passed. “Signed” requires `enrollment_confirmed=true` attesting that enrollment happened separately; it creates no membership, identity or public consent.
- Program → opportunity → application lock ordering serializes decisions and capacity. State + append-only versioned `application_events` + outbox enqueue are one transaction. Private notes are separate and retained only with the application.
- A1 `notification_outbox` registered template `b2_application`: submit/invite/reschedule/stage/decision/withdraw/confirmation intents to applicant and current recruiting staff. Payload contains application UUID/version/state only, with `entity_type=user_account` and applicant account ID for tombstone cleanup. Dedupe key is application/version/recipient.
- Delivery rechecks both flags, live application/version/retention, adult claim, club hold and recipient access. Stale intents are cancelled. Emails contain a neutral sign-in destination and no applicant name, note, email, proof or credentials. Delivery remains at-least-once per A1's contract. Run the existing outbox worker; no daemon/after-commit send path.

## Privacy and maintenance

- Applications (including signed outcomes) expire at the earlier of 90 days after trial end/start or vacancy closing date, and 180 days after submission. Explicit early closure/cancellation can shorten that deadline to 90 days from closure. No permanent “signed” retention exemption.
- Run `python -m src.jobs.run_opportunity_retention --limit 100` daily and repeat until caught up. This job works with flags OFF, closes expired postings, deletes expired applications/notes/events/all related outbox dispositions, and deletes empty closed/cancelled opportunities after 90 days. Each invocation bounds opportunity and application processing.
- The migration guards event UPDATE/DELETE/TRUNCATE. The transaction-local privacy setting permits only deletion for retention/erasure or an actor-only nulling update; API routes cannot rewrite history. Downgrade refuses retained rows.
- Account export includes created opportunities, own applications and associated events, own action events, and own authored notes. Club-private notes by other staff are excluded from applicant DTOs and routine export. Erasure removes applicant rows plus notes/events/intents, removes authored notes on others' applications, and nulls event actors/opportunity creators. Hooks stay effective after rollback of flags and tolerate a pre-B2 schema.
- Run the retention job before enabling, and schedule it with the existing production job mechanism during rollout. Production migration/deploy/job scheduling and flag enablement belong to the orchestrator.
