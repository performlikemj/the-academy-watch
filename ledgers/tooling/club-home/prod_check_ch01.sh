#!/bin/zsh
source "${0:A:h}/_prodenv.sh"
psql "$PGCONN" -X -q -A -v ON_ERROR_STOP=1 <<'SQL'
SELECT version_num AS alembic FROM alembic_version;
SELECT tablename, rowsecurity FROM pg_tables WHERE schemaname='public' AND tablename IN ('club_squads','club_staff') ORDER BY 1;
SELECT table_name||'.'||column_name AS col FROM information_schema.columns WHERE table_schema='public' AND ((table_name='club_roster_members' AND column_name IN ('squad_id','shirt_number')) OR (table_name='club_programs' AND column_name IN ('brand_primary_color','brand_accent_color','banner_url','banner_updated_at'))) ORDER BY 1;
SELECT conname FROM pg_constraint WHERE conname IN ('ck_club_roster_shirt','ck_club_squad_kind') ORDER BY 1;
SELECT indexname FROM pg_indexes WHERE indexname IN ('uq_club_squad_name','uq_club_squad_shirt') ORDER BY 1;
SELECT count(*) AS local_player_provenance_nulls FROM local_players WHERE provenance IS NULL;
SQL
