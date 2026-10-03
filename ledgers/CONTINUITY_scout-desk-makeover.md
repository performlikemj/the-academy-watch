# CONTINUITY — scout desk (Discover) + watchlist makeover (lane SD)

Directive: `~/codex-runs/aw-redesign/briefs/SD.directive.md` (MJ-approved 2026-10-02). Mockups:
`reference/player-card/ScoutDesk.dc.html`, `Watchlist.dc.html`. Branch `feat/scout-desk-makeover`.

## State
- Done (2026-10-03): Discover rebuilt (new sub-line, server-filter chips, Cards | Table, desk card, leaders below the
  results and only with rows); watchlist rebuilt (one row per player, private note in full and edited in place,
  introduction state for this scout + the one next action). Proof: `~/codex-runs/aw-redesign/shots/SD/INDEX.md`.
- Fix round SDF1 (2026-10-03): duel findings fixed — introduction state mirrors the contact routes (target claim, per-request block, neutral blocked state; parity table test vs the real POST route, also run on PostgreSQL), desk control offers only what is allowed and refreshes after an ask, table-only filters stay visible in cards, same-page thread deep link, view choice per viewer, pre-PC2 figures withheld in table and leaders too.
- Fix round SDF2 (2026-10-03): IntroductionsPage / ContactThread / ClubIntroductionsPanel / ListsPage made viewer-keyed boundaries (previous account's invitation could show after a switch + same-page Back/Forward); compare withholds pre-PC2 figures; `conversation_open` mirrors the message route's manager-block rule; view choice keyed by account; no Ask while verification is loading (watchlist).
- Now: PR #1141 open to main, awaiting re-review. Do not merge here.
- Next: after PC2 lands, merge main in (both edit `routes/scout.py`, `pages/ScoutPage.jsx`, `e2e/player-card.spec.mjs`).

## Decisions
- No schema change, no migration, no flag. Web only.
- Backend additions live in `services/scout_desk_card.py`: `contactable=1` filter (same rule as the per-row flag),
  `availability` on desk rows (approved showcase profile only), `introduction` on watchlist entries and — for a
  signed-in caller — on desk rows. Read-only; one `contact_requests` query per response.
- Card = PC's `PlayerCard` with `variant="desk"`; watchlist tile = `PlayerTile`. No second card component.
- Club- or player-entered counters print only on rows carrying PC2's fields (`club_confirmed` key), so SD is safe
  before and after PC2.
- View choice is stored per viewer under a one-way tag of the credential (never the credential).
- Kept: compare + introduce controls on each card (on the tile), the verification pill, season picker, Export CSV.
  Dropped from the Discover header: Watchlist / Introductions pills (the desk nav has them). Dropped from the
  watchlist: the "also a List" notice (the nav's Lists link covers it) and the "Scout Pro — free during beta" eyebrow text.

## Open / follow-ups
- Club colours on initials tiles: list rows have no link to a `ClubProgram` palette → default green + gold.
- Search matches the player NAME only (mockup says "name, club or town") — needs a server search change.
- Withdrawn date is not stored on the request (only in the audit trail) → "You withdrew this request." has no date.
- iOS: needs `contactable=1`, `availability`, `introduction` (desk + watchlist) to draw the same card and row.
- `e2e/uxm1-polish.spec.mjs` (not in CI) still has stale 390 px table checks and player-page checks from before this lane.
