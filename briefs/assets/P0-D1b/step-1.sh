#!/bin/bash
# P0-D1b — shipped step 1 (run from the worktree root: bash briefs/assets/P0-D1b/step-1.sh)
SI=$(grep -n '^from src.services import video_queue$' academy-watch-backend/src/jobs/run_video_maintenance.py | cut -d: -f1); echo "SI=$SI"; sed -i '' "${SI}d" academy-watch-backend/src/jobs/run_video_maintenance.py && sed -i '' "$((SI-1))r briefs/assets/P0-D1b/services_import.py" academy-watch-backend/src/jobs/run_video_maintenance.py && echo IMPORT-REPLACED
