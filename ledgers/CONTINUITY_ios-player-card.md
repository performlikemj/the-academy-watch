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
- IPCF1 (2026-10-03, after RIPCV-X + RIPCV-O): "Read more" is decided from the measured layout; a community player's showcase (`local_player_id`, no provider id) decodes; the page keeps photo / picked photo / lines when it comes back on screen for the same account (`bind(to:)` + `loadIfNeeded`), dropping them only on a real account change; a failed provider match-log read is never an empty season; desk counters stack and never break inside a number at accessibility sizes; role chip and club caption wrap; the hero name is sized by its longest word and the scrim follows the text so the photo stays visible at large text; the agent-email fact has an explicit VoiceOver action; card images from the production host are refused wherever production API calls are; with the server's card fields (#1138) the desk card shows `bio_line` and prints counters for every row, as the web does. Receipts: `~/codex-runs/aw-redesign/logs/IPCF1.final.md`.
- Next: re-review. Hero actions over the photo (watch / introduction) were left where they are today — lead's call.

## Not done here
- Watchlist and saved-list rows keep today's layout.
- Review fixture JSON and five small generated PNGs ship in the bundle like the existing review fixtures.
