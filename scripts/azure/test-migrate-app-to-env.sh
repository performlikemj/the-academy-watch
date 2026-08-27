#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATION_SCRIPT="${SCRIPT_DIR}/migrate-app-to-env.sh"
FIXTURE_DIR="${SCRIPT_DIR}/test-fixtures"
SOURCE_FIXTURE="${FIXTURE_DIR}/containerapp-export.json"
ENVIRONMENT_FIXTURE="${FIXTURE_DIR}/destination-environment.json"
REGISTRY_FIXTURE="${FIXTURE_DIR}/destination-registry.json"

EXPECTED_IMAGE="acrbwmj.azurecr.io/bywayofmj-web:release-20260827015903"
EXPECTED_ENVIRONMENT_ID="/subscriptions/mock/resourceGroups/rg-nbhd-prod/providers/Microsoft.App/managedEnvironments/nbhd-env-westus2"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

pass() {
  printf 'PASS: %s\n' "$1"
}

run_dry_run() {
  local include_image="$1"

  (
    az() {
      if [[ "$1" == "containerapp" && "$2" == "show" ]]; then
        command cat "$SOURCE_FIXTURE"
      elif [[ "$1" == "containerapp" && "$2" == "env" && "$3" == "show" ]]; then
        command cat "$ENVIRONMENT_FIXTURE"
      elif [[ "$1" == "acr" && "$2" == "show" ]]; then
        command cat "$REGISTRY_FIXTURE"
      else
        printf 'Unexpected mock az call: %s\n' "$*" >&2
        return 1
      fi
    }

    if [[ "$include_image" == "yes" ]]; then
      set -- \
        --app bywayofmj-web \
        --src-rg rg-bywayofmj \
        --dst-rg rg-nbhd-prod \
        --dst-env nbhd-env-westus2 \
        --dst-registry acrbwmj \
        --image "$EXPECTED_IMAGE"
    else
      set -- \
        --app bywayofmj-web \
        --src-rg rg-bywayofmj \
        --dst-rg rg-nbhd-prod \
        --dst-env nbhd-env-westus2 \
        --dst-registry acrbwmj
    fi

    source "$MIGRATION_SCRIPT"
  )
}

extract_spec() {
  awk '
    /^{$/ { capturing = 1 }
    capturing { print }
    capturing && /^}$/ { exit }
  '
}

assert_spec() {
  local spec="$1"
  local description="$2"
  local expression="$3"

  if jq -e \
    --arg image "$EXPECTED_IMAGE" \
    --arg environment_id "$EXPECTED_ENVIRONMENT_ID" \
    "$expression" <<< "$spec" >/dev/null; then
    pass "$description"
  else
    fail "$description"
  fi
}

override_output="$(run_dry_run yes)"
override_spec="$(extract_spec <<< "$override_output")"

if grep -Fq "Destination image: ${EXPECTED_IMAGE}" <<< "$override_output"; then
  pass "--image is logged verbatim, including ':release-'"
else
  fail "--image was not logged verbatim"
fi

assert_spec "$override_spec" \
  "--image reaches containers[0].image verbatim" \
  '.properties.template.containers[0].image == $image'
assert_spec "$override_spec" \
  "registries are replaced by one system-identity destination entry" \
  '.properties.configuration.registries == [{"server":"acrbwmj.azurecr.io","identity":"system"}]'
assert_spec "$override_spec" \
  "environmentId points to the destination environment" \
  '.properties.environmentId == $environment_id'
assert_spec "$override_spec" \
  "managedEnvironmentId points to the destination environment" \
  '.properties.managedEnvironmentId == $environment_id'
assert_spec "$override_spec" \
  "workloadProfileName is preserved" \
  '.properties.workloadProfileName == "Consumption"'
assert_spec "$override_spec" \
  "scale.rules remains present and null" \
  '(.properties.template.scale | has("rules")) and (.properties.template.scale.rules == null)'
assert_spec "$override_spec" \
  "scale.minReplicas remains zero" \
  '.properties.template.scale.minReplicas == 0'

rewrite_output="$(run_dry_run no)"
rewrite_spec="$(extract_spec <<< "$rewrite_output")"
assert_spec "$rewrite_spec" \
  "implicit image rewrite changes only the registry host" \
  '.properties.template.containers[0].image == $image'

printf 'All migrate-app-to-env mock tests passed.\n'
