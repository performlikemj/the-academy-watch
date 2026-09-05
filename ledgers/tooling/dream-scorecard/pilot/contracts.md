## Overview

These contracts are based on local HEAD `59dfdca9ae80ae58df737360c0e7ee6f9e96a22f`. This was a read-only, offline review: no files changed, commands against services executed, or tests run.

**Path abbreviations:** `B/` = `academy-watch-backend/`; `W/` = `academy-watch-frontend/`. Citations identify existing files. Files marked **new** are proposed deliverables.

| Wave | Package | Dependency and release condition | Effort |
|---|---|---|---|
| Operator | P0 | Rehearse first; real footage requires the recorded permissions and sample gate | S |
| 1, parallel | P1 | Independent of P2; absent later tables produce explicit capability gaps | M |
| 1, parallel | P2 | Builds independently; production writes remain disabled until P3 account hooks land | M |
| 2, sequential | P3 | Starts after both wave-1 merges; completes P2/P3 account lifecycle before activation | M |
| 2, sequential | P4 | Starts after P3; required before repeat result entry | L |

Budget **17–29 builder-days**, including focused tests and checker fixes; operator, processing, recruitment, and observation time are additional. This exceeds the original estimate because the contracts include migration recovery, account lifecycle, legacy result adoption, and actual concurrency evidence. The original effort definitions are at `ledgers/research/pilot-direction-codex-2026-09-05.md:76`.

**Two integration decisions preserve the fences:**

- P1 extends the existing `events.py` blueprint and embeds its page in `AdminTools`; neither wave-1 package edits `main.py`, `App.jsx`, `api.js`, or `track.js`. Existing registration and navigation support those entry points. (`B/src/main.py:142`; `W/src/App.jsx:4183`; `W/src/lib/api.js:292`)
- P2 ships with `PILOT_CLUB_RELATIONSHIPS_ENABLED=false`. P3 owns the account-service changes for invitations and feedback, plus schema-aware hooks for P4. Enable relationships only after P3’s export/erasure tests pass. This is necessary because account deletion explicitly rejects unclassified user foreign keys **before** deleting the account; `ON DELETE CASCADE` alone does not suffice. (`B/src/services/account.py:595`)

**Common implementation contract**

- One commit and one PR per software package; stage exact paths, never `git add -A`, never bypass hooks, merge, or push to main. Builders do not edit ledgers, documentation, dependency manifests, or unrelated files. This follows the money-stage operating contract. (`ledgers/tooling/dream-scorecard/s3/money-safety/ms-common.md:10`)
- New timestamps: naive UTC `DateTime()`, generated using `datetime.now(UTC).replace(tzinfo=None)`; API timestamps use explicit `Z`. Reuse the existing UTC convention, not older timezone-aware model defaults. (`B/src/services/contact.py:51`)
- Generic SQLAlchemy types and queries. SQLite proves behavior and constraints; PostgreSQL proves locking, migrations, and RLS.
- Every migration guards tables, columns, indexes, and constraints individually; a partially applied table must not cause the remaining DDL to be skipped. Enable PostgreSQL RLS on every new table, including when the table already exists; add **no public access policies**. (`docs/agents/backend.md:19`; `docs/agents/invariants.md:22`)
- Existing migration helpers query PostgreSQL catalogs. Do not claim that SQLite `create_all()` or offline `alembic --sql` verifies them. Use online disposable PostgreSQL and SQLAlchemy inspection for constraint guards. (`B/migrations/_migration_helpers.py:11`; `ledgers/tooling/dream-scorecard/s3/money-safety/ms-critique-gpt-6-astra.md:29`)
- New request bodies reject non-object JSON, unknown fields, booleans in integer fields, oversized strings, and invalid enums. Errors never echo submitted private text.
- Authentication errors retain the existing strings: `missing auth token`, `auth token expired`, `invalid auth token`, `invalid token payload`, `account not found`. Manager denial remains `403 {"error":"Club manager access denied"}`. Admin auth remains `require_api_key`, which requires an admin Bearer and API key. (`B/src/auth.py:517`; `B/src/services/club_registry.py:171`; `B/src/auth.py:284`)
- New private responses, including errors after authentication: `Cache-Control: private, no-store`.
- New limited endpoints return `429 {"error":"rate_limit_exceeded"}` with `Retry-After`, using decorator-level rejection handling; no global limiter changes.
- PostgreSQL deadlock/serialization failures roll back the entire operation and return `409 {"error":"retry_conflict"}`. Clients may retry with the same request identity/version; never retry an unknown partial transaction.
- Signed player IDs are nonzero integers within ±2,147,483,647. Use `resolve_public_adult_subject`, which wraps `resolve_player_subject` and adds conservative positive-player age and local-suppression checks. Do not use `PlayerSubject.is_public` alone as positive-player adult proof. (`B/src/services/public_player_subject.py:13`; `B/src/services/player_subject.py:119`; `B/src/services/season_rollup_service.py:596`)
- No invitation, feedback, or result flow grants public footage access, profile ownership, a public affiliation, or introduction consent implicitly. Existing roster membership is explicitly private; existing public showcase excludes club footage. (`B/src/models/funding.py:448`; `B/src/routes/showcase.py:1328`)

**Common verification**

```bash
ruff check academy-watch-backend
ruff format --check academy-watch-backend
```

Run the named backend suites using `/Users/michaeljones/Projects/loanarmy/.loan/bin/python -m pytest`. For web changes, run `pnpm lint`, `pnpm build`, and `pnpm test` from `academy-watch-frontend`. Restore dependencies only through the repository setup/security gate if missing or stale. (`docs/agents/backend.md:6`; `docs/agents/frontend.md:12`)

For each new Playwright spec:

```bash
# Select and verify an unused port; 5199 is only an example.
pnpm exec vite --host 127.0.0.1 --port 5199 --strictPort
E2E_BASE_URL=http://127.0.0.1:5199 \
  pnpm exec playwright test e2e/<package-spec>.spec.mjs --project=chromium
```

Mock all API requests and fail on unexpected calls. Include desktop and 390px mobile-width scenarios. `E2E_BASE_URL` disables the configuration’s automatic 5173/5001 servers; do not reuse another session’s servers. (`W/playwright.config.js:11`; `W/playwright.config.js:42`)

**PR body template — required for P1–P4**

```markdown
Problem and resulting behavior:
<Concrete trigger and resulting behavior; package ID>

Contract:
<Contract sections satisfied; explicit deviations or “none”>

Validation:
<Exact commands and output counts>
<PostgreSQL checks: PASS / not run, with reason>
<Playwright scenarios and artifact location>

Migration / pre-apply:
<Revision and parent, or none>
<Verified DDL artifact/checksum, legacy-data work, RLS checks>
<Activation and rollback conditions>

Checker attacks:
<Named negative/concurrency cases and outcomes>

Delivery:
<Diff stat, commit SHA, unresolved limitations>
```

The checker must report PASS or FIX-FIRST, with reproducible findings tied to these contracts. A skipped required PostgreSQL check is not PASS.

## P0 runbook

**Goal and non-goals**

Prove that one authorized club can complete a useful, private, founder-operated review with an adult subgroup. Rehearsal proves application journeys; the real sample proves actual processing and coach usefulness. This runbook does not activate billing, send outreach, authorize youth participation, or turn the sim’s seeded analysis into real processing evidence. The owner directive makes those boundaries explicit. (`ledgers/DIRECTIVE_pilot-club.md:12`)

**Data model, migration, export/erasure**

None. No schema changes or production fixture seeding. Store the register, permission references, evidence, costs, and decisions in an operator-controlled location outside public PRs. Store references to permissions, not identity documents or footage, in the rollout record.

**1. Rehearse the exact candidate**

The orchestrator runs:

```bash
zsh ledgers/tooling/dream-scorecard/basecamp_sim.sh main
```

For a package candidate, substitute its pushed origin branch. Record the printed SHA.

The current script checks occupied ports, makes a `sim_<timestamp>` database copy, migrates that copy, runs `SIM_GRADE=0`, prints step results, and drops the copy on exit. It also permits an “ahead of branch” migration exception and can print results after a nonzero sim exit. Therefore **exit status alone is insufficient**. (`ledgers/tooling/dream-scorecard/basecamp_sim.sh:10`; `:138`; `:224`; `:227`; `ledgers/tooling/dream-scorecard/README.md:9`)

Pass requires:

- Intended SHA, disposable database name, no shared-database migration.
- No “DB ahead of branch” exception for the candidate under review.
- Report generated by this run; every required step succeeds, with nonzero step count.
- Cleanup succeeds.
- Screenshots contain synthetic subjects only.
- Record `SIM RESULT n/n ok`, report path, SHA, migration head, and any deliberately absent coverage.

Do not treat this ungraded run as proof that a GPU/model worker processed the pilot’s footage.

**2. Establish the operating record before ingestion**

Record:

- Program ID and provider team ID separately.
- Two staff accounts, six adult player accounts/subjects, external scout account, supporter account.
- Founder/team/reviewer/test exclusions.
- Named coach, first review date, later-week review date, processing allowance.
- Footage permission reference, approved purpose, permitted viewers, withdrawal contact, and raw/derived-data treatment.
- Adult eligibility check for each player; footage permissions also cover identifiable opponents and bystanders.
- Agreed date and responsible buyer for the paid-continuation discussion.

Raw retention currently deletes footage while retaining derived records; do not promise otherwise. (`B/src/services/video_retention.py:1`)

**3. Verify official approval and console authority**

Each staff member signs in personally and submits the existing club claim through `/my-club`. For a provider club, the equivalent request is:

```http
POST /api/clubs/claim
Authorization: Bearer <staff-token>
Content-Type: application/json

{"team_api_id":<provider-team-id>,"role_title":"Coach","message":"<bounded verification note>"}
```

The existing submission requires exactly one provider-team/local-club identity and limits claims to five per hour. (`B/src/routes/showcase.py:2117`)

The founder verifies authority and approves through the admin UI or:

```bash
curl -sS -o "$PILOT_EVIDENCE/claim-review.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer $PILOT_ADMIN_TOKEN" \
  -H "X-API-Key: $PILOT_ADMIN_KEY" \
  -H 'Content-Type: application/json' \
  --data '{"action":"approve"}' \
  "$PILOT_API/admin/club-claims/$PILOT_OFFICIAL_CLAIM_ID/review"
```

Expected: 200 and approved claim. Approval invokes the console bridge; a conflicting registry program must use the funding-claim path rather than creating another program. (`B/src/routes/showcase.py:3337`; `B/src/routes/showcase.py:3377`; `B/src/services/club_console_bridge.py:511`)

Here and below, `PILOT_API` includes `/api`; credentials are supplied privately, shell tracing is off, and evidence files have restricted permissions.

Run this read-only PostgreSQL check using an already configured connection:

```sql
SELECT p.id AS program_id, p.team_api_id, p.platform_status,
       p.emergency_hidden, m.user_account_id, m.status AS manager_status,
       c.id AS source_claim_id, c.status AS source_claim_status
FROM club_programs p
JOIN club_program_managers m ON m.program_id = p.id
LEFT JOIN club_program_claims c
  ON c.id = m.source_claim_id
 AND c.program_id = m.program_id
 AND c.user_account_id = m.user_account_id
WHERE p.id = :program_id
ORDER BY m.user_account_id;
```

For `psql`, supply `-v program_id="$PILOT_PROGRAM_ID"` and use `:program_id` exactly as above. Pass requires both staff to have active grants, approved source claims, and an approved, non-hidden program—the strict console predicate. (`B/src/services/club_registry.py:138`)

**4. Perform authority attacks**

```bash
curl -sS -o "$PILOT_EVIDENCE/manager-roster.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer $PILOT_MANAGER_TOKEN" \
  "$PILOT_API/club/$PILOT_PROGRAM_ID/roster"

curl -sS -o "$PILOT_EVIDENCE/other-club-denial.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer $PILOT_OTHER_MANAGER_TOKEN" \
  "$PILOT_API/club/$PILOT_PROGRAM_ID/roster"

curl -sS -o "$PILOT_EVIDENCE/anonymous-denial.json" -w '%{http_code}\n' \
  "$PILOT_API/club/$PILOT_PROGRAM_ID/roster"
```

Expected respectively: 200; 403 `Club manager access denied`; 401 `missing auth token`.

On the disposable rehearsal, revoke an approved official claim using the existing review endpoint with `{"action":"revoke"}`. Reuse its previously issued manager token: roster, matches, report, reel, and media-token requests must all deny. Test a pending manager and cross-program resource IDs too. The existing review path revokes the console grant. (`B/src/routes/showcase.py:3351`; `:3379`)

For the real club, use existing pending/revoked test accounts; do not revoke the operating coach merely to demonstrate a negative test.

**5. Reconcile the selected identities**

For each signed player ID:

```bash
curl -sS --fail "$PILOT_API/players/$PILOT_PLAYER_ID/profile" \
  -o "$PILOT_EVIDENCE/player-profile.json"

curl -sS --fail \
  "$PILOT_API/players/$PILOT_PLAYER_ID/season-stats?season=$PILOT_SEASON" \
  -o "$PILOT_EVIDENCE/player-season.json"
```

These existing routes support signed IDs. (`B/src/routes/players.py:643`; `:866`)

In the web UI, compare name, birth/adult eligibility, academy origin, current club, tracking status, season, and provenance against the coach’s records. Record corrections or explicit “coverage unavailable”; do not substitute academy-relative status for contractual availability.

Before P2 activation, do not create a duplicate manager-owned local identity to bypass the creator-only roster restriction. (`B/src/routes/club.py:862`)

**6. Process one authorized real sample**

In `/my-club`:

1. Create a match with date, opponent, competition, kit colors, and camera answers.
2. Upload using its issued SAS.
3. Mark kickoff and complete upload.
4. Save the shirt-number roster.
5. Request processing.

Equivalent request shapes:

```http
POST /api/club/<program>/matches
{"match_date":"2026-09-05","opponent_name":"<opponent>",
 "competition":"<competition>","our_kit_color":"<color>",
 "opponent_kit_color":"<color>"}

POST /api/club/<program>/matches/<match>/upload-complete
{"kickoff_s":12.5,"duration_s":5400}

PUT /api/club/<program>/matches/<match>/roster
{"entries":[{"club_roster_member_id":<member-id>,"jersey_number":8}]}

POST /api/club/<program>/matches/<match>/process
{}
```

Creation returns 201 and `upload.upload_url`, or an explicit upload-unavailable state. Upload completion verifies the blob and records its ETag. Processing request returns 202 but **only records a request**. (`B/src/routes/club.py:1210`; `:1289`; `:1413`; `:1491`; `B/src/services/video_storage.py:72`)

If performing upload with curl:

```bash
curl -sS --fail -X PUT \
  -H 'x-ms-blob-type: BlockBlob' -H 'Content-Type: video/mp4' \
  --upload-file "$PILOT_VIDEO_FILE" "$PILOT_UPLOAD_URL"
```

Do not print or preserve the SAS in the public evidence.

The operator then queues the actual job:

```bash
curl -sS -o "$PILOT_EVIDENCE/cv-dispatch.json" -w '%{http_code}\n' \
  -H "Authorization: Bearer $PILOT_ADMIN_TOKEN" \
  -H "X-API-Key: $PILOT_ADMIN_KEY" -X POST \
  "$PILOT_API/admin/video/matches/$PILOT_MATCH_ID/process"
```

Expected: 202 with `job` and `dispatch`; not completion. Club-console processing requires the manager’s request and bypasses the legacy team-credit debit. (`B/src/routes/video.py:306`)

Inspect:

```sql
SELECT id, video_match_id, pipeline_kind, status, stage, attempt,
       worker_id, started_at, heartbeat_at, completed_at, gpu_seconds,
       error IS NOT NULL AS has_error
FROM video_analysis_jobs
WHERE video_match_id = :match_id
ORDER BY created_at, id;
```

Pass requires an actual CV job with worker/start/completion evidence and `status='succeeded'`; the model supplies these fields and status vocabulary. (`B/src/models/video.py:38`; `:160`)

In `/admin/video/<match-id>`:

- Review real tracklets and bind only identities supported by footage.
- Confirm own-team identity.
- Queue `/admin/video/matches/<match-id>/analyze`.
- Require a succeeded `qwen_analysis` job from this sample.
- Finalize using `/admin/video/matches/<match-id>/finalize`.
- Open the manager report and reel, including playback.

The analysis endpoint requires completed CV artifacts; tagging accepts explicit bindings; finalization generates reports and records honest low/no-coverage cases. (`B/src/routes/video.py:393`; `:503`; `:568`; `:597`)

```bash
curl -sS --fail -H "Authorization: Bearer $PILOT_MANAGER_TOKEN" \
  "$PILOT_API/club/$PILOT_PROGRAM_ID/matches/$PILOT_MATCH_ID/report" \
  -o "$PILOT_EVIDENCE/report.json"

curl -sS --fail -H "Authorization: Bearer $PILOT_MANAGER_TOKEN" \
  "$PILOT_API/club/$PILOT_PROGRAM_ID/matches/$PILOT_MATCH_ID/reel" \
  -o "$PILOT_EVIDENCE/reel.json"
```

Before finalization, report must return 409 `Report is not finalized`. Cross-club paths must deny. (`B/src/routes/club.py:1383`; `:1512`)

**7. Record the actual outcome**

Pass requires:

- Coach confirms at least one observation useful for a real review.
- Unsupported observations remain withheld.
- No private brief or footage appears on the public player page.
- Measured founder minutes, processing duration, GPU seconds, cost basis, quota remaining, and agreed turnaround.
- Failure/requeue handling demonstrated on synthetic data, not by corrupting the real sample.
- Named owner for failed jobs and permission withdrawals.

Current quota counts all match rows for the program; unsuccessful attempts also consume that count. Inspect before promising another upload. (`B/src/routes/club.py:1222`)

**Authorization matrix**

| Actor | Permitted | Denied |
|---|---|---|
| Approved current manager | Own program’s private console | Other programs; admin tagging/processing |
| Founder with admin credentials | Verification and concierge processing | Impersonating participant actions for measurement |
| Pending/revoked manager | Public surfaces | Private console and media grants |
| Player/scout/supporter | Their existing authorized product surfaces | Club raw film, briefs, reports, or reels |

**Fences and delivery**

No software changes or package commit. Operator records only: candidate SHA, schema head, sim results, permission references, account/subject register, redacted status checks, sample job IDs, human review decision, costs, and next review date. Production bulk resync is outside this runbook. (`docs/agents/invariants.md:61`)

**Decisions made for the owner**

- First sample is concierge and adult-facing.
- Billing is independent.
- A failed permissions, identity, processing, or usefulness gate pauses real onboarding; software rehearsal may continue.
- Rehearsal success and real-sample success are recorded separately.

**Top risks**

1. **Synthetic output mistaken for delivery:** require real worker/job and footage evidence.
2. **Uncleared footage:** permission reference and viewers recorded before upload.
3. **Technically successful but useless review:** coach usefulness is a pass criterion.

**Pre-apply DDL note:** none.

## P1

**Goal and non-goals**

Produce an admin-only, reproducible report for a declared cohort and observation window. Count distinct people performing qualifying actions, later-week use, cross-person outcomes, and the continuation decision separately. No general analytics dashboard, identity inference, or persistent in-app register editor.

**Data model**

None; **no migration**.

Use an admin-posted JSON register. The operator freezes it before counting, records its SHA-256 and declaration time, and uploads it again for each report. Browser state is memory-only; no localStorage persistence.

This avoids a new personal-data store and a wave-1 migration. The report must say that pre-declaration and person/account reconciliation are operator-verified, not database-enforced.

Existing sources include claims, result entries, watchlists, fan follows, and contact outcomes. (`B/src/models/showcase.py:147`; `B/src/models/player_match_entry.py:16`; `B/src/models/scout_watchlist.py:12`; `B/src/models/player_fan.py:12`; `B/src/models/contact.py:246`)

**API contract**

Extend `events_bp`:

```http
POST /api/admin/pilot-cohort/report
@require_api_key
@limiter.limit("6 per minute")
@limiter.limit("30 per hour")
```

Limit by authenticated admin email, internally; never return it.

```json
{
  "schema_version": 1,
  "cohort_id": "one-club-pilot",
  "declared_at": "2026-09-05T00:00:00Z",
  "program_id": 7,
  "window": {
    "start": "2026-09-05T00:00:00Z",
    "end": "2026-10-05T00:00:00Z"
  },
  "participants": [
    {
      "person_key": "p01",
      "primary_role": "player",
      "user_account_ids": [101],
      "player_api_ids": [-42],
      "own_account_verified": true,
      "excluded": false
    }
  ],
  "excluded_user_account_ids": [1, 2],
  "observations": [
    {
      "id": "obs01",
      "person_key": "p01",
      "kind": "self_operated_action",
      "occurred_at": "2026-09-12T10:00:00Z",
      "record_type": "player_match_entry",
      "record_id": "123",
      "evidence_ref": "cycle-2-review-01"
    }
  ],
  "continuation": {
    "decision": "not_discussed",
    "occurred_at": null,
    "evidence_ref": null
  }
}
```

Rules:

- Maximum 50 people, 100 accounts, 100 subjects, 500 observations, 256 KiB request, 90-day window.
- `person_key`, observation ID, cohort ID, and evidence reference: bounded opaque identifiers; no names, emails, documents, URLs, or message bodies.
- Primary role: `staff|player|scout|supporter`. Additional accounts for the same person belong in that same row.
- An account appearing under two people is a 400 error.
- Exclusions override every other field. Configured review accounts are also excluded using `_review_account_is_configured`. (`B/src/auth.py:104`)
- Window is `[start,end)` in UTC. Declaration must be no later than its start.
- Hash the canonical register portion independently of observations and continuation. Return that hash; changing membership creates a new declared register.
- Observations cannot create a missing database action. They corroborate who operated an action or supply facts the application does not record.
- Allowed observation kinds: `self_operated_action`, `scout_discovery`, `supporter_update_view`, `cross_person_outcome`, `staff_review`.
- Allowed record types: fixed implementation allowlist only—never arbitrary table names or SQL.

Response:

```json
{
  "schema_version": 1,
  "register_sha256": "<hex>",
  "generated_at": "<UTC>",
  "capabilities": {
    "relationships": false,
    "feedback": false,
    "stable_results": false
  },
  "summary": {
    "qualifying_people": 0,
    "by_role": {"staff": 0, "player": 0, "scout": 0, "supporter": 0},
    "repeat_people": 0,
    "repeat_staff": 0,
    "repeat_players": 0,
    "repeat_target_met": false
  },
  "participants": [
    {
      "person_key": "p01",
      "primary_role": "player",
      "qualified": false,
      "eligible_now": true,
      "qualified_at": null,
      "action_dates": [],
      "repeat_dates": [],
      "evidence": [],
      "missing": ["accepted_relationship"]
    }
  ],
  "cross_person_outcomes": [],
  "continuation": {"decision": "not_discussed", "evidence_basis": "operator"},
  "warnings": ["relationships_not_installed"]
}
```

Each evidence item contains only `kind`, `record_type`, `record_id`, `occurred_at`, and `basis: database|operator_correlated`. Never serialize source rows wholesale.

**Counting rules**

| Role | Qualification |
|---|---|
| Staff | Strict approved-program manager; own-account-verified real club result or published feedback, corroborated as self-operated |
| Player | Own approved `player` claim, accepted P2 relationship for the registered program, then own `source='self'` game or explicit P3 acknowledgment |
| Scout | Approved scout verification; operator-correlated discovery plus persisted watchlist save of a registered adult player |
| Supporter | Persisted fan follow plus operator-correlated later view of an actual update |
| Any | Excluded/test/founder-operated evidence never qualifies |

Repeat use requires another qualifying role action at least seven days after the person’s first qualifying action, on a different UTC date. The target is at least one staff member and three players. Merely accepting a relationship again, editing a register, or loading a report is not repeat use.

Count a person once overall and under their declared primary role. A feedback revision and acknowledgment pair counts as one outcome, not one per HTTP request. Contact outcomes must join the registered subject and genuine counterpart; return stage and IDs, never notes.

**Measurement limitation that must appear in the UI:** `track.js` sends no Authorization header, and `profile_view` explicitly removes identity even if one was supplied. Named return use cannot be reconstructed from these events. (`W/src/lib/track.js:113`; `B/src/routes/events.py:95`)

P1 uses schema inspection and fixed reflected-table adapters for P2/P3/P4. Missing tables or required columns yield `capabilities=false` and missing milestones; no imports of not-yet-existing modules and no “zero adoption” interpretation of unavailable functionality.

Errors:

- 400 `invalid_register`, `invalid_window`, `duplicate_account`, `invalid_observation`.
- 413 `register_too_large`.
- 422 `cohort_reference_invalid` for an unknown program or unresolved supplied references.
- 429 common rate error; 500 `cohort_report_failed`.
- Existing admin-auth errors unchanged.

Read-only operation: no application records, ProductEvents, or report snapshots written. Repeating the request cannot change milestones.

**Authorization matrix**

Only dual-authenticated admins can submit/read the report. Ordinary staff, claimants, scouts, supporters, wrong-club managers, and anonymous users receive admin-auth denial. An admin cannot turn an excluded account, missing action, minor/suppressed subject, or unresolved identity into a database-qualified participant.

**Web and analytics**

Add **new** `W/src/pages/admin/AdminPilotCohort.jsx`, embedded in `AdminTools.jsx`.

States and copy:

- Empty: “Upload the register declared before the pilot.”
- Loading: “Checking registered actions…”
- Missing capabilities: “Relationship/feedback evidence is not available yet.”
- Denied: “Admin access required.”
- Error: “The report could not be generated. Your register has not been saved.”
- Report: “Qualifying people”, “Later-week use”, “Cross-person outcomes”, “Paid continuation”.
- Disclosure: “Observed outside the app” on operator evidence; “This report contains account references. Store it privately.”

Download register and report as JSON through browser memory, without server persistence.

P1 adds one `pilot_ui` ingestion branch to `events.py`. It stores only allowlisted `{package,action,outcome}` enums; set user email, path, referrer, and session ID to null. All packages call existing `track('pilot_ui', …)`. This instrumentation is diagnostic and **never qualifies participation**. Existing ingestion otherwise remains unchanged. (`B/src/routes/events.py:24`; `W/src/lib/track.js:166`)

P1 actions: `report_requested`, `report_completed`, `report_failed`.

**Checker tests**

New `B/tests/test_pilot_cohort.py`:

- `test_duplicate_accounts_cannot_inflate_people`
- `test_exclusions_override_database_and_observations`
- `test_registration_and_anonymous_views_do_not_qualify`
- `test_operator_observation_cannot_invent_database_action`
- `test_actor_subject_program_and_window_must_all_match`
- `test_seven_day_repeat_boundary_and_primary_role_counting`
- `test_missing_future_tables_are_capability_gaps`
- `test_future_table_adapters_use_exact_contract_columns`
- `test_deleted_revoked_minor_and_suppressed_subjects_do_not_qualify`
- `test_report_contains_no_private_bodies_names_emails_or_tokens`
- `test_admin_auth_precedes_rate_limit`
- `test_pilot_ui_drops_identifiers_and_unknown_properties`

New `W/e2e/pilot-cohort.spec.mjs`: upload, validation, capability gaps, download, denied access, server failure, no browser persistence, mobile layout.

Run existing `B/tests/test_events.py` if present at implementation time; otherwise locate the existing events suite without adding it to the edit fence.

**Exact file fence**

- `B/src/routes/events.py`
- **new** `B/src/services/pilot_cohort.py`
- **new** `B/tests/test_pilot_cohort.py`
- `W/src/pages/admin/AdminTools.jsx`
- **new** `W/src/pages/admin/AdminPilotCohort.jsx`
- **new** `W/e2e/pilot-cohort.spec.mjs`

One commit: `feat(admin): report declared pilot cohort actions`.

**Decisions made for the owner**

- Posted JSON, no register table or in-app persistence.
- Operator corroboration is explicit rather than inferred from anonymous telemetry.
- Reports are current-state snapshots; revoked/deleted prerequisites can reduce later counts.
- P1 understands later schemas without depending on their deployment.

**Top risks / mitigation**

1. Inflated participation → person reconciliation, exclusions, evidence joins.
2. Fabricated retention from views → operator-labelled return evidence.
3. Private-content leakage → explicit narrow serializers and sentinel tests.

**Account export/erasure:** no new persisted personal data; existing telemetry erasure remains unchanged. (`B/src/services/account.py:550`)

**Pre-apply DDL note:** none.

## P2

**Goal and non-goals**

Let an existing approved adult claimant explicitly accept a club relationship, including a player-created local identity. Separately allow a moderated local contract attestation to select that club for included contact routing. No account creation/handover, invitation email automation, public affiliation creation, or automatic approach consent.

**Data model**

Migration: **new** `B/migrations/versions/s4a1_club_invitations.py`.

```text
revision = "s4a1"
down_revision = "s3e1"
```

New `club_invitations`:

| Column | Contract |
|---|---|
| `id` | String(36), UUID PK |
| `program_id` | Integer FK `club_programs.id`, CASCADE, required |
| `player_api_id` | Signed logical integer, required, nonzero |
| `claim_id` | FK `player_profile_claims.id`, required |
| `recipient_user_id` | FK `user_accounts.id`, required |
| `created_by_user_id` | FK `user_accounts.id`, nullable for P3 erasure |
| `source_manager_claim_id` | FK `club_program_claims.id`, nullable, SET NULL |
| `client_request_id` | String(36), UUID, required |
| `request_hash` | String(64), required |
| `status` | `pending|accepted|declined|revoked|expired`, required |
| `created_at`, `expires_at` | Naive UTC, required |
| `responded_at`, `revoked_at` | Naive UTC, nullable |

Constraints/indexes:

- Unique `(program_id, created_by_user_id, client_request_id)`.
- Partial unique `(program_id, player_api_id)` for `status IN ('pending','accepted')`, with both SQLite and PostgreSQL predicates.
- Index `(recipient_user_id,status,created_at,id)`.
- Index `(program_id,status,created_at,id)`.
- Checks for status, nonzero subject, expiry after creation.
- RLS enabled, no policies.

Add to `club_roster_members`:

- `accepted_invitation_id`: nullable FK `club_invitations.id`, SET NULL, indexed.
- `requires_player_acceptance`: Boolean, non-null, default false.
- A member with `requires_player_acceptance=true` and no effective linked invitation is unavailable. Losing an FK must never restore legacy access.

Existing claim and profile tables already contain approved and pending contract/program fields; add no duplicate attestation columns. (`B/src/models/showcase.py:187`; `:265`)

Put the new model and request-independent relationship policy helpers in **new** `B/src/models/club_invitation.py`. Helpers accept a session and never commit. Route-specific HTTP wrappers remain in `club.py` and `showcase.py`.

**API contract**

All new routes require `PILOT_CLUB_RELATIONSHIPS_ENABLED=true`, checked after authentication/authority and before limiting. Disabled returns 404 `not_found`.

Manager routes:

```text
POST /api/club/<program_id>/invitations
GET  /api/club/<program_id>/invitations
POST /api/club/<program_id>/invitations/<uuid>/revoke
```

Decorator order: `require_club_manager()` → feature gate → limiter. That decorator already includes user authentication. (`B/src/services/club_registry.py:171`)

Limits: create 20/hour per manager/program; revoke 30/hour; list 60/minute.

Create:

```json
{"player_api_id":-42,"client_request_id":"<uuid>"}
```

The server resolves a public adult subject and chooses the newest approved `relationship_type='player'` claim by `reviewed_at DESC,id DESC`, matching the existing contact target ordering. Pin both claim and recipient; never accept a caller-supplied recipient email/user ID. (`B/src/routes/contact.py:252`)

Return 201:

```json
{
  "invitation": {
    "id": "<uuid>",
    "program_id": 7,
    "program_name": "Club name",
    "player_api_id": -42,
    "claim_id": 123,
    "status": "pending",
    "created_at": "<UTC>",
    "expires_at": "<UTC>",
    "responded_at": null,
    "roster_member_id": null
  },
  "share_path": "/players/-42#club-invitation=<uuid>"
}
```

The link is navigation, **not a bearer capability**. It grants nothing without the pinned claimant’s account. No invitation ID in query parameters or telemetry.

Player routes:

```text
GET  /api/me/club-invitations?player_api_id=<signed>&limit=20&before=<uuid>
POST /api/me/club-invitations/<uuid>/accept
POST /api/me/club-invitations/<uuid>/decline
POST /api/me/club-invitations/<uuid>/revoke
```

Decorator order: `require_user_auth` → pinned-recipient/resource authority wrapper → feature gate → limiter. Lists scope to the authenticated recipient before pagination. Limits: list 60/minute; decisions 20/hour/account.

Bodies: `{}` only. Response: `{"invitation":{...}}`.

Lists return `{"invitations":[...],"next_before":null}`; limit 1–50, ordered newest first by `(created_at,id)`.

**State and transaction rules**

- Expiry: seven days after creation, checked using `now >= expires_at`; no extension on retries.
- Create replay with the same request ID and canonical payload returns 200 with the same invitation; changed payload returns 409 `client_request_id_reused`.
- A different request ID cannot create another pending/accepted invitation for the program/subject: 409 `invitation_exists`.
- Expired pending rows transition to expired under lock before creating a replacement.
- Acceptance is permitted only from pending. Replayed acceptance/decline returns 409 `invitation_already_resolved`; it never creates another roster member.
- Acceptance rechecks subject, pinned claim/user, inviter’s current strict grant, source claim, and program standing under locks.
- It creates or reuses the canonical roster member atomically, setting both acceptance fields. A pre-existing provider roster member becomes acceptance-governed.
- It never changes identity creator, claim owner/status, affiliation, contract status, or contact consent.
- Pending invitations from a revoked inviter are unusable. An accepted relationship belongs to the club; another current strict manager may manage it after the original inviter leaves.
- Either claimant or current manager may revoke an accepted relationship. Repeating its revoke returns 200 without another mutation.
- Revocation detaches governed video roster links, removes the acceptance-governed roster member, clears the matching approved/pending local routing-program selection, and closes active `club_included` requests for that exact claim/program with `club_consent_status='declined'`.
- Preserve contract status conservatively; revocation must not assert “free agent”.
- Historical club-result rows remain; acceptance withdrawal is not historical-stat erasure.

Existing removal detaches video roster links, while finalized reports use stored snapshots. P2 must therefore enforce the effective governed relationship in roster/result-player resolution, reel selection, and finalized report selection—not just the roster list. (`B/src/routes/club.py:941`; `:465`; `:621`; `:1390`; `:1521`)

Lock account rows involved in the mutation in ascending ID order, then the recipient claim, program, source grant/claim, invitation, roster, and affected contact rows. Revalidate after locks. Close-contact and message admission serialize on the same contact-request row: update `messaging_is_open` to refresh/lock that row before evaluating its existing state. Preserve request-independent service behavior and caller-owned commits. Existing messaging already requires accepted player consent and, for included routing, granted club consent. (`B/src/services/contact.py:188`)

**Local attestation**

Extend the existing local showcase profile PUT and admin profile review; preserve unrelated profile-edit behavior.

Accepted local request:

```json
{
  "contract_status": "contracted",
  "club_program_id": 7
}
```

- Requires the exact approved player claimant and an effective accepted relationship with program 7.
- `current_club_name` is derived from the program; do not accept a contradictory display name.
- `free_agent` clears program/name; `unknown` stays conservative.
- Stage fields on `PlayerShowcaseProfile`; approved claim routing remains unchanged until admin approval.
- Approval repeats claimant, subject, relationship, and program checks under locks.
- Reject stale/withdrawn relationship with 409 `club_relationship_required`.
- Local platform belief is unknown; do not call positive-provider status resolution with a null ID.
- Extend owner payload, pending admin listing, review, and response paths to local subjects. Removing only the existing local-field rejection is insufficient. (`B/src/routes/showcase.py:583`; `:1652`; `:2669`; `:5119`)
- `routing_mode_for_claim` resolves local claims through their signed subject and requires the accepted relationship and at least one strict current manager for `club_included`.
- No viable included club uses the existing conservative notified/attestation behavior; never silently choose direct routing.
- Provider routing and provider result authority remain unchanged. An invitation alone does not create a provider affiliation. Reuse `club_has_authority_over_player` / batch equivalent for provider result permission. (`B/src/services/contact.py:173`; `B/src/routes/contact.py:478`; `B/src/services/club_player_authority.py:23`)

Additional errors:

| Status | `error` |
|---|---|
| 400 | `invalid_request` |
| 404 | `player_not_invitable`, `invitation_not_found` |
| 409 | `invitation_exists`, `client_request_id_reused`, `invitation_already_resolved`, `invitation_expired`, `invitation_unavailable`, `club_relationship_required`, `retry_conflict` |
| 500 | `invitation_operation_failed` |

Wrong recipients get neutral 404, including another approved claimant for the same player. Minor, unknown-age, suppressed, merged, or nonpublic subjects get neutral unavailable responses, not identifying details.

**Authorization matrix**

| Actor/state | Invitation/relationship | Local attestation/contact |
|---|---|---|
| Current strict manager of same program | Create/list/revoke | Cannot attest for the player |
| Pinned approved adult player claimant | List/accept/decline/revoke | Stage own attestation |
| Other claimant, agent, guardian, club-official player claim | Denied | Denied |
| Other program or revoked/pending manager | Denied | Cannot grant club consent through this package |
| Expired/replayed invitation | No acceptance | No relationship created |
| Suppressed/minor/unknown-age subject | No new/readable invitation or governed roster access | No new pilot routing |
| Admin | Existing moderation only | No manager/player impersonation bypass |

Revocation removes the individual relationship-derived access; it does not claim to erase the club’s independently authorized shared raw footage.

**Web and analytics**

Change `MyClubConsole.jsx` roster panel:

- “Invite player”; public signed subject selection.
- “Copy invitation link”, “Awaiting player”, “Accepted”, “Expired”, “Revoke relationship”.
- Explain: “The player must accept before this relationship is active.”
- Keep existing private attachment clearly separate.

Change `ShowcaseSection.jsx`:

- Claimant-only “Club invitations”.
- “Accept club relationship”, “Decline”, “Leave club relationship”.
- Copy: “Accepting adds you to this club’s private roster. Contract status and introductions require separate choices.”
- Local contract controls: “Pending review” and “Contact routing updates after approval.”

Handle empty/loading/error/denied/expired/replayed states; discard stale requests on account, subject, or program changes. The component already distinguishes canonical signed game IDs and claimant relationship types. (`W/src/components/ShowcaseSection.jsx:294`; `:698`)

Use `APIService.request` directly; do not edit `api.js`.

`pilot_ui` actions: `invite_created`, `invite_accepted`, `invite_declined`, `relationship_revoked`, `attestation_submitted`; props only package/action/outcome.

**Checker tests**

New `B/tests/test_club_invitations.py`:

- Provider and player-created local acceptance.
- Exact claimant pinning with multiple approved claims.
- Double create, same-ID changed payload, double accept, expiry boundary.
- Revoked inviter before acceptance; second manager after acceptance.
- Hidden/suspended program, wrong program, self-invitation, unknown age, minor, suppression, merged/graduated identity mismatch.
- Existing roster reuse; no claim/affiliation/contract mutation.
- Foreign local attachment remains denied without acceptance.
- Revocation removes report/reel/roster access and closes exact included threads.
- No provider public-stat authority gained through acceptance alone.
- Transaction rollback on roster/contact failure.
- Feature off creates no records.

New `B/tests/test_local_club_attestation.py`:

- Stage → reject/approve; routing changes only after approval.
- Wrong relationship, revoked claim, suppression between submit and review.
- Local `contracted|unknown|free_agent` routing; no null/provider lookup.
- Both player and club consent required before messaging.
- Other program’s messages remain unaffected.
- Provider attestation/contact regression cases.

New `W/e2e/club-invitations.spec.mjs`: manager invite → correct claimant accept; wrong-account denial; duplicate response; local pending/approved attestation; revoke; stale subject/account responses; mobile width.

Run existing `test_club_console.py`, `test_club_result_affiliation.py`, `test_contact.py`, and `test_showcase.py`. PostgreSQL migration validation is mandatory; SQLite alone does not establish concurrent acceptance exclusion.

**Exact file fence**

- `B/src/routes/club.py`
- `B/src/routes/showcase.py`
- `B/src/services/contact.py`
- `B/src/models/funding.py`
- `B/src/models/showcase.py`
- **new** `B/src/models/club_invitation.py`
- **new** `B/migrations/versions/s4a1_club_invitations.py`
- **new** `B/tests/test_club_invitations.py`
- **new** `B/tests/test_local_club_attestation.py`
- `W/src/pages/MyClubConsole.jsx`
- `W/src/components/ShowcaseSection.jsx`
- **new** `W/e2e/club-invitations.spec.mjs`

One commit: `feat(club): add claimant-accepted pilot relationships (s4a1)`.

**Account export/erasure**

P3 implements the hooks before activation:

- Export own sent/received invitation metadata; no bearer/share secrets or unrelated recipient data.
- Delete recipient-owned invitations after dependent feedback and governed roster cleanup.
- On inviter deletion, delete pending invitations; accepted relationships may survive for the club with author/source references cleared.
- Erasure must not leave a governed roster member with legacy privileges.

**Decisions made for the owner**

- Seven-day invitations, manual link sharing, no bearer capability.
- Newest approved self-claim is pinned; another claimant cannot substitute.
- Private acceptance does not publish affiliation or assert a contract.
- Production activation waits for P3 account lifecycle completion.

**Top risks / mitigation**

1. Consent concepts collapse → separate state transitions and explicit copy.
2. Revocation leaves snapshot access → report/reel/roster checks plus contact closure.
3. Deletion fails on new FKs → default-off release and mandatory P3 integration.

**Pre-apply DDL note**

Online-upgrade disposable PostgreSQL from `s3e1` to `s4a1`; inspect fresh, fully pre-applied, and partially pre-applied schemas. Dump verified DDL for `club_invitations`, the two roster columns, FKs, checks, indexes, and RLS. Pre-apply before merge; stamp `s4a1` after deployment. Keep the feature disabled throughout.

## P3

**Goal and non-goals**

Deliver separately authored private feedback to the exact accepted adult claimant and record explicit acknowledgment of a published revision. No raw analysis, coach/system brief projection, player access to match/reel media, replies, email notifications, or native inbox.

The coach’s brief is existing private analysis input, including roster-linked presentation; it is not this feedback record. (`B/src/routes/club.py:899`; `W/src/components/video/PlayerReel.jsx:158`)

**Data model**

Migration: **new** `B/migrations/versions/s4b1_player_feedback.py`.

```text
revision = "s4b1"
down_revision = "s4a1"
```

New `player_feedback` stores one immutable row per published revision:

- `id`: UUID String(36), PK.
- `thread_id`: UUID String(36), required.
- `revision`: Integer ≥1.
- `program_id`: FK club program, required.
- `invitation_id`: FK P2 invitation, required.
- `claim_id`, `recipient_user_id`: required FKs, pinned.
- `player_api_id`: required signed logical ID snapshot.
- `author_user_id`: nullable user FK, SET NULL after explicit erasure handling.
- `video_match_id`: nullable FK video match, SET NULL.
- `title`: String(140), required.
- `body`: Text, required, sanitized plain text, 1–4,000 characters.
- `observation_refs`: generic JSON, default `[]`; at most ten `{label,timestamp_s}` items, label 1–160 characters, timestamp null or finite nonnegative number.
- `client_request_id`: UUID String(36), required.
- `request_hash`: String(64), required.
- `published_at`: required naive UTC.
- `acknowledged_at`: nullable naive UTC.
- `withdrawn_at`: nullable naive UTC.
- `audit_expires_at`: nullable naive UTC.

Constraints/indexes:

- Unique `(thread_id,revision)`.
- Unique `(program_id,client_request_id)`.
- Index `(recipient_user_id,published_at,id)`.
- Index `(invitation_id,thread_id,revision)`.
- Check revision positive and signed subject nonzero.
- RLS, no policies.

No server-side drafts. Text is immutable after publication; correction creates a new revision. Acknowledgment applies to one revision only.

**API contract**

New `feedback_bp`, registered in `main.py` under `/api`; do not add feedback endpoints to `club.py`.

Manager:

```text
POST /api/club/<program_id>/player-feedback
GET  /api/club/<program_id>/player-feedback?invitation_id=<uuid>&limit=20&before=<uuid>
POST /api/club/<program_id>/player-feedback/<thread_uuid>/revisions
POST /api/club/<program_id>/player-feedback/<thread_uuid>/withdraw
```

`require_club_manager()` → feedback authority wrapper → limiter. Publish/revise: 30/hour; withdraw: 30/hour; list: 60/minute.

Initial publication:

```json
{
  "invitation_id": "<accepted-invitation-uuid>",
  "client_request_id": "<uuid>",
  "title": "Receiving under pressure",
  "body": "Coach-authored feedback.",
  "video_match_id": 41,
  "observation_refs": [{"label": "First-half receiving position", "timestamp_s": 315}]
}
```

Server derives program, claimant, recipient, subject, author, revision, and publication time. Reject caller-supplied identity/publication/acknowledgment fields.

A video reference must belong to the same program, be finalized, and have a roster subject matching the recipient. It remains a textual reference; no URL/token is returned. Finalized status and report snapshots are existing explicit seams. (`B/src/routes/club.py:1512`; `B/src/routes/video.py:612`)

Revision request includes the same authored fields plus `expected_revision`; recipient and invitation cannot change. Withdrawal body: `{"expected_revision":2}`.

Player:

```text
GET  /api/me/player-feedback?player_api_id=<signed>&limit=20&before=<uuid>
GET  /api/me/player-feedback/<revision_uuid>
POST /api/me/player-feedback/<revision_uuid>/acknowledge
```

`require_user_auth` → exact recipient/effective-relationship authority wrapper → limiter. Reads 60/minute; acknowledgment 30/hour. Acknowledge body `{}` only.

Detail response:

```json
{
  "feedback": {
    "id": "<revision-uuid>",
    "thread_id": "<uuid>",
    "revision": 2,
    "program": {"id": 7, "name": "Club name"},
    "player_api_id": -42,
    "title": "Receiving under pressure",
    "body": "Coach-authored feedback.",
    "observation_refs": [{"label": "First-half receiving position", "timestamp_s": 315}],
    "author": {"display_name": "Coach"},
    "published_at": "<UTC>",
    "acknowledged_at": null,
    "can_acknowledge": true
  }
}
```

Player payload excludes claim IDs, recipient account IDs, source manager claims, roster notes, briefs, `capture_meta`, raw Qwen output, tracklet/report IDs, blob paths, media tokens, and video URLs. Manager payload may additionally expose pinned IDs and acknowledgment status.

Lists return latest nonwithdrawn revision per thread and `next_before`; no body in list summaries. Manager lists may include a withdrawn metadata stub.

**Lifecycle and locking**

- Publishing requires an effective accepted P2 relationship and current public-adult eligibility, checked again under lock.
- Lock relevant account rows, pinned player claim, program/grants, invitation, then thread rows in deterministic order.
- Same create/revision request ID and canonical payload returns the existing revision, 200; different payload returns 409 `client_request_id_reused`.
- Revision number is allocated while holding the invitation/thread lock; unique constraint is the final guard.
- Stale `expected_revision` returns 409 `feedback_revision_conflict`, with current revision number only.
- Acknowledgment sets `acknowledged_at` once using conditional update; retries return the original timestamp.
- Only the latest revision can be newly acknowledged. Publishing revision 2 does not erase revision 1’s acknowledgment and does not mark revision 2 acknowledged.
- Withdrawal marks the whole thread withdrawn. It cannot be reopened; a later publication requires a new thread.
- Revoked claim/relationship, suppression, loss of adult eligibility, or unavailable program denies subsequent player reads and acknowledgments, including by direct revision ID.
- A different claim for the same subject cannot inherit prior feedback.
- Losing the original author’s grant denies that author manager access, but does not erase properly published club feedback while the relationship and another strict manager remain valid.
- Closed-access records are administrative audit only. `audit_expires_at` is set to 30 days after closure when observed by the feedback service or withdrawal operation; expired audit records are purged by the operator endpoint below. Account erasure takes precedence.

Operator cleanup:

```text
POST /api/admin/player-feedback/purge
@require_api_key → limiter("1 per hour")
{"dry_run":true}
```

Scan bounded batches of 500. Detect no-longer-effective relationships, set closure deadlines when absent, and delete expired closed-access rows when `dry_run=false`. Return counts and next cursor, never bodies. The P0 operator runs it weekly and records counts; do not promise automatic scheduled retention.

Errors:

- 400 `invalid_request`.
- 404 `feedback_not_found` for wrong claimant/program, suppression, or hidden content.
- 409 `club_relationship_required`, `feedback_revision_conflict`, `feedback_withdrawn`, `client_request_id_reused`, `feedback_reference_unavailable`, `retry_conflict`.
- 500 `feedback_operation_failed`.
- Existing auth/manager errors and common 429.

**Authorization matrix**

| Actor/state | Publish/manage | Read/acknowledge |
|---|---|---|
| Current manager, same program | Publish/revise/withdraw for accepted adults | Manager view; cannot acknowledge |
| Exact pinned adult claimant | No | Own accessible revisions; latest acknowledgment |
| Different claimant/account or other club | No | Neutral 404 |
| Revoked manager | No manager access | No author-based bypass |
| Revoked relationship/claim, minor, suppressed | No new feedback | No player detail, list body, or acknowledgment |
| Admin | Purge and restricted audit operations | No participant impersonation |

**Account export/erasure — mandatory activation gate**

Extend `account.py`:

- Export P2 invitation metadata for the caller.
- Export received feedback only through the same current authorization predicate as the inbox. Do not use account export to bypass revocation.
- Export authored feedback only while the caller still has the relevant manager authority. Otherwise return author-owned metadata without recipient/body disclosure.
- Recipient deletion: delete their feedback revisions, detach/delete their governed roster relationships, then delete their invitations before claims/account deletion.
- Author deletion: preserve feedback for its legitimate recipient/club, set author to null and display “Former club staff”; remove any cached author display identity. No copied author email in the feedback table.
- Pending invitation creator deletion deletes pending invites. Accepted club relationships survive only with another strict manager and cleared author/source references; otherwise become ineffective.
- Clear or classify the existing actor FKs reached by the pilot too: roster `added_by_user_id`, brief authors, video processing requester, and local-player creator. Do not add new unclassified-FK exemptions globally. Nullable authors become null; retained non-null club-owned roster actor references use the existing tombstone mechanism, with authored private notes/briefs scrubbed.
- Public sports identity retention remains separate from private feedback erasure; a local creator reference must not prevent deleting the account. Existing local identities have a nullable creator FK. (`B/src/models/showcase.py:76`)
- Add schema-aware P4 hooks now: export `club_result_id` when present; export result headers attributable to the caller; clear nullable `club_results.created_by_user_id` and `updated_by_user_id` before the exhaustive FK check. When P4’s table/column is absent, skip without error.
- Every operation remains inside the account service’s transaction; inject a failure and prove full rollback.

The existing export explicitly serializes match fields and applies current authorization to received contact data; extend that approach rather than dumping model dictionaries. (`B/src/services/account.py:177`; `:234`; `:347`)

**Web and analytics**

- `MyClubConsole.jsx`: “Publish feedback” on eligible roster members; empty text form, never prefilled from briefs/analysis; confirmation preview, publication history, “Publish correction”, “Withdraw feedback”.
- **New** `W/src/components/showcase/PlayerFeedbackInbox.jsx`, mounted by `ShowcaseSection.jsx` for the authenticated player claimant.
- Inbox and detail live on the player’s profile, including mobile web.
- Copy: “Private feedback from your club”, “I’ve read this feedback”, “Acknowledged”, “Updated feedback — please read again”.
- Disclosure: “Acknowledging confirms you read this revision; it does not mean you agree.”
- Empty: “Your club has not published feedback yet.”
- Denied/withdrawn: “This feedback is no longer available.”
- Errors retain draft text only in mounted component memory; never persist private text in localStorage.
- Abort/ignore stale requests and clear text on logout, subject change, or revoked access.

`pilot_ui` actions: `feedback_published`, `feedback_opened`, `feedback_acknowledged`, `feedback_withdrawn`; no IDs or authored text.

**Checker tests**

New `B/tests/test_player_feedback.py`:

- `test_exact_claimant_only_even_with_second_approved_claim`
- `test_publish_does_not_project_private_analysis_sentinels`
- `test_video_reference_requires_same_program_and_subject`
- `test_publish_replay_and_changed_payload_conflict`
- `test_revisions_are_immutable_and_acknowledgments_are_revision_scoped`
- `test_stale_revision_and_concurrent_revision_predicate`
- `test_withdrawal_claim_revocation_suppression_and_minor_denial`
- `test_revoked_author_cannot_read_through_export`
- `test_author_deletion_preserves_recipient_feedback_without_identity`
- `test_recipient_deletion_removes_feedback_and_relationships`
- `test_purge_dry_run_and_retention_boundary`
- `test_account_failure_rolls_back_every_pilot_change`

Extend `B/tests/test_account.py` with actual player-created local and manager accounts, invitations, roster briefs, feedback, and the P4 optional-schema adapter. Use FK-enforced SQLite; also verify the migrated PostgreSQL schema.

New `W/e2e/player-feedback.spec.mjs`: publish → exact player inbox → acknowledge → correction → new acknowledgment; revoked/withdrawn direct detail; private sentinel absent from DOM and responses; mobile layout; logout during delayed request.

**Exact file fence**

- **new** `B/src/routes/feedback.py`
- **new** `B/src/models/player_feedback.py`
- `B/src/main.py` — import/register `feedback_bp` only
- **new** `B/migrations/versions/s4b1_player_feedback.py`
- `B/src/services/account.py`
- **new** `B/tests/test_player_feedback.py`
- `B/tests/test_account.py`
- `W/src/pages/MyClubConsole.jsx`
- `W/src/components/ShowcaseSection.jsx`
- **new** `W/src/components/showcase/PlayerFeedbackInbox.jsx`
- **new** `W/e2e/player-feedback.spec.mjs`

One commit: `feat(feedback): publish private player revisions and acknowledgments (s4b1)`.

**Decisions made for the owner**

- Plain text, immutable revisions, no server drafts.
- Acknowledgment means read, not agreement.
- Revocation denies future player reads.
- No player media access.
- This package completes account lifecycle for P2 and prepares P4, allowing P2 activation.

**Top risks / mitigation**

1. Private analysis leaks → separately authored input and allowlisted payloads.
2. Wrong person inherits feedback → immutable claim/user binding.
3. Erasure or revocation bypass → shared authorization, explicit deletion order, rollback tests.

**Pre-apply DDL note**

Upgrade disposable PostgreSQL `s4a1→s4b1`; verify table, FKs, uniqueness, defaults, indexes, RLS, and repeat/partial application. Dump and pre-apply exact DDL before merge; stamp after deployment. Enable relationships only after both P2 and P3 production smoke checks and account lifecycle verification succeed.

## P4

**Goal and non-goals**

Give each club result a stable identity, persisted optional video association, complete lineup replacement, and versioned correction/deletion. Refresh old and new seasons atomically. No fixture scheduling, multi-match aggregation, automatic identity merging, or changes to self-reported game ownership.

The current POST groups by date/opponent, leaves omitted players, and only echoes its video association. Existing confirmed rows already retain entry-time authority. (`B/src/routes/club.py:959`; `:1024`; `:1061`; `:1077`)

**Data model**

Migration: **new** `B/migrations/versions/s4c1_club_results.py`.

```text
revision = "s4c1"
down_revision = "s4b1"
```

Define `ClubResult` alongside `PlayerMatchEntry` in `B/src/models/player_match_entry.py`.

New `club_results`:

- `id`: UUID String(36), PK.
- `program_id`: required FK club program.
- `client_request_id`: required String(36).
- `create_request_hash`: required String(64), immutable.
- `version`: required Integer, default 1, positive.
- `match_date`: required Date.
- `season`: required Integer, server-derived.
- `opponent`: String(120), required.
- `opponent_key`: String(120), required; sanitize, trim, then Python lowercase.
- `competition`: nullable String(120).
- `home_away`: required `home|away|neutral`.
- `result_for`, `result_against`: required integers 0–20.
- `video_match_id`: nullable FK video match, SET NULL.
- `created_by_user_id`, `updated_by_user_id`: nullable user FKs, SET NULL.
- `created_at`, `updated_at`: required naive UTC.
- `deleted_at`: nullable naive UTC.

Constraints/indexes:

- Unique `(program_id,client_request_id)`.
- Unique `(id,program_id)` for the child composite FK.
- Partial unique `(program_id,match_date,opponent_key)` where `deleted_at IS NULL`.
- Index `(program_id,season,match_date,id)`.
- Index on `video_match_id`.
- Named enum/count/version checks.
- RLS enabled, no policies.

Add `player_match_entries.club_result_id`, nullable String(36), indexed:

- Composite FK `(club_result_id,club_program_id) → club_results(id,program_id)`.
- Unique `(club_result_id,player_api_id)`.
- Check: a non-null result ID requires `source='club'` and a non-null program.
- Keep existing self-game uniqueness and checks unchanged. Existing fields and uniqueness are at `B/src/models/player_match_entry.py:17`.

`club_result_id` stays nullable for old binaries during pre-apply and self rows. The deployed P4 writer must never create an unlinked club row.

**Legacy adoption**

The migration contains a separately callable, idempotent `backfill_legacy_results(bind)` using Core SQLAlchemy and no application imports.

- Group non-null-program club rows by program/date/normalized opponent.
- Require consistent season/header values and at most one row per player.
- Inconsistent headers, duplicate player lines, or null-program club rows produce a bounded diagnostic and stop adoption; do not choose arbitrary winners.
- Generate deterministic UUIDv5 result IDs from the group key and a fixed namespace defined in the migration.
- Keep all entry IDs, reporters, statuses, stats, and timestamps.
- Video association is null: the existing implementation did not persist it. Do not infer it from date/opponent.
- Set `version=1`; do not emit new activity or move rollups.
- Repeat adoption produces no changes.
- The orchestrator pauses club-result submissions during final adoption/deploy and checks again for orphan club rows before reopening.

**API contract**

Existing `/club/<program>/results` becomes the stable result API:

```text
POST   /api/club/<program_id>/results
GET    /api/club/<program_id>/results?season=2026&limit=20&before=<uuid>
GET    /api/club/<program_id>/results/<uuid>
PUT    /api/club/<program_id>/results/<uuid>
DELETE /api/club/<program_id>/results/<uuid>
```

All: `require_club_manager()` → resource authority → limiter. Reads 60/minute; writes 30/hour/account/program.

Create:

```json
{
  "client_request_id": "<uuid>",
  "match_date": "2026-09-05",
  "opponent": "Riverside",
  "competition": "League",
  "home_away": "home",
  "result_for": 2,
  "result_against": 1,
  "video_match_id": 41,
  "entries": [
    {
      "club_roster_member_id": 51,
      "minutes": 80,
      "goals": 1,
      "assists": 0,
      "yellows": 0,
      "reds": 0,
      "saves": null,
      "goals_conceded": null,
      "note": null
    }
  ]
}
```

Reuse existing header/count validation: date ≥1970 and no later than tomorrow UTC; opponent/competition 120; minutes 0–130; counts 0–20; note 500. Add maximum 100 lineup entries and reject duplicates after canonical subject resolution. (`B/src/routes/club.py:335`; `:362`; `:382`)

PUT has the full header, `expected_version`, and a **complete replacement** `entries` array:

- Existing line: `{"entry_id":123,...complete stats...}`.
- New line: `{"club_roster_member_id":51,...complete stats...}`.
- Exactly one identity field per line.
- Existing entry ID must belong to this result; its player cannot change.
- Omitted lines are deleted.
- At least one line remains; use DELETE for an empty result.
- An existing historical line may be corrected by entry ID after roster departure; a new/re-added line requires current roster/authority.

DELETE body:

```json
{"expected_version":3}
```

Create returns 201; replay 200. PUT returns 200:

```json
{
  "result": {
    "id": "<uuid>",
    "version": 2,
    "program_id": 7,
    "season": 2026,
    "match_date": "2026-09-05",
    "opponent": "Riverside",
    "competition": "League",
    "home_away": "home",
    "result_for": 2,
    "result_against": 1,
    "video_match_id": 41,
    "updated_at": "<UTC>"
  },
  "matches": [],
  "removed_entry_ids": [],
  "refreshed_scopes": [
    {"player_api_id":-42,"season":2025},
    {"player_api_id":-42,"season":2026}
  ],
  "season_stats_by_player": {}
}
```

`matches` uses the existing result-entry serializer, adding `club_result_id`; do not expose a private video association through the public player-match serializer. (`B/src/routes/club.py:643`; `B/src/models/player_match_entry.py:90`)

List preserves `results` and `total`, adding `next_before`; group by stable header ID, never date/opponent. Deleted headers are excluded.

**Idempotency, locking, and authority**

1. Parse and normalize the complete request before mutation.
2. Lock the program using the existing program serialization seam; lock the result header for updates.
3. Resolve the union of existing, removed, and incoming player IDs.
4. Acquire existing result-player advisory locks in sorted signed-ID order. Acquire rollup refresh locks in that same player order before refreshing scopes. Existing services already expose these PostgreSQL lock seams. (`B/src/routes/club.py:689`; `:698`; `B/src/services/season_rollup_service.py:904`)
5. Recheck resource ownership, manager authority, version, affected rows, and collisions after locks.
6. Validate all changes before modifying any header, entry, or rollup.
7. Apply header, line updates/additions/removals; flush.
8. Refresh the union of every old `(player,season)` and new `(player,season)` scope, sorted and deduplicated, in the same transaction.
9. Commit once.

Add a small `refresh_player_scopes(scopes,session)` helper in `season_rollup_service.py`; it calls existing `refresh_player`, never commits, and clears old scopes even when no lines remain. Existing refresh deletes/rebuilds scoped cells and totals inside its caller’s transaction. (`B/src/services/season_rollup_service.py:916`)

Authority rules:

- Existing `club_confirmed` lines retain entry-time authority, including after transfer or season correction.
- New provider additions use `club_has_authority_over_player` / `club_authorized_player_ids` for the **new result season**.
- New local additions require current approved identity and effective P2-governed membership, or the preserved legacy manager-created local rule.
- Removed then re-added players are new additions.
- Never reevaluate current authority while rebuilding historical rollups.
- Never mutate or delete `source='self'` rows.
- Preserve current cross-program protection: another program’s matching date/opponent/player line blocks a conflicting result; check under the same result-player lock. (`B/src/routes/club.py:1035`; `B/src/services/club_player_authority.py:23`)
- New video associations may reference any same-program finalized or editable match, or an expired match retaining derived records. Association does not authorize video mutation or playback. Failed/in-flight foreign references are rejected; an unchanged existing reference can survive normal lifecycle changes.
- Minor/suppressed/unavailable players cannot be newly added or have retained stats edited. Return existing unavailable lines to managers only as `{id,unavailable:true}`. They may remove those lines or delete the whole result; they cannot recover hidden stats through correction.

Replay/version policy:

- Same create key + original normalized input returns current result state, no writes. Different input: 409 `client_request_id_reused`.
- A new create key hitting an existing active fixture slot: 409 `result_already_exists`, with own-program result ID.
- PUT requires the current version; every successful change increments once.
- Repeated/stale PUT returns 409 `result_version_conflict`; it never reapplies.
- DELETE removes club lines and refreshes totals, but retains a tombstone header and create key. Increment version once.
- Exact repeated DELETE against that tombstone returns 200 `{"id":"...","deleted":true,"version":4}`; stale contradictory versions conflict.
- Create replay against a deleted header returns 409 `result_deleted`; never resurrect.

Errors:

| Status | `error` |
|---|---|
| 400 | `invalid_request`, `client_request_id_required` |
| 404 | `result_not_found` |
| 409 | `client_request_id_reused`, `result_already_exists`, `result_version_conflict`, `result_deleted`, `result_identity_conflict`, `video_match_unavailable`, `retry_conflict` |
| 422 | `player_not_affiliated` with sorted `player_api_ids`; `result_player_unavailable` with own-result entry IDs only |
| 500 | `result_operation_failed` |

**Authorization matrix**

| Actor/state | Permission |
|---|---|
| Current manager of owning program | Create/correct/delete under the rules above |
| Second current manager | Same rights; stale versions conflict |
| Revoked/pending manager, other program, ordinary admin without manager grant | Denied |
| Player claimant | Existing self-game APIs only; no club-result mutation |
| Transferred historical player | Existing confirmed line remains correctable |
| New unauthorized provider/local player | Whole request rejected |
| Minor/suppressed retained line | Redacted stub; removal/deletion only |

**Web and analytics**

Extend `MyClubConsole.jsx` result form and history:

- “Results” history within Matches & reports, including results without video.
- “Edit result” loads stable result detail and version.
- Existing unavailable/departed entries remain represented; never rebuild the form solely from the current roster.
- Explicit “Remove from this result” and save-time removal count.
- “Save correction”; “Delete result”.
- Conflict: “Someone changed this result. Reload the latest version before saving.”
- Deletion: “This removes the club-confirmed lines and updates season totals.”
- Persist video association on reload; display “Video unavailable” when the referenced footage is no longer playable.
- Keep a stable create request UUID during retries; generate a new one only for a genuinely new result.
- Clear stale drafts/responses on program/account change.

The existing form always posts through `recordClubResult`; replace that submission choice with create versus versioned PUT using `APIService.request`, without editing the shared API file. (`W/src/pages/MyClubConsole.jsx:897`)

`pilot_ui` actions: `result_created`, `result_corrected`, `result_deleted`, `result_conflict`; no player/result IDs or notes.

**Checker tests**

New `B/tests/test_club_results.py`:

- Date/opponent correction retains IDs and creates no duplicate.
- July/August season move refreshes both old/new scopes.
- Competition youth/senior move clears old level totals.
- Omitted player removed; last-line removal requires DELETE.
- Whole fixture deletion restores underlying self/provider headline selection.
- Existing transferred line editable; unauthorized new/re-added line rejected atomically.
- Same-program second manager; wrong-program entry injection.
- Minor/suppressed stub handling.
- Video association survives reload and lifecycle changes.
- Create replay, changed-key payload, stale PUT, repeated DELETE, no resurrection.
- Failure after line writes or first rollup refresh rolls everything back.
- Legacy adoption repeat, duplicate players, inconsistent headers, null-program rows.
- P3 account hooks export/clear new header references and include entry result IDs.

New **required** `B/tests/test_club_results_postgres.py`:

- Skip only when `PILOT_TEST_POSTGRES_URL` is absent.
- If supplied, refuse nonlocal hosts and non-disposable database names; setup failure is a failure, not a skip.
- Use independent connections/sessions and transaction barriers, not sequential requests described as concurrency.
- Two simultaneous same-key creates → one header and one lineup.
- Two different-key creates in one fixture slot → one success, one conflict.
- Two same-version corrections → one success, one version conflict.
- Correction versus deletion → one coherent final state, no resurrection.
- Two programs entering a conflicting player/date/opponent → one winner.
- Concurrent results sharing a player → no lost season totals.
- Opposite lineup ordering → deterministic locks, no deadlock.
- Forced mid-refresh failure → unchanged header, entries, and both seasons.

The orchestrator must run:

```bash
PILOT_TEST_POSTGRES_URL="$PILOT_DISPOSABLE_SQLALCHEMY_URL" \
  /Users/michaeljones/Projects/loanarmy/.loan/bin/python \
  -m pytest academy-watch-backend/tests/test_club_results_postgres.py -q
```

New `W/e2e/club-result-corrections.spec.mjs`: create without video → reload → date/opponent correction → remove player → delete; associated video reload; stale conflict; departed player; mobile form.

Run existing `test_club_console.py`, `test_club_result_affiliation.py`, and relevant season-rollup tests. Preserve their substantive authority assertions.

**Exact file fence**

- `B/src/routes/club.py`
- `B/src/models/player_match_entry.py`
- `B/src/services/season_rollup_service.py`
- **new** `B/migrations/versions/s4c1_club_results.py`
- **new** `B/tests/test_club_results.py`
- **new** `B/tests/test_club_results_postgres.py`
- `B/tests/test_club_console.py` — expected stable-result API changes only
- `B/tests/test_club_result_affiliation.py` — request-shape updates only; preserve authority assertions
- `W/src/pages/MyClubConsole.jsx`
- **new** `W/e2e/club-result-corrections.spec.mjs`

One commit: `feat(club): support stable result corrections and deletion (s4c1)`.

**Account export/erasure**

Use P3’s already-landed schema-aware hooks. Result headers remain club-owned; nullable actor references are cleared on account deletion. Existing reported club lines retain the established tombstone policy, while self lines retain existing deletion behavior. No new body/history store is introduced. (`B/src/services/account.py:81`; `:858`)

**Decisions made for the owner**

- PUT replaces the entire lineup.
- Historical authority survives corrections; new additions require current authority.
- Optimistic versions reject stale updates; tombstones prevent replay resurrection.
- Existing result adoption is explicit, deterministic, and never guesses a video link.
- Result writes pause during final adoption/deployment.

**Top risks / mitigation**

1. Duplicate/orphan fixtures → stable header, uniqueness, deterministic legacy adoption.
2. Stale totals → old/new scope union inside one transaction.
3. False concurrency confidence → mandatory independent-session PostgreSQL attacks.

**Pre-apply DDL note**

Upgrade disposable PostgreSQL `s4b1→s4c1`, including legacy fixtures. Verify fresh, repeated, and partial DDL plus backfill repeatability.

The orchestrator must separately preserve:

1. Exact verified schema DDL, including the composite FK, partial indexes, and RLS.
2. The validated legacy-adoption invocation and diagnostics.
3. Before/after entry counts, unchanged entry IDs/stat totals, and orphan count.

Pre-apply DDL before merge. **DDL alone is insufficient:** run the migration’s same `backfill_legacy_results(bind)` through an online SQLAlchemy connection without changing `alembic_version`. During the agreed result-write pause, rerun adoption immediately around deployment and require:

```sql
SELECT count(*) AS orphan_club_entries
FROM player_match_entries
WHERE source = 'club' AND club_result_id IS NULL;
```

Expected: zero. Then verify the deployed writer, stamp `s4c1`, and reopen result entry. A rollback keeps additive schema and the write pause; do not resume the old writer against adopted results.

## Open questions for the owner

None block implementation. Recruitment, footage permissions, and the paid-continuation discussion remain P0 operating gates. P2’s production activation waits for P3’s account lifecycle checks; P4 cannot pass without the orchestrator’s disposable-PostgreSQL concurrency run.