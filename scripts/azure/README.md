# The Academy Watch shared Container Apps room migration

This runbook moves the Flask backend and its eight Container Apps Jobs from
`cae-loan-army` in `rg-loan-army-westus2` to the shared Consumption environment
`nbhd-env-westus2` in `rg-nbhd-prod`. The source resources stay intact during a
seven-day soak. The migration scripts default to dry-run, never delete resources,
and refuse plain (non-Key-Vault-reference) secrets.

Run these commands from an authenticated operator shell after this branch is
reviewed and merged. Do not paste tokens, secret values, certificates, or private
keys into logs, issues, or terminal transcripts.

## 1. Set coordinates and put the backend image in `acrbwmj`

Changing `ACR_NAME` and completing one deploy is a prerequisite. Do not change
`AZURE_RG` or `ACA_ENV` yet.

```bash
export REPO="performlikemj/loanarmy"
export SRC_RG="rg-loan-army-westus2"
export DST_RG="rg-nbhd-prod"
export SRC_ENV="cae-loan-army"
export DST_ENV="nbhd-env-westus2"
export DST_ACR="acrbwmj"
export APP="ca-loan-army-backend"
export KEY_VAULT_NAME="kv-loan-army"
export GH_IDENTITY_NAME="id-gh-loanarmy"
export API_DOMAIN="api.theacademywatch.com"
export CF_ZONE="theacademywatch.com"

az account show --query '{subscription:id,tenant:tenantId}' --output table
az containerapp env show \
  --name "$DST_ENV" \
  --resource-group "$DST_RG" \
  --query '{id:id,location:location,defaultDomain:properties.defaultDomain}' \
  --output table
az acr show \
  --name "$DST_ACR" \
  --query '{id:id,loginServer:loginServer,adminUserEnabled:adminUserEnabled}' \
  --output table

gh variable set ACR_NAME --repo "$REPO" --body "$DST_ACR"
gh workflow run deploy.yml --repo "$REPO" --ref main -f skip_security_checks=false
gh run list --repo "$REPO" --workflow deploy.yml --limit 1
gh run watch --repo "$REPO"
```

Read the newest exact backend tag from the destination repository, verify it,
and freeze the image reference used for this migration:

```bash
export BACKEND_TAG="$(az acr repository show-tags \
  --name "$DST_ACR" \
  --repository loanarmy/backend \
  --orderby time_desc \
  --top 1 \
  --output tsv)"
test -n "$BACKEND_TAG"
export BACKEND_IMAGE="acrbwmj.azurecr.io/loanarmy/backend:${BACKEND_TAG}"

az acr repository show \
  --name "$DST_ACR" \
  --image "loanarmy/backend:${BACKEND_TAG}" \
  --query '{image:name,tag:tag,digest:digest}' \
  --output table
printf 'Migration image: %s\n' "$BACKEND_IMAGE"
```

The current workflow uses the mutable tag `prod`; record the digest shown above
in the change ticket so the exact cut-over artifact remains auditable.

## 2. Stage the stable API hostname before changing the frontend

The permanent frontend API-base contract is
`https://api.theacademywatch.com/api`. The `/api` suffix is required because the
frontend appends route paths directly to `VITE_API_BASE`. Establish and test the
hostname before dispatching any workflow that builds the frontend with
`API_BASE_URL`.

Azure cannot attach a hostname to a Container App that does not exist. Therefore,
stage the DNS values now, create the destination app in step 3, and execute the
hostname commands immediately afterward. Do not perform the frontend/repository
variable cut-over until this section passes.

After the destination app exists, read the target environment verification ID and
new app FQDN:

```bash
export API_ASUID="$(az containerapp env show \
  --name "$DST_ENV" \
  --resource-group "$DST_RG" \
  --query properties.customDomainConfiguration.customDomainVerificationId \
  --output tsv)"
export NEW_APP_FQDN="$(az containerapp show \
  --name "$APP" \
  --resource-group "$DST_RG" \
  --query properties.configuration.ingress.fqdn \
  --output tsv)"
test -n "$API_ASUID"
test -n "$NEW_APP_FQDN"

printf 'Cloudflare TXT:   asuid.api -> %s\n' "$API_ASUID"
printf 'Cloudflare CNAME: api -> %s\n' "$NEW_APP_FQDN"
```

In the `theacademywatch.com` Cloudflare zone, create or update:

- TXT `asuid.api` with the exact value printed above.
- CNAME `api` to the exact new Container App FQDN.

If `~/.config/bwmj/cloudflare.env` contains an orchestrator token, it may be used
to upsert those records without printing or sourcing the token file. Otherwise,
use the two records printed above in the Cloudflare dashboard. Keep the CNAME
DNS-only while Azure validates it, then add and bind the hostname:

```bash
az containerapp hostname add \
  --name "$APP" \
  --resource-group "$DST_RG" \
  --hostname "$API_DOMAIN" \
  --output none

az containerapp hostname bind \
  --name "$APP" \
  --resource-group "$DST_RG" \
  --environment "$DST_ENV" \
  --hostname "$API_DOMAIN" \
  --validation-method CNAME \
  --output none
```

Using CNAME validation for this subdomain avoids the HTTP-validation routing gap.
After the managed certificate is ready, turn the Cloudflare proxy on for `api`
and set zone SSL/TLS encryption mode to **Full (strict)**.

The Static Web App custom domain has previously returned 405 for POSTs even when
GETs worked. Do not infer API health from a GET. This unauthenticated validation
POST has a known application-level 400 response for `{}`; any application 4xx is
acceptable, but 405 is not:

```bash
export API_POST_STATUS="$(curl \
  --silent \
  --show-error \
  --output /tmp/academy-watch-api-post.json \
  --write-out '%{http_code}' \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{}' \
  "https://${API_DOMAIN}/api/community-takes/submit")"
printf 'API POST status: %s\n' "$API_POST_STATUS"
test "$API_POST_STATUS" != "405"
test "$API_POST_STATUS" -ge 400
test "$API_POST_STATUS" -lt 500
```

If `CORS_ALLOW_ORIGINS` is unset, the backend currently defaults to `*`. Confirm
the intended production CORS policy separately; the migration preserves the
existing environment value exactly.

## 3. Migrate the backend, then finish the API hostname

The generic app migration tool is copied verbatim from the shared-room toolkit.
It rewrites the environment and registry, preserves runtime configuration and Key
Vault references, creates a system-identity destination app, and grants its
identity `AcrPull` plus `Key Vault Secrets User` on referenced vaults.

Dry-run first:

```bash
scripts/azure/migrate-app-to-env.sh \
  --app "$APP" \
  --src-rg "$SRC_RG" \
  --dst-rg "$DST_RG" \
  --dst-env "$DST_ENV" \
  --dst-registry "$DST_ACR" \
  --image "$BACKEND_IMAGE"
```

Review port `5001`, external ingress, `0.5` CPU / `1Gi`, min/max replicas `0/2`,
the exact image, all environment variables, probes, and Key Vault references.
Then apply:

```bash
scripts/azure/migrate-app-to-env.sh \
  --app "$APP" \
  --src-rg "$SRC_RG" \
  --dst-rg "$DST_RG" \
  --dst-env "$DST_ENV" \
  --dst-registry "$DST_ACR" \
  --image "$BACKEND_IMAGE" \
  --apply
```

Return immediately to step 2, create the Cloudflare records, run `hostname add`
and `hostname bind`, and pass the POST check before continuing.

Now grant the GitHub OIDC deploy identity access only to the new app resource.
Do not grant it over `rg-nbhd-prod`:

```bash
export GH_IDENTITY_PRINCIPAL_ID="$(az identity show \
  --name "$GH_IDENTITY_NAME" \
  --resource-group "$SRC_RG" \
  --query principalId \
  --output tsv)"
export NEW_APP_ID="$(az containerapp show \
  --name "$APP" \
  --resource-group "$DST_RG" \
  --query id \
  --output tsv)"
test -n "$GH_IDENTITY_PRINCIPAL_ID"
test -n "$NEW_APP_ID"

az role assignment create \
  --assignee-object-id "$GH_IDENTITY_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Container Apps Contributor" \
  --scope "$NEW_APP_ID" \
  --output none
```

An existing equivalent assignment may return `RoleAssignmentExists`; verify it
rather than broadening scope.

## 4. Migrate all eight jobs, then pause source schedules

Use an explicit list so an unrelated future job in the source resource group is
not migrated accidentally:

```bash
JOB_ARGS=(
  --job job-sync-fixtures
  --job job-transfer-heal
  --job job-video-maintenance
  --job job-seed-teams
  --job job-reclass-journeys
  --job job-status-refresh
  --job job-data-fix
  --job job-full-rebuild
)
```

Dry-run all transforms:

```bash
scripts/azure/migrate-jobs-to-env.sh \
  --src-rg "$SRC_RG" \
  --dst-rg "$DST_RG" \
  --dst-env "$DST_ENV" \
  --dst-registry "$DST_ACR" \
  --image "$BACKEND_IMAGE" \
  "${JOB_ARGS[@]}"
```

Review trigger types and crons, especially `job-sync-fixtures` (`0 5 * * *`),
`job-transfer-heal` (`0 3 * * *`), and `job-video-maintenance`
(`0 3 * * *`); also review replica timeout, CPU/memory, command/args, environment,
and the three Key Vault references on `job-video-maintenance`. Apply without
pausing sources. Use a controlled window that does not cross 03:00 or 05:00 UTC,
then complete the verification and pause command below in the same window to
avoid duplicate scheduled executions:

```bash
scripts/azure/migrate-jobs-to-env.sh \
  --src-rg "$SRC_RG" \
  --dst-rg "$DST_RG" \
  --dst-env "$DST_ENV" \
  --dst-registry "$DST_ACR" \
  --image "$BACKEND_IMAGE" \
  "${JOB_ARGS[@]}" \
  --apply
```

Grant the deploy identity `Container Apps Jobs Contributor` on each exact new
job resource ID, not on the destination resource group:

```bash
for JOB_NAME in \
  job-sync-fixtures \
  job-transfer-heal \
  job-video-maintenance \
  job-seed-teams \
  job-reclass-journeys \
  job-status-refresh \
  job-data-fix \
  job-full-rebuild; do
  export NEW_JOB_ID="$(az containerapp job show \
    --name "$JOB_NAME" \
    --resource-group "$DST_RG" \
    --query id \
    --output tsv)"
  az role assignment create \
    --assignee-object-id "$GH_IDENTITY_PRINCIPAL_ID" \
    --assignee-principal-type ServicePrincipal \
    --role "Container Apps Jobs Contributor" \
    --scope "$NEW_JOB_ID" \
    --output none
done
```

Inspect all destination jobs before pausing anything:

```bash
az containerapp job list \
  --resource-group "$DST_RG" \
  --query "[?starts_with(name, 'job-')].{name:name,trigger:properties.configuration.triggerType,cron:properties.configuration.scheduleTriggerConfig.cronExpression,image:properties.template.containers[0].image}" \
  --output table
```

Persist the rollback report outside the repository and rerun with the pause flag:

```bash
mkdir -p "${HOME}/.config/bwmj"
export JOB_REPORT="${HOME}/.config/bwmj/loanarmy-job-migration-report.json"

scripts/azure/migrate-jobs-to-env.sh \
  --src-rg "$SRC_RG" \
  --dst-rg "$DST_RG" \
  --dst-env "$DST_ENV" \
  --dst-registry "$DST_ACR" \
  --image "$BACKEND_IMAGE" \
  "${JOB_ARGS[@]}" \
  --apply \
  --pause-source \
  --report "$JOB_REPORT"

jq '{sourceResourceGroup,scheduledSourceJobs}' "$JOB_REPORT"
```

The exact pause command issued for each scheduled source job is:

```bash
az containerapp job update \
  --name "<scheduled-job>" \
  --resource-group "rg-loan-army-westus2" \
  --cron-expression "0 0 31 2 *" \
  --output none
```

February 31 never occurs, so that cron cannot fire. `az containerapp job stop`
is deliberately not used: it stops current executions but does not disable the
next scheduled execution. Manual and event-triggered source jobs remain intact.

## 5. Build the frontend against the stable API domain

Both frontend workflows use repository variable `API_BASE_URL`, defaulting to
`https://api.theacademywatch.com/api`, and refuse to build if `VITE_API_BASE` is
empty. The variable must include the `/api` suffix. `src/lib/track.js` appends
`/events`, so this value correctly produces
`https://api.theacademywatch.com/api/events`. Set the variable explicitly after
the API POST test passes:

```bash
gh variable set API_BASE_URL \
  --repo "$REPO" \
  --body "https://api.theacademywatch.com/api"

gh workflow run deploy-frontend.yml --repo "$REPO" --ref main
gh run list --repo "$REPO" --workflow deploy-frontend.yml --limit 1
gh run watch --repo "$REPO"
```

## 6. Flip repository routing and dispatch

Only after the app, jobs, API domain, runtime RBAC, and deploy-identity RBAC are
ready, point GitHub Actions at the shared room:

```bash
gh variable set AZURE_RG --repo "$REPO" --body "$DST_RG"
gh variable set ACA_ENV --repo "$REPO" --body "$DST_ENV"

gh workflow run deploy.yml --repo "$REPO" --ref main -f skip_security_checks=false
gh run list --repo "$REPO" --workflow deploy.yml --limit 1
gh run watch --repo "$REPO"

curl -sS --fail https://api.theacademywatch.com/api/seasons \
  | jq -e '.seasons | type == "array"'
```

Confirm repository variables:

```bash
gh variable list --repo "$REPO"
```

`scheduled-scaling.yml` already reads `AZURE_RG` and `ACA_APP`; it contains no
hardcoded old resource group or environment. Dispatch it and verify it now updates
the new app:

```bash
gh workflow run scheduled-scaling.yml \
  --repo "$REPO" \
  --ref main \
  -f mode=off-peak
gh run list --repo "$REPO" --workflow scheduled-scaling.yml --limit 1
gh run watch --repo "$REPO"

az containerapp show \
  --name "$APP" \
  --resource-group "$DST_RG" \
  --query 'properties.template.scale.{minReplicas:minReplicas,maxReplicas:maxReplicas}' \
  --output table
```

## 7. Verify, soak for seven days, and roll back if needed

Verification checklist:

```bash
curl --silent --show-error --fail --location https://theacademywatch.com/ >/dev/null
curl --silent --show-error --fail --location "https://${API_DOMAIN}/api/seasons" >/dev/null

curl \
  --silent \
  --show-error \
  --output /tmp/academy-watch-api-post.json \
  --write-out 'POST HTTP %{http_code}\n' \
  --request POST \
  --header 'Content-Type: application/json' \
  --data '{}' \
  "https://${API_DOMAIN}/api/community-takes/submit"

az containerapp show \
  --name "$APP" \
  --resource-group "$DST_RG" \
  --query '{fqdn:properties.configuration.ingress.fqdn,state:properties.runningStatus,ready:properties.latestReadyRevisionName}' \
  --output table

az containerapp job execution list \
  --name job-sync-fixtures \
  --resource-group "$DST_RG" \
  --output table
```

After the next `0 5 * * *` occurrence, require a successful
`job-sync-fixtures` execution in the new resource group. Also verify the two 03:00
UTC jobs on their next occurrence, application logs, Key Vault reference health,
site navigation, authentication, and CORS from `https://theacademywatch.com`.

Keep the source app, source jobs, source environment, and rollback report for at
least seven full days.

### Rollback

First prevent duplicate schedules by pausing destination scheduled jobs, then
restore source crons from the report:

```bash
jq -r '.scheduledSourceJobs[].job' "$JOB_REPORT" |
while IFS= read -r JOB_NAME; do
  az containerapp job update \
    --name "$JOB_NAME" \
    --resource-group "$DST_RG" \
    --cron-expression "0 0 31 2 *" \
    --output none
done

jq -r '.scheduledSourceJobs[] | [.job,.originalCron] | @tsv' "$JOB_REPORT" |
while IFS=$'\t' read -r JOB_NAME ORIGINAL_CRON; do
  az containerapp job update \
    --name "$JOB_NAME" \
    --resource-group "$SRC_RG" \
    --cron-expression "$ORIGINAL_CRON" \
    --output none
done
```

Set Cloudflare CNAME `api` back to the old source app FQDN (keep it proxied), then
verify POST is not 405. Restore repository routing and dispatch:

```bash
export OLD_APP_FQDN="$(az containerapp show \
  --name "$APP" \
  --resource-group "$SRC_RG" \
  --query properties.configuration.ingress.fqdn \
  --output tsv)"
printf 'ROLLBACK DNS: CNAME api -> %s (proxied)\n' "$OLD_APP_FQDN"

gh variable set AZURE_RG --repo "$REPO" --body "$SRC_RG"
gh variable set ACA_ENV --repo "$REPO" --body "$SRC_ENV"
gh workflow run deploy.yml --repo "$REPO" --ref main -f skip_security_checks=false
```

The stable `API_BASE_URL` remains `https://api.theacademywatch.com/api` during
rollback; only its DNS origin changes.

### Final old-resource-group deletion (operator only; never run by scripts)

Deleting `rg-loan-army-westus2` is currently unsafe while `kv-loan-army` remains
there and the migrated resources reference it. The Static Web App's resource
group must also be confirmed. Before deletion, move or replace every retained
resource, update references and RBAC, and prove the old group is disposable:

```bash
az resource list \
  --resource-group "$SRC_RG" \
  --query '[].{name:name,type:type,id:id}' \
  --output table

az containerapp show \
  --name "$APP" \
  --resource-group "$DST_RG" \
  --query 'properties.configuration.secrets[].keyVaultUrl' \
  --output tsv

az staticwebapp show \
  --name swa-goonloan \
  --query '{id:id,resourceGroup:resourceGroup,defaultHostname:defaultHostname}' \
  --output table
```

Only after `kv-loan-army`, `swa-goonloan`, and every other retained resource are
outside the deletion boundary, and after an additional explicit human review,
the final destructive command is:

```bash
az group delete \
  --name "rg-loan-army-westus2" \
  --yes \
  --no-wait
```

Neither migration script invokes this command or deletes any Azure resource.
