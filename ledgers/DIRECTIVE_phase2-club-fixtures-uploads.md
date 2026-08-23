# DIRECTIVE (DRAFT) — Phase 2: clubs enter fixtures without video; uploads that survive; quota that grows

Status: DRAFT 2026-08-23 (Fable, from code reads during the Phase 0 lane). Not ratified. Decisions in §4
are MJ's. Source plan: `docs/platform-review-2026-08-23.md` Phase 2 (items 1–5). Depends on the Phase 1
stats grain (`player_match_entries`, `ledgers/DIRECTIVE_phase1-user-fed-data.md` §2b) for item 1.
Executor when ratified: qwen lane (`briefs/P2-*.md`).

## 1. What the code already has (read 2026-08-23)

- Console routes (`routes/club.py`, all `@require_club_manager()`): roster GET/POST/DELETE, matches POST
  (+ GET list from P0-B1), `/sas` re-mint (only while `created|uploaded`), `/upload-complete` (verifies blob
  size+etag, stamps `uploaded_at`, `expires_at`), PATCH, GET one, roster PUT, `/process`, `/report`.
- Quota: `_quota()` = `CLUB_MATCH_QUOTA_DEFAULT` (3) capped by `MAX_MATCH_QUOTA` (100), counted as ALL
  `VideoMatch` rows of the program, serialized by `pg_advisory_xact_lock(QUOTA_LOCK_NAMESPACE, program_id)`.
- Upload client (`api.js::uploadVideoToBlob`): Azure Put Block (32 MB blocks, ids `block-00000000` base64,
  sequential, one fetch per block) + Put Block List commit; on failure the console re-mints the SAS and
  restarts at offset 0. Write SAS is 60 min (`UPLOAD_SAS_MINUTES`), permissions write+create only.
- Roster add: a local player is attachable only if `local.created_by_user_id == g.user_id` (B5);
  `PlayerClubAffiliation` (player↔club, statuses pending/self_reported/club_confirmed/rejected) exists on
  the showcase side and is exactly the "player says I play here / club confirms" signal.
- No playback for clubs (the `<video>` lives only in the admin reviewer); media-token route is admin-only.

## 2. Smallest correct mechanisms

**2.1 Fixture/result entry without video (review item 1).** Two tables, one of which Phase 1 creates:
`club_fixtures` (id, program_id, match_date, competition, opponent, home_away, goals_for, goals_against,
notes, created_by, created_at, RLS) and per-player rows in Phase 1's `player_match_entries` with
`club_fixture_id` (nullable FK; added here). Console: "Add a fixture" form → squad picker from the
roster (minutes/goals/assists/cards per player) → one POST `/club/<id>/fixtures` creating the header and
entries (`source='club'`, `status='club_confirmed'`), calling `season_rollup_service.refresh_player` per
player in the same transaction. `VideoMatch` is untouched: a fixture MAY later link to a VideoMatch
(`video_match_id` nullable) when footage is uploaded. Quota does not apply to fixtures.

**2.2 Resumable uploads (item 2).** Keep the client's block scheme; add (a) backend
`GET /club/<id>/matches/<mid>/uploaded-blocks` → the blob's UNCOMMITTED block ids via the service client
(`get_block_list(block_list_type="uncommitted")`), manager-gated, only while `created|uploaded`; (b) client:
on start or retry, fetch that list, skip blocks already present, re-mint the SAS when it is within
5 minutes of expiry (the `/sas` route already re-mints; `expires_at` is in the grant), commit the FULL
block list at the end. Net effect: a 6 GB upload survives SAS expiry and a dropped connection, never
restarts from zero. No change to `verify_uploaded_blob`.

**2.3 Club playback preview (item 3).** Reuse the admin media path with a manager-scoped token:
`GET /club/<id>/matches/<mid>/media-token` (manager-gated, mints `mint_media_token(match_id)`) and let
`/admin/video/matches/<mid>/footage?token=` accept any valid media token (it already checks the token, not
the admin headers) — the 30-minute read SAS from P0-D2 applies. Console shows a `<video>` for uploaded
matches before "Request processing". Nothing new is stored.

**2.4 Growth-compatible quota (item 4).** Replace "lifetime count" with a monthly allowance:
`CLUB_MATCH_QUOTA_MONTHLY` (default 4) counted over `VideoMatch.created_at` in the current UTC month,
plus the existing lifetime hard max as a safety cap. Same advisory lock; the 429 payload gains
`window: "month"` and `resets_at`. Paid tiers can later raise the monthly number per program
(`ClubProgram.match_quota_monthly` nullable override) — no billing here.

**2.5 Roster vouch (item 5).** Allow a manager to roster a local player they did NOT create when ONE of:
(a) a `PlayerClubAffiliation` between that local player and this club exists with status
`club_confirmed`; or (b) the manager creates a vouch request (`POST /club/<id>/roster/vouch
{local_player_id}`) that the local player's claimant confirms from their profile (reuse the affiliation
table: status `pending` → `club_confirmed` on player accept). The roster rule becomes
`created_by_user_id == g.user_id OR confirmed affiliation exists`. Suppression/merged/minor rules unchanged.

## 3. Not in scope

Stripe/billing for quota tiers (Phase 3/4); ffprobe preflight (Phase 3 item 4); any change to the
worker, report contracts, or public attribution of club footage (explicitly excluded today).

## 4. MJ decisions needed

- **D1 quota number + window** (recommend 4/month + lifetime cap 100; or per-program override only).
- **D2 fixture entry visibility:** do club-entered results/minutes show on the PUBLIC player profile
  immediately (`club_confirmed` provenance chip) or only after the player's claimant acknowledges?
  Recommend: show immediately with provenance; the player can dispute (Phase 1 `disputed` status).
- **D3 club preview:** is exposing the raw upload to the club's own managers (30-min SAS) acceptable under
  the youth-footage posture? It is their own footage; recommend yes, manager-gated + no-store.

## 5. Brief plan once ratified (each ≤75 min, qwen)

P2-A1 `club_fixtures` migration (+RLS, chained) · P2-A2 model + serializer · P2-A3 POST/GET fixtures
route + entries + rollup refresh (tests) · P2-A4 console "Add a fixture" form + squad stats grid ·
P2-B1 `uploaded-blocks` route (+ fake storage test) · P2-B2 client resume + SAS renewal · P2-C1 manager
media-token route + footage route accepts it · P2-C2 console preview `<video>` · P2-D1 monthly quota ·
P2-E1 affiliation-based roster rule + tests · P2-E2 vouch request/accept · P2-E3 console vouch UI.
