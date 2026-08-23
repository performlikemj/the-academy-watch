#!/bin/bash
# P0-D6 — shipped step 3: upload-complete (admin + club) take the retention row lock after loading the match. Run: bash briefs/assets/P0-D6/step-3.sh
F=academy-watch-backend/src/routes/video.py
D=$(grep -n '^    job-start content-swap check, optionally capture timeline markers."""$' "$F" | cut -d: -f1); echo "D=$D"
[ -n "$D" ] && [ "$(sed -n "$((D+3))p" "$F")" = '        return jsonify({"error": "match not found"}), 404' ] || { echo "STEP3-BLOCKED (admin upload_complete shape unexpected)"; exit 1; }
sed -i '' "$((D+3))r briefs/assets/P0-D6/lock_refresh.py" "$F" && echo ADMIN-UPLOAD-LOCKED
G=academy-watch-backend/src/routes/club.py
K=$(grep -n '^def club_match_upload_complete(program_id: int, match_id: int):$' "$G" | cut -d: -f1); echo "K=$K"
[ -n "$K" ] && [ "$(sed -n "$((K+3))p" "$G")" = '        return jsonify({"error": "Match not found"}), 404' ] || { echo "STEP3-BLOCKED (club upload_complete shape unexpected)"; exit 1; }
sed -i '' "$((K+3))r briefs/assets/P0-D6/lock_refresh.py" "$G" && echo CLUB-UPLOAD-LOCKED
