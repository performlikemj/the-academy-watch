"""Add scout watchlist table and user scout columns

Revision ID: aw15
Revises: aw14
Create Date: 2026-06-12

Per-user scout watchlists (saved players + notes + digest snapshots) and
UserAccount preferences for the scout digest email.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import add_column_safe, column_exists, create_index_safe, index_exists, table_exists

revision = "aw15"
down_revision = "aw14"
branch_labels = None
depends_on = None


def upgrade():
    if not table_exists("scout_watchlist_entries"):
        op.create_table(
            "scout_watchlist_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            # The composite unique below leads on user_account_id and serves
            # every user-scoped query — no standalone indexes needed.
            sa.Column("user_account_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("note", sa.Text()),
            sa.Column("last_snapshot", sa.Text()),
            sa.Column("last_digest_at", sa.DateTime()),
            sa.Column("created_at", sa.DateTime()),
            sa.Column("updated_at", sa.DateTime()),
            sa.UniqueConstraint("user_account_id", "player_api_id", name="uq_scout_watchlist_user_player"),
        )

    # Every per-player stats lookup (compute_stats, recent-form, scout
    # aggregates) filters fixture_player_stats by (player_api_id, team_api_id);
    # only (fixture_id, player_api_id) was indexed before this.
    create_index_safe("ix_fps_player_team", "fixture_player_stats", ["player_api_id", "team_api_id"])

    add_column_safe(
        "user_accounts",
        sa.Column("scout_digest_opt_in", sa.Boolean(), nullable=False, server_default="true"),
    )
    add_column_safe(
        "user_accounts",
        sa.Column("scout_tier", sa.String(20), nullable=False, server_default="free"),
    )


def downgrade():
    if index_exists("ix_fps_player_team"):
        op.drop_index("ix_fps_player_team", table_name="fixture_player_stats")
    if table_exists("scout_watchlist_entries"):
        op.drop_table("scout_watchlist_entries")
    if column_exists("user_accounts", "scout_digest_opt_in"):
        op.drop_column("user_accounts", "scout_digest_opt_in")
    if column_exists("user_accounts", "scout_tier"):
        op.drop_column("user_accounts", "scout_tier")
