# Live iOS UI smoke tests

`AcademyWatchUITests` runs against the live API. The target is skipped in the regular `AcademyWatch` scheme so ordinary unit-test runs stay offline.

Every reviewer walk requests a login code and therefore emails the review mailbox. Provide reviewer credentials only through the test-runner environment; never put their values in source, command output, result-bundle names, or screenshots filenames.

```sh
export TEST_RUNNER_SMOKE_OUT="$OUT"
export TEST_RUNNER_REVIEW_SCOUT_EMAIL
export TEST_RUNNER_REVIEW_SCOUT_CODE

xcodebuild test \
  -project AcademyWatch.xcodeproj \
  -scheme AcademyWatchUISmoke \
  -destination 'platform=iOS Simulator,name=iPhone 17' \
  -only-testing:AcademyWatchUITests

printf '' | pbcopy
```

Run the clipboard-clear command even when `xcodebuild` fails. The UI runner also uses local-only, expiring pasteboard items and clears the Simulator pasteboard after each Paste action and at the start of teardown.
