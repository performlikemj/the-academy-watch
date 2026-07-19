# Task Ledger: iOS P4b Branding + Device Refresh

Parent: CONTINUITY.md
Root: CONTINUITY.md
Related: ledgers/CONTINUITY_ios-p4a-launch-performance.md; ledgers/CONTINUITY_ios-device-install.md; PR #634
Owner: /root

## Goal

- Replace the placeholder iOS icon with the cropped, full-bleed winged-football-boot brand mark.
- Add a storyboard-free `UILaunchScreen` using the sampled icon background and a centered boot asset.
- Complete decision-free P4 polish, verify XcodeGen/build/full tests, capture simulator evidence, refresh MJ's physical-device install, then commit and push to PR #634.

## Constraints / Assumptions

- Work in `academy-watch-ios/` plus this ledger, the master rollup, and requested `scratchpad/` evidence.
- Brand source is `academy-watch-frontend/public/assets/loan_army_assets/favicon-512x512.png` in this worktree.
- Remove the source's baked outer margin/rounded-tile treatment; the iOS app icon must have a full-bleed dark background and remain a single 1024x1024 universal image.
- Preserve unrelated worktree changes and stage explicit paths only.
- Device target is `A44DF4A4-65C2-5A1E-9B95-F4479737A8F6`; install is required, launch is best-effort if locked.

## Key Decisions

- Crop the 512px source at `left=98, top=104, width=304, height=304`; this keeps ~9.5% side padding, removes the rounded tile edge/sparkle, and produces full-bleed opaque corners.
- Use the safe-interior median/mode `RGB(28, 28, 28)` / `#1C1C1C` for the launch background.
- Use a transparent 200pt `LaunchBoot` asset at 1x/2x/3x over `LaunchBackground`; generate it from the same crop so launch and icon stay aligned.
- Generate `AcademyWatch/Info.plist` through XcodeGen `info.properties` with direct storyboard-free `UILaunchScreen` keys.
- Keep branding generation deterministic and source-relative so the placeholder generator cannot silently restore the old AW shield.
- Fix the reproduced standard-XXL Compare truncation with caption-relative `@ScaledMetric` geometry and allow the Scout filter value to scale to 0.6; defer maximum-accessibility-size structural redesign because it is not cheap P4 polish.

## State

- Done: Full-bleed winged-boot icon and deterministic generator; centered storyboard-free launch screen; standard-XXL polish; XcodeGen/build/51 tests; simulator icon/launch screenshots; signed physical-device build and install; locked-device launch result recorded.
- Now: Commit and push the verified P4b closeout to `feat/ios-app` / PR #634.
- Next: PR #634 review.

## Links

- Upstream: CONTINUITY.md
- Downstream: PR #634 / `feat/ios-app`
- Related: ledgers/CONTINUITY_ios-p4a-launch-performance.md; ledgers/CONTINUITY_ios-device-install.md

## Open Questions (UNCONFIRMED)

- None.

## Working Set

- `academy-watch-ios/project.yml`
- `academy-watch-ios/AcademyWatch/Info.plist`
- `academy-watch-ios/AcademyWatch/Assets.xcassets/`
- `academy-watch-ios/AcademyWatch/Features/Compare/CompareView.swift`
- `academy-watch-ios/AcademyWatch/Features/ScoutDesk/ScoutDeskView.swift`
- `academy-watch-ios/scripts/`
- `academy-watch-frontend/public/assets/loan_army_assets/favicon-512x512.png`
- `scratchpad/ios-p4b-icon.png`
- `scratchpad/ios-p4b-launch.png`
- `scratchpad/ios-p4b-app-icon-preview.png`

## Notes

- Initial toolchain: Xcode 26.5, XcodeGen 2.45.4.
- Simulator: booted iPhone 17 Pro (`40BAC604-5CAD-4767-BF56-21F69FAB5423`, iOS 27.0).
- Physical device: MJ's iPhone connected and available via `devicectl`.
- Icon audit: `1024x1024`, RGB/no alpha; TL/TR/BL/BR corner samples are RGB `(27,28,28)`, `(27,27,27)`, `(28,28,28)`, `(27,27,27)`; preview visually confirmed centered/full-bleed.
- Brand regeneration is byte-deterministic for the app icon and all three launch images.
- `xcodegen generate`: passed; generated plist contains direct `UIColorName=LaunchBackground`, `UIImageName=LaunchBoot`, and `UIImageRespectsSafeAreaInsets=false` keys.
- Clean simulator build: passed against iPhone 17 Pro; asset catalog compiled without branding warnings.
- Full XCTest suite: 51 passed, 0 failed; `** TEST SUCCEEDED **`.
- Standard-XXL evidence: scaled Compare geometry was visually confirmed without prior name/metadata/row-label truncation; Scout displays full `Goal contributions` at the 0.6 floor.
- Simulator evidence visually confirmed: `scratchpad/ios-p4b-icon.png` (`1206x2622`) and `scratchpad/ios-p4b-launch.png` (`1206x2622`). The temporary first-page icon layout used for the SpringBoard evidence was restored afterward.
- Signed device build: passed for destination `00008150-001568902E88401C` using `Apple Development: Michael Jones (GXQMXX8C62)` and the automatic team provisioning profile.
- `devicectl` install: succeeded on `A44DF4A4-65C2-5A1E-9B95-F4479737A8F6`; bundle `com.theacademywatch.app`, installation UUID `6F193952-A8D8-43DC-AC97-377C7947DF4E`.
- One device launch attempt failed only with `BSErrorCodeDescription=Locked`; no retry per task constraint.
