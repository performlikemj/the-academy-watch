#!/usr/bin/env bash
set -euo pipefail

umask 077

usage() {
  cat <<'EOF'
Usage:
  migrate-app-to-env.sh --app <name> --src-rg <rg> --dst-rg <rg> \
    --dst-env <env-name> [--dst-registry <name>] [--image <ref>] \
    [--new-name <name>] [--apply] [--bind-domains] [--flip-dns] \
    [--cf-zone <zone>] [--origin-cert <pem> --origin-key <key>]

Copies an Azure Container App into an existing Container Apps environment.
The default is a read-only dry run: Azure is queried and the transformed app
specification is printed with secret and literal environment values redacted.

Required:
  --app NAME             Source Container App name.
  --src-rg RG            Source resource group.
  --dst-rg RG            Destination resource group.
  --dst-env NAME         Existing destination Container Apps environment.

Optional:
  --dst-registry NAME    Destination ACR. Defaults to the source app's first ACR.
  --image REF            Exact destination image reference. Without it, replace
                         the source image's registry host with the destination ACR.
  --new-name NAME        Destination app name. Defaults to the source name.
  --apply                Permit writes. Without this flag, no Azure or DNS writes.
  --bind-domains         Add every source custom hostname to the destination app
                         and bind a certificate. Intended for the public web app.
  --flip-dns             Point source custom hostnames at the destination FQDN,
                         verify HTTP 200 plus body identity, and print rollback.
  --cf-zone ZONE         Cloudflare zone containing the custom hostnames.
  --origin-cert PEM      Cloudflare Origin CA certificate in PEM format.
  --origin-key KEY       Private key matching --origin-cert. The key is never read
                         to stdout. Both origin flags must be supplied together.
  -h, --help             Show this help.

Cloudflare automation reads CLOUDFLARE_API_TOKEN from
~/.config/bwmj/cloudflare.env. The file is parsed, never sourced or printed. If
the file or token is absent, exact TXT/CNAME records are printed for a human.

Every invocation re-exports the source. Creation, role grants, hostname binding,
certificate upload, and DNS changes are idempotent. This tool never deletes an
app, resource group, DNS record, certificate, or role assignment.
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

shell_quote() {
  printf '%q' "$1"
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

APP=""
SRC_RG=""
DST_RG=""
DST_ENV=""
DST_REGISTRY=""
IMAGE_OVERRIDE=""
DST_APP=""
APPLY=false
BIND_DOMAINS=false
FLIP_DNS=false
CF_ZONE=""
ORIGIN_CERT=""
ORIGIN_KEY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --app)
      [[ $# -ge 2 ]] || die "--app requires a value"
      APP="$2"
      shift 2
      ;;
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
    --image)
      [[ $# -ge 2 ]] || die "--image requires a value"
      IMAGE_OVERRIDE="$2"
      shift 2
      ;;
    --new-name)
      [[ $# -ge 2 ]] || die "--new-name requires a value"
      DST_APP="$2"
      shift 2
      ;;
    --apply)
      APPLY=true
      shift
      ;;
    --bind-domains)
      BIND_DOMAINS=true
      shift
      ;;
    --flip-dns)
      FLIP_DNS=true
      shift
      ;;
    --cf-zone)
      [[ $# -ge 2 ]] || die "--cf-zone requires a value"
      CF_ZONE="$2"
      shift 2
      ;;
    --origin-cert)
      [[ $# -ge 2 ]] || die "--origin-cert requires a value"
      ORIGIN_CERT="$2"
      shift 2
      ;;
    --origin-key)
      [[ $# -ge 2 ]] || die "--origin-key requires a value"
      ORIGIN_KEY="$2"
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

[[ -n "$APP" ]] || die "--app is required"
[[ -n "$SRC_RG" ]] || die "--src-rg is required"
[[ -n "$DST_RG" ]] || die "--dst-rg is required"
[[ -n "$DST_ENV" ]] || die "--dst-env is required"
DST_APP="${DST_APP:-$APP}"

if [[ -n "$ORIGIN_CERT" || -n "$ORIGIN_KEY" ]]; then
  [[ -n "$ORIGIN_CERT" && -n "$ORIGIN_KEY" ]] || \
    die "--origin-cert and --origin-key must be supplied together"
  $BIND_DOMAINS || die "Origin certificate flags require --bind-domains"
  [[ -r "$ORIGIN_CERT" ]] || die "Origin certificate is not readable: $ORIGIN_CERT"
  [[ -r "$ORIGIN_KEY" ]] || die "Origin private key is not readable: $ORIGIN_KEY"
fi

require_command az
require_command jq
require_command python3
if $APPLY || $FLIP_DNS; then
  require_command curl
fi
if [[ -n "$ORIGIN_CERT" ]]; then
  require_command openssl
fi

TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/aca-migrate.XXXXXX")"
trap 'rm -rf "$TMP_DIR"' EXIT

SOURCE_JSON="$TMP_DIR/source.json"
SPEC_JSON="$TMP_DIR/destination.json"
DOMAINS_FILE="$TMP_DIR/domains.txt"
DESTINATION_JSON="$TMP_DIR/destination-current.json"
NEW_BODY="$TMP_DIR/new-body"
CF_API_BASE="https://api.cloudflare.com/client/v4"
CF_TOKEN_FILE="${HOME}/.config/bwmj/cloudflare.env"
CF_API_TOKEN=""
CF_ZONE_ID=""
NEW_FQDN=""
OLD_FQDN=""
NEW_BODY_HASH=""
ORIGIN_CERT_ID=""

phase_export() {
  log ""
  log "== Phase 1: export and transform =="
  log "Reading source app '$APP' from resource group '$SRC_RG'."
  az containerapp show \
    --name "$APP" \
    --resource-group "$SRC_RG" \
    --output json > "$SOURCE_JSON"

  OLD_FQDN="$(jq -r '.properties.configuration.ingress.fqdn // empty' "$SOURCE_JSON")"
  jq -r '.properties.configuration.ingress.customDomains // [] | .[].name' \
    "$SOURCE_JSON" > "$DOMAINS_FILE"

  local plain_secret_count
  plain_secret_count="$(jq '[.properties.configuration.secrets // [] | .[] |
    select((.keyVaultUrl // "") == "")] | length' "$SOURCE_JSON")"
  if [[ "$plain_secret_count" != "0" ]]; then
    die "Source app has non-Key-Vault secrets. Move them to Key Vault references before migration; no secret values were printed."
  fi

  local destination_env_id destination_env_location destination_env_json
  destination_env_json="$TMP_DIR/destination-environment.json"
  az containerapp env show \
    --name "$DST_ENV" \
    --resource-group "$DST_RG" \
    --output json > "$destination_env_json"
  destination_env_id="$(jq -r '.id // empty' "$destination_env_json")"
  destination_env_location="$(jq -r '.location // empty' "$destination_env_json")"
  [[ -n "$destination_env_id" && -n "$destination_env_location" ]] || \
    die "Could not resolve destination environment ID and location"

  local source_registry_server
  source_registry_server="$(jq -r \
    '.properties.configuration.registries[0].server // empty' "$SOURCE_JSON")"
  if [[ -z "$DST_REGISTRY" ]]; then
    [[ -n "$source_registry_server" ]] || \
      die "--dst-registry is required when the source app has no registry entry"
    DST_REGISTRY="${source_registry_server%%.*}"
    log "Destination registry not supplied; inferred ACR '$DST_REGISTRY'."
  fi

  DST_REGISTRY_JSON="$TMP_DIR/registry.json"
  az acr show --name "$DST_REGISTRY" --output json > "$DST_REGISTRY_JSON"
  DST_REGISTRY_SERVER="$(jq -r '.loginServer // empty' "$DST_REGISTRY_JSON")"
  DST_REGISTRY_ID="$(jq -r '.id // empty' "$DST_REGISTRY_JSON")"
  [[ -n "$DST_REGISTRY_SERVER" && -n "$DST_REGISTRY_ID" ]] || \
    die "Could not resolve destination registry server and ID"

  local source_image destination_image
  source_image="$(jq -r '.properties.template.containers[0].image // empty' "$SOURCE_JSON")"
  [[ -n "$source_image" ]] || die "Source app's first container has no image"
  destination_image="$(resolve_destination_image \
    "$IMAGE_OVERRIDE" \
    "$source_image" \
    "$DST_REGISTRY_SERVER")"

  jq \
    --arg app_name "$DST_APP" \
    --arg environment_id "$destination_env_id" \
    --arg environment_location "$destination_env_location" \
    --arg registry_server "$DST_REGISTRY_SERVER" \
    --arg destination_image "$destination_image" '
      .name = $app_name
      | .location = $environment_location
      | .properties.environmentId = $environment_id
      | .properties.managedEnvironmentId = $environment_id
      | .properties.configuration.registries =
          [{"server": $registry_server, "identity": "system"}]
      | .properties.template.containers[0].image = $destination_image
      | del(.id,
            .etag,
            .systemData,
            .identity.principalId,
            .identity.tenantId,
            .properties.provisioningState,
            .properties.latestRevisionName,
            .properties.latestReadyRevisionName,
            .properties.latestRevisionFqdn,
            .properties.runningStatus,
            .properties.outboundIpAddresses,
            .properties.eventStreamEndpoint,
            .properties.customDomainVerificationId,
            .properties.configuration.ingress.fqdn,
            .properties.configuration.ingress.customDomains,
            .properties.template.revisionSuffix)
      | (.identity.userAssignedIdentities[]? |= del(.clientId, .principalId))
      | (.properties.configuration.ingress.traffic // []) |=
          map(del(.revisionName))
    ' "$SOURCE_JSON" > "$SPEC_JSON"

  log "Destination: app '$DST_APP', group '$DST_RG', environment '$DST_ENV'."
  log "Destination image: $destination_image"
  log "Transformed destination specification (secrets and literal env values redacted):"
  jq '
    if .properties.configuration.secrets then
      .properties.configuration.secrets |= map({
        name: .name,
        source: (if (.keyVaultUrl // "") != "" then "key-vault-reference" else "redacted" end),
        redacted: true
      })
    else . end
    | (.properties.configuration.registries[]? |
        select(has("username")) | .username) = "<redacted>"
    | (.properties.template.containers[]?.env[]? |
        select(has("value")) | .value) = "<redacted>"
    | (.properties.template.initContainers[]?.env[]? |
        select(has("value")) | .value) = "<redacted>"
  ' "$SPEC_JSON"
}

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

  log "Assigning '$role' to the destination app identity at scope '$scope'."
  az role assignment create \
    --assignee-object-id "$principal_id" \
    --assignee-principal-type ServicePrincipal \
    --role "$role" \
    --scope "$scope" \
    --output none
}

grant_runtime_roles() {
  local principal_id="$1"
  log "Ensuring the destination app identity can pull from '$DST_REGISTRY_SERVER'."
  ensure_role_assignment "$principal_id" "AcrPull" "$DST_REGISTRY_ID"

  local key_vault_url vault_host vault_name vault_id
  while IFS= read -r key_vault_url; do
    [[ -n "$key_vault_url" ]] || continue
    vault_host="${key_vault_url#*://}"
    vault_host="${vault_host%%/*}"
    vault_name="${vault_host%%.*}"
    [[ -n "$vault_name" ]] || die "Could not parse a Key Vault name from a secret reference"
    vault_id="$(az keyvault show --name "$vault_name" --query id --output tsv)"
    [[ -n "$vault_id" ]] || die "Could not resolve Key Vault '$vault_name'"
    log "Ensuring Key Vault reference access on '$vault_name'."
    ensure_role_assignment "$principal_id" "Key Vault Secrets User" "$vault_id"
  done < <(jq -r '
    [.properties.configuration.secrets // [] | .[] | .keyVaultUrl // empty]
    | unique[]
  ' "$SOURCE_JSON")
}

wait_for_running_app() {
  local attempt state_json ready_revision running_status
  log "Waiting for a ready revision with runningStatus=Running."
  for attempt in $(seq 1 36); do
    state_json="$(az containerapp show \
      --name "$DST_APP" \
      --resource-group "$DST_RG" \
      --output json)"
    ready_revision="$(jq -r '.properties.latestReadyRevisionName // empty' <<< "$state_json")"
    running_status="$(jq -r '.properties.runningStatus // empty' <<< "$state_json")"
    if [[ -n "$ready_revision" && "$running_status" == "Running" ]]; then
      log "Ready revision: $ready_revision"
      return
    fi
    sleep 5
  done
  die "Destination app did not reach a ready Running state within 3 minutes"
}

probe_new_fqdn() {
  local attempt http_code
  NEW_FQDN="$(az containerapp show \
    --name "$DST_APP" \
    --resource-group "$DST_RG" \
    --query properties.configuration.ingress.fqdn \
    --output tsv)"
  [[ -n "$NEW_FQDN" ]] || die "Destination app has no ingress FQDN"

  log "Checking https://${NEW_FQDN}/ (cold starts may take two minutes)."
  for attempt in $(seq 1 24); do
    if http_code="$(curl \
      --silent \
      --show-error \
      --max-time 20 \
      --output "$NEW_BODY" \
      --write-out '%{http_code}' \
      "https://${NEW_FQDN}/")"; then
      if [[ "$http_code" =~ ^[23][0-9][0-9]$ ]]; then
        log "Destination FQDN returned HTTP $http_code."
        if [[ "$http_code" == "200" ]]; then
          NEW_BODY_HASH="$(python3 -c \
            'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' \
            "$NEW_BODY")"
        fi
        return
      fi
    fi
    sleep 5
  done
  die "Destination FQDN did not return HTTP 200-399 within 2 minutes"
}

phase_create() {
  log ""
  log "== Phase 2: create and verify =="
  if ! $APPLY; then
    log "DRY-RUN: would create '$DST_APP' from the transformed JSON specification."
    log "DRY-RUN: would grant its system identity AcrPull on '$DST_REGISTRY'."
    if jq -e '.properties.configuration.secrets // [] | any(.keyVaultUrl)' \
      "$SOURCE_JSON" >/dev/null; then
      log "DRY-RUN: would grant Key Vault Secrets User on every referenced vault."
    fi
    log "DRY-RUN: would wait for a ready Running revision and probe its FQDN."
    return
  fi

  if az containerapp show \
    --name "$DST_APP" \
    --resource-group "$DST_RG" \
    --output json > "$DESTINATION_JSON" 2>/dev/null; then
    log "Destination app '$DST_APP' already exists; creation is unchanged."
  else
    log "Creating destination app '$DST_APP'."
    if ! az containerapp create \
      --name "$DST_APP" \
      --resource-group "$DST_RG" \
      --yaml "$SPEC_JSON" \
      --output json > "$DESTINATION_JSON"; then
      if az containerapp show \
        --name "$DST_APP" \
        --resource-group "$DST_RG" \
        --output json > "$DESTINATION_JSON" 2>/dev/null; then
        log "Creation reported an incomplete revision; the app resource exists, so runtime roles will be reconciled before readiness is retried."
      else
        die "Destination app creation failed before a resource was created"
      fi
    fi
  fi

  local principal_id latest_revision
  principal_id="$(az containerapp show \
    --name "$DST_APP" \
    --resource-group "$DST_RG" \
    --query identity.principalId \
    --output tsv)"
  [[ -n "$principal_id" ]] || die "Destination app has no system-assigned identity"
  grant_runtime_roles "$principal_id"

  if jq -e '.properties.configuration.secrets // [] | any(.keyVaultUrl)' \
    "$SOURCE_JSON" >/dev/null; then
    latest_revision="$(az containerapp show \
      --name "$DST_APP" \
      --resource-group "$DST_RG" \
      --query properties.latestRevisionName \
      --output tsv)"
    if [[ -n "$latest_revision" ]]; then
      log "Restarting the initial revision after Key Vault role reconciliation."
      az containerapp revision restart \
        --name "$DST_APP" \
        --resource-group "$DST_RG" \
        --revision "$latest_revision" \
        --output none
    fi
  fi

  wait_for_running_app
  probe_new_fqdn
}

load_cloudflare_token() {
  if [[ ! -r "$CF_TOKEN_FILE" ]]; then
    return
  fi
  local line value
  while IFS= read -r line; do
    line="${line#export }"
    case "$line" in
      CLOUDFLARE_API_TOKEN=*)
        value="${line#CLOUDFLARE_API_TOKEN=}"
        value="${value%$'\r'}"
        if [[ "$value" == \"*\" && "$value" == *\" ]]; then
          value="${value:1:${#value}-2}"
        elif [[ "$value" == \'*\' && "$value" == *\' ]]; then
          value="${value:1:${#value}-2}"
        fi
        CF_API_TOKEN="$value"
        ;;
    esac
  done < "$CF_TOKEN_FILE"
}

cf_get() {
  local url="$1"
  local output_file="$2"
  curl \
    --silent \
    --show-error \
    --fail \
    --header "Authorization: Bearer ${CF_API_TOKEN}" \
    --header 'Content-Type: application/json' \
    --output "$output_file" \
    "$url"
  jq -e '.success == true' "$output_file" >/dev/null || \
    die "Cloudflare API request failed (response suppressed)"
}

cf_write() {
  local method="$1"
  local url="$2"
  local payload="$3"
  local output_file="$4"
  curl \
    --silent \
    --show-error \
    --fail \
    --request "$method" \
    --header "Authorization: Bearer ${CF_API_TOKEN}" \
    --header 'Content-Type: application/json' \
    --data "$payload" \
    --output "$output_file" \
    "$url"
  jq -e '.success == true' "$output_file" >/dev/null || \
    die "Cloudflare API write failed (response suppressed)"
}

resolve_cloudflare_zone() {
  [[ -n "$CF_ZONE" ]] || \
    die "--cf-zone is required when Cloudflare automation is available"
  local encoded_zone response
  encoded_zone="$(jq -rn --arg value "$CF_ZONE" '$value | @uri')"
  response="$TMP_DIR/cf-zone.json"
  cf_get "${CF_API_BASE}/zones?name=${encoded_zone}&status=active" "$response"
  CF_ZONE_ID="$(jq -r \
    'if (.result | length) == 1 then .result[0].id else empty end' "$response")"
  [[ -n "$CF_ZONE_ID" ]] || \
    die "Cloudflare zone '$CF_ZONE' was not resolved uniquely"
}

ensure_cf_txt_record() {
  local record_name="$1"
  local content="$2"
  local encoded_name response count record_id payload write_response
  encoded_name="$(jq -rn --arg value "$record_name" '$value | @uri')"
  response="$TMP_DIR/cf-txt-query.json"
  cf_get "${CF_API_BASE}/zones/${CF_ZONE_ID}/dns_records?type=TXT&name=${encoded_name}" \
    "$response"
  count="$(jq '.result | length' "$response")"
  [[ "$count" -le 1 ]] || \
    die "Multiple TXT records named '$record_name' exist; refusing an ambiguous update"
  payload="$(jq -nc \
    --arg name "$record_name" \
    --arg content "$content" \
    '{type:"TXT", name:$name, content:$content, ttl:1}')"
  write_response="$TMP_DIR/cf-txt-write.json"
  if [[ "$count" == "1" ]]; then
    if jq -e --arg content "$content" \
      '.result[0].content == $content' "$response" >/dev/null; then
      log "Cloudflare TXT '$record_name' is already correct."
      return
    fi
    record_id="$(jq -r '.result[0].id' "$response")"
    log "Updating Cloudflare TXT '$record_name'."
    cf_write PUT \
      "${CF_API_BASE}/zones/${CF_ZONE_ID}/dns_records/${record_id}" \
      "$payload" "$write_response"
  else
    log "Creating Cloudflare TXT '$record_name'."
    cf_write POST \
      "${CF_API_BASE}/zones/${CF_ZONE_ID}/dns_records" \
      "$payload" "$write_response"
  fi
}

ensure_cf_cname_record() {
  local record_name="$1"
  local content="$2"
  local encoded_name response count record_id payload write_response
  encoded_name="$(jq -rn --arg value "$record_name" '$value | @uri')"
  response="$TMP_DIR/cf-address-query.json"
  cf_get "${CF_API_BASE}/zones/${CF_ZONE_ID}/dns_records?name=${encoded_name}" \
    "$response"
  count="$(jq '[.result[] | select(.type == "A" or .type == "CNAME")] | length' \
    "$response")"
  [[ "$count" -le 1 ]] || \
    die "Multiple A/CNAME records named '$record_name' exist; refusing an ambiguous update"
  payload="$(jq -nc \
    --arg name "$record_name" \
    --arg content "$content" \
    '{type:"CNAME", name:$name, content:$content, ttl:1, proxied:true}')"
  write_response="$TMP_DIR/cf-address-write.json"
  if [[ "$count" == "1" ]]; then
    if jq -e --arg content "$content" '
      [.result[] | select(.type == "A" or .type == "CNAME")][0]
      | .type == "CNAME" and .content == $content and .proxied == true
    ' "$response" >/dev/null; then
      log "Cloudflare CNAME '$record_name' is already correct and proxied."
      return
    fi
    record_id="$(jq -r \
      '[.result[] | select(.type == "A" or .type == "CNAME")][0].id' \
      "$response")"
    log "Updating Cloudflare '$record_name' to a proxied CNAME."
    cf_write PUT \
      "${CF_API_BASE}/zones/${CF_ZONE_ID}/dns_records/${record_id}" \
      "$payload" "$write_response"
  else
    log "Creating proxied Cloudflare CNAME '$record_name'."
    cf_write POST \
      "${CF_API_BASE}/zones/${CF_ZONE_ID}/dns_records" \
      "$payload" "$write_response"
  fi
}

prepare_origin_certificate() {
  local certificate_name existing_count pfx_file upload_json
  certificate_name="origin-${DST_APP//[^a-zA-Z0-9-]/-}"
  certificate_name="${certificate_name:0:50}"
  upload_json="$TMP_DIR/origin-certificate.json"
  az containerapp env certificate list \
    --name "$DST_ENV" \
    --resource-group "$DST_RG" \
    --output json > "$upload_json"
  existing_count="$(jq --arg name "$certificate_name" \
    '[.[] | select(.name == $name)] | length' "$upload_json")"
  if [[ "$existing_count" != "0" ]]; then
    ORIGIN_CERT_ID="$(jq -r --arg name "$certificate_name" \
      '[.[] | select(.name == $name)][0].id' "$upload_json")"
    log "Environment certificate '$certificate_name' already exists."
    return
  fi

  pfx_file="$TMP_DIR/origin.pfx"
  log "Packaging the supplied Origin CA PEM and key without printing either."
  openssl pkcs12 -export \
    -out "$pfx_file" \
    -in "$ORIGIN_CERT" \
    -inkey "$ORIGIN_KEY" \
    -passout pass: >/dev/null 2>&1 || \
      die "Could not package the supplied Origin CA certificate and key"
  log "Uploading environment certificate '$certificate_name'."
  az containerapp env certificate upload \
    --name "$DST_ENV" \
    --resource-group "$DST_RG" \
    --certificate-name "$certificate_name" \
    --certificate-file "$pfx_file" \
    --password "" \
    --output json > "$upload_json"
  ORIGIN_CERT_ID="$(jq -r '.id // empty' "$upload_json")"
  [[ -n "$ORIGIN_CERT_ID" ]] || die "Certificate upload returned no resource ID"
}

phase_domains() {
  if ! $BIND_DOMAINS; then
    return
  fi
  log ""
  log "== Phase 3: custom domains =="
  if [[ ! -s "$DOMAINS_FILE" ]]; then
    log "Source app has no custom domains; nothing to bind."
    return
  fi

  local verification_id hostname txt_name destination_json certificate_id
  verification_id="$(az containerapp env show \
    --name "$DST_ENV" \
    --resource-group "$DST_RG" \
    --query properties.customDomainConfiguration.customDomainVerificationId \
    --output tsv)"
  if [[ -z "$verification_id" ]]; then
    verification_id="$(az containerapp env show \
      --name "$DST_ENV" \
      --resource-group "$DST_RG" \
      --query properties.customDomainVerificationId \
      --output tsv)"
  fi
  [[ -n "$verification_id" ]] || \
    die "Could not resolve the destination environment domain verification ID"

  load_cloudflare_token
  if [[ -n "$CF_API_TOKEN" ]] && $APPLY; then
    resolve_cloudflare_zone
  fi

  while IFS= read -r hostname; do
    [[ -n "$hostname" ]] || continue
    txt_name="asuid.${hostname}"
    if [[ -n "$CF_API_TOKEN" ]] && $APPLY; then
      ensure_cf_txt_record "$txt_name" "$verification_id"
    else
      log "DNS REQUIRED: TXT ${txt_name} = ${verification_id} (DNS only)"
    fi
  done < "$DOMAINS_FILE"

  if ! $APPLY; then
    if [[ -n "$ORIGIN_CERT" ]]; then
      log "DRY-RUN: would package/upload the Origin CA certificate and bind it to each hostname."
    else
      log "DRY-RUN: would request an Azure managed certificate for each hostname using TXT validation."
      log "NOTE: issuance can fail while a hostname still routes to the source environment."
    fi
    return
  fi

  if [[ -n "$ORIGIN_CERT" ]]; then
    prepare_origin_certificate
  fi

  while IFS= read -r hostname; do
    [[ -n "$hostname" ]] || continue
    destination_json="$(az containerapp show \
      --name "$DST_APP" \
      --resource-group "$DST_RG" \
      --output json)"
    if jq -e --arg hostname "$hostname" '
      .properties.configuration.ingress.customDomains // []
      | any(.name == $hostname)
    ' <<< "$destination_json" >/dev/null; then
      log "Hostname '$hostname' is already added to '$DST_APP'."
    else
      log "Adding hostname '$hostname' to '$DST_APP'."
      az containerapp hostname add \
        --name "$DST_APP" \
        --resource-group "$DST_RG" \
        --hostname "$hostname" \
        --output none
    fi

    destination_json="$(az containerapp show \
      --name "$DST_APP" \
      --resource-group "$DST_RG" \
      --output json)"
    certificate_id="$(jq -r --arg hostname "$hostname" '
      [.properties.configuration.ingress.customDomains // [] |
        .[] | select(.name == $hostname)][0].certificateId // empty
    ' <<< "$destination_json")"
    if [[ -n "$certificate_id" ]]; then
      log "Hostname '$hostname' already has a certificate binding."
      continue
    fi

    if [[ -n "$ORIGIN_CERT_ID" ]]; then
      log "Binding the uploaded Origin CA certificate to '$hostname'."
      az containerapp hostname bind \
        --name "$DST_APP" \
        --resource-group "$DST_RG" \
        --environment "$DST_ENV" \
        --hostname "$hostname" \
        --certificate "$ORIGIN_CERT_ID" \
        --output none
    else
      log "Requesting an Azure managed certificate for '$hostname' with TXT validation."
      az containerapp hostname bind \
        --name "$DST_APP" \
        --resource-group "$DST_RG" \
        --environment "$DST_ENV" \
        --hostname "$hostname" \
        --validation-method TXT \
        --output none
    fi
  done < "$DOMAINS_FILE"
}

verify_cutover() {
  local hostname="$1"
  local attempt http_code domain_body domain_hash
  domain_body="$TMP_DIR/domain-body"
  [[ -n "$NEW_BODY_HASH" ]] || \
    die "The destination FQDN did not provide an HTTP 200 body baseline; refusing unverifiable DNS cut-over"

  log "Verifying https://${hostname}/ returns HTTP 200 from the destination app."
  for attempt in $(seq 1 24); do
    if http_code="$(curl \
      --silent \
      --show-error \
      --location \
      --max-redirs 5 \
      --max-time 20 \
      --output "$domain_body" \
      --write-out '%{http_code}' \
      "https://${hostname}/")"; then
      if [[ "$http_code" == "200" ]]; then
        domain_hash="$(python3 -c \
          'import hashlib,sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' \
          "$domain_body")"
        if [[ "$domain_hash" == "$NEW_BODY_HASH" ]]; then
          log "Verified '$hostname': HTTP 200 and body hash matches the destination FQDN."
          return
        fi
      fi
    fi
    sleep 5
  done
  die "'$hostname' did not return HTTP 200 with the destination body within 2 minutes"
}

print_rollback_and_deletion() {
  local hostname
  log ""
  log "Rollback (do not remove the source app during the seven-day soak):"
  while IFS= read -r hostname; do
    [[ -n "$hostname" ]] || continue
    log "  CNAME ${hostname} -> ${OLD_FQDN} (proxied: true)"
  done < "$DOMAINS_FILE"
  printf 'After 7 days, remove only the old app with: az containerapp delete --name '
  shell_quote "$APP"
  printf ' --resource-group '
  shell_quote "$SRC_RG"
  printf ' --yes\n'
}

phase_flip_dns() {
  if ! $FLIP_DNS; then
    return
  fi
  log ""
  log "== Phase 4: DNS cut-over and verification =="
  [[ -s "$DOMAINS_FILE" ]] || die "Source app has no custom domains to flip"
  [[ -n "$OLD_FQDN" ]] || die "Source app has no ingress FQDN for rollback"

  if ! $APPLY; then
    local dry_hostname dry_target
    dry_target="${NEW_FQDN:-<new-app-fqdn-after-create>}"
    while IFS= read -r dry_hostname; do
      [[ -n "$dry_hostname" ]] || continue
      log "DNS CUT-OVER: CNAME ${dry_hostname} -> ${dry_target} (proxied: true)"
    done < "$DOMAINS_FILE"
    log "DRY-RUN: would require HTTP 200 and a destination body-hash match within 2 minutes."
    print_rollback_and_deletion
    return
  fi

  [[ -n "$NEW_FQDN" ]] || probe_new_fqdn
  [[ -n "$NEW_BODY_HASH" ]] || \
    die "Destination FQDN must return HTTP 200 before DNS can be changed"
  load_cloudflare_token
  local hostname
  if [[ -n "$CF_API_TOKEN" ]]; then
    resolve_cloudflare_zone
    while IFS= read -r hostname; do
      [[ -n "$hostname" ]] || continue
      ensure_cf_cname_record "$hostname" "$NEW_FQDN"
    done < "$DOMAINS_FILE"
  else
    while IFS= read -r hostname; do
      [[ -n "$hostname" ]] || continue
      log "DNS REQUIRED: CNAME ${hostname} -> ${NEW_FQDN} (proxied: true)"
    done < "$DOMAINS_FILE"
    log "No Cloudflare token was found; no DNS write was made. Verifying the human-managed records now."
  fi

  print_rollback_and_deletion
  while IFS= read -r hostname; do
    [[ -n "$hostname" ]] || continue
    verify_cutover "$hostname"
  done < "$DOMAINS_FILE"
}

phase_export
phase_create
phase_domains
phase_flip_dns

if ! $APPLY; then
  log ""
  log "DRY-RUN complete. No Azure or DNS writes were performed."
elif ! $FLIP_DNS; then
  log ""
  log "Apply phase complete. DNS was not changed."
fi
