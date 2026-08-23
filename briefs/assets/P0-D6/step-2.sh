#!/bin/bash
# P0-D6 — shipped step 2: src/services/video_identity.py — completion refuses a job that is no longer running. Run: bash briefs/assets/P0-D6/step-2.sh
F=academy-watch-backend/src/services/video_identity.py
G=$(grep -n '^        raise ValueError(f"job {job_id} not found")$' "$F" | cut -d: -f1); echo "G=$G"
[ -n "$G" ] && [ "$(grep -c '^        raise ValueError(f"job {job_id} not found")$' "$F")" -eq 1 ] || { echo "STEP2-BLOCKED (not-found anchor not unique)"; exit 1; }
sed -i '' "${G}r briefs/assets/P0-D6/complete_guard.py" "$F" && echo COMPLETE-GUARDED
