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
- **Match rule:** a scoped caller sees a match only if its squad label is in their squads **and every
  player it covers is currently in their squads** (`match_visible_to`). Coverage = the current roster
  plus, once a recording exists (upload-complete), the append-only `video_match_coverage` record:
  an `origin` marker written at upload, a `member` row for every club player ever on the roster since,
  and a permanent `uncertain` marker if an unidentified row was ever present. Removing or replacing
  roster rows **never** narrows coverage; only a future explicitly verified trimmed asset may. A
  recording with no `origin` marker (uploaded before p2a2) or with `uncertain` is whole-club only.
  Coverage is recorded even with the flag off, so history is complete when it is switched on. The
  same gate covers match detail/report/reel/media-token/list, footage/crops/bbox, profile film,
  `/roster` film totals, feedback evidence and feedback citations. Writes: a squad-labelled match may
  only hold that squad's players; mixed-squad matches stay unlabelled (whole-club roles only).
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
| Direct upload SAS (from `POST /matches` or `/sas`) | up to **60 minutes** — storage writes only; completing/processing the upload re-checks access | `services/video_storage.py` `UPLOAD_SAS_MINUTES` |
| Club media tokens minted while the flag was **off** | up to **30 minutes**, legacy behaviour (no live re-check) after the flag is switched on | `auth.py` `MEDIA_TOKEN_TTL`, `routes/video.py` `_media_match_or_error` |
| Bytes already downloaded / an open transfer | not recoverable; an in-flight transfer may outlive the SAS expiry | — |

So: after switching the flag on, allow 30 minutes before relying on live media revocation for
pre-existing sessions; after removing someone, assume they could finish a footage view or an
upload started within the previous hour.

## Tests that pin this

`tests/test_club_staff_access.py` (route matrix, invites, revocation) and
`tests/test_club_staff_access_ra2.py`, `test_club_staff_access_ra2_denials.py`,
`test_club_staff_access_ra2v.py` (RA2/RA2V security regressions incl. the 18 roster-cleanup
sequences), `test_club_staff_access_coverage.py` (monotonic coverage) and
`test_club_staff_access_flagoff_parity.py` (164 flag-off responses == origin/main).
