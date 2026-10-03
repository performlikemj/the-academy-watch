# Real staging contracts

These JSON files are unedited HTTP response bodies from the isolated synthetic
staging world at https://basecamp.tail37b60.ts.net:15443. `manifest.json` records
request paths, methods, personas, HTTP status and the Swift response type. Login
credentials are never saved. Owner membership is deliberately empty: verified
owners resolve through approved funding claims and `access/me`, while invited
coaches resolve through `me/club-access`.

Refresh reads (preserves previously captured writes/refusals):

```sh
python3 academy-watch-ios/sim/refresh-phase2-contracts.py
```

Refresh the complete contract set, including genuine 422/429 responses:

```sh
python3 academy-watch-ios/sim/refresh-phase2-contracts.py --exercise-writes --capture-rate-limit
```

The explicit write mode creates a labelled synthetic scratch trial and adult
application, publishes it, shortlists/invites/confirms/reschedules, writes a note,
then withdraws the application and closes the post. A second scratch position is created and cancelled.
Editor contracts include edit success, field 422, horizon 422, stale-version 409,
application-lock 409, and the locked private list after submission. It creates and revokes a
synthetic staff invite (staging SMTP sink only). A seeded coach's scope PATCH is
an exact no-op apart from the server version/audit record. DELETE is captured as
a genuine missing-grant refusal rather than removing a seeded user's access.
The app discards successful grant/revoke bodies (`Phase2Empty`); those decoders
and the actual DELETE refusal envelope are covered. Captured cancelled/withdrawn
records remain under the staging retention rules; the script never resets staging.

The rate-limit capture is bounded at 200 requests because staging has three
workers with process-local rate-limit storage. Never use this script against
production. `Phase2ContractTests` decodes every manifest file through the shipped
Swift DTO and sends real error bodies through APIClient's HTTP error parser.
Private date-picker bounds introduced by RI1 use optional `trial_invite_deadline`;
older staging responses omit it, so the client also bounds by application date
and position closing date. The server remains authoritative for the exact window.
