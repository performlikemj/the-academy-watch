# iOS player and club experience

Parent: CONTINUITY.md
Root: CONTINUITY.md
Related: ledgers/CONTINUITY_ios-outreach-readiness.md; ledgers/CONTINUITY_pilot-club.md
Owner: /root

## Goal
- Implement the outreach recommendations: clear player/club onboarding, persistent profile hub, correct age validation, profile editing/sharing, and club invitation/feedback access.

## Constraints / Assumptions
- Worktree .worktrees/ios-player-club-experience, branch feat/ios-player-club-experience from origin/main 2dd1a191.
- Preserve moderation, private club footage, adult self-claim policy, and backend authorization. Role preference is navigation only.
- No production feature-flag changes, live emails, or App Store submission as part of implementation.
- No frontend dependencies required. Use native SwiftUI and existing backend contracts.

## Key decisions
- Add persistent Home with player/club/scout intent, My Profiles, and My Club; keep existing scout tools accessible.
- Native club invitation decisions and feedback reading/acknowledgment; roster/video management through existing web console.
- Native moderated bio/highlight/photo workflow where existing contracts support it; public share eligibility must come from public share API.

## State
- Done: Assessment and current backend recon; isolated latest-main worktree created.
- Now: Implementation complete, validated, and committed locally as 3723bff8; user authorized branch publication and draft PR creation; delivery in progress.
- Next: Push to performlikemj/the-academy-watch and open the authorized draft PR; inspect CI. Then deploy additive backend before release, update photo disclosure, and run a real-device pilot walkthrough.

## Links
- Upstream: CONTINUITY.md
- Related: ledgers/CONTINUITY_ios-outreach-readiness.md

## Open questions
- None blocking implementation; production pilot remains flag-gated.

## Working set
- academy-watch-ios/AcademyWatch/{App,Features,Core}
- academy-watch-ios/AcademyWatchTests and AcademyWatchUITests

## Notes
- 2026-09-06: git fetch + worktree creation passed. Sandbox denied CoreSimulator IPC; simulator validation will use normal host access.

## Implementation / validation milestones
- 2026-09-06: Home intent navigation, persistent My Profiles, claim-state next steps, unified identity search, and conditional adult age validation implemented.
- Native basics editor + moderated photo/YouTube submission; public-adult eligibility gates profile sharing; native invitation decisions and private feedback acknowledgment.
- Added basic-profile PATCH for tracked/local subjects preserving web fields and pending contract attestations under existing ownership/moderation gates; no migration.
- XcodeGen + simulator build passed. Initial unit suite 192 passed; final expanded unit/API suite 197 passed, 0 failures.
- Backend `python3.11 -m pytest tests/test_showcase.py -q`: 61 passed. Changed backend files pass Ruff lint/format.
- Four offline UI walks passed (coach, pending profile, profile edit + feedback, invitation acceptance). First fixture run failed because NSArgumentDomain overrode role updates; corrected fixture setup and all walks passed.
- Exported and inspected player-home, club-home, profile-editor screenshots; added persistent position/height labels and removed club-official tools from the player's main card list.
- XcodeGen initially rewrote MARKETING_VERSION binding; project.yml now explicitly preserves it. Privacy manifest adds selected-photo disclosure and app-only UserDefaults reason.
- CoreSimulator/xcresult export need host access; approved tool retries succeeded. No production mutations or emails.

## Final checks / release limits
- Full iOS unit/API suite: 197 passed, 0 failures (`/tmp/academy-player-club-final-unit.xcresult`).
- Five offline UI journeys: 5 passed (`/tmp/academy-player-club-ui3.xcresult`); final signup visibility assertion also passed after moving age fields earlier, replacing the clipped relationship segmented control, and scrolling errors into view (`/tmp/academy-player-club-age-visible.xcresult`).
- Backend showcase 61 passed; trust/moderation 24 passed. Ruff check + format-check and git diff --check pass.
- Unsigned Release archive passed; version binding resolves to 1.0.1. No version bump/submission made. Final form revision archive verification recorded below.
- Screenshots: primary workspace `scratchpad/ios-player-club-experience/` (player-home, club-home, profile-editor, pending-profile, feedback-acknowledged, club-connection, age-verification). Explicit offline fixtures only.
- Deploy basic-profile PATCH first (no migration). Pilot relationship/feedback flag stays as configured. Before submitting a new binary, update App Store Connect Photos or Videos disclosure and select version/build.
- Native core player/club flows implemented. Advanced club roster/video and profile tools retain explicit web handoffs; full youth consent, universal links, and push notifications are outside this delivery.
- No frontend dependency install, no production mutations, and no login emails. Production photo-storage acceptance and real App Store device walk remain release checks.

## Delivery
- Commit: `3723bff8` on `feat/ios-player-club-experience`; implementation complete locally.
- Final unsigned archive: `/tmp/AcademyPlayerClubFinal.xcarchive` — ARCHIVE SUCCEEDED.
- PR title/body prepared at `/tmp/academy-player-club-pr.md`; no PR exists yet.
- Automatic approval review rejected `git push -u origin feat/ios-player-club-experience`: publication to an external/unverified remote was not explicitly authorized by the build request. No workaround or alternate publication attempted. Await explicit authorization for `performlikemj/the-academy-watch`.

- 2026-09-06: User explicitly approved the requested push to `performlikemj/the-academy-watch` and draft PR creation ("go for it"). Prior publication blocker resolved.
