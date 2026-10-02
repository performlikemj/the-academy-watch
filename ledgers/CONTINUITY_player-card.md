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
