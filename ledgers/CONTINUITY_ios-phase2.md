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
- Now: I1F4 in progress; fix RI1V2 ten-item union, native regression coverage and final evidence. Draft #1118 stays unmerged.
- Next: independent review of the I1F3 pushed head; backend8305283b through renewal; app rollout depends on UXB #1124; no fleet merge.

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

## I1 fix round 1
- Now: RI1 full findings read; clean pull to fidelity67fa3244. Fix all findings with evidence; L2 anchor handed to web lane.
- Next: native state/navigation/errors, real staging contract capture + decode tests, all unit/offline UI/Release gates, refreshed light/dark evidence, push + external hand-back.

- Native refresh retains one confirmed flags/access snapshot and stable account/role tab identity; drafts survive successful/failed foreground refresh. Legacy club fallback, saved-list destinations and flags-off Explore tab switching restored.
- Real staging contracts: 47 unedited response bodies, all five personas, verified-owner empty membership/funding bridge, genuine 422/429, success writes and confirmation/reschedule history; tokens excluded. Refresh script commits provenance and cleans synthetic writes. DELETE captures missing-grant refusal rather than deleting a seeded grant.
- All 279 native unit/API/contract tests pass on final source. Focused regressions confirm Trials draft through Settings + failed flag fetch, first location alert, saved lists, staff email clearing and legacy club fallback. Full offline scheme (four classes) and final Release running.
- Backend focused integration: 164 pass; independently gated recruiting access and private exact invitation deadline covered. Ruff check/format and diff whitespace pass. No frontend dependency/lock changes.
- Final Release simulator build passes for arm64/x86_64. All 28 initial viewports refreshed on separate owned capture simulator. Final offline run has passed claims-error copy, location permission, Explore/GOL, saved destinations, legacy flags-off navigation and invite/private-note Settings drafts; board and inherited regressions finishing.
- Remaining fidelity/board gaps explicitly retained: RIM16 gold light-tab label on chalk-2 (~4.40:1); RIM18 chrome superseded by dedicated role tabs while saved routes restored; public age groups/proximity/claim age and scoped captain/playing-up/score DTO fields absent; C2/C4 proposals outside I1 scope. L2 anchor web handoff remains open.

## I1F1 final gates / delivery
- Exact final source: 279/279 unit/API tests; offline Experience 39 pass / 2 inherited opt-in skips / 0 fail across all four classes, including all 23 Phase 2 journeys. Release simulator arm64/x86_64 build passes. Backend 164 focused checks + exact final two new regressions pass; Ruff and diff whitespace pass.
- 47 raw staging contracts with refresh script committed; no saved credentials. Narrow backend access/me independent-flag and private invitation-deadline additions included. Fidelity67fa3244 is retained as an ancestor.
- 28 fresh initial light/dark shots, nine final scrolled viewports, 28 current IMF1 comparisons, source/hash manifests and 51 named Phase 2 UI screenshots: ~/codex-runs/aw-redesign/shots/I1/INDEX.md. Per-finding results/remaining RIM gaps: ~/codex-runs/aw-redesign/logs/I1F1.final.md.
- Owned review/capture simulators 1A649F0A-6B8E-41E5-A06B-ECF2F45050C0 / 4583A7BD-8437-45E5-A34B-DA39FD00BAC6 deleted; /tmp/aw-I1F1-derived + /tmp/aw-I1F1-release and owned interim evidence removed. Other lanes untouched. Foreground commands only; no live login-email suite, background server, production writes or dependency restore.
- Push feat/ios-phase2 to draft #1118; no merge. External hand-back records final pushed SHA and BUS DONE.

## I1 round 2
- Now: native Post-a-trial editor and N5-aligned shared cleat loader in progress; RI1 fix72fc5884 present.
- Next: staging editor contracts, view-model/offline UI tests, light/dark screenshots, unit/offline/Release gates, cleanup and push.

- Native editor + shared loader implemented. First289 native unit tests and80 focused backend tests pass; staging editor success/refusal contracts refreshed. UI fixture funding bridge corrected to include editor owner; screenshot and final gates ongoing.

- Full offline Experience gate:42 pass/2 inherited opt-in skips/0 fail across all four classes. Renewal19:00 low-cut/solid-upper redraw applied with exact N5F1 paths;292 native unit tests and Release arm64/x86_64 pass. Final affected UI/capture checks and push/cleanup ongoing.

## I1 round 2 final delivery
- Source aea2fa96: full native opportunity editor behind current owner/manager recruiting capability and opportunities flag. Exact nullable clearing/term lock, server-created clock +90-day horizon, position close+14-day invitations, explicit409 reconciliation, field400/422 and429. Private created_at is additive; older staging DTOs keep authoritative server validation.
- Renewal19:00 redraw applied: all four N5F1/818c70bc paths verbatim, solid club upper, contrast laces, soleplate/five blades;1s hold/200ms CSS ease over six1.2s phases. Every explicit indeterminate spinner uses CleatLoader; adaptive static launch vector shares CGPaths; logo untouched.
- Final292 unit/API/view-model/staging-contract tests pass; all four offline classes42 pass/2 inherited opt-in skips/0 fail. Post-redraw affected flows4/4 pass, including create→publish→application lock, zone/validation, live initial loading and light/dark form/phase captures. Release arm64/x86_64 green; backend80 + Ruff/Python/diff checks green.
- Real contracts56; raw write/refusal capture and provenance committed. Current synthetic scratch trial closed/app withdrawn, position cancelled, invite revoked. No credentials saved.
- Evidence:60 round2 PNGs with18 initial viewports,34 final UI state/scrolled captures,6 journey captures and2 Reduce Motion snapshots. INDEX + source/reference/shot hashes in ~/codex-runs/aw-redesign/shots/I1; logs/results ~/codex-runs/aw-redesign/logs/I1F2. Final hand-back ~/codex-runs/aw-redesign/logs/I1F2.final.md.
- Owned simulators36372A24-5FA3-4FA8-97FF-B1050AD0E45D andC9A15843-FDCA-45CC-A74F-1390C556E128 deleted; three /tmp/aw-I1F2-* DerivedData directories and generator/scratch script removed. Optional owned post-success diagnostic collectors stopped after all cases passed; xcodebuild returned TEST SUCCEEDED. Other lanes untouched.
- Foreground commands only; no frontend dependencies/lock changes, servers, production writes, live login emails, deployment, flag enablement or merge. Push draft1118; external hand-back/BUS record final SHA.

## I1F3 review-duel fix round
- Now: implement union O1-O7/O9-O13/X1-X4 + N1; O8 excluded with cross-exam evidence.
- Next: targeted regression tests; separate backend commit; merge current main; final governed native/Release/backend gates and screenshot evidence; push/no merge.
- Release dependency: UXB #1124 parent-interest anchor. MJ question: approved N17 live-thread other-states legend.

- I1F3 targeted regression milestones: first-edit/terminal, flags-off sign-out, retry-only apply, directory detail return, dirty-discard, zone picker and390pt largest Home pass. Unit model regressions cover denied/transient membership,31-row older invitation, wall-time/DST and in-flight writes.
- Backend-only8305283b based on main784b1490: cached full4078pass69skip/Ruff570 clean. Native integrates current A2/B1/B2/B351f30f5b heads; integrated PostgreSQL19 +3contract checks pass after applying actual B3 schema (fixture guard accepts p2b3). No migration source change.
- Next: final new role/late-bootstrap checks; final source commit; four cached gates, full native unit/offline suite and Release;light/dark captures; external hand-back/PR body;push and owned resource cleanup.

## I1F3 final verification / delivery record
- All accepted runtime findings implemented; O8 excluded by weak-reference evidence (9 live while owned,0 after scope). Backend-only8305283b is a parent commit for independent cherry-pick/release; original native history is retained without a force push.
- Targeted UI:7 distinct regression cases pass across initial/corrected runs; additional analyst/viewer and late-bootstrap2 pass. Model tests cover all public/private flag outcomes,31applications/older invitation/current priority, time-zone wall values/gap/repeated DST, dirty/in-flight state, reader dates and actual tab text AA contrast.
- Source frozen before final cached backend/full/lint/frontend gates, full unit/offline and Release. Exact receipts/counts, light/dark screenshot index, resource cleanup and pushed SHA are authoritative in external `I1F3.final.md`; no I1-authored migration changes; inherited B3 timeout migration/preapply CONTRACT and schema equality are recorded in the external hand-back.
- Release dependency: `/opportunities/<id>#parent-interest` app link is retained; UXB #1124 must ship its web anchor/focus implementation before the app build.
- Question for MJ (design, not defect): keep the approved N17 “Other states you will see” legend in the live thread?

- Final visual inspection found the long-name DEBUG fixture was overwritten by auth/me refresh; fixture now preserves it and the390pt test asserts the actual name. Runtime source unchanged; final gates run on the revised committed head.

- Final-head full offline run caught the inherited first-location test assuming fresh simulator authorization after a previous run denied it. Test now resets authorization via XCTest before launch; verify twice on the reused simulator. Runtime sources unchanged. Final gates and full offline scheme run on the new test head; all prior receipts remain labelled interim.

- Delivery refresh: B3 landed on main33bf30bd after the b1002027 final offline suite passed8:07. GitHub reported conflicts; merge current main and retain both AGENTS/CONTINUITY records. Only Markdown changes; all native/backend/frontend/migration blobs match b1002027. Final gates run on the new merge head; existing156 native captures remain valid for identical source.

## I1F4 review-duel fix round

- In progress: O1 pinned warning; X1 complete actionable introductions/routing copy; X2+N1 contrast; O2 stable-ID applications; O3 honest public counts; O4 legacy icon; O5 public navigation/auth detail reset; O6 read errors; O7 failed-read loader; O8 visible sign-in.
- Read both independent findings and both cross-examinations. No refutations; N17 legend is MJ design question, UXB1124 parent anchor remains dependency.
- Iteration: targeted xcodebuild only; final full offline/unit + one Release. Governed foreground commands, owned-resource cleanup, no merge.
- Targeted models:59 pass/0 fail (`I1F4/targeted-models3.xcresult`). Two earlier compiles caught test-only helper/typecheck errors; corrected. Seven behaviour UI regressions queued under machine governor; no second invocation.
