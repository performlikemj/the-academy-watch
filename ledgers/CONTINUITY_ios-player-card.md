# iOS player card (lane IPC)

## Goal
- The web profile redesign (#1131) on the native app: player page (hero C, facts strip, season block, one line per match) and the scout desk card (A / D). Draft PR against `feat/ios-phase2`, review-only.

## Constraints / Decisions
- Numbers come from the server's `GET /players/<id>/matches?view=lines`; nothing is merged or totalled on the device. `PlayerCardText` is the Swift twin of the web's `lib/player-card.js` wording rules.
- Provider totals are kept whole and labelled (same rule as web), never added to the lines.
- Desk counters follow the web: apps/minutes only for provider-sourced rows, or for `provenance.primary_source = matches` once PC2 (#1138) is live. `approved_photo_url`, `club_confirmed`, `bio_line`, `contactable` are decoded when present.
- No payload carries a club palette yet: initials tiles use club green + gold (`PlayerClubColors` takes colours when one does).
- Showcase and match lines are scoped to the account: `resetAccount()` on every identity change.
- Simulator and tests are offline (`-floodlightPreview pc-<state>`); the URL guard is untouched.

## State
- Done: models, wording rules, views, player page and scout desk wiring, offline review fixtures built from the server merge function, unit + UI tests, screenshots next to the web's.
- Found and fixed: a public profile whose own contract status is `under_contract` / `expiring` made the whole showcase fail to decode (reel, footage and the introduction entry silently vanished).
- Now: draft PR open, review-only. Receipts: `~/codex-runs/aw-redesign/logs/IPC.final.md`, pictures `~/codex-runs/aw-redesign/shots/IPC/INDEX.md`.
- Next: REVIEW-DUEL. Hero actions over the photo (watch / introduction) were left where they are today — lead's call.

## Not done here
- Watchlist and saved-list rows keep today's layout.
- Review fixture JSON and five small generated PNGs ship in the bundle like the existing review fixtures.
