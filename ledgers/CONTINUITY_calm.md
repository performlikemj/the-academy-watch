# CONTINUITY — Calm pass (information-overload redesign + shared filter bar)

Directive: `~/codex-runs/aw-redesign/briefs/CALM.directive.md` (approved 2026-10-03). Three PRs, in order.

## CALM-1 — filter bar + admin area + house rules (branch `feat/calm-1-filterbar-admin`)

Status: built 2026-10-03; PR open, not merged. Release waits for the owner's own look on staging.

Done
- `FilterBar` (`src/components/filter/`) + `useUrlFilters` + pure helpers in `src/lib/url-filters.js`.
- Admin Today: only queues with something waiting, "Everything else is clear", four headline numbers each from an
  existing endpoint (left out when the source is missing), the rest collapsed.
- Club approval: list of clubs waiting -> one club: summary card "N of 11 checks pass" with the gaps named, existing
  Approve / Reject / Revoke, checks grouped and collapsed (a failing group open). Content review is its own tab.
- People and Clubs: search + FilterBar + compact list + slim detail panel; rare actions behind ⋯.
- Backend: new list filters and two option-count endpoints in `routes/admin_control.py`
  (`tests/test_admin_control_calm.py`, SQLite + PostgreSQL). No migration.
- House rules in `docs/agents/frontend.md`; contract in `docs/p2-admin-control.md`.

Decisions
- The mock shows "12 of 13 checks" and an approval with a gap. The server refuses approval below its evidence bar,
  and two of the thirteen rows are not part of that bar, so the page counts the 11 required checks and offers
  Approve only when all pass.
- "Ask for the missing check" does not exist on the server; left out.
- Per-option counts ship for Club (People) and Country (Clubs) only.
- The sidebar keeps its current sections; the mock's seven-item navigation is a wider change across ~30 admin pages.
- League registry, Demand and Content review tabs keep their existing cards (not part of the approval story).

Next
- CALM-2: club console shell + Matches (include polish item 17).
- CALM-3: players list, player-page actions, FilterBar on the scout desk — after the scout desk and player card PRs merge.
