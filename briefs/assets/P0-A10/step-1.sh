#!/bin/bash
# P0-A10 — shipped step 1: api.js gains getFeatures() right above getProfile(). Run: bash briefs/assets/P0-A10/step-1.sh
F=academy-watch-frontend/src/lib/api.js
G=$(grep -n '^    static async getProfile() {$' "$F" | cut -d: -f1); echo "G=$G"
[ -n "$G" ] || { echo "STEP1-BLOCKED (getProfile anchor not found)"; exit 1; }
sed -i '' "$((G-1))r briefs/assets/P0-A10/features-method.js" "$F" && echo FEATURES-METHOD-INSERTED
