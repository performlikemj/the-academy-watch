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
- Now: I1F fidelity delivery complete; all 14 boards refined/compared with current IMF1 references; draft #1118 remains unmerged.
- Next: orchestrator’s separate I1F1 correctness fix round for RI1 findings; no merge.

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

## I1F fidelity round
- Approved references: current project/N*.dc.html + preview/shots/N*.png; IMF1 confirms these are the regenerated fix-round versions.
- Dedicated tabs requested by user supersede IMF1 legacy tab choices; backend capability/data rules still apply.
- Gaps: generic home hero, filled system tab symbols, redundant large headings, picker/menu treatments, stage chips absent, sparse fixture data, plain staff forms and consent rail.

- I1F visual refinement: personal photo hero, serif/hairline rows, outline role tab bar, stage chips and native swipe actions, timeline cards, branded headers, compact staff roles/squad chips, consent rail/messages, checkbox consent and framed forms. Public/scoped DTO omissions preserved.
- Focused UI gate: 4/4 pass (hero/banner/tab count, swipe shortlist/counts, adult consent/submission, staff edit preserving both squads). Fixed hidden system-tab accessibility duplication and replaced gesture with native List swipe actions.
- I1F unit/API gate: 262/262 pass, including interval end times, midnight and DST offsets. Full offline suite and Release simulator build running. Owned review/capture simulators: 12A44BED-AC86-4A10-9133-38C73C1CCE2A / B6BEDF10-6865-4149-B922-0C451D97DC38; temporary builds /tmp/aw-I1F-derived and /tmp/aw-I1F-release.
- I1F Release simulator build passes (arm64 + x86_64); offline suite running. Re-captures on the separate owned capture simulator; tests retain the owned review simulator.
- Full offline first pass: one failure, private-note save obscured by keyboard; remaining journeys and all 14 board captures pass. Added a focused keyboard Done control, retained multi-line notes and explicit submission; test now dismisses the keyboard as a user would. Final focused/full reruns pending.
- Final visual pass removed a duplicate native List disclosure chevron, corrected same-day fixture message order/count, and aligned location filter pills and branded navigation headers. No API/model workflow contract changes.
- Private-note focus regression rerun passes with actual keyboard Done → save → persisted note. Final build/UI capture data includes 4 trial posts, 14 pipeline applicants/stage counts, 6 staff and pending/expired invite states; expired Invite again fills the form for explicit sending.
- Final full offline gate is running on frozen source. Final Release compile green; recapture/compare and push remain.
- Final offline run: note submission passes; parent card accessibility assertion caught the uppercase visual copy change. Kept approved uppercase typography and restored the natural-language accessibility label. Full final rerun required before delivery.

- Full offline delivery: 30 pass / 2 opt-in skips / 0 fail, including all 14 Phase 2 journeys. Contract audit found contact DTOs use naive UTC timestamps; date labels now accept exact naive UTC ISO timestamps, with a regression test and review fixture matching the real contract. Final reruns pending.
- Final UTC contract unit/API regression gate: 263/263 pass (27 Phase 2 checks); Release arm64/x86_64 compile green. Final board pass also checks corrected DEBUG-only back label sizing. All 14 comparisons inspected; supported omissions documented in INDEX.
- Exact final native source: 263/263 unit/API pass; final all-14-board/scrolled UI check passes (186s), corrected Clubs/Trials labels visually checked. Final full timestamp-contract UI run: all 14 Phase 2 tests pass; inherited regression suite finishing.

## I1F final gates / delivery
- 263 native unit/API pass (27 Phase 2 checks); full offline Experience 30 pass / 2 opt-in skips / 0 fail (all 14 Phase 2 journeys); final all-14-board/scrolled check passes separately. Release simulator arm64 + x86_64 green.
- Personal photo home, outline editorial role tabs, stage chips/swipe actions, application timeline, branded club/trial headers, framed forms, staff/squad controls and consent/thread typography match supported IMF1 elements. Singular applicants/places corrected. Contract omissions recorded in INDEX; no C2 approvals or invented public/minor data.
- 28 recaptured board PNGs, 14 required light comparisons + 14 dark comparisons, nine separately labelled scrolled captures, source/comparison hash manifests and successful UI attachments in ~/codex-runs/aw-redesign/shots/I1/INDEX.md.
- Logs/result bundles: ~/codex-runs/aw-redesign/logs/I1F/. Hand-back: ~/codex-runs/aw-redesign/logs/I1F.final.md.
- Owned simulators 12A44BED-AC86-4A10-9133-38C73C1CCE2A / B6BEDF10-6865-4149-B922-0C451D97DC38 shut down/deleted; /tmp/aw-I1F-derived, /tmp/aw-I1F-release and /tmp/aw-I1F-capture removed. Other lanes’ resources untouched. No background shell commands, live emails/servers, backend changes or dependency restores.
- Draft #1118 retains the exact requested title and targets main; DO NOT MERGE. Final commit identity is recorded in the external hand-back. RI1 correctness fixes remain for the queued I1F1 lane.
