#!/bin/bash
# P0-D6 — shipped step 1: src/services/video_queue.py — add JobFenced; heartbeat becomes conditional and returns bool. Run: bash briefs/assets/P0-D6/step-1.sh
F=academy-watch-backend/src/services/video_queue.py
grep -q '^class JobFenced' "$F" && { echo "STEP1-BLOCKED (JobFenced already present)"; exit 1; }
C=$(grep -n '^STALE_RUNNING_HOURS = 6' "$F" | cut -d: -f1); [ -n "$C" ] || { echo "STEP1-BLOCKED (STALE_RUNNING_HOURS anchor not found)"; exit 1; }
sed -i '' "${C}r briefs/assets/P0-D6/job_fenced_class.py" "$F" && echo CLASS-INSERTED
H=$(grep -n '^def heartbeat(job_id: str, stage: str | None = None, progress: int | None = None) -> None:$' "$F" | cut -d: -f1); E=$(awk -v s="$H" 'NR>s && /^    db.session.commit\(\)$/ {print NR; exit}' "$F"); echo "H=$H E=$E"
[ -n "$H" ] && [ -n "$E" ] && [ "$E" -eq "$((H+7))" ] || { echo "STEP1-BLOCKED (heartbeat shape unexpected: H=$H E=$E)"; exit 1; }
sed -i '' "${H},${E}d" "$F" && sed -i '' "$((H-1))r briefs/assets/P0-D6/heartbeat.py" "$F" && echo HEARTBEAT-REPLACED
