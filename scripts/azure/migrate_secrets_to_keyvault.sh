#!/usr/bin/env bash
set -euo pipefail

# Migrate plain Azure Container App secrets to Azure Key Vault references without
# exposing secret values. Dry-run is the default; --apply performs the migration.
#
# --rollback note: there is no automatic rollback mode. After migration, the plain
# values remain recoverable from Key Vault (never from the app). An operator with
# appropriate Key Vault access can deliberately restore an app secret if required.

usage() {
  cat <<'EOF'
Usage:
  migrate_secrets_to_keyvault.sh --app <name> --rg <rg> --vault <kv-name> [--jobs] [--apply] [--restart]

Options:
  --app NAME      Container App to inspect and migrate.
  --rg RG         Resource group containing the app and optional jobs.
  --vault NAME    RBAC-enabled Key Vault in the active Azure subscription.
  --jobs          Also migrate every Container Apps Job in the resource group.
  --apply         Write Key Vault secrets and replace plain app/job secrets.
  --restart       After a successful --apply, roll a new app revision.
  -h, --help      Show this help.

The default is a names-only dry run. Secret values are never printed.
EOF
}

die() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 1
}

need() {
  command -v "$1" >/dev/null 2>&1 || die "Missing required command: $1"
}

APP_NAME=""
RESOURCE_GROUP=""
VAULT_NAME=""
INCLUDE_JOBS=0
APPLY=0
RESTART=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)
      [[ $# -ge 2 ]] || die "--app requires a value"
      APP_NAME="$2"
      shift 2
      ;;
    --rg)
      [[ $# -ge 2 ]] || die "--rg requires a value"
      RESOURCE_GROUP="$2"
      shift 2
      ;;
    --vault)
      [[ $# -ge 2 ]] || die "--vault requires a value"
      VAULT_NAME="$2"
      shift 2
      ;;
    --jobs)
      INCLUDE_JOBS=1
      shift
      ;;
    --apply)
      APPLY=1
      shift
      ;;
    --restart)
      RESTART=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

[[ -n "$APP_NAME" ]] || die "--app is required"
[[ -n "$RESOURCE_GROUP" ]] || die "--rg is required"
[[ -n "$VAULT_NAME" ]] || die "--vault is required"
[[ "$RESTART" -eq 0 || "$APPLY" -eq 1 ]] || die "--restart requires --apply"

need az
need jq

show_resource() {
  local kind="$1"
  local name="$2"

  if [[ "$kind" == "app" ]]; then
    az containerapp show --name "$name" --resource-group "$RESOURCE_GROUP" --output json
  else
    az containerapp job show --name "$name" --resource-group "$RESOURCE_GROUP" --output json
  fi
}

list_secret_values() {
  local kind="$1"
  local name="$2"

  if [[ "$kind" == "app" ]]; then
    az containerapp secret list \
      --name "$name" \
      --resource-group "$RESOURCE_GROUP" \
      --show-values \
      --output json
  else
    az containerapp job secret list \
      --name "$name" \
      --resource-group "$RESOURCE_GROUP" \
      --show-values \
      --output json
  fi
}

assign_system_identity() {
  local kind="$1"
  local name="$2"

  if [[ "$kind" == "app" ]]; then
    az containerapp identity assign \
      --name "$name" \
      --resource-group "$RESOURCE_GROUP" \
      --system-assigned \
      --output none
  else
    az containerapp job identity assign \
      --name "$name" \
      --resource-group "$RESOURCE_GROUP" \
      --system-assigned \
      --output none
  fi
}

set_secret_reference() {
  local kind="$1"
  local name="$2"
  local secret_name="$3"
  local secret_url="$4"
  local identity_ref="$5"
  local reference

  reference="${secret_name}=keyvaultref:${secret_url},identityref:${identity_ref}"
  if [[ "$kind" == "app" ]]; then
    az containerapp secret set \
      --name "$name" \
      --resource-group "$RESOURCE_GROUP" \
      --secrets "$reference" \
      --output none
  else
    az containerapp job secret set \
      --name "$name" \
      --resource-group "$RESOURCE_GROUP" \
      --secrets "$reference" \
      --output none
  fi
}

resolve_reference_identity() {
  local resource_json="$1"
  local identities
  local identity_count

  identities="$(jq -r '
    [.properties.configuration.secrets[]?
      | select((.keyVaultUrl // "") != "")
      | (.identity // "system")]
    | unique[]
  ' <<<"$resource_json")"
  identity_count="$(jq -r '
    [.properties.configuration.secrets[]?
      | select((.keyVaultUrl // "") != "")
      | (.identity // "system")]
    | unique
    | length
  ' <<<"$resource_json")"

  if [[ "$identity_count" -eq 0 ]]; then
    printf '%s\n' "system"
  elif [[ "$identity_count" -eq 1 ]]; then
    printf '%s\n' "$identities"
  else
    die "Existing Key Vault references use multiple identities; choose one before migrating"
  fi
}

ensure_vault_role() {
  local kind="$1"
  local resource_name="$2"
  local identity_ref="$3"
  local principal_id

  if [[ "$identity_ref" == "system" || "$identity_ref" == "System" ]]; then
    assign_system_identity "$kind" "$resource_name"
    principal_id="$(show_resource "$kind" "$resource_name" | jq -er '.identity.principalId')"
    identity_ref="system"
  else
    principal_id="$(az identity show --ids "$identity_ref" --query principalId --output tsv)"
    [[ -n "$principal_id" ]] || die "Could not resolve managed identity: $identity_ref"
  fi

  printf '  identity: ensuring Key Vault Secrets User on vault\n'
  az role assignment create \
    --assignee-object-id "$principal_id" \
    --assignee-principal-type ServicePrincipal \
    --role "Key Vault Secrets User" \
    --scope "$VAULT_ID" \
    --output none
}

migrate_plain_secret() {
  local kind="$1"
  local resource_name="$2"
  local secret_name="$3"
  local identity_ref="$4"
  local vault_secret_name="${resource_name}-${secret_name}"
  local secret_value
  local secret_url

  [[ "$vault_secret_name" =~ ^[0-9A-Za-z-]+$ ]] || \
    die "Key Vault secret name is invalid: $vault_secret_name"
  [[ "${#vault_secret_name}" -le 127 ]] || \
    die "Key Vault secret name exceeds 127 characters: $vault_secret_name"

  printf '  %-40s plain  -> migrate as %s\n' "$secret_name" "$vault_secret_name"

  # Keep the value only in memory. The producing command is piped directly through
  # jq, command output is captured, and neither the value nor JSON is printed.
  if ! IFS= read -r -d '' secret_value < <(
    list_secret_values "$kind" "$resource_name" |
      jq -jer --arg secret_name "$secret_name" '
        [.[] | select(.name == $secret_name)][0].value
        // error("plain secret value was not returned")
      ' || exit 1
    printf '\0'
  ); then
    die "Could not retrieve the value for secret: $secret_name"
  fi

  az keyvault secret set \
    --vault-name "$VAULT_NAME" \
    --name "$vault_secret_name" \
    --value "$secret_value" \
    --only-show-errors \
    --output none
  unset secret_value

  # Use the versionless URI so a later Key Vault rotation is picked up without
  # rewriting the Container Apps secret reference.
  secret_url="${VAULT_URI%/}/secrets/${vault_secret_name}"
  set_secret_reference "$kind" "$resource_name" "$secret_name" "$secret_url" "$identity_ref"
}

process_resource() {
  local kind="$1"
  local resource_name="$2"
  local resource_json
  local secret_rows
  local plain_count
  local identity_ref
  local secret_name
  local state

  resource_json="$(show_resource "$kind" "$resource_name")"
  jq -e '.properties.configuration.secrets // []' >/dev/null <<<"$resource_json"
  secret_rows="$(jq -r '
    (.properties.configuration.secrets // [])[]
    | [.name, (if ((.keyVaultUrl // "") != "") then "kv-ref" else "plain" end)]
    | @tsv
  ' <<<"$resource_json")"
  plain_count="$(jq -r '
    [.properties.configuration.secrets[]? | select((.keyVaultUrl // "") == "")]
    | length
  ' <<<"$resource_json")"
  identity_ref="$(resolve_reference_identity "$resource_json")"

  printf '\n%s: %s\n' "$kind" "$resource_name"
  if [[ -z "$secret_rows" ]]; then
    printf '  (no secrets)\n'
    return
  fi

  if [[ "$APPLY" -eq 1 && "$plain_count" -gt 0 ]]; then
    ensure_vault_role "$kind" "$resource_name" "$identity_ref"
  fi

  while IFS=$'\t' read -r secret_name state; do
    [[ -n "$secret_name" ]] || continue
    if [[ "$state" == "kv-ref" ]]; then
      printf '  %-40s kv-ref -> skip\n' "$secret_name"
    elif [[ "$APPLY" -eq 1 ]]; then
      migrate_plain_secret "$kind" "$resource_name" "$secret_name" "$identity_ref"
    else
      printf '  %-40s plain  -> would migrate as %s-%s\n' \
        "$secret_name" "$resource_name" "$secret_name"
    fi
  done <<<"$secret_rows"
}

verify_resource() {
  local kind="$1"
  local resource_name="$2"
  local resource_json
  local plain_count

  resource_json="$(show_resource "$kind" "$resource_name")"
  plain_count="$(jq -r '
    [.properties.configuration.secrets[]? | select((.keyVaultUrl // "") == "")]
    | length
  ' <<<"$resource_json")"

  jq -r --arg kind "$kind" --arg resource "$resource_name" '
    (.properties.configuration.secrets // [])[]
    | [$kind, $resource, .name, (if ((.keyVaultUrl // "") != "") then "kv-ref" else "plain" end)]
    | @tsv
  ' <<<"$resource_json"

  [[ "$plain_count" -eq 0 ]] || die "$kind $resource_name still has $plain_count plain secret(s)"
}

ACTIVE_SUBSCRIPTION_ID="$(az account show --query id --output tsv)"
[[ -n "$ACTIVE_SUBSCRIPTION_ID" ]] || die "No active Azure subscription"

VAULT_JSON="$(az keyvault show --name "$VAULT_NAME" --output json)"
VAULT_ID="$(jq -er '.id' <<<"$VAULT_JSON")"
VAULT_URI="$(jq -er '.properties.vaultUri' <<<"$VAULT_JSON")"
VAULT_SUBSCRIPTION_ID="$(jq -er '.id | split("/")[2]' <<<"$VAULT_JSON")"
VAULT_RBAC="$(jq -r '.properties.enableRbacAuthorization // false' <<<"$VAULT_JSON")"
VAULT_SOFT_DELETE="$(jq -r '.properties.enableSoftDelete // false' <<<"$VAULT_JSON")"
VAULT_PURGE_PROTECTION="$(jq -r '.properties.enablePurgeProtection // false' <<<"$VAULT_JSON")"

[[ "$VAULT_SUBSCRIPTION_ID" == "$ACTIVE_SUBSCRIPTION_ID" ]] || \
  die "Vault is in subscription $VAULT_SUBSCRIPTION_ID, not active subscription $ACTIVE_SUBSCRIPTION_ID"
[[ "$VAULT_RBAC" == "true" ]] || die "Vault must use Azure RBAC authorization"
[[ "$VAULT_SOFT_DELETE" == "true" ]] || die "Vault soft-delete must be enabled"
[[ "$VAULT_PURGE_PROTECTION" == "true" ]] || die "Vault purge protection must be enabled"

RESOURCE_KINDS=("app")
RESOURCE_NAMES=("$APP_NAME")

if [[ "$INCLUDE_JOBS" -eq 1 ]]; then
  while IFS= read -r job_name; do
    [[ -n "$job_name" ]] || continue
    RESOURCE_KINDS+=("job")
    RESOURCE_NAMES+=("$job_name")
  done < <(
    az containerapp job list \
      --resource-group "$RESOURCE_GROUP" \
      --query '[].name' \
      --output tsv
  )
fi

if [[ "$APPLY" -eq 1 ]]; then
  printf 'Mode: APPLY\n'
else
  printf 'Mode: DRY-RUN (use --apply to migrate)\n'
fi

for index in "${!RESOURCE_NAMES[@]}"; do
  process_resource "${RESOURCE_KINDS[$index]}" "${RESOURCE_NAMES[$index]}"
done

if [[ "$APPLY" -eq 1 ]]; then
  printf '\nVerification (names only):\n'
  printf 'TYPE\tRESOURCE\tSECRET\tSTATE\n'
  for index in "${!RESOURCE_NAMES[@]}"; do
    verify_resource "${RESOURCE_KINDS[$index]}" "${RESOURCE_NAMES[$index]}"
  done

  revision_suffix="kv-$(date +%Y%m%d)"
  printf '\nFollow-up command to roll a new app revision:\n'
  printf '  az containerapp update --name %q --resource-group %q --revision-suffix %q\n' \
    "$APP_NAME" "$RESOURCE_GROUP" "$revision_suffix"

  if [[ "$RESTART" -eq 1 ]]; then
    printf 'Rolling the app revision because --restart was supplied.\n'
    az containerapp update \
      --name "$APP_NAME" \
      --resource-group "$RESOURCE_GROUP" \
      --revision-suffix "$revision_suffix" \
      --output none
  fi
fi
