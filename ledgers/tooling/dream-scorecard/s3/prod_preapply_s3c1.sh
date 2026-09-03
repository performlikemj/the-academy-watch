#!/bin/zsh
RG=rg-nbhd-prod; APP=ca-loan-army-backend
sec() { v=$(az containerapp secret show -g $RG -n $APP --secret-name "$1" --query value -o tsv 2>/dev/null | tr -d '"'); case "$v" in kvref:*) az keyvault secret show --id "${v#kvref:}" --query value -o tsv | tr -d '"';; *) echo "$v";; esac; }
H=$(sec supabase-db-host); P=$(sec supabase-db-port); U=$(sec supabase-db-user); N=$(sec supabase-db-name); export PGPASSWORD=$(sec supabase-db-password)
unset PGOPTIONS
psql "host=$H port=$P user=$U dbname=$N sslmode=require" -X -q -A -v ON_ERROR_STOP=1 -c "SELECT version_num AS before FROM alembic_version;" -f /Users/michaeljones/Projects/loanarmy/ledgers/tooling/dream-scorecard/s3/s3c1_preapply.sql \
  -c "SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public' AND tablename IN ('club_program_updates');" \
  -c "SELECT count(*) AS policies FROM pg_policies WHERE tablename IN ('club_program_updates');" \
  -c "SELECT indexname FROM pg_indexes WHERE indexname IN ('ix_club_program_updates_program_status_published');" \
  -c "SELECT version_num AS after FROM alembic_version;"
