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
  sessions cannot receive a new decision. Stale decisions return 409.
- Mutations lock program → opportunity → attendance; state, audit and A1 notification
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
