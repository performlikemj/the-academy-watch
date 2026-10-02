# Player card + read view of a player (lane PC)

## Goal / constraints
- MJ-approved directive `~/codex-runs/aw-redesign/briefs/PC.directive.md`; mockups `reference/player-card/*.dc.html`.
- Read-only views only: the owner's edit forms in `ShowcaseSection.jsx` are not restyled or restructured.
- No migration, no model change, no change to who can see what. Web only.

## What changed
- Backend: `src/services/match_lines.py` (pure) merges `player_match_entries` into one line per match and totals
  exactly those lines. Served by the existing read route as `GET /api/players/<id>/matches?view=lines`
  (same minor / suppression / publication checks as the list). There is no link column between a self entry and
  a club entry: pairing is player + date + opponent (trim, collapse spaces, lower-case); a different date never
  merges; only `club_confirmed` club rows confirm; `disputed` rows stay out, as in the rollup.
- Frontend: `src/components/player-card/` (PlayerCard A/D, PlayerHero, PlayerFacts, PlayerSeason, MatchLines,
  `usePlayerReadView`), wording/quiet-zero rules in `src/lib/player-card.js`. Mounted in `PlayerPage` and
  `LocalPlayerPage`; `ShowcaseSection` takes `readSectionsElsewhere` so visitors do not see photos, profile
  facts and games twice (owners keep the full manage card). `PublicMatchPanels` is gone: the season block
  carries the frozen-mode "Public match data — last updated" line.
- Scout desk: Cards / Table switch (cards by default under 768px); `?compare=<one id>` now fills the tray.
- Provider totals are used only when the provider really has play for the season; they are labelled and
  never added to match-line totals.

## State
- Now: PR open against main; REVIEW-DUEL next. No merge, no deploy.
- Evidence: `~/codex-runs/aw-redesign/shots/PC/INDEX.md`, hand-back `~/codex-runs/aw-redesign/logs/PC.final.md`.
- Staging seed needed for MJ's look: `~/codex-runs/aw-redesign/staging/pc-seed.md` (not loaded by this lane).

## Known gaps (not in this lane)
- Scout desk / watchlist / compare / CSV numbers come from the season rollup, which takes the club's rows
  whole and ignores self-only matches when any club row exists. A player with both can show fewer apps on
  the desk than on the page. Fix = rollup feeders + stored cells + rebuild; it can reuse `match_lines`.
- Club colours on the no-photo card fall back to club green + gold: the showcase payload has no club colours.
- List payloads carry no approved showcase photo or bio, so desk cards show initials (or the small provider
  headshot at its own size) and "Position at Club".
- iOS still shows the old rows; it needs `?view=lines` and the same wording rules.

## Fix round PCF1 (2026-10-03, after REVIEW-DUEL RPCV-X / RPCV-O at a7d73c65)
- Rows are never dropped: a club row and an own row pair only when they are the only two rows for that date and
  opponent; every other shape keeps each row as its own counted line (`shared_slot: true`).
- Scout-desk cards print no apps/minutes unless the figures are the provider's; no tick; compare + introduce on the card.
- Showcase is read once (ShowcaseSection hands it up); raw match rows are requested only for the owner. Anonymous and
  scout page loads make the same number of requests as main (`~/codex-runs/aw-redesign/logs/PCF1.request-counts.md`).
- Community page: the URL `?season=` is the one picked season; provider totals of another season are never shown.
- A failed match read is an error with Try again; last good data is kept on a failed refresh; `truncated` is carried.
- Showcase payload gained `contactable` (the player's own approved claim — the scout desk's rule) for the
  "Ask for an introduction" button; unverified users are sent to verification. No contact rule changed.
- Hand-back: `~/codex-runs/aw-redesign/logs/PCF1.final.md`.

## Fix round PCF2 (2026-10-03, after codex verification RPCV2-X at a903a29c)
- Serious: the shared showcase was keyed by player only, so signed-in-only fields (agent email) stayed on screen after
  logout until the anonymous read answered. Now showcase, lines, season totals, watchlist state and the open
  introduction dialog are all scoped to player + viewer and withheld in the render where the token changes; late
  answers for the old scope are ignored. ShowcaseSection's own loaded gate and dialogs follow the same scope.
- Medium: the season-totals read is tracked on its own (`useSeasonTotalsRead`): error + Try again, last good totals
  kept for the same player/viewer/season. When totals are missing or failed but the provider's match rows loaded,
  totals are built from those rows; "No matches recorded yet" is never shown while a read has failed.
- Request counts unchanged (`~/codex-runs/aw-redesign/logs/PCF2.request-counts.md`). Hand-back `logs/PCF2.final.md`.
