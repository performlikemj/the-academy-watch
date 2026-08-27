#!/usr/bin/env bash
set -euo pipefail

umask 077

usage() {
  cat <<'EOF'
Usage:
  migrate-jobs-to-env.sh --src-rg <rg> --dst-rg <rg> --dst-env <env> \
    --dst-registry <acr> [--job <name> ...] [--image <ref>] [--apply] \
    [--pause-source --report <path>]

Copies Azure Container Apps Jobs into an existing Container Apps environment.
With no --job flags, every job in --src-rg is selected. The default is a
read-only dry run. This tool never deletes a job.

Required:
  --src-rg RG           Source resource group.
  --dst-rg RG           Destination resource group.
  --dst-env NAME        Existing destination Container Apps environment.
  --dst-registry NAME   Destination Azure Container Registry.

Optional:
  --job NAME            Migrate only this job. Repeat for multiple jobs.
  --image REF           Exact image for the single main container in every
                        selected job. Otherwise only the registry host changes.
  --apply               Permit Azure writes. Without it, no Azure state changes.
  --pause-source        After every destination job is created and authorized,
                        replace scheduled source crons with '0 0 31 2 *'. Manual
                        and event jobs are unchanged. Requires --apply and
                        --report for an actual pause.
  --report PATH         Write a JSON rollback report before source schedules are
                        paused. The report contains job names and crons, no secrets.
  -h, --help            Show this help.

The transform preserves trigger configuration, replica settings, containers,
resources, environment variables, and Key Vault reference metadata. It aborts
the entire run before Azure writes if any selected job contains a plain secret.
EOF
}

log() {
  printf '%s\n' "$*"
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

resolve_destination_image() {
  local image_override="$1"
  local source_image="$2"
  local destination_registry_server="$3"

  if [[ -n "$image_override" ]]; then
    printf '%s' "$image_override"
    return
  fi

  [[ "$source_image" == */* ]] || \
    die "Source image '$source_image' has no registry host to replace; pass --image explicitly"
  printf '%s/%s' "$destination_registry_server" "${source_image#*/}"
}

SRC_RG=""
DST_RG=""
DST_ENV=""
DST_REGISTRY=""
IMAGE_OVERRIDE=""
APPLY=false
PAUSE_SOURCE=false
REPORT_PATH=""
PAUSED_CRON="0 0 31 2 *"
JOBS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --src-rg)
      [[ $# -ge 2 ]] || die "--src-rg requires a value"
      SRC_RG="$2"
      shift 2
      ;;
    --dst-rg)
      [[ $# -ge 2 ]] || die "--dst-rg requires a value"
      DST_RG="$2"
      shift 2
      ;;
    --dst-env)
      [[ $# -ge 2 ]] || die "--dst-env requires a value"
      DST_ENV="$2"
      shift 2
      ;;
    --dst-registry)
      [[ $# -ge 2 ]] || die "--dst-registry requires a value"
      DST_REGISTRY="$2"
      shift 2
      ;;
    --job)
      [[ $# -ge 2 ]] || die "--job requires a value"
      JOBS+=("$2")
      shift 2
      ;;
    --image)
      [[ $# -ge 2 ]] || die "--image requires a value"
      IMAGE_OVERRIDE="$2"
      shift 2
      ;;
    --apply)
      APPLY=true
      shift
      ;;
    --pause-source)
      PAUSE_SOURCE=true
      shift
      ;;
    --report)
      [[ $# -ge 2 ]] || die "--report requires a value"
      REPORT_PATH="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1 (use --help)"
      ;;
  esac
done

[[ -n "$SRC_RG" ]] || die "--src-rg is required"
[[ -n "$DST_RG" ]] || die "--dst-rg is required"
[[ -n "$DST_ENV" ]] || die "--dst-env is required"
[[ -n "$DST_REGISTRY" ]] || die "--dst-registry is required"
[[ "$SRC_RG" != "$DST_RG" ]] || \
  die "--src-rg and --dst-rg must differ; this tool never migrates jobs in place"
if $APPLY && $PAUSE_SOURCE; then
  [[ -n "$REPORT_PATH" ]] || \
    die "--pause-source with --apply requires --report so rollback crons are persisted before changes"
fi

require_command az
require_command jq

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/aca-job-migrate.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

ENV_JSON="$TMP_DIR/destination-environment.json"
REGISTRY_JSON="$TMP_DIR/destination-registry.json"
REPORT_ITEMS="$TMP_DIR/report-items.jsonl"
: > "$REPORT_ITEMS"

az containerapp env show \
  --name "$DST_ENV" \
  --resource-group "$DST_RG" \
  --output json > "$ENV_JSON"
DESTINATION_ENV_ID="$(jq -r '.id // empty' "$ENV_JSON")"
DESTINATION_LOCATION="$(jq -r '.location // empty' "$ENV_JSON")"
[[ -n "$DESTINATION_ENV_ID" && -n "$DESTINATION_LOCATION" ]] || \
  die "Could not resolve destination environment ID and location"

az acr show --name "$DST_REGISTRY" --output json > "$REGISTRY_JSON"
DST_REGISTRY_SERVER="$(jq -r '.loginServer // empty' "$REGISTRY_JSON")"
DST_REGISTRY_ID="$(jq -r '.id // empty' "$REGISTRY_JSON")"
[[ -n "$DST_REGISTRY_SERVER" && -n "$DST_REGISTRY_ID" ]] || \
  die "Could not resolve destination registry server and ID"

if [[ "${#JOBS[@]}" -eq 0 ]]; then
  JOB_LIST_JSON="$TMP_DIR/source-jobs.json"
  az containerapp job list --resource-group "$SRC_RG" --output json > "$JOB_LIST_JSON"
  while IFS= read -r job_name; do
    [[ -n "$job_name" ]] && JOBS+=("$job_name")
  done < <(jq -r '.[].name' "$JOB_LIST_JSON")
fi
[[ "${#JOBS[@]}" -gt 0 ]] || die "No Container Apps Jobs selected"
for job_name in "${JOBS[@]}"; do
  if [[ "${#job_name}" -ge 32 || "$job_name" == *--* || "$job_name" == *- ]] || \
     ! [[ "$job_name" =~ ^[a-z][a-z0-9-]*$ ]]; then
    die "Invalid Container Apps Job name: $job_name"
  fi
done

ensure_role_assignment() {
  local principal_id="$1"
  local role="$2"
  local scope="$3"
  local existing_count

  existing_count="$(az role assignment list \
    --scope "$scope" \
    --role "$role" \
    --output json | jq --arg principal "$principal_id" \
      '[.[] | select(.principalId == $principal)] | length')"
  if [[ "$existing_count" != "0" ]]; then
    log "Role '$role' already assigned at the required scope."
    return
  fi

  az role assignment create \
    --assignee-object-id "$principal_id" \
    --assignee-principal-type ServicePrincipal \
    --role "$role" \
    --scope "$scope" \
    --output none
}

grant_runtime_roles() {
  local job_name="$1"
  local source_json="$2"
  local principal_id vault_url vault_host vault_name vault_id

  principal_id="$(az containerapp job show \
    --name "$job_name" \
    --resource-group "$DST_RG" \
    --query identity.principalId \
    --output tsv)"
  [[ -n "$principal_id" ]] || \
    die "Destination job '$job_name' has no system-assigned identity"

  log "Ensuring '$job_name' can pull from '$DST_REGISTRY_SERVER'."
  ensure_role_assignment "$principal_id" "AcrPull" "$DST_REGISTRY_ID"

  while IFS= read -r vault_url; do
    [[ -n "$vault_url" ]] || continue
    vault_host="${vault_url#*://}"
    vault_host="${vault_host%%/*}"
    vault_name="${vault_host%%.*}"
    [[ -n "$vault_name" ]] || \
      die "Could not parse a Key Vault name from '$job_name' secret metadata"
    vault_id="$(az keyvault show --name "$vault_name" --query id --output tsv)"
    [[ -n "$vault_id" ]] || die "Could not resolve Key Vault '$vault_name'"
    log "Ensuring '$job_name' has Key Vault reference access on '$vault_name'."
    ensure_role_assignment "$principal_id" "Key Vault Secrets User" "$vault_id"
  done < <(jq -r '
    [.properties.configuration.secrets // [] | .[] | .keyVaultUrl // empty]
    | unique[]
  ' "$source_json")
}

log ""
log "== Phase 1: export and transform all selected jobs =="
for job_name in "${JOBS[@]}"; do
  source_json="$TMP_DIR/${job_name}.source.json"
  spec_json="$TMP_DIR/${job_name}.destination.json"

  log "Reading source job '$job_name' from '$SRC_RG'."
  az containerapp job show \
    --name "$job_name" \
    --resource-group "$SRC_RG" \
    --output json > "$source_json"

  plain_secret_count="$(jq '[.properties.configuration.secrets // [] | .[] |
    select((.keyVaultUrl // "") == "")] | length' "$source_json")"
  if [[ "$plain_secret_count" != "0" ]]; then
    die "Source job '$job_name' has non-Key-Vault secrets. Migration aborted before Azure writes; no secret values were printed."
  fi

  container_count="$(jq '.properties.template.containers // [] | length' "$source_json")"
  [[ "$container_count" -gt 0 ]] || die "Source job '$job_name' has no containers"
  if [[ -n "$IMAGE_OVERRIDE" && "$container_count" != "1" ]]; then
    die "Source job '$job_name' has $container_count main containers; --image is only unambiguous for one"
  fi

  jq \
    --arg environment_id "$DESTINATION_ENV_ID" \
    --arg environment_location "$DESTINATION_LOCATION" \
    --arg registry_server "$DST_REGISTRY_SERVER" \
    --arg image_override "$IMAGE_OVERRIDE" '
      .location = $environment_location
      | .identity = {"type": "SystemAssigned"}
      | .properties.environmentId = $environment_id
      | .properties.managedEnvironmentId = $environment_id
      | .properties.configuration.registries =
          [{"server": $registry_server, "identity": "system"}]
      | (.properties.template.containers[]?.image) |=
          (if $image_override != "" then $image_override
           elif test("/") then ($registry_server + "/" + sub("^[^/]+/"; ""))
           else error("container image has no registry host; pass --image explicitly")
           end)
      | (.properties.template.initContainers[]?.image) |=
          (if test("/") then ($registry_server + "/" + sub("^[^/]+/"; ""))
           else error("init container image has no registry host")
           end)
      | del(.id,
            .etag,
            .systemData,
            .properties.provisioningState,
            .properties.eventStreamEndpoint,
            .properties.runningStatus,
            .properties.latestExecutionName,
            .properties.outboundIpAddresses)
    ' "$source_json" > "$spec_json"

  trigger_type="$(jq -r '.properties.configuration.triggerType // empty' "$source_json")"
  original_cron="$(jq -r '.properties.configuration.scheduleTriggerConfig.cronExpression // empty' "$source_json")"
  if [[ "$trigger_type" == "Schedule" || "$trigger_type" == "schedule" ]]; then
    [[ -n "$original_cron" ]] || \
      die "Scheduled source job '$job_name' has no cronExpression"
    jq -cn \
      --arg job "$job_name" \
      --arg original "$original_cron" \
      --arg paused "$PAUSED_CRON" \
      --arg src_rg "$SRC_RG" \
      '{job:$job,sourceResourceGroup:$src_rg,originalCron:$original,
        pausedCron:$paused,
        rollbackCommand:("az containerapp job update --name " + $job +
          " --resource-group " + $src_rg + " --cron-expression " +
          ($original|@sh) + " --output none")}' >> "$REPORT_ITEMS"
  fi

  log "Destination image(s) for '$job_name':"
  jq -r '.properties.template.containers[].image' "$spec_json"
  log "Transformed '$job_name' specification (secrets and literal env values redacted):"
  jq '
    if .properties.configuration.secrets then
      .properties.configuration.secrets |= map({
        name: .name,
        source: (if (.keyVaultUrl // "") != "" then "key-vault-reference" else "redacted" end),
        redacted: true
      })
    else . end
    | (.properties.template.containers[]?.env[]? |
        select(has("value")) | .value) = "<redacted>"
    | (.properties.template.initContainers[]?.env[]? |
        select(has("value")) | .value) = "<redacted>"
  ' "$spec_json"
done

log ""
log "== Phase 2: create destination jobs and grant runtime roles =="
if ! $APPLY; then
  for job_name in "${JOBS[@]}"; do
    log "DRY-RUN: would create destination job '$job_name' in '$DST_RG'."
    log "DRY-RUN: would grant its identity AcrPull and any required Key Vault Secrets User roles."
  done
else
  for job_name in "${JOBS[@]}"; do
    spec_json="$TMP_DIR/${job_name}.destination.json"
    source_json="$TMP_DIR/${job_name}.source.json"
    if az containerapp job show \
      --name "$job_name" \
      --resource-group "$DST_RG" \
      --output json >/dev/null 2>&1; then
      log "Destination job '$job_name' already exists; creation is unchanged."
    else
      log "Creating destination job '$job_name'."
      az containerapp job create \
        --name "$job_name" \
        --resource-group "$DST_RG" \
        --yaml "$spec_json" \
        --output none
    fi
    grant_runtime_roles "$job_name" "$source_json"
  done
fi

log ""
log "== Phase 3: source schedule pause =="
scheduled_count="$(wc -l < "$REPORT_ITEMS" | tr -d ' ')"
if ! $PAUSE_SOURCE; then
  log "Source jobs are unchanged. Pass --pause-source after destination verification to pause schedules."
elif ! $APPLY; then
  log "DRY-RUN: would pause $scheduled_count scheduled source job(s) with cron '$PAUSED_CRON'."
  jq -s '{scheduledSourceJobs:.}' "$REPORT_ITEMS"
else
  report_dir="$(dirname "$REPORT_PATH")"
  [[ -d "$report_dir" ]] || die "Report directory does not exist: $report_dir"
  jq -s \
    --arg created_at "$(date -u +'%Y-%m-%dT%H:%M:%SZ')" \
    --arg src_rg "$SRC_RG" \
    --arg dst_rg "$DST_RG" \
    --arg dst_env "$DST_ENV" \
    '{createdAt:$created_at,sourceResourceGroup:$src_rg,
      destinationResourceGroup:$dst_rg,destinationEnvironment:$dst_env,
      scheduledSourceJobs:.}' "$REPORT_ITEMS" > "$REPORT_PATH"
  log "Rollback report written before source changes: $REPORT_PATH"

  while IFS=$'\t' read -r job_name original_cron; do
    [[ -n "$job_name" ]] || continue
    log "Pausing source schedule '$job_name' (original cron: '$original_cron')."
    az containerapp job update \
      --name "$job_name" \
      --resource-group "$SRC_RG" \
      --cron-expression "$PAUSED_CRON" \
      --output none
  done < <(jq -r '[.job,.originalCron] | @tsv' "$REPORT_ITEMS")
  log "Paused $scheduled_count scheduled source job(s). Manual and event jobs were unchanged."
fi

log ""
log "Migration phase complete. No source or destination job was deleted."
