"""Showcase P2 — local clubs and player affiliations.

Adds a moderated, user-created club layer for clubs outside API-Football and
pre-moderated player affiliations that can reference either a local club or an
API-Football team. These records are showcase-only and remain separate from
the API-synced ``teams`` table.

Idempotent (guards + helpers) — production has had objects added out-of-band,
so every DDL op is safe to re-run in both directions. Row Level Security is
enabled in this migration alongside both new public tables.

Revision ID: shp03
Revises: shp02
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, index_exists, table_exists

revision = "shp03"
down_revision = "shp02"
branch_labels = None
depends_on = None


def upgrade():
    if not table_exists("local_clubs"):
        op.create_table(
            "local_clubs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=200), nullable=False),
            sa.Column("normalized_name", sa.String(length=220), nullable=False),
            sa.Column("country", sa.String(length=100), nullable=True),
            sa.Column("city", sa.String(length=120), nullable=True),
            sa.Column("level", sa.String(length=30), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("api_team_id", sa.Integer(), nullable=True),
            sa.Column(
                "merged_into_local_club_id",
                sa.Integer(),
                sa.ForeignKey("local_clubs.id"),
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

    if table_exists("local_clubs"):
        op.execute("ALTER TABLE local_clubs ENABLE ROW LEVEL SECURITY;")
        create_index_safe(
            "ix_local_clubs_normalized_name",
            "local_clubs",
            ["normalized_name"],
        )
        create_index_safe("ix_local_clubs_status", "local_clubs", ["status"])

    if not table_exists("player_club_affiliations"):
        op.create_table(
            "player_club_affiliations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column(
                "local_club_id",
                sa.Integer(),
                sa.ForeignKey("local_clubs.id"),
                nullable=True,
            ),
            sa.Column("team_api_id", sa.Integer(), nullable=True),
            sa.Column("season", sa.String(length=20), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
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

    if table_exists("player_club_affiliations"):
        op.execute("ALTER TABLE player_club_affiliations ENABLE ROW LEVEL SECURITY;")
        create_index_safe(
            "ix_player_club_affiliations_player_status",
            "player_club_affiliations",
            ["player_api_id", "status"],
        )


def downgrade():
    if index_exists("ix_player_club_affiliations_player_status"):
        op.drop_index(
            "ix_player_club_affiliations_player_status",
            table_name="player_club_affiliations",
        )
    if table_exists("player_club_affiliations"):
        op.drop_table("player_club_affiliations")

    if index_exists("ix_local_clubs_status"):
        op.drop_index("ix_local_clubs_status", table_name="local_clubs")
    if index_exists("ix_local_clubs_normalized_name"):
        op.drop_index("ix_local_clubs_normalized_name", table_name="local_clubs")
    if table_exists("local_clubs"):
        op.drop_table("local_clubs")
