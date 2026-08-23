#!/bin/bash
# P0-D3 — shipped step 1: append media_token_remaining_seconds to the end of src/auth.py. Run: bash briefs/assets/P0-D3/step-1.sh
F=academy-watch-backend/src/auth.py
grep -q '^def media_token_remaining_seconds' "$F" && { echo "STEP1-BLOCKED (helper already present)"; exit 1; }
cat briefs/assets/P0-D3/media_token_remaining.py >> "$F" && echo HELPER-APPENDED
