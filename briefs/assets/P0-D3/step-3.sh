#!/bin/bash
# P0-D3 — shipped step 3: src/routes/video.py — import the helper; the footage redirect mints a SAS capped at the token's remaining life. Run: bash briefs/assets/P0-D3/step-3.sh
F=academy-watch-backend/src/routes/video.py
grep -q '^from src.auth import mint_media_token, verify_media_token$' "$F" || { echo "STEP3-BLOCKED (import anchor not found)"; exit 1; }
sed -i '' 's#^from src.auth import mint_media_token, verify_media_token$#from src.auth import media_token_remaining_seconds, mint_media_token, verify_media_token#' "$F" && echo IMPORT-UPDATED
RL=$(grep -n '^        resp = redirect(video_storage.mint_media_read_sas(match.blob_path))$' "$F" | cut -d: -f1); echo "RL=$RL"
[ -n "$RL" ] || { echo "STEP3-BLOCKED (redirect line not found)"; exit 1; }
sed -i '' "${RL}d" "$F" && sed -i '' "$((RL-1))r briefs/assets/P0-D3/route_block.py" "$F" && echo ROUTE-UPDATED
