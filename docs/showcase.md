# Talent Showcase — Player Profiles, Claims & Club-Verified Evidence

> **Living document.** Last updated **2026-07-02**. When the feature changes, update the
> relevant section and add a line to the Changelog. Roadmap/state:
> `ledgers/ROADMAP_talent-showcase-vision.md`.

## 1. What it is

Every player page carries a **Showcase** section (top of page, above stats):

1. **Highlight reel** — embedded YouTube videos. Sources: owner-curated links,
   fan-submitted links (moderated), and admin-entered newsletter YouTube links
   (merged read-only, deduped by video id).
2. **Player profile card** — bio / positions / preferred foot / height, always badged
   **"Self-reported"** (never styled like verified stats).
3. **Verified appearances** — badged **"Club-verified"** (emerald): appearance evidence
   from Film Room reports where a **human confirmed the identity** and an admin linked
   the roster entry to the platform player. Shows opponent, date, minutes on camera,
   % of match.
4. **Claim strip** — "Is this you? Claim this profile."

## 2. The claim → curate lifecycle

```
user (logged in) claims player  →  admin approves (Admin → Showcase → Claims)
  →  owner curates: add/reorder/delete reel videos, edit profile card
  →  every content edit is PRE-MODERATED (pending → admin approves → public)
```

- Relationships: `player | agent | guardian | club_official`. Multiple approved claims
  per player are allowed (player + agent may co-own).
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

## 4. API surface (all under /api)

Public: `GET /players/<id>/showcase` (optional Bearer: approved owners also get their
pending items). User: `POST /players/<id>/claim`, `GET /me/claims`, owner-gated
`PUT .../showcase/profile`, `POST/PATCH/DELETE .../showcase/reel*`. Admin
(`require_api_key`): `/admin/showcase/{claims,claims/<id>/review,profiles,
profiles/<pid>/review,video-rosters,video-rosters/<rid>/link,player-search}`.

URL safety: all submitted links must be https + YouTube (server-side `_is_youtube_url`);
`javascript:`/`data:`/http are rejected everywhere, including the pre-existing
`POST /players/<id>/links` (hardened in this slice).

## 5. Operator notes

- **Migration `aw19`** merges the `cs01` + `vid02` heads back to one and adds
  `player_profile_claims`, `player_showcase_profiles`, `player_links.sort_order`.
  Idempotent/guarded. Note: `flask db downgrade` across any merge revision needs an
  explicit target revision (alembic "Ambiguous walk" — same as aw17).
- **Local dev DB caveat (2026-07-02):** the local DB is stamped `vid03` (uncommitted
  migration); aw19's DDL was applied there manually (guarded SQL) without touching
  `alembic_version`. After the vid-chain work lands, rebase vid03 onto aw19
  (`down_revision="aw19"`, drop its merge) and run a normal upgrade.
- **Known pre-existing issue:** the historical migration chain cannot replay on an EMPTY
  database (an old unguarded migration alters the deleted `supplemental_loans` table).
  Existing stamped DBs are unaffected.
- Tests: `pytest tests/test_showcase.py` (40). Demo data on local dev DB: player 403064
  (H. Amass) has a claimed profile, curated reel, and a club-verified appearance from
  Film Room match 4.

## 6. Changelog

- **2026-07-02** — Initial slice shipped (P0 showcase surfacing + P1 claim & curate +
  X Film Room verified evidence). Built multi-agent (Fable 5 orchestrating Opus 4.8
  builders), adversarially reviewed (23 agents, 8 findings fixed), live-verified.
