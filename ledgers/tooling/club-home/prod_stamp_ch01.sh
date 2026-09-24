#!/bin/zsh
source "${0:A:h}/_prodenv.sh"
psql "$PGCONN" -X -q -A -v ON_ERROR_STOP=1 <<'SQL'
SELECT version_num AS before FROM alembic_version;
UPDATE alembic_version SET version_num='ch01' WHERE version_num='s4d1';
SELECT version_num AS after FROM alembic_version;
SQL
