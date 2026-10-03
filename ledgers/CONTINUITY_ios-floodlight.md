# iOS Floodlight — L4

- Goal: behaviour-preserving Floodlight restyle of all existing native screens; draft PR for MJ.
- Branch: redesign/ios-floodlight; base origin/main.
- Constraints: no real sign-in/email, deployment, TestFlight, device install or merge; logo unchanged; DEBUG simulator fixtures only.
- Design: ~/codex-runs/aw-redesign/DESIGN.md §3 and reference/boards.

## Tasks
- complete: inventory + generic DEBUG simulator review harness; 44 origin/main baseline screens (a143badd), final fixture overlay position verified clear of native navigation.
- complete: four bundled font faces with OFL licences; adaptive palette, Dynamic Type and shared controls; all existing Features views restyled.
- complete: 44 paired light/dark review screens; visual inspection; 20 largest-accessibility-text checks; INDEX.md maps all 152 PNGs.
- complete: final 235 main-scheme tests; offline UI suite and all seven bundled journeys; Release simulator build.
- complete: owned simulators shut down; four DerivedData paths, temporary baseline source tree and font downloads removed.
- complete: committed and pushed; draft PR #1105 against main: https://github.com/performlikemj/the-academy-watch/pull/1105. DO NOT MERGE — awaiting MJ review.
- complete: temporary PR body removed; BUS DONE handoff follows final documentation push.

## Validation
- Main scheme offline: 235 tests, zero failures (`unit-tests-review-complete.xcresult`). Fonts registered; generic data decodes; unmatched/mutation requests fail closed; adaptive text AA contrast passes.
- Release simulator build passes (`release-build.log`).
- AcademyWatchExperience: 18 tests, zero failures, 2 expected skips; all 7 bundled journeys additionally pass. No live smoke scheme.
- Baseline captured through identical offline harness over origin/main.
- No real authentication, emails, production mutations or deployment.

## Evidence
- Screenshots: ~/codex-runs/aw-redesign/shots/ios/; before/ and INDEX.md.

## Decisions
- Applied orchestrator BUS correction: gold-text #84661F (4.73:1 on chalk); small labels on chalk use corrected gold-text in light, gold in dark; tinted badges and elevated surfaces use muted/ink for AA.
- Keep native tab bar, menus and Safari handoffs; retain horizontal carousels and 3–4-player comparison scrolling. Two comparisons fit ordinary 390pt; accessibility sizes show a horizontal scroll indicator and content-driven headers.

## Review limits
- Installed runtime: iOS 27 simulator, iPhone 17 Pro 402pt. No physical-device or older-runtime validation.
- Native platform menus/tabs/keyboard and existing Safari web destinations are preserved.
