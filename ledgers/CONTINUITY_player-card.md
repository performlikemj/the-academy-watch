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

## Fix round PCF3 (2026-10-03, after verification duel RPCV3 at 9f912b4e: Opus READY, codex FIX)
- Class closed by construction: `PlayerPage`, `ScoutPage`, `ShowcaseSection` and `LocalPlayerPage` are thin wrappers
  keying their body on player + viewer; a viewer change remounts it, discarding drafts (video URL/title, claim form,
  everything else), dialogs, timers and pending callbacks of the previous viewer.
- Late mutation results from the old viewer are ignored: remount, plus `useViewerState` (a setter made for one viewer
  does nothing once another is on screen) for watch marks and the introduction form; `useScopedShowcase` drops answers
  for a scope that is no longer on screen.
- `tests/viewer-boundary.test.mjs` pins the wrappers; rule written into `docs/agents/frontend.md`.
- Request counts unchanged. Hand-back `~/codex-runs/aw-redesign/logs/PCF3.final.md`.

## Fix round PCF4 (2026-10-03, after re-check RPCV4 at f38fc204: Opus READY, codex FIX)
- Remounting dropped state but not running handlers. Closed at the two places every case passes:
  (A) `APIService.request` binds each request to the credential it was sent with — a late answer is a
  `StaleViewerError`, never a success or a status failure, so no late 401 signs the current session out;
  (B) `useViewerLifetime()` — viewer-bound components call `life.api` (throws before sending once the viewer changed)
  and wrap navigate / logout / sign-in prompt in `useGuarded`.
- Opt-outs (`anyViewer`): features, data mode, season directory; sign-in code request/verify; account claim.
- Deliberate reading: requests are refused on a viewer change, not on unmount alone (a same-viewer save finishes);
  side effects are refused on both.
- Hand-back `~/codex-runs/aw-redesign/logs/PCF4.final.md`.

## Fix round PCF5 (2026-10-03, after re-check RPCV5 at 0cf79bce: both FIX — the global request change went too far)
- Lead's ruling applied. (A') `APIService.request` is back to main for data: answers reach their caller across a
  credential change (public pages outside the keyed boundaries — club page, pricing — do not re-read on sign-in
  changes). Only rule kept: a 401 for a credential that is no longer current is a plain failure (no `status`,
  `staleCredential: true`), so nothing signs the current session out. Removed: `anyViewer`, `_boundFetch`, stale
  conversion of data/network answers.
- (B') Strict binding stays inside the keyed pages via `life.api`; pre-send refusal is now a rejected promise (RPCV5-O
  Small: unhandled rejection in the journey hydration). `CommentSection` keys itself on the viewer (also mounted on the
  newsletter write-up page, which does not remount).
- (C') CSV: `fetchScoutCsv` returns the fully read Blob; the desk saves it through `useGuarded(life, saveScoutCsv)`
  (`lib/download.js`). `downloadScoutCsv` (watchlist page) unchanged from main.
- Hand-back `~/codex-runs/aw-redesign/logs/PCF5.final.md`.
