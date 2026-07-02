# Smart Grouping + Personalized Newsletter Architecture — The Academy Watch

## The one insight that makes this tractable for a solo founder

Today you have two follow primitives that *look* different but are the same shape: a `UserSubscription` (all players where `TrackedPlayer.team_id = X`) and a `ScoutWatchlistEntry` (an explicit set of `player_api_id`s). Both **resolve to a set of players at send time**. So does every group MJ described ("club X's academy", "players I follow in Ecuador + Colombia", "breakout U19s in South America").

Everything below is built on that: **one resolver, one assembly pipeline, one delivery job.** You already own the resolver — `_base_scout_query()` + `_apply_filters()` in `routes/scout.py` is a player-set query engine keyed on position/status/age/nationality/min_minutes. We extend it with `country`/`competition`/`team_id` and reuse it as the single resolution primitive. And you already own the delivery job — `scout_digest_service.send_scout_digests()` with its cursor paging, per-player memo cache, and `last_snapshot` delta logic. We generalize both instead of building new.

---

## (a) Follow-graph primitives — first-class vs composed

**Two first-class tables. Everything else is a discriminator + selector JSON.** Resist a table per follow-type; a solo shop cannot maintain five resolvers and five digest paths.

- **`FollowList`** (first-class): a user's named bundle that compiles to **exactly one newsletter edition**. Carries cadence, timezone, season policy. This *is* the newsletter subscription.
- **`Follow`** (first-class): a single targeting rule inside a list. A `kind` + a `selector` JSONB. All follow "types" MJ named are just `kind` values:

| kind | selector | resolves via |
|---|---|---|
| `player` | `{"player_api_id": 12345}` | direct (this is the migrated watchlist entry) |
| `academy_club` | `{"team_id": 33}` | `TrackedPlayer.team_id == 33, is_active` (this is the migrated team subscription) |
| `geo` | `{"countries": ["Ecuador","Colombia"]}` | `_base_scout_query` + join `Team.country`/`league.country` |
| `competition` | `{"academy_league_id": 5}` | join `AcademyLeague` / `AcademyAppearance` |
| `query` | `{"scout_args": {"position":"Attacker","min_age":16,"max_age":19,"status":"on_loan","min_minutes":270}}` | `_apply_filters()` verbatim — a **saved scout filter** |
| `smart` | `{"smart_key":"breakout_u19_south_america","cap":15}` | reads materialized `smart_group_members` (see (c)) |

So: **player** and **academy_club** are first-class only in the sense that they're the two migration targets; architecturally they're just two kinds. **Age band is not first-class** — it's a `query` follow (`min_age`/`max_age`). **Country/region/competition are not first-class** — they're `geo`/`competition` kinds funneling into the scout query. This is the whole reuse win: `geo`, `competition`, `query`, and age bands all become one code path through the existing scout query builder.

A `FollowList`'s player set = **union of its follows' resolved sets, deduped, capped**. MJ's "random players I follow in Ecuador + Colombia" = one list holding a `geo` follow (`["Ecuador","Colombia"]`) plus a handful of `player` follows. "All of club X's academy" = one list, one `academy_club` follow.

---

## Minimal data model

```sql
CREATE TABLE follow_lists (
  id                SERIAL PRIMARY KEY,
  user_account_id   INT NOT NULL REFERENCES user_accounts(id),
  name              VARCHAR(120) NOT NULL DEFAULT 'Following',
  cadence           VARCHAR(20)  NOT NULL DEFAULT 'weekly',   -- weekly|biweekly|monthly|matchday
  send_dow          SMALLINT,                                  -- 0-6 preferred local day (NULL=auto)
  send_hour         SMALLINT     NOT NULL DEFAULT 8,           -- local hour
  timezone          VARCHAR(40)  NOT NULL DEFAULT 'UTC',       -- IANA e.g. America/Guayaquil
  season_scope      VARCHAR(20)  NOT NULL DEFAULT 'active_only',-- active_only|always
  player_cap        INT          NOT NULL DEFAULT 40,          -- resolved-set send cap (was watchlist's 200)
  active            BOOLEAN      NOT NULL DEFAULT TRUE,
  unsubscribe_token VARCHAR(100) UNIQUE,                       -- carried from UserSubscription semantics
  last_sent_at      TIMESTAMPTZ,
  created_at        TIMESTAMPTZ  DEFAULT now(),
  updated_at        TIMESTAMPTZ  DEFAULT now()
);

CREATE TABLE follows (
  id          SERIAL PRIMARY KEY,
  list_id     INT NOT NULL REFERENCES follow_lists(id) ON DELETE CASCADE,
  kind        VARCHAR(20) NOT NULL,       -- player|academy_club|geo|competition|query|smart
  selector    JSONB NOT NULL,
  label       VARCHAR(160),               -- denormalized display ("Ecuador U19 breakouts")
  note        TEXT,                       -- migrated from ScoutWatchlistEntry.note (player kind)
  created_at  TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ix_follows_list ON follows(list_id);

-- (c) materialized smart groups; refreshed nightly
CREATE TABLE smart_group_members (
  smart_key     VARCHAR(60) NOT NULL,
  player_api_id INT NOT NULL,
  score         REAL NOT NULL,
  reason        VARCHAR(120),             -- "first senior goal", "U18→Senior"
  computed_at   TIMESTAMPTZ NOT NULL,
  PRIMARY KEY (smart_key, player_api_id)
);

-- (b) deterministic newsworthiness per player per send window
CREATE TABLE player_pulse (
  player_api_id  INT NOT NULL,
  window_end     DATE NOT NULL,
  score          REAL NOT NULL,
  delta_json     JSONB NOT NULL,          -- {goals:+2, minutes:+180, status:"first_team", milestones:[...]}
  PRIMARY KEY (player_api_id, window_end)
);

-- (b) shared AI card cache — the ONE place LLM output lives, reused across all users
CREATE TABLE player_card_cache (
  player_api_id  INT NOT NULL,
  window_end     DATE NOT NULL,
  card_html      TEXT NOT NULL,
  card_text      TEXT NOT NULL,
  model          VARCHAR(40),
  PRIMARY KEY (player_api_id, window_end)
);
```

The old `ScoutWatchlistEntry.last_snapshot` per-user delta store is superseded by `player_pulse` (computed once per player, not once per user).

---

## (b) Assembly pipeline + cost control

**The cost problem:** if every user's letter differs, naive generation is `#users × #players` LLM calls. **The fix: split expensive per-PLAYER content (shared, cached) from cheap per-USER assembly (deterministic templating).** LLM cost then scales with the **content universe** (~3,400 players), never with audience size.

Five stages:

**1. Window** — per list, `[max(last_sent_at, cadence-back), now]`. Reuse the snapshot/delta concept already in `scout_digest_service._entry_update`, but compute deltas once globally, not per user.

**2. Newsworthiness scoring (deterministic, NO LLM)** — dedup every player across *all* active lists, score each once into `player_pulse`. Every signal already exists:
- Δgoals/Δassists/Δminutes/Δappearances from `FixturePlayerStats`/`PlayerStatsCache` — the exact deltas `_entry_update` computes today.
- Status change via `PlayerJourney.current_status` / `TrackedPlayer.status` — you already have `_STATUS_LABELS` (promoted, loaned, sold).
- Milestones: debut, first senior goal, first start, level jump (`current_level` U18→U21→Senior).
- New injury/return via `api_client.get_player_injuries` (already wired in the digest).
- Per-90 spike vs baseline from `radar_stats_service`.
- Rank within age band (breakout signal).

**3. Player-card generation — the ONLY LLM step, shared + cached.** For players above a newsworthiness threshold, generate a 2–3 sentence card **once per window**, cached in `player_card_cache`. Every user following that player reuses it. With ~3,400 players and ~10–20% newsworthy weekly, that's ~500 calls/week **regardless of subscriber count**. Batch through the existing `agents/weekly_newsletter_agent.py`, use prompt caching, run cards on a Haiku-class model, and reserve a larger model only for a list-level editorial intro. Every number in a card carries provenance/confidence — the card prompt receives only verified stats, never free-text (honesty constraint).

**4. Per-user assembly (deterministic, NO LLM).** Per list: resolve player set → pull each player's `player_pulse` + cached card → rank → sectionize (by follow, or by theme: "Status changes", "In form", "New faces") → render the existing Gmail-safe 77KB template. Optional single cheap LLM line for a personalized intro ("3 of your Ecuadorians scored this week"), or template it for zero marginal cost.

**5. Sectional / block reuse.** A smart-group block ("Breakout U19s in South America") is identical for every subscriber of that group — render once, embed many. An `academy_club` block is identical across everyone following that club — render per window, reuse. Maintain a per-window **block cache** (club-block, smart-group-block, player-card); only *selection + ordering* is per-user. This is how 10 users and 10,000 users cost nearly the same to generate.

---

## (c) Smart / auto groups — computed from what you already have

A `smart_group` is an admin-defined (a few user-selectable) saved scout query + ranking, **materialized nightly** to `smart_group_members` via cron (you already run pg_cron for cache purges). Then `kind='smart'` follows just read the table — no per-send computation.

**"Breakout U19s in South America this month":**
- Base: `_base_scout_query()` filtered `age ≤ 19` (`_age_expression()`), `Team.country IN (S.America set)`, window minutes > threshold.
- Breakout signal: `player_pulse.score` high, OR window-minutes / prior-3-window-average > 1.5, OR first senior goal, OR level jump.
- Rank composite, `cap 15`, write rows with `reason`.

Other near-free smart groups from existing data:
- **"Just promoted"** — `effective_status` Δ → `first_team` this window.
- **"On the move"** — new loan/sale this window (journey change).
- **"Minutes leaders U21 in <region>"** — reuse `/scout/leaderboards`.
- **"Back from injury"** — injury cleared.
- **"Golden boot — academy loanees"** — goals leaderboard, status `on_loan`.

These double as a public **"Trending"** surface (acquisition funnel), and each is directly addable as a `smart` follow.

---

## (d) Migration path — additive, non-destructive, two SKUs coexist

Key decision: **do not force-merge the two existing primitives into one product.** They are two SKUs.
- **Per-team editorial `Newsletter`** (AI + writer commentary, `public_slug`, mature bounce/unsubscribe via `UserSubscription`) stays as-is.
- **Personalized `FollowList` digest** is the new assembled product.

**Step 1 — create tables + backfill (no behavior change):**
- Each `UserAccount` with `ScoutWatchlistEntry` rows → one `FollowList` ("My Watchlist", cadence from `scout_digest_opt_in`) + one `Follow(kind='player')` per entry, carrying `note`. Drop `last_snapshot` (recomputable into `player_pulse`).
- Each active `UserSubscription` → resolve `email` → `UserAccount` (mint via existing passwordless OTP if absent) → `FollowList("<Team> Academy")` + `Follow(kind='academy_club', {team_id})`. Copy `unsubscribe_token` to the list. `UserSubscription` **stays** as the delivery/consent ledger for the editorial newsletter; a one-way mirror keeps team subs reflected as `academy_club` follows for users who opt into the unified digest.

**Step 2 — dual-write + refactor delivery:** New watchlist adds write a `Follow(kind='player')` (and temporarily still `ScoutWatchlistEntry`). Refactor `send_scout_digests()` to consume **resolved lists** instead of raw entries — the `_entry_update`/snapshot/delta/`player_cache` memo logic is reused verbatim on the resolved player set. Cutover is invisible to users already on the digest.

**Step 3 — flip UI + retire old writes:** Scout hub UI moves to lists ("Watchlist" becomes "your default list"). Stop writing `ScoutWatchlistEntry`; keep the table one release, then drop.

---

## (e) Frequency / timezone / season awareness

- **Scheduler:** an hourly cron replaces the admin-triggered send. It selects lists whose next fire (`cadence` + `send_dow` + `send_hour` in `timezone`, and `last_sent_at` older than cadence) is due, then reuses the existing cursor-paged / `MAX_DIGEST_USERS`-batched sender so hourly firing naturally spreads load.
- **Season awareness:** build a lightweight `competition_calendar` (reuse `AcademyLeague` + season windows: European Aug–May, Brazil/MLS Feb–Dec, Argentina year-round, plus youth-tournament dates). At assembly, a follow contributes content only if its competition is in-season **or** had fixtures in the window. A `season_scope='active_only'` list **skips a send entirely** when none of its follows are in-season — so an Ecuador follower is never emailed dead air in an off-week; `always` lists fall back to "next fixtures" preview.
- **Matchday cadence:** a special cadence keyed off `Fixture` rows — fire the morning after a followed player's team plays, localized to `list.timezone`. This is the **year-round profitability hook**: a user following Argentine + MLS + Brazilian academies gets near-continuous content precisely when the European calendar is dark. Overlapping global calendars = no summer churn cliff, continuous send cadence, continuous billing.
- **Billing tie-in (finally wires `UserAccount.scout_tier`):** Free = one default list, weekly only, ~25 resolved players, smart groups monthly. **Scout Pro** = unlimited/custom-named lists, all cadences incl. matchday, smart-group follows, timezone control, CSV. **Club/Film Room** tier = club-branded list editions with inline emerald "Club-verified" footage cards. Cost scales with the content universe, not audience — so margin improves as subscribers grow.

---

## 3-step build sequence (minimal)

1. **Follow graph + resolver + delivery refactor.** Ship `follow_lists`/`follows`; write `resolve_follow()` reusing `_base_scout_query`/`_apply_filters` (add `country`/`competition`/`team_id` filters); backfill watchlist→`player` follows and team subs→`academy_club` follows; refactor `send_scout_digests()` to consume resolved lists. **No new LLM.** This alone delivers MJ's ask #1 — "players I follow in Ecuador + Colombia" and "all of club X's academy" ship here using today's delta cards.

2. **Newsworthiness + cached AI cards + block assembly.** Add `player_pulse` (deterministic scoring) + `player_card_cache` (shared LLM cards via `weekly_newsletter_agent`) + per-user assembly with club/smart/card block reuse. Editorial quality, flat cost.

3. **Smart groups + season/timezone scheduler + billing.** Materialize `smart_group_members` nightly; hourly cadence/timezone/season-aware scheduler; a public "Trending" surface for acquisition; wire `scout_tier` billing to gate lists/cadences. This closes MJ's ask #3 — profitable, year-round.

(MJ's ask #2 — players uploading their own stats/video under a trust system — rides on this cleanly later: a platform-native player id becomes just another `Follow(kind='player')` target, and their self-reported vs Club-verified content flows through the same newsworthiness→card pipeline with the existing trust-ladder badges controlling what a card is allowed to assert.)

Key files to extend: `models/scout_watchlist.py` → new `models/follow.py`; `routes/scout.py` (`_base_scout_query`, `_apply_filters` become the shared resolver); `services/scout_digest_service.py` (generalize to lists); `agents/weekly_newsletter_agent.py` (batch card generation); `services/radar_stats_service.py` (per-90 baselines for pulse scoring).