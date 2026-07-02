"""Talent Showcase — profile claims, showcase profiles, reel ordering.

Merges the two open heads (cs01 journey current_status + vid02 structured
player report) back to a single head and adds the Talent Showcase surface:

- ``player_profile_claims``   — a user claims a player's profile (admin-reviewed)
- ``player_showcase_profiles`` — self-reported profile card (pre-moderated)
- ``player_links.sort_order``  — curated highlight-reel ordering

Idempotent (guards + helpers) — production has had objects added out-of-band,
so every DDL op is safe to re-run in both directions.

Revision ID: aw19
Revises: cs01, vid02
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import (
    add_column_safe,
    column_exists,
    create_index_safe,
    index_exists,
    table_exists,
)

revision = "aw19"
down_revision = ("cs01", "vid02")
branch_labels = None
depends_on = None


def upgrade():
    if not table_exists("player_profile_claims"):
        op.create_table(
            "player_profile_claims",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column(
                "user_account_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id"),
                nullable=False,
            ),
            sa.Column("relationship_type", sa.String(length=20), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("reviewed_by", sa.String(length=200), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("player_api_id", "user_account_id", name="uq_profile_claim_player_user"),
        )
    create_index_safe("ix_profile_claims_player", "player_profile_claims", ["player_api_id"])
    create_index_safe("ix_profile_claims_user", "player_profile_claims", ["user_account_id"])

    if not table_exists("player_showcase_profiles"):
        op.create_table(
            "player_showcase_profiles",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("bio", sa.Text(), nullable=True),
            sa.Column("positions", sa.String(length=100), nullable=True),
            sa.Column("preferred_foot", sa.String(length=10), nullable=True),
            sa.Column("height_cm", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column(
                "updated_by_user_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id"),
                nullable=True,
            ),
            sa.Column("reviewed_by", sa.String(length=200), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )
    create_index_safe("ix_showcase_profiles_player", "player_showcase_profiles", ["player_api_id"], unique=True)

    add_column_safe("player_links", sa.Column("sort_order", sa.Integer(), nullable=True, server_default="0"))


def downgrade():
    if column_exists("player_links", "sort_order"):
        op.drop_column("player_links", "sort_order")

    if index_exists("ix_showcase_profiles_player"):
        op.drop_index("ix_showcase_profiles_player", table_name="player_showcase_profiles")
    if table_exists("player_showcase_profiles"):
        op.drop_table("player_showcase_profiles")

    if index_exists("ix_profile_claims_user"):
        op.drop_index("ix_profile_claims_user", table_name="player_profile_claims")
    if index_exists("ix_profile_claims_player"):
        op.drop_index("ix_profile_claims_player", table_name="player_profile_claims")
    if table_exists("player_profile_claims"):
        op.drop_table("player_profile_claims")
