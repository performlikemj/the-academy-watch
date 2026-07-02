# Roadmap: Two-Sided Talent Platform (Player Showcase × Club Film Room)

> Vision (MJ, 2026-07-02): a place where **players worldwide have a profile page that
> lets them show their talents** — uploaded YouTube video, commentary, verified stats —
> to increase **discoverability + engagement**; and where, at the **club level, verified
> clubs upload footage and get stats about the players in it** (Film Room — "also needs
> enhancements").
>
> This roadmap sequences that vision against what already ships. It does not restate the
> two live ledgers it depends on:
> - **Scout discovery + global footprint** — `CONTINUITY_global-talent-platform.md` (shipped)
> - **Film Room / video analysis** — `CONTINUITY_video-analysis.md` + `../docs/film-room.md`

## Strategic thesis

The commodity is a highlight reel — every player already has Instagram. The **moat is
verification**: stats pulled from real fixtures (not self-reported) and footage-derived
stats vouched by a club. So the play is: **lead with verification, package it in a
showcase profile, and let Film Room feed club-verified evidence into that profile.** The
two pillars are one flywheel — Film Room manufactures the trust that makes a showcase
credible.

## What already exists (do NOT rebuild)

- **Verified stats primitive** — `PlayerPage.jsx` renders `compute_stats()` totals, per-90s,
  radar, career journey, academy stats. This is the trust layer; it's real.
- **Scout discovery layer** — `/scout` browse/filter/leaderboards/compare/watchlist, global
  16-league footprint, provenance-clean roster (own-academy-only, real names, ages). All
  shipped in the global-talent ledger.
- **`PlayerLink`** (`models/league.py:1818`) — moderated user-submitted URLs typed
  `article | highlight | social | stats | other`, `pending→approved` flow, upvotes. A
  highlight reel already has a data home; it just isn't surfaced as an embedded showcase.
- **Film Room Phase A concierge** — full CV pipeline (detect→track→cluster→jersey-read→
  chain→human tag-review→per-player report) + RLHF-style learning loop + admin routes.
  Honestly gives identity + on-camera coverage today.

## The gaps (what the vision needs that doesn't exist)

**Pillar 1 — player self-showcase:** no profile ownership/claiming, no embedded video
showcase (YouTube is a stored URL, not a curated reel), no commentary/endorsement/follow
layer. Everything today is admin/journalist-curated, not player-owned.

**Pillar 2 — Film Room enhancements:** physical metrics (distance/speed/sprints/heatmap)
blocked on homography; touches need ball association; identity coverage/merge quality is
the documented core R&D problem (over-merge; VLM entity-consistency gate lifted 17.5→70%);
still concierge-only (no self-serve accounts, billing unwired, crops/boxes dev-only in prod).

## Phases

### Pillar 1 — Player showcase profile
| ID | Phase | Effort | Risk | Depends on |
|----|-------|--------|------|-----------|
| P0 | **Surface what exists** — a "Showcase" block on PlayerPage: embed approved `PlayerLink` highlight URLs as YouTube players, lead with verified stats + radar, journey timeline. No auth, no new models. | S | low | — |
| P1 | **Claim & curate** — player/agent identity + claim flow; owner curates an ordered highlight reel (self-submit YouTube), bio/about, self-attested position/foot/height **clearly marked self-reported vs verified**; moderation + anti-spam. | M | med | P0 |
| P2 | **Engagement + discovery** — commentary/endorsements (verified scouts/coaches), follow/notify, public "discover talent" search (extend the scout browse toward a consumer surface). | M | med | P1 |

### Pillar 2 — Club Film Room (extends the video-analysis ledger)
| ID | Phase | Effort | Risk | Depends on |
|----|-------|--------|------|-----------|
| F0 | **Prod-harden output** — persist crop JPEGs + per-frame boxes to Blob (`serve_crop` is 501 in prod today), CSP `media-src`. Makes concierge output actually reviewable in prod. | S–M | low | — |
| F1 | **Identity / merge quality** — the credibility blocker: over-merge; ship the VLM entity-consistency gate (17.5→70% precision). Reports aren't sellable until tracklets are clean. | L | high (R&D) | F0 |
| F2 | **Physical metrics via homography** — unlock distance/speed/sprints/heatmap ("pending calibration" today). The "wow", but only once identity is trustworthy. | L | med | F1 |
| F3 | **Ball association → touches** — beta → real. | L | med | F1 |
| F4 | **Self-serve + billing** — graduate from concierge: club accounts, credit purchase (Stripe scaffold + `scout_tier` posture already exist). | M | med | F0 |

### The flywheel
| ID | Phase | Effort | Risk | Depends on |
|----|-------|--------|------|-----------|
| X | **Film Room → showcase** — a finalized per-player report attaches a **club-verified** clip + stat badge to that player's showcase profile. The unique differentiator: verified footage-derived evidence on the profile, not self-reported. | M | med | P1 + F0 |

## Recommended sequence + rationale

1. **P0** — cheap, uses data already in the DB, foundation for everything, ships in ~a day.
2. **F0** — small prod-hardening; makes Film Room actually usable in prod AND unblocks the flywheel.
3. **P1** — the headline consumer pillar; delivers "players show their talents" literally.
4. **X** — with P1 + F0 done, the differentiator lights up for free-ish.
5. **Then branch by bottleneck:** if the constraint is *demand-side engagement* → **P2**;
   if it's *supply-side credibility of Film Room* → **F1** (then F2/F3/F4).

Lead with cheap high-leverage surfacing, harden the moat's output, build the consumer
headline, wire the differentiator — and defer the expensive CV R&D (F1/F2/F3) and
productization (F4) until profiles prove demand.

## Open decisions for MJ (steer before P1)

- **Who can claim a profile?** player-only / player + agent / club-vouched. Determines the
  auth + verification model.
- **Safeguarding (minors).** Many tracked players are academy = minors. Player-uploaded
  media + open commentary is a real constraint (mirrors Film Room's opposition-numbers-only
  consent posture). Likely needs age-gating / guardian consent / restricted commentary.
- **Self-reported vs verified.** How hard to visually separate on the profile (the whole
  moat is that a scout can trust which is which).
- **Monetization shape.** Is the showcase free top-of-funnel, with Film Room + Scout Pro the
  paid layers? (`scout_tier` + `/pricing` already assume paid Scout Pro / Film Room.)

## Status

- **EXECUTING (2026-07-02)** — MJ set /goal "carry out the vision" (Fable 5 orchestrating,
  Opus 4.8 subagents). This session builds **P0 + P1 + X** on branch
  `feature/talent-showcase` (worktree, isolated from uncommitted Film Room work).
- Open decisions resolved with conservative defaults (MJ can revise):
  - **Claiming:** any authenticated UserAccount may *request* a claim; **admin approves**
    (verification stays human). Player + agent both allowed via claim `relationship` field.
  - **Safeguarding:** no open commentary on claimed minor profiles in this slice —
    engagement layer (P2) deferred; curated links remain admin-moderated before display.
  - **Self-reported vs verified:** hard visual separation — self-reported fields carry an
    explicit "self-reported" badge; verified stats keep their existing treatment.
  - **Monetization:** showcase is free top-of-funnel (Scout Pro / Film Room stay the paid
    layers per /pricing).
- Pointer added to master `CONTINUITY.md` ✓. F0/F1+ remain with the video-analysis ledger.
- **P0 + P1 + X SHIPPED to `feature/talent-showcase` (2026-07-02)** — built multi-agent,
  adversarially reviewed (8 findings fixed), 40 tests, live-verified end-to-end (demo:
  player 403064 H. Amass). See `docs/showcase.md` for the operator guide. Remaining
  phases: P2 (engagement/discovery) and the Film Room track (F0 prod-hardening → F1
  identity quality → F2 homography → F3 touches → F4 self-serve+billing).
