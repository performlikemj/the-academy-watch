# Talent Showcase — Player Profiles, Photos, Claims & Club-Verified Evidence

> **Living document.** Last updated **2026-07-14**. When the feature changes, update the
> relevant section and add a line to the Changelog. Roadmap/state:
> `ledgers/ROADMAP_talent-showcase-vision.md`.

## 1. What it is

Every player page carries a **Showcase** section (top of page, above stats):

1. **Highlight reel** — embedded YouTube videos. Sources: owner-curated links,
   fan-submitted links (moderated), and admin-entered newsletter YouTube links
   (merged read-only, deduped by video id).
2. **Photo gallery** — owner-uploaded, admin-approved images with a primary-photo slot;
   anonymous visitors never see pending or rejected media.
3. **Player profile card** — bio / positions / preferred foot / height, always badged
   **"Self-reported"** (never styled like verified stats).
4. **Verified appearances** — badged **"Club-verified"** (emerald): appearance evidence
   from Film Room reports where a **human confirmed the identity** and an admin linked
   the roster entry to the platform player. Shows opponent, date, minutes on camera,
   % of match.
5. **Claim strip** — "Is this you? Claim this profile."

## 2. The claim → curate lifecycle

```
user (logged in) claims player  →  receives a one-time code
  →  places the code in the bio of a public Instagram / TikTok / X / Facebook / YouTube profile
  →  submits that profile URL for a best-effort automated check
  →  admin reviews and approves, OR an eligible verified club official vouches for identity
  →  owner curates: upload/reorder photos, add/reorder/delete reel videos, edit profile card
  →  every content edit is PRE-MODERATED (pending → admin approves → public)
```

- Relationships: `player | agent | guardian | club_official`. Multiple approved claims
  per player are allowed (player + agent may co-own).
- Social proof demonstrates control of a known public profile; it does not prove legal
  identity. The automated result is advisory (`unverified`, `code_found`, or
  `code_not_found`) and never approves a claim by itself. Identity approval comes from
  admin review or an eligible verified-club-official vouch.
- Claimants may retry with the same one-time code. Admins can re-run the check against the
  stored profile URL before deciding a claim.
- **There is no document or ID upload, ever.** The platform does not collect or store KYC
  documents for Showcase claims; unresolved claims remain a manual-review decision.
- **Safeguarding posture:** many players are minors — all owner content is pre-moderated;
  a rejected/revoked claim can be resubmitted (resets to pending); no commentary surfaces.
- Owners see their own pending items (amber badge); the public never does.
- Reel link moderation reuses the existing **Admin → Inbox → Player Links** queue.
- Profile-edit moderation lives in **Admin → Showcase → Profile edits**.

## 3. Film Room → profile (the flywheel)

Admin → Showcase → **Film Room links**: for finalized matches, link a roster entry
(e.g. "Yorkies No. 2", identity `human_confirmed`) to a platform player via name search.
Only **human-confirmed** identities ever surface publicly; linking is an explicit admin
action; opposition players have no roster rows and can never appear.

## Media policy

- **Photos are self-hosted and pre-moderated.** An approved profile owner uploads JPEG,
  PNG, or WebP directly to private blob storage. The Flask app mints the short-lived PUT
  URL; it never relays browser upload bytes. An admin must approve every image before it
  appears publicly.
- **Location data is never published.** Approval decodes the source image, limits its long
  edge to 1600 px, strips all EXIF (especially GPS), and re-encodes it as JPEG before
  writing to the public media container. Pending and rejected originals are never public.
- **Native video is never accepted.** Public video remains YouTube embeds only. Film Room's
  private, club-consented match-analysis pipeline is the sole exception; it does not turn
  native match footage into a public player upload surface.
- A player may have at most eight non-rejected photos. Owners can see moderation state,
  reorder approved photos, select one primary photo, and delete their media; anonymous
  visitors see approved photos only.

## 4. Local clubs & affiliations

A **local club** is a community-created club record for a team that is not covered by
API-Football. It lives separately from the API-synced `teams` table and lets a player name
their real club on Showcase without inventing an API team. Authenticated users search both
API teams and pending/verified local clubs before creating a local club.

The local-club lifecycle is:

1. Creation starts at `pending` and records user provenance; an admin either moves it to
   `verified` or `rejected`.
2. An admin can merge a duplicate into an active target. The source becomes `merged`, all
   affiliations pointing at it move to the target, and merged/rejected clubs disappear from
   user search and cannot receive new affiliations.
3. If API-Football later covers the club, an admin may store its API team id as a bridge on
   the local-club row. Linking does not create or modify a `teams` row and does not turn the
   local club into synced data.

An approved profile owner can submit an affiliation to exactly one API team or local club.
Affiliations are pre-moderated: `pending` → `self_reported` after admin approval, or
`rejected`. `club_confirmed` is reserved for the club-official confirmation flow in Chunk 4.
Anonymous/public responses include only `self_reported` and `club_confirmed` affiliations;
owners can also see their pending/rejected rows and moderation notes.

**Hard isolation rule:** local clubs and affiliations are a parallel, self-reported Showcase
layer only. They must never enter player journeys, team sync, crawl scope, classifiers, Scout
queries, leaderboards, or any other API-Football-derived data pipeline.

New API surface (all under `/api`):

- Authenticated: `GET /clubs/search?q=<name>` and `POST /local-clubs`.
- Approved profile owner: `POST /players/<id>/showcase/affiliations` and
  `DELETE /players/<id>/showcase/affiliations/<affiliation_id>`.
- Public: `GET /players/<id>/showcase` includes the visibility-filtered `affiliations` list;
  an approved owner may authenticate to see their moderation state.
- Admin (`require_api_key`): `GET /admin/local-clubs?status=<status>`,
  `POST /admin/local-clubs/<club_id>/review`,
  `POST /admin/local-clubs/<club_id>/merge`,
  `POST /admin/local-clubs/<club_id>/link-api`,
  `GET /admin/showcase/affiliations?status=<status>`, and
  `POST /admin/showcase/affiliations/<affiliation_id>/review`.

## 5. Club officials & vouching

A club official claims exactly one API-Football team or active local club. Official claims
reuse the player-claim social-proof ladder: the claimant receives a one-time code, places it
on an allowlisted public social profile, submits that profile URL for a best-effort check,
and remains `pending` until an admin approves or rejects the claim. An approved claim may
later be revoked. Automated social proof remains advisory; only an approved official claim
opens the club trust actions below.

An approved official's **My Club** queue contains pending or self-reported affiliations that
name their club and pending player-profile claims linked to it by a non-rejected affiliation.
Local-club matching follows one merge hop, so work attached to a merged duplicate reaches the
official for the surviving club.

- Confirming an affiliation changes it to `club_confirmed`; rejecting it changes it to
  `rejected` and may record a review note.
- Vouching auto-approves a pending player-profile claim and records verification method
  `vouch`. **A vouch approves identity only.** Every owner-submitted photo, reel link, and
  profile edit remains pre-moderated before it can appear publicly.
- A club-claim verification code is returned only in the authenticated creation response,
  the claimant's own `/me/club-claims` list, and the admin list. It is never included in
  public or cross-user payloads.
- Player-claim verification codes are likewise stripped from the cross-user My Club vouch
  queue and vouch response; advisory status and check timestamps remain visible.

Club-official API surface (all under `/api`):

- Authenticated: `POST /clubs/claim`, `GET /me/club-claims`,
  `POST /me/club-claims/<claim_id>/verify`, and `GET /me/club`.
- Approved official for the referenced club:
  `POST /me/club/affiliations/<affiliation_id>/confirm`,
  `POST /me/club/affiliations/<affiliation_id>/reject`, and
  `POST /me/club/player-claims/<claim_id>/vouch`.
- Admin (`require_api_key`): `GET /admin/club-claims?status=<status>`,
  `POST /admin/club-claims/<claim_id>/review` (`approve`, `reject`, or `revoke`), and
  `POST /admin/club-claims/<claim_id>/recheck`.

## 6. API surface (all under /api)

Public: `GET /players/<id>/showcase` includes approved `photos` (optional Bearer: approved
owners also get their pending/rejected items and preview URLs). It exposes claim status but
never a claim verification code. User:

- `POST /players/<id>/claim` — create a pending claim and receive its one-time verification
  code in the authenticated response.
- `GET /me/claims` — list the caller's claims and their verification state; legacy claims
  receive a code lazily.
- `POST /me/claims/<claim_id>/verify` — submit `{ "proof_url": "https://..." }` and run a
  best-effort social-profile check. Both code-found and code-not-found checks return a
  normal claim response; neither approves the claim.
- Owner-gated `PUT .../showcase/profile` and `POST/PATCH/DELETE .../showcase/reel*`.

Photo media:

- `POST /players/<id>/showcase/photos` — create a pending upload and receive a direct
  `PUT` URL plus its required headers.
- `POST /players/<id>/showcase/photos/<media_id>/complete` — verify the private blob and
  move it to the moderation queue.
- `PATCH /players/<id>/showcase/photos/order` — reorder approved photos.
- `PATCH /players/<id>/showcase/photos/<media_id>` — select an approved primary photo.
- `DELETE /players/<id>/showcase/photos/<media_id>` — delete the row and stored blobs.

The showcase profile API also accepts `contract_status`, `contract_until`, `availability`,
`agent_name`, `agent_contact_email`, `nationality_secondary`, and `languages`. Agent name is
public; agent contact email is returned only to authenticated callers.

Admin (`require_api_key`) retains the existing claims, profiles, Film Room links, and player
search routes, and adds:

- `POST /admin/showcase/claims/<claim_id>/recheck` — re-run the advisory check against the
  stored proof URL and return the updated claim.
- `GET /admin/showcase/media?status=<status>` — list media, optionally by lifecycle status.
- `POST /admin/showcase/media/<media_id>/review` — approve or reject; approval performs the
  EXIF-stripping conversion before publication.

Local development additionally exposes direct `PUT` and `GET` operations at
`/dev/showcase-media/<blob_path>`. Both are disabled in production.

URL safety: Showcase reel links must be https + YouTube (server-side `_is_youtube_url`);
`javascript:`/`data:`/http are rejected everywhere, including the pre-existing
`POST /players/<id>/links`. Social-proof URLs are separately limited to https profiles on
Instagram, TikTok, X/Twitter, Facebook, or YouTube; the checker rejects IP literals,
userinfo, explicit ports, and unsafe redirects, and applies strict time and body-size caps.

## 7. Operator notes

- **Migration `aw19`** merges the `cs01` + `vid02` heads back to one and adds
  `player_profile_claims`, `player_showcase_profiles`, `player_links.sort_order`.
  Idempotent/guarded. Note: `flask db downgrade` across any merge revision needs an
  explicit target revision (alembic "Ambiguous walk" — same as aw17).
- **Migration `shp01`** adds Showcase media plus enriched profile fields. Production photo
  uploads require the private `showcase-media-pending` and public-read `showcase-media`
  containers; until Azure is configured, photo upload creation returns 503 while the rest
  of Showcase remains available.
- **Migration `shp02`** adds social-proof code, URL, method, result, checked-at, and note
  fields to `player_profile_claims`. No external credentials or social-platform API keys
  are required; checks fetch only public profile pages and fail closed as advisory results.
- **Migration `shp03`** adds the guarded, RLS-enabled `local_clubs` and
  `player_club_affiliations` tables. Both remain Showcase-only and never feed API-Football
  sync, crawl, classifier, journey, or Scout paths.
- **Migration `shp04`** adds the guarded, RLS-enabled `club_official_claims` table. Official
  claims reuse the social-proof evidence fields but remain a separate lifecycle from player
  claims; vouching records identity approval without bypassing content moderation.
- **Local dev DB caveat (2026-07-02):** the local DB is stamped `vid03` (uncommitted
  migration); aw19's DDL was applied there manually (guarded SQL) without touching
  `alembic_version`. After the vid-chain work lands, rebase vid03 onto aw19
  (`down_revision="aw19"`, drop its merge) and run a normal upgrade.
- **Known pre-existing issue:** the historical migration chain cannot replay on an EMPTY
  database (an old unguarded migration alters the deleted `supplemental_loans` table).
  Existing stamped DBs are unaffected.
- Tests: `pytest tests/test_showcase.py tests/test_showcase_media.py tests/test_claim_verification.py
  tests/test_local_clubs.py tests/test_club_officials.py`.
  Demo data on local dev DB: player 403064
  (H. Amass) has a claimed profile, curated reel, and a club-verified appearance from
  Film Room match 4.

## 8. Changelog

- **2026-07-14** — Added club-official claims using the social-proof ladder, a My Club queue
  for confirming or rejecting player affiliations, and verified-official vouching for player
  identity claims. Vouching approves identity only; all owner content remains pre-moderated.

- **2026-07-14** — Added community-created local clubs, admin verification/merge/API-bridge
  tooling, and pre-moderated player affiliations. Local clubs remain permanently isolated
  from journey/team sync, crawl scope, classifiers, and Scout data.

- **2026-07-14** — Added the claim-verification ladder: one-time code in a known public
  social profile, SSRF-hardened best-effort checking, claimant retry and admin re-check.
  Automated evidence remains advisory and never self-approves; identity approval is an admin
  decision or, since Chunk 4, an eligible verified-official vouch. Document/ID upload is
  explicitly never part of Showcase verification.
- **2026-07-08** — Added pre-moderated, self-hosted player photos with direct blob upload,
  EXIF/GPS stripping, gallery ordering/primary selection, admin media review, and enriched
  contract/availability/agent/nationality/language profile fields. Codified the permanent
  no-native-video policy (YouTube embeds only; club-consented Film Room is the sole exception).
- **2026-07-02** — Initial slice shipped (P0 showcase surfacing + P1 claim & curate +
  X Film Room verified evidence). Built multi-agent (Fable 5 orchestrating Opus 4.8
  builders), adversarially reviewed (23 agents, 8 findings fixed), live-verified.
