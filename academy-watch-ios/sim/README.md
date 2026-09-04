# Academy Watch iOS sim lane

This lane runs Yuki's signed-out fan journey against the loopback-only Flask stub backend. It never uses the live API or reviewer credentials.

## Run

From the repository root:

```bash
academy-watch-ios/sim/backend.sh start
SIM_APP_ROOT=. SIM_PROJECT=academy-watch-ios/AcademyWatch.xcodeproj \
  SIM_APP=AcademyWatch SIM_BACKEND_PORT=5001 \
  HARNESS_ROOT=/Users/michaeljones/Projects/harness \
  academy-watch-ios/sim/run.sh \
  --scheme AcademyWatchUISmoke \
  --only-testing AcademyWatchUITests/JourneyRunnerUITests \
  --journey academy-watch-ios/sim/journeys/yuki-fan-scout-desk.json \
  --no-grade
academy-watch-ios/sim/backend.sh stop
```

`SIM_APP_ROOT=.` lets the nested iOS pack consume the repository-root `harness.yaml`. `SIM_BACKEND_PORT` defaults to `5001`; `run.sh` substitutes it into the journey's `${SIM_BACKEND_PORT}` launch argument, then curls `/api/health`, the Scout Desk query, and the selected player's profile before Xcode starts. It prints counts only. The launch base includes `/api` because that is the Flask blueprint root.

Use `backend.sh status` to print `running` or `stopped`. Backend logs and PID state stay under ignored `sim/.run/`; reports and caches are also ignored.

## Boundary

- CAN: unsigned DEBUG simulator builds, signed-out fan browsing against local stub mode, deterministic selectors, per-step PNG evidence, and strict local reports.
- CANNOT: signed-in journeys, reviewer-code delivery, device signing, TestFlight/App Store behavior, or production truth.
- FORBIDDEN: pointing `-apiBaseURL` anywhere except HTTP loopback or running this journey against the live API.

`SmokeUITests.swift` remains a separate live-API walk surface. Do not run it for this lane; the sim runner selects only `JourneyRunnerUITests` under `AcademyWatchUISmoke`.
