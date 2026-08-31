# App Sim Lane — loanarmy web

This lane drives four scripted user journeys in headless Chromium, saves a screenshot and expectation for every attempted step, and optionally asks an Ollama vision model to grade the result. It uses Node.js standard-library APIs plus the frontend's existing `@playwright/test` installation; it adds no package or SDK.

## Run locally

From the repository root:

```bash
SIM_GRADE=0 node sim/run.mjs
```

By default the runner starts the Flask backend and Vite frontend, waits for both health checks, runs all journeys, and sends `SIGTERM` only to the dedicated process groups it spawned (never to processes discovered by port). Enable grading by omitting `SIM_GRADE=0` once Ollama and the configured vision model are ready:

```bash
node sim/run.mjs
```

`SIGINT` and `SIGTERM` use that same managed-process teardown path, then close Chromium best-effort and exit `130` or `143`. A second signal exits immediately, while normal completion keeps the `finally` teardown authoritative.

The backend needs its normal database configuration and `SECRET_KEY` / `ADMIN_API_KEY` in `academy-watch-backend/.env`. To override those two values explicitly, use `SIM_SECRET_KEY` and `SIM_ADMIN_API_KEY`. For each credential, precedence is the explicit `SIM_*` override first, then the backend `.env`, then a clear error when neither exists. Ambient `SECRET_KEY` and `ADMIN_API_KEY` variables are deliberately ignored: shell profiles often retain stale values, and silently accepting one would make the simulated app differ between machines. The run header says which source was selected without printing credential values.

The runner forces `API_USE_STUB_DATA=true` and `SKIP_API_HANDSHAKE=1`. It mints the admin bearer through `SIM_PYTHON` using the backend's `itsdangerous` implementation and keeps all auth values in memory.

To use already-running servers:

```bash
SIM_EXTERNAL=1 SIM_BASE_URL=http://localhost:5173 SIM_GRADE=0 node sim/run.mjs
```

`SIM_EXTERNAL=1` disables all server boot and teardown. The supplied URL must already be reachable and must route `/api` to the matching backend.

## Run on basecamp

Use the same repository-root command. Basecamp needs Node.js, `pnpm`, frontend dependencies (including its Playwright Chromium), the `.loan` Python environment, access to the seeded database (match 4 by default), and Ollama when grading is enabled:

```bash
node sim/run.mjs
```

No basecamp-specific paths are needed when its Python is at the default location. Otherwise set `SIM_PYTHON`.

## Environment

| Variable | Default | Purpose |
| --- | --- | --- |
| `SIM_BASE_URL` | `http://localhost:5173` | App origin under test. |
| `SIM_EXTERNAL` | unset / `0` | Set to `1` to use existing servers and skip boot/teardown. |
| `SIM_PYTHON` | `/Users/michaeljones/Projects/loanarmy/.loan/bin/python` | Python with the backend and `itsdangerous` installed. |
| `SIM_ADMIN_EMAIL` | `mj@bywayofmj.com` | Email embedded in the in-memory admin bearer. |
| `SIM_SECRET_KEY` | unset | Explicit `SECRET_KEY` override; otherwise the backend `.env` value is used. |
| `SIM_ADMIN_API_KEY` | unset | Explicit `ADMIN_API_KEY` override; otherwise the backend `.env` value is used. |
| `OLLAMA_URL` | `http://127.0.0.1:11434` | Ollama HTTP origin. |
| `SIM_VISION_MODEL` | `qwen3.8:27b-obliterated-q8` | Ollama vision model used for grading and the proposal. |
| `SIM_GRADE` | `1` | Set to `0` to skip all Ollama calls; expected steps become `ungraded`. |
| `SIM_MATCH_ID` | `4` | Seeded Film Room match exercised by the player-reels journey. |

## Output and exit status

Each run writes `sim/report/<UTC timestamp>/steps.json`, `report.json`, and `shots/*.png`. `steps.json` is the raw action record, including URLs, errors, and optional payloads such as video playhead times. `report.json` contains grouped journeys, grading verdicts, totals, and at most one unexecuted exploration proposal.

The process exits `1` when any action step failed or any vision verdict is `fail`. A `concern`, an `ungraded` result, or an observed-only step does not fail the run. Ollama connection or response errors never fabricate a pass and never crash report generation.

## Pure checks

```bash
node --test sim/test/sim-lane.test.mjs
node --check sim/run.mjs
for f in sim/lib/*.mjs sim/journeys/*.mjs; do node --check "$f"; done
```
