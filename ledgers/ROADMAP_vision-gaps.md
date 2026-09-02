# ROADMAP — Platform Priorities (vision-gap remediation)

Created 2026-07-16 from a six-perspective gap-analysis panel (marketplace design,
legal/safeguarding, monetization, competitive landscape, repo audit, growth loops)
plus a completeness critic — 48 findings, arbitrated. Raw panel evidence:
`ledgers/research/vision-gap-panel-2026-07-16.json`.

Parent: `CONTINUITY.md`
Related: `ROADMAP_talent-showcase-vision.md`, `CONTINUITY_grassroots-funding.md`,
`CONTINUITY_video-analysis.md`, `CONTINUITY_talent-platform-next.md`,
`CONTINUITY_scout-data-attribution.md`, `CONTINUITY_ios-app.md`
Owner: MJ (product decisions); implementation dispatched per phase.

## The one-paragraph thesis

The whitespace is real — nobody combines verified young-talent data + club funding
+ child-safe handling (TransferRoom is 18+ pro-facing, Tonsser is unverified,
Snap! Raise has no football context, Wyscout has no funding) — but each pillar
alone loses to a funded incumbent. So: launch **adults-only** to reach revenue and
close the marketplace loop fast, build the trust floor that is non-delegable
either way, then expand **down** into the under-18 layer deliberately — that
expansion is the moat, entered with machinery instead of exposure.

## Decision records

Status (updated 2026-07-16): **D1/D2 confirmed in principle** — MJ ordered the
full-circle build, which proceeds on the adults-only participation cut and the
attestation-plus-floor Film Room posture. **D5 superseded by MJ**: the iOS app
is built out NOW as the full-circle surface (see
`ledgers/CONTINUITY_full-circle.md`); notification plumbing folds in as needed.
D3/D4 remain open (not blocking this track). **Execution model (MJ directive):
all suitable implementation runs on the actual Codex CLI (Sol); Fable
orchestrates, plans, reviews, and checks Codex at intervals.**

### D1 — Adults-only PARTICIPATION at launch (sharpened)

The cut is on **participation, not on the editorial database**:

- 18+ only: accounts, profile **claims**, contact/introductions, user-submitted
  media, donations, club-manager grants. Enforced server-side against known
  `birth_date` (API-Football gives us DOBs); unknown DOB = treated as minor =
  not claimable until age is verified.
- Editorial tracking of academy players (many minors) CONTINUES — public pages
  for U18s show provider-covered fixture data only (newspaper posture): no
  claiming, no contact affordance, no user-submitted media, no commentary.
- Revisit at Phase 5 (guardian-mediated expansion).

**What this buys:** the contact rail un-gates (no guardian mediation needed for
18+ ↔ verified-scout intro), COPPA verifiable-parental-consent machinery is
deferred, claim flow needs an age gate but not a guardian flow, Film Room v1
targets adult football. The marketplace loop can close in v1.

**What this does NOT fix (non-delegable regardless of 18+):**
| Still required | Why |
|---|---|
| Erasure / opt-out / takedown path | We still PROFILE minors editorially (TrackedPlayer, shadow profiles). A guardian's "delete my child" is a legal right we currently cannot honour. |
| Illegal-content (CSAM) detection + reporting process on uploads | Provider duty (18 U.S.C. 2258A); cannot be contracted away. |
| Donation-platform registration (CA AB 488 + ~40-state charitable solicitation) | About charities/solicitation, not minors. Gate on money movement (funding F3). |
| API-Football license confirmation for paid redistribution | Sole data source; a termination takes down everything at once. |
| Own data correctness (journey mislabels) + correction/dispute path | Publishing wrong "verified" facts about named minors is worse than an Instagram reel. |

### D2 — Film Room consent: club attestation + indemnity, NOT full onus transfer

MJ's proposal: responsibility on coaches/clubs to ensure no minors in footage, or
that minors consented — "legal onus on them." Assessment: **necessary layer, not
sufficient.** What a contract clause does and doesn't do:

- DOES: required upload-time attestation ("everyone in this footage is 18+ OR has
  documented guardian consent"), indemnification, and a takedown-defense posture.
  Publishing is gated on attestation (default unpublished).
- DOES NOT: remove platform obligations. Under GDPR we are processor — and
  controller for derived clips/analytics we publish on profiles; CSAM reporting
  attaches to the provider; publicity/image-rights claims target whoever hosts
  and monetizes; and "the contract said it was the club's fault" does not survive
  the headline. Regulators and journalists come to the platform first.
- Practical note: adult open-age football legally fields 16–17-year-olds, so the
  attestation must be per-upload and cover "or has documented guardian consent,"
  not just "adult league."
- Keep the already-designed posture: own-team-only reports, opposition anonymous,
  90-day recognizable-footage retention (see `CONTINUITY_video-analysis.md`).

### D3 — Donation fee becomes an optional donor tip (recommended)

GoFundMe charges 0% platform fee on youth-sports fundraisers; Zeffy markets 0%
for teams. A mandatory skim off kids' football donations is a headline risk that
poisons the trust brand the whole platform depends on. Restructure as
donor-chooses-tip (Givebutter model): club receives 100% less card processing.

### D4 — Beachhead: verified-club funding + recurring club bundle (recommended)

Its incumbents (Snap! Raise, Vertical Raise) have zero football verification;
Wyscout/TransferRoom have zero funding. Clubs demonstrably pay recurring
($800–1,300/yr Veo benchmark). Bundle: funding registry + Film Room match
allotment + roster/showcase tools as one club subscription. Scout Pro gets a
committed launch price + beta-grandfather path NOW (the "free during beta,
price at launch" page is training users to expect $0). Film Room billing stays
OFF until identity-merge accuracy clears a bar (currently the documented R&D
risk); at ~$25/match with human review it is also likely below cost — re-price
or bundle.

### D6 — Contact routing is contract-status-aware; club-in-the-loop for contracted players (MJ-confirmed 2026-07-17)

The 18+ cut solved child safety, not **tapping-up**: approach rules (FIFA RSTP +
national FA/league rules) bar approaching a CONTRACTED player without the club's
consent — adults included. Routing, powered by journey status + claim-time
attestation (free_agent | contracted | unknown):
- **Free agent / released / out of contract → direct** scout↔player (the rail as
  built). The platform's sweet spot; no rule engaged. Later refinement: relax
  within 6 months of contract expiry (RSTP 18.3).
- **Contracted, club ON-platform → club-in-the-loop**: the club's verified
  manager(s) join the request as participants with an explicit consent step
  before messaging opens. Also creates the club engagement loop + club-bundle
  surface (D4).
- **Contracted, club OFF-platform → scout attestation** that permission has been
  or will be obtained + tapping-up warning + club email notice where known; all
  recorded in the audit trail.
- **Unknown status → treated as contracted** (safe default); attestation
  contradictions vs journey data get flagged for admin review, not silently
  trusted.
Implementation: FC-B3 in `CONTINUITY_full-circle.md`; PR #651 held until it
lands so the rail merges in corrected shape.

### D5 — iOS app P4 resumes after Phase 3 (recommended)

The app is a consumption surface; its payoff arrives when there is something to
push. Park at P3-complete. P4 becomes push notifications + "scouts are watching
you" + digest deep links — a far stronger P4 than more browse screens.

## Phases

### Phase 0 — Paper + decisions (days, mostly MJ + counsel; blocks everything)
- 0.1 Confirm/amend D1–D5.
- 0.2 API-Football license: written confirmation that paid-tier surfacing of
  cached stats is licensed. (Existential single-source risk.)
- 0.3 ToS/attestation/indemnity drafting: 18+ participation terms, Film Room
  upload attestation, self-reported-content disclaimer.
- 0.4 Donations regulatory scoping: CA AB 488 platform registration + state
  charitable-solicitation plan + 501(c)(3)-vs-for-profit labeling rules
  ("donation" wording only for actual charities). Gate for funding F3 money
  movement — registry work (PR #636) is unaffected.
- 0.5 Commit Scout Pro launch price + grandfather terms (update /pricing copy).

### Phase 1 — Trust floor (non-delegable; ship before any contact or money)
- 1.1 Account deletion + data-subject-request rail (export + erasure) for
  UserAccount and everything hanging off it. Also remove/replace the
  unauthenticated boilerplate delete route (`routes/user.py`, unregistered but
  wrong-model and unauth'd). **S–M**
- 1.2 Player opt-out/takedown: per-player suppression flag honored across
  scout/showcase/shadow/newsletter surfaces; guardian-reachable request path.
  Covers shadow-tracking exposure (profiles minted on follow, no consent). **M**
- 1.3 Report/flag button on player profiles, showcase content, and club
  programs → moderation queue (single-admin OK for now, queue is the point). **S–M**
- 1.4 18+ claim gate: DOB-enforced claimability; unknown DOB requires age
  verification before claim approval. **S**
- 1.5 Data-correction/dispute path on player pages ("this is wrong" → review
  queue) + finish the known correctness debts: released-status systemic
  mislabel (~1375 rows, designed not implemented), scout stat-attribution
  P1/P3 prod repair, **Aug 1 season-rollover guard (dated deadline)**. See
  `CONTINUITY_scout-data-attribution.md`. **M**
- 1.6 Ops floor: support inbox, safeguarding/incident runbook, Stripe-dispute
  runbook (solo founder = single point of failure for time-boxed duties). **S**
- 1.7 Illegal-content posture for uploads: hash-scan or vendor API on Film Room
  uploads + NCMEC reporting process documented in the runbook. **M** (can land
  with Phase 4 Film Room billing, but design it here)

### Phase 2 — Close the loop (the marketplace becomes a marketplace)
- 2.1 Scout verification (lightweight credential/affiliation review → "verified
  scout" badge). Not a child-safety gate anymore (D1) but the demand-side trust
  signal players list themselves FOR. **M**
- 2.2 Contact/introduction rail: verified scout → 18+ claimed player/club;
  audit-logged, rate-limited, report-button integrated. **M**
- 2.3 Outcome capture: intro → contact → trial → signing, even self-reported.
  This is the proof metric everything else prices against. **S–M**
- 2.4 Player-side return signal: "N scouts viewed / watchlisted you this week"
  on claimed profiles (aggregate, not identity, unless scout opts to reveal). **S–M**

### Phase 3 — Engagement plumbing (features stop being write-only)
- 3.1 **Off-season content mode FIRST — it is July now**: transfer-window
  tracker, season retrospectives, "players to watch," academy intake news, so
  newsletters/digests/pulse have something to say without fixtures. **S–M**
- 3.2 Scheduler for digests (off-container per prod-capacity invariant — the
  0.5-CPU container must not run fan-out sends). **M**
- 3.3 Transactional notifications service: claim decisions, followed-player
  events, `notify_when_fundable` (currently stored-but-never-fired). Email
  first; push lands with iOS P4. **M**
- 3.4 Shareable verified player card + per-player og:image (the one native
  viral loop: players posting verified stats to Instagram/TikTok). **S–M**
- 3.5 SEO: sitemap + prerender for player/showcase/newsletter routes (SPA is
  currently invisible to Google). **M**
- 3.6 Newsletter → marketplace bridges: follow/claim CTAs and player-page deep
  links inside newsletter content. **S**

### Phase 4 — Revenue rails (in this order)
- 4.1 Club bundle (D4): club dashboard (donations, analytics-ready, profile
  views) + subscription billing. **M–L**
- 4.2 Scout Pro billing wiring at the committed price (0.5). **M**
- 4.3 Funding F3 money movement: checkout + optional-tip model (D3) + donor
  update/impact loop (program updates feed, receipts, recurring giving) +
  roster-driven campaign mechanic (Snap! Raise-style demand engine, adapted
  minor-safe: clubs mobilize their own supporter networks). Gated on 0.4. **L**
- 4.4 Film Room billing: only after identity-accuracy bar (VLM
  entity-consistency gate, `CONTINUITY_video-analysis.md` F1) + re-price
  (bundle-first per D4). **L (R&D-gated)**
- 4.5 Grassroots attested match-data entry rail (manual stats w/ provenance
  labels) so funding-registry clubs outside API-Football coverage have a
  verified-ish data path — without it the registry sells trust it cannot
  deliver to its own audience. **M**

### Phase 5 — Expand down (the real moat, entered deliberately)
- 5.1 Guardian-mediated claims + verifiable parental consent (COPPA machinery).
- 5.2 U18 visibility limited to verified scouts; guardian-mediated contact only.
- 5.3 Youth Film Room attestation/consent flows (per-player consent registry).
- 5.4 Camera-ecosystem ingestion (Veo/Trace/Pixellot import instead of
  re-upload) — clubs already film there; meet the footage where it lives.

### Parked / ambient
- Accessibility pass (EAA applicable since 2025-06; do before donations GA —
  an inaccessible checkout loses money and invites complaints).
- Agent-side product: design the pay-to-play line FIRST (agents may buy
  discovery tools; never placement/ranking for a player). Do not build until
  the line is written down.
- Data-licensing rail: blocked on 0.2 license terms.
- Standing ops debts (tracked elsewhere, listed for priority honesty):
  Supabase prod DB password rotation (leaked 2026-06-13,
  `project_rotate_supabase_password`); Ecuador/Colombia crawl quota decision.

## Sequencing note

Phases 0–1 are prerequisites, not products — small, mostly S/M items. Phase 2
is where the product visibly changes (the loop closes). Phase 3.1 is
calendar-urgent (off-season is NOW). The Aug 1 rollover guard (1.5) is the only
hard-dated engineering item. iOS resumes after Phase 3 (D5).

## Status

- 2026-07-16: Ledger created from panel arbitration. D1–D5 awaiting MJ
  confirmation. No implementation dispatched yet.
