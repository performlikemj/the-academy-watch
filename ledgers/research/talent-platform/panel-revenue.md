This is a strategy/design question, not a coding task. The user (via the orchestration script) wants me to design the year-round revenue architecture. I have enough context. Let me not over-engineer with tool calls — I should verify a few key entities to be concrete, but the ask is clearly for a written design deliverable.

Let me produce the deliverable directly. I'll return well-structured markdown.

# The Academy Watch — Year-Round Revenue Architecture

## Framing: trust is the moat, so payment must never buy trust

The one rule that governs every line below: **money can buy reach, tooling, and speed — never a verification badge or a stat.** The trust ladder (Self-reported < Claimed < Platform-verified < Club-verified) is the product's whole reason to exist. So paywalls sit on *distribution, aggregation, and workflow*, never on *the truth layer*. A paid player showcase can rank higher in a "new talent" carousel; it can never turn a self-reported goal tally emerald. Keep that line and the revenue compounds; cross it once and the CSV export becomes worthless because buyers stop believing the data.

---

## (a) The Payer Map — who pays, for what, on which existing surface

Five payer segments, each tied to a concrete surface that exists today or is one PR away.

### 1. Scouts / agents / recruitment analysts — **Scout Pro subscription**
The `scout_tier` column already exists (free default), billing not wired. This is the first switch to flip because the scaffold is done and the value is already built and sitting behind no wall.

What they pay for (all live surfaces in Scout Desk):
- **Watchlist beyond the free cap.** Free = keep the visible cap low (say 25 players in `ScoutWatchlistEntry`); Pro = the full 200 cap. The 200 cap is already the model constant — just gate the lower number for free.
- **The weekly digest email** at *their* cadence and *their* segmentation (this is where MJ's ask #1 — smart grouping — becomes a paid feature; see below).
- **CSV export** — free gets 25 rows / watermarked; Pro gets full export with per-column provenance & confidence fields.
- **Compare** — free compares 2 players; Pro compares up to 6 and saves comparison sets.
- **Saved filters / alerts** — "notify me when any U19 CB in Ecuador crosses 900 league minutes." This is the retention hook that makes the subscription year-round rather than window-only.

Segment surface (MJ ask #1) becomes the Pro anchor feature. New model:

```
SavedSegment
  id
  user_account_id        -> UserAccount
  name                   "Ecuador+Colombia U20 forwards I follow"
  kind                   enum: watchlist_subset | club_academy | league_region | dynamic_filter
  filter_json            {regions:[...], leagues:[...], positions:[...],
                          age_max:20, min_minutes:600, watchlist_only:bool}
  player_api_ids         int[]   -- for hand-picked static sets
  digest_cadence         enum: off | weekly | biweekly | window_only
  created_at / last_sent_at
```

A `SavedSegment` is the join between "watchlist" and "newsletter." The existing digest generator (admin-triggered, cursor-paged) gets refactored to iterate `SavedSegment` rows instead of one global digest. Free tier: 1 segment, weekly. Pro: unlimited segments, any cadence, including "club X's whole academy" and "random players I follow in Ecuador + Colombia."

### 2. Clubs (grassroots / college / academy) — **Film Room credits + verification SaaS**
Two shapes, deliberately:
- **Pay-per-match credits** ($25/match design already set) for the concierge CV pipeline. This is the wedge for clubs with video but no stats — the explicit target. Credits are the right shape here because usage is spiky and seasonal (a club uploads a batch after a tournament weekend, nothing for a month).
- **Club account / roster SaaS** (near-term gap: "no club accounts"). A club seat unlocks: managing their Film Room roster entries, bulk claiming their own academy players' profiles (guardian-flow for minors still enforced), and a **club-branded verified page** — the emerald "Club-verified" appearances aggregated into a shareable squad page. This is a seat/subscription, not credits, because it's continuous.

The critical trust guard: a club paying for Film Room does **not** get to mark identities themselves as club-verified without the human-tag-review step. They pay for the *pipeline and the workflow*, and verification remains an earned output of that workflow, not a purchasable status.

### 3. Players' families / agents — **Claimed profile + Showcase boost (trust-safe)**
Talent Showcase (PR #565) already lets players/agents/guardians claim profiles and curate reels + self-reported bio, all pre-moderated and badged "Self-reported." Monetization here is the most dangerous — get it wrong and you're selling fake credibility to parents of minors. So:

**What families can pay for (reach & tooling, never trust):**
- **Showcase Boost** — placement in a "New on the Watch" / "Rising" discovery carousel and inclusion in scout-facing *discovery* segments. This is advertising placement, clearly labeled "Promoted," exactly like it's clearly labeled "Self-reported." A boosted profile with zero platform-verified data still shows zero verified data — boost buys *eyeballs on the profile*, not a change to what the profile says.
- **Extra reel slots / a polished profile theme / a downloadable one-pager** (auto-generated PDF from their verified + self-reported data with provenance badges intact).
- **Priority moderation** (24h vs standard queue) — you're selling *your own scarce moderation time*, which is honest.

**Hard guardrails (write these into policy and code):**
- Minors: boosts on a minor's profile require a verified guardian claim and are **off by default**; safeguarding overrides revenue every time.
- A "Promoted" tag is non-removable and visually equal-weight to "Self-reported."
- Boost never touches ranking on *verified* leaderboards — only *discovery* surfaces. Platform-verified and Club-verified leaderboards stay pure. This is the pay-to-win firewall.

### 4. Fans — **team newsletter premium + web version support**
UserSubscription (email subscriptions to teams) + public newsletter web versions (public_slug) are the surface. Fans are low-ARPU but high-volume and free-to-acquire — treat as top-of-funnel with a thin paid tier:
- Free: the weekly team newsletter, web versions.
- **Supporter tier** ($3–5/mo): early access, an ad-free/founder-badge web version, and the ability to subscribe-and-segment (fan version of SavedSegment: "just the loan players from my club who played this week"). This also closes the known "no subscribe-from-team-page UX" gap — the subscribe CTA on TeamDetailPage becomes a funnel into both free email and the supporter tier.

### 5. Media / sponsors / affiliates — **sponsored newsletters + affiliate rails**
- **Sponsored newsletter placement** — a boot brand, an agency, a football-data course sponsors a region's weekly digest. Priced per-send on audience size. The Gmail-safe template already has an Academy Watch section; add a clearly-labeled sponsor slot.
- **Affiliate** — streaming/ticketing/kit links inside player journeys and fixtures. Low effort, always-on, non-corrupting.
- **Data licensing (later):** the provenance-clean, own-academy-only dataset across 16 leagues is genuinely rare. A read-only API tier for media/data shops is a large future line — but only once volume justifies support load. Not first-$10k territory.

---

## (b) Price points, shapes, and honest math to $10k MRR

| Line | Shape | Price | Why this shape |
|---|---|---|---|
| Scout Pro | Subscription | **$19/mo** or $180/yr | Continuous value (alerts, segments, digests); recurring = predictable MRR |
| Scout Pro Team (agency) | Seat-based | **$49/mo** for 3 seats | Agencies share watchlists |
| Film Room | Credits | **$25/match**, 5-pack $100 | Spiky, seasonal usage |
| Club account | Subscription | **$99/mo** (incl. 2 match credits) | Continuous roster + branded page |
| Showcase Boost | Subscription | **$9/mo** per profile | Reach, clearly promoted |
| Showcase one-pager PDF | One-off | **$15** | Tooling |
| Fan Supporter | Subscription | **$4/mo** | Volume top-of-funnel |
| Sponsored digest | Per-send | **$150–500/send** | Depends on segment size |

**Rough mix to first $10k MRR** (pick the realistic-and-boring path — scouts + clubs carry it, showcase/fans are gravy):

- 150 Scout Pro @ $19 = **$2,850**
- 10 Scout Pro Team @ $49 = **$490**
- 25 Club accounts @ $99 = **$2,475**
- Film Room credits: 120 matches/mo @ $25 = **$3,000** (this is lumpy — treat as ~$3k/mo trailing average across tournament windows)
- 80 Showcase Boosts @ $9 = **$720**
- 100 Fan Supporters @ $4 = **$400**
- 2 sponsored digests/mo @ ~$250 = **$500**

**Total ≈ $10,435 MRR.** The load-bearing lines are Scout Pro (150 subs) and Clubs (25 accounts + credit volume) — together ~$8.3k. Everything else is diversification, not the foundation. 150 paying scouts against ~3,400 tracked players across a global scout/agent population is conservative if the digest + alerts genuinely save them time. 25 grassroots/college clubs is the harder number and depends entirely on the concierge pipeline staying cheap to run (it runs on Apple Silicon locally today — margin is good until you must scale off-Mac).

Margin note tied to your infra memory: prod is tiny (0.5 CPU/1Gi) and journey re-syncs already flap health. Film Room CV must stay **off-container** (local Apple Silicon / a dedicated worker), and credits must be priced to cover the human tag-review minutes, which are your real COGS — not compute. $25/match only works if review is <20 min/match; watch that.

---

## (c) Seasonality map — so revenue never sleeps

The core insight: your 16 leagues / 4 regions span calendars that *deliberately overlap*, so you're never fully dark. European (Aug–May), Brazil/MLS/Nordic (Feb–Dec), Argentina (year-round), and youth tournaments constantly. Match each window to the surface that monetizes it.

| Month | Active competitions | Scout demand | Primary monetized surface |
|---|---|---|---|
| **Jan** | Europe mid-season; **Jan transfer window**; Argentina | **PEAK** (window) | Scout Pro (alerts/segments spike), sponsored digests |
| **Feb** | Europe; **MLS + Brazil + Nordic kick off** | High | Scout Pro; new-season Showcase Boost push |
| **Mar** | Europe run-in; S.Am/US early | Med | Film Room (spring youth tournaments) |
| **Apr** | Europe title/relegation; **youth tournaments** | Med-High | Film Room credits (tournament weekends) |
| **May** | Europe season **ends**; S.Am/MLS mid | Med | Club SaaS (end-of-season squad review pages) |
| **Jun** | **Summer window opens**; youth showcases, tournaments | **PEAK** (window) | Scout Pro + Showcase Boost + Film Room all fire |
| **Jul** | Summer window; pre-season; US/Brazil mid | **PEAK** | Scout Pro; sponsored pre-season digests |
| **Aug** | **Europe kicks off**; window closes | High | Scout Pro (new-season watchlists); Fan Supporter renewals |
| **Sep** | Europe early; S.Am/MLS run-in | Med | Fan newsletters; steady Scout Pro |
| **Oct** | Europe; MLS playoffs approach | Med | Film Room (fall college/youth) |
| **Nov** | Europe; **Brazil/MLS/Nordic seasons END** | Med | Club SaaS (S.Am/US end-of-season review); Film Room batch |
| **Dec** | Europe congestion; **Jan window pre-buzz** | Rising | Scout Pro (pre-window prep); gift subs |

**The anti-seasonality design principles:**
1. **Two transfer-window super-peaks (Jan, Jun–Jul)** are your Scout Pro acquisition + sponsored-digest revenue spikes. Front-load marketing and annual-plan pushes into December and May.
2. **Film Room is counter-cyclical to European scouting** — youth tournaments and college/grassroots seasons (spring + fall in N.America, year-round elsewhere) fill the summer/autumn troughs when top-league scouting cools.
3. **South America + Argentina year-round coverage** is the literal hedge: when Europe sleeps (Jun–Jul), Brazil/MLS/Argentina are mid-season, so the "random players in Ecuador + Colombia" segment stays valuable and the digest keeps sending.
4. **Annual plans** convert spiky window-demand into flat MRR — push $180/yr Scout Pro hardest at the two peaks so a window-motivated buyer pays for the whole trough.

---

## (d) What stays FREE forever — and exactly where each wall sits

**Free forever (the top-of-funnel — never wall these):**
- All **public player profiles** (verified stats, journey, radar, injuries) — this is the SEO/discovery engine and the honesty proof. Walling it kills the moat.
- **Self-reported & Claimed** showcase profiles and reels — creating your profile is free; safeguarding requires it be free so guardians aren't priced out of controlling a minor's page.
- **Basic team newsletter** (email + public web version).
- **Scout Desk browse / filter / leaderboards** at baseline depth.
- **One SavedSegment, weekly digest.**

**Exact paywall coordinates:**

| Wall sits at | Free side | Paid side |
|---|---|---|
| Watchlist cap | 25 entries | Full 200 (`ScoutWatchlistEntry`) |
| SavedSegments | 1, weekly | Unlimited, any cadence |
| Alerts | none | threshold/event alerts |
| CSV export | 25 rows, watermarked | full + provenance columns |
| Compare | 2 players | 6 + saved sets |
| Film Room | view public results | upload/process match (credits) |
| Club page | individual verified appearances | aggregated branded squad page (seat) |
| Showcase | profile + reels | Boost placement, extra slots, PDF, priority moderation |
| Newsletter | weekly team digest | supporter early-access/segmented/ad-free |

The principle: **the truth layer is free and open; the aggregation, automation, distribution, and workflow layers are paid.** You never charge to *see* a verified fact — you charge to *collect, monitor, export, and act on* many of them efficiently.

---

## (e) Sequencing — which switch flips first

Order is dictated by "what scaffold is done" × "what has value already built behind no wall."

**Switch 1 — Scout Pro billing (weeks, not months).** The `scout_tier` column exists; Stripe is already integrated for writer payouts, so the Stripe customer/subscription plumbing and webhook handling largely exist. The value (watchlist, digest, CSV, compare) is *already shipped and currently free*. This is pure wall-placement + a checkout flow. Highest ROI, lowest build. Ship the `SavedSegment` model with it — segments are the feature that justifies $19/mo and directly answers MJ ask #1. **Flip this first.**

**Switch 2 — Film Room credits.** Design ($25/match) and pipeline exist; billing is manual today. Wire a Stripe credit-purchase + a `MatchCredit` ledger against the account, decremented when a match enters the pipeline. Keep concierge/human-review in the loop; automate only the *payment*, not the *verification*. Second because it needs a credit ledger and the club-account concept, slightly more build than flipping a tier column.

```
MatchCredit
  id, account_id, credits_remaining, source (purchase|club_plan|grant),
  stripe_payment_intent_id, created_at
MatchCreditUse
  id, credit_id, film_room_match_id, used_at
```

**Switch 3 — Club accounts (SaaS seat).** Requires building the missing "club account" entity (known gap: concierge-only today). Bundles Film Room credits + branded verified page. Third because it's net-new account infrastructure, but it's where the durable $99/mo MRR and the 25-club anchor number live.

**Switch 4 — Showcase Boost.** Talent Showcase just shipped (#565); let the moderation flow and trust badging settle before layering paid placement, precisely because this is the trust-risk line and the minor-safeguarding line. Build the "Promoted" surface and guardian-gating carefully. Fourth on purpose.

**Switch 5 — Fan Supporter + Sponsored digests + affiliates.** Lowest per-unit revenue, so last — but affiliates are near-zero-effort and can go in anytime as a background line. Fan Supporter pairs naturally with finally shipping the subscribe-from-TeamDetailPage CTA.

**Net:** flip Scout Pro now (it funds the rest), Film Room credits next (highest-price-per-transaction, target segment), club SaaS third (durable MRR anchor), then showcase and fan tiers as diversification. The two things you must not do: (1) never let a payment mutate a trust badge or a stat, and (2) keep Film Room CV off the tiny prod container so margins survive contact with volume.