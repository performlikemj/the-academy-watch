#!/bin/bash
# P0-D1b — shipped step 3 (run from the worktree root: bash briefs/assets/P0-D1b/step-3.sh)
DL=$(grep -n 'Raw-footage retention expiry joins this job in a$' academy-watch-backend/src/jobs/run_video_maintenance.py | cut -d: -f1); echo "DL=$DL"; sed -i '' "${DL},$((DL+1))d" academy-watch-backend/src/jobs/run_video_maintenance.py && sed -i '' "$((DL-1))r briefs/assets/P0-D1b/docstring_lines.py" academy-watch-backend/src/jobs/run_video_maintenance.py && echo DOCSTRING-REPLACED
