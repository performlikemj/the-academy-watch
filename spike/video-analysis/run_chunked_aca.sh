#!/bin/bash
# Drive a chunked spike run on the ACA GPU job: one execution per footage chunk,
# each well under the ~33-minute serverless-GPU eviction window observed on
# 2026-06-10/11. Artifacts land in blob under $RUN_PREFIX/chunk<i>/.
# After all chunks: merge locally with
#   python merge_tracklets.py --results-dir <combined> --chunk-dirs <chunk dirs> --video <match>
set -uo pipefail

JOB=job-video-spike
RG=rg-video-spike
RUN_PREFIX="${RUN_PREFIX:-veo-v8}"
VIDEO_SECONDS="${VIDEO_SECONDS:-6921}"
CHUNK_SECONDS="${CHUNK_SECONDS:-1500}"
ATTEMPTS_PER_CHUNK=2

n_chunks=$(( (VIDEO_SECONDS + CHUNK_SECONDS - 1) / CHUNK_SECONDS ))
echo "video ${VIDEO_SECONDS}s -> ${n_chunks} chunks of ${CHUNK_SECONDS}s"

for (( i=0; i<n_chunks; i++ )); do
  S=$(( i * CHUNK_SECONDS ))
  E=$(( S + CHUNK_SECONDS ))
  (( E > VIDEO_SECONDS )) && E=$VIDEO_SECONDS
  OFF=$(( (i + 1) * 1000000 ))
  ok=0
  for (( attempt=1; attempt<=ATTEMPTS_PER_CHUNK; attempt++ )); do
    echo "=== chunk $i [$S,$E] tid-offset $OFF (attempt $attempt) ==="
    az containerapp job update -n "$JOB" -g "$RG" --replace-env-vars \
      "FOOTAGE_SAS_URL=secretref:footage-sas" \
      "RESULTS_SAS_URL=secretref:results-sas" \
      "RUN_NAME=$RUN_PREFIX/chunk$i" \
      "SKIP_MERGE=1" \
      "SPIKE_ARGS=--start-seconds $S --max-seconds $E --tid-offset $OFF --slicer off --render-start 999999" \
      -o none 2>/dev/null || { echo "job update failed"; sleep 30; continue; }
    EXEC=$(az containerapp job start -n "$JOB" -g "$RG" -o tsv --query name 2>/dev/null)
    [ -z "$EXEC" ] && { echo "start failed"; sleep 30; continue; }
    echo "chunk $i execution: $EXEC"
    while true; do
      STATUS=$(az containerapp job execution show -n "$JOB" -g "$RG" --job-execution-name "$EXEC" --query "properties.status" -o tsv 2>/dev/null)
      echo "$(date '+%H:%M:%S') chunk $i: $STATUS"
      case "$STATUS" in
        Succeeded) ok=1; break;;
        Failed|Stopped) break;;
      esac
      sleep 120
    done
    (( ok )) && break
  done
  (( ok )) || echo "WARNING: chunk $i FAILED after $ATTEMPTS_PER_CHUNK attempts — merge will run without it"
done
echo "ALL CHUNKS DONE"
