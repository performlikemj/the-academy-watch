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
  →  admin reviews the claim and the advisory check (Admin → Showcase → Claims)
  →  admin approves
  →  owner curates: upload/reorder photos, add/reorder/delete reel videos, edit profile card
  →  every content edit is PRE-MODERATED (pending → admin approves → public)
```

- Relationships: `player | agent | guardian | club_official`. Multiple approved claims
  per player are allowed (player + agent may co-own).
- Social proof demonstrates control of a known public profile; it does not prove legal
  identity. The automated result is advisory (`unverified`, `code_found`, or
  `code_not_found`) and **admin approval remains the only gate that approves a claim**.
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

## 4. API surface (all under /api)

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

## 5. Operator notes

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
- **Local dev DB caveat (2026-07-02):** the local DB is stamped `vid03` (uncommitted
  migration); aw19's DDL was applied there manually (guarded SQL) without touching
  `alembic_version`. After the vid-chain work lands, rebase vid03 onto aw19
  (`down_revision="aw19"`, drop its merge) and run a normal upgrade.
- **Known pre-existing issue:** the historical migration chain cannot replay on an EMPTY
  database (an old unguarded migration alters the deleted `supplemental_loans` table).
  Existing stamped DBs are unaffected.
- Tests: `pytest tests/test_showcase.py tests/test_showcase_media.py tests/test_claim_verification.py`.
  Demo data on local dev DB: player 403064
  (H. Amass) has a claimed profile, curated reel, and a club-verified appearance from
  Film Room match 4.

## 6. Changelog

- **2026-07-14** — Added the claim-verification ladder: one-time code in a known public
  social profile, SSRF-hardened best-effort checking, claimant retry and admin re-check.
  Automated evidence remains advisory and admin approval remains the sole approval gate;
  document/ID upload is explicitly never part of Showcase verification.
- **2026-07-08** — Added pre-moderated, self-hosted player photos with direct blob upload,
  EXIF/GPS stripping, gallery ordering/primary selection, admin media review, and enriched
  contract/availability/agent/nationality/language profile fields. Codified the permanent
  no-native-video policy (YouTube embeds only; club-consented Film Room is the sole exception).
- **2026-07-02** — Initial slice shipped (P0 showcase surfacing + P1 claim & curate +
  X Film Room verified evidence). Built multi-agent (Fable 5 orchestrating Opus 4.8
  builders), adversarially reviewed (23 agents, 8 findings fixed), live-verified.
