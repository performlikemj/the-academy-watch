#!/bin/bash
# Build once, run every selected journey once, verify XCTest evidence, and publish atomically.

set -u

SIM_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
if [ -n "${SIM_APP_ROOT-}" ]; then APP_ROOT=$(CDPATH= cd -- "$SIM_APP_ROOT" && pwd)
else APP_ROOT=$(CDPATH= cd -- "$SIM_DIR/.." && pwd); fi

usage() {
  echo "Usage: run.sh [--journey <file>]... [--destination <dest>] [--scheme <name>] [--only-testing <selector>] [--out <dir>] [--grade|--no-grade]"
  echo "Environment: SIM_SCHEME, SIM_UI_TEST_TARGET, SIM_PROJECT|SIM_WORKSPACE, SIM_APP,"
  echo "             SIM_PERSONA, SIM_PERSONA_MANIFEST, HARNESS_ROOT, SIM_GRADE_BUDGET_S"
}

journeys=()
destination_arg=
out_arg=
grade_arg=
scheme_arg=
only_testing_arg=
while [ "$#" -gt 0 ]; do
  case "$1" in
    --journey) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; journeys+=("$2"); shift 2 ;;
    --destination) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; destination_arg=$2; shift 2 ;;
    --scheme) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; scheme_arg=$2; shift 2 ;;
    --only-testing) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; only_testing_arg=$2; shift 2 ;;
    --out) [ "$#" -ge 2 ] || { usage >&2; exit 2; }; out_arg=$2; shift 2 ;;
    --grade) grade_arg=1; shift ;;
    --no-grade) grade_arg=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "run.sh: unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

yaml_sim_value() {
  yaml_key=$1
  yaml_file=$2
  [ -f "$yaml_file" ] || return 0
  awk -v key="$yaml_key" '
    /^sim:[[:space:]]*$/ { inside=1; next }
    inside && /^[^[:space:]]/ { exit }
    inside {
      line=$0; sub(/^[[:space:]]+/, "", line)
      if (index(line, key ":") == 1) {
        sub("^" key ":[[:space:]]*", "", line)
        gsub(/^[\047\"]|[\047\"]$/, "", line)
        print line; exit
      }
    }
  ' "$yaml_file"
}

resolve_from_root() {
  case "$1" in /*) printf '%s\n' "$1" ;; *) printf '%s\n' "$APP_ROOT/$1" ;; esac
}

harness_root=${HARNESS_ROOT-}
if [ -z "$harness_root" ]; then
  probe=$APP_ROOT
  while [ "$probe" != / ]; do
    if [ -x "$probe/checks/session-reclaim.sh" ]; then harness_root=$probe; break; fi
    probe=$(dirname "$probe")
  done
fi

config_file="$APP_ROOT/harness.yaml"
if [ -n "$destination_arg" ]; then
  destination=$destination_arg
  destination_source="CLI --destination"
else
  destination=$(yaml_sim_value destination "$config_file")
  if [ -n "$destination" ]; then destination_source="harness.yaml sim.destination"
  else destination="platform=iOS Simulator,name=iPhone 17,OS=26.2"; destination_source="pack canonical"; fi
fi
echo "Destination source: $destination_source"
echo "Destination: $destination"

destination_os=$(printf '%s\n' "$destination" | sed -n 's/.*OS=\([^,]*\).*/\1/p')
if [ -z "$destination_os" ]; then
  echo "run.sh: destination must pin an OS= runtime: $destination" >&2
  exit 2
fi
runtime_line=$(xcrun simctl list runtimes 2>/dev/null | grep "iOS $destination_os " | head -n 1)
if [ -z "$runtime_line" ] || printf '%s' "$runtime_line" | grep -qi unavailable; then
  echo "run.sh: required iOS $destination_os simulator runtime is not installed" >&2
  exit 2
fi

journeys_dir=${SIM_JOURNEYS_DIR:-$(yaml_sim_value journeys_dir "$config_file")}
journeys_dir=$(resolve_from_root "${journeys_dir:-sim/journeys}")
report_root=${out_arg:-${SIM_REPORT_DIR:-$(yaml_sim_value report_dir "$config_file")}}
report_root=$(resolve_from_root "${report_root:-sim/report}")
grade=${grade_arg:-${SIM_GRADE:-$(yaml_sim_value grade "$config_file")}}
case "${grade:-true}" in
  1|true|TRUE|yes|YES) grade=1 ;;
  0|false|FALSE|no|NO) grade=0 ;;
  *) echo "run.sh: sim.grade must be true or false" >&2; exit 2 ;;
esac

if [ "${#journeys[@]}" -eq 0 ]; then
  for journey_file in "$journeys_dir"/*.json; do [ -f "$journey_file" ] && journeys+=("$journey_file"); done
fi
if [ "${#journeys[@]}" -eq 0 ]; then echo "run.sh: no journey files found in $journeys_dir" >&2; exit 2; fi

resolved_journeys=()
for journey_file in "${journeys[@]}"; do
  case "$journey_file" in /*) resolved=$journey_file ;; *) resolved="$APP_ROOT/$journey_file" ;; esac
  if [ ! -f "$resolved" ]; then echo "run.sh: journey file is missing: $journey_file" >&2; exit 2; fi
  resolved=$(CDPATH= cd -- "$(dirname -- "$resolved")" && pwd)/$(basename "$resolved")
  resolved_journeys+=("$resolved")
done

scheme=${scheme_arg:-${SIM_SCHEME-}}
container_args=()
if [ -n "${SIM_WORKSPACE-}" ]; then
  workspace=$(resolve_from_root "$SIM_WORKSPACE"); container_args=(-workspace "$workspace")
  [ -n "$scheme" ] || scheme=$(basename "$workspace" .xcworkspace)
elif [ -n "${SIM_PROJECT-}" ]; then
  project=$(resolve_from_root "$SIM_PROJECT"); container_args=(-project "$project")
  [ -n "$scheme" ] || scheme=$(basename "$project" .xcodeproj)
else
  for workspace in "$APP_ROOT"/*.xcworkspace; do
    if [ -d "$workspace" ]; then container_args=(-workspace "$workspace"); [ -n "$scheme" ] || scheme=$(basename "$workspace" .xcworkspace); break; fi
  done
  if [ "${#container_args[@]}" -eq 0 ]; then
    for project in "$APP_ROOT"/*.xcodeproj; do
      if [ -d "$project" ]; then container_args=(-project "$project"); [ -n "$scheme" ] || scheme=$(basename "$project" .xcodeproj); break; fi
    done
  fi
fi
if [ "${#container_args[@]}" -eq 0 ] || [ -z "$scheme" ]; then
  echo "run.sh: set SIM_PROJECT or SIM_WORKSPACE and SIM_SCHEME; no Xcode container was found" >&2
  exit 2
fi

only_testing=${only_testing_arg:-${SIM_ONLY_TESTING-}}
if [ -n "$only_testing" ]; then
  selected_target=${only_testing%%/*}
  case "$only_testing" in */*) ;; *) echo "run.sh: --only-testing must include target/class" >&2; exit 2 ;; esac
  ui_test_target=${SIM_UI_TEST_TARGET:-$selected_target}
  if [ "$selected_target" != "$ui_test_target" ]; then
    echo "run.sh: --only-testing target must match SIM_UI_TEST_TARGET" >&2
    exit 2
  fi
else
  ui_test_target=${SIM_UI_TEST_TARGET:-JourneyRunnerUITests}
  only_testing="$ui_test_target/JourneyRunnerUITests/testJourneys"
fi
app_name=${SIM_APP:-$(basename "$APP_ROOT")}
persona_path=${SIM_PERSONA-}
[ -n "$persona_path" ] || { [ -n "$harness_root" ] && persona_path="$harness_root/core/personas/yuki.md"; }
persona_manifest=${SIM_PERSONA_MANIFEST:-$SIM_DIR/persona/yuki.json}
if [ "$grade" -eq 1 ] && { [ ! -f "$persona_path" ] || [ ! -f "$persona_manifest" ]; }; then
  echo "run.sh: grading requires SIM_PERSONA markdown and SIM_PERSONA_MANIFEST" >&2
  exit 2
fi

mkdir -p "$report_root/.receipts" "$report_root/.cache" || exit 2
keep_days=${SIM_KEEP_DAYS:-14}
case "$keep_days" in ''|*[!0-9]*) echo "run.sh: SIM_KEEP_DAYS must be an integer" >&2; exit 2 ;; esac
find "$report_root" -mindepth 1 -maxdepth 1 -type d -mtime +"$keep_days" -print 2>/dev/null |
while IFS= read -r old_report; do
  old_name=$(basename "$old_report")
  case "$old_name" in [0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9]T[0-9][0-9][0-9][0-9][0-9][0-9]Z*) rm -rf "$old_report" ;; esac
done

run_at=$(date -u '+%Y-%m-%dT%H:%M:%SZ')
stamp=$(date -u '+%Y%m%dT%H%M%SZ')
final_report="$report_root/$stamp"
staging="$report_root/.staging-$stamp"
suffix=1
while [ -e "$final_report" ] || [ -e "$staging" ]; do
  final_report="$report_root/$stamp-$suffix"; staging="$report_root/.staging-$stamp-$suffix"; suffix=$((suffix + 1))
done
mkdir -p "$staging/shots" "$staging/diagnostics" || exit 2
tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/harness-ios-sim.XXXXXX") || exit 2

cleanup() {
  status=$?
  trap - EXIT
  rm -rf "$tmp_dir"
  if [ -n "$harness_root" ] && [ -x "$harness_root/checks/session-reclaim.sh" ]; then
    reclaim_line=$(/bin/bash "$harness_root/checks/session-reclaim.sh" --reclaim --quiet "$APP_ROOT" 2>&1)
    reclaim_status=$?
    echo "sim reclaim: $reclaim_line"
    [ "$reclaim_status" -eq 0 ] || echo "sim reclaim: check exited $reclaim_status" >&2
  else
    echo "sim reclaim: skipped (HARNESS_ROOT/checks/session-reclaim.sh not found)"
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

if [ -n "$harness_root" ] && [ -x "$harness_root/checks/session-reclaim.sh" ]; then
  audit_line=$(/bin/bash "$harness_root/checks/session-reclaim.sh" --audit --quiet "$APP_ROOT" 2>&1)
  audit_status=$?
  echo "sim reclaim audit: $audit_line"
  if [ "$audit_status" -ne 0 ]; then echo "run.sh: session reclaim audit failed" >&2; exit 2; fi
else
  echo "sim reclaim audit: skipped (HARNESS_ROOT/checks/session-reclaim.sh not found)"
fi

locale=${SIM_LOCALE:-en_US}
timezone=${SIM_TIMEZONE:-Asia/Tokyo}
appearance=${SIM_APPEARANCE:-light}
dynamic_type=${SIM_DYNAMIC_TYPE:-large}
prepared="$tmp_dir/journeys.json"
plan="$tmp_dir/plan.json"

if ! node --input-type=module - "$report_root/.receipts" "$prepared" "$plan" "$locale" "$timezone" "$appearance" "$dynamic_type" "${resolved_journeys[@]}" <<'NODE'
import crypto from 'node:crypto'
import fs from 'node:fs'
import path from 'node:path'

const [receiptRoot, preparedPath, planPath, locale, timezone, appearance, dynamicType, ...files] = process.argv.slice(2)
const sourcePattern = /^.+:[0-9]+(?:-[0-9]+)?$/
const secretName = /password|token|secret|bearer/i
const prepared = []
const plan = []
for (const file of files) {
  const bytes = fs.readFileSync(file)
  let source = bytes.toString('utf8')
  if (source.includes('${SIM_BACKEND_PORT}')) {
    const backendPort = process.env.SIM_BACKEND_PORT || '5001'
    if (!/^[0-9]+$/.test(backendPort) || Number(backendPort) < 1 || Number(backendPort) > 65535) {
      throw new Error(`SIM_BACKEND_PORT must be between 1 and 65535 for ${file}`)
    }
    source = source.replaceAll('${SIM_BACKEND_PORT}', backendPort)
  }
  let journey
  try { journey = JSON.parse(source) } catch { throw new Error(`journey JSON is invalid: ${file}`) }
  if (!['1.1', '1.2'].includes(String(journey.version))) throw new Error(`journey must use version 1.1 or 1.2: ${file}`)
  if (!journey.name || !Array.isArray(journey.steps) || !journey.steps.length) throw new Error(`journey name/steps missing: ${file}`)
  for (const [key, fallback] of [['settle_ms', 400], ['settle_timeout_ms', 4000]]) {
    const value = journey[key] === undefined ? fallback : journey[key]
    if (!Number.isInteger(value) || value <= 0) throw new Error(`${key} must be a positive integer in ${file}`)
  }
  const settleQuietRatio = journey.settle_quiet_ratio === undefined ? 0.005 : journey.settle_quiet_ratio
  if (typeof settleQuietRatio !== 'number' || !Number.isFinite(settleQuietRatio) || settleQuietRatio < 0 || settleQuietRatio > 1) {
    throw new Error(`settle_quiet_ratio must be between zero and one in ${file}`)
  }
  const evidence = journey.fixture_evidence
  if (!evidence || !Array.isArray(evidence.offered_inputs) || !evidence.offered_inputs.length ||
      !Array.isArray(evidence.server_state) || !Array.isArray(evidence.layout) || !evidence.layout.length ||
      !evidence.preflight || !['none', 'api'].includes(evidence.preflight.kind) || !evidence.preflight.note) {
    throw new Error(`fixture_evidence is required and incomplete: ${file}`)
  }
  if (!evidence.server_state.length && !evidence.server_state_reason) throw new Error(`empty server_state requires server_state_reason: ${file}`)
  for (const claim of [...evidence.offered_inputs, ...evidence.server_state, ...evidence.layout]) {
    if (!claim?.claim || !sourcePattern.test(claim?.source || '')) throw new Error(`invalid fixture evidence source in ${file}`)
  }
  if (!journey.steps.some((step) => step.checkpoint === true)) throw new Error(`journey needs a checkpoint:true step: ${file}`)
  const seen = new Set()
  for (const step of journey.steps) {
    if (!step.id || seen.has(step.id) || typeof step.expectation !== 'string' || !step.action || Object.keys(step.action).length !== 1) {
      throw new Error(`invalid or duplicate step in ${file}`)
    }
    seen.add(step.id)
    for (const key of ['settle_ms', 'settle_timeout_ms']) {
      if (step[key] !== undefined && (!Number.isInteger(step[key]) || step[key] <= 0)) {
        throw new Error(`${key} must be a positive integer in step ${step.id} of ${file}`)
      }
    }
    if (step.settle_quiet_ratio !== undefined &&
        (typeof step.settle_quiet_ratio !== 'number' || !Number.isFinite(step.settle_quiet_ratio) ||
         step.settle_quiet_ratio < 0 || step.settle_quiet_ratio > 1)) {
      throw new Error(`settle_quiet_ratio must be between zero and one in step ${step.id} of ${file}`)
    }
    if (step.settle !== undefined) {
      const waitFor = step.settle?.waitFor
      const byID = typeof waitFor?.id === 'string' && waitFor.id.length > 0
      const byText = typeof waitFor?.text === 'string' && waitFor.text.length > 0
      if (!waitFor || byID === byText || !(step.settle.timeout > 0)) {
        throw new Error(`settle requires waitFor with id or text, plus positive timeout, in step ${step.id} of ${file}`)
      }
    }
    const [action, value] = Object.entries(step.action)[0]
    if (!['launch','tap','type','clearAndType','swipe','waitFor','assertVisible','screenshot','dismissKeyboard','systemAlert'].includes(action)) {
      throw new Error(`unsupported action ${action} in ${file}`)
    }
    if (action === 'launch') {
      for (const key of Object.keys(value.env || {})) if (secretName.test(key)) throw new Error(`forbidden launch environment key ${key} in ${file}`)
      value.args = ['-AppleLanguages', '(en)', '-AppleLocale', locale, '-AppleInterfaceStyle', appearance === 'dark' ? 'Dark' : 'Light', '-UIPreferredContentSizeCategoryName', dynamicType, ...(value.args || [])]
      value.env = { TZ: timezone, ...(value.env || {}) }
    }
    if (['tap','waitFor','assertVisible'].includes(action)) {
      const byID = typeof value.id === 'string' && value.id.length > 0
      const byText = typeof value.text === 'string' && value.text.length > 0 && typeof value.why === 'string' && value.why.length > 0
      if (byID === byText) throw new Error(`${action} requires id, or text plus why, in ${file}`)
    }
    if (['type','clearAndType'].includes(action) && (!value.id || typeof value.text !== 'string')) throw new Error(`${action} requires id and text in ${file}`)
  }
  const preconditions = journey.preconditions || []
  for (const precondition of preconditions) {
    if (!['resetPermission', 'grantPermission', 'push'].includes(precondition?.kind)) throw new Error(`unsupported precondition in ${file}`)
    if (precondition.kind === 'push' && (!precondition.bundle_id || typeof precondition.payload !== 'object')) throw new Error(`push requires bundle_id and payload in ${file}`)
    if (precondition.kind !== 'push' && (!precondition.bundle_id || !precondition.service)) throw new Error(`${precondition.kind} requires service and bundle_id in ${file}`)
  }
  let apiPreflight = null
  if (evidence.preflight.kind === 'api') {
    const launchArgs = journey.steps.flatMap((step) => step.action?.launch?.args || [])
    const baseIndex = launchArgs.indexOf('-apiBaseURL')
    const searchStep = journey.steps.find((step) => step.action?.type?.id === 'scout-search' || step.action?.clearAndType?.id === 'scout-search')
    const playerStep = journey.steps.find((step) => /^scout-player--?[0-9]+$/.test(step.action?.tap?.id || ''))
    const baseURL = baseIndex >= 0 ? launchArgs[baseIndex + 1] : ''
    const search = searchStep?.action?.type?.text ?? searchStep?.action?.clearAndType?.text ?? ''
    const playerID = (playerStep?.action?.tap?.id || '').replace('scout-player-', '')
    let parsed
    try { parsed = new URL(baseURL) } catch { throw new Error(`api preflight requires a valid -apiBaseURL in ${file}`) }
    if (parsed.protocol !== 'http:' || !['127.0.0.1', 'localhost'].includes(parsed.hostname) || !search || !playerID) {
      throw new Error(`api preflight requires loopback -apiBaseURL, scout-search text, and scout-player id in ${file}`)
    }
    apiPreflight = { base_url: baseURL.replace(/\/$/, ''), search, player_id: playerID }
  }
  const hash = crypto.createHash('sha256').update(bytes).digest('hex')
  const receiptPath = path.join(receiptRoot, hash)
  const checkpointOnly = !fs.existsSync(receiptPath)
  prepared.push({ ...journey, journey_hash: hash, checkpoint_only: checkpointOnly })
  plan.push({ name: journey.name, hash, receipt_path: receiptPath, checkpoint_only: checkpointOnly, preconditions, api_preflight: apiPreflight })
}
fs.writeFileSync(preparedPath, JSON.stringify(prepared))
fs.writeFileSync(planPath, JSON.stringify(plan))
NODE
then
  echo "run.sh: journey validation/preparation failed" >&2
  exit 2
fi

api_preflight_count=$(node -e 'const p=require(process.argv[1]); console.log(p.filter(j=>j.api_preflight).length)' "$plan")
if [ "$api_preflight_count" -gt 0 ]; then
  node - "$plan" "$tmp_dir" <<'NODE'
const fs = require('fs')
const { execFileSync } = require('child_process')
const [planPath, temporary] = process.argv.slice(2)
let sequence = 0
for (const journey of JSON.parse(fs.readFileSync(planPath, 'utf8'))) {
  const item = journey.api_preflight
  if (!item) continue
  const health = execFileSync('curl', ['-fsS', '--max-time', '5', `${item.base_url}/health`], { encoding: 'utf8' })
  JSON.parse(health)
  const scoutPath = `${temporary}/preflight-scout-${++sequence}.json`
  const scout = execFileSync('curl', ['-fsS', '--max-time', '15', '--get', '--data-urlencode', `search=${item.search}`, '--data', 'per_page=25', `${item.base_url}/scout/players`], { encoding: 'utf8' })
  fs.writeFileSync(scoutPath, scout)
  const scoutPayload = JSON.parse(scout)
  const players = Array.isArray(scoutPayload.players) ? scoutPayload.players : []
  const matches = players.filter((player) => String(player.player_id) === String(item.player_id)).length
  if (!matches) throw new Error(`preflight did not find player ${item.player_id} in the Scout Desk response`)
  const profile = execFileSync('curl', ['-fsS', '--max-time', '15', `${item.base_url}/players/${item.player_id}/profile`], { encoding: 'utf8' })
  const profileCount = JSON.parse(profile)?.player_id === Number(item.player_id) ? 1 : 0
  if (!profileCount) throw new Error(`preflight profile did not match player ${item.player_id}`)
  console.log(`preflight: health=1 scout_players=${players.length} selected_player_matches=${matches} profile_matches=${profileCount}`)
}
NODE
  if [ "$?" -ne 0 ]; then echo "run.sh: API preflight failed" >&2; exit 2; fi
fi

precondition_count=$(node -e 'const p=require(process.argv[1]); console.log(p.reduce((n,j)=>n+j.preconditions.length,0))' "$plan")
if [ "$precondition_count" -gt 0 ]; then
  device_json="$tmp_dir/devices.json"
  xcrun simctl list devices available -j > "$device_json" || exit 2
  device_udid=$(node - "$device_json" "$destination" "$destination_os" <<'NODE'
const fs = require('fs')
const data = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))
const destination = process.argv[3]
const os = process.argv[4]
const id = destination.match(/(?:^|,)id=([^,]+)/)?.[1]
if (id) { process.stdout.write(id); process.exit(0) }
const name = destination.match(/(?:^|,)name=([^,]+)/)?.[1]
const runtime = Object.entries(data.devices).find(([key]) => key.endsWith(`-${os.replaceAll('.', '-')}`))
const device = runtime?.[1].find((item) => item.name === name && item.isAvailable)
if (!device) process.exit(1)
process.stdout.write(device.udid)
NODE
  ) || { echo "run.sh: could not resolve a simulator for preconditions" >&2; exit 2; }
  xcrun simctl boot "$device_udid" >/dev/null 2>&1 || true
  xcrun simctl bootstatus "$device_udid" -b || { echo "run.sh: simulator boot readiness failed" >&2; exit 2; }
  node --input-type=module - "$plan" "$device_udid" "$tmp_dir" <<'NODE'
import fs from 'node:fs'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
const [planPath, udid, temporary] = process.argv.slice(2)
let sequence = 0
for (const journey of JSON.parse(fs.readFileSync(planPath, 'utf8'))) {
  for (const item of journey.preconditions) {
    let args
    if (item.kind === 'push') {
      const payload = path.join(temporary, `push-${++sequence}.json`)
      fs.writeFileSync(payload, JSON.stringify(item.payload))
      args = ['simctl', 'push', udid, item.bundle_id, payload]
    } else {
      const verb = item.kind === 'grantPermission' ? 'grant' : 'reset'
      args = ['simctl', 'privacy', udid, verb, item.service, item.bundle_id]
    }
    const result = spawnSync('xcrun', args, { stdio: 'inherit' })
    if (result.status !== 0) throw new Error(`simctl precondition failed: ${item.kind}`)
  }
}
NODE
fi

echo "iOS sim: app=$app_name scheme=$scheme target=$ui_test_target only-testing=$only_testing journeys=${#resolved_journeys[@]}"
if ! (
  cd "$APP_ROOT" || exit 2
  xcodebuild "${container_args[@]}" -scheme "$scheme" -destination "$destination" \
    -derivedDataPath "$tmp_dir/DerivedData" CODE_SIGNING_ALLOWED=NO build-for-testing
) > "$tmp_dir/build.log" 2>&1; then
  echo "run.sh: build-for-testing failed" >&2; tail -n 80 "$tmp_dir/build.log" >&2; exit 2
fi
xctestrun_base=$(find "$tmp_dir/DerivedData/Build/Products" -maxdepth 1 -type f -name '*.xctestrun' -print | head -n 1)
if [ -z "$xctestrun_base" ]; then echo "run.sh: build did not produce an .xctestrun file" >&2; exit 2; fi

xctestrun_dir=$(dirname "$xctestrun_base")
run_configuration="$xctestrun_dir/sim-run.xctestrun"
cp "$xctestrun_base" "$run_configuration" || exit 2
journeys_json=$(cat "$prepared")
environment_key="$ui_test_target.EnvironmentVariables.SIM_JOURNEYS_JSON"
if plutil -extract "$environment_key" raw -o - "$run_configuration" >/dev/null 2>&1; then
  plutil -replace "$environment_key" -string "$journeys_json" "$run_configuration"
else
  plutil -insert "$environment_key" -string "$journeys_json" "$run_configuration"
fi
if [ "$?" -ne 0 ]; then echo "run.sh: could not inject SIM_JOURNEYS_JSON content" >&2; exit 2; fi

result_bundle="$staging/run-$stamp.xcresult"
test_log="$tmp_dir/test.log"
run_test() {
  (
    cd "$APP_ROOT" || exit 2
    xcodebuild -xctestrun "$run_configuration" -destination "$destination" \
      -resultBundlePath "$result_bundle" CODE_SIGNING_ALLOWED=NO \
      test-without-building -only-testing:"$only_testing"
  ) > "$test_log" 2>&1
}
if ! run_test; then
  echo "run.sh: test infrastructure failed; retrying once" >&2
  rm -rf "$result_bundle"
  if ! run_test; then echo "run.sh: test-without-building failed after one retry" >&2; tail -n 100 "$test_log" >&2; exit 2; fi
fi

export_dir="$staging/.attachments"
if ! xcrun xcresulttool export attachments --path "$result_bundle" --output-path "$export_dir" > "$tmp_dir/export.log" 2>&1; then
  echo "run.sh: xcresult attachment export failed" >&2; cat "$tmp_dir/export.log" >&2; exit 2
fi

xcode_version=$(xcodebuild -version | tr '\n' ';' | sed 's/;$//')
if ! node --input-type=module - "$export_dir" "$staging" "$plan" "$run_at" "$app_name" "$destination" "$xcode_version" "$locale" "$timezone" "$appearance" "$dynamic_type" <<'NODE'
import fs from 'node:fs'
import path from 'node:path'

const [exportDir, reportDir, planPath, runAt, app, destination, xcodeVersion, locale, timezone, appearance, dynamicType] = process.argv.slice(2)
const manifest = JSON.parse(fs.readFileSync(path.join(exportDir, 'manifest.json'), 'utf8'))
const attachments = manifest.flatMap((test) => test.attachments || [])
const named = (name) => {
  const extension = path.extname(name)
  const stem = path.basename(name, extension)
  const matches = attachments.filter((item) => item.suggestedHumanReadableName === name ||
    (item.suggestedHumanReadableName.startsWith(`${stem}_`) && item.suggestedHumanReadableName.endsWith(extension)))
  if (matches.length !== 1) throw new Error(`expected one attachment ${name}; found ${matches.length}`)
  return matches[0]
}
const plan = JSON.parse(fs.readFileSync(planPath, 'utf8'))
const journeyRecords = []
let expectedCount = 0
let expectedBytes = 0
for (const entry of plan) {
  const safe = entry.name.replace(/[^A-Za-z0-9._-]/g, '-').replace(/^-+|-+$/g, '') || 'step'
  const stepAttachment = named(`sim-steps__${safe}.json`)
  const stepPath = path.join(exportDir, stepAttachment.exportedFileName)
  const result = JSON.parse(fs.readFileSync(stepPath, 'utf8'))
  if (result.name !== entry.name || result.journey_hash !== entry.hash) throw new Error(`journey result identity mismatch: ${entry.name}`)
  expectedCount += 1
  expectedBytes += fs.statSync(stepPath).size
  for (const expected of result.attachments) {
    const attachment = named(expected.name)
    const source = path.join(exportDir, attachment.exportedFileName)
    const bytes = fs.statSync(source).size
    if (bytes !== expected.bytes) throw new Error(`attachment byte mismatch for ${expected.name}: ${bytes} != ${expected.bytes}`)
    expectedCount += 1
    expectedBytes += expected.bytes
    const destinationDir = expected.kind === 'shot' ? 'shots' : 'diagnostics'
    fs.copyFileSync(source, path.join(reportDir, destinationDir, path.basename(expected.name)))
  }
  let receipt
  if (entry.checkpoint_only) {
    if (!result.checkpoint_reached) throw new Error(`checkpoint receipt was not earned: ${entry.name}`)
    const checkpoint = result.steps.find((step) => step.id === result.steps.at(-1)?.id)
    receipt = {
      journey_hash: entry.hash,
      status: 'created',
      checkpoint_step_id: checkpoint.id,
      fixture_evidence: result.fixture_evidence,
      recorded_at: runAt,
    }
    fs.writeFileSync(entry.receipt_path, `${JSON.stringify(receipt, null, 2)}\n`)
  } else {
    receipt = JSON.parse(fs.readFileSync(entry.receipt_path, 'utf8'))
    if (receipt.journey_hash !== entry.hash) throw new Error(`stored receipt hash mismatch: ${entry.name}`)
    receipt = { ...receipt, status: 'present' }
  }
  journeyRecords.push({
    name: result.name,
    journey_hash: result.journey_hash,
    fixture_evidence: result.fixture_evidence,
    evidence_receipt: receipt,
    attachment_count: result.attachments.length + 1,
    attachment_bytes: result.attachments.reduce((sum, row) => sum + row.bytes, fs.statSync(stepPath).size),
    steps: result.steps,
  })
}
const actualBytes = attachments.reduce((sum, item) => sum + fs.statSync(path.join(exportDir, item.exportedFileName)).size, 0)
if (attachments.length !== expectedCount || actualBytes !== expectedBytes) {
  throw new Error(`manifest accounting mismatch: count ${attachments.length}/${expectedCount}, bytes ${actualBytes}/${expectedBytes}`)
}
const journeys = journeyRecords.map((journey) => ({
  name: journey.name,
  steps: journey.steps.map((step) => {
    const expectation = typeof step.expectation === 'string' ? step.expectation : ''
    const shaped = { ...step, expectation, payload: null }
    if (!step.ok) return { ...shaped, verdict: 'fail', note: step.note || 'The step action failed mechanically.' }
    if (!expectation.trim()) return { ...shaped, verdict: 'observed', note: step.note || 'Observed only.' }
    return { ...shaped, verdict: 'ungraded', note: step.note || 'Vision grading disabled by SIM_GRADE=0.' }
  }),
}))
const steps = journeys.flatMap((journey) => journey.steps)
const totals = {
  steps: steps.length,
  ok: steps.filter((step) => step.ok).length,
  pass: 0,
  concern: 0,
  fail: steps.filter((step) => step.verdict === 'fail').length,
  ungraded: steps.filter((step) => step.verdict === 'ungraded').length,
}
const report = {
  app,
  run_at: runAt,
  base_url: `simulator://${destination}`,
  platform: 'ios',
  metadata: { locale, timezone, appearance, dynamic_type: dynamicType, destination, xcode_version: xcodeVersion },
  journeys,
  totals,
  proposals: [],
  recommendations: [],
}
fs.writeFileSync(path.join(reportDir, 'steps.json'), `${JSON.stringify({ version: 2, attachment_count: expectedCount, attachment_bytes: expectedBytes, journeys: journeyRecords }, null, 2)}\n`)
fs.writeFileSync(path.join(reportDir, 'report.json'), `${JSON.stringify(report, null, 2)}\n`)
console.log(`Attachment manifest: verified count=${expectedCount} bytes=${expectedBytes}`)
NODE
then
  echo "run.sh: exported attachment verification failed" >&2
  exit 2
fi

max_shot_bytes=${SIM_MAX_SHOT_BYTES:-209715200}
case "$max_shot_bytes" in ''|*[!0-9]*) echo "run.sh: SIM_MAX_SHOT_BYTES must be an integer" >&2; exit 2 ;; esac
shot_bytes=$(find "$staging/shots" -type f -exec stat -f %z {} \; | awk '{total += $1} END {print total + 0}')
if [ "$shot_bytes" -gt "$max_shot_bytes" ]; then
  echo "run.sh: screenshot bytes $shot_bytes exceed SIM_MAX_SHOT_BYTES=$max_shot_bytes" >&2
  exit 2
fi

if [ "$grade" -eq 1 ]; then
  SIM_GRADE=1 SIM_GRADE_BUDGET_S=${SIM_GRADE_BUDGET_S:-600} SIM_GRADE_CACHE_DIR="$report_root/.cache" \
    node "$SIM_DIR/grade.mjs" "$staging" "$persona_path" "$persona_manifest" || {
      echo "run.sh: grader failed mechanically" >&2; exit 2;
    }
fi

checker=
if [ -n "$harness_root" ] && [ -x "$harness_root/checks/sim-report.sh" ]; then checker="$harness_root/checks/sim-report.sh"; fi
if [ -z "$checker" ]; then echo "run.sh: checks/sim-report.sh is required for atomic publication" >&2; exit 2; fi
checker_args=(--strict)
[ -f "$persona_manifest" ] && checker_args+=(--persona "$persona_manifest")
if ! /bin/bash "$checker" "${checker_args[@]}" "$staging"; then
  echo "run.sh: strict report validation failed; staging and result bundle retained" >&2
  exit 2
fi

rm -rf "$result_bundle" "$export_dir"
mv "$staging" "$final_report" || exit 2
node -e '
  const fs=require("fs"), path=require("path"), r=JSON.parse(fs.readFileSync(path.join(process.argv[1],"report.json")));
  const observed=r.journeys.flatMap(j=>j.steps).filter(s=>s.verdict==="observed").length, t=r.totals;
  console.log(`TOTAL steps=${t.steps} ok=${t.ok} pass=${t.pass} concern=${t.concern} fail=${t.fail} ungraded=${t.ungraded} observed=${observed}`);
  console.log(`Report: ${path.join(process.argv[1],"report.json")}`);
' "$final_report"

exit 0
