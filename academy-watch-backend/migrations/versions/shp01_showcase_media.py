"""Showcase P2 — moderated player photos and profile enrichment.

Adds the private-upload/publication metadata used by the pre-moderated player
photo flow and widens ``player_showcase_profiles`` with self-reported contract,
availability, representation, nationality, and language fields.

Idempotent (guards + helpers) — production has had objects added out-of-band,
so every DDL op is safe to re-run in both directions. Row Level Security is
enabled in this migration alongside the new public table.

Revision ID: shp01
Revises: sea01
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

revision = "shp01"
down_revision = "sea01"
branch_labels = None
depends_on = None


_PROFILE_COLUMNS = (
    sa.Column("contract_status", sa.String(length=30), nullable=True),
    sa.Column("contract_until", sa.Date(), nullable=True),
    sa.Column("availability", sa.String(length=30), nullable=True),
    sa.Column("agent_name", sa.String(length=200), nullable=True),
    sa.Column("agent_contact_email", sa.String(length=320), nullable=True),
    sa.Column("nationality_secondary", sa.String(length=100), nullable=True),
    sa.Column("languages", sa.String(length=300), nullable=True),
)


def upgrade():
    if not table_exists("player_showcase_media"):
        op.create_table(
            "player_showcase_media",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False, server_default="photo"),
            sa.Column("blob_path", sa.Text(), nullable=False),
            sa.Column("public_url", sa.Text(), nullable=True),
            sa.Column("content_type", sa.String(length=50), nullable=True),
            sa.Column("size_bytes", sa.Integer(), nullable=True),
            sa.Column("is_primary", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending_upload"),
            sa.Column(
                "uploaded_by_user_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id"),
                nullable=True,
            ),
            sa.Column("reviewed_by", sa.String(length=200), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    if table_exists("player_showcase_media"):
        op.execute("ALTER TABLE player_showcase_media ENABLE ROW LEVEL SECURITY;")
        create_index_safe(
            "ix_showcase_media_player_status",
            "player_showcase_media",
            ["player_api_id", "status"],
        )

    for column in _PROFILE_COLUMNS:
        add_column_safe("player_showcase_profiles", column)


def downgrade():
    for column in reversed(_PROFILE_COLUMNS):
        if column_exists("player_showcase_profiles", column.name):
            op.drop_column("player_showcase_profiles", column.name)

    if index_exists("ix_showcase_media_player_status"):
        op.drop_index("ix_showcase_media_player_status", table_name="player_showcase_media")
    if table_exists("player_showcase_media"):
        op.drop_table("player_showcase_media")
