# Phase 2 B1 — Clubs near you (club directory)

- Goal: real `/clubs` directory (list first, simple no-provider plot) fed by anonymous `GET /api/programs`; approved location/offering fields on club profile revisions; club-side edit in Club Home; all dark behind `CLUB_DIRECTORY_ENABLED`.
- Branch: `p2/b1-directory` (from `origin/p2/a2-staff-access` bb126fce — stacked on #1109). Draft PR against `main`.
- Migration: `p2b1` → `p2a2`. Seven nullable columns + two CHECKs on `club_program_profile_revisions`; no new table, no RLS/account-export change. Pre-apply SQL `~/codex-runs/aw-redesign/p2b1_preapply.sql` (applied twice on scratch, then `flask db upgrade` over it; downgrade verified).
- Flag: `CLUB_DIRECTORY_ENABLED` default OFF. Off = today: teaser at `/clubs`, `GET /api/programs` handed to the app catch-all exactly as before, no new payload keys, club saves ignore `directory`.
- Playbook: `docs/agents/club-directory.md` (eligibility, payload allowlist, distance, moderation, API).
- Decisions taken (flag to MJ/orchestrator):
  - Eligibility = approved + not hidden + listed league + active manager with approved claim. NOT `is_verified_program` (US payments meaning).
  - Clubs on the "Console (unlisted)" league stay out of the directory (their public page is already a 404); admitting them is a product decision.
  - Filters shipped: who-it's-for (girls & women / adults / youth), level, text, place, distance. "Open opportunities", "Under-16s" and "Film Room clubs" from the board are NOT shipped: no real definition yet (open-opportunity count appears automatically once B2's `open_opportunity_counts` exists).
  - No geocoding provider: clubs enter coordinates; visitor position is browser-only, rounded to ~1 km, never stored or put in the URL.
- Status: complete, awaiting review.
- Gates: ruff check/format clean; backend pytest 3534 passed / 47 skipped / 0 failed (flag off, no local .env); 71 new directory tests; club+funding suites with flag ON 439 pass, 1 expected (A2's exact `/features` payload test). Frontend lint 0 errors (183 pre-existing warnings), build OK, 6 new node tests, 6 new Playwright tests; teaser/navigation/club-console specs pass with flag off.
- Known, not mine: node tests `club-introductions-panel` + `introductions-nav` (2) already fail on the A2 base branch (assert a `MyClubConsole.jsx` line A2 changed).
- Real-flow verification on scratch PostgreSQL `aw_p2_b1` through the real UI: club edits venue/pin → pending is not public → admin sees the fields and approves → public list, radius search and club page show it; hide → gone everywhere; lift → back. Screenshots `~/codex-runs/aw-redesign/shots/B1/` (26 PNGs, 1440 + 390).
- Next: orchestrator review; after A2 (#1109) merges, rebase onto main; pre-apply p2b1, deploy with flag off, verify, ask MJ before switching on. iOS parity is lane C3.
