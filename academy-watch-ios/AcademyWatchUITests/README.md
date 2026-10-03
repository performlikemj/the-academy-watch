# Live iOS UI smoke tests

`SmokeUITests` runs against staging only after an explicit staging opt-in. Debug, simulator and test hosts refuse the production API. The target is skipped in the regular `AcademyWatch` scheme so ordinary unit-test runs stay offline.

Every reviewer walk requests a login code and therefore emails the review mailbox. Provide reviewer credentials only through the test-runner environment; never put their values in source, command output, result-bundle names, or screenshots filenames.

```sh
export TEST_RUNNER_SMOKE_OUT="$OUT"
export TEST_RUNNER_ACADEMY_SMOKE_API_URL=https://basecamp.tail37b60.ts.net:15443/api
export TEST_RUNNER_REVIEW_SCOUT_EMAIL
export TEST_RUNNER_REVIEW_SCOUT_CODE

xcodebuild test \
  -project AcademyWatch.xcodeproj \
  -scheme AcademyWatchUISmoke \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -only-testing:AcademyWatchUITests/SmokeUITests

printf '' | pbcopy
```

Run the clipboard-clear command even when `xcodebuild` fails. The UI runner also uses local-only, expiring pasteboard items and clears the Simulator pasteboard after each Paste action and at the start of teardown.

For player and coach checks without production requests, run `AcademyWatchExperience`
with `-only-testing:AcademyWatchUITests/PlayerClubExperienceUITests`. These tests
use an explicit, labeled offline fixture and an ephemeral token store; they send
no login emails and make no production changes. See `docs/ios-player-club-experience.md`.

`AcademyWatchExperience` runs the offline unit and fixture UI suites. All schemes explicitly use staging for Debug Run and loopback port 9 for Test; fixture UI launches intercept requests before networking. Unit-test hosts render an inert root. An absent or invalid developer URL displays a configuration error; it never falls back to production. Release device archives default to production; Release simulator and test hosts still refuse it.
