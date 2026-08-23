#!/bin/bash
# P0-C3 — shipped step 1 (run from the worktree root: bash briefs/assets/P0-C3/step-1.sh)
FI=$(grep -n '^from flask import g, jsonify$' academy-watch-backend/src/services/club_registry.py | cut -d: -f1); echo "FI=$FI"; sed -i '' "${FI}d" academy-watch-backend/src/services/club_registry.py && sed -i '' "$((FI-1))r briefs/assets/P0-C3/flask_import.py" academy-watch-backend/src/services/club_registry.py && echo IMPORT-REPLACED
