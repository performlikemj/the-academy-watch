"""Showcase P2 — local player identities and subject-aware showcase rows.

Adds the moderated, community-created ``local_players`` identity layer. Local
players are showcase-only and never overload API-Football ids. The existing
showcase subject tables (and ``player_links`` for reels) gain an explicit
``local_player_id`` foreign key, while their API player key becomes nullable so
each row can reference exactly one kind of player. That XOR is deliberately
application-enforced rather than a database CHECK constraint.

Idempotent (guards + helpers) — production has had objects added out-of-band,
so every DDL op is safe to re-run in both directions. Row Level Security is
enabled in this migration alongside the new public table. Downgrading removes
local-subject rows before restoring the legacy API keys to NOT NULL because
those rows cannot be represented by the pre-shp05 schema.

Revision ID: shp05
Revises: shp04
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

revision = "shp05"
down_revision = "shp04"
branch_labels = None
depends_on = None


_SHOWCASE_SUBJECTS = (
    ("player_profile_claims", "player_api_id", "ix_profile_claims_local_player"),
    ("player_showcase_profiles", "player_api_id", "ix_showcase_profiles_local_player"),
    ("player_showcase_media", "player_api_id", "ix_showcase_media_local_player"),
    (
        "player_club_affiliations",
        "player_api_id",
        "ix_player_club_affiliations_local_player",
    ),
)


def _widen_subject_table(table_name: str, api_column: str, index_name: str) -> None:
    if not table_exists(table_name):
        return
    add_column_safe(
        table_name,
        sa.Column(
            "local_player_id",
            sa.Integer(),
            sa.ForeignKey("local_players.id"),
            nullable=True,
        ),
    )
    if column_exists(table_name, api_column):
        op.alter_column(
            table_name,
            api_column,
            existing_type=sa.Integer(),
            nullable=True,
        )
    if column_exists(table_name, "local_player_id"):
        create_index_safe(
            index_name,
            table_name,
            ["local_player_id"],
            unique=table_name == "player_showcase_profiles",
        )


def _restore_api_only_subject(table_name: str, api_column: str, index_name: str) -> None:
    if not table_exists(table_name):
        return

    # Local-only rows have no representation before shp05. Remove them before
    # restoring the legacy API key's NOT NULL constraint.
    if column_exists(table_name, api_column):
        op.execute(f"DELETE FROM {table_name} WHERE {api_column} IS NULL")
    if index_exists(index_name):
        op.drop_index(index_name, table_name=table_name)
    if column_exists(table_name, "local_player_id"):
        op.drop_column(table_name, "local_player_id")
    if column_exists(table_name, api_column):
        op.alter_column(
            table_name,
            api_column,
            existing_type=sa.Integer(),
            nullable=False,
        )


def upgrade():
    if not table_exists("local_players"):
        op.create_table(
            "local_players",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("display_name", sa.String(length=200), nullable=False),
            sa.Column("normalized_name", sa.String(length=220), nullable=False),
            sa.Column("birth_year", sa.Integer(), nullable=True),
            sa.Column("position", sa.String(length=50), nullable=True),
            sa.Column("country", sa.String(length=100), nullable=True),
            sa.Column("city", sa.String(length=120), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("api_player_id", sa.Integer(), nullable=True),
            sa.Column(
                "merged_into_local_player_id",
                sa.Integer(),
                sa.ForeignKey("local_players.id"),
                nullable=True,
            ),
            sa.Column("provenance", sa.String(length=20), nullable=False, server_default="user"),
            sa.Column(
                "created_by_user_id",
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

    if table_exists("local_players"):
        op.execute("ALTER TABLE local_players ENABLE ROW LEVEL SECURITY;")
        create_index_safe(
            "ix_local_players_normalized_name",
            "local_players",
            ["normalized_name"],
        )
        create_index_safe("ix_local_players_status", "local_players", ["status"])

    for table_name, api_column, index_name in _SHOWCASE_SUBJECTS:
        _widen_subject_table(table_name, api_column, index_name)

    if table_exists("player_profile_claims"):
        create_index_safe(
            "uq_profile_claim_local_player_user",
            "player_profile_claims",
            ["local_player_id", "user_account_id"],
            unique=True,
        )

    _widen_subject_table(
        "player_links",
        "player_id",
        "ix_player_links_local_player_id",
    )


def downgrade():
    if index_exists("uq_profile_claim_local_player_user"):
        op.drop_index(
            "uq_profile_claim_local_player_user",
            table_name="player_profile_claims",
        )
    _restore_api_only_subject(
        "player_links",
        "player_id",
        "ix_player_links_local_player_id",
    )
    for table_name, api_column, index_name in reversed(_SHOWCASE_SUBJECTS):
        _restore_api_only_subject(table_name, api_column, index_name)

    if index_exists("ix_local_players_status"):
        op.drop_index("ix_local_players_status", table_name="local_players")
    if index_exists("ix_local_players_normalized_name"):
        op.drop_index(
            "ix_local_players_normalized_name",
            table_name="local_players",
        )
    if table_exists("local_players"):
        op.drop_table("local_players")
