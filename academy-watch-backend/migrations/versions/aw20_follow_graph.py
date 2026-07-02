"""Follow graph + shadow tracking tables.

Creates the four Follow-graph surfaces:

- ``follow_lists``            — named lists of follows per user
- ``follows``                 — heterogeneous follow rows (player/academy/geo/query)
- ``player_shadows``          — lightweight worldwide players minted on follow
- ``follow_player_snapshots`` — per-(user, player) digest delta baseline
- ``player_shadow_stats``     — dedicated per-season shadow stats store

Idempotent (guards + helpers) — production has had objects added out-of-band,
so every DDL op is safe to re-run in both directions. Tables + indexes only;
the watchlist -> follow-list backfill is an admin endpoint, not a migration.

Revision ID: aw20
Revises: aw19
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import (
    create_index_safe,
    index_exists,
    table_exists,
)

revision = "aw20"
down_revision = "aw19"
branch_labels = None
depends_on = None


def upgrade():
    if not table_exists("follow_lists"):
        op.create_table(
            "follow_lists",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_account_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("name", sa.String(length=120), nullable=False, server_default="My Watchlist"),
            sa.Column("cadence", sa.String(length=20), nullable=False, server_default="weekly"),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("player_cap", sa.Integer(), nullable=False, server_default="40"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("user_account_id", "name", name="uq_follow_list_user_name"),
        )
    create_index_safe("ix_follow_lists_user", "follow_lists", ["user_account_id"])

    if not table_exists("follows"):
        op.create_table(
            "follows",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "list_id",
                sa.Integer(),
                sa.ForeignKey("follow_lists.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("kind", sa.String(length=20), nullable=False),
            sa.Column("selector", sa.JSON(), nullable=False),
            sa.Column("label", sa.String(length=160), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    create_index_safe("ix_follows_list", "follows", ["list_id"])

    if not table_exists("player_shadows"):
        op.create_table(
            "player_shadows",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("player_name", sa.String(length=200), nullable=False),
            sa.Column("photo_url", sa.String(length=500), nullable=True),
            sa.Column("position", sa.String(length=50), nullable=True),
            sa.Column("nationality", sa.String(length=100), nullable=True),
            sa.Column("birth_date", sa.Date(), nullable=True),
            sa.Column("current_club_name", sa.String(length=200), nullable=True),
            sa.Column("current_club_api_id", sa.Integer(), nullable=True),
            sa.Column(
                "requested_by_user_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id"),
                nullable=True,
            ),
            sa.Column("last_profile_sync_at", sa.DateTime(), nullable=True),
            sa.Column("last_stats_sync_at", sa.DateTime(), nullable=True),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    create_index_safe("ix_player_shadows_player", "player_shadows", ["player_api_id"], unique=True)

    if not table_exists("follow_player_snapshots"):
        op.create_table(
            "follow_player_snapshots",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_account_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("last_snapshot", sa.Text(), nullable=True),
            sa.Column("last_digest_at", sa.DateTime(), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("user_account_id", "player_api_id", name="uq_follow_snapshot_user_player"),
        )

    if not table_exists("player_shadow_stats"):
        op.create_table(
            "player_shadow_stats",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("team_api_id", sa.Integer(), nullable=True),
            sa.Column("team_name", sa.String(length=200), nullable=True),
            sa.Column("season", sa.Integer(), nullable=False),
            sa.Column("appearances", sa.Integer(), nullable=True),
            sa.Column("goals", sa.Integer(), nullable=True),
            sa.Column("assists", sa.Integer(), nullable=True),
            sa.Column("minutes", sa.Integer(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("player_api_id", "team_api_id", "season", name="uq_shadow_stats"),
        )
    create_index_safe("ix_shadow_stats_player", "player_shadow_stats", ["player_api_id"])


def downgrade():
    if index_exists("ix_shadow_stats_player"):
        op.drop_index("ix_shadow_stats_player", table_name="player_shadow_stats")
    if table_exists("player_shadow_stats"):
        op.drop_table("player_shadow_stats")

    if table_exists("follow_player_snapshots"):
        op.drop_table("follow_player_snapshots")

    if index_exists("ix_player_shadows_player"):
        op.drop_index("ix_player_shadows_player", table_name="player_shadows")
    if table_exists("player_shadows"):
        op.drop_table("player_shadows")

    if index_exists("ix_follows_list"):
        op.drop_index("ix_follows_list", table_name="follows")
    if table_exists("follows"):
        op.drop_table("follows")

    if index_exists("ix_follow_lists_user"):
        op.drop_index("ix_follow_lists_user", table_name="follow_lists")
    if table_exists("follow_lists"):
        op.drop_table("follow_lists")
