#!/bin/bash
# P0-D5 — shipped step 2: src/routes/video.py — /process and /requeue load the match FOR UPDATE (same lock the sweeper takes). Run: bash briefs/assets/P0-D5/step-2.sh
F=academy-watch-backend/src/routes/video.py
P=$(grep -n '^    """Debit one credit and queue the GPU job. 402 when the team has no credits."""$' "$F" | cut -d: -f1); echo "P=$P"
[ -n "$P" ] && [ "$(sed -n "$((P+1))p" "$F")" = '    match = _get_match_or_404(match_id)' ] || { echo "STEP2-BLOCKED (process_match shape unexpected)"; exit 1; }
sed -i '' "$((P+1))d" "$F" && sed -i '' "${P}r briefs/assets/P0-D5/process_lock_line.py" "$F" && echo PROCESS-LOCKED
Q=$(grep -n '^    """Admin: re-run a failed job WITHOUT a new debit."""$' "$F" | cut -d: -f1); echo "Q=$Q"
[ -n "$Q" ] && [ "$(sed -n "$((Q+1))p" "$F")" = '    match = _get_match_or_404(match_id)' ] || { echo "STEP2-BLOCKED (requeue_match shape unexpected)"; exit 1; }
sed -i '' "$((Q+1))d" "$F" && sed -i '' "${Q}r briefs/assets/P0-D5/process_lock_line.py" "$F" && echo REQUEUE-LOCKED
grep -c "with_for_update=True" "$F" | sed 's/^/with_for_update lines in video.py (expect 2): /'
