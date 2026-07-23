# Full Circle trust and privacy incident response (FC-TF3)

> **Living runbook.** Last reviewed **2026-07-23** against `origin/main` at
> `c9fdbcb`. Update this document whenever a trust route, retained-data policy,
> suppression surface, encryption key, or production containment control changes.

This is the operator playbook for the Full Circle trust stack:

- FC-B1: scout verification, content reports, and the adults-only player-claim gate;
- FC-B2/B3: the feature-gated contact rail and contract-aware club routing;
- FC-TF1: account data export and atomic account deletion; and
- FC-TF2: player takedown intake and reversible publication suppression.

For general availability incidents, start with
[Debugging](../agents/debugging.md). For an incident that may expose personal data,
endanger a player, or defeat a trust control, use this runbook first.

---

## 1. Scenario index

| Signal | Default severity | First containment | Playbook |
|---|---:|---|---|
| An account export contains another person's private data | SEV-0 | Disable backend ingress | [Export disclosure](#5-account-export-disclosure-or-scope-defect) |
| Account deletion timed out, returned 500, or appears incomplete | SEV-1; SEV-0 if the old account still works after a confirmed completion | Freeze retries and verify database outcome | [Deletion failure](#6-account-deletion-failure-unknown-outcome-or-residue) |
| A player/guardian/club requests urgent removal | SEV-1; SEV-0 for an active safety/legal threat | Activate suppression, then check every exposure class | [Urgent takedown](#7-urgent-player-takedown) |
| An actively suppressed player remains public | SEV-0 | Disable backend ingress unless a forward fix already covers the leaking surface | [Suppression leak](#8-active-suppression-leak) |
| Takedown intake or the admin queue fails to decrypt | SEV-1; SEV-0 when an urgent request cannot be contained | Restore the exact prior key material; use break-glass activation only if required | [Encryption failure](#9-suppression-encryption-or-queue-failure) |
| Harassment, fraudulent verification, a minor claim, or contract-routing bypass reaches the contact rail | SEV-0/1 | Set `CONTACT_RAIL_ENABLED=false` | [Safeguarding/contact](#10-safeguarding-report-or-contact-rail-abuse) |
| A migration or release removes a trust control | SEV-0/1 | Preserve the database; deploy a forward fix at or above the trust-floor commit | [Release/schema](#11-release-or-schema-regression) |
| A documented endpoint returns 401, 404, or 429 | Usually not an incident | Compare with the expected-state table | [Initial triage](#3-first-15-minutes) |

### Severity definitions

- **SEV-0 — critical:** active cross-account disclosure, public exposure after an
  active suppression, unauthorized contact involving a minor or immediate safety
  risk, compromised suppression evidence/key material, or a deletion reported as
  complete while the original account remains usable.
- **SEV-1 — high:** one or more trust controls are unavailable or uncertain, but no
  active disclosure or immediate safety risk is confirmed.
- **SEV-2 — limited:** isolated UX, authorization, or expected rate-limit behavior
  with the underlying control still enforcing correctly.

Assign these roles at declaration; one person may hold more than one role for a
small incident:

- **Incident commander:** owns severity, change approval, timeline, and closure.
- **Operations:** snapshots and changes Azure state.
- **Privacy/safeguarding lead:** controls sensitive evidence and notification decisions.
- **Security/credential owner:** owns credential containment, rotation, and access review
  for cross-account disclosure or key/secret compromise.
- **Engineering:** diagnoses, fixes, tests, and prepares the forward deployment.
- **Communications:** gives time-bounded internal/user updates without disclosing PII.

## 2. Non-negotiable incident rules

1. Use UTC and an incident ID on every note and change.
2. Keep names, email addresses, request statements, message bodies, bearer tokens,
   admin keys, raw exports, and ciphertext out of GitHub, chat, screenshots, and the
   PR. Store sensitive evidence only in the approved restricted incident location.
3. Record IDs and counts in the working timeline: user id, player API id, suppression
   id, report id, contact request id, deletion event id, revision, and UTC timestamps.
4. Do not blindly retry account deletion after a timeout or 500. The commit occurs
   before the response is constructed, so the client-visible outcome can be unknown.
5. Do not manually delete an account, suppression, report, contact audit event, or
   deletion event. Do not disable RLS to make incident queries easier.
6. Do not use any downgrade from `tf02` through `fc01` as containment. `tf01`/`tf02`
   refuse destructive history loss, while `fc01`–`fc03` can remove live contact,
   audit/report, claim, and club-routing state.
7. Do not rotate `SECRET_KEY` or `PLAYER_SUPPRESSION_ENCRYPTION_KEY` as a first
   response. Restore the exact prior material; plan rotation and re-encryption later.
8. Do not lift a suppression as a diagnostic step. Lifting immediately republishes
   retained player data and reactivates matching shadows.
9. `/api/health` is a process check, not a database or trust-control check. A 200 is
   necessary but not sufficient.
10. Prefer a forward code fix. A restart does not repair data, schema, key material,
    cached payloads, or a missing suppression predicate.

## 3. First 15 minutes

### Establish the production baseline

Use a restricted workstation with authenticated `az`/`gh`, `curl`, `jq`, and the approved
database client. Use task-specific shell variables; do not put secrets in shell history:

```bash
FC_SUBSCRIPTION="63ceeeac-fe3f-4bcb-b6d2-b7aa7fd6bf52"
FC_RESOURCE_GROUP="rg-loan-army-westus2"
FC_BACKEND_APP="ca-loan-army-backend"
FC_INCIDENT_ID="INC-1234" # replace with the unique incident record ID
FC_INCIDENT_SLUG="inc-1234" # unique, lowercase, and short enough for revision suffixes

az account set --subscription "$FC_SUBSCRIPTION"
if ! FC_ACTIVE_SUBSCRIPTION=$(az account show --query id -o tsv); then
  printf 'Azure account read failed; stop before any mutation\n' >&2
  exit 1
fi
if [ "$FC_ACTIVE_SUBSCRIPTION" != "$FC_SUBSCRIPTION" ]; then
  printf 'Wrong Azure subscription; stop before any mutation\n' >&2
  exit 1
fi
if ! FC_FQDN=$(az containerapp show \
    --resource-group "$FC_RESOURCE_GROUP" \
    --name "$FC_BACKEND_APP" \
    --query properties.configuration.ingress.fqdn -o tsv); then
  printf 'Container App read failed; stop before any mutation\n' >&2
  exit 1
fi
if [ -z "$FC_FQDN" ]; then
  printf 'Container App FQDN is empty; stop before any mutation\n' >&2
  exit 1
fi
FC_API="https://${FC_FQDN}"

az containerapp show \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --query '{revisionMode:properties.configuration.activeRevisionsMode,latest:properties.latestRevisionName,ready:properties.latestReadyRevisionName,image:properties.template.containers[0].image,scale:properties.template.scale,ingress:properties.configuration.ingress}' \
  -o yaml

az containerapp revision list \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --all \
  --query '[].{name:name,active:properties.active,health:properties.healthState,running:properties.runningState,created:properties.createdTime,traffic:properties.trafficWeight,image:properties.template.containers[0].image}' \
  -o table

curl --fail --silent --show-error \
  --connect-timeout 5 --max-time 20 \
  -o /dev/null -w 'health %{http_code}\n' \
  "$FC_API/api/health"
```

Capture the command output in the restricted incident record. Production uses Azure
Container Apps in **single-revision mode**; an inactive last-known-good revision may
not exist, so never assume instant revision rollback is available. The live app can
scale to zero: one bounded health timeout during cold start is not proof of a code
failure. Retry after the revision is running, then perform a DB-backed control check.

Before changing Azure state, identify and freeze overlapping deploy or scheduled-scaling
runs. The deploy workflow has no concurrency group, and both paths can create revisions.

```bash
gh run list --workflow Deploy --limit 20 \
  --json databaseId,status,conclusion,headSha,createdAt,updatedAt,url,displayTitle

gh run list --workflow "Scheduled Scaling" --limit 20 \
  --json databaseId,status,conclusion,headSha,createdAt,updatedAt,url,displayTitle

az acr manifest list-metadata \
  --registry acrloanarmy \
  --name loanarmy/backend \
  --orderby time_desc \
  --top 20 \
  --query '[].{digest:digest,tags:tags,created:createdTime,lastUpdated:lastUpdateTime}' \
  -o table
```

With incident-commander approval, cancel each overlapping in-progress run by its listed
ID, enforce a merge/deploy freeze, and disable the cron workflow before changing ACA.
The GitHub identity needs Actions write permission for cancel/disable/enable:

```bash
FC_OVERLAPPING_RUN_ID="replace-with-reviewed-run-id"
gh run cancel "$FC_OVERLAPPING_RUN_ID"
gh run watch "$FC_OVERLAPPING_RUN_ID"
gh run view "$FC_OVERLAPPING_RUN_ID" --json status,conclusion,url
gh workflow disable scheduled-scaling.yml
```

Cancellation is asynchronous. Do not mutate ACA until every overlapping run reports
`status=completed`; require `conclusion=cancelled`, or re-snapshot and reassess ACA if a
run completed successfully before cancellation won the race.

Record whether Scheduled Scaling was enabled and the pre-incident `minReplicas`. At
recovery, restore that value in a unique revision, then re-enable the workflow only after
all gates pass:

```bash
FC_PRE_MIN_REPLICAS="replace-with-snapshotted-value"
FC_REVISION_SUFFIX="${FC_INCIDENT_SLUG}-scale-restore-1"
if ! az containerapp update \
    --resource-group "$FC_RESOURCE_GROUP" \
    --name "$FC_BACKEND_APP" \
    --min-replicas "$FC_PRE_MIN_REPLICAS" \
    --revision-suffix "$FC_REVISION_SUFFIX" \
    -o none; then
  printf 'Scale restoration failed; leave Scheduled Scaling disabled\n' >&2
  exit 1
fi

FC_SCALE_REVISION="${FC_BACKEND_APP}--${FC_REVISION_SUFFIX}"
az containerapp revision show \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --revision "$FC_SCALE_REVISION" \
  --query '{name:name,active:properties.active,health:properties.healthState,running:properties.runningState}' \
  -o yaml
if ! FC_RESTORED_MIN_REPLICAS=$(az containerapp show \
    --resource-group "$FC_RESOURCE_GROUP" \
    --name "$FC_BACKEND_APP" \
    --query properties.template.scale.minReplicas -o tsv); then
  printf 'Scale read-back failed; leave Scheduled Scaling disabled\n' >&2
  exit 1
fi
if [ "$FC_RESTORED_MIN_REPLICAS" != "$FC_PRE_MIN_REPLICAS" ]; then
  printf 'Scale read-back mismatch; leave Scheduled Scaling disabled\n' >&2
  exit 1
fi
```

Wait until that exact revision is active, healthy, and running. Only after the read-back
matches may an Actions-write operator run `gh workflow enable scheduled-scaling.yml`.

Do not cancel an unrelated run or re-enable a workflow that was already disabled.

### Read logs only in the restricted incident context

```bash
az containerapp logs show \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --tail 300 \
  --format text

az containerapp logs show \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --type system \
  --tail 300
```

Relevant exact application messages include:

- `Failed to export account data`
- `Failed to delete account`
- `Failed to record player takedown request`
- `Failed to load suppression queue`
- `Failed to activate suppression`, `Failed to reject suppression`, or
  `Failed to lift suppression`
- `Failed to list content reports` or `Failed to resolve content report`
- `Failed to create contact request` or `Failed to send contact message`

Production 500 responses may contain an eight-character `reference`; correlate it
with `Error reference=<reference>` in the logs. Do not paste the surrounding payload
or stack trace into a public channel. During suppression encryption/database-bind
failures, framework SQL logging can include attempted plaintext parameters. Treat all
such logs as restricted evidence even when the API response itself is generic.

The 300-line CLI tail covers only one revision/replica/container. For a bounded older
window, query the Container App environment's Log Analytics workspace:

```bash
FC_CONTAINER_ENV="cae-loan-army"
FC_WORKSPACE_ID=$(az containerapp env show \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_CONTAINER_ENV" \
  --query properties.appLogsConfiguration.logAnalyticsConfiguration.customerId \
  -o tsv)
FC_ERROR_REFERENCE="replace-with-8-character-reference"
FC_LOG_START_UTC="replace-with-incident-start-ISO8601"
FC_LOG_END_UTC="replace-with-bounded-end-ISO8601"

az monitor log-analytics query \
  --workspace "$FC_WORKSPACE_ID" \
  --analytics-query "ContainerAppConsoleLogs_CL
    | where ContainerAppName_s == '$FC_BACKEND_APP'
    | where TimeGenerated >= todatetime('$FC_LOG_START_UTC')
    | where TimeGenerated <= todatetime('$FC_LOG_END_UTC')
    | where Log_s has 'reference=$FC_ERROR_REFERENCE'
    | project TimeGenerated, RevisionName_s, ContainerName_s, Log_s
    | order by TimeGenerated asc" \
  -o table

az monitor log-analytics query \
  --workspace "$FC_WORKSPACE_ID" \
  --analytics-query "ContainerAppSystemLogs_CL
    | where ContainerAppName_s == '$FC_BACKEND_APP'
    | where TimeGenerated >= todatetime('$FC_LOG_START_UTC')
    | where TimeGenerated <= todatetime('$FC_LOG_END_UTC')
    | project TimeGenerated, RevisionName_s, ReplicaName_s, Reason_s, Log_s
    | order by TimeGenerated asc" \
  -o table
```

Choose an explicit UTC window that begins before the earliest plausible exposure and
ends after detection; widen it for delayed user reports instead of relying on `ago(2h)`.

### Know the expected unauthenticated states

| Probe | Expected state |
|---|---|
| `GET /api/health` | 200; does not prove DB access |
| `GET /api/account/export` | 401 without a user bearer token |
| `GET /api/admin/suppressions` | 401 without both admin credentials |
| `GET /api/admin/reports` | 401 without both admin credentials |
| Admin route with a wrong API key or disallowed source IP | 403; this is an auth/configuration signal, not proof the trust route failed |
| `GET /api/contact/requests` | 404 while the contact flag is off; 401 while on but unauthenticated |
| `GET /api/showcase/mine/interest-signals` | 404 while the contact flag is off |
| Suppressed or unknown player detail | the same neutral `404 {"error":"Player not found"}` |
| Export limiter policy | `3 per hour`; fleet-wide 429 behavior is deterministic only with shared limiter storage |
| Deletion limiter policy | `5 per hour`; the same storage condition applies |

Do not smoke-test `POST /api/players/<id>/takedown-request` in production: a valid
test creates durable moderation history and correctly returns the same neutral 202 for
known and unknown players. Do not generate account deletions or a fourth export merely
to test rate limiting. Without a shared `RATELIMIT_STORAGE_URL`, production workers keep
separate in-memory counters and revision/process changes reset them.

### Prepare dual admin authentication only when needed

Admin moderation routes require a current admin bearer token **and** the API key bound to
the running ACA configuration. Admin bearer lifetime is 30 days, and an optional
`ADMIN_IP_WHITELIST` can still reject both valid credentials with 403. At the reviewed
live snapshot, the inline ACA secret is authoritative and same-named Key Vault copies are
stale. First identify the bound secret reference, then retrieve only that one value
without echo or shell tracing:

```bash
FC_ADMIN_SECRET_REF=$(az containerapp show \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --query "properties.template.containers[0].env[?name=='ADMIN_API_KEY'].secretRef | [0]" \
  -o tsv)
printf 'ADMIN_API_KEY secretRef=%s\n' "$FC_ADMIN_SECRET_REF"

read -r -s FC_ADMIN_BEARER
set +x
FC_ADMIN_API_KEY=$(az containerapp secret show \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --secret-name "$FC_ADMIN_SECRET_REF" \
  --query value -o tsv)
```

Stop if the reference is empty, retrieval is unauthorized, or the bearer came from an
unverified/expired source. Never list every ACA secret to find the key.

Use the variables only in the active shell, then clear them:

```bash
unset FC_ADMIN_BEARER FC_ADMIN_API_KEY
```

Suppression/report list responses contain decrypted private fields and reviewer identity
even if a later `jq` filter hides them. Use the read-only metadata queries in Appendix A
for ordinary triage. Open the admin queue only inside the authorized restricted privacy
session.

## 4. Containment controls

### Stop all contact-rail traffic

This is the narrowest production kill switch. It hides every `/api/contact/*` route,
including OPTIONS/wrong-method probes, and hides interest signals. First record and
normalize the configured value; absence is one of several disabled states.

```bash
if ! FC_CONTACT_ENTRY_COUNT=$(az containerapp show \
    --resource-group "$FC_RESOURCE_GROUP" \
    --name "$FC_BACKEND_APP" \
    --query "length(properties.template.containers[0].env[?name=='CONTACT_RAIL_ENABLED'])" \
    -o tsv); then
  printf 'CONTACT_RAIL_ENABLED query failed; stop and contain explicitly\n' >&2
  exit 1
fi

FC_CONTACT_REQUIRES_MUTATION=false
FC_CONTACT_RESTORE_BINDING=""
case "$FC_CONTACT_ENTRY_COUNT" in
  0)
    FC_CONTACT_CLASSIFICATION="absent-disabled"
    ;;
  1)
    FC_CONTACT_STATE_RAW=$(az containerapp show \
      --resource-group "$FC_RESOURCE_GROUP" \
      --name "$FC_BACKEND_APP" \
      --query "properties.template.containers[0].env[?name=='CONTACT_RAIL_ENABLED'].value | [0]" \
      -o tsv) || exit 1
    FC_CONTACT_SECRET_REF=$(az containerapp show \
      --resource-group "$FC_RESOURCE_GROUP" \
      --name "$FC_BACKEND_APP" \
      --query "properties.template.containers[0].env[?name=='CONTACT_RAIL_ENABLED'].secretRef | [0]" \
      -o tsv) || exit 1
    if [ -n "$FC_CONTACT_SECRET_REF" ]; then
      FC_CONTACT_CLASSIFICATION="secretref-unknown"
      FC_CONTACT_REQUIRES_MUTATION=true
      FC_CONTACT_RESTORE_BINDING="secretref:${FC_CONTACT_SECRET_REF}"
    else
      FC_CONTACT_STATE=$(printf '%s' "$FC_CONTACT_STATE_RAW" | tr '[:upper:]' '[:lower:]')
      case "$FC_CONTACT_STATE" in
        ""|false|0|no|off)
          FC_CONTACT_CLASSIFICATION="plain-disabled"
          ;;
        true|1|yes|on)
          FC_CONTACT_CLASSIFICATION="plain-enabled"
          FC_CONTACT_REQUIRES_MUTATION=true
          FC_CONTACT_RESTORE_BINDING="$FC_CONTACT_STATE_RAW"
          ;;
        *)
          FC_CONTACT_CLASSIFICATION="plain-unknown"
          FC_CONTACT_REQUIRES_MUTATION=true
          ;;
      esac
    fi
    ;;
  *)
    printf 'Multiple CONTACT_RAIL_ENABLED entries; stop and contain explicitly\n' >&2
    exit 1
    ;;
esac
printf 'CONTACT_RAIL_ENABLED classification=%s\n' "$FC_CONTACT_CLASSIFICATION"
```

Absent, `false`, `0`, `no`, and `off` are known disabled states. `true`, `1`, `yes`, and
`on` enable the rail. A secret reference is deliberately not dereferenced for triage and
is treated as unknown/enabled; an unknown plain token also fails closed. Do not print an
unknown value. Apply a unique incident revision only when the classification requires it:

```bash
FC_REVISION_SUFFIX="${FC_INCIDENT_SLUG}-contact-off-1"

if [ "$FC_CONTACT_REQUIRES_MUTATION" = true ]; then
  az containerapp update \
    --resource-group "$FC_RESOURCE_GROUP" \
    --name "$FC_BACKEND_APP" \
    --set-env-vars CONTACT_RAIL_ENABLED=false \
    --revision-suffix "$FC_REVISION_SUFFIX" \
    -o none || exit 1
fi
```

Whether or not a mutation was needed, run both probes:

```bash
curl --silent --show-error --connect-timeout 5 --max-time 20 \
  -o /dev/null -w 'contact %{http_code}\n' "$FC_API/api/contact/requests"
curl --silent --show-error --connect-timeout 5 --max-time 20 \
  -o /dev/null -w 'signals %{http_code}\n' "$FC_API/api/showcase/mine/interest-signals"
```

Both probes must return 404 after any new revision is ready. Do not restore the prior
value automatically. A disabled state caused no mutation and needs no restore. A known
enabled value or secret reference has an exact captured binding; a fresh unique revision
may restore it only after all recovery gates pass. An unknown plain token has no automatic
restore path and requires an owner decision:

```bash
if [ -z "$FC_CONTACT_RESTORE_BINDING" ]; then
  printf 'No approved automatic contact-state restore binding\n' >&2
  exit 1
fi
FC_REVISION_SUFFIX="${FC_INCIDENT_SLUG}-contact-restore-1"
az containerapp update \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --set-env-vars CONTACT_RAIL_ENABLED="$FC_CONTACT_RESTORE_BINDING" \
  --revision-suffix "$FC_REVISION_SUFFIX" \
  -o none
```

Then repeat the expected-state and safeguarding gates.

### Stop the whole backend ingress

Use this only for SEV-0 active disclosure or when no narrower control can guarantee
containment. It takes every backend API offline; the static frontend may remain visible.
Snapshot the ingress object and active revision first.

```bash
az containerapp show \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --query properties.configuration.ingress \
  -o yaml

az containerapp ingress disable \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  -o none

az containerapp show \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --query properties.configuration.ingress \
  -o yaml
```

Require the post-change ingress result to be absent/disabled; an accepted CLI command is
not proof that public containment completed.

After a forward fix and the offline gates in Section 12, use a controlled reopen to run
the direct production HTTP matrix. Restore the documented ingress baseline, but keep
other narrow containment and publication/job freezes in place:

```bash
az containerapp ingress enable \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --type external \
  --target-port 5001 \
  --transport auto \
  --allow-insecure false \
  -o none
```

### Code rollback boundary

The `origin/main` squash commit `96508e7` contains both FC-TF1 and FC-TF2. Any
last-known-good source candidate must include it:

```bash
FC_CANDIDATE_SHA="replace-with-reviewed-sha"
git merge-base --is-ancestor 96508e7 "$FC_CANDIDATE_SHA"
```

Exit 0 proves ancestry; any other result rejects the candidate. Do not roll the
database back.

The deploy workflow builds a mutable `:prod` tag; scheduled scaling also creates
revisions, and a failed overlapping deploy can move the tag before the app update fails.
Therefore neither `:prod` nor a revision name proves code provenance. Prefer a reviewed
forward fix. If rollback is unavoidable, map the reviewed SHA to an immutable ACR digest
using the exact digest emitted by the reviewed Actions build/push log, then verify that
manifest in ACR and deploy it explicitly. ACR tag/timestamp proximity alone does **not**
prove a SHA-to-digest mapping. The successful trust-floor deploy recorded this floor
artifact, which must be revalidated at incident time for retention and schema
compatibility:

```bash
FC_SAFE_DIGEST="sha256:6f5f98a10cc91f01e3b9e7e9bd66ca7b6dcae2d5754384beab9fb8fd0a668245"
FC_SAFE_IMAGE="acrloanarmy.azurecr.io/loanarmy/backend@${FC_SAFE_DIGEST}"
FC_REVISION_SUFFIX="${FC_INCIDENT_SLUG}-rollback-1"

az acr manifest show-metadata \
  --registry acrloanarmy \
  --name "loanarmy/backend@${FC_SAFE_DIGEST}" \
  --query '{digest:digest,created:createdTime,lastUpdated:lastUpdateTime,tags:tags}' \
  -o yaml

az containerapp update \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --image "$FC_SAFE_IMAGE" \
  --revision-suffix "$FC_REVISION_SUFFIX" \
  -o none

FC_EXPECTED_REVISION="${FC_BACKEND_APP}--${FC_REVISION_SUFFIX}"
az containerapp revision show \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --revision "$FC_EXPECTED_REVISION" \
  --query '{name:name,active:properties.active,health:properties.healthState,running:properties.runningState,image:properties.template.containers[0].image}' \
  -o yaml

az containerapp show \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --query '{latest:properties.latestRevisionName,ready:properties.latestReadyRevisionName,image:properties.template.containers[0].image,provisioning:properties.provisioningState}' \
  -o yaml
```

The manifest command must return the exact digest before deployment. Afterward,
`latestReadyRevisionName` must equal `FC_EXPECTED_REVISION`, both image fields must equal
`FC_SAFE_IMAGE`, revision health/running state must be healthy/running, and startup logs
must be clean before any controlled ingress reopen. A successful update command alone is
not a rollback gate.

An app rollback does not roll scheduled jobs. The deploy workflow independently manages
`job-weekly-newsletters`, `job-transfer-heal`, `job-sync-fixtures`,
`job-status-refresh`, and `job-data-fix`. Inventory all current jobs and triggers/images:

```bash
az containerapp job list \
  --resource-group "$FC_RESOURCE_GROUP" \
  --query '[].{name:name,trigger:properties.configuration.triggerType,image:properties.template.containers[0].image}' \
  -o table
```

For a suppression/publication incident, `job-weekly-newsletters` is the first outbound
boundary. If it exists, list and stop each active execution by its reviewed name:

```bash
az containerapp job execution list \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name job-weekly-newsletters \
  --query '[].{name:name,status:properties.status,start:properties.startTime,end:properties.endTime}' \
  -o table

FC_JOB_EXECUTION="replace-with-reviewed-active-execution"
az containerapp job stop \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name job-weekly-newsletters \
  --job-execution-name "$FC_JOB_EXECUTION"
```

Stopping one execution does not disable its next trigger. Freeze the owning schedule or
manual invoker, snapshot its configuration, and prove no new execution can start before
reopening. The repository defines no universal non-destructive job pause, so this requires
an incident-approved trigger-owner action. If a non-publication job must keep running on
rollback code, map and pin its reviewed immutable digest separately; do not assume the app
image update changed it. Restore captured triggers/images only after verification.

## 5. Account export disclosure or scope defect

`GET /api/account/export` is synchronous, read-only, bearer-authenticated, and limited
to three requests per hour per authenticated key. The server does not retain an export
artifact.

### If another person's private data appears

1. Declare SEV-0 and disable backend ingress. There is no export-only feature flag.
2. Stop the reporter from sending or re-downloading the raw file. Record only the
   HTTP status, export timestamp, affected section names, account IDs, any response
   reference that is actually present, and a restricted-evidence pointer.
3. Determine whether the row was actually unauthorized. Received contact threads
   require a current approved player claim; club threads require current program-manager
   authorization. Historical actor references alone are intentionally excluded.
4. Reproduce with two incident-controlled accounts in a non-production environment.
   Prove account A cannot receive account B's verification, lists/follows, claims,
   owner content, contact threads, reports, or subscriptions.
5. Deploy a forward fix, repeat the two-account test, then follow Section 12's controlled
   reopen sequence.
6. The privacy lead owns impact analysis and any notification decision. Do not make
   legal-deadline claims in the engineering timeline.

### If export is missing data or returns 500

- A 429 is expected after three attempts; stop retry loops and wait for the limiter
  window when requests reach the same counter. If `RATELIMIT_STORAGE_URL` is absent, the
  default limiter is process-local memory and must not be treated as a security boundary.
- A route-body 500 logs `Failed to export account data` and includes a response reference.
  If that exact anchor/reference is absent, inspect framework/auth traces for an earlier
  database or `user_accounts.is_tombstone` schema failure. Export can be safely retried
  after the fault is fixed; no server-side partial export needs cleanup.
- Suppressed direct follows intentionally render as `Unavailable`. Revoked authorization
  can intentionally remove previously visible received/club threads.
- Recovery requires a two-account isolation test, not only a shape-valid 200. Require
  `exported_at`, `account`, `scout_verifications`, `watchlist_entries`, `follow_lists`,
  `showcase_claims`, `showcase_profiles`, `submitted_links`, `contact_requests`,
  `content_reports`, and `email_subscriptions`. Recursively reject capability or
  counterparty fields such as `unsubscribe_token`, `managed_by_user_id`,
  `reporter_user_id`, `scout_user_id`, `sender_user_id`, and `reported_by_user_id`, plus
  another account's IDs/emails or pending-contract data. Never copy a real user's export
  into a test fixture or incident ticket.

## 6. Account deletion failure, unknown outcome, or residue

`POST /api/account/delete` requires a JSON object whose `confirm` field is exactly
`"DELETE"`.
The service locks the account, creates a non-authenticatable tombstone, deletes or
anonymizes classified data, removes the original account, and appends a counts-only
deletion event in one transaction.

### Classify the result before doing anything else

| Client result | Meaning and action |
|---|---|
| 400 exact-confirmation error | No deletion attempt ran. Correct the body. |
| 401 missing/invalid/expired token error | No authenticated deletion reached the route. Correct authentication; do not interpret this as a deletion result. |
| 401 `account not found` | The signed identity no longer resolves to a non-tombstone account: an already committed deletion or a concurrent account-generation change is possible. Verify before creating a replacement account. |
| 429 | No new service attempt passed the limiter. Stop automated retries. |
| 500 | Often a rolled-back pre-commit fault, but still treat as outcome-unknown until DB verification. |
| Timeout/disconnect | Outcome-unknown: the database commit may have succeeded before the response was lost. |
| 200 with `deletion_event_id` | Committed and application-irreversible. Preserve the non-PII original user id and request timestamp/window when known, plus event id, completion time, and counts. Never preserve the bearer token or email in a public timeline. |

### Verify outcome

Use the bound, read-only queries in [Appendix A](#appendix-a-read-only-database-checks).

- **Committed:** the returned event exists; its linked account is a tombstone with
  `email IS NULL`; the original account id is absent; the old bearer token gets 401.
- **Rolled back:** the known original id still resolves to the original non-tombstone
  account and representative owned rows remain. Time-window event/tombstone rows are
  supporting candidates only; they cannot be called a match.
- **Uncorrelated:** deletion events intentionally store no original id/email. Without
  the response event id or the original user id, a time-window match is a candidate,
  not proof. Escalate instead of guessing.

### Recover safely

- `account deletion policy missing for <table>.<column>` is a deliberate fail-closed
  guard for a new direct user FK. Stop retries, classify that table as delete versus
  anonymize in code, test the forward policy, and deploy. Do not NULL/drop/repoint the
  FK by hand.
- Never reconstruct a completed deletion from tombstoned/shared records. A new signup
  is a new account generation and does not restore deleted data.
- Shared contact messages, content-report details, and append-only audit rows can
  legitimately survive with identity references repointed to `Account deleted`.
  Co-owned showcase content and other explicitly allowlisted shared/moderation rows can
  also remain. Counts of zero are valid when that category had no matching pre-state;
  compare counts to known metadata rather than treating zero alone as failure. A known
  owned row still keyed to the original identity after a completed event is an incident;
  a known shared row should point to the tombstone or have its direct identity link
  scrubbed according to policy. If pre-state is unknown, escalate to engineering rather
  than infer completeness from aggregate counts alone.
- Never delete the event, repoint its tombstone, or downgrade `tf01` to "undo" a
  deletion.

## 7. Urgent player takedown

Public intake returns the same neutral 202 for a known or unknown player and stores
requester contact/statement as Fernet ciphertext. Keep those fields inside the restricted
privacy workflow. A second valid request while the row is still `requested` can overwrite
the first requester's encrypted evidence, so preserve the authorized restricted record
before further intake or action when evidence chronology matters.

### Activate the request

Use Appendix A's metadata-only queue query in the ordinary incident terminal. The admin
list endpoint always decrypts and transmits contact, statement, and notes for every row
on the page, so only the privacy/safeguarding lead may open it in a restricted session.
After confirming the target, record the current row once, then activate it without
printing the full decrypted response:

```bash
FC_SUPPRESSION_ID="replace-with-id"
curl --silent --show-error --connect-timeout 5 --max-time 30 -X POST \
  --output /dev/null \
  --write-out 'activate %{http_code}\n' \
  -H "Authorization: Bearer $FC_ADMIN_BEARER" \
  -H "X-API-Key: $FC_ADMIN_API_KEY" \
  -H 'Content-Type: application/json' \
  -d "$(jq -cn --arg notes "${FC_INCIDENT_ID}: emergency containment; evidence retained separately" '{notes:$notes}')" \
  "$FC_API/api/admin/suppressions/$FC_SUPPRESSION_ID/activate"
```

Expected status is 200. Verify the new status through the metadata-only SQL query.
Any timeout or disconnect is outcome-unknown: query metadata before considering a retry.

Activation marks the row active and soft-deactivates matching player shadows. It does
not delete stored data, and repeating activation overwrites decision metadata; do not
repeat it casually.

### Treat activation as partial containment

On the current implementation, activation protects the core player detail, search,
Scout Desk, team, showcase/claim, watchlist/follow, digest/pulse/card, academy/journey,
community-take, shadow-mint, and new-contact paths. Existing participant contact threads
remain available by design.

It is **not a complete platform-wide takedown**. Stored newsletter payloads/rendered
views; public cohort-member and feeder-origin data; GOL data, lookup, suggestions, and
web-search results; public journalist charts, articles, commentary detail/search;
writer commentary mutations; curator player lists; some quick-take paths; and global or
cohort aggregates are not consistently suppression-filtered. GOL also holds a five-minute
per-process cache. The feeder GET can refresh upstream data and persist journeys, so do
not use it as a production probe before the guard is fixed. For any urgent safety/legal
request, or whenever the player can appear on one of those surfaces:

1. activate the suppression;
2. set the contact flag false;
3. disable backend ingress if any uncovered surface can still disclose the player; and
4. keep containment until a forward fix filters the response and invalidates affected
   caches.

Previously delivered email cannot be recalled. Record it in impact analysis; do not
lift the live suppression to compare content. Freeze writer/curator publication and
inspect scheduled jobs so no new newsletter or derived artifact is emitted during
containment. Do not open a stored newsletter detail endpoint for ordinary verification;
that path can log a stored player name as well as return unfiltered material.

## 8. Active suppression leak

1. Confirm the row is `active` using metadata only. Do not rely on a public 404 to
   distinguish unknown from suppressed; neutrality is intentional.
2. Test the backend FQDN directly so the static frontend cannot hide API behavior.
3. Declare SEV-0 for any public disclosure. Disable backend ingress unless a narrower
   forward fix is already deployed and verified on the exact leaking surface.
4. Preserve the active row and all moderation/audit data. Do not change it to lifted,
   rejected, or a new lifecycle.
5. Inspect both classes:
   - **core enforcement:** profile, stats, season stats, availability, commentary,
     showcase, links/comments, journey/map, academy stats, player/Scout search,
     compare, team rosters, watchlists/follows, claims, shadow mint, new contact;
   - **secondary/stored/aggregate:** newsletter JSON/HTML and journalist view, cohort
     members and analytics, feeder origins, GOL chat/lookup/suggestions/web search/data
     cache, journalist charts, article/commentary detail and search, writer-created
     commentary, curator player listings, quick takes with cached identity but no player
     id, global counts, and any already rendered or delivered artifact.
6. Add the suppression predicate at the data-loading boundary, not as a late name-only
   redaction. Test that the player id, name, links, stats, and derived text are absent.
7. After deploying the fix, clear every GOL process cache before reopening ingress. The
   admin endpoint clears only the worker that handles that request, so one 200 does not
   prove fleet-wide invalidation. Restart the active revision (all replicas/workers) or
   hold ingress closed for longer than 300 seconds, then verify repeatedly across the
   running fleet:

```bash
FC_FIXED_REVISION="replace-with-exact-reviewed-fixed-revision"
az containerapp revision show \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --revision "$FC_FIXED_REVISION" \
  --query '{name:name,active:properties.active,health:properties.healthState,running:properties.runningState,traffic:properties.trafficWeight,image:properties.template.containers[0].image}' \
  -o yaml

az containerapp ingress traffic show \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  -o table

az containerapp revision restart \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --revision "$FC_FIXED_REVISION" \
  -o none
```

Use the exact revision created by the reviewed fixed/digest deployment, not ambient
`latestReadyRevisionName`. Before restart, require it to be active, healthy/running, on
the expected immutable image, and receiving the intended traffic; otherwise keep ingress
closed and resolve the rollout race.

8. Follow Section 12's controlled-reopen sequence, run the full suppression matrix, and
   observe logs. The incident commander and privacy/safeguarding lead approve full
   restoration only after it passes.

## 9. Suppression encryption or queue failure

Encrypted fields use this read order:

1. `PLAYER_SUPPRESSION_ENCRYPTION_KEY` when configured; then
2. a domain-separated key derived from `SECRET_KEY`.

New writes use the first candidate. Historical rows carry only a `fernet:v1:` prefix,
not a key id, so removing a previously used key can strand newer ciphertext. A malformed
dedicated key fails closed before the fallback is tried.

As of the 2026-07-23 live snapshot, production has no dedicated suppression-key env
entry. Existing suppression ciphertext therefore depends on the current derived
`SECRET_KEY`. Adding a dedicated key changes new writes but does not re-encrypt old rows;
rotating `SECRET_KEY` afterward would strand those historical rows.

### Diagnose without printing values

```bash
az containerapp show \
  --resource-group "$FC_RESOURCE_GROUP" \
  --name "$FC_BACKEND_APP" \
  --query "properties.template.containers[0].env[?name=='PLAYER_SUPPRESSION_ENCRYPTION_KEY' || name=='SECRET_KEY'].{name:name,secretRef:secretRef}" \
  -o table
```

Expected error text includes:

- `PLAYER_SUPPRESSION_ENCRYPTION_KEY or SECRET_KEY is required`
- `player suppression encryption key must be a valid Fernet key`
- `unencrypted suppression value rejected`
- `suppression value failed authentication`

Do not display secret values or raw ciphertext. This query proves only which secret
reference is wired; inline ACA secret references are not version-pinned and provide no
reliable historical-key version. The reviewed live configuration uses inline ACA secrets,
and repository-noted Key Vault copies are stale. Recover the exact prior material only
from an approved deployment/backup record. If no such record exists, keep broad
containment in place and escalate key recovery rather than guessing, rotating, or testing
candidates against live data. Existing active suppressions generally continue to filter
core SQL paths because enforcement reads only player id and status, but intake, queue
serialization, and admin decisions can fail.

### Break-glass activation during a crypto outage

Use only for an urgent request when the normal admin action is unavailable. This is a
write transaction requiring incident-commander and privacy/safeguarding approval. Execute
through an approved parameter-binding database client; never interpolate values into SQL.

```sql
BEGIN;

SELECT id, player_api_id, status, created_at
FROM player_suppressions
WHERE id = :suppression_id
FOR UPDATE;

WITH target AS (
  SELECT id, player_api_id
  FROM player_suppressions
  WHERE id = :suppression_id
    AND status = 'requested'
),
activated AS (
  UPDATE player_suppressions AS suppression
  SET status = 'active',
      updated_at = CURRENT_TIMESTAMP,
      decided_at = CURRENT_TIMESTAMP,
      decided_by = :incident_actor
  FROM target
  WHERE suppression.id = target.id
  RETURNING suppression.id, suppression.player_api_id
),
shadow_changes AS (
  UPDATE player_shadows AS shadow
  SET is_active = FALSE
  WHERE shadow.player_api_id IN (SELECT player_api_id FROM activated)
  RETURNING shadow.id
)
SELECT activated.id AS activation_id,
       activated.player_api_id,
       (SELECT count(*) FROM shadow_changes) AS shadows_deactivated
FROM activated;
```

Set `incident_actor` to a non-PII incident marker such as `incident:INC-1234`. Do not
write encrypted `notes` while key handling is impaired. The parameter-binding client must
remain outside autocommit and return exactly one `activation_id`; only then issue `COMMIT`.
If it returns zero/multiple rows or any error, issue `ROLLBACK` and escalate. An already
active row returns zero deliberately so its original decision evidence is not overwritten.
After `COMMIT`, open a fresh read-only session and run Appendix A's lifecycle/shadow query:
the target row must be `active` and every matching shadow must be inactive. A timeout or
disconnect during/after commit is outcome-unknown; run that verification before any
retry, and never rerun activation when the row is already active. Immediately run the
public leak checks and use broad containment because the known secondary-surface gaps
still apply.
After key recovery, verify that the authorized admin queue can decrypt the row and add
the missing decision context to the restricted incident record rather than rewriting
history.

## 10. Safeguarding report or contact-rail abuse

This playbook covers a reported contact message, fraudulent scout verification, an
approved player self-claim that is under 18/has unknown DOB, or a contact request that
bypassed the contracted-player routing rules.

1. Set `CONTACT_RAIL_ENABLED=false`. This is the only shipped global stop for existing
   threads; revoking scout verification prevents new requests but does **not** close an
   already accepted thread.
2. Preserve metadata from the open report queue with Appendix A's read-only query.
   The admin response also includes reporter identity and report details, so open it only
   in the restricted evidence session.

3. For a fraudulent or unsafe scout verification, revoke it with a bounded reason:

```bash
FC_VERIFICATION_ID="replace-with-id"
curl --silent --show-error --connect-timeout 5 --max-time 30 -X POST \
  --output /dev/null \
  --write-out 'verification-revoke %{http_code}\n' \
  -H "Authorization: Bearer $FC_ADMIN_BEARER" \
  -H "X-API-Key: $FC_ADMIN_API_KEY" \
  -H 'Content-Type: application/json' \
  -d "$(jq -cn --arg reason "${FC_INCIDENT_ID}: verification revoked during safeguarding review" '{revocation_reason:$reason}')" \
  "$FC_API/api/admin/scout-verifications/$FC_VERIFICATION_ID/revoke"
```

4. For an ineligible/fraudulent player self-claim, revoke the approved claim:

```bash
FC_CLAIM_ID="replace-with-id"
curl --silent --show-error --connect-timeout 5 --max-time 30 -X POST \
  --output /dev/null \
  --write-out 'claim-revoke %{http_code}\n' \
  -H "Authorization: Bearer $FC_ADMIN_BEARER" \
  -H "X-API-Key: $FC_ADMIN_API_KEY" \
  -H 'Content-Type: application/json' \
  -d '{"action":"revoke"}' \
  "$FC_API/api/admin/showcase/claims/$FC_CLAIM_ID/review"
```

5. Preserve `contact_requests`, messages, outcomes, and append-only audit events. There
   is no shipped per-thread admin freeze. Suppression blocks new contact for a player but
   intentionally leaves an existing participant thread available; use the global flag.
   A revoke/review timeout is outcome-unknown; read the bounded metadata row before any
   retry so decision evidence is not overwritten.
6. A content report does not auto-hide content or stop contact. The resolution endpoint
   accepts only `resolved` or `dismissed`; although `reviewing` is a model/list status,
   there is no API transition into it. Resolve only after containment and evidence review.
7. Before re-enabling, prove: the unsafe verification/claim is no longer authoritative;
   no new request can be created; club-included messages require both player acceptance
   and club consent; club-notified requests retain the scout permission attestation; and
   all relevant audit rows remain.

## 11. Release or schema regression

The expected migration chain is `tf02 -> tf01 -> fc03 -> fc02 -> fc01`, with one
Alembic head. `tf01` creates deletion tombstones/events and `tf02` creates suppression
history; both enable RLS in the creating migration.

1. Pause deletion/takedown decisions when the schema is uncertain. Read-only intake and
   active suppression behavior may fail differently, so test each control independently.
2. Run the schema checks in Appendix A through the approved owner/operator role. A
   policy-free RLS table can appear empty to an ordinary role; never disable RLS to test.
   Separately run the role-semantics query through the exact application DB identity.
   Because the shipped tables intentionally have no permissive policy, that identity
   must be superuser/BYPASSRLS or own the table while `relforcerowsecurity=false`; an
   unrelated operator result proves nothing. Treat any unexpected policy as drift for
   review, not an automatic fix.
   Require `user_accounts.is_tombstone` to exist as non-null with a false default,
   `contact_requests.claim_id` to be nullable, every listed FC/TF trust table to exist
   with RLS enabled, every listed routing column to exist, and all four event/queue
   indexes plus suppression column types/nullability/lengths to match the migration. All
   three named suppression check constraints must return non-null definitions, and the
   duplicate-open lifecycle query must return zero rows. A `tf02` version row alone does
   not prove guarded DDL completed.
3. Apply the reviewed forward migration path. The deploy workflow does **not** run
   `flask db upgrade`; migration success must be established separately. Do not
   hand-create columns/tables and do not stamp past missing DDL. This repository does not
   define the production migration owner, backup/PITR owner, or restore procedure; those
   are **UNCONFIRMED** and must be assigned before any database write. PITR is a separately
   authorized recovery path, not routine incident containment.
4. Never downgrade any part of the `fc01 -> fc02 -> fc03 -> tf01 -> tf02` trust stack
   for containment. In addition to deletion/suppression history loss, older downgrades can
   expire active club-included requests or remove contact, audit/report, claim, and routing
   state. Preserve the database and ship a forward fix.
5. Validate route behavior, targeted tests, RLS, and one-head state before restoring
   ingress. A green `/api/health` alone is insufficient.

## 12. Recovery verification

### Controlled reopen sequence

1. While ingress remains disabled, require: reviewed source-to-digest evidence; the exact
   revision/image healthy and ready; clean startup/system logs; one Alembic head and all
   schema/RLS/index checks; metadata-safe incident-state checks; repository/staging tests;
   and all relevant outbound job triggers frozen.
2. Incident commander plus privacy/safeguarding lead approve a bounded production test
   window. Enable ingress with the Section 4 baseline while leaving the contact rail off
   and publication freezes active when relevant.
3. Run the direct-FQDN matrix below immediately and watch both system and console logs.
4. On any unexpected status, disclosure, timeout pattern, revision/image change, or new
   job execution, disable ingress again immediately and return to containment.
5. Only after the full matrix and observation window pass may owners restore the prior
   contact flag, scaling workflow, publication, and captured job triggers/images.

### Production smoke matrix

Run direct against the backend FQDN after the fixed revision is ready:

- process health is 200;
- unauthenticated export/admin routes remain 401;
- the contact rail is 404 while disabled;
- an active suppression's canonical player endpoints return neutral 404;
- player/Scout/team lists and compare results contain neither the id nor identity;
- watchlist/follow entries are inert and name-free;
- stored newsletter/journalist view, chart, article/detail/search, cohort-member, community-
  take, quick-take, writer-catalog, and curator-list responses omit the id, identity,
  links, statistics, and derived text, including name-only legacy rows;
- global and cohort aggregates are recomputed without the target rather than merely
  redacting a label;
- GOL cache was invalidated after the fixed predicate deployed;
- staging regression proves feeder and every GOL lookup/suggestion/chat/web-search path
  filters before upstream calls, caching, persistence, or serialization;
- staging write tests prove new claim, shadow mint, contact creation, writer commentary,
  and quick-take submission/approval cannot republish the target;
- account export scope passes two-account isolation in controlled staging; and
- completed deletion has one event/tombstone, no original account, and invalid old auth.

Never use a real urgent takedown request as a production test. Use a controlled staging
fixture or read an already active id without lifting it. Do not use production feeder GET
or GOL chat as smoke tests: they can call upstream services and persist data. Do not put a
target name in a query string; use candidate IDs and boolean assertions in the restricted
session, and keep all production verification read-only.

### Authorized suppression lift

Lifting is republication, not a diagnostic or ordinary incident-recovery step. Use it only
after privacy/safeguarding/legal approval and after every known gap has a deployed guard or
an explicitly accepted exception.

1. Preserve the metadata-only row, activation timestamps, candidate artifact IDs/counts,
   and restricted-evidence pointer. The lifecycle row is mutable; lift overwrites decision
   notes/time/actor and there is no append-only action history.
2. Require zero duplicate open lifecycles. Review stored newsletters, cohorts,
   commentaries/takes, external delivery, and any legal hold; lifting does not remove or
   safely republish those retained artifacts.
3. Call the normal dual-factor endpoint once and discard its decrypted response body:

```bash
FC_SUPPRESSION_ID="replace-with-id"
curl --silent --show-error --connect-timeout 5 --max-time 30 -X POST \
  --output /dev/null \
  --write-out 'lift %{http_code}\n' \
  -H "Authorization: Bearer $FC_ADMIN_BEARER" \
  -H "X-API-Key: $FC_ADMIN_API_KEY" \
  -H 'Content-Type: application/json' \
  -d "$(jq -cn --arg notes "${FC_INCIDENT_ID}: republication approved; evidence retained separately" '{notes:$notes}')" \
  "$FC_API/api/admin/suppressions/$FC_SUPPRESSION_ID/lift"
```

4. Expected status is 200. A timeout/disconnect is outcome-unknown: do not retry until a
   fresh read-only lifecycle/shadow query proves the result. Repeating an already lifted
   action overwrites decision evidence.
5. Require the target row to be `lifted`, no `active` lifecycle for that player, and every
   matching shadow to be active (no shadow is acceptable if none existed). Stop on
   duplicates or mixed state.
6. Recycle the corrected GOL fleet cache, then validate ordinary trust/claim/contact
   prerequisites and data freshness separately. Do not automatically republish a
   previously redacted/unpublished artifact merely because live suppression was lifted.

### Repository gates

Run from `academy-watch-backend/` in a prepared development environment:

```bash
pytest -q \
  tests/test_account.py \
  tests/test_auth_decorators.py \
  tests/test_player_suppression.py \
  tests/test_trust.py \
  tests/test_contact.py \
  tests/test_migration_heads.py

ruff check .
ruff format --check .
alembic -c alembic.ini heads
```

The Alembic command must report only `tf02` for the source version covered by this
runbook. Any suppression fix must add regressions for every secondary surface named in
Sections 7–8, not only the canonical player routes.

## 13. Evidence and communications

### Minimum incident record

- incident ID, severity, UTC start/detect/contain/recover/close times;
- incident commander, privacy/safeguarding lead, and security/credential owner when applicable;
- affected control and IDs (no names/email/message bodies);
- backend revision, immutable image digest, reviewed build/run correlation evidence, and
  source SHA (mark the SHA `UNCONFIRMED` unless that correlation proves it);
- initial and post-containment contact-flag/ingress state;
- response status, any reference that is present, and exact generic log signature;
- approved changes, actor, command class, and result;
- verification matrix result and remaining uncertainty; and
- restricted-evidence pointer, impact assessment, and notification owner.

### Update template

> `INCIDENT_ID` — investigating a trust/privacy control affecting `CONTROL` since
> `UTC_TIME`. `CONTAINMENT` is active. No raw personal data belongs in this channel.
> Next update by `UTC_TIME`; privacy/safeguarding review is `STATUS`.

Do not promise breach, legal, or regulator notification timelines in an engineering
update. The privacy/safeguarding lead determines jurisdiction, scope, and communications.

## 14. Known operational gaps

- FC-TF2 is not yet suppression-complete across stored newsletter, cohort, feeder, and
  GOL surfaces, or several journalist/commentary/quick-take paths; urgent takedowns can
  require backend-wide containment and an outbound-publication freeze.
- There is no route-specific kill switch for export, deletion, takedown intake, or the
  suppression admin queue. Only the contact rail has a dedicated flag.
- There is no per-thread admin freeze; verification revocation does not stop an existing
  accepted thread.
- There is no universal non-destructive pause for Container App jobs; outbound schedulers
  require a trigger-owner freeze plus active-execution stop.
- The content-report API cannot transition a report to `reviewing`.
- `/api/health` does not query the database.
- If `RATELIMIT_STORAGE_URL` is absent, rate limits use process-local memory and reset
  with process/revision changes.
- Deletion events are intentionally PII-free and cannot independently map back to the
  original account after a lost response.
- Suppression ciphertext has no key id or automated re-encryption command.
- Single-revision deployment and the mutable production image tag mean an old runnable
  revision may not be available; maintain a forward-fix path.
- Production migration ownership and the backup/PITR owner/procedure are not defined in
  this repository; do not improvise a restore during an incident.
- The resource group had no Azure metric or scheduled-query alerts in the 2026-07-23
  live inspection. No paging destination, legal contact, or restricted evidence system
  is defined in this repository; the incident commander must assign them at declaration.

Do not close an incident merely because the service restarted or a single route returned
the expected code. Close only after the full affected-surface matrix passes, the privacy/
safeguarding lead accepts the impact assessment, containment is intentionally restored,
and a follow-up owner exists for every known gap.

## Appendix A: read-only database checks

Run through the approved database/operator path with bound parameters and a read-only
transaction. Production connectivity must use the configured IPv4 Supabase pooler, not
the IPv6-only direct host. Force the connection default with
`PGOPTIONS='-c default_transaction_read_only=on'` in addition to the transaction guard.
The `:name` tokens below are for an approved parameter-binding SQLAlchemy client, not raw
`psql` paste or text substitution. If only `psql` is available, stop and use a
reviewed parameter wrapper. Do not paste bound values or result bodies into the public
timeline.

```sql
BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout = '10s';

-- Source head and full FC-B1/B2/B3/TF1/TF2 trust schema.
SELECT version_num FROM alembic_version;
SELECT expected.table_name,
       to_regclass('public.' || expected.table_name) AS relation
FROM (VALUES
  ('scout_verifications'),
  ('content_reports'),
  ('contact_requests'),
  ('contact_messages'),
  ('contact_audit_events'),
  ('contact_outcomes'),
  ('account_deletion_events'),
  ('player_suppressions')
) AS expected(table_name)
ORDER BY expected.table_name;
SELECT c.relname,
       c.relrowsecurity,
       c.relforcerowsecurity,
       pg_get_userbyid(c.relowner) AS table_owner
FROM pg_class AS c
JOIN pg_namespace AS n ON n.oid = c.relnamespace
WHERE n.nspname = 'public'
  AND c.relname IN (
    'scout_verifications',
    'content_reports',
    'contact_requests',
    'contact_messages',
    'contact_audit_events',
    'contact_outcomes',
    'account_deletion_events',
    'player_suppressions'
  )
ORDER BY c.relname;

-- Run this role check through the exact application DB identity, not merely an
-- unrelated operator identity. Policy-free RLS requires a valid bypass path.
SELECT session_user,
       current_user,
       role_row.rolsuper,
       role_row.rolbypassrls,
       class_row.relforcerowsecurity,
       class_row.relowner = role_row.oid AS current_role_owns_suppression_table
FROM pg_roles AS role_row
JOIN pg_class AS class_row ON class_row.relname = 'player_suppressions'
JOIN pg_namespace AS namespace_row ON namespace_row.oid = class_row.relnamespace
WHERE role_row.rolname = current_user
  AND namespace_row.nspname = 'public';

SELECT tablename, policyname, roles, cmd
FROM pg_policies
WHERE schemaname = 'public'
  AND tablename IN (
    'scout_verifications',
    'content_reports',
    'contact_requests',
    'contact_messages',
    'contact_audit_events',
    'contact_outcomes',
    'account_deletion_events',
    'player_suppressions'
  )
ORDER BY tablename, policyname;

-- Guarded migrations can be partially stamped; verify critical routing/deletion columns.
SELECT table_name,
       column_name,
       data_type,
       udt_name,
       character_maximum_length,
       is_nullable,
       column_default
FROM information_schema.columns
WHERE table_schema = 'public'
  AND (table_name, column_name) IN (
    ('user_accounts', 'is_tombstone'),
    ('player_profile_claims', 'contract_status'),
    ('player_profile_claims', 'current_club_name'),
    ('player_profile_claims', 'club_program_id'),
    ('player_profile_claims', 'status_contradiction'),
    ('player_showcase_profiles', 'pending_contract_claim_id'),
    ('player_showcase_profiles', 'pending_contract_status'),
    ('player_showcase_profiles', 'pending_current_club_name'),
    ('player_showcase_profiles', 'pending_club_program_id'),
    ('player_showcase_profiles', 'pending_status_contradiction'),
    ('contact_requests', 'claim_id'),
    ('contact_requests', 'routing_mode'),
    ('contact_requests', 'club_program_id'),
    ('contact_requests', 'club_consent_status'),
    ('contact_requests', 'club_consent_at'),
    ('contact_requests', 'club_consent_by_user_id'),
    ('contact_requests', 'club_consent_note'),
    ('contact_requests', 'permission_attestation'),
    ('contact_requests', 'permission_attested_at'),
    ('contact_messages', 'sender_role'),
    ('club_programs', 'contact_email'),
    ('player_suppressions', 'player_api_id'),
    ('player_suppressions', 'reason_code'),
    ('player_suppressions', 'requester_role'),
    ('player_suppressions', 'requester_contact'),
    ('player_suppressions', 'request_statement'),
    ('player_suppressions', 'status'),
    ('player_suppressions', 'notes'),
    ('player_suppressions', 'created_at'),
    ('player_suppressions', 'updated_at'),
    ('player_suppressions', 'decided_at'),
    ('player_suppressions', 'decided_by')
  )
ORDER BY table_name, column_name;

SELECT expected.conname,
       pg_get_constraintdef(constraint_row.oid) AS definition
FROM (VALUES
  ('ck_player_suppressions_reason'),
  ('ck_player_suppressions_requester_role'),
  ('ck_player_suppressions_status')
) AS expected(conname)
LEFT JOIN pg_constraint AS constraint_row
  ON constraint_row.conrelid = 'public.player_suppressions'::regclass
 AND constraint_row.conname = expected.conname
ORDER BY expected.conname;

-- Verify the required event and suppression indexes exist; inspect definitions.
SELECT tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname IN (
    'uq_account_deletion_events_tombstone_user',
    'ix_account_deletion_events_requested_at',
    'uq_player_suppressions_open_player',
    'ix_player_suppressions_status_created'
  )
ORDER BY tablename, indexname;

-- Exact committed deletion check when the client retained the event id.
SELECT event.id,
       event.tombstone_user_id,
       event.requested_at,
       event.completed_at,
       event.counts,
       account.is_tombstone,
       (account.email IS NULL) AS tombstone_email_cleared,
       account.display_name
FROM account_deletion_events AS event
JOIN user_accounts AS account ON account.id = event.tombstone_user_id
WHERE event.id = :deletion_event_id;

-- The original id must be absent after a committed deletion.
SELECT EXISTS (
  SELECT 1 FROM user_accounts WHERE id = :original_user_id
) AS original_account_still_exists;

-- If the original id was not captured and the account may have rolled back, bind the
-- restricted email value; a returned row proves only that this account still exists.
SELECT id, created_at, is_tombstone
FROM user_accounts
WHERE lower(email) = lower(:original_email);

-- Lost-response fallback: candidates only, never exact attribution.
SELECT event.id,
       event.tombstone_user_id,
       event.requested_at,
       event.completed_at
FROM account_deletion_events AS event
WHERE event.requested_at >= :window_start
  AND event.requested_at < :window_end
ORDER BY event.requested_at, event.id;

-- Representative metadata-only residue checks using IDs captured before deletion.
SELECT id
FROM scout_watchlist_entries
WHERE id = :known_owned_watchlist_id
  AND user_account_id = :original_user_id;
SELECT id, scout_user_id, claim_id
FROM contact_requests
WHERE id = :known_shared_contact_request_id;
SELECT id, reporter_user_id
FROM content_reports
WHERE id = :known_shared_report_id;

-- Suppression metadata and envelope integrity without decrypting or returning PII.
SELECT id,
       player_api_id,
       reason_code,
       requester_role,
       status,
       created_at,
       updated_at,
       decided_at,
       requester_contact LIKE 'fernet:v1:%' AS contact_wrapped,
       request_statement LIKE 'fernet:v1:%' AS statement_wrapped,
       (notes IS NULL OR notes LIKE 'fernet:v1:%') AS notes_wrapped
FROM player_suppressions
WHERE id = :suppression_id;

-- Runtime invariant and post-action state. Any duplicate group is a stop condition.
SELECT player_api_id, count(*) AS open_lifecycles
FROM player_suppressions
WHERE status IN ('requested', 'active')
GROUP BY player_api_id
HAVING count(*) > 1;

SELECT suppression.id,
       suppression.player_api_id,
       suppression.status,
       shadow.id AS shadow_id,
       shadow.is_active AS shadow_is_active
FROM player_suppressions AS suppression
LEFT JOIN player_shadows AS shadow
  ON shadow.player_api_id = suppression.player_api_id
WHERE suppression.player_api_id = :player_api_id
ORDER BY suppression.created_at, suppression.id, shadow.id;

-- Metadata-only takedown queue. Never select the encrypted field values here.
SELECT id,
       player_api_id,
       reason_code,
       requester_role,
       status,
       created_at,
       updated_at,
       requester_contact LIKE 'fernet:v1:%' AS contact_wrapped,
       request_statement LIKE 'fernet:v1:%' AS statement_wrapped
FROM player_suppressions
WHERE status = 'requested'
ORDER BY created_at, id;

-- Candidate secondary artifacts: IDs/flags only, never bodies or names.
SELECT id, public_slug, published
FROM newsletters
WHERE strpos(
        coalesce(structured_content, '') || coalesce(content, ''),
        cast(:player_api_id AS text)
      ) > 0
ORDER BY id;

SELECT id, cohort_id
FROM cohort_members
WHERE player_api_id = :player_api_id
ORDER BY cohort_id, id;

SELECT id, newsletter_id, is_active
FROM newsletter_commentary
WHERE player_id = :player_api_id
ORDER BY id;

SELECT id, newsletter_id, status
FROM community_takes
WHERE player_id = :player_api_id
ORDER BY id;

SELECT id, status
FROM quick_take_submissions
WHERE player_id = :player_api_id
ORDER BY id;

-- Metadata-only content-report queue; details and reporter identity stay restricted.
SELECT id,
       subject_type,
       subject_id,
       reason_code,
       status,
       created_at
FROM content_reports
WHERE status = 'open'
ORDER BY created_at, id;

-- Bound-id lookups for safeguarding actions; no evidence/profile text.
SELECT id, user_account_id, status, submitted_at
FROM scout_verifications
WHERE id = :verification_id;
SELECT id, player_api_id, user_account_id, relationship_type, status, created_at
FROM player_profile_claims
WHERE id = :claim_id;

-- A fail-closed deletion error naming a future user FK: inventory only.
SELECT constraint_row.conrelid::regclass AS table_name,
       attribute_row.attname AS column_name
FROM pg_constraint AS constraint_row
JOIN pg_attribute AS attribute_row
  ON attribute_row.attrelid = constraint_row.conrelid
 AND attribute_row.attnum = constraint_row.conkey[1]
WHERE constraint_row.contype = 'f'
  AND constraint_row.confrelid = 'user_accounts'::regclass
  AND array_length(constraint_row.conkey, 1) = 1
ORDER BY 1, 2;

ROLLBACK;
```

The newsletter numeric-text match is only a candidate and can false-positive on unrelated
numbers. Legacy name-only newsletter/commentary/take rows require restricted identity
review; do not put a target name into shared SQL history or return stored bodies during
ordinary triage.

## Changelog

- **2026-07-23 — FC-TF3:** initial incident-response runbook for Full Circle trust,
  account export/deletion, player takedown/suppression, encryption, contact/safeguarding,
  release recovery, evidence handling, and cross-surface verification.
