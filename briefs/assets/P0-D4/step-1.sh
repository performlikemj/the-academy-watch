#!/bin/bash
# P0-D4 — shipped step 1: src/services/video_queue.py — import VideoMatch and replace reap_stale_jobs (19 lines). Run: bash briefs/assets/P0-D4/step-1.sh
F=academy-watch-backend/src/services/video_queue.py
grep -q '^from src.models.video import VideoAnalysisJob$' "$F" || { echo "STEP1-BLOCKED (import anchor not found)"; exit 1; }
sed -i '' 's#^from src.models.video import VideoAnalysisJob$#from src.models.video import VideoAnalysisJob, VideoMatch#' "$F" && echo IMPORT-UPDATED
R=$(grep -n '^def reap_stale_jobs() -> int:$' "$F" | cut -d: -f1); E=$(awk -v s="$R" 'NR>s && /^    return int\(stale\)$/ {print NR; exit}' "$F"); echo "R=$R E=$E"
[ -n "$R" ] && [ -n "$E" ] && [ "$E" -eq "$((R+18))" ] || { echo "STEP1-BLOCKED (reap_stale_jobs shape unexpected: R=$R E=$E)"; exit 1; }
sed -i '' "${R},${E}d" "$F" && sed -i '' "$((R-1))r briefs/assets/P0-D4/reap_stale_jobs.py" "$F" && echo REAP-REPLACED
