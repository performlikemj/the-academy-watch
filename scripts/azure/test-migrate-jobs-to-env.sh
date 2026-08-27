#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MIGRATION_SCRIPT="${SCRIPT_DIR}/migrate-jobs-to-env.sh"
FIXTURE_DIR="${SCRIPT_DIR}/test-fixtures"
SCHEDULED_FIXTURE="${FIXTURE_DIR}/containerjob-scheduled-export.json"
MANUAL_FIXTURE="${FIXTURE_DIR}/containerjob-manual-export.json"
PLAIN_FIXTURE="${FIXTURE_DIR}/containerjob-plain-secret-export.json"
ENVIRONMENT_FIXTURE="${FIXTURE_DIR}/destination-environment.json"
REGISTRY_FIXTURE="${FIXTURE_DIR}/destination-registry.json"
EXPECTED_ENVIRONMENT_ID="/subscriptions/mock/resourceGroups/rg-nbhd-prod/providers/Microsoft.App/managedEnvironments/nbhd-env-westus2"
EXPECTED_IMAGE="acrbwmj.azurecr.io/loanarmy/backend:release-20260827"

fail() {
  printf 'FAIL: %s\n' "$1" >&2
  exit 1
}

pass() {
  printf 'PASS: %s\n' "$1"
}

extract_spec() {
  awk '
    /^{$/ { capturing = 1 }
    capturing { print }
    capturing && /^}$/ { exit }
  '
}

run_dry_run() {
  (
    az() {
      if [[ "$1" == "containerapp" && "$2" == "env" ]]; then
        command cat "$ENVIRONMENT_FIXTURE"
      elif [[ "$1" == "acr" && "$2" == "show" ]]; then
        command cat "$REGISTRY_FIXTURE"
      elif [[ "$1" == "containerapp" && "$2" == "job" && "$3" == "show" ]]; then
        command cat "$SCHEDULED_FIXTURE"
      else
        printf 'Unexpected mock az call: %s\n' "$*" >&2
        return 1
      fi
    }

    set -- \
      --src-rg rg-loan-army-westus2 \
      --dst-rg rg-nbhd-prod \
      --dst-env nbhd-env-westus2 \
      --dst-registry acrbwmj \
      --job job-video-maintenance \
      --image "$EXPECTED_IMAGE" \
      --pause-source
    source "$MIGRATION_SCRIPT"
  )
}

dry_output="$(run_dry_run)"
dry_spec="$(extract_spec <<< "$dry_output")"

if jq -e \
  --arg image "$EXPECTED_IMAGE" \
  --arg environment_id "$EXPECTED_ENVIRONMENT_ID" '
    .identity == {"type":"SystemAssigned"}
    and .properties.environmentId == $environment_id
    and .properties.managedEnvironmentId == $environment_id
    and .properties.configuration.registries ==
      [{"server":"acrbwmj.azurecr.io","identity":"system"}]
    and .properties.template.containers[0].image == $image
    and .properties.configuration.scheduleTriggerConfig.cronExpression == "0 3 * * *"
    and .properties.configuration.replicaTimeout == 1800
    and .properties.template.containers[0].resources == {"cpu":0.5,"memory":"1Gi"}
    and (.properties.configuration.secrets | length) == 2
    and (has("id") | not)
    and (.properties | has("provisioningState") | not)
  ' <<< "$dry_spec" >/dev/null; then
  pass "scheduled job transform preserves runtime configuration and drops read-only fields"
else
  fail "scheduled job transform was not correct"
fi

if grep -Fq '"value": "<redacted>"' <<< "$dry_output" && \
   ! grep -Fq '"value": "scheduled"' <<< "$dry_output"; then
  pass "dry-run redacts literal environment values"
else
  fail "dry-run exposed or failed to redact a literal environment value"
fi

if grep -Fq "DRY-RUN: would pause 1 scheduled source job(s) with cron '0 0 31 2 *'." <<< "$dry_output" && \
   grep -Fq '"originalCron": "0 3 * * *"' <<< "$dry_output"; then
  pass "dry-run reports the pause cron and rollback cron"
else
  fail "dry-run pause report was missing"
fi

test_tmp="$(mktemp -d "${TMPDIR:-/tmp}/job-migrate-test.XXXXXX")"
trap 'rm -rf "$test_tmp"' EXIT
call_log="$test_tmp/az-calls.log"
report_path="$test_tmp/rollback.json"

(
  az() {
    printf '%s\n' "$*" >> "$call_log"
    if [[ "$1" == "containerapp" && "$2" == "env" ]]; then
      command cat "$ENVIRONMENT_FIXTURE"
    elif [[ "$1" == "acr" && "$2" == "show" ]]; then
      command cat "$REGISTRY_FIXTURE"
    elif [[ "$1" == "containerapp" && "$2" == "job" && "$3" == "list" ]]; then
      printf '[{"name":"job-video-maintenance"},{"name":"job-seed-teams"}]\n'
    elif [[ "$1" == "containerapp" && "$2" == "job" && "$3" == "show" ]]; then
      if [[ "$*" == *"--resource-group rg-loan-army-westus2"* ]]; then
        if [[ "$*" == *"--name job-video-maintenance"* ]]; then
          command cat "$SCHEDULED_FIXTURE"
        else
          command cat "$MANUAL_FIXTURE"
        fi
      elif [[ "$*" == *"--query identity.principalId"* ]]; then
        printf 'destination-principal\n'
      else
        return 1
      fi
    elif [[ "$1" == "containerapp" && "$2" == "job" && "$3" == "create" ]]; then
      return 0
    elif [[ "$1" == "containerapp" && "$2" == "job" && "$3" == "update" ]]; then
      return 0
    elif [[ "$1" == "role" && "$2" == "assignment" && "$3" == "list" ]]; then
      printf '[]\n'
    elif [[ "$1" == "role" && "$2" == "assignment" && "$3" == "create" ]]; then
      return 0
    elif [[ "$1" == "keyvault" && "$2" == "show" ]]; then
      printf '/subscriptions/mock/resourceGroups/rg-loan-army-westus2/providers/Microsoft.KeyVault/vaults/kv-loan-army\n'
    else
      printf 'Unexpected mock az call: %s\n' "$*" >&2
      return 1
    fi
  }

  set -- \
    --src-rg rg-loan-army-westus2 \
    --dst-rg rg-nbhd-prod \
    --dst-env nbhd-env-westus2 \
    --dst-registry acrbwmj \
    --apply \
    --pause-source \
    --report "$report_path"
  source "$MIGRATION_SCRIPT"
) >/dev/null

create_count="$(grep -c '^containerapp job create ' "$call_log")"
pause_count="$(grep -c '^containerapp job update ' "$call_log")"
if [[ "$create_count" == "2" && "$pause_count" == "1" ]] && \
   grep -Fq 'containerapp job update --name job-video-maintenance --resource-group rg-loan-army-westus2 --cron-expression 0 0 31 2 * --output none' "$call_log"; then
  pass "apply creates every listed job and pauses only the scheduled source"
else
  fail "apply create/pause calls were incorrect"
fi

if jq -e '
  .sourceResourceGroup == "rg-loan-army-westus2"
  and (.scheduledSourceJobs | length) == 1
  and .scheduledSourceJobs[0].job == "job-video-maintenance"
  and .scheduledSourceJobs[0].originalCron == "0 3 * * *"
  and .scheduledSourceJobs[0].pausedCron == "0 0 31 2 *"
  and (.scheduledSourceJobs[0].rollbackCommand | contains("--cron-expression"))
  and (.scheduledSourceJobs[0].rollbackCommand | contains("0 3 * * *"))
' "$report_path" >/dev/null; then
  pass "apply persists a complete source-schedule rollback report"
else
  fail "rollback report was incorrect"
fi

unsafe_output="$test_tmp/unsafe-output.txt"
if (
  az() {
    if [[ "$1" == "containerapp" && "$2" == "env" ]]; then
      command cat "$ENVIRONMENT_FIXTURE"
    elif [[ "$1" == "acr" && "$2" == "show" ]]; then
      command cat "$REGISTRY_FIXTURE"
    elif [[ "$1" == "containerapp" && "$2" == "job" && "$3" == "show" ]]; then
      command cat "$PLAIN_FIXTURE"
    else
      return 1
    fi
  }
  set -- \
    --src-rg rg-loan-army-westus2 \
    --dst-rg rg-nbhd-prod \
    --dst-env nbhd-env-westus2 \
    --dst-registry acrbwmj \
    --job job-unsafe
  source "$MIGRATION_SCRIPT"
) >"$unsafe_output" 2>&1; then
  fail "plain secret fixture did not abort"
fi

if grep -Fq 'has non-Key-Vault secrets' "$unsafe_output" && \
   ! grep -Fq 'must-not-be-printed' "$unsafe_output"; then
  pass "plain secrets abort without printing their values"
else
  fail "plain secret abort leaked or omitted the safe error"
fi

printf 'All migrate-jobs-to-env mock tests passed.\n'
