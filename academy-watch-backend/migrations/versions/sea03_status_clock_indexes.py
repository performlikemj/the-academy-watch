"""Single-column clock indexes for the season-rollup /status gauge

Revision ID: sea03
Revises: sea02
Create Date: 2026-07-08

The cheap default ``GET /api/admin/season-rollup/status`` gauge reads the newest
mutation clock of each timed source via ``MAX(<clock>)`` (season_rollup route
``_max_source_change``). PostgreSQL only turns ``MAX(col)`` into an index lookup
(ORDER BY col DESC LIMIT 1) when a b-tree exists on that column — otherwise every
call is a full sequential scan of the source table. The rollup tables' own clock
(``player_season_cells.synced_at``) is indexed in sea02; this migration adds the
matching single-column indexes on the three EXISTING source tables so all four
gauge MAX scans are genuine index lookups and the admin gauge stays pollable on
the 0.5 CPU prod box (invariants §7):

  ix_pje_stats_synced_at   — player_journey_entries(stats_synced_at)   [sea01 column]
  ix_apss_updated_at       — academy_player_season_stats(updated_at)
  ix_pss_updated_at        — player_shadow_stats(updated_at)

These tables' CREATE migrations (sea01 / aw14 / older) are already merged to main,
so the indexes cannot be folded into them — a follow-up migration is the correct
vehicle. All three shipped ORM models declare the matching ``db.Index`` in
``__table_args__`` (autogenerate parity), so ``flask db migrate`` proposes no diff.

No new table and no ADD COLUMN — only CREATE INDEX on existing, already-populated
columns — so there is NO RLS statement (invariants §2 applies to new public tables
only) and NO UndefinedColumn/UndefinedTable read-path 500 window: adding a
``db.Index`` to a model changes metadata only and issues no new SELECT. Every op is
guarded via create_index_safe / index_exists (invariants §8 — prod schema drifted
out-of-band); re-applied or partially-applied, upgrade() is a clean no-op.

DEPLOY ORDERING (migrations do NOT auto-run — deploy.yml runs only the RLS
security-check; the container CMD is gunicorn, nothing runs `flask db upgrade`).
Because no read path depends on these indexes existing, ordering is relaxed
relative to sea01/sea02: a not-yet-applied migration causes no 500s — the gauge
merely falls back to seq scans until the index lands. Preferred sequence still
mirrors the others: PRE-APPLY out-of-band against prod BEFORE merging — from a
local checkout with the prod DB env (IPv4 pooler + `postgresql+psycopg://`,
invariants §1) run `FLASK_APP=src/main.py flask db upgrade`. Each CREATE INDEX is a
single-column b-tree build; PJE is the only sizeable table (~77k rows) and still
builds in well under a second. Then merge: the in-container `flask db upgrade` is a
pure no-op stamp (every op guarded via index_exists). Fallback (safe here): apply
post-deploy in the container.
"""

from alembic import op
from migrations._migration_helpers import (
    create_index_safe,
    index_exists,
)

revision = "sea03"
down_revision = "sea02"
branch_labels = None
depends_on = None


def upgrade():
    create_index_safe("ix_pje_stats_synced_at", "player_journey_entries", ["stats_synced_at"])
    create_index_safe("ix_apss_updated_at", "academy_player_season_stats", ["updated_at"])
    create_index_safe("ix_pss_updated_at", "player_shadow_stats", ["updated_at"])


def downgrade():
    if index_exists("ix_pss_updated_at"):
        op.drop_index("ix_pss_updated_at", table_name="player_shadow_stats")
    if index_exists("ix_apss_updated_at"):
        op.drop_index("ix_apss_updated_at", table_name="academy_player_season_stats")
    if index_exists("ix_pje_stats_synced_at"):
        op.drop_index("ix_pje_stats_synced_at", table_name="player_journey_entries")
