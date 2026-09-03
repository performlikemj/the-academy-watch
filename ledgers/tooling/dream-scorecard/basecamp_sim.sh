#!/bin/zsh
# Usage: basecamp_sim.sh <git-ref-on-origin e.g. fix/s0-player-claim-door | main>
# Runs the loanarmy web sim (SIM_GRADE=0, deterministic) on basecamp in a separate worktree.
set -e
REF="$1"; [ -z "$REF" ] && { echo "ref required"; exit 2; }
ssh-add --apple-load-keychain >/dev/null 2>&1 || true
ssh -o BatchMode=yes mjjones@100.82.160.117 REF="$REF" 'bash -s' <<'REMOTE'
set -e
export PATH="$HOME/homebrew/bin:$HOME/homebrew/opt/postgresql@16/bin:$PATH"
if pgrep -f "sim/run.mjs" >/dev/null; then echo "ANOTHER SIM IS RUNNING — abort"; exit 3; fi
if pgrep -f "qwen_match_analysis" >/dev/null; then echo "note: a loanarmy regen is active on basecamp — running UNGRADED only (SIM_GRADE=0), no ollama calls"; fi
if ss -ltn 2>/dev/null | grep -qE ':5001 |:5173 ' || lsof -iTCP:5001 -sTCP:LISTEN -t >/dev/null 2>&1 || lsof -iTCP:5173 -sTCP:LISTEN -t >/dev/null 2>&1; then echo "PORTS 5001/5173 BUSY ON BASECAMP — abort"; exit 4; fi
MAIN=~/Projects/loanarmy; WT=~/Projects/loanarmy-sim
cd $MAIN && git fetch -q origin "$REF" && SHA=$(git rev-parse FETCH_HEAD)
if [ -d $WT ]; then git -C $WT checkout -q --detach "$SHA"; else git worktree add -q --detach $WT "$SHA"; fi
echo "sim worktree at: $(git -C $WT log --oneline -1)"
ENV_FILE=$WT/academy-watch-backend/.env
SIMDB=
SIMDB_CREATED=0
ENV_REWRITTEN=0

cleanup_sim_db() {
  local status=$?
  local cleanup_status=0
  trap - EXIT HUP INT TERM
  set +e
  unset PGDATABASE PGSERVICE PGSERVICEFILE
  if [ "${SIMDB_CREATED:-0}" -eq 1 ]; then
    if [[ "$SIMDB" =~ ^sim_[0-9]{14}$ ]]; then
      psql -d postgres -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$SIMDB' AND pid <> pg_backend_pid()" >/dev/null 2>&1
      [ "$?" -eq 0 ] || cleanup_status=1
      dropdb --if-exists "$SIMDB" >/dev/null 2>&1
      [ "$?" -eq 0 ] || cleanup_status=1
    else
      cleanup_status=1
    fi
  fi
  if [ -n "${ENV_FILE:-}" ] && [ "${ENV_REWRITTEN:-0}" -ne 1 ]; then
    rm -f "$ENV_FILE" >/dev/null 2>&1
    [ "$?" -eq 0 ] || cleanup_status=1
  fi
  if [ "$cleanup_status" -ne 0 ]; then
    echo "THROWAWAY DB CLEANUP FAILED" >&2
    [ "$status" -ne 0 ] || status=8
  fi
  exit "$status"
}
trap cleanup_sim_db EXIT
trap 'exit 129' HUP
trap 'exit 130' INT
trap 'exit 143' TERM

cp $MAIN/academy-watch-backend/.env "$ENV_FILE"
TS=$(date +%Y%m%d%H%M%S)
SIMDB="sim_${TS}"
echo "throwaway db: $SIMDB"

read_env_value() {
  "$MAIN/.loan/bin/python" - "$ENV_FILE" "$1" <<'PY'
import sys

from dotenv import dotenv_values

value = dotenv_values(sys.argv[1]).get(sys.argv[2])
if value is None:
    raise SystemExit(1)
sys.stdout.write(value)
PY
}

unset PGHOST PGPORT PGUSER PGPASSWORD PGSSLMODE PGDATABASE PGSERVICE PGSERVICEFILE
DATABASE_URL_VALUE=$(read_env_value DATABASE_URL 2>/dev/null || true)
URL_MODE=0
if [ -n "$DATABASE_URL_VALUE" ]; then
  URL_MODE=1
  SIM_DATABASE_URL_INPUT=$DATABASE_URL_VALUE
  export SIM_DATABASE_URL_INPUT
  url_component() {
    "$MAIN/.loan/bin/python" - "$1" <<'PY'
import os
import sys
from urllib.parse import parse_qs, unquote, urlsplit

parsed = urlsplit(os.environ["SIM_DATABASE_URL_INPUT"])
if parsed.scheme.split("+", 1)[0] not in {"postgres", "postgresql"}:
    raise SystemExit(1)
query = parse_qs(parsed.query, keep_blank_values=True)
values = {
    "host": unquote(parsed.hostname) if parsed.hostname is not None else query.get("host", [""])[-1],
    "port": str(parsed.port or query.get("port", ["5432"])[-1]),
    "user": unquote(parsed.username) if parsed.username is not None else query.get("user", [""])[-1],
    "password": unquote(parsed.password) if parsed.password is not None else query.get("password", [""])[-1],
    "sslmode": query.get("sslmode", [""])[-1],
}
sys.stdout.write(values[sys.argv[1]])
PY
  }
  PGHOST=$(url_component host) || { echo "DATABASE_URL PARSE FAILED — abort"; exit 7; }
  PGPORT=$(url_component port) || { echo "DATABASE_URL PARSE FAILED — abort"; exit 7; }
  PGUSER=$(url_component user) || { echo "DATABASE_URL PARSE FAILED — abort"; exit 7; }
  PGPASSWORD=$(url_component password) || { echo "DATABASE_URL PARSE FAILED — abort"; exit 7; }
  PGSSLMODE=$(url_component sslmode) || { echo "DATABASE_URL PARSE FAILED — abort"; exit 7; }
  [ -n "$PGSSLMODE" ] || PGSSLMODE=prefer
  unset SIM_DATABASE_URL_INPUT
else
  PGHOST=$(read_env_value DB_HOST) || { echo "DB_HOST MISSING — abort"; exit 7; }
  PGPORT=$(read_env_value DB_PORT) || { echo "DB_PORT MISSING — abort"; exit 7; }
  PGUSER=$(read_env_value DB_USER) || { echo "DB_USER MISSING — abort"; exit 7; }
  PGPASSWORD=$(read_env_value DB_PASSWORD) || { echo "DB_PASSWORD MISSING — abort"; exit 7; }
  PGSSLMODE=$(read_env_value DB_SSLMODE 2>/dev/null || true)
fi
export PGHOST PGPORT PGUSER PGPASSWORD
if [ -n "$PGSSLMODE" ]; then export PGSSLMODE; else unset PGSSLMODE; fi

if CUTOFF_TS=$(date -v-1d +%Y%m%d%H%M%S 2>/dev/null); then
  :
else
  CUTOFF_TS=$(date -d '1 day ago' +%Y%m%d%H%M%S)
fi
if ! OLD_SIM_DBS=$(psql -d postgres -tA -c "SELECT datname FROM pg_database WHERE datname LIKE 'sim_%'"); then
  echo "STALE SIM DB DISCOVERY FAILED — abort" >&2
  exit 7
fi
while IFS= read -r OLDDB; do
  [[ "$OLDDB" =~ ^sim_[0-9]{14}$ ]] || continue
  OLDSTAMP=${OLDDB#sim_}
  [[ "$OLDSTAMP" < "$CUTOFF_TS" ]] || continue
  if ! psql -d postgres -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$OLDDB' AND pid <> pg_backend_pid()" >/dev/null; then
    echo "STALE SIM DB CONNECTION CLEANUP FAILED — abort" >&2
    exit 7
  fi
  if ! dropdb --if-exists "$OLDDB" >/dev/null; then
    echo "STALE SIM DB DROP FAILED — abort" >&2
    exit 7
  fi
done <<< "$OLD_SIM_DBS"

CREATE_RETRIES=0
while true; do
  SIMDB_CREATED=1
  if createdb -T soccer_newsletter "$SIMDB" >/tmp/sim-createdb.log 2>&1; then
    break
  fi
  SIMDB_CREATED=0
  if ! grep -q "being accessed by other users" /tmp/sim-createdb.log; then
    echo "THROWAWAY DB CREATE FAILED (see /tmp/sim-createdb.log) — abort" >&2
    exit 7
  fi
  if [ "$CREATE_RETRIES" -ge 5 ]; then
    echo "SHARED DB STILL BUSY AFTER 5 RETRIES — abort" >&2
    exit 7
  fi
  CREATE_RETRIES=$((CREATE_RETRIES + 1))
  echo "shared DB busy; retrying in 10s ($CREATE_RETRIES/5)"
  sleep 10
done

if ! "$MAIN/.loan/bin/python" - "$ENV_FILE" "$SIMDB" <<'PY'
import re
import sys
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

from dotenv import dotenv_values

path = Path(sys.argv[1])
simdb = sys.argv[2]
values = dotenv_values(path)
has_db_name = values.get("DB_NAME") is not None
database_url = values.get("DATABASE_URL")
if not has_db_name and not database_url:
    raise SystemExit(1)

if database_url:
    parsed = urlsplit(database_url)
    if parsed.scheme.split("+", 1)[0] not in {"postgres", "postgresql"}:
        raise SystemExit(1)
    query = [
        (key, simdb if key.lower() in {"database", "dbname"} else value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    database_url = urlunsplit(
        (parsed.scheme, parsed.netloc, "/" + quote(simdb, safe=""), urlencode(query), parsed.fragment)
    )

assignment = re.compile(r"^(\s*(?:export\s+)?)(DB_NAME|DATABASE_URL)\s*=.*$")
rewritten = []
for line in path.read_text(encoding="utf-8").splitlines(keepends=True):
    body = line.rstrip("\r\n")
    ending = line[len(body) :]
    match = assignment.match(body)
    if not match:
        rewritten.append(line)
    elif match.group(2) == "DB_NAME":
        rewritten.append(f"{match.group(1)}DB_NAME={simdb}{ending}")
    elif database_url:
        rewritten.append(f"{match.group(1)}DATABASE_URL={database_url}{ending}")
    else:
        rewritten.append(line)
path.write_text("".join(rewritten), encoding="utf-8")
PY
then
  echo "SIM DB ENV REWRITE FAILED — abort" >&2
  exit 7
fi
if grep -Fq 'soccer_newsletter' "$ENV_FILE"; then
  echo "SIM DB ENV REWRITE LEFT THE SHARED DB NAME — abort" >&2
  exit 7
fi
ENV_REWRITTEN=1

export DB_HOST="$PGHOST" DB_PORT="$PGPORT" DB_USER="$PGUSER" DB_PASSWORD="$PGPASSWORD" DB_NAME="$SIMDB"
export PGDATABASE="$SIMDB"
if [ -n "$PGSSLMODE" ]; then export DB_SSLMODE="$PGSSLMODE"; else unset DB_SSLMODE; fi
unset SQLALCHEMY_DATABASE_URI
if [ "$URL_MODE" -eq 1 ]; then
  DATABASE_URL=$(read_env_value DATABASE_URL) || { echo "DATABASE_URL RELOAD FAILED — abort"; exit 7; }
  export DATABASE_URL
else
  unset DATABASE_URL
fi
unset DATABASE_URL_VALUE

(cd $WT/academy-watch-backend && $MAIN/.loan/bin/flask --app src.main db upgrade > /tmp/sim-migrate.log 2>&1 && echo "db upgraded: $($MAIN/.loan/bin/flask --app src.main db heads 2>/dev/null | tail -1)") || { if grep -q "Can.t locate revision" /tmp/sim-migrate.log; then echo "db AHEAD of branch (extra columns are additive) — continuing"; else echo "MIGRATION FAILED"; tail -5 /tmp/sim-migrate.log; exit 6; fi; }
cd $WT && ./scripts/setup_frontend.sh > /tmp/sim-setup.log 2>&1 || { echo "setup_frontend FAILED"; tail -20 /tmp/sim-setup.log; exit 5; }
export SIM_ALLOW_DB_NAME="$SIMDB"
SIM_GRADE=0 SIM_PYTHON=$MAIN/.loan/bin/python node sim/run.mjs > /tmp/sim-run.log 2>&1 || echo "sim exit code $?"
LATEST=$(ls -td sim/report/*/ | head -1)
python3 - "$LATEST/report.json" <<'PY'
import json,sys
r=json.load(open(sys.argv[1])); tot=ok=0; fails=[]
for j in r.get("journeys",[]):
    for s in j.get("steps",[]):
        tot+=1
        if s.get("ok"): ok+=1
        else: fails.append(f"{j['name']}/{s['id']}: {s.get('note','')[:120]}")
print(f"SIM RESULT {ok}/{tot} ok  (report {sys.argv[1]})")
for f in fails: print("  FAIL", f)
PY
tail -3 /tmp/sim-run.log
REMOTE
