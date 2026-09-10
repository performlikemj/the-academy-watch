#!/bin/bash
# lane-gate.sh — the qwen lane's gate for this repo (two tiers, harness docs/ORCHESTRATION.md "Two gate tiers").
#
#   ./lane-gate.sh <TASK> fast   slice gate: CI lint mirrors + ONLY the tests briefs/<TASK>.gate names
#   ./lane-gate.sh all   full    lane gate: CI lint/build mirrors + complete backend and frontend test suites
#
# A briefs/<TASK>.gate file is sourced bash with up to three variables:
#   BACKEND_TESTS="tests/test_a.py tests/test_b.py"   # run from academy-watch-backend/ with the .loan python
#   FRONTEND_TESTS="tests/x.test.mjs"                 # run from academy-watch-frontend/ with node --test
#   FRONTEND_BUILD=1                                  # also run pnpm lint + pnpm build (the frontend CI gates)
#
# The full tier runs pytest and node scripts/run-tests.mjs with the test environment from
# .github/workflows/ci.yml, plus ruff check + ruff format --check + pnpm lint + pnpm build.
# The fast tier runs only brief-named tests. With task `all`, a missing named test file is
# SKIPPED with a visible line (briefs not landed yet); with a specific task it is RED.
set -u

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
TASK=${1:-all}
TIER=${2:-fast}
PY=${LANE_PY:-/Users/michaeljones/Projects/loanarmy/.loan/bin/python}
BACKEND="$ROOT/academy-watch-backend"
FRONTEND="$ROOT/academy-watch-frontend"
LOGGER="${HARNESS_ROOT:-$HOME/Projects/harness}/telemetry/log-event.sh"

case "$TIER" in
  fast | full) ;;
  *) echo "lane-gate: tier must be fast or full, got '$TIER'" >&2; exit 2 ;;
esac
cd "$ROOT" || exit 2
START=$(date +%s)

finish() {
  status=$1
  dur=$(( $(date +%s) - START ))
  if [ -f "$LOGGER" ]; then
    /bin/bash "$LOGGER" gate "lane-gate.sh $TASK $TIER" "$status" "$dur" "tier=$TIER task=$TASK" > /dev/null 2>&1 || :
  fi
  if [ "$status" -eq 0 ]; then
    echo
    echo "GATE GREEN (task=$TASK tier=$TIER ${dur}s)"
  else
    echo
    echo "GATE RED (task=$TASK tier=$TIER ${dur}s) — read the FIRST error above" >&2
  fi
  exit "$status"
}

step() {
  echo
  echo "── gate step: $*"
}

# ---- collect the test lists ------------------------------------------------------------------
if [ "$TASK" = all ]; then
  gate_files=$(ls "$ROOT"/briefs/*.gate 2>/dev/null)
else
  gate_files="$ROOT/briefs/$TASK.gate"
  if [ ! -f "$gate_files" ]; then
    echo "lane-gate: no gate file briefs/$TASK.gate (every brief ships one)" >&2
    finish 2
  fi
fi
BACKEND_TESTS=
FRONTEND_TESTS=
FRONTEND_BUILD=0
for g in $gate_files; do
  eval "$(/bin/bash -c '. "$1"; printf "bt=%q\nft=%q\nfb=%q\n" "${BACKEND_TESTS-}" "${FRONTEND_TESTS-}" "${FRONTEND_BUILD-0}"' _ "$g")"
  BACKEND_TESTS="$BACKEND_TESTS $bt"
  FRONTEND_TESTS="$FRONTEND_TESTS $ft"
  if [ "$fb" = 1 ]; then FRONTEND_BUILD=1; fi
done
BACKEND_TESTS=$(printf '%s\n' $BACKEND_TESTS | awk 'NF && !seen[$0]++' | tr '\n' ' ')
FRONTEND_TESTS=$(printf '%s\n' $FRONTEND_TESTS | awk 'NF && !seen[$0]++' | tr '\n' ' ')
if [ "$TIER" = full ]; then FRONTEND_BUILD=1; fi

echo "lane-gate: task=$TASK tier=$TIER"
if [ "$TIER" = full ]; then
  echo "lane-gate: backend tests: complete suite (pytest -q)"
  echo "lane-gate: frontend tests: complete suite (node scripts/run-tests.mjs)   lint+build: $FRONTEND_BUILD"
else
  echo "lane-gate: backend tests: ${BACKEND_TESTS:-(none)}"
  echo "lane-gate: frontend tests: ${FRONTEND_TESTS:-(none)}   lint+build: $FRONTEND_BUILD"
fi

# ---- 1. backend lint — the two CI gates, BOTH required (format --check is separate from check)
step "ruff check academy-watch-backend"
ruff check --no-cache academy-watch-backend || finish 1
step "ruff format --check academy-watch-backend"
ruff format --check --no-cache academy-watch-backend || finish 1

# ---- 2. backend tests — complete suite in full, named files in fast
if [ "$TIER" = full ]; then
  step "pytest (from academy-watch-backend/): complete suite"
  (cd "$BACKEND" && SKIP_API_HANDSHAKE=1 API_USE_STUB_DATA=true TEST_ONLY_MANU=false OPENAI_API_KEY=test-not-a-real-key "$PY" -m pytest -q) || finish 1
elif [ -n "${BACKEND_TESTS// /}" ]; then
  step "pytest (from academy-watch-backend/): $BACKEND_TESTS"
  present=
  for t in $BACKEND_TESTS; do
    if [ ! -f "$BACKEND/$t" ]; then
      if [ "$TASK" = all ]; then echo "lane-gate: SKIP (not landed yet): $t"; continue; fi
      echo "lane-gate: named backend test file missing: $t" >&2; finish 1
    fi
    present="$present $t"
  done
  if [ -n "${present// /}" ]; then (cd "$BACKEND" && API_USE_STUB_DATA=true SKIP_API_HANDSHAKE=1 "$PY" -m pytest -q -p no:cacheprovider $present) || finish 1; fi
else
  echo "(no backend tests named)"
fi

# ---- 3. frontend unit tests — CI runner in full, named files in fast
if [ "$TIER" = full ]; then
  step "node scripts/run-tests.mjs (from academy-watch-frontend/): complete suite"
  (cd "$FRONTEND" && node scripts/run-tests.mjs) || finish 1
elif [ -n "${FRONTEND_TESTS// /}" ]; then
  step "node --test (from academy-watch-frontend/): $FRONTEND_TESTS"
  presentf=
  for t in $FRONTEND_TESTS; do
    if [ ! -f "$FRONTEND/$t" ]; then
      if [ "$TASK" = all ]; then echo "lane-gate: SKIP (not landed yet): $t"; continue; fi
      echo "lane-gate: named frontend test file missing: $t" >&2; finish 1
    fi
    presentf="$presentf $t"
  done
  if [ -n "${presentf// /}" ]; then (cd "$FRONTEND" && node --test --test-concurrency=1 $presentf) || finish 1; fi
else
  echo "(no frontend tests named)"
fi

# ---- 4. frontend CI mirrors — pnpm lint AND pnpm build (a build error reddens CI even with clean lint)
if [ "$FRONTEND_BUILD" = 1 ]; then
  step "pnpm lint (academy-watch-frontend)"
  (cd "$FRONTEND" && pnpm lint) || finish 1
  step "pnpm build (academy-watch-frontend)"
  (cd "$FRONTEND" && pnpm build) || finish 1
else
  echo "(frontend lint/build not requested by this task)"
fi

finish 0
