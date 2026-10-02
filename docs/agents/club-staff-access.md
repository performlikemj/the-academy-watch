# Club staff access (Phase 2 · A2) — read before enabling or touching club auth

Dark behind `CLUB_STAFF_ACCESS_ENABLED` (default off). With it off, every club route answers
exactly as it did before (same statuses, same payloads, including HEAD requests); the new
routes return 404.

## The model in one screen

- `club_access_grants` (+ `club_access_grant_squads`) hold invited staff roles; `club_staff_invites`
  hold one-use emailed invites (only the SHA-256 of the token is stored).
- Claim-verified managers (`ClubProgramManager` + approved claim) keep full whole-club access. The
  owner is set only by `POST /api/admin/programs/<id>/owner`, and only for a verified manager.
- **One active owner per club, enforced twice.** `assign_owner` / `remove_owner` take the
  `club_programs` row lock (`_lock_program`, `FOR NO KEY UPDATE`) *before* reading the current
  owner, so concurrent admin assigns queue and the later one is a clean transfer. The partial unique
  index `uq_club_access_grants_one_active_owner` (`program_id WHERE role='owner' AND
  status='active'`; model + migration `p2a2` + pre-apply SQL) is the database backstop; a collision
  returns 409 `owner_conflict`. Lock order is always program row first, then grant rows. No club
  route can promote to owner (`INVITE_ROLES` excludes it) — keep it that way, or take the same lock.
- Every club route uses `require_club_permission(capability)` (`src/services/club_access.py`).
  Squad-scoped roles (coach/analyst/viewer) are additionally filtered by the scope helpers.
- **Whole-club = owner/manager only** (`ClubAccess.whole_club`; includes the legacy claim-verified
  manager). A coach/analyst/viewer granted **"all squads"** is still squad-scoped: the grant stores
  `all_squads` and `resolve_club_access` resolves it on every request to the club's *current* squad
  ids (a squad created later is included automatically; a club with no squads yields nothing). They
  pass through every scoped gate exactly like a specific-squad grant — no unassigned players, no
  legacy/unlabelled recordings, snapshot-only footage signing, workflow-only DTOs, viewer redaction,
  and a squad label is required when they create a match. `scoped_squad_ids()` is `None` only for
  owner/manager. `/access/me` returns `whole_club: false, all_squads: true` plus the resolved
  `squad_ids` for such a grant; the web console keys "Unassigned" and "squad required" off
  `whole_club`. Never use `all_squads` as a shortcut around a scope check.
- **The access board never has its own role table.** `GET /club/<id>/access` gives each person a
  `permissions` list (one bool per `matrix.rows` label) from
  `board_permissions(resolve_club_access(user, program))` — the same capabilities the guards check.
  So an invited (unverified) manager shows no `VERIFIED_ONLY` right (deciding scout requests), and a
  grant that currently resolves to no access shows none. Do not reintroduce a per-role matrix.
- **A grant's squad scope is a set.** The web editor and invite form (`StaffAccess.jsx`, helpers
  `scopeFromEntry` / `scopeBody` in `lib/staff-access.js`) hold and send the **whole** `squad_ids`
  array ("All squads" or any subset of one or more); never initialise an editor from one element.
  A scoped grant left with no squads is refused on save, not widened to "All squads".
- **Match rule (`match_visible_to`):** a squad-scoped caller (coach/analyst/viewer) sees a club match
  only if ALL hold: its squad label is in their squads; it has a **grant-time `origin`** coverage
  marker; it has no `uncertain` marker; and every player it covers — today's roster plus every
  `member` coverage row — is currently in their squads (dangling ids refuse). Anything that serves
  footage or data derived from it (media token, footage/crops/bbox, reel, report, profile film,
  `/roster` film totals, feedback evidence and citations) additionally needs a **completed upload**
  (`uploaded_at` + `blob_etag`). Match detail/list and the upload workflow (re-grant, completion,
  roster, processing request) use the gate without that last clause so scoped uploaders can work;
  an in-progress match carries no footage-derived data. Whole-club roles are unaffected.
- **Recording coverage (`video_match_coverage`, append-only):**
  - `origin` is written only in `create_club_match`, in the same transaction as the match and its
    first upload grant (the grant is always for the match's single `blob_path`), flag on or off. Coverage
    history therefore starts before any bytes can exist in storage.
  - Every roster write (club and admin, snapshotted before AND after the change), every upload-URL
    re-mint and every completion appends `member` rows — but only to a match that already has an
    `origin`. An unidentified/dangling/other-club roster row adds a permanent `uncertain` marker.
  - Removing or replacing roster rows never deletes coverage; deleting a member leaves its id behind,
    which then fails to resolve and keeps the match closed.
  - Completion and re-attestation (any ETag, flag on or off) **never** create or upgrade an `origin`.
- **Legacy recordings are managers-only.** A club match without a grant-time `origin` (every match
  created before p2a2, or one whose history is otherwise unknown) is whole-club only, forever — no
  roster edit, re-grant, re-upload, new ETag or flag change can open it to squad-scoped staff.
- **The only way coverage may ever narrow** is a future, explicitly *verified trimmed asset*: a new
  derived recording (new blob, its own `origin`) produced from the original by a reviewed trim/crop
  step that records which club members appear in it, approved by a whole-club role and audited. It
  would get its own coverage rows; the original recording's coverage never shrinks. Not built in
  Phase 2 — do not add any code path that deletes or rewrites `video_match_coverage` rows (other than
  the FK cascade when a match row itself is deleted; a future match-deletion route must keep provenance
  for any blob it leaves behind).
- Writes: a squad-labelled match may only hold that squad's players; mixed-squad matches stay
  unlabelled (whole-club roles only).
- **Completed recordings are immutable for clubs (flag on).** `POST /club/<id>/matches/<m>/sas` on a
  completed upload → 409 `recording_locked`; club `/upload-complete` on a completed recording whose
  stored ETag differs → 409 `recording_locked` (a same-ETag retry stays an idempotent 200). Footage
  is replaced by creating a new match, or through an **admin replacement grant**
  (`/admin/video/matches/<m>/sas`), which sets `scoped_ready_etag = "replacing"` and clears the
  snapshot until the next verified completion.
- **Scoped reads target an immutable generation.** Every verified completion (flag on or off) takes
  an Azure blob **snapshot** conditional on the verified ETag (`video_storage.create_verified_snapshot`)
  and stores it in `video_matches.scoped_snapshot`. Scoped readiness = `uploaded_at` + `blob_etag` +
  `scoped_ready_etag == blob_etag` + `scoped_snapshot`. Scoped footage is signed **only** for that
  snapshot (`sr=bs`, `?snapshot=…`), never for the mutable base blob, so bytes written through any
  upload SAS are unreachable with a scoped capability. No snapshot → no scoped access. The live ETag
  check on every scoped token mint/byte request stays as defence in depth (mismatch → neutral 404).
  Whole-club callers are signed for the base blob as before. Retention's `delete_blob` removes
  snapshots with the recording. Local dev artifact mode cannot verify any of this, so scoped staff
  get no bytes there.
- **`capture_meta.local` is server-owned** (dev artifact paths): stripped from club AND admin CREATE
  input (`capture_meta.strip_server_owned`); PATCH only merges preflight keys. Register dev artifacts
  only through trusted server code.
- **Scoped match DTO fallback:** when the derived-data predicate fails (in-progress, replacing,
  expired…) but the caller may still work on the match, detail, list and every write response
  (create, PATCH, upload-complete, process) return only a workflow DTO
  (`match_summary` + in-scope roster + processing request flag) — no capture metadata, jobs, blob
  paths or analysis.
- **Stored feedback evidence follows live scope:** scoped feedback reads and the profile
  `development` section drop `observation_refs` whose source match fails the derived-data predicate;
  coach-written text is kept. Whole-club and player reads are unchanged.
- What each role may read is decided in one place: `member_view` / `profile_view` / `match_summary`
  (allowlists). Add new fields there deliberately.

## Revocation bounds — what "remove access" can and cannot stop

Removing or narrowing a grant, hiding or suspending the program, or a roster change that makes a
match mixed-squad takes effect on the **next request** for every app route, including media tokens
minted with the flag on (they carry `club_user_id` and are re-checked on each byte request).
What it cannot reach:

| Capability already handed out | How long it keeps working after revocation | Where |
|---|---|---|
| Footage read SAS (the 302 target of `/footage`) | up to **30 minutes** — capped at the media token's remaining life; for scoped staff it addresses the verified snapshot only | `services/video_storage.py` `MEDIA_READ_SAS_MINUTES`, `routes/video.py` `stream_footage` |
| Direct upload SAS (from `POST /matches` or `/sas`) | up to **60 minutes** — storage writes only; completing/processing the upload re-checks access, and scoped reads re-verify the stored ETag so unverified replacement bytes are never served through the app | `services/video_storage.py` `UPLOAD_SAS_MINUTES` |
| Club media tokens minted while the flag was **off** | up to **30 minutes**, legacy behaviour (no live re-check) after the flag is switched on | `auth.py` `MEDIA_TOKEN_TTL`, `routes/video.py` `_media_match_or_error` |
| Bytes already downloaded / an open transfer | not recoverable; an in-flight transfer may outlive the SAS expiry | — |

So: after switching the flag on, allow 30 minutes before relying on live media revocation for
pre-existing sessions; after removing someone, assume they could finish a footage view or an
upload started within the previous hour.

## Tests that pin this

`tests/test_club_staff_access.py` (route matrix, invites, revocation) and
`tests/test_club_staff_access_ra2.py`, `test_club_staff_access_ra2_denials.py`,
`test_club_staff_access_ra2v.py`, `…_ra2v2.py`, `…_ra2v3.py` and `…_ra2v4.py` (RA2–RA2V4 security
regressions incl. roster-cleanup, legacy re-attestation and pre-completion byte cases),
`test_club_staff_access_ra2v5.py` ("all squads" coach/analyst/viewer stay behind the scoped gates;
late-created squads are in scope; owner/manager unchanged),
`test_club_staff_access_a2f9.py` (board permissions == resolved capabilities for every role x
verified state; multi-squad grants survive a role-only change) with
`academy-watch-frontend/e2e/club-staff-access.spec.mjs` and `tests/staff-access-scope.test.mjs`
(the editor sends the full squad set),
`test_club_staff_access_coverage.py` (grant-time monotonic coverage, happy path),
`test_video_storage_snapshot.py` (snapshot SAS against a fake Azure client) and
`test_club_staff_access_flagoff_parity.py` (164 flag-off responses == origin/main).

## Coach’s brief versus player feedback (UXM2 · P-18)

- Product decision: BUS `2026-10-01 14:29 | orchestrator | ANSWER` explicitly confirms Coach’s brief is coaching content. Write requires **`players.manage` OR `feedback`**, so a scoped coach may edit an available player in their assigned squads.
- `PUT /club/<id>/roster/<member>/brief` applies `member_in_scope` and returns neutral 404 outside scope; responses use `member_view`. BUS `2026-10-01 19:01 | ORCH | DISPUTE` lead option 1: whole-club roles refuse every stored club name; squad-limited staff refuse only names on readable own-squad roster identities and match sheets. Hidden and unknown candidates save identically. Stored hidden text can remain readable to the author and their squad; the save never consults the hidden-name inventory.
- The worker's `_brief_context` replaces entire lines containing **any** club player name in roster and system briefs with a fixed neutral placeholder before model input, preserving normalized expectation positions and the **stored** brief hash. `services/brief_names.py` loads stored aliases independently of availability: both roster key forms, all local/provider/shadow bridges (including signed shadow IDs), forward merge survivors and reverse retained aliases, and match sheets. It folds complete stored names before token extraction (including NFD accents), with case plus Ł/Ø/Đ/Æ/Œ/ı/Þ/Ð mapped to defined ASCII equivalents (ß already casefolds); this is not universal romanization. The inventory never enters a response or log.
- Name refusals remain the same neutral 422 for all roles; malformed shape/length is 400. A shared 20/hour **refusal-only** account budget spans members/programs and IPs; successful work consumes no budget, including 25 consecutive manager saves with flags off. Clean saves remain available after exhaustion; only the next name refusal returns a neutral JSON 429 with private/no-store and Retry-After, preserved by the production HTTP handler. Permission checks precede limiting.
- Read follows `players.view` within squad scope through `member_view` / `profile_view`. Viewers receive neither brief field. Analysts may read but cannot write; viewers cannot write.
- Authorization and redaction remain unchanged with the flag off; the full stored-name validation, neutral 422 and refusal-only account budget also protect managers. Squad assignment, photo, note and system-brief writes still require `players.manage`. The club player page shows Edit brief independently of those manager-only controls.
- Pathway reads include recorded `ClubRosterSquadHistory` plus the current squad when imported/older assignments lack an open history row. Unknown assignment dates stay unknown; GET never creates history.

- Scoped match-sheet refusal aliases require a currently readable own-squad member, matching the detail sheet filter. Scoped club JSON adapters withhold private brief checks, hashes, counters, brief limits and check-only notes (including historical filtered analyses); ordinary observations remain readable. Whole-club/flag-off readers retain checks.
