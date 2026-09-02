#!/bin/zsh
# Read-only prod adoption counts. Never prints the connection string.
set -e
RG=rg-nbhd-prod; APP=ca-loan-army-backend
sec() { v=$(az containerapp secret show -g $RG -n $APP --secret-name "$1" --query value -o tsv 2>/dev/null | tr -d '"'); case "$v" in kvref:*) az keyvault secret show --id "${v#kvref:}" --query value -o tsv | tr -d '"';; *) echo "$v";; esac; }
H=$(sec supabase-db-host); P=$(sec supabase-db-port); U=$(sec supabase-db-user); N=$(sec supabase-db-name); PW=$(sec supabase-db-password)
[ -z "$H" ] && { echo "NO HOST" >&2; exit 2; }
echo "host=${H:0:12}... port=$P user=${U:0:8}... db=$N" >&2
export PGPASSWORD="$PW"
PGURL="host=$H port=${P:-5432} user=$U dbname=${N:-postgres} sslmode=require"
export PGOPTIONS='-c default_transaction_read_only=on'
export PGCONNECT_TIMEOUT=20
psql "$PGURL" -X -q -A -F' | ' -v ON_ERROR_STOP=0 <<'SQL'
\echo === TABLE COUNTS ===
SELECT 'user_accounts' t, count(*) FROM user_accounts
UNION ALL SELECT 'players', count(*) FROM players
UNION ALL SELECT 'tracked_players', count(*) FROM tracked_players
UNION ALL SELECT 'player_profile_claims', count(*) FROM player_profile_claims
UNION ALL SELECT 'local_players', count(*) FROM local_players
UNION ALL SELECT 'player_showcase_profiles', count(*) FROM player_showcase_profiles
UNION ALL SELECT 'player_showcase_media', count(*) FROM player_showcase_media
UNION ALL SELECT 'player_links', count(*) FROM player_links
UNION ALL SELECT 'manual_player_submissions', count(*) FROM manual_player_submissions
UNION ALL SELECT 'local_clubs', count(*) FROM local_clubs
UNION ALL SELECT 'club_programs', count(*) FROM club_programs
UNION ALL SELECT 'club_program_claims', count(*) FROM club_program_claims
UNION ALL SELECT 'club_official_claims', count(*) FROM club_official_claims
UNION ALL SELECT 'club_program_managers', count(*) FROM club_program_managers
UNION ALL SELECT 'club_roster_members', count(*) FROM club_roster_members
UNION ALL SELECT 'club_connect_accounts', count(*) FROM club_connect_accounts
UNION ALL SELECT 'funding_leagues', count(*) FROM funding_leagues
UNION ALL SELECT 'scout_verifications', count(*) FROM scout_verifications
UNION ALL SELECT 'scout_watchlist_entries', count(*) FROM scout_watchlist_entries
UNION ALL SELECT 'follow_lists', count(*) FROM follow_lists
UNION ALL SELECT 'follows', count(*) FROM follows
UNION ALL SELECT 'contact_requests', count(*) FROM contact_requests
UNION ALL SELECT 'contact_messages', count(*) FROM contact_messages
UNION ALL SELECT 'contact_outcomes', count(*) FROM contact_outcomes
UNION ALL SELECT 'video_matches', count(*) FROM video_matches
UNION ALL SELECT 'video_player_reports', count(*) FROM video_player_reports
UNION ALL SELECT 'video_credit_ledger', count(*) FROM video_credit_ledger
UNION ALL SELECT 'stripe_subscriptions', count(*) FROM stripe_subscriptions
UNION ALL SELECT 'user_subscriptions', count(*) FROM user_subscriptions
UNION ALL SELECT 'stripe_connected_accounts', count(*) FROM stripe_connected_accounts
UNION ALL SELECT 'stripe_platform_revenue', count(*) FROM stripe_platform_revenue
UNION ALL SELECT 'content_reports', count(*) FROM content_reports
UNION ALL SELECT 'player_suppressions', count(*) FROM player_suppressions
UNION ALL SELECT 'account_deletion_events', count(*) FROM account_deletion_events
UNION ALL SELECT 'product_events', count(*) FROM product_events
UNION ALL SELECT 'newsletters', count(*) FROM newsletters
UNION ALL SELECT 'community_takes', count(*) FROM community_takes
UNION ALL SELECT 'player_comments', count(*) FROM player_comments
UNION ALL SELECT 'commentary_applause', count(*) FROM commentary_applause
UNION ALL SELECT 'journalist_subscriptions', count(*) FROM journalist_subscriptions
UNION ALL SELECT 'contributor_profiles', count(*) FROM contributor_profiles;
\echo === user_accounts columns ===
SELECT string_agg(column_name, ',') FROM information_schema.columns WHERE table_name='user_accounts';
\echo === claims by status ===
SELECT status, count(*) FROM player_profile_claims GROUP BY 1;
\echo === scout_verifications by status ===
SELECT status, count(*) FROM scout_verifications GROUP BY 1;
\echo === contact_requests by status ===
SELECT status, count(*) FROM contact_requests GROUP BY 1;
\echo === club_program_claims by status ===
SELECT status, count(*) FROM club_program_claims GROUP BY 1;
\echo === video_matches by status ===
SELECT status, count(*) FROM video_matches GROUP BY 1;
\echo === user_accounts created last 30/90 days ===
SELECT count(*) FILTER (WHERE created_at > now() - interval '30 days') d30, count(*) FILTER (WHERE created_at > now() - interval '90 days') d90 FROM user_accounts;
\echo === user_accounts by role ===
SELECT role, count(*) FROM user_accounts GROUP BY 1;
\echo === product_events top types ===
SELECT event_type, count(*) FROM product_events GROUP BY 1 ORDER BY 2 DESC LIMIT 15;
SQL
