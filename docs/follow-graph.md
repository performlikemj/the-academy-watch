# Follow Graph & Worldwide Shadow Tracking (Phase 1)

> **Living document.** Last updated **2026-07-02**. Design rationale:
> `ledgers/research/talent-platform/`. Roadmap: `ledgers/ROADMAP_talent-showcase-vision.md`.

## 1. What it is

Scouts organize who they track into **named lists** at `/scout/lists`. A list holds
**follows** of four kinds, and resolves to a live player set:

| Kind | Example | Resolves via |
|---|---|---|
| Player | Endrick | tracked player, else a **shadow** (see §3) |
| Club academy | "Club academy: Ajax" | all active tracked players of that parent club |
| Countries | "Playing in: Ecuador, Colombia" or "Nationality: …" | current-club country / nationality (case-insensitive) |
| Saved filter | "Filter: Attacker, age -19, 270+ mins" | the Scout Desk query engine |

## 2. The digest (additive semantics — important)

The weekly scout digest now renders: the **legacy watchlist section first
(byte-identical to before this feature)**, then one grouped section per active
non-default list (players already in the watchlist section are not repeated).
The auto-created "My Watchlist" default list mirrors watchlist adds/removes and
**never** routes the digest (fallback: it resolves only if the watchlist is empty).
Sends remain admin-triggered: `POST /api/scout/admin/send-digests {dry_run, limit, cursor}`.

## 3. Shadow tracking (worldwide)

Following a player outside the tracked universe **mints a shadow**: profile from
API-Football `players/profiles` (name search: `GET /api/scout/player-search?q=`,
min 3 chars), season stats into the dedicated `player_shadow_stats` table (NEVER
`player_stats_cache` — unowned legacy, kept isolated; scout surfaces unaffected).
Shadow players get working pages: profile fallback + `stats_coverage='limited'`
season stats. They are followable only via lists (the legacy watchlist stays
tracked-players-only). Caps (env): `MAX_FOLLOW_LISTS=10`, `MAX_FOLLOWS_PER_LIST=50`,
`SHADOW_FOLLOW_LIMIT=10` distinct worldwide players per user — these become the
Scout Pro entitlement levers when billing wires up.

Refresh (operator-paced, quota-capped, mirrors backfill-names):
`POST /api/admin/scout/shadow-refresh {limit}` — stalest-first profile+stats refresh.
Quota safety: 24h/7d DB api_cache + the client's daily quota gate.

## 4. Operator notes

- **Migration `aw20`** (chains aw19 — REQUIRES the Talent Showcase branch/PR #565
  first). Tables: follow_lists, follows, player_shadows, follow_player_snapshots,
  player_shadow_stats. Idempotent both directions.
- **Backfill** (after upgrade): `POST /api/admin/scout/backfill-follow-lists
  {dry_run, limit, cursor}` — copies each user's watchlist into their default list
  (notes + snapshots carried). Loop on next_cursor. Idempotent.
- **LOCAL DEV DB**: cs01's `player_journeys.current_status` columns were missing
  locally until 2026-07-02 (DB stamped on the vid chain; cs01 never ran) — local
  scout browse 500'd since PR #514. Applied manually; a future full-chain upgrade
  no-ops (guarded).
- Tests: `pytest tests/test_follow_graph.py` (54). The digest regression bar is
  enforced by a REAL-API-path test (adds via POST /scout/watchlist, then diffs the
  rendered email against the legacy render).

## 5. Changelog

- **2026-07-02** — Phase 1 shipped: follow graph (4 kinds), worldwide shadow
  tracking, additive digest generalization, ListsPage UI. Adversarially reviewed
  (8 findings fixed — headline: dual-write mirror silently rerouted watchlist
  users onto the list digest path; redesigned to additive semantics).
