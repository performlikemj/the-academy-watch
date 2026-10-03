# Scout attendance, club Today and distance (C4)

`SCOUT_ATTEND_ENABLED` defaults OFF. OFF preserves the existing Scout Desk, club Today,
public opportunities and unrouted API method/body/header behavior. The separate feature
probe is `/api/scout-attendance/features`; clients treat a missing probe as disabled.

Enable after `p2c3` is applied, with B1 `CLUB_DIRECTORY_ENABLED`, B2
`OPPORTUNITIES_ENABLED`, and A1 `P2_FOUNDATION_ENABLED` for notification delivery.
`APPLICATIONS_ENABLED`, `CONTACT_RAIL_ENABLED` and A2 `CLUB_STAFF_ACCESS_ENABLED`
control their own queues/scopes. Reuse canonical adult, suppression and publication-hold
checks; do not add independent player eligibility rules.

- `POST /api/opportunities/<uuid>/attendance`: authenticated, currently verified/active
  scout; `{note, no_approach_confirmed:true}`. Note max 500; ten requests/hour and
  thirty/day per account. One event/scout pair; identical retry returns the same request.
- Attendable events: published, listed/approved club without a publication hold, future
  trial/open session and unexpired deadline. P2R explicitly permits public youth-session
  adverts; age bands do not grant access to applications, rosters or player identities.
  Applicant identities remain private regardless of the session's advertised age band.
- `GET /api/me/scout-attendance?after=<uuid>`: own retained requests, bounded cursor
  pages, fresh verification/listing/hold checks. Closed sessions stay in own history.
  `POST /api/me/scout-attendance/<uuid>/withdraw` takes `expected_version`.
- `POST /api/club/<id>/attendance/<uuid>/decision`: verified `contact` capability,
  `{decision:"accepted"|"declined",expected_version,arrival_instructions}`. Instructions
  max 500, required on acceptance, visible to that scout only after acceptance. Closed
  intake still permits pending decisions until the session starts. Stale decisions return 409.
- Admission/club decisions lock program → opportunity → scout mutex → attendance;
  trust revocation locks scout mutex → attendance and never asks for program locks; state, audit and A1 notification
  intents commit together. Outbox payloads contain UUID/version/state, never notes,
  credentials, arrival instructions or applicant data. The registered `c4_attendance`
  eligibility function rechecks standing, verification, listing, hold and live contact
  capability at delivery. Old versions are cancelled; A1 retains at-least-once behavior.
- `GET /api/club/<id>/today`: private `players.view` entry guard. Queue keys are omitted
  without their capability: `recruiting` for per-post application counts, verified
  `contact` for introductions/attendance, `matches.view` plus `match_bytes_in_scope`
  for team-sheet/analysing summaries. No applicant DTO, recording token/blob/job data.
- `POST /api/opportunities/search`: anonymous JSON body `lat,lng,radius_km,page,type,
  program_id,event_sessions`; 4 kB hard streaming cap, 60 requests/minute. Uses B1's
  approved revision pin and haversine SQL ordering/radius before pagination. Missing
  pins return `distance_km:null`; radius excludes them. Coordinates are never accepted
  by the C4-enabled GET list; web location is memory-only and can be turned off.

Migration `p2c3 -> p2c2` is guarded schema-only DDL with RLS. C1/C2 ancestor revisions
are verbatim copies of their owners' real revisions, not placeholders. Before code
rollout, apply `ledgers/tooling/phase2/p2c3_preapply.sql` after p2c2 (handoff copy in the external logs). It does not
stamp Alembic. Retained requests prohibit downgrade.

Retention is the earlier of creation +180 days or event end/start/deadline +90 days.
Reads hide expired rows. Account export/erasure and expiry cleanup operate independently
of flags. Run `python -m src.jobs.run_scout_attendance_retention` daily on the backend
maintenance environment after migration; it drains bounded batches. Account erasure
also deletes all matching C4 outbox intents and redacts decision actors.

Tests: `tests/test_scout_attendance.py`; opt-in real PostgreSQL races with
`C4_POSTGRES_URL=postgresql+psycopg://<local-user>@localhost/aw_p2_c4` and
`tests/test_scout_attendance_postgres.py`. The PG fixture refuses other databases.
Web flows: `e2e/scout-attendance.spec.mjs`. All fabricated fixture names are TEST ONLY;
product screens render API data and explicit loading/empty/error states.


## RC4 lifecycle and rollout contract

- New requests still require published intake before its application deadline. Existing pending decisions remain available with published **or closed** intake until `starts_at` (fallback `ends_at`) for the session. Today uses the same timing. At session start, pending requests become neutral `expired`, version/audit/outbox advance once, and instructions are cleared. Own attendance reads, club decision attempts and the daily maintenance job reconcile expiry in bounded batches; Today filters by current session timing and stays read-only.
- A verified contact manager can rescind `accepted -> declined` with `expected_version`; instructions clear and scout/club receive neutral updates. Rescinding remains possible after session start during retained history. Acceptance never grants applicant, roster or player-contact access, including youth sessions.
- Club Today exposes `accepted_attendance` with the session and scout name, organisation and verification status. Accepted permissions remain visible through ongoing sessions for check-in and rescinds. Today stops listing them at `ends_at` (fallback `starts_at + 1 day`); retained own history stays separate. Pagination is `accepted_next_cursor` / `?accepted_after=<uuid>`. Unauthorized callers get neither the queue nor pagination hints.
- Verification revocation and account suspension atomically revoke pending/accepted attendance even after flag rollback. Submit and accept acquire program/opportunity locks, then the scout account mutex before request locks. Moderation takes the scout mutex first, re-reads requests after any wait, then locks requests without program/opportunity locks; trust is checked after acquiring locks. The ORM flush hook locks/retains changed trust IDs before explicit or automatic flush; the commit hook reconciles them atomically, rechecks reverted changes, and clears transaction state on rollback; bulk SQL moderation must call `revoke_user` in its transaction. The daily job also performs a bounded authoritative safety sweep for bulk maintenance changes; Today applies authoritative trust predicates on reads.
- Cancellation changes live requests to neutral `cancelled`, clears instructions and notifies both sides. Closing player intake notifies accepted scouts while preserving future session permissions.
- Trusted C4 outbox callbacks defer current authorized notices during emergency club holds, with no attempt consumed. Lift retries; stale versions, expired retention and permanently invalid membership cancel. Terminal revocation notices remain eligible for the club when the scout has lost verification; suspended recipients remain subject to the central standing gate. Messages contain no notes, identities or arrival instructions.
- A scout may re-request **once** after their own withdrawal while intake is still open. The same row increments version and `request_count` (maximum 2), preserving its original retention deadline. Identical pending retries deduplicate. A second withdrawal or club/system terminal state cannot re-open a request.
- Account exports retain personal request history but omit arrival instructions unless the scout is currently active/verified, the row remains accepted and retained, and the event is currently a visible published/closed session without a club hold. This applies with the feature flag OFF.
- Today returns at most 30 rows per queue, using an authorized/eligible 31st row for pagination hints: 31 attendance rows per status, 31 posts, 101 applications (counts explicitly labelled partial above 100), 31 eligible introductions and 31 scoped matches. Introductions constrain subject candidates to the club's pending queue and load narrow canonical adult evidence as a batch before LIMIT; the match SQL predicate covers squad, snapshot, durable/current roster members and uncertain coverage before LIMIT, with a batched canonical recheck. Trust/advert reads use joined queries and roster/coverage scope evidence is batched. The SQLite regression measures **16 SQL statements for both 1 and 50 pending requests** (including auth/capability checks, no applications/matches backlog). A 50-expired-pending regression also verifies 16 statements and zero writes. Lifecycle maintenance stays outside Today, separately bounded to 100 transitions; its writes/audit/intents scale with actual transitions.
- Schema: guarded p2c3/preapply adds `request_count INTEGER NOT NULL DEFAULT 1`, a 1/2 CHECK, neutral terminal statuses and `ix_scout_attendance_scout(scout_user_id,id)`. Reapply the updated preapply after p2c2; do not stamp Alembic. Fresh upgrade and preapply-twice-plus-upgrade must match.
- **retention job must be scheduled daily before the flag goes ON**: `python -m src.jobs.run_scout_attendance_retention`. It now drains session expiry and trust safety batches before deleting retained-expired rows. No production scheduling or flag action is performed by this lane.

## REVIEW-DUEL C4F2 fixes

- Live retained pending/accepted attendance locks type, start/end, timezone, venue and address with `409 advertised_terms_locked`, including youth adverts with no player applications and after flag rollback. Cancel through the lifecycle route to clear permission and notify; retained terminal rows do not lock these terms.
- Rescind opens a labelled confirmation naming the scout/session and explaining notification and no renewed request. Keep/Escape perform no write and restore focus. The API still uses optimistic versions.
- Intake-closed messages use scout permission wording only for scouts; club recipients get club attendance wording.
- Public opportunity rows show distance only after location is shared. Empty radius searches identify the selected radius and published-location requirement, with Browse without location to recover the ordinary list.
- Both distinct cross-examination N1 findings are covered: canonical introduction eligibility before cap/hints, and removal of accepted scouts from Today after session end. X3's ongoing-session visibility remains covered.

## REVIEW-DUEL C4F3 fixes

- Session locks reject actual normalized changes, allowing full editor payloads with unchanged terms and unrelated corrections. Private club adverts include batched `live_attendance` after rollback. The editor disables the six session terms with an explanation and preserves their exact stored dates; term-lock conflicts have distinct copy.
- Same-program Today refetch preserves other rows and drafts; a successful decision focuses the next request, another accepted action, or the inbox heading. Program changes and failed reads clear private rows/drafts. Rescind errors render once.
- Scout-tab row distances appear only after location is shared; independent club opportunity counts remain visible. Introduction counts append `+` when the eligible queue is capped.
- C4F3 carries verbatim B3F5/C1F2/C2F2 ancestor migrations (p2b3f073ecc8, p2c1 7ff6c7d2, p2c2 58af1d88). Their updated preapply scripts precede unchanged C4 preapply; full-schema preapply-twice/upgrade parity is recorded in the hand-back. B3 preapply requires dedicated `psql -X -v ON_ERROR_STOP=1`; on55P03 rollback/disconnect and retry the entire script after the blocker ends.
