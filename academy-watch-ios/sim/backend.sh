#!/bin/bash

set -u

SIM_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
IOS_DIR=$(CDPATH= cd -- "$SIM_DIR/.." && pwd)
REPO_DIR=$(CDPATH= cd -- "$IOS_DIR/.." && pwd)
BACKEND_DIR="$REPO_DIR/academy-watch-backend"
RUN_DIR="$SIM_DIR/.run"
PID_FILE="$RUN_DIR/backend.pid"
LOG_FILE="$RUN_DIR/backend.log"
DEFAULT_ENV_FILE="$BACKEND_DIR/.env"
PRIMARY_ENV_FILE="$HOME/Projects/loanarmy/academy-watch-backend/.env"
if [ -n "${SIM_BACKEND_ENV_FILE-}" ]; then
  ENV_FILE=$SIM_BACKEND_ENV_FILE
elif [ -f "$DEFAULT_ENV_FILE" ]; then
  ENV_FILE=$DEFAULT_ENV_FILE
else
  ENV_FILE=$PRIMARY_ENV_FILE
fi
PYTHON=${SIM_PYTHON:-/Users/michaeljones/Projects/loanarmy/.loan/bin/python}
PORT=${SIM_BACKEND_PORT:-5001}

usage() {
  echo "Usage: backend.sh start|stop|status" >&2
}

valid_pid() {
  [ -f "$PID_FILE" ] || return 1
  pid=$(sed -n '1p' "$PID_FILE")
  case "$pid" in ''|*[!0-9]*) return 1 ;; esac
  kill -0 "$pid" 2>/dev/null || return 1
  command=$(ps -p "$pid" -o command= 2>/dev/null || true)
  printf '%s\n' "$command" | grep -q -- "-m flask --app src.main run --host 127.0.0.1 --port"
}

status_backend() {
  if valid_pid; then echo running; else echo stopped; fi
}

start_backend() {
  case "$PORT" in ''|*[!0-9]*) echo "backend.sh: SIM_BACKEND_PORT must be numeric" >&2; exit 2 ;; esac
  if [ "$PORT" -lt 1 ] || [ "$PORT" -gt 65535 ]; then
    echo "backend.sh: SIM_BACKEND_PORT must be between 1 and 65535" >&2
    exit 2
  fi
  if valid_pid; then echo "backend.sh: already running" >&2; exit 1; fi
  mkdir -p "$RUN_DIR" || exit 2
  if [ -f "$PID_FILE" ]; then rm -f "$PID_FILE"; fi
  if lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "backend.sh: refusing to start because port $PORT is busy" >&2
    exit 1
  fi
  if [ ! -x "$PYTHON" ]; then
    echo "backend.sh: Python is unavailable at the configured SIM_PYTHON path" >&2
    exit 1
  fi
  echo "backend env: $ENV_FILE"
  if [ ! -f "$ENV_FILE" ]; then
    echo "backend.sh: configured backend .env is missing: $ENV_FILE" >&2
    exit 1
  fi

  (
    set -a
    # shellcheck disable=SC1090
    . "$ENV_FILE"
    set +a
    export API_USE_STUB_DATA=true
    export SKIP_API_HANDSHAKE=1
    export FLASK_DEBUG=false
    cd "$BACKEND_DIR" || exit 2
    exec "$PYTHON" -c 'import os, sys; os.setsid(); os.execv(sys.argv[1], sys.argv[1:])' \
      "$PYTHON" -m flask --app src.main run --host 127.0.0.1 --port "$PORT" --no-debugger --no-reload
  ) >"$LOG_FILE" 2>&1 < /dev/null &
  pid=$!
  printf '%s\n%s\n' "$pid" "$PORT" > "$PID_FILE"

  deadline=$((SECONDS + 60))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$PID_FILE"
      echo "backend.sh: backend exited before health became ready (see sim/.run/backend.log)" >&2
      exit 1
    fi
    if curl -fsS --max-time 3 "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; then
      echo "backend health: http://127.0.0.1:$PORT/api/health ok"
      return
    fi
    sleep 1
  done

  /bin/kill -TERM -"$pid" 2>/dev/null || true
  rm -f "$PID_FILE"
  echo "backend.sh: timed out waiting for /api/health after 60 seconds" >&2
  exit 1
}

stop_backend() {
  if ! valid_pid; then
    if [ -f "$PID_FILE" ]; then rm -f "$PID_FILE"; fi
    echo stopped
    return
  fi
  pid=$(sed -n '1p' "$PID_FILE")
  /bin/kill -TERM -"$pid" 2>/dev/null || true
  deadline=$((SECONDS + 10))
  while kill -0 "$pid" 2>/dev/null && [ "$SECONDS" -lt "$deadline" ]; do sleep 1; done
  if kill -0 "$pid" 2>/dev/null; then /bin/kill -KILL -"$pid" 2>/dev/null || true; fi
  rm -f "$PID_FILE"
  echo stopped
}

if [ "$#" -ne 1 ]; then usage; exit 2; fi
case "$1" in
  start) start_backend ;;
  stop) stop_backend ;;
  status) status_backend ;;
  *) usage; exit 2 ;;
esac
