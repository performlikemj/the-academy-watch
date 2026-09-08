#!/bin/bash
# Read-only gates against the committed app and every retained report bundle.
set -euo pipefail
: "${HARNESS_ROOT:?Set HARNESS_ROOT}"
repo=$(git rev-parse --show-toplevel)
cd "$repo"
for report in ledgers/research/story-map-proof/green-*/report.json ledgers/research/story-map-proof/red-*/report.json; do
  bundle=$(dirname "$report")
  python3 - "$bundle" <<'PY'
import json, pathlib, subprocess, sys
bundle = pathlib.Path(sys.argv[1])
report = json.loads((bundle / 'report.json').read_text())
required = ['report.json', 'steps.json', 'stories.json'] + [s['shot'] for j in report['journeys'] for s in j['steps']]
for name in required:
    file = bundle / name
    committed = subprocess.check_output(['git', 'show', f'HEAD:{file.as_posix()}'])
    assert file.read_bytes() == committed, f'not identical to committed bytes: {file}'
print(f'committed bundle: {len(required) - 3} screenshots; all referenced bytes match HEAD')
PY
  bash "$HARNESS_ROOT/checks/sim-report.sh" --strict --app-dir academy-watch-ios "$bundle"
  case "$bundle" in
    */green-*) node academy-watch-ios/sim/stories-proof.mjs "$bundle" --require-proven scout-opens-app change-home-changes-home ;;
  esac
done
node "$HARNESS_ROOT/checks/story-map.mjs" check academy-watch-ios
