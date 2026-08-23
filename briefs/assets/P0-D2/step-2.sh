#!/bin/bash
# P0-D2 — shipped step 2 (run from the worktree root: bash briefs/assets/P0-D2/step-2.sh)
VU=$(grep -n '^def verify_uploaded_blob' academy-watch-backend/src/services/video_storage.py | cut -d: -f1); echo "VU=$VU; line VU-3 is: [$(sed -n "$((VU-3))p" academy-watch-backend/src/services/video_storage.py)]"; sed -i '' "$((VU-3))r briefs/assets/P0-D2/mint_media_read_sas.py" academy-watch-backend/src/services/video_storage.py && echo FUNCTION-INSERTED
