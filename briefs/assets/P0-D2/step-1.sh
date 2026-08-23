#!/bin/bash
# P0-D2 — shipped step 1 (run from the worktree root: bash briefs/assets/P0-D2/step-1.sh)
RH=$(grep -n '^READ_SAS_HOURS = 6$' academy-watch-backend/src/services/video_storage.py | cut -d: -f1); echo "RH=$RH"; sed -i '' "${RH}r briefs/assets/P0-D2/media_sas_constant.py" academy-watch-backend/src/services/video_storage.py && echo CONSTANT-INSERTED
