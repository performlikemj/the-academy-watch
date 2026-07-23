"""Showcase P2 — social-profile claim verification metadata.

Adds the one-time code and best-effort social-proof check fields used to help
admins assess profile claims. Admin review remains the only approval gate.

Idempotent (guards + helpers) — production has had objects added out-of-band,
so every DDL op is safe to re-run in both directions. This migration changes
an existing table only, so no new Row Level Security statement is required.

Revision ID: shp02
Revises: shp01
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import add_column_safe, column_exists

revision = "shp02"
down_revision = "shp01"
branch_labels = None
depends_on = None


_CLAIM_COLUMNS = (
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
)


def upgrade():
    for column in _CLAIM_COLUMNS:
        add_column_safe("player_profile_claims", column)


def downgrade():
    for column in reversed(_CLAIM_COLUMNS):
        if column_exists("player_profile_claims", column.name):
            op.drop_column("player_profile_claims", column.name)
