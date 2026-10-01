"""Floodlight interest sign-ups.

Revision ID: fl01
Revises: ch02
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, table_exists

revision = "fl01"
down_revision = "ch02"
branch_labels = None
depends_on = None


def upgrade():
    if not table_exists("interest_signups"):
        op.create_table(
            "interest_signups",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("email", sa.String(254), nullable=False),
            sa.Column("feature", sa.String(40), nullable=False),
            sa.Column("role", sa.String(20), nullable=True),
            sa.Column("source_path", sa.String(500), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        )
    constraints = sa.inspect(op.get_bind()).get_unique_constraints("interest_signups")
    if not any(c["name"] == "uq_interest_signups_email_feature" for c in constraints):
        op.create_unique_constraint("uq_interest_signups_email_feature", "interest_signups", ["email", "feature"])
    create_index_safe("ix_interest_signups_feature", "interest_signups", ["feature"])
    op.execute("ALTER TABLE public.interest_signups ENABLE ROW LEVEL SECURITY")


def downgrade():
    if table_exists("interest_signups"):
        op.drop_table("interest_signups")
