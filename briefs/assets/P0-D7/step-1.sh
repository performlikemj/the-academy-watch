#!/bin/bash
# P0-D7 — shipped step 1: src/services/video_queue.py — import and_/exists; replace reap_stale_jobs with the queued-aware version + fail_running_job CAS. Run: bash briefs/assets/P0-D7/step-1.sh
F=academy-watch-backend/src/services/video_queue.py
grep -q '^from sqlalchemy import update$' "$F" || { echo "STEP1-BLOCKED (sqlalchemy import anchor not found)"; exit 1; }
sed -i '' 's#^from sqlalchemy import update$#from sqlalchemy import and_, exists, update#' "$F" && echo IMPORT-UPDATED
R=$(grep -n '^def reap_stale_jobs() -> int:$' "$F" | cut -d: -f1); E=$(awk -v s="$R" 'NR>s && /^    return len\(reaped\)$/ {print NR; exit}' "$F"); echo "R=$R E=$E"
[ -n "$R" ] && [ -n "$E" ] && [ "$E" -eq "$((R+26))" ] || { echo "STEP1-BLOCKED (reap_stale_jobs shape unexpected: R=$R E=$E)"; exit 1; }
sed -i '' "${R},${E}d" "$F" && sed -i '' "$((R-1))r briefs/assets/P0-D7/reap_and_fail.py" "$F" && echo REAP-AND-FAIL-REPLACED
grep -c '^def fail_running_job' "$F" | sed 's/^/fail_running_job defs (expect 1): /'
