# Azure OIDC and Key Vault runbook

This runbook moves GitHub Actions from a password-bearing service principal to a
user-assigned identity federated with GitHub OIDC, then migrates live Container
Apps secrets into Key Vault. Run these commands from an authenticated operator
shell; the repository workflows do not create identities or role assignments.

The workflows do **not** declare a GitHub `environment:`. Create only the `main`
branch federated credential below. Scheduled workflow runs use the workflow file
from the default branch and receive the `main` ref subject, so the same credential
covers `scheduled-scaling.yml`. A manual dispatch must also target `main`.

## 1. Set the current resource names

```bash
export AZURE_SUBSCRIPTION_ID="63ceeeac-fe3f-4bcb-b6d2-b7aa7fd6bf52"
export AZURE_RG="rg-loan-army-westus2"
export ACA_ENV="cae-loan-army"
export ACR_NAME="acrloanarmy"
export ACA_APP="ca-loan-army-backend"
export KEY_VAULT_NAME="kv-loan-army"
export GH_IDENTITY_NAME="id-gh-loanarmy"

az account set --subscription "$AZURE_SUBSCRIPTION_ID"
export AZURE_TENANT_ID="$(az account show --query tenantId --output tsv)"
```

## 2. Create the OIDC identity and federation

```bash
az identity create \
  --name "$GH_IDENTITY_NAME" \
  --resource-group "$AZURE_RG" \
  --location westus2 \
  --output none

export AZURE_CLIENT_ID="$(az identity show \
  --name "$GH_IDENTITY_NAME" \
  --resource-group "$AZURE_RG" \
  --query clientId \
  --output tsv)"
export GH_IDENTITY_PRINCIPAL_ID="$(az identity show \
  --name "$GH_IDENTITY_NAME" \
  --resource-group "$AZURE_RG" \
  --query principalId \
  --output tsv)"

az identity federated-credential create \
  --name github-main \
  --identity-name "$GH_IDENTITY_NAME" \
  --resource-group "$AZURE_RG" \
  --issuer "https://token.actions.githubusercontent.com" \
  --subject "repo:performlikemj/loanarmy:ref:refs/heads/main" \
  --audiences "api://AzureADTokenExchange" \
  --output none
```

Do not add an `environment:<env>` subject today. If a future workflow job gains
`environment: production`, add a separate credential (the environment subject
replaces the branch subject for that job):

```bash
az identity federated-credential create \
  --name github-environment-production \
  --identity-name "$GH_IDENTITY_NAME" \
  --resource-group "$AZURE_RG" \
  --issuer "https://token.actions.githubusercontent.com" \
  --subject "repo:performlikemj/loanarmy:environment:production" \
  --audiences "api://AzureADTokenExchange" \
  --output none
```

## 3. Assign least-privilege deployment roles

The workflow updates both a Container App and Container Apps Jobs, so Azure's
separate app and job contributor roles are both required. `az acr build` is an ACR
quick build; it needs `Container Registry Tasks Contributor`, not `AcrPush`.

```bash
export AZURE_RG_ID="$(az group show --name "$AZURE_RG" --query id --output tsv)"
export ACR_ID="$(az acr show \
  --name "$ACR_NAME" \
  --resource-group "$AZURE_RG" \
  --query id \
  --output tsv)"

az role assignment create \
  --assignee-object-id "$GH_IDENTITY_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Container Apps Contributor" \
  --scope "$AZURE_RG_ID" \
  --output none

az role assignment create \
  --assignee-object-id "$GH_IDENTITY_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Container Apps Jobs Contributor" \
  --scope "$AZURE_RG_ID" \
  --output none

az role assignment create \
  --assignee-object-id "$GH_IDENTITY_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role "Container Registry Tasks Contributor" \
  --scope "$ACR_ID" \
  --output none
```

The recurring workflow no longer grants roles. Provision the Container App's
runtime pull access once (repeat after recreating the app):

```bash
az containerapp identity assign \
  --name "$ACA_APP" \
  --resource-group "$AZURE_RG" \
  --system-assigned \
  --output none
export ACA_PRINCIPAL_ID="$(az containerapp show \
  --name "$ACA_APP" \
  --resource-group "$AZURE_RG" \
  --query identity.principalId \
  --output tsv)"
az role assignment create \
  --assignee-object-id "$ACA_PRINCIPAL_ID" \
  --assignee-principal-type ServicePrincipal \
  --role AcrPull \
  --scope "$ACR_ID" \
  --output none
```

No Key Vault role is needed by the GitHub OIDC deploy identity: neither workflow
reads or writes Key Vault. The migration script grants `Key Vault Secrets User` to
each app/job runtime identity. The operator running that script separately needs
permission to read the current Container Apps secret values, write Key Vault
secrets (for example, `Key Vault Secrets Officer` on the vault), and create role
assignments on the vault (for example, `Role Based Access Control Administrator`).

No Static Web App RBAC is needed by the OIDC identity. `deploy.yml` continues to
deploy through `SWA_DEPLOYMENT_TOKEN`. An operator running `deploy_aca.sh` needs
`Microsoft.Web/staticSites/listSecrets/action`; `Contributor` scoped to the Static
Web App is the simplest built-in role that supplies it.

### Command-to-role audit

| Actor / commands | Minimum access and scope |
|---|---|
| OIDC workflow: `az account set` | No resource role; it selects the subscription already authorized by OIDC. |
| OIDC workflow: `az acr show`, `az acr build` | `Container Registry Tasks Contributor` on the ACR. This includes registry read and quick-build/task-run actions; `AcrPush` alone does not authorize `az acr build`. |
| OIDC workflows: `az containerapp show`, `identity assign`, `registry set`, `revision set-mode`, `update`, `ingress enable` | `Container Apps Contributor` on the resource group (or individually on the app plus the environment read/join permissions). |
| OIDC workflow: `az containerapp job show`, `job update` | `Container Apps Jobs Contributor` on the resource group (or every named job plus environment read/join permissions). |
| `deploy.yml`: `Azure/static-web-apps-deploy` | No Azure RBAC for the OIDC identity; the action uses `SWA_DEPLOYMENT_TOKEN`. |
| Local `deploy_aca.sh`: `az role assignment create` for app `AcrPull` | `Role Based Access Control Administrator` on the ACR for the interactive operator. This is intentionally not granted to the OIDC identity. |
| Local `deploy_aca.sh`: `az staticwebapp secrets list`, `show`, `hostname list` | A custom role with the needed Static Web App read/list-secret actions is the narrowest option; `Contributor` scoped to the Static Web App is the available simple built-in choice. |
| Local `deploy_aca.sh`: Container App, job, and ACR commands | The same Container Apps, Container Apps Jobs, and Container Registry Tasks roles listed above. `az extension add` is a local CLI operation and needs no Azure resource role. |

## 4. Add GitHub repository variables

Run from this repository, or retain the explicit `--repo` arguments:

```bash
gh variable set AZURE_CLIENT_ID \
  --repo performlikemj/loanarmy --body "$AZURE_CLIENT_ID"
gh variable set AZURE_TENANT_ID \
  --repo performlikemj/loanarmy --body "$AZURE_TENANT_ID"
gh variable set AZURE_SUBSCRIPTION_ID \
  --repo performlikemj/loanarmy --body "$AZURE_SUBSCRIPTION_ID"
gh variable set AZURE_RG \
  --repo performlikemj/loanarmy --body "$AZURE_RG"
gh variable set ACA_ENV \
  --repo performlikemj/loanarmy --body "$ACA_ENV"
gh variable set ACR_NAME \
  --repo performlikemj/loanarmy --body "$ACR_NAME"
gh variable set ACA_APP \
  --repo performlikemj/loanarmy --body "$ACA_APP"
```

## 5. Migrate app and job secrets

Start with the names-only dry run. The script never prints secret values.

```bash
scripts/azure/migrate_secrets_to_keyvault.sh \
  --app "$ACA_APP" \
  --rg "$AZURE_RG" \
  --vault "$KEY_VAULT_NAME" \
  --jobs

scripts/azure/migrate_secrets_to_keyvault.sh \
  --app "$ACA_APP" \
  --rg "$AZURE_RG" \
  --vault "$KEY_VAULT_NAME" \
  --jobs \
  --apply \
  --restart
```

The second command verifies every app/job secret is a Key Vault reference before
rolling the app revision. Jobs use their updated configuration on later runs.

## 6. Verify OIDC deployment

Role assignments and federated credentials can take several minutes to propagate.
Dispatch the full deployment on `main`, then inspect the run:

```bash
gh workflow run deploy.yml \
  --repo performlikemj/loanarmy \
  --ref main \
  -f skip_security_checks=false
gh run list --repo performlikemj/loanarmy --workflow deploy.yml --limit 1
gh run watch --repo performlikemj/loanarmy
```

Also dispatch the scaling workflow on `main` to verify its OIDC path without waiting
for the next schedule:

```bash
gh workflow run scheduled-scaling.yml \
  --repo performlikemj/loanarmy \
  --ref main \
  -f mode=peak
gh run list --repo performlikemj/loanarmy --workflow scheduled-scaling.yml --limit 1
gh run watch --repo performlikemj/loanarmy
```

## 7. Retire the password credential

All three Azure-login workflows now use the same OIDC identity and parameterized
resource names. After all three workflows succeed with OIDC, identify the old
service principal app ID and credential key ID and confirm no other repository or
automation shares either one. GitHub cannot reveal the existing secret value, so
record these identifiers from the operator's secured credential inventory before
deleting the `AZURE_CREDENTIALS` secret.

Then remove the repository secret first and delete only the confirmed password
credential (do not use `--all`):

```bash
export OLD_SP_APP_ID="<confirmed-old-service-principal-app-id>"
export OLD_CREDENTIAL_KEY_ID="<confirmed-password-credential-key-id>"

az ad sp credential list \
  --id "$OLD_SP_APP_ID" \
  --query '[].{keyId:keyId,endDateTime:endDateTime}' \
  --output table

gh secret delete AZURE_CREDENTIALS --repo performlikemj/loanarmy
az ad sp credential delete \
  --id "$OLD_SP_APP_ID" \
  --key-id "$OLD_CREDENTIAL_KEY_ID"
```

If the sharing audit is inconclusive, stop after the successful OIDC verification
and leave the old credential in place until its consumers are identified.
