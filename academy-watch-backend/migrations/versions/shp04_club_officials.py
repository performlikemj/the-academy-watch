"""Showcase P2 — club-official claims and vouching.

Adds moderated claims for officials representing either an API-Football team
or a local club. Club-reference exclusivity is enforced by the application so
the claim lifecycle can share the existing social-proof verification ladder.

Idempotent (guards + helpers) — production has had objects added out-of-band,
so every DDL op is safe to re-run in both directions. Row Level Security is
enabled in this migration alongside the new public table.

Revision ID: shp04
Revises: shp03
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, index_exists, table_exists

revision = "shp04"
down_revision = "shp03"
branch_labels = None
depends_on = None


def upgrade():
    if not table_exists("club_official_claims"):
        op.create_table(
            "club_official_claims",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_account_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id"),
                nullable=False,
            ),
            sa.Column("team_api_id", sa.Integer(), nullable=True),
            sa.Column(
                "local_club_id",
                sa.Integer(),
                sa.ForeignKey("local_clubs.id"),
                nullable=True,
            ),
            sa.Column("role_title", sa.String(length=100), nullable=True),
            sa.Column("message", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("verification_code", sa.String(length=24), nullable=True),
            sa.Column("verification_proof_url", sa.String(length=500), nullable=True),
            sa.Column(
                "verification_status",
                sa.String(length=20),
                nullable=False,
                server_default="unverified",
            ),
            sa.Column("verification_checked_at", sa.DateTime(), nullable=True),
            sa.Column("verification_note", sa.String(length=500), nullable=True),
            sa.Column("verification_method", sa.String(length=20), nullable=True),
            sa.Column("reviewed_by", sa.String(length=200), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("review_note", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    if table_exists("club_official_claims"):
        op.execute("ALTER TABLE club_official_claims ENABLE ROW LEVEL SECURITY;")
        create_index_safe(
            "ix_club_official_claims_user_status",
            "club_official_claims",
            ["user_account_id", "status"],
        )
        create_index_safe(
            "ix_club_official_claims_team",
            "club_official_claims",
            ["team_api_id"],
        )
        create_index_safe(
            "ix_club_official_claims_local_club",
            "club_official_claims",
            ["local_club_id"],
        )


def downgrade():
    if index_exists("ix_club_official_claims_local_club"):
        op.drop_index(
            "ix_club_official_claims_local_club",
            table_name="club_official_claims",
        )
    if index_exists("ix_club_official_claims_team"):
        op.drop_index(
            "ix_club_official_claims_team",
            table_name="club_official_claims",
        )
    if index_exists("ix_club_official_claims_user_status"):
        op.drop_index(
            "ix_club_official_claims_user_status",
            table_name="club_official_claims",
        )
    if table_exists("club_official_claims"):
        op.drop_table("club_official_claims")
