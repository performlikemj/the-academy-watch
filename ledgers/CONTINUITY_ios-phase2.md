# iOS Phase 2 — I1

## Goal
- Native supported Phase 2 boards, flagged role navigation, tested offline fixtures, light/dark evidence, draft PR against main.

## Constraints / Decisions
- Foreground commands only; no merge to main.
- User-requested dedicated role tabs override FEATURE-MAP fix-round navigation.
- Adult self-profile applications only; parents link to interest sign-up. No C2 approvals, invented distances, or public capacity.
- Scope and permissions come from access/me, never role preference or all_squads.

## State
- Done: merged B3 + final B1/B2 dependencies; conflicts preserved owned feature blocks. Native role tabs, browse/apply/application actions, recruiting/invites/notes/signing, owner staff grants and scoped squads implemented.
- Now: complete; draft PR [#1118](https://github.com/performlikemj/the-academy-watch/pull/1118) to main, unmerged.
- Next: owner review of draft PR; no merge.

## Validation
- Debug simulator compile passes. First XCTest launch hit simulator infrastructure error before tests; rerun on booted dedicated simulator, parallel testing disabled.
- Backend integration: 271 pass, 2 inherited B1 allowlist assertions fail because the integrated B2 optional open_opportunities field is now present. Updated assertions to permit only that documented aggregate; focused directory rerun passes (112/112).

## Milestones
- 260 native unit/API tests pass (25 Phase 2 tests): flags, role capabilities, posted-location body, pagination, stale response isolation, adult claim/consent/retries, trial actions, stale private record removal, notes, staff scope preservation and posting zones/DST.
- 273 focused backend integration checks pass across runs (271 unaffected checks + both B1 assertions fixed; directory rerun 112/112).
- Full offline Experience scheme: 27 pass, 2 opt-in skips, 0 fail; all 11 Phase 2 journeys pass. Skips: optional live local-sign-in GOL check and opt-in story-map runner.
- 28 native board captures (14 light + 14 dark), plus successful journey attachments. Visual review caught and fixed the initial coach-tab launch race; coach screenshot now shows scoped squad + first name/initial.

- Final native unit/API delivery: 260/260 pass; Release simulator build passes; all 11 Phase 2 UI journeys pass in the full offline run.
- Screenshot INDEX.md written with all 28 board captures.
- Main merge reconciled backend/doc conflicts from independently landed A2/N3; preserved N3 evidence UNION/GOL adapters and B2 private-only reversible hold reconciliation. No native conflicts. New final native unit/API run: 261/261 pass, including N3 scout-age ranges.

## Final gates / cleanup
- Final main-integrated checks: 261 native unit/API pass; offline Experience 27 pass / 2 opt-in skips / 0 fail (11 Phase 2 journeys); Release simulator build green.
- 428 focused backend checks pass (directory, applications, RB2/B2F2, staff, admin/RB3/RB3V, N3 adult rules). Ruff check/format of merge-resolution files and git diff --check pass. Alembic has one p2b3 head.
- No frontend dependency restore or lockfile changes; dependency scan not applicable.
- Evidence: ~/codex-runs/aw-redesign/shots/I1/INDEX.md, 28 board PNGs and 14 final Phase 2 journey attachments. Logs/result bundles: ~/codex-runs/aw-redesign/logs/I1/.
- Owned simulators 10B0899B-CACC-49F7-9195-111597FB39C5 and 8C5022C7-D676-44BC-BBD4-73F32B7E89F7 shut down/deleted. /tmp/aw-I1-derived and /tmp/aw-I1-shots removed. No live email suite, production writes, servers or DB copies created.

## Delivery
- Draft PR #1118 to main: https://github.com/performlikemj/the-academy-watch/pull/1118; exact requested title; DO NOT MERGE.
- Hand-back: ~/codex-runs/aw-redesign/logs/I1.final.md.
- Native implementation commit d0bb7fb5; main reconciliation 5706739d. Dependency commits remain visible until their separate PRs land.
