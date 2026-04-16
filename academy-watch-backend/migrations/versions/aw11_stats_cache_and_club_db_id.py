"""Add PlayerStatsCache table and current_club_db_id to tracked_players

Revision ID: aw11
Revises: aw10
Create Date: 2026-03-31
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "aw11"
down_revision = "eab3f61ae7ca"
branch_labels = None
depends_on = None


def upgrade():
    # Create player_stats_cache table
    op.create_table(
        "player_stats_cache",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("player_api_id", sa.Integer(), nullable=False),
        sa.Column("team_api_id", sa.Integer(), nullable=False),
        sa.Column("season", sa.Integer(), nullable=False),
        sa.Column("stats_coverage", sa.String(20), nullable=False, server_default="limited"),
        sa.Column("appearances", sa.Integer(), server_default="0"),
        sa.Column("goals", sa.Integer(), server_default="0"),
        sa.Column("assists", sa.Integer(), server_default="0"),
        sa.Column("minutes_played", sa.Integer(), server_default="0"),
        sa.Column("saves", sa.Integer(), server_default="0"),
        sa.Column("yellows", sa.Integer(), server_default="0"),
        sa.Column("reds", sa.Integer(), server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("player_api_id", "team_api_id", "season", name="uq_player_stats_cache"),
    )
    op.create_index("ix_player_stats_cache_player_api_id", "player_stats_cache", ["player_api_id"])

    # Add current_club_db_id FK to tracked_players
    op.add_column("tracked_players", sa.Column("current_club_db_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_tracked_players_current_club",
        "tracked_players",
        "teams",
        ["current_club_db_id"],
        ["id"],
    )


def downgrade():
    op.drop_constraint("fk_tracked_players_current_club", "tracked_players", type_="foreignkey")
    op.drop_column("tracked_players", "current_club_db_id")
    op.drop_index("ix_player_stats_cache_player_api_id", table_name="player_stats_cache")
    op.drop_table("player_stats_cache")
