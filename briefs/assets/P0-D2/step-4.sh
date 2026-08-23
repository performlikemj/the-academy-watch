#!/bin/bash
# P0-D2 — shipped step 4 (run from the worktree root: bash briefs/assets/P0-D2/step-4.sh)
grep -n "^MEDIA_READ_SAS_MINUTES\|^def mint_read_sas\|^def mint_media_read_sas\|^def verify_uploaded_blob" academy-watch-backend/src/services/video_storage.py; grep -c "mint_media_read_sas" academy-watch-backend/src/routes/video.py
