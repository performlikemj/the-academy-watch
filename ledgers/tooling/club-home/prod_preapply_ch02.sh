#!/bin/zsh
source "${0:A:h}/_prodenv.sh"
psql "$PGCONN" -X -q -A -v ON_ERROR_STOP=1 -f "${0:A:h}/ch02_preapply.sql"
