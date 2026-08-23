#!/bin/bash
# P0-A10b — shipped step 1: append the /features route to the end of auth_routes.py. Run: bash briefs/assets/P0-A10b/step-1.sh
F=academy-watch-backend/src/routes/api.py
grep -q '^def features():$' "$F" && { echo "STEP1-BLOCKED (route already present)"; exit 1; }
cat briefs/assets/P0-A10b/features_route.py >> "$F" && echo ROUTE-APPENDED
grep -n '^@api_bp.route("/features", methods=\["GET"\])$' "$F" | cut -d: -f1 | sed 's/^/route at line /'
