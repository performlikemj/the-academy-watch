# Player and club QA on Basecamp

Date: 2026-09-06. Feature: PR #1045, `feat/ios-player-club-experience`.
Source baseline: `d54ecd973bc50ab49c283fd93247ec6cdabb641a`, plus the QA test corrections and filled-button contrast fix in this PR.

## Environment and evidence

- Basecamp checkout: `/Users/mjjones/Projects/loanarmy-ios-qa`.
- Xcode 26.6; iPhone 17 simulator running iOS 26.5. Dedicated device: `566D42C1-EDD8-4BF0-B053-E96223695119`.
- Native UI: explicit offline fixture responses, with all app API calls intercepted. These walks run real SwiftUI screens but do not connect to a live backend.
- Browser: Chromium at 1280px and 390px, real club invitation and feedback components with mocked APIs.
- Backend: real Flask routes and database writes in isolated SQLite fixtures; PostgreSQL migration/concurrency cases use the disposable `pilot_p2_ios_qa_20260906` database with the installed psycopg driver. Photo lifecycle uses local development storage.
- Frontend dependencies reused from the existing Basecamp installation after verifying identical lockfiles; no dependency installation or lockfile changes.
- Raw evidence is under `scratchpad/basecamp-qa/` in the Basecamp checkout. Retrieved screenshots and report are under `scratchpad/ios-basecamp-qa/` in MJ's primary checkout.
- No live login emails, production records, deployment, or TestFlight upload. MJ authorized using his account for email if needed; these checks did not need it.

## Results

| Layer | Result | Evidence |
| --- | --- | --- |
| iOS unit/API tests | 197 passed, zero failures/skips | `ios-unit.xcresult` |
| Original native walkthroughs, light/default text | 5 passed | `ios-ui.xcresult`, seven screenshots |
| Expanded native walkthroughs, dark/XXXL standard text | 8 passed after contrast fix | `ios-ui-final.xcresult`, eleven screenshots |
| Browser invitation/feedback journeys | 22 passed | `web.log`, `web-results/` screenshots |
| Backend account/claims/showcase/photos/club/feedback | 334 passed, zero failures/skips, including PostgreSQL | `backend-final.xml`, `backend-final.log` |

The backend run emits 52 deprecation warnings for the existing Flask-Migrate `get_engine` integration. The only app change in this QA follow-up is using the existing high-contrast fill/foreground tokens on four new filled actions.

## Checklist coverage

“Automated coverage” below means the named layer passed; it does not claim one continuous TestFlight-to-live-backend session.

| QA | Check | Automated coverage | Still needed for release sign-off |
| --- | --- | --- | --- |
| 1 | Fresh install, role selection, email sign-in | Native Home entry; native auth tests; request/verify-code backend tests with mocked email | Real email receipt and sign-in on the distributed binary |
| 2 | Find existing identity or create new | Native find/create journey; backend claim and identity cases | One real existing identity and one genuine new player through the deployed API |
| 3 | Missing or underage self-claim evidence | Visible native missing-age error; iOS age-boundary tests; backend age gates | Physical-device usability confirmation |
| 4 | Pending profile remains accessible | Native pending-claim destination and no owner/share actions; backend claim listing | Kill/relaunch against the same persisted live claim |
| 5 | Approval unlocks owner tools | Separate pending and approved native states; backend approval/permission tests | Admin approval followed by player refresh in the same live session |
| 6 | Edit basics and retain other web fields | Native save interaction; PATCH serialization/persistence and trust tests | Edit/relaunch in a native session using the deployed PATCH endpoint |
| 7 | Photo/highlight submission and moderation | Backend real local photo upload/completion/approval/rejection/public visibility, EXIF stripping; showcase/reel tests | Native Photos picker to Azure Blob upload and approved YouTube playback |
| 8 | Share eligible public profile | Native share entry present only for approved fixture; URL validation; public/private route tests | System share sheet and signed-out browser resolution of a real public profile |
| 9 | Coach workspace and permissions | Native My club/verification entry; backend club-manager permission tests | Safari handoff and same-email web sign-in from distributed iOS app |
| 10–11 | Invite, explicit acceptance, roster connection | Browser manager-to-player flow; native explicit acceptance; backend identity pinning and roster persistence/concurrency | Continuous web-coach to native-player session against the same deployed backend |
| 12–13 | Publish, read, acknowledge feedback | Browser publication/revision/withdrawal; native read/acknowledgment; backend private access and persisted per-revision acknowledgment | Continuous web-coach/native-player loop after deployment |
| A | Cancel invitation acceptance | Native cancellation passed using the observed popover dismissal control; backend acceptance requires explicit request | None specific to cancellation beyond the live-session check |
| B | Interrupted save/upload | Backend upload failure cleanup; native credential-bound upload and model error tests; browser draft retry | Real device network interruption during an Azure upload |
| C | Sign-out/account switch privacy | Native auth/model tests; browser delayed-response/logout/account-change tests; backend wrong-account rejection | Native end-to-end switch between two real accounts |
| D | Dark mode and large text | Dark/standard XXXL walkthrough screenshots; mobile browser layout checks | Physical-device maximum accessibility size and VoiceOver pass |
| E | Return the following week | Not elapsed | Real participant return and new feedback next week |

## Issues diagnosed and corrected

1. Basecamp has psycopg 3, while the first PostgreSQL command requested psycopg2. Corrected the test URL; no dependency was installed.
2. The admin-status authorization test relied on an ambient admin key. It now sets a test-only key explicitly.
3. Public claim/photo fixtures created approved claims with no underlying player identity. Added real synthetic adult tracked-player records so the public resolver, moderation, and media visibility assertions execute correctly. Existing assertions remain intact.
4. The pre-invitation migration recovery fixture created today's entire schema, including a later feedback table whose foreign key blocked removing the old invitation table. The test now removes that later table when reconstructing the older schema. Production migrations were not changed.
5. Added native checks for cancellation, public-share entry, and reading feedback without acknowledgment. iOS 26 rendered a popover with `PopoverDismissRegion` instead of the Cancel button expected by the first test version; the test now exercises the observed dismissal control.

6. Screenshot review found white text on pale pink filled actions in dark mode. Four new Home/invitation/feedback buttons now use `claretFill` with `claretOnFill`, matching existing app controls.

## Reproduce on Basecamp

From `academy-watch-ios`:

```sh
xcodebuild -project AcademyWatch.xcodeproj -scheme AcademyWatch \
  -destination 'platform=iOS Simulator,name=Academy Player Club QA' \
  -parallel-testing-enabled NO CODE_SIGNING_ALLOWED=NO test
xcodebuild -project AcademyWatch.xcodeproj -scheme AcademyWatchExperience \
  -destination 'platform=iOS Simulator,name=Academy Player Club QA' \
  -parallel-testing-enabled NO CODE_SIGNING_ALLOWED=NO test
```

From `academy-watch-backend`, using only the dedicated disposable database:

```sh
PILOT_TEST_POSTGRES_URL=postgresql+psycopg://mjjones@localhost/pilot_p2_ios_qa_20260906 \
  /Users/mjjones/Projects/loanarmy/.loan/bin/python -m pytest \
  tests/test_auth_endpoints.py tests/test_claim_verification.py \
  tests/test_showcase.py tests/test_showcase_trust.py tests/test_showcase_media.py \
  tests/test_club_console.py tests/test_club_invitations.py tests/test_player_feedback.py -q
```

With the isolated Vite server running at `http://127.0.0.1:5274`, from `academy-watch-frontend`:

```sh
E2E_BASE_URL=http://127.0.0.1:5274 pnpm exec playwright test \
  e2e/club-invitations.spec.mjs e2e/player-feedback.spec.mjs --project=chromium
```

Deploy the additive backend PATCH before distributing the next iOS binary. Update its photo privacy disclosure and select a release build through the normal release workflow. Then complete the outstanding real-device checks above.
