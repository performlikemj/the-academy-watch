# Club staff access (Phase 2 · A2) — read before enabling or touching club auth

Dark behind `CLUB_STAFF_ACCESS_ENABLED` (default off). With it off, every club route answers
exactly as it did before (same statuses, same payloads, including HEAD requests); the new
routes return 404.

## The model in one screen

- `club_access_grants` (+ `club_access_grant_squads`) hold invited staff roles; `club_staff_invites`
  hold one-use emailed invites (only the SHA-256 of the token is stored).
- Claim-verified managers (`ClubProgramManager` + approved claim) keep full whole-club access. The
  owner is set only by `POST /api/admin/programs/<id>/owner`, and only for a verified manager.
- Every club route uses `require_club_permission(capability)` (`src/services/club_access.py`).
  Squad-scoped roles (coach/analyst/viewer) are additionally filtered by the scope helpers.
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
- **Completed recordings are immutable for clubs.** With the flag on, `POST /club/<id>/matches/<m>/sas`
  on a completed upload returns 409 `recording_locked` (replace footage by creating a new match).
  An admin re-grant on a completed club recording clears `video_matches.scoped_ready_etag`
  ("replacing"): scoped staff lose all footage-derived access until the next **verified** completion
  republishes the new ETag. "Completed" for scoped reads means `uploaded_at` + `blob_etag` +
  `scoped_ready_etag == blob_etag`. On every scoped media-token mint and byte request the stored
  blob's live ETag is re-verified against `blob_etag` (covers a still-live original write SAS);
  a mismatch is a neutral 404. Local dev artifact mode (storage not configured) cannot verify this,
  so scoped staff get no bytes there; whole-club behaviour is unchanged in both modes.
- **`capture_meta.local` is server-owned** (dev artifact paths): stripped from club CREATE/PATCH input.
- **Scoped detail/list fallback:** when the derived-data predicate fails (in-progress, replacing,
  expired…) but the caller may still work on the match, detail and list return only a workflow DTO
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
| Footage read SAS (the 302 target of `/footage`) | up to **30 minutes** — capped at the media token's remaining life | `services/video_storage.py` `MEDIA_READ_SAS_MINUTES`, `routes/video.py` `stream_footage` |
| Direct upload SAS (from `POST /matches` or `/sas`) | up to **60 minutes** — storage writes only; completing/processing the upload re-checks access, and scoped reads re-verify the stored ETag so unverified replacement bytes are never served through the app | `services/video_storage.py` `UPLOAD_SAS_MINUTES` |
| Club media tokens minted while the flag was **off** | up to **30 minutes**, legacy behaviour (no live re-check) after the flag is switched on | `auth.py` `MEDIA_TOKEN_TTL`, `routes/video.py` `_media_match_or_error` |
| Bytes already downloaded / an open transfer | not recoverable; an in-flight transfer may outlive the SAS expiry | — |

So: after switching the flag on, allow 30 minutes before relying on live media revocation for
pre-existing sessions; after removing someone, assume they could finish a footage view or an
upload started within the previous hour.

## Tests that pin this

`tests/test_club_staff_access.py` (route matrix, invites, revocation) and
`tests/test_club_staff_access_ra2.py`, `test_club_staff_access_ra2_denials.py`,
`test_club_staff_access_ra2v.py`, `test_club_staff_access_ra2v2.py` and `test_club_staff_access_ra2v3.py` (RA2–RA2V3 security
regressions incl. roster-cleanup, legacy re-attestation and pre-completion byte cases),
`test_club_staff_access_coverage.py` (grant-time monotonic coverage, happy path) and
`test_club_staff_access_flagoff_parity.py` (164 flag-off responses == origin/main).
