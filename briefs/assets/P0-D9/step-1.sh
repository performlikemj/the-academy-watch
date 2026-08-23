#!/bin/bash
# P0-D9 — shipped step 1: routes/video.py upload_complete — refuse a closed retention window; keep the original deadline on reattestation. Run: bash briefs/assets/P0-D9/step-1.sh
F=academy-watch-backend/src/routes/video.py
D=$(grep -n '^    job-start content-swap check, optionally capture timeline markers."""$' "$F" | cut -d: -f1); echo "D=$D"
[ -n "$D" ] && [ "$(sed -n "$((D+7))p" "$F")" = '        return _bad_request(f"cannot complete upload in status '"'"'{match.status}'"'"'")' ] || { echo "STEP1-BLOCKED (upload_complete shape unexpected: [$(sed -n "$((D+7))p" "$F")])"; exit 1; }
sed -i '' "$((D+7))r briefs/assets/P0-D9/window_guard.py" "$F" && echo ADMIN-WINDOW-GUARDED
X=$(grep -n '^    match.expires_at = datetime.now(UTC) + timedelta(days=RAW_RETENTION_DAYS)$' "$F" | cut -d: -f1); echo "X=$X"
[ -n "$X" ] && [ "$(grep -c '^    match.expires_at = datetime.now(UTC) + timedelta(days=RAW_RETENTION_DAYS)$' "$F")" -eq 1 ] || { echo "STEP1-BLOCKED (expires_at line not unique)"; exit 1; }
sed -i '' "${X}d" "$F" && sed -i '' "$((X-1))r briefs/assets/P0-D9/expires_video.py" "$F" && echo ADMIN-DEADLINE-PRESERVED
