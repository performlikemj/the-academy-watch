#!/bin/bash
# P0-D2 — shipped step 3 (run from the worktree root: bash briefs/assets/P0-D2/step-3.sh)
RL=$(grep -n '^        return redirect(video_storage.mint_read_sas(match.blob_path))$' academy-watch-backend/src/routes/video.py | cut -d: -f1); echo "RL=$RL"; sed -i '' "${RL}d" academy-watch-backend/src/routes/video.py && sed -i '' "$((RL-1))r briefs/assets/P0-D2/redirect_block.py" academy-watch-backend/src/routes/video.py && echo REDIRECT-REPLACED
