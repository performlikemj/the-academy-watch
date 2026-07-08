"""Season-rollup tables — player_season_cells / _totals + league_season_config

Revision ID: sea02
Revises: sea01
Create Date: 2026-07-08

Creates the sea02 half of proposal §2 (ledgers/research/seasons-design-proposal.md):
the precomputed, provenance-tagged per-player-per-season read surface that lets every
hot stats surface read ONE indexed row instead of a live cross-source aggregation on
the 0.5 CPU prod box.

- player_season_cells  — fine grain: one row per SOURCE-contributed cell
                         (player, season, source, club, competition_tier). source is
                         IN the unique key so feeders never collide.
- player_season_totals — coarse grain: the single hot-read row per
                         (player, season, level_group). Both raw fixtures/journey
                         minutes + a reconcile_flag ride along (never-cross-source-sum).
- league_season_config — per-league "what season is NOW" (calendar vs Aug-rollover);
                         seeded for the five calendar-year leagues (Brazil 71,
                         Argentina 128, MLS 253, Liga MX 262, J1 98).

D3a is SCHEMA ONLY — the D3b rollup service is the sole writer. No route/service
SELECTs these tables in the shipped image yet, so unlike sea01 there is NO
UndefinedTable 500 window (the ORM classes in src/models/season_rollup.py only
register metadata; they issue no query).

All DDL is guarded (invariants §8 — prod schema has drifted out-of-band): table
creation via table_exists, indexes via create_index_safe, the seed via
ON CONFLICT DO NOTHING, and ENABLE ROW LEVEL SECURITY is itself idempotent. Re-applied
or partially-applied, upgrade() is a clean no-op.

RLS: all THREE new public tables ENABLE ROW LEVEL SECURITY in this migration — the
Deploy security-check fails the deploy for any public table with relrowsecurity=false
(invariants §2). The ALTER runs unconditionally after the table is guaranteed to exist.

DEPLOY ORDERING (migrations do NOT auto-run — deploy.yml runs only the RLS
security-check; the container CMD is gunicorn, nothing runs `flask db upgrade`).
Preferred sequence: PRE-APPLY this migration out-of-band against prod BEFORE merging —
from a local checkout with the prod DB env (IPv4 pooler + `postgresql+psycopg://`,
invariants §1) run `FLASK_APP=src/main.py flask db upgrade`. The three CREATE TABLEs are
instant metadata ops; the seed and RLS are trivial. Then merge: the in-container
`flask db upgrade` is a pure no-op stamp (every op guarded), and the security-check
sees the tables already RLS-enabled.
Fallback (safe here, unlike sea01): apply post-deploy in the container. Because no read
path SELECTs these tables in the D3a image, a not-yet-applied migration causes no 500s —
and while the tables are absent from prod they simply don't appear in the RLS scan;
once created (by this migration) they are RLS-enabled in the same transaction.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import (
    create_index_safe,
    index_exists,
    table_exists,
)
from sqlalchemy.dialects.postgresql import JSONB

revision = "sea02"
down_revision = "sea01"
branch_labels = None
depends_on = None


# The eight aggregatable stat columns shared by cells and totals (all nullable —
# a source that doesn't observe a metric leaves it NULL; observed-zero stays 0).
def _stat_columns():
    return [
        sa.Column("appearances", sa.Integer(), nullable=True),
        sa.Column("goals", sa.Integer(), nullable=True),
        sa.Column("assists", sa.Integer(), nullable=True),
        sa.Column("minutes", sa.Integer(), nullable=True),
        sa.Column("yellows", sa.Integer(), nullable=True),
        sa.Column("reds", sa.Integer(), nullable=True),
        sa.Column("saves", sa.Integer(), nullable=True),
        sa.Column("goals_conceded", sa.Integer(), nullable=True),
    ]


def upgrade():
    # ---- player_season_cells (fine grain) --------------------------------
    if not table_exists("player_season_cells"):
        op.create_table(
            "player_season_cells",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("season", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(length=12), nullable=False),
            sa.Column("club_api_id", sa.Integer(), nullable=False),
            sa.Column("club_name", sa.String(length=200), nullable=True),
            sa.Column("competition_tier", sa.String(length=20), nullable=False),
            sa.Column("level_group", sa.String(length=13), nullable=False),
            *_stat_columns(),
            sa.Column("avg_rating", sa.Numeric(precision=4, scale=2), nullable=True),
            sa.Column("detail", JSONB(), nullable=True),
            sa.Column("synced_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.UniqueConstraint(
                "player_api_id",
                "season",
                "source",
                "club_api_id",
                "competition_tier",
                name="uq_psc_player_season_source_club_tier",
            ),
        )
    create_index_safe("ix_psc_player_season", "player_season_cells", ["player_api_id", "season"])

    # ---- player_season_totals (coarse grain) -----------------------------
    if not table_exists("player_season_totals"):
        op.create_table(
            "player_season_totals",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("season", sa.Integer(), nullable=False),
            sa.Column("level_group", sa.String(length=13), nullable=False),
            *_stat_columns(),
            sa.Column("avg_rating", sa.Numeric(precision=4, scale=2), nullable=True),
            sa.Column("primary_source", sa.String(length=12), nullable=False),
            sa.Column("fixtures_minutes", sa.Integer(), nullable=True),
            sa.Column("journey_minutes", sa.Integer(), nullable=True),
            sa.Column("reconcile_flag", sa.String(length=20), nullable=True),
            sa.Column("source_breakdown", JSONB(), nullable=True),
            sa.Column("clubs", JSONB(), nullable=True),
            sa.Column("computed_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.UniqueConstraint("player_api_id", "season", "level_group", name="uq_pst_player_season_group"),
        )
    create_index_safe("ix_pst_season_group", "player_season_totals", ["season", "level_group"])
    create_index_safe("ix_pst_player", "player_season_totals", ["player_api_id", "season"])

    # ---- league_season_config (natural key, no sequence) -----------------
    if not table_exists("league_season_config"):
        op.create_table(
            "league_season_config",
            sa.Column("league_api_id", sa.Integer(), primary_key=True, autoincrement=False),
            sa.Column("season_type", sa.String(length=12), nullable=True),
            sa.Column("rollover_month", sa.Integer(), nullable=True),
        )
    # Idempotent seed of the five calendar-year leagues (Brazil/Argentina/MLS/Liga MX/J1).
    op.execute(
        "INSERT INTO league_season_config (league_api_id, season_type, rollover_month) VALUES "
        "(71, 'calendar', 1), (128, 'calendar', 1), (253, 'calendar', 1), "
        "(262, 'calendar', 1), (98, 'calendar', 1) "
        "ON CONFLICT (league_api_id) DO NOTHING"
    )

    # ---- RLS on all three new public tables (invariants §2; idempotent) ---
    for table in ("player_season_cells", "player_season_totals", "league_season_config"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade():
    if index_exists("ix_pst_player"):
        op.drop_index("ix_pst_player", table_name="player_season_totals")
    if index_exists("ix_pst_season_group"):
        op.drop_index("ix_pst_season_group", table_name="player_season_totals")
    if index_exists("ix_psc_player_season"):
        op.drop_index("ix_psc_player_season", table_name="player_season_cells")

    if table_exists("league_season_config"):
        op.drop_table("league_season_config")
    if table_exists("player_season_totals"):
        op.drop_table("player_season_totals")
    if table_exists("player_season_cells"):
        op.drop_table("player_season_cells")
