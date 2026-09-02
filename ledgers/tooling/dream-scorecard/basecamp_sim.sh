#!/bin/zsh
# Usage: basecamp_sim.sh <git-ref-on-origin e.g. fix/s0-player-claim-door | main>
# Runs the loanarmy web sim (SIM_GRADE=0, deterministic) on basecamp in a separate worktree.
set -e
REF="$1"; [ -z "$REF" ] && { echo "ref required"; exit 2; }
ssh-add --apple-load-keychain >/dev/null 2>&1 || true
ssh -o BatchMode=yes mjjones@100.82.160.117 REF="$REF" 'bash -s' <<'REMOTE'
set -e
export PATH="$HOME/homebrew/bin:$HOME/homebrew/opt/postgresql@16/bin:$PATH"
MAIN=~/Projects/loanarmy; WT=~/Projects/loanarmy-sim
cd $MAIN && git fetch -q origin "$REF" && SHA=$(git rev-parse FETCH_HEAD)
if [ -d $WT ]; then git -C $WT checkout -q --detach "$SHA"; else git worktree add -q --detach $WT "$SHA"; fi
echo "sim worktree at: $(git -C $WT log --oneline -1)"
cp $MAIN/academy-watch-backend/.env $WT/academy-watch-backend/.env
if pgrep -f "sim/run.mjs" >/dev/null; then echo "ANOTHER SIM IS RUNNING — abort"; exit 3; fi
if pgrep -f "qwen_match_analysis" >/dev/null; then echo "note: a loanarmy regen is active on basecamp — running UNGRADED only (SIM_GRADE=0), no ollama calls"; fi
if ss -ltn 2>/dev/null | grep -qE ':5001 |:5173 ' || lsof -iTCP:5001 -sTCP:LISTEN -t >/dev/null 2>&1 || lsof -iTCP:5173 -sTCP:LISTEN -t >/dev/null 2>&1; then echo "PORTS 5001/5173 BUSY ON BASECAMP — abort"; exit 4; fi
(cd $WT/academy-watch-backend && $MAIN/.loan/bin/flask --app src.main db upgrade > /tmp/sim-migrate.log 2>&1 && echo "db upgraded: $($MAIN/.loan/bin/flask --app src.main db heads 2>/dev/null | tail -1)") || { if grep -q "Can.t locate revision" /tmp/sim-migrate.log; then echo "db AHEAD of branch (extra columns are additive) — continuing"; else echo "MIGRATION FAILED"; tail -5 /tmp/sim-migrate.log; exit 6; fi; }
cd $WT && ./scripts/setup_frontend.sh > /tmp/sim-setup.log 2>&1 || { echo "setup_frontend FAILED"; tail -20 /tmp/sim-setup.log; exit 5; }
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
