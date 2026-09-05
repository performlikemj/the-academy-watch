#!/bin/zsh
RG=rg-nbhd-prod; APP=ca-loan-army-backend
sec() { v=$(az containerapp secret show -g $RG -n $APP --secret-name "$1" --query value -o tsv 2>/dev/null | tr -d '"'); case "$v" in kvref:*) az keyvault secret show --id "${v#kvref:}" --query value -o tsv | tr -d '"';; *) echo "$v";; esac; }
H=$(sec supabase-db-host); P=$(sec supabase-db-port); U=$(sec supabase-db-user); N=$(sec supabase-db-name); export PGPASSWORD=$(sec supabase-db-password)
unset PGOPTIONS
psql "host=$H port=$P user=$U dbname=$N sslmode=require" -X -q -A -v ON_ERROR_STOP=1 <<'SQL'
SELECT version_num AS before FROM alembic_version;
UPDATE alembic_version SET version_num='s3e1' WHERE version_num='s3d1';
SELECT version_num AS after FROM alembic_version;
SELECT count(*) AS s3e1_tables FROM pg_tables WHERE schemaname='public' AND tablename IN ('gol_chat_executions','gol_payment_settlements','gol_checkout_terms');
SQL
