#!/bin/bash
# P0-D9 — shipped step 2: routes/club.py club_match_upload_complete — same two changes. Run: bash briefs/assets/P0-D9/step-2.sh
G=academy-watch-backend/src/routes/club.py
K=$(grep -n '^def club_match_upload_complete(program_id: int, match_id: int):$' "$G" | cut -d: -f1); echo "K=$K"
[ -n "$K" ] && [ "$(sed -n "$((K+7))p" "$G")" = '        return _bad_request(f"cannot complete upload in status '"'"'{match.status}'"'"'")' ] || { echo "STEP2-BLOCKED (club upload_complete shape unexpected: [$(sed -n "$((K+7))p" "$G")])"; exit 1; }
sed -i '' "$((K+7))r briefs/assets/P0-D9/window_guard.py" "$G" && echo CLUB-WINDOW-GUARDED
X=$(grep -n '^    match.expires_at = now + timedelta(days=RAW_RETENTION_DAYS)$' "$G" | cut -d: -f1); echo "X=$X"
[ -n "$X" ] && [ "$(grep -c '^    match.expires_at = now + timedelta(days=RAW_RETENTION_DAYS)$' "$G")" -eq 1 ] || { echo "STEP2-BLOCKED (expires_at line not unique)"; exit 1; }
sed -i '' "${X}d" "$G" && sed -i '' "$((X-1))r briefs/assets/P0-D9/expires_club.py" "$G" && echo CLUB-DEADLINE-PRESERVED
