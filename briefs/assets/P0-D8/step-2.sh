#!/bin/bash
# P0-D8 — shipped step 2: the two re-mint SAS routes refuse a grant that would outlive the retention deadline. Run: bash briefs/assets/P0-D8/step-2.sh
F=academy-watch-backend/src/routes/video.py
grep -q '^from src.services import ' "$F" || { echo "STEP2-BLOCKED (video.py services import not found)"; exit 1; }
grep -q 'video_retention' "$F" || sed -i '' 's#^from src.services import video_dev_artifacts, video_queue, video_storage$#from src.services import video_dev_artifacts, video_queue, video_retention, video_storage#' "$F"
grep -q '^from src.services import video_dev_artifacts, video_queue, video_retention, video_storage$' "$F" || { echo "STEP2-BLOCKED (video.py services import not the expected line)"; exit 1; }
A1=$(grep -n '^    """Re-mint the write SAS — 6GB at club uplink speeds outlives 60 minutes."""$' "$F" | cut -d: -f1); echo "A1=$A1"
[ -n "$A1" ] && [ "$(sed -n "$((A1+6))p" "$F")" = '    if not video_storage.is_configured():' ] || { echo "STEP2-BLOCKED (remint_upload_sas shape unexpected: [$(sed -n "$((A1+6))p" "$F")])"; exit 1; }
sed -i '' "$((A1+5))r briefs/assets/P0-D8/grant_guard.py" "$F" && echo ADMIN-REMINT-GUARDED
G=academy-watch-backend/src/routes/club.py
grep -q '^from src.services import ' "$G" || { echo "STEP2-BLOCKED (club.py services import not found)"; exit 1; }
grep -q 'video_retention' "$G" || sed -i '' 's#^from src.services import video_storage$#from src.services import video_retention, video_storage#' "$G"
grep -q '^from src.services import video_retention, video_storage$' "$G" || { echo "STEP2-BLOCKED (club.py services import not the expected line)"; exit 1; }
K=$(grep -n '^def club_match_sas(program_id: int, match_id: int):$' "$G" | cut -d: -f1); echo "K=$K"
[ -n "$K" ] && [ "$(sed -n "$((K+5))p" "$G")" = '        return _bad_request(f"cannot re-mint SAS in status '"'"'{match.status}'"'"'")' ] || { echo "STEP2-BLOCKED (club_match_sas shape unexpected: [$(sed -n "$((K+5))p" "$G")])"; exit 1; }
sed -i '' "$((K+5))r briefs/assets/P0-D8/grant_guard.py" "$G" && echo CLUB-REMINT-GUARDED
grep -c "can_issue_upload_grant" "$F" "$G" | sed 's/^/guards: /'
