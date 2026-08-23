#!/bin/bash
# P0-D3 — shipped step 2: replace mint_media_read_sas (6 lines: def … return) in src/services/video_storage.py. Run: bash briefs/assets/P0-D3/step-2.sh
F=academy-watch-backend/src/services/video_storage.py
M=$(grep -n '^def mint_media_read_sas(blob_path: str, minutes: int = MEDIA_READ_SAS_MINUTES) -> str:$' "$F" | cut -d: -f1); echo "M=$M"
[ -n "$M" ] || { echo "STEP2-BLOCKED (old function signature not found)"; exit 1; }
E=$(awk -v s="$M" 'NR>s && /^    return f"\{client.url\}\{_container\(\)\}\/\{blob_path\}\?\{sas\}"$/ {print NR; exit}' "$F"); echo "E=$E"
[ -n "$E" ] && [ "$E" -eq "$((M+5))" ] || { echo "STEP2-BLOCKED (function shape unexpected: M=$M E=$E)"; exit 1; }
sed -i '' "${M},${E}d" "$F" && sed -i '' "$((M-1))r briefs/assets/P0-D3/mint_media_read_sas.py" "$F" && echo FUNCTION-REPLACED
