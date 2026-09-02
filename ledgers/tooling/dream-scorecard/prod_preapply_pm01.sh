#!/bin/zsh
RG=rg-nbhd-prod; APP=ca-loan-army-backend
sec() { v=$(az containerapp secret show -g $RG -n $APP --secret-name "$1" --query value -o tsv 2>/dev/null | tr -d '"'); case "$v" in kvref:*) az keyvault secret show --id "${v#kvref:}" --query value -o tsv | tr -d '"';; *) echo "$v";; esac; }
H=$(sec supabase-db-host); P=$(sec supabase-db-port); U=$(sec supabase-db-user); N=$(sec supabase-db-name); export PGPASSWORD=$(sec supabase-db-password)
unset PGOPTIONS
psql "host=$H port=$P user=$U dbname=$N sslmode=require" -X -q -A -v ON_ERROR_STOP=1 -c "SELECT version_num AS before FROM alembic_version;" -f /private/tmp/claude-502/-Users-michaeljones-Projects-loanarmy/f5fbc4a9-e25b-4e82-8304-fcf94dad87d1/scratchpad/pm01_preapply.sql \
  -c "SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public' AND tablename IN ('player_match_entries','showcase_moderation_events');" \
  -c "SELECT count(*) AS policies FROM pg_policies WHERE tablename IN ('player_match_entries','showcase_moderation_events');" \
  -c "SELECT indexname FROM pg_indexes WHERE indexname IN ('ux_local_players_api_player_id','ix_player_match_entries_player_season','ix_player_match_entries_club_program','ix_showcase_moderation_events_user_created');" \
  -c "SELECT version_num AS after FROM alembic_version;"
