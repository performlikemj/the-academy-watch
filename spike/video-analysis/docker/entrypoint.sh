#!/bin/bash
# Spike job entrypoint for ACA GPU Jobs.
# Required env:
#   FOOTAGE_SAS_URL   read SAS URL of the input video blob
#   RESULTS_SAS_URL   container SAS URL (create+write) for uploading results,
#                     e.g. https://acct.blob.core.windows.net/spike?<sas>
# Optional env:
#   RUN_NAME          results prefix (default: spike-<epoch>)
#   SPIKE_ARGS        extra args appended to run_spike.py
set -euo pipefail

RUN_NAME="${RUN_NAME:-spike-$(date +%s)}"
# Non-root friendly paths (ACA GPU profile does not run the container as root).
WORK="${WORK_DIR:-/tmp/work}"
export HF_HOME=/tmp/hf TORCH_HOME=/tmp/torch MPLCONFIGDIR=/tmp/mpl NUMBA_CACHE_DIR=/tmp/numba
mkdir -p "$WORK/results" "$HF_HOME" "$TORCH_HOME" "$MPLCONFIGDIR" "$NUMBA_CACHE_DIR"

echo "=== GPU check ==="
python -c "import torch; print('cuda available:', torch.cuda.is_available(), '|', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'none')"

echo "=== downloading footage ==="
curl -sfSL -o "$WORK/match.mp4" "$FOOTAGE_SAS_URL"
ls -la "$WORK/match.mp4"

echo "=== running spike ($RUN_NAME) ==="
set +e
# shellcheck disable=SC2086
python -u /app/run_spike.py --video "$WORK/match.mp4" --device cuda --slicer both \
    --out "$WORK/results" ${SPIKE_ARGS:-} 2>&1 | tee "$WORK/results/run.log"
SPIKE_RC=${PIPESTATUS[0]}
set -e
echo "spike exit code: $SPIKE_RC"

MERGE_RC=0
if [ "${SKIP_MERGE:-0}" = "1" ]; then
    echo "=== merge skipped (chunked run; merge happens after all chunks) ==="
else
    echo "=== merging tracklets ==="
    set +e
    python -u /app/merge_tracklets.py --results-dir "$WORK/results" --video "$WORK/match.mp4" \
        ${MERGE_ARGS:-} 2>&1 | tee -a "$WORK/results/run.log"
    MERGE_RC=${PIPESTATUS[0]}
    set -e
    echo "merge exit code: $MERGE_RC"
fi

echo "=== uploading results ==="
BASE="${RESULTS_SAS_URL%%\?*}"
SAS="${RESULTS_SAS_URL#*\?}"
shopt -s nullglob
for f in "$WORK"/results/*; do
    name=$(basename "$f")
    echo "PUT $name"
    curl -sfS -X PUT -H "x-ms-blob-type: BlockBlob" \
        --upload-file "$f" "$BASE/$RUN_NAME/$name?$SAS" || echo "WARN: upload failed for $name"
done

echo "=== report (stdout copy) ==="
cat "$WORK"/results/report.md 2>/dev/null || echo "(no report.md produced)"
cat "$WORK"/results/merge_report.json 2>/dev/null || echo "(no merge_report.json produced)"

if [ "$SPIKE_RC" -ne 0 ]; then exit "$SPIKE_RC"; fi
exit "$MERGE_RC"
