# Native GOL verification

GOL is the first card in Account for every role. Keeping this entry outside the
role-specific tab inventory preserves Scout Desk as the scout landing screen
and keeps all five player/club tabs visible. The root presents the chat so a
successful sign-in does not dismiss it when Account rebuilds its protected state.

The chat is in memory. New chat resets the session ID and messages. Each question
freezes its message, last 20 history entries (including assistant tool calls and
tool results), session ID and client message ID. Retry resends that same snapshot.
Stopping after text or a card marks the answer cut short; stopping before either
allows retry with the original ID. A terminal partial replay cannot be retried.
Refund usage frames are processed even after a stream error. Unknown SSE events
are ignored, and unknown cards use a bounded plain-text field summary.

Usage shows only free-question and credit counts. Account access failures use
controlled native messages. No purchase action or destination is rendered;
server error text and additional usage fields are never used as UI instructions.

## Local end-to-end test

Use a dedicated simulator and DerivedData path. This test starts signed out; use
a new simulator or reset **only that simulator's** Keychain before running it.
Do not run the live email smoke scheme.

```sh
# From repo root, in a separate terminal. Only the explicitly selected synthetic
# user's GOL rows are reset. Flask uses local soccer_newsletter on 127.0.0.1.
# Choose a free port (the default is 53971).
/path/to/venv/bin/python academy-watch-ios/sim/fixtures/gol_local_server.py \
  --key-file /path/to/local/backend.env

xcodegen generate --spec academy-watch-ios/project.yml
TEST_RUNNER_GOL_LOCAL_API_URL=http://127.0.0.1:53971/api \
xcodebuild -project academy-watch-ios/AcademyWatch.xcodeproj \
  -scheme AcademyWatchExperience -configuration Debug \
  -destination "platform=iOS Simulator,id=$GOL_SIMULATOR_ID" \
  -derivedDataPath .gol-derived -parallel-testing-enabled NO \
  -only-testing:AcademyWatchUITests/GolChatUITests \
  -resultBundlePath /tmp/gol-local-ui.xcresult test
```

The local launcher imports the real `src/main.py` app with database host/name
assertions, email delivery disabled, a synthetic account, and a one-question free
allowance. It reads only model/football API credentials from the supplied file;
other inherited configuration is discarded. Authentication, credit reservation,
SSE serialization and exhaustion all use the real backend. The public synthetic
review credential exists only on this local process. Do not expose its port.

If no LLM key is available, opt in to `--fixture-model`: only
`GolService._run_completion` is replaced in this test launcher, with explicitly
synthetic timed tokens. Nothing in the shipped application stubs chat responses.
The football API credential is still needed by the backend's normal startup.

The application accepts `ACADEMY_LOCAL_API_URL` only in Debug simulator builds,
only for an HTTP loopback `/api` URL. Release always defaults to the production
API. The integration test skips unless explicitly given a loopback address.

The test attaches five screenshots: signed out, starter prompts, streaming,
completed answer, and exhausted questions. Export with:

```sh
xcrun xcresulttool export attachments --path /tmp/gol-local-ui.xcresult \
  --output-path /tmp/gol-shots
```

## Offline gates

`AcademyWatch` runs the full unit/API suite. `AcademyWatchExperience` runs the
existing player/club suite; the local GOL test skips without its environment flag.
Select `TEST_RUNNER_SIM_JOURNEYS=gol-entry` to run the bundled Account-to-chat story
through `JourneyRunnerUITests`. That story proves entry, composer and starter
prompts only; the separate local integration test proves streaming and 402.
The offline experience transport fails closed if asked to send a GOL request.
