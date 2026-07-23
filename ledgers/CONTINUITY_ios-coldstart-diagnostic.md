# Task Ledger: iOS Crash + Cold-Start Diagnostic

Parent: CONTINUITY.md
Root: CONTINUITY.md
Related: ledgers/CONTINUITY_ios-p4a-launch-performance.md; ledgers/CONTINUITY_ios-p4b-branding-device-refresh.md; PR #634
Owner: /root

## Goal

- Diagnose MJ's reported AcademyWatch crash and/or long Xcode launch with crash-report and measured runtime evidence.
- Fix confirmed crash/performance causes within `academy-watch-ios/` and ensure a fresh first launch visibly reports `Waking up the match server…` with elapsed feedback after about three seconds.
- Build, run the full suite, capture `scratchpad/ios-diag-coldstart.png`, reinstall MJ's device, commit explicit paths, and push `feat/ios-app` for PR #634.

## Constraints / Assumptions

- Investigate in this order: crash reports; fresh-install cold path and health warm-up; schema-v1 cache, Keychain, main-thread decode, and image-storm suspects; debugger versus standalone nuance.
- Preserve unrelated worktree changes and stage explicit paths only.
- Do not read or modify `/Users/michaeljones/Projects/loanarmy/ledgers/CONTINUITY_grassroots-funding.md` or its lock.
- Device target is `A44DF4A4-65C2-5A1E-9B95-F4479737A8F6`; tolerate a launch failure when the phone is locked, but record the exact install/launch outcome.
- Actual crash remediation requires quoted evidence and a regression test; do not broaden scope to unconfirmed suspects.

## Key Decisions

- Treat the report as an unconfirmed crash until runtime reproduction yields process-exit evidence: no AcademyWatch crash artifact exists locally, in the synced-device directory, or in the phone's directly queried crash-log domain.
- Add delayed, explicit cold-start feedback to the existing first-page loading state; the current generic `Scouting talent…` spinner and skeletons do not explain the known backend wake-up wait.
- Use monotonic uptime plus SwiftUI `TimelineView` for elapsed feedback instead of a task-based timer; this avoids timer cancellation/revision races and only retains a start timestamp while an empty-cache player request is active.
- Do not change cache, decode, image, Keychain, or debugger settings: each named suspect was ruled out, and debugger overhead is development-only.

## State

- Done: Evidence collection and all named-suspect audits; delayed `Waking up the match server…` state with per-second elapsed text implemented; review follow-up fixed empty cached payload handling; XcodeGen, simulator/device builds, and all 55 tests pass; fresh-install waiting screenshot visually verified; signed app reinstalled to MJ's phone.
- Now: Complete; explicit-path delivery commit and push follow this final ledger rollup.
- Next: PR #634 review; unlock MJ's phone before a manual standalone launch if desired.

## Links

- Upstream: CONTINUITY.md
- Downstream: PR #634 / `feat/ios-app`
- Related: ledgers/CONTINUITY_ios-p4a-launch-performance.md; ledgers/CONTINUITY_ios-p4b-branding-device-refresh.md

## Open Questions (UNCONFIRMED)

- UNCONFIRMED: whether MJ observed a process crash, a backend-cold-start UI silence, or both.
- Resolved: no device crash report has synced to this Mac, and no AcademyWatch report is exposed by the connected device.

## Working Set

- `academy-watch-ios/`
- `~/Library/Logs/DiagnosticReports/`
- `~/Library/Logs/CrashReporter/MobileDevice/`
- `scratchpad/ios-diag-coldstart.png`
- Simulator `iPhone 17 Pro` / device `A44DF4A4-65C2-5A1E-9B95-F4479737A8F6`

## Notes

- 2026-07-15: Diagnostic started at exact local HEAD `600c314e006c777596b645e152c0685bfc429413`.
- 2026-07-15 crash-report evidence: `~/Library/Logs/DiagnosticReports` contains 68 `.ips`/`.crash` files, but filename/content searches for `AcademyWatch`, `Academy Watch`, and `com.theacademywatch.app` returned none; `~/Library/Logs/CrashReporter/MobileDevice` contains zero `.ips`/`.crash` files.
- 2026-07-15 direct-device evidence: MJ's phone reported `passcodeRequired: false`, `unlockedSinceBoot: true`; `devicectl device info files --domain-type systemCrashLogs --search AcademyWatch` returned `0 files`.
- 2026-07-15 baseline build: clean simulator `xcodebuild` against booted iPhone 17 Pro (`069084FF-086B-478E-8BBB-B69C791436CE`, iOS 26.2) succeeded from a clean DerivedData path.
- 2026-07-15 fresh-install baseline: app uninstall/install succeeded. Production was already warm, so first row rendered in `2.864s` from network; `/scout/players` network `0.774s`, decode `0.016s`, 39,081 bytes; `/scout/leaderboards` network `1.008s`, decode `0.007s`, 24,190 bytes.
- Warm-up evidence: `/api/health` completed in `1.068s` after the players response (`0.774s`); it is detached and does not gate Scout loading. No process exit/crash occurred.
- Prior same-branch cold evidence remains the reproducible cold-container baseline: P4a measured first row `29.716s`, players network `28.957s`/decode `0.004s`, boards network `29.443s`/decode `0.001s`.
- Current empty-cache UI: leaderboard cards show skeleton rows and a spinner; player results show only `Scouting talent…` plus `Loading…` count. It communicates generic activity but gives no backend wake-up explanation or elapsed progress during a ~29s cold start.
- Cache/schema: P4a `8fab3b1` and P4b `600c314` have identical Scout model/cache/ViewModel blobs; live cache is schema 1; cache actor catches all read/decode errors as misses. Added old-schema/incompatible-payload regression coverage.
- Main-thread/decode: cache work runs on `ScoutResponseCache` actor and API decode is non-actor-isolated; fresh decode measured `0.016s` players / `0.007s` boards, while prior cold decode was `0.004s` / `0.001s`.
- AsyncImage: `CFNETWORK_DIAGNOSTICS=3` on a fresh launch showed only two visible `media.api-sports.io` images after player data, completing in ~0.111s/~0.129s; no 25-row storm.
- Keychain: token lookup is synchronous in `AuthManager` but any Security error is swallowed to signed-out; accessibility is `AfterFirstUnlockThisDeviceOnly`. A measured failing simulator lookup returned in ~24ms; added `errSecInteractionNotAllowed` startup regression coverage. No source fix justified.
- Debugger: Xcode's physical-device run result is `succeeded`, not crashed, and warns missing device support plus process-memory `libobjc` symbol reads that reduce performance. Same-cache timing was `1.516s` console/no debugger versus `5.180s` with LLDB; Xcode also injects Metal debug, Main Thread Checker, View Debugger, and synchronous log capture.
- Implementation: empty-cache player loads retain monotonic start uptime; before 3s the existing spinner remains, from 3s onward the UI displays `Waking up the match server…`, `Still working — Ns elapsed`, and first-visit context. Cache hit/response/error/cancellation/revision changes clear the state.
- Focused tests: first attempt failed before build because custom simulator `0CF1A268-F170-4761-A644-A26AF3003368` disappeared (xcodebuild exit 70). Single retry on booted iPhone 17 Pro succeeded: 17 tests, 0 failures, including new elapsed-state lifecycle, incompatible cache, and unavailable Keychain cases.
- Read-only review: the initial implementation treated any cached response as visible data. Fixed the real empty-payload edge so a valid cache envelope containing zero players still starts delayed cold feedback; added a regression test. Follow-up review reported no remaining findings.
- Final verification: `xcodegen generate` succeeded with no project drift; final simulator build succeeded; `/tmp/academy-watch-ios-diag-final/Logs/Test/Test-AcademyWatch-2026.07.15_14-36-33-+0900.xcresult` reports 55 passed, 0 failed, 0 skipped; `git diff --check` passed.
- Screenshot verification: Azure currently reports `minReplicas: 1`, so production stayed warm and the historic 29.716s network-cold condition was not naturally repeatable without disrupting the deployed service. A fresh install plus temporary DEBUG-only 60s request delay captured the same empty-cache wait path at 14s; the delay was removed immediately and is absent from the final diff. `scratchpad/ios-diag-coldstart.png` was visually verified with SHA-256 `c61bfc168f23de2b3dbd091c96a36bef49cb048c0d3af47968ba694d735a45fa`.
- Device verification: signed device build succeeded as `Apple Development: Michael Jones (GXQMXX8C62)`; `devicectl device install app` succeeded for `com.theacademywatch.app` at `/private/var/containers/Bundle/Application/37E4ECAD-BBE2-46D9-A2D7-137616F4AB50/AcademyWatch.app/`. Lock state was `passcodeRequired: true`, `unlockedSinceBoot: true`. Best-effort launch failed only with `FBSOpenApplicationErrorDomain error 7`: `Unable to launch com.theacademywatch.app because the device was not, or could not be, unlocked.`
