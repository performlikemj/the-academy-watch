#!/bin/bash
# P0-D5 — shipped step 1: src/services/video_queue.py — import sqlalchemy.update; replace reap_stale_jobs with the compare-and-swap version. Run: bash briefs/assets/P0-D5/step-1.sh
F=academy-watch-backend/src/services/video_queue.py
grep -q '^from sqlalchemy import update$' "$F" && { echo "STEP1-BLOCKED (import already present)"; exit 1; }
L=$(grep -n '^from src.models.league import db$' "$F" | cut -d: -f1); [ -n "$L" ] || { echo "STEP1-BLOCKED (league import anchor not found)"; exit 1; }
sed -i '' "${L}i\\
from sqlalchemy import update
" "$F" && echo IMPORT-INSERTED
R=$(grep -n '^def reap_stale_jobs() -> int:$' "$F" | cut -d: -f1); E=$(awk -v s="$R" 'NR>s && /^    return len\(stale_jobs\)$/ {print NR; exit}' "$F"); echo "R=$R E=$E"
[ -n "$R" ] && [ -n "$E" ] && [ "$E" -eq "$((R+25))" ] || { echo "STEP1-BLOCKED (reap_stale_jobs shape unexpected: R=$R E=$E)"; exit 1; }
sed -i '' "${R},${E}d" "$F" && sed -i '' "$((R-1))r briefs/assets/P0-D5/reap_stale_jobs.py" "$F" && echo REAP-REPLACED
