#!/bin/zsh
source "${0:A:h}/_prodenv.sh"
psql "$PGCONN" -X -q -A -v ON_ERROR_STOP=1 <<'SQL'
SELECT version_num AS alembic FROM alembic_version;
SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public' AND tablename='club_roster_squad_history';
SELECT table_name||'.'||column_name AS col, data_type, character_maximum_length FROM information_schema.columns
WHERE table_schema='public' AND (
    table_name='club_roster_squad_history'
    OR (table_name='club_roster_members' AND column_name IN ('photo_path','photo_updated_at'))
    OR (table_name='local_players' AND column_name='origin_program_id')
) ORDER BY 1;
SELECT count(*) AS club_players_null_origin FROM local_players WHERE provenance='club' AND origin_program_id IS NULL;
SQL
