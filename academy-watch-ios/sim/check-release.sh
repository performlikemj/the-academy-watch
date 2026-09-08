#!/bin/bash
# Validate a full, revision-matched report before an iOS release.
set -euo pipefail
app_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
: "${HARNESS_ROOT:?Set HARNESS_ROOT to the harness checkout}"
report_dir=${1:?Usage: sim/check-release.sh <full-report-directory>}
node "$HARNESS_ROOT/checks/story-map.mjs" check "$app_root"
/bin/bash "$HARNESS_ROOT/checks/sim-report.sh" --strict --app-dir "$app_root" "$report_dir"
release_stories=()
while IFS= read -r story; do release_stories+=("$story"); done < <(
  awk '
    /^sim:/ { sim=1; next }
    sim && /^[^[:space:]]/ { exit }
    sim && /^  release_stories:/ { stories=1; next }
    stories && /^    - [a-z0-9-]+$/ { sub(/^    - /, ""); print; next }
    stories { exit }
  ' "$app_root/harness.yaml"
)
[ "${#release_stories[@]}" -gt 0 ] || { echo "No sim.release_stories declared" >&2; exit 2; }
node "$app_root/sim/stories-proof.mjs" --app-dir "$app_root" --report-dir "$report_dir" \
  --require-proven "${release_stories[@]}"
