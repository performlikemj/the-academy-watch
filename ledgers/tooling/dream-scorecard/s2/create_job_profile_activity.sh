#!/bin/zsh
# Creates ACA job job-profile-activity mirroring job-scout-digest (run AFTER PR #984 merges + Deploy succeeds). Never prints secret values.
set -e
RG=rg-nbhd-prod; ENV=nbhd-env-westus2; VAULT=kv-loan-army; SRC=job-scout-digest; JOB=job-profile-activity
ID=/subscriptions/63ceeeac-fe3f-4bcb-b6d2-b7aa7fd6bf52/resourcegroups/rg-nbhd-prod/providers/Microsoft.ManagedIdentity/userAssignedIdentities/id-loanarmy-runtime
# 1) copy per-job KV secrets vault→vault (values never echoed)
for s in supabase-db-password api-football-key secret-key mailgun-api-key; do
  v=$(az keyvault secret show --vault-name $VAULT --name $SRC-$s --query value -o tsv)
  az keyvault secret set --vault-name $VAULT --name $JOB-$s --value "$v" --query id -o tsv >/dev/null && echo "kv: $JOB-$s set"
  unset v
done
# 2) create the job (schedule Mon 07:30 UTC, after the scout digest at 07:00)
az containerapp job create -g $RG -n $JOB --environment $ENV --trigger-type Schedule --cron-expression "30 7 * * 1" \
  --replica-timeout 1800 --replica-retry-limit 0 --parallelism 1 --replica-completion-count 1 \
  --image acrbwmj.azurecr.io/loanarmy/backend:prod --registry-server acrbwmj.azurecr.io --registry-identity $ID \
  --mi-user-assigned $ID --cpu 0.5 --memory 1Gi \
  --secrets supabase-db-password=keyvaultref:https://$VAULT.vault.azure.net/secrets/$JOB-supabase-db-password,identityref:$ID \
            api-football-key=keyvaultref:https://$VAULT.vault.azure.net/secrets/$JOB-api-football-key,identityref:$ID \
            secret-key=keyvaultref:https://$VAULT.vault.azure.net/secrets/$JOB-secret-key,identityref:$ID \
            mailgun-api-key=keyvaultref:https://$VAULT.vault.azure.net/secrets/$JOB-mailgun-api-key,identityref:$ID \
  --env-vars PYTHONPATH=/app FLASK_ENV=production DB_HOST=aws-1-us-west-1.pooler.supabase.com DB_PORT=5432 DB_USER=postgres.snqwamzutbcbjgusubsa DB_NAME=postgres DB_SSLMODE=require \
             MAILGUN_DOMAIN=theacademywatch.com MAILGUN_API_URL=https://api.mailgun.net/v3 "EMAIL_FROM_NAME=The Academy Watch" EMAIL_FROM_ADDRESS=mail@theacademywatch.com \
             PUBLIC_BASE_URL=https://theacademywatch.com PUBLIC_API_BASE_URL=https://api.theacademywatch.com PROFILE_ACTIVITY_MAX_SENDS=500 PROFILE_ACTIVITY_DRY_RUN=1 \
             DB_PASSWORD=secretref:supabase-db-password API_FOOTBALL_KEY=secretref:api-football-key SECRET_KEY=secretref:secret-key MAILGUN_API_KEY=secretref:mailgun-api-key \
  --command python /app/src/jobs/run_profile_activity_notifications.py \
  --query "{name:name,state:properties.provisioningState,cron:properties.configuration.scheduleTriggerConfig.cronExpression}" -o json
