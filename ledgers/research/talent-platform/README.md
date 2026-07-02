# Talent Platform Design — Follow Graph × Trust System × Year-Round Revenue

> 2026-07-02. Design panel (4 Opus agents: grouping / trust / revenue / repo-grounding),
> synthesized by the orchestrator. Full reports in this directory. Answers MJ's ask:
> smart player grouping for tailored newsletters + player-uploaded stats with anti-lying
> trust + profitable year-round.

## The one spine (synthesis)

```
Follow graph (user-owned lists of {player|club-academy|geo|competition|query|smart})
  → one resolver (extend routes/scout.py _base_scout_query — already a player-set engine)
  → player_pulse (deterministic newsworthiness, computed ONCE per player per window)
  → player_card_cache (the ONLY LLM step — shared across all users; cost scales with
    ~3,400 players, NEVER with subscriber count)
  → per-user assembly (cheap templating) → tiered delivery (cadence/timezone/season-aware)
```

Trust tiers flow through it (a card may only assert what its tier allows); money attaches
at the joints (lists/cadence/alerts = Scout Pro; footage = Film Room credits; roster
tooling = Club SaaS; reach-not-truth = Showcase Boost).

## Key converged decisions

- **FollowList + Follow(kind, selector JSONB)** — one table pair, one resolver. Watchlist
  and team subscriptions become two kinds; "Ecuador+Colombia players" = a geo follow +
  player follows in one list. Migration is additive (backfill, dual-write, flip).
- **Trust = assertions + append-only corroboration** (`player_assertion` +
  `assertion_corroboration`, tier recomputed as a pure fold). Ladder gains middle rungs:
  self_reported < peer < club_vouched < **opponent_confirmed** < footage/platform-verified.
  Opponent confirmation is the cheapest strong signal (adversarial = trustworthy).
- **Batch match confirmation is the network effect**: one verified club official confirms
  a match roster+score → vouches their own squad AND auto-upgrades opponents to
  opponent_confirmed. Verification scales sublinearly with headcount.
- **Discoverability is the incentive**: only opponent_confirmed+ enters leaderboards/
  digests/compare. Self-reported stays on your own page, badged. Lying buys nothing.
- **`showcase_player`** (platform-native id, guardian-required for minors, DOB never
  public) closes the worldwide gap; Film Room roster entries can mint them footage-first.
- **Money never buys trust.** Paywalls on aggregation/automation/distribution/workflow;
  the truth layer stays free. "Promoted" ≠ verified, non-removable label, minors' boosts
  guardian-gated + off by default.
- **Year-round = hemispheric overlap + matchday cadence** (fire the morning after a
  followed player's team plays, any hemisphere) + annual plans sold at the two transfer-
  window peaks (Jan, Jun–Jul). Film Room is counter-cyclical (youth/college tournaments
  fill European troughs).
- **~$10k MRR mix (honest math)**: 150 Scout Pro @ $19 + 25 Club accounts @ $99 +
  ~120 Film Room matches/mo @ $25 are load-bearing (~$8.3k); boosts/fans/sponsors are
  diversification. COGS watch: Film Room human review minutes, not compute.

## Grounding corrections (facts that changed the plan)

1. **Ecuador + Colombia are NOT in SUPPORTED_LEAGUES** (only Brazil 71 + Argentina 128
   in S.America). MJ's exact example needs league IDs 242/239 added + CRAWL_LEAGUE_IDS
   widened (env + API-quota decision) before those players have real stats.
2. **Stripe is greenfield** — zero live API calls; Connect models are DEPRECATED. But two
   designed-for seams exist: `VideoCreditLedger.stripe_session_id` (webhook idempotency
   ready) and `UserAccount.scout_tier`. First checkout+webhook is a real (small) build,
   not a flip.
3. Team newsletters deliver via **n8n webhook** (N8N_EMAIL_WEBHOOK_URL), not Mailgun —
   only the scout digest uses email_service/Mailgun. The digest path
   (`scout_digest_service.py:225`, with its per-player memoization + cursor paging) is
   the engine to generalize.
4. `UserSubscription` is keyed by EMAIL not user id (joined by string match) — migration
   must mint accounts via the existing OTP flow.

## Build sequence (each phase ships value alone)

1. **Follow graph** — tables + resolver + generalize `send_scout_digests` + backfill.
   Delivers "club X's academy" and "my Ecuador/Colombia list" with today's delta cards.
   Prereq for the example: add leagues 242/239 (+crawl quota decision).
2. **Pulse + cached AI cards** — editorial quality at flat cost (`player_pulse`,
   `player_card_cache`, batch via weekly_newsletter_agent).
3. **Scheduler + billing switch 1** — hourly cadence/timezone/season-aware sends;
   Stripe checkout + webhook wiring scout_tier (Scout Pro $19/mo; lists/cadence/alerts
   gated). Then Film Room credit purchases on the ledger seam.
4. **Assertions + trust engine** — player-uploaded stats day-1 automatable checks
   (bounds, z-score vs cohort, YouTube-id dedup, solo-anchor cap, DOB-vs-band), strikes,
   TrustBadge on every number (bare numbers never render).
5. **Club accounts + batch confirmation** — club_membership, the vouching network
   effect, Club SaaS $99/mo, showcase_player minting from Film Room rosters.

## Extension (2026-07-02, MJ): scattered-player tracking + YouTube discovery

### Three coverage lanes (how a scout tracks ANY player on Earth)

| Lane | Universe | Cost model | Status |
|---|---|---|---|
| **League crawl** (dense) | 16 supported leagues, academy provenance | quota per LEAGUE (CRAWL_LEAGUE_IDS, env-gated) | live |
| **Shadow tracking** (sparse, NEW) | any API-Football player worldwide (~200k+) | quota per PLAYER — scales with scout demand | designed |
| **showcase_player** (off-grid) | grassroots players with no API id | Film Room / club-vouched | designed |

**Shadow tracking design** — the Scout Pro killer feature ("follow any player on Earth"):
- Scout searches API-Football by name → `Follow(kind='player')` on a player with NO
  TrackedPlayer row → a `player_shadow` row is minted: profile (get_player_profile),
  season stats refreshed into the existing **PlayerStatsCache** (built for exactly this),
  optional journey sync (per-player endpoint exists), injuries.
- **MUST NOT be TrackedPlayer rows** — academy-window repair sweeps would auto-deactivate
  non-academy adults; shadow rows live outside provenance semantics entirely (no academy
  claim implied; PlayerPage already degrades gracefully by player_api_id).
- Refresh scheduling piggybacks the pulse pipeline: shadow players refresh per follow
  cadence (matchday/weekly), deduped across all followers — quota scales with UNIQUE
  followed players, not followers. ~500 shadows × 2 refreshes/wk ≈ 150 calls/day —
  cheap vs one league crawl.
- Entitlement: Free = follow within the tracked universe only; **Scout Pro = N shadow
  slots (e.g. 50/seat)** — the quota cost is literally what the subscription pays for.
  This converts "widen coverage?" from a capex league-crawl decision into demand-driven
  opex that arrives pre-monetized.

### YouTube highlight discovery (future scope, MJ-flagged)

- Nightly job (quota-aware: YouTube search = 100 units/call, ~100 searches/day at default
  10k quota → prioritize by pulse score + active claims/follows): search "name + club +
  highlights" → `video_candidate` rows (yt video id, title, channel, published_at,
  status: candidate|offered|accepted|rejected). Dedup via existing _youtube_video_id
  against reels + prior candidates; channel allow/blocklist.
- **Trust posture: candidates NEVER auto-publish.** Offered to the claimed owner ("we
  found 3 possible videos of you") and/or admin; acceptance still flows through the
  existing pending→approved moderation; badge stays distinct from Club-verified.
- Cross-pollination with Film Room R&D: the video-identity VLM entity-consistency gate
  (the 17.5→70% precision montage check from the spike) can later score "is the claimed
  player visibly in this clip" BEFORE offering — machine pre-filter, human final say.
- Newsletter flywheel: accepted highlights feed player_pulse ("new footage" card block).

## Status

- Talent Showcase slice: **PR #565** (awaiting MJ).
- **Phase 1 (follow graph + shadow tracking): SHIPPED to PR #566** (2026-07-02, stacked
  on #565). Design held up in build; one architectural catch by adversarial review
  (dual-write mirror silently rerouting the digest — fixed to additive semantics).
  Full narrative in `docs/follow-graph.md` (on the branch) + CONTINUITY.md.
- Next in leverage order: (2) pulse + cached AI cards, (3) scheduler + Scout Pro billing
  switch, (4) assertions/trust engine, (5) club accounts + batch confirmation.

## IA + backlog notes (2026-07-02, MJ session)

- Nav rework shipped in #566: Dream XI demoted (page + Home grid remain; team picker
  made worldwide), Lists added for logged-in users. Journalists nav item PENDING MJ
  (live writer relationships — not an IA-only call).
- **Analytics gap**: zero usage instrumentation — MJ "can't tell if anyone has used
  anything." Add privacy-light analytics (Plausible/Umami, cookieless) BEFORE the next
  demote/invest decision; also feeds the revenue metrics (claims/send, list-creation
  rate, search→follow conversion).
- **Dream XI re-engagement idea** (MJ: "missing something to make it engaging"):
  build-your-XI-from-your-Lists (incl. worldwide shadows), every player in a shared XI
  deep-links to their showcase → shared XIs become distribution for player profiles.
  Earns nav placement back if it works. Not scheduled.
