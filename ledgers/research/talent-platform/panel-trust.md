I have everything I need. Here is the design.

---

# Player-Uploaded Stats & Video — Trust & Integrity System

## Design lens: nothing enters the trust ladder as "true." It enters as *claimed*, and earns its way up through cheap, stacked corroboration — or gets struck down.

The platform already has a working trust spine I'm extending, not replacing:

- **Self-reported** — `PlayerShowcaseProfile` (bio/positions/foot/height, `self_reported: True`)
- **Claimed** — `PlayerProfileClaim` (`relationship_type ∈ {player, agent, guardian, club_official}`, `status='approved'`)
- **Platform-verified** — API-Football stats via `TrackedPlayer.compute_stats()` / `FixturePlayerStats`
- **Club-verified** — `VideoPlayerReport.identity_confidence='human_confirmed'` on a `finalized` `VideoMatch` (the emerald tier surfaced by `_verified_footage()` in `showcase.py`)

Player-uploaded *stats* are the missing rung: a claimed owner asserting "I played 84 mins and scored 2 vs Deportivo on 2026-05-03." Today there is no place to put that and no way to stop it being a lie. Below is that surface.

---

## (a) The submission surface — one assertion per fact

Grassroots is the whole point (MJ's ask #2, and the "no platform-native players" gap), so the subject cannot be `player_api_id`-only. I introduce a **platform-native player id** and a single **assertion** table where every claim is one atomic, individually-verifiable row. Never store a blob of "my season stats" — store facts you can each corroborate or kill independently.

```
# NEW — grassroots players who have no API-Football id (closes the known gap)
showcase_player
  id                uuid PK
  display_name      str
  dob               date          # PRIVATE — never in any public dict; only age-band derived
  country / region  str
  guardian_user_id  fk user_accounts  # REQUIRED if dob implies minor
  club_team_id      fk teams NULL     # their grassroots/college club once it has an account
  status            str  # active | merged_to_api_id | suspended
  merged_player_api_id int NULL       # set if later matched to an API-Football identity

# NEW — the heart of it: one verifiable fact per row
player_assertion
  id                   int PK
  subject_player_api_id int NULL           # exactly one of these two is set
  subject_showcase_id  uuid NULL
  asserted_by_user_id  fk user_accounts     # must hold an approved PlayerProfileClaim on subject
  relationship_type    str                  # snapshot of claim at assert time
  kind                 str  # match_played | goals | assists | minutes | position | clean_sheet | motm
  # match anchor (mirrors VideoMatch's free-text opponent model)
  match_date           date
  opponent_name        str
  competition          str
  home_away            str
  # payload + evidence
  value                json   # {goals:2} | {minutes:84} | {position:"LW"}
  video_link_id        fk player_links NULL  # link_type='highlight' evidence, reuses reel storage
  # derived, never written by the user
  trust_tier           str  # see (c)
  status               str  # pending | published | hidden | revoked
  plausibility_flags   json # auto-checks that fired: ["minutes_gt_100","goals_zscore_4.1"]
  created_at / updated_at

# NEW — append-only corroboration events; trust_tier is a fold over these
assertion_corroboration
  id                 int PK
  assertion_id       fk player_assertion
  source_type        str  # club_own | club_opponent | peer | footage | api_football | metadata_auto | admin
  corroborator_user_id  fk user_accounts NULL
  corroborator_team_id  fk teams NULL           # the vouching club
  video_report_id       fk video_player_reports NULL
  decision           str  # confirm | dispute | abstain
  weight             float                      # club_official=1.0, opponent=1.2, peer=0.2, footage=1.5
  created_at
```

Rules baked into the write path (extends `showcase.py`, same auth/rate-limit decorators already there):
- **You cannot assert about a player you don't own** — `_approved_claim_or_403()` already exists; every `POST /players/<id>/assertions` reuses it.
- **Everything lands `status='pending'`** and is invisible until it clears moderation, exactly like `PlayerShowcaseProfile` reverting to `pending` on edit (safeguarding default).
- Video evidence is not free-typed — it reuses the `PlayerLink` reel + the `_youtube_video_id()` extractor already in `showcase.py`, so a "video" is a canonical YouTube id or a Film Room `video_report_id`, both dedup-able.

---

## (b) The corroboration engine — attack vector → the cheap check that kills it

| Attack | What the liar does | Cheap check(s) that catch it | Automatable **day-1** | Needs **scale** |
|---|---|---|---|---|
| **Invented match** | Asserts a match that never happened | Require two *independent* parties to anchor the same `(match_date, opponent_name, competition)`; a lone anchor never rises above `self_reported`. Cross-check against any `VideoMatch` row for that club/date, and against known fixture calendars where the club maps to API-Football. Future-dated / out-of-season → auto-flag. | ✅ date sanity, VideoMatch join, "solo anchor = capped" | opponent-club confirmation, fixture-calendar coverage for grassroots |
| **Inflated goals/minutes** | 84′→90′, 1 goal→4 | Hard bounds (`minutes ≤ ~100`, goals within sane cap). Per-90 **z-score vs the player's cohort/league norm** — reuses the cohort + `radar_stats_service` machinery. Reconcile: sum of both sides' asserted goals must equal the asserted scoreline. Film Room `VideoPlayerReport.events` / `minutes_visible` cross-check when footage exists. | ✅ hard bounds, z-score flag | cross-side goal reconciliation, footage cross-check at volume |
| **Someone else's footage** | Links a highlight that isn't them | **YouTube video-id dedup** (extractor already exists) — same id on two players' reels = instant flag. Canonicalize URL. Perceptual/video fingerprint of uploaded clips vs existing `PlayerLink` reels. Kit colour / jersey number in footage vs asserted (Film Room already reads jerseys). | ✅ YouTube-id + URL dedup across `player_links` | perceptual hashing of raw uploads, kit/number vision check |
| **Age fraud** | Overage player in a youth band | Cross-check `showcase_player.dob` / API-Football `Player.birth` against asserted competition band. Guardian claim mandatory for minors. Physical-plausibility from Film Room height. Document review (proof shown to admin, **attribute stored, document not**). | ✅ DOB-vs-band cross-check where an id exists | human document review for pure-grassroots |
| **Impersonation** | User claims a player who isn't them | Existing admin-approved `PlayerProfileClaim` flow + OTP email. **Ring detection**: one user/IP/device claiming many unrelated elite players → flag. Email-domain match for `club_official`. Conflict resolution when two users claim one identity. | ✅ dupe-claim / velocity detection, OTP (exists) | manual adjudication of contested identities |

The engine is a single service (`services/assertion_trust.py`) that, on every new corroboration row, **recomputes `trust_tier` as a pure fold** and writes `plausibility_flags`. It is idempotent and cheap — same pattern as `VideoCreditLedger.balance()` being `SUM(delta)`.

---

## (c) Trust-ladder extension — the new middle rungs, and visual carriage of every number

The existing ladder has a cliff: from "Self-reported" straight to "Club-verified (footage)." Player-uploaded stats need the middle. Ordered `trust_tier` values on `player_assertion`:

1. `self_reported` — a claimed owner said so. No corroboration. **Slate badge, "Self-reported."**
2. `peer_corroborated` — ≥N teammates (each a claimed owner) confirmed. Weak (weight 0.2 each). **Amber, "Teammate-corroborated."**
3. `club_vouched` — the player's *own* verified club official confirmed via `assertion_corroboration(source_type='club_own')`. **Blue, "Club-vouched."**
4. `opponent_confirmed` — the **opposing** club confirmed the same match anchor. Strongest human signal (an opponent has no incentive to inflate your numbers). **Teal, "Opponent-confirmed."**
5. `footage_verified` — collapses into existing **Club-verified**: a `VideoPlayerReport` with `identity_confidence='human_confirmed'` on a `finalized` match backs the number. **Emerald, "Club-verified (footage)."**
6. `platform_verified` — a parallel lane: API-Football already has the fixture stat. **Emerald, "Platform stats."**

Where do they sit? `self_reported < peer_corroborated < club_vouched < opponent_confirmed < footage_verified ≈ platform_verified`. Opponent-confirmed is the highest *human* rung, sitting just below machine/footage evidence — deliberately, because opponent confirmation is adversarial and therefore trustworthy.

**Every displayed number carries its tier — enforced at the API contract, not the component.** Mirror the existing per-field confidence shape from `VideoPlayerReport.metrics` (`[{key, value, confidence, ...}]`). Every stat the showcase/scout endpoints return becomes:

```json
{ "key": "goals", "value": 2, "trust_tier": "opponent_confirmed",
  "evidence_count": 3, "sources": ["club_opponent","club_own","footage"] }
```

A single `<TrustBadge tier=...>` component (sibling to the existing emerald "Club-verified" pill in `ShowcaseSection.jsx`) maps tier→colour+label. Rule: **a bare number never renders** — no tier, no display. This is the honesty brand made literal.

---

## (d) Incentives — truth pays, lying costs

**Why tell the truth:** verified tiers are the *only* ones that unlock discoverability.
- Only `opponent_confirmed` / `footage_verified` / `platform_verified` assertions are eligible for **Scout Desk leaderboards, compare, and the weekly digest** (`scout_digest_service`). Self-reported numbers live on your own page, badged, and are **excluded from all ranking and search filters**.
- Scout Desk gains a `min_trust_tier` filter — scouts will naturally sort to verified players, so verification = eyeballs.
- A verified profile earns a persistent badge and eligibility for team newsletter inclusion (the AI generator in `agents/` may only cite `opponent_confirmed`+).
- Ties to billing: `scout_tier` entitlement gates *consuming* verified data at volume; earning verification is free — that's the growth loop.

**What happens to liars** — the mechanics already half-exist (`PlayerProfileClaim.status` has `revoked`; `PlayerFlag`/`loan_flags` has a moderation lifecycle):

```
profile_strike
  id, subject (api_id|showcase_id), user_account_id (the actor),
  assertion_id, reason, severity (minor|major), created_at, expires_at (decay)
```

- A **disputed** assertion (opponent or footage contradicts it) → auto-demote to `self_reported` (or `hidden`) + a strike on the asserting user.
- Duplicate-footage or age-fraud hit → **major** strike immediately.
- **3 active strikes → claim auto-`revoked`** and all that user's assertions on the subject go `hidden` (shadowed, not deleted — audit trail preserved). Strikes decay via `expires_at` so a reformed honest user recovers.
- Community reports route through the existing `PlayerFlag` model with a new `category='assertion'` — zero new moderation surface, admin already triages `loan_flags`.

---

## (e) Verified clubs as the scalable vouching layer — the real unlock

Solo-founder + minors means human review can't scale linearly. **One club official action must verify many players at once.** `relationship_type='club_official'` already exists in `PlayerProfileClaim`; Film Room already establishes club↔`Team` ownership via `VideoMatch.team_id` + `VideoCreditLedger`. Formalize it:

```
club_membership
  user_account_id fk, team_id fk,
  role  # official | coach
  verified_via  # email_domain | admin | film_room_owner
  status  # pending | verified | revoked
```

The leverage move — **batch match confirmation**: a verified official for Team A confirms one match roster + scoreline in a single action. That single write:
1. `club_own`-confirms every one of Team A's players' assertions for that match (club_vouched in one shot), **and**
2. auto-emits `club_opponent` corroboration for **Team B's** players who asserted the same anchor → they get `opponent_confirmed` *for free*, no work from B.

So each club that joins verifies its own squad **and** upgrades its opponents. This is the network effect that makes verification scale sublinearly with headcount — and it dovetails with Film Room: a club already paying for footage is a pre-verified vouching node, and its `human_confirmed` reports auto-corroborate assertions with no extra step.

---

## (f) Safeguarding constraints on all of it (non-negotiable, many subjects are minors)

- **Publish gate for minors:** if `dob`/API-Football birth implies a minor, an assertion may be *created* by a player-claim but only **published by a `guardian` or `club_official` claim**. Self-claim never publishes a minor's data alone.
- **Pre-moderation everywhere:** every assertion, reel item, and profile edit lands `pending` and stays hidden until admin approval — the pattern already enforced in `showcase.py` (edit → revert to `pending`).
- **DOB never leaves the server** — only a derived age *band*. `showcase_player.dob` is excluded from every public/owner dict, same discipline as the existing `public_dict()`.
- **Footage stays scoped:** Film Room video is already never public. Self-uploaded reels are YouTube-only (owner already chose to publish there) + pre-moderated; no raw minor footage is served publicly.
- **No opponent-PII leakage:** an opponent-confirmation request exposes only `(date, opponent_name, competition, scoreline, jersey number)` — never the minor's name/contact. Opposition players stay numbers-only, exactly as `VideoRosterEntry` already enforces ("opposition is numbers-only and never gets roster rows").
- **Right to erasure + no fabrication:** revocation shadows (never fabricates a correction); nothing is ever auto-generated as if self-reported. Honesty brand holds.

---

## Build order (what ships without scale vs what waits for it)

**Day-1, fully automatable (no new headcount):**
- `player_assertion` + `assertion_corroboration` + `showcase_player` tables; assertion write endpoints reusing `_approved_claim_or_403` and `_youtube_video_id`.
- `assertion_trust.py` fold: hard-bound plausibility, per-90 z-score vs cohort, solo-anchor cap, future/out-of-season rejection.
- **YouTube-id + URL dedup** across `player_links` (extractor already exists) — kills reused-footage cheaply.
- DOB-vs-competition-band cross-check where a `player_api_id` exists.
- Claim-velocity / ring detection on `PlayerProfileClaim`.
- Per-field `trust_tier` in the showcase/scout API contract + `<TrustBadge>` component; `min_trust_tier` filter in Scout Desk.
- `profile_strike` + auto-demote-on-dispute; community reports via `PlayerFlag(category='assertion')`.

**Needs scale (clubs + volume, staged behind Film Room adoption):**
- `club_membership` + batch match confirmation (the opponent-confirmed cross-emit).
- Perceptual/video fingerprinting of raw uploads and kit/jersey vision cross-check.
- Cross-side goal-reconciliation across two clubs' assertions.
- Human document review for pure-grassroots age verification.

**Files to extend (not create new subsystems):** `models/showcase.py` (+`models/assertion.py`), `routes/showcase.py`, `services/` (`assertion_trust.py`), reuse `PlayerLink`/`PlayerFlag`/`VideoPlayerReport`/`scout_digest_service`, and the emerald-badge pattern in `ShowcaseSection.jsx`. New Alembic migration chaining off `aw19`.

The through-line: a lie is only worth telling if it buys discoverability. Here, discoverability is gated behind adversarial corroboration (opponents, footage, machines) that a liar cannot manufacture — so the cheapest path to being seen is to be honest.