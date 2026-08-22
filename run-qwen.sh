#!/bin/bash
# Run one lane task through the pinned dsh + qwen model (basecamp/forge server by default), in THIS
# loanarmy worktree. Copied from the nbhd-ios constellation-growth lane (2026-08-22) and adapted.
#
# The task id names a brief the ORCHESTRATOR authors at briefs/<TASK>.md (task-brief standard,
# ~/Projects/harness/core/templates/task-brief.md) plus its gate list briefs/<TASK>.gate. This runner
# never writes briefs or code. HARNESS_TASK_PROMPT overrides the constructed prompt for one-off probes.
# Usage: ./run-qwen.sh P0-A1 [think=off]
#        ./run-qwen.sh --resume-with-answer <session> "<answer>"
#        ./run-qwen.sh --resume-paused <session>
#
# Boot pitfalls this script encodes are documented in
# ~/Projects/harness/adapters/dsh/README.md ("Boot pitfalls, validated 2026-08-20, rc.7").
#
# MODEL/SERVER. Default patch is adapters/dsh/qwen-forge.patch.yml → ollama on basecamp
# (192.168.86.96:11434, qwen3.8:27b-mlx-bf16, keep-alive forever). HARNESS_PATCH / HARNESS_MODEL
# override (e.g. the laptop's qwen-local.patch.yml + qwen3.8:27b-q3-oc64k).
#
# THINKING DIAL. The optional second argument think=off appends " /no_think" to the task prompt
# (the qwen3-family soft switch). Default is thinking on. Surgical tasks want think=off.
#
# HELP LANE (telemetry v1.3). Contract: ~/Projects/harness/telemetry/HELP.md. The worker writes
# .harness/help/<session>.json and stops; this runner notices, logs a `help` event, PAUSES the budget
# clock, and exits 4. Someone answers with:
#   ./run-qwen.sh --resume-with-answer <session> "<answer>"
# which relaunches with the answer prepended (fresh session — rc.7 headless cannot --resume) and the
# budget resumed from where it paused. missing_package NEVER auto-installs (orchestrator, off-sandbox).
#
# THE SANDBOX AND THE GATE. dsh workspace-write = macOS Seatbelt: read anything, write only inside this
# worktree (+/tmp, $TMPDIR). This repo's gate (lane-gate.sh: ruff + named pytest files via the primary
# checkout's .loan venv, named node --test files, pnpm lint+build) runs INSIDE that profile — verified
# by the orchestrator with sandbox-exec before the first dispatch — so qwen runs `make gate TASK=<id>`
# itself during the task. THE RUNNER STILL RE-RUNS THE GATE after dsh exits, outside the sandbox, under
# the session's dsh/qwen identity (HARNESS_RUN_GATE=0 turns that off). A red post-gate makes this script
# exit with the gate's status, so one command means "qwen finished AND the gate is green".
#
# LIVENESS, NUDGES, BUDGET (telemetry v1.1 + v1.2). A background pulse logs content-free vitals every
# two minutes. Two wall-clock guards sit on top:
#   - Idle nudge: no file writes under the ACTIVITY PATHS for HARNESS_NUDGE_IDLE_S seconds (default
#     900; the FIRST nudge waits twice that — reading a brief is not stalling) stops the dsh tree and
#     restarts the step. At most HARNESS_MAX_NUDGES (default 2), each logged as a `nudge` event.
#   - Budget: HARNESS_BUDGET_S seconds (default 5400) ends the run. Tree stopped TERM-then-KILL, a
#     `budget` event logged, exit 3.
# GUARD PRECEDENCE: help is checked FIRST, including after dsh has already exited. Budget is checked
# before the idle nudge, so a run near its limit ends rather than restarting.
#
# ACTIVITY PATHS are the model's work product only (backend src/tests/migrations, frontend src/tests).
# .harness/telemetry.jsonl is deliberately NOT one (the pulse writes to it — live T3b lesson).
#
# POWER GUARD. Running on battery is refused with exit 5 before any session exists (HARNESS_ALLOW_BATTERY=1
# overrides). Inference is on basecamp, but dsh + the gate run here and the lesson stands.
# LOW-BATTERY PAUSE. Below HARNESS_BATTERY_MIN (default 25, 0 disables) on battery the run winds down at a
# quiet spot, persists the paused budget, exits 6; resume with ./run-qwen.sh --resume-paused <session>.
#
# EXIT CODES: 0 the worker's own status (and the gate was green) · 2 bad arguments · 3 budget exhausted ·
#             4 help requested · 5 refused to launch (on battery) · 6 paused (battery low) ·
#             anything else = the post-run gate's exit status (qwen stopped cleanly but the gate is red)
#
# Overrides, both for testing: HARNESS_ROOT points at a different harness checkout, HARNESS_DSH_BIN
# substitutes another command for dsh (see the nbhd-ios lane runner header for the fake-dsh drill).

set -u

# Hold the machine awake for the whole run, then hand off to the real script. A run that outlives
# the display sleeping used to die with it (2026-08-20). Absent caffeinate this is a silent no-op.
if [ -z "${HARNESS_CAFFEINATED-}" ] && command -v caffeinate > /dev/null 2>&1; then
  export HARNESS_CAFFEINATED=1
  exec caffeinate -is "$0" "$@"
fi

usage() {
  echo "usage: ./run-qwen.sh <TASK-ID> [think=off]            e.g. ./run-qwen.sh P0-A1 think=off" >&2
  echo "       ./run-qwen.sh --resume-with-answer <session> \"<answer>\"" >&2
  echo "       ./run-qwen.sh --resume-paused <session>" >&2
  echo "exit codes: 0 the worker's own status · 2 bad arguments · 3 budget exhausted" >&2
  echo "            4 help requested, answer it and resume · 5 refused: on battery" >&2
  echo "            6 paused: battery below the reserve, resume with --resume-paused" >&2
  echo "HARNESS_ALLOW_BATTERY=1 launches anyway on battery; HARNESS_BATTERY_MIN=0 disables the" >&2
  echo "low-battery pause." >&2
}

MODE=fresh
RESUME_SESSION=
ANSWER=
TASK=
THINK=think=on

case "${1-}" in
  --resume-with-answer)
    MODE=answer
    RESUME_SESSION=${2-}
    ANSWER=${3-}
    if [ -z "$RESUME_SESSION" ] || [ -z "$ANSWER" ] || [ $# -gt 3 ]; then usage; exit 2; fi
    ;;
  --resume-paused)
    MODE=paused
    RESUME_SESSION=${2-}
    if [ -z "$RESUME_SESSION" ] || [ $# -gt 2 ]; then usage; exit 2; fi
    ;;
  *)
    TASK=${1-}
    THINK=${2-think=on}
    if [ -z "$TASK" ] || [ $# -gt 2 ]; then usage; exit 2; fi
    case "$THINK" in
      think=on | think=off) ;;
      *)
        echo "run-qwen: second argument must be think=on or think=off, got '$THINK'" >&2
        exit 2
        ;;
    esac
    ;;
esac

REPO=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
HARNESS=${HARNESS_ROOT:-/Users/michaeljones/Projects/harness}
DSH_BIN=${HARNESS_DSH_BIN:-$HARNESS/adapters/dsh/runtime/node_modules/.bin/dsh}
PATCH="${HARNESS_PATCH:-$HARNESS/adapters/dsh/qwen-forge.patch.yml}"
PULSE="$HARNESS/telemetry/pulse.sh"
LOGGER="$HARNESS/telemetry/log-event.sh"
RUN_STATE="$HARNESS/telemetry/run-state.sh"

# The model's work product — the only places a write counts as activity.
ACTIVITY_PATHS="academy-watch-backend/src academy-watch-backend/tests academy-watch-backend/migrations academy-watch-frontend/src academy-watch-frontend/tests"

BUDGET_S=${HARNESS_BUDGET_S:-5400}
NUDGE_IDLE_S=${HARNESS_NUDGE_IDLE_S:-900}
MAX_NUDGES=${HARNESS_MAX_NUDGES:-2}
# Reading a brief and its anchors is not stalling. The FIRST nudge gets a longer fuse; the
# rest use the normal idle threshold.
FIRST_NUDGE_S=${HARNESS_FIRST_NUDGE_S:-$((NUDGE_IDLE_S * 2))}
# Slices verify FAST (the brief's named tests + CI lint mirrors); the lane verifies FULL (every
# brief's tests + pnpm lint/build) before any push. Law 3 lives at the merge.
GATE_TIER=${HARNESS_GATE_TIER:-fast}
case "$GATE_TIER" in
  fast | full) ;;
  *) echo "run-qwen: HARNESS_GATE_TIER must be fast or full, got '$GATE_TIER'" >&2; exit 2 ;;
esac
GATE_CMD=${HARNESS_GATE_CMD:-}
RUN_GATE=${HARNESS_RUN_GATE:-1}
BATTERY_MIN=${HARNESS_BATTERY_MIN:-25}
QUIET_S=${HARNESS_QUIET_S:-30}
QUIET_MAX_S=${HARNESS_QUIET_MAX_S:-120}
for setting in "$BUDGET_S" "$NUDGE_IDLE_S" "$MAX_NUDGES" "$BATTERY_MIN" "$QUIET_S" "$QUIET_MAX_S" "$FIRST_NUDGE_S"; do
  case "$setting" in
    '' | *[!0-9]*)
      echo "run-qwen: budget, nudge idle, and nudge count must be whole numbers, got '$setting'" >&2
      exit 2
      ;;
  esac
done

# POWER GUARD. Refuse to start on battery, for a fresh run and a resumed one alike. Runs before any
# session exists, so a refusal logs nothing. Absent pmset (not macOS) the guard does not apply.
on_battery() {
  command -v pmset > /dev/null 2>&1 || return 1
  pmset -g batt 2>/dev/null | grep -q "Now drawing from 'Battery Power'"
}

if [ "${HARNESS_ALLOW_BATTERY-}" != 1 ] && on_battery; then
  echo "run-qwen: on battery — plug in, or override with HARNESS_ALLOW_BATTERY=1" >&2
  exit 5
fi

# Node 24: dsh requires ^22.19 || >=24, and npx will not resolve the pinned tree.
export PATH="$HOME/.nvm/versions/node/v24.19.0/bin:$PATH"
export DSH_HOME="$HARNESS/adapters/dsh/dsh-home"
export DSH_TELEMETRY_MODE=DISABLED   # dsh otherwise posts to its own OTEL endpoint
export OLLAMA_API_KEY=dummy          # provider schema requires apiKeyEnv; ollama ignores it
# INEFFECTIVE AS AN EXPORT (server-side setting, measured 2026-08-20); basecamp runs keep-alive -1 anyway.
export OLLAMA_KEEP_ALIVE=95m

export HARNESS_TELEMETRY=1
export HARNESS_AGENT=dsh
export HARNESS_MODEL="${HARNESS_MODEL:-qwen3.8:27b-mlx-bf16}"

cd "$REPO" || exit 2
mkdir -p .harness/runs .harness/help

PAUSED_S=0
if [ "$MODE" != fresh ]; then
  export HARNESS_SESSION="$RESUME_SESSION"
  STATE_FILE=".harness/runs/$HARNESS_SESSION.state"
  if [ ! -f "$STATE_FILE" ] || [ ! -f "$RUN_STATE" ]; then
    echo "run-qwen: no paused run to resume for session '$HARNESS_SESSION'" >&2
    echo "run-qwen: expected $REPO/$STATE_FILE" >&2
    exit 2
  fi
  TASK=$(/bin/bash "$RUN_STATE" get "$STATE_FILE" task)
  THINK=$(/bin/bash "$RUN_STATE" get "$STATE_FILE" think)
  RESUMED_NUDGES=$(/bin/bash "$RUN_STATE" get "$STATE_FILE" nudges)
  PAUSED_AT=$(/bin/bash "$RUN_STATE" get "$STATE_FILE" paused_at)
  case "$TASK" in '') TASK=unknown ;; esac
  case "$THINK" in think=on | think=off) ;; *) THINK=think=on ;; esac
  case "$RESUMED_NUDGES" in '' | *[!0-9]*) RESUMED_NUDGES=0 ;; esac
  case "$PAUSED_AT" in '' | *[!0-9]*) PAUSED_AT=0 ;; esac
else
  export HARNESS_SESSION="qwen-$TASK-$(date -u +%Y%m%dT%H%M)"
  STATE_FILE=".harness/runs/$HARNESS_SESSION.state"
  RESUMED_NUDGES=0
fi
export HARNESS_PULSE_PHASE="$TASK"

HELP_FILE=".harness/help/$HARNESS_SESSION.json"
LOG=".harness/runs/$HARNESS_SESSION.log"

if [ ! -x "$DSH_BIN" ]; then
  echo "run-qwen: pinned dsh missing at $DSH_BIN" >&2
  echo "run-qwen: install it with: (cd $HARNESS/adapters/dsh/runtime && npm ci)" >&2
  exit 2
fi
if [ ! -f "briefs/$TASK.md" ] && [ -z "${HARNESS_TASK_PROMPT-}" ]; then
  echo "run-qwen: no brief at briefs/$TASK.md — the orchestrator authors it before dispatch" >&2
  exit 2
fi

TASK_PROMPT="Read briefs/QWEN.md first — it is your rulebook. If PROGRESS.md exists, read it next — it is your memory. Then read briefs/$TASK.md and do ONLY that task. Follow its gate. Stop honestly."
# Probe seam: an orchestrator can drive a one-off prompt without authoring a brief file.
if [ -n "${HARNESS_TASK_PROMPT-}" ]; then TASK_PROMPT="$HARNESS_TASK_PROMPT"; fi
NUDGE_PROMPT="Read briefs/QWEN.md and briefs/$TASK.md. You were restarted. FIRST write PROGRESS.md with these three headings: ## Facts learned / ## Done / ## Next smallest step. THEN take that next smallest step — write the file, run the gate, or say BLOCKED. /no_think"
if [ "$THINK" = think=off ]; then TASK_PROMPT="$TASK_PROMPT /no_think"; fi

RUN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/run-qwen.XXXXXX") || exit 2
PID_FILE="$RUN_DIR/dsh.pid"
RC_FILE="$RUN_DIR/dsh.rc"
PULSE_PID=
PIPELINE_PID=
NUDGES=$RESUMED_NUDGES
# rc.7 headless cannot restore a session (adapters/dsh/README.md); every continuation is a restart.
RESUME_MODE=restart

cleanup() {
  if [ -n "$PULSE_PID" ]; then kill "$PULSE_PID" 2>/dev/null || :; fi
  rm -rf "$RUN_DIR" 2>/dev/null || :
}
trap cleanup EXIT INT TERM

START_EPOCH=$(date +%s)
if [ "$MODE" != fresh ]; then
  # The clock restarts where it paused, however long the interruption lasted.
  START_EPOCH=$(/bin/bash "$RUN_STATE" resume-epoch "$STATE_FILE") || START_EPOCH=$(date +%s)
  now=$(date +%s)
  if [ "$PAUSED_AT" -gt 0 ]; then PAUSED_S=$((now - PAUSED_AT)); fi
  if [ "$PAUSED_S" -lt 0 ]; then PAUSED_S=0; fi
fi

if [ "$MODE" = answer ]; then
  # Retire the answered question so a fresh one is what gets detected next.
  if [ -f "$HELP_FILE" ]; then
    mkdir -p .harness/help/answered 2>/dev/null || :
    mv "$HELP_FILE" ".harness/help/answered/$HARNESS_SESSION-$(date +%s).json" 2>/dev/null || rm -f "$HELP_FILE"
  fi
  TASK_PROMPT="You asked for help and here is the answer: $ANSWER\n\nIf PROGRESS.md exists, read it first — it is your memory.

$TASK_PROMPT"
  if [ -f "$LOGGER" ]; then
    /bin/bash "$LOGGER" help "run-qwen.sh $TASK" 0 "$PAUSED_S" \
      "kind=answered mode=fresh_session paused_s=$PAUSED_S" > /dev/null 2>&1 || :
  fi
elif [ "$MODE" = paused ]; then
  TASK_PROMPT="Read briefs/QWEN.md and briefs/$TASK.md. If PROGRESS.md exists, read it first — it is your memory. You were paused for power. Run the gate; whatever is red is your next step. Continue task $TASK."
  if [ "$THINK" = think=off ]; then TASK_PROMPT="$TASK_PROMPT /no_think"; fi
  if [ -f "$LOGGER" ]; then
    /bin/bash "$LOGGER" pause "run-qwen.sh $TASK" 0 "$PAUSED_S" \
      "kind=resumed mode=fresh_session paused_s=$PAUSED_S" > /dev/null 2>&1 || :
  fi
else
  : > "$LOG"
fi
ACTIVITY_FLOOR=$START_EPOCH

spent=$(( $(date +%s) - START_EPOCH ))
echo "run-qwen: task=$TASK session=$HARNESS_SESSION model=$HARNESS_MODEL $THINK patch=$(basename "$PATCH")"
echo "run-qwen: log=$REPO/$LOG budget=${BUDGET_S}s (spent ${spent}s) nudge_idle=${NUDGE_IDLE_S}s max_nudges=$MAX_NUDGES"
if [ "$MODE" != fresh ]; then
  echo "run-qwen: resumed after ${PAUSED_S}s paused; that wait cost no budget"
fi
if [ ! -f "$RUN_STATE" ]; then
  echo "run-qwen: WARNING $RUN_STATE is missing — a help request will still exit 4, but the" >&2
  echo "run-qwen: WARNING paused budget cannot be recorded and --resume-with-answer will fail." >&2
fi

# Telemetry never gates: a missing pulse helper costs visibility, not the run.
if [ -f "$PULSE" ]; then
  # shellcheck disable=SC2086
  /bin/bash "$PULSE" 120 "$START_EPOCH" $ACTIVITY_PATHS > /dev/null 2>&1 &
  PULSE_PID=$!
fi


ENVELOPE="$HARNESS/telemetry/result-envelope.mjs"
FLAKE_FILTER="$HARNESS/telemetry/flake-filter.sh"
FLAKE_LEDGER=".harness/flaky.txt"
RESULT_FILE=".harness/results/$HARNESS_SESSION.json"
PROGRESS_FILE="PROGRESS.md"
GATE_EXIT=0
GATE_DURATION=0
GATE_FLAKE_RERUN=0
GATE_RAN=0

resolve_gate_command() {
  if [ -n "$GATE_CMD" ]; then printf '%s' "$GATE_CMD"; return 0; fi
  if [ "$GATE_TIER" = fast ]; then
    printf 'make integrate-gate-fast TASK=%s' "$TASK"
  else
    printf 'make integrate-gate'
  fi
}

# Best effort by design: a red we cannot attribute to named tests is never treated as a flake,
# because flake-filter refuses an empty list. pytest prints "FAILED tests/x.py::T::t - msg";
# node --test prints "not ok N - name".
extract_failing_tests() {
  sed -n -E \
    -e 's/^FAILED ([^ ]+).*/\1/p' \
    -e 's/^not ok [0-9]+ - (.*)$/\1/p' \
    "$1" 2>/dev/null | sort -u
}

session_help_count() {
  node -e '
    const fs = require("fs");
    try {
      let n = 0;
      for (const line of fs.readFileSync(process.argv[1], "utf8").split(/\r?\n/)) {
        if (!line.trim()) continue;
        try {
          const event = JSON.parse(line);
          if (event.session === process.argv[2] && event.kind === "help" && !/kind=answered/.test(event.note || "")) n += 1;
        } catch {}
      }
      process.stdout.write(String(n));
    } catch { process.stdout.write("0"); }
  ' .harness/telemetry.jsonl "$HARNESS_SESSION" 2>/dev/null
}

write_envelope() {
  envelope_class=$1
  if [ ! -f "$ENVELOPE" ]; then return 0; fi
  envelope_tier=$GATE_TIER
  if [ "$GATE_RAN" -eq 0 ]; then envelope_tier=none; fi
  touched=$(git status --porcelain 2>/dev/null | sed -E 's/^.{3}//' | tr '\n' ',')
  node "$ENVELOPE" --out "$RESULT_FILE" \
    "session=$HARNESS_SESSION" "task=$TASK" "agent=$HARNESS_AGENT" "model=$HARNESS_MODEL" \
    "exit_class=$envelope_class" "gate_tier=$envelope_tier" "gate_exit=$GATE_EXIT" \
    "gate_duration_s=$GATE_DURATION" "gate_flake_rerun=$GATE_FLAKE_RERUN" \
    "nudges=$NUDGES" "helps=$(session_help_count)" "resume_mode=$RESUME_MODE" \
    "files_touched=$touched" "handback_path=.harness/handback/$HARNESS_SESSION.md" \
    "started=$(date -u -r "$START_EPOCH" '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null)" \
    "ended=$(date -u '+%Y-%m-%dT%H:%M:%SZ')" > /dev/null 2>&1 || :
}

# dsh runs node children. Signalling only the top process leaves them holding the pipe open, so
# collect the whole tree before signalling anything.
descendants() {
  for child in $(pgrep -P "$1" 2>/dev/null); do
    echo "$child"
    descendants "$child"
  done
}

kill_dsh_tree() {
  dsh_pid=$(cat "$PID_FILE" 2>/dev/null) || dsh_pid=
  if [ -z "$dsh_pid" ]; then return 0; fi
  tree=$(printf '%s\n' "$dsh_pid"; descendants "$dsh_pid")
  for pid in $tree; do kill -TERM "$pid" 2>/dev/null || :; done
  waited=0
  while kill -0 "$dsh_pid" 2>/dev/null; do
    if [ "$waited" -ge 10 ]; then break; fi
    waited=$((waited + 1))
    sleep 1
  done
  for pid in $tree; do kill -KILL "$pid" 2>/dev/null || :; done
}

# Bounded: a grandchild that survives everything must not hold this script open.
wait_pipeline_quiet() {
  waited=0
  while kill -0 "$PIPELINE_PID" 2>/dev/null; do
    if [ "$waited" -ge 10 ]; then
      kill -TERM "$PIPELINE_PID" 2>/dev/null || :
      break
    fi
    waited=$((waited + 1))
    sleep 1
  done
}

idle_seconds() {
  # shellcheck disable=SC2086
  newest=$(find $ACTIVITY_PATHS -type f -not -path '*/node_modules/*' -not -name '*.pyc' -print0 2>/dev/null | xargs -0 stat -f '%m' 2>/dev/null | sort -rn | head -1)
  case "$newest" in '' | *[!0-9]*) newest=0 ;; esac
  if [ "$newest" -lt "$ACTIVITY_FLOOR" ]; then newest=$ACTIVITY_FLOOR; fi
  now=$(date +%s)
  delta=$((now - newest))
  if [ "$delta" -lt 0 ]; then delta=0; fi
  echo "$delta"
}

launch_dsh() {
  rm -f "$RC_FILE"
  ACTIVITY_FLOOR=$(date +%s)
  {
    "$DSH_BIN" --profile headless --patch "$PATCH" "$1" 2>&1 &
    echo $! > "$PID_FILE"
    wait $!
    echo $? > "$RC_FILE"
  } | tee -a "$LOG" &
  PIPELINE_PID=$!
}

nudge() {
  count=$1
  idle=$2
  echo "run-qwen: nudge $count — no writes under the activity paths for ${idle}s; restarting the step" >&2
  kill_dsh_tree
  wait_pipeline_quiet
  if [ -f "$LOGGER" ]; then
    /bin/bash "$LOGGER" nudge "run-qwen.sh $TASK" 0 "$idle" \
      "nudge=$count idle_s=$idle mode=fresh_session" > /dev/null 2>&1 || :
  fi
  launch_dsh "$NUDGE_PROMPT"
}

# The help kind, read out of the file the worker left. Never trusted to be well-formed.
help_kind() {
  node -e '
    const fs = require("fs");
    try {
      const value = JSON.parse(fs.readFileSync(process.argv[1], "utf8")).kind;
      const kinds = ["missing_package", "missing_info", "design_decision", "env_broken"];
      process.stdout.write(kinds.includes(value) ? value : "unknown");
    } catch { process.stdout.write("unparsable"); }
  ' "$HELP_FILE" 2>/dev/null || printf 'unparsable'
}

pause_for_help() {
  elapsed=$1
  kind=$(help_kind)
  echo "run-qwen: the worker asked for help (kind=$kind); pausing the budget clock" >&2
  kill_dsh_tree
  wait_pipeline_quiet
  if [ -n "$PULSE_PID" ]; then
    kill "$PULSE_PID" 2>/dev/null || :
    PULSE_PID=
  fi
  if [ -f "$LOGGER" ]; then
    /bin/bash "$LOGGER" help "run-qwen.sh $TASK" 0 "$elapsed" "kind=$kind" > /dev/null 2>&1 || :
  fi
  if [ -f "$RUN_STATE" ]; then
    /bin/bash "$RUN_STATE" save "$STATE_FILE" \
      "task=$TASK" "think=$THINK" "elapsed_s=$elapsed" "nudges=$NUDGES" "paused_at=$(date +%s)" || :
  else
    echo "run-qwen: run-state.sh missing — the paused budget was not recorded" >&2
  fi
  echo "run-qwen: question is in $REPO/$HELP_FILE"
  echo "run-qwen: answer it with: ./run-qwen.sh --resume-with-answer $HARNESS_SESSION \"<answer>\""
  write_envelope help
  echo "run-qwen: budget paused at ${elapsed}s of ${BUDGET_S}s"
  exit 4
}

# The charge level, but only while actually running on battery.
battery_percent() {
  command -v pmset > /dev/null 2>&1 || return 1
  reading=$(pmset -g batt 2>/dev/null) || return 1
  case "$reading" in *"'Battery Power'"*) ;; *) return 1 ;; esac
  percent=$(printf '%s' "$reading" | grep -o '[0-9][0-9]*%' | head -1 | tr -d '%')
  case "$percent" in '' | *[!0-9]*) return 1 ;; esac
  printf '%s' "$percent"
}

wind_down_for_battery() {
  percent=$1
  echo "run-qwen: battery at ${percent}%, below the ${BATTERY_MIN}% reserve; winding down" >&2

  # Let the worker reach a quiet spot so a pause never lands mid-write. Past the ceiling, stop anyway.
  quiet_waited=0
  while [ "$quiet_waited" -lt "$QUIET_MAX_S" ]; do
    if [ "$(idle_seconds)" -ge "$QUIET_S" ]; then break; fi
    sleep 5
    quiet_waited=$((quiet_waited + 5))
  done

  now=$(date +%s)
  elapsed=$((now - START_EPOCH))
  kill_dsh_tree
  wait_pipeline_quiet
  if [ -n "$PULSE_PID" ]; then
    kill "$PULSE_PID" 2>/dev/null || :
    PULSE_PID=
  fi
  if [ -f "$RUN_STATE" ]; then
    /bin/bash "$RUN_STATE" save "$STATE_FILE" \
      "task=$TASK" "think=$THINK" "elapsed_s=$elapsed" "nudges=$NUDGES" "paused_at=$now" || :
  else
    echo "run-qwen: run-state.sh missing — the paused budget was not recorded" >&2
  fi
  if [ -f "$LOGGER" ]; then
    /bin/bash "$LOGGER" pause "run-qwen.sh $TASK" 0 "$elapsed" \
      "battery_low=$percent threshold=$BATTERY_MIN" > /dev/null 2>&1 || :
  fi
  echo "run-qwen: paused at ${elapsed}s of ${BUDGET_S}s after waiting ${quiet_waited}s for a quiet spot"
  write_envelope paused
  echo "run-qwen: plug in, then: ./run-qwen.sh --resume-paused $HARNESS_SESSION"
  exit 6
}

stop_on_budget() {
  elapsed=$1
  echo "run-qwen: wall-clock budget of ${BUDGET_S}s exceeded at ${elapsed}s; stopping dsh" >&2
  kill_dsh_tree
  if [ -n "$PULSE_PID" ]; then
    kill "$PULSE_PID" 2>/dev/null || :
    PULSE_PID=
  fi
  if [ -f "$LOGGER" ]; then
    /bin/bash "$LOGGER" budget "run-qwen.sh $TASK" 1 "$elapsed" \
      "wall_clock_budget_exceeded=$BUDGET_S nudges=$NUDGES" > /dev/null 2>&1 || :
  fi
  wait_pipeline_quiet
  write_envelope budget
  echo "run-qwen: stopped on budget after ${elapsed}s (nudges used: $NUDGES)"
  exit 3
}

launch_dsh "$TASK_PROMPT"

while :; do
  now=$(date +%s)
  elapsed=$((now - START_EPOCH))

  # First, always: a question on disk outlives whatever else is true.
  if [ -f "$HELP_FILE" ]; then pause_for_help "$elapsed"; fi
  if [ -f "$RC_FILE" ]; then break; fi
  if ! kill -0 "$PIPELINE_PID" 2>/dev/null; then break; fi

  if [ "$elapsed" -ge "$BUDGET_S" ]; then stop_on_budget "$elapsed"; fi

  # Budget outranks the battery: a run that is over ends rather than becoming resumable.
  if [ "$BATTERY_MIN" -gt 0 ]; then
    if charge=$(battery_percent); then
      if [ "$charge" -lt "$BATTERY_MIN" ]; then wind_down_for_battery "$charge"; fi
    fi
  fi

  idle=$(idle_seconds)
  nudge_threshold=$NUDGE_IDLE_S
  if [ "$NUDGES" -eq 0 ]; then nudge_threshold=$FIRST_NUDGE_S; fi
  if [ "$idle" -ge "$nudge_threshold" ] && [ "$NUDGES" -lt "$MAX_NUDGES" ]; then
    NUDGES=$((NUDGES + 1))
    nudge "$NUDGES" "$idle"
    continue
  fi

  sleep 5
done

wait_pipeline_quiet

# The worker may have written its question and exited before the loop looked again.
if [ -f "$HELP_FILE" ]; then pause_for_help "$(( $(date +%s) - START_EPOCH ))"; fi

status=$(cat "$RC_FILE" 2>/dev/null) || status=
case "$status" in '' | *[!0-9]*) status=1 ;; esac

echo "run-qwen: dsh exited $status (nudges used: $NUDGES)"

# THE GATE RUNS HERE TOO, OUTSIDE DSH. qwen runs the same gate inside the sandbox during the task;
# the runner re-verifies once the model has stopped, logs the event under the session's dsh/qwen
# identity (it is qwen's work being judged), and this time is outside the model's budget.
if [ "$status" -eq 0 ] && [ "$RUN_GATE" = 1 ]; then
  if [ -f Makefile ] && grep -q '^integrate-gate' Makefile 2>/dev/null; then
    gate_command=$(resolve_gate_command)
    echo "run-qwen: running '$gate_command' (tier=$GATE_TIER) outside the sandbox to verify the work"
    GATE_RAN=1
    gate_started=$(date +%s)
    gate_log="$RUN_DIR/gate.log"
    $gate_command > "$gate_log" 2>&1
    GATE_EXIT=$?
    cat "$gate_log" >> "$LOG"

    # A red may be rerun exactly once, and only when every failing test is a known flake.
    if [ "$GATE_EXIT" -ne 0 ]; then
      if extract_failing_tests "$gate_log" | /bin/bash "$FLAKE_FILTER" "$FLAKE_LEDGER"; then
        echo "run-qwen: all failures are known flakes — rerunning the gate once, fresh"
        GATE_FLAKE_RERUN=1
        $gate_command > "$gate_log" 2>&1
        GATE_EXIT=$?
        cat "$gate_log" >> "$LOG"
      fi
    fi

    GATE_DURATION=$(( $(date +%s) - gate_started ))
    if [ -f "$LOGGER" ]; then
      /bin/bash "$LOGGER" gate "$gate_command" "$GATE_EXIT" "$GATE_DURATION" \
        "verified_outside_sandbox=1 tier=$GATE_TIER flake_rerun=$GATE_FLAKE_RERUN" > /dev/null 2>&1 || :
    fi
    echo "run-qwen: gate exited $GATE_EXIT after ${GATE_DURATION}s (full output appended to $LOG)"

    if [ "$GATE_EXIT" -ne 0 ]; then
      if [ -f "$PROGRESS_FILE" ]; then echo "run-qwen: kept $PROGRESS_FILE (gate red)"; fi
      write_envelope error
      echo "run-qwen: qwen stopped cleanly but THE GATE IS RED" >&2
      exit "$GATE_EXIT"
    fi

    # Green: this task's story is finished, and stale progress must not leak into the next one.
    if [ -f "$PROGRESS_FILE" ]; then
      rm -f "$PROGRESS_FILE"
      echo "run-qwen: gate green — cleared $PROGRESS_FILE"
    fi
  else
    echo "run-qwen: no integrate-gate target here; skipping the post-run gate" >&2
  fi
fi

if [ "$status" -eq 0 ]; then write_envelope completed; else write_envelope error; fi

exit "$status"
