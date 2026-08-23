#!/bin/bash
# P0-D8 — shipped step 1: src/services/video_identity.py — import sqlalchemy.update; replace complete_job_with_artifacts with the fenced version. Run: bash briefs/assets/P0-D8/step-1.sh
F=academy-watch-backend/src/services/video_identity.py
grep -q '^from sqlalchemy import update$' "$F" && { echo "STEP1-BLOCKED (import already present)"; exit 1; }
L=$(grep -n '^from src.models.league import db$' "$F" | cut -d: -f1); [ -n "$L" ] || { echo "STEP1-BLOCKED (league import anchor not found)"; exit 1; }
sed -i '' "${L}i\\
from sqlalchemy import update
" "$F" && echo IMPORT-INSERTED
C=$(grep -n '^def complete_job_with_artifacts(job_id: str, artifacts: dict, gpu_seconds: float | None = None) -> dict:$' "$F" | cut -d: -f1); E=$(awk -v s="$C" 'NR>s && /^    return result$/ {print NR; exit}' "$F"); echo "C=$C E=$E"
[ -n "$C" ] && [ -n "$E" ] && [ "$E" -eq "$((C+19))" ] || { echo "STEP1-BLOCKED (complete_job_with_artifacts shape unexpected: C=$C E=$E)"; exit 1; }
sed -i '' "${C},${E}d" "$F" && sed -i '' "$((C-1))r briefs/assets/P0-D8/complete_job.py" "$F" && echo COMPLETE-REPLACED
