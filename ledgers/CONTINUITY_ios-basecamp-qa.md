# iOS player/club Basecamp QA

Parent: CONTINUITY.md
Root: CONTINUITY.md
Related: ledgers/CONTINUITY_ios-player-club-experience.md
Owner: /root

## Goal
- Execute the requested player/coach QA on Basecamp and record evidence for each checklist item.

## Constraints / Assumptions
- User explicitly authorized Basecamp QA. Use isolated test data and branch checkout; preserve running workers and services.
- No production mutations, real participant emails, deployment, or App Store submission.
- Simulator fixtures, real local API/browser checks, and physical-device checks must be reported separately.

## State
- Done: Located Basecamp SSH endpoint and confirmed access.
- Now: Basecamp automated QA complete; 27 screenshots packaged and QA report ready for PR #1045.
- Next: Review PR #1045. Release still needs a deployed native/web session, real email/media transfer, and physical-device install.

## Open questions
- Basecamp Xcode 26.6, iOS 26.5; dedicated iPhone 17 simulator 566D42C1-EDD8-4BF0-B053-E96223695119.

## Working set
- Basecamp: mjjones@100.82.160.117.
- Source branch: feat/ios-player-club-experience, draft PR #1045.

## Notes
- SSH read-only preflight succeeded; zsh unmatched optional path glob prevented directory listing, will use explicit discovery.

## QA milestones
- Basecamp checkout `~/Projects/loanarmy-ios-qa` at d54ecd97; existing matching-lockfile frontend dependencies reused, no installation.
- 197 iOS unit/API tests passed. Five original native fixture UI walks passed; seven screenshots exported.
- 22 existing Playwright invitation/feedback scenarios passed at desktop and mobile widths (mocked APIs).
- Initial backend batch: 317 passed, 6 failed, 11 errors. PostgreSQL URL used absent psycopg2; switched to installed psycopg without installing dependencies.
- Correcting test setup: one auth test omitted an admin key; public media/claim tests omitted a resolvable player; pre-s4a1 recovery test retained a newer feedback table with a foreign key. Product code unchanged.
- User requested screenshots and authorized using their account for emails if needed; isolated tests currently require no live email.
- Expanded native checks cover invitation cancellation, feedback open without acknowledgment, and public-share entry. Dark/large-text pass running.
- Corrected backend suite now passes 334/334, including all 11 PostgreSQL cases. Ruff check/format pass for all four fixture files.
- Cancellation check passed after using the actual iOS 26 popover dismissal region; dialog initially exposed no Cancel button.
- Visual inspection found white-on-pale-pink filled buttons in dark mode. Changed four new Home/invitation/feedback actions to existing claretFill/claretOnFill tokens; final eight-scenario UI run and screenshots pending.
- Final dark-mode/standard-XXXL native run: 8 passed, zero failures/skips (`ios-ui-final.xcresult`), eleven screenshots exported.
- Visual review covered player/club Home, pending/approved profiles, age error, editor, private feedback, invitation state, and mobile web feedback.
- Final backend 334 passed, iOS unit/API 197 passed, web component journeys 22 passed; no live mail or production mutation.
- QA report: `docs/qa/ios-player-club-basecamp.md`; local screenshots/index: primary checkout `scratchpad/ios-basecamp-qa/`.
- Final screenshots confirm dark filled-button contrast correction; cancellation leaves invitation pending. Local bundle: `scratchpad/ios-basecamp-qa/screenshots-and-qa.zip`.
