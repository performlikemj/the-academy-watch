"""create commentary_applause table

Revision ID: a7b8c9d0e1f2
Revises: z5a6b7c8d9e0
Create Date: 2025-11-24 08:12:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a7b8c9d0e1f2"
down_revision = "z5a6b7c8d9e0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "commentary_applause",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("commentary_id", sa.Integer(), sa.ForeignKey("newsletter_commentary.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=True),
        sa.Column("session_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("timezone('utc', now())")),
    )

    op.create_index("ix_commentary_applause_commentary_id", "commentary_applause", ["commentary_id"])
    op.create_index("ix_commentary_applause_user_id", "commentary_applause", ["user_id"])


def downgrade():
    op.drop_index("ix_commentary_applause_user_id", table_name="commentary_applause")
    op.drop_index("ix_commentary_applause_commentary_id", table_name="commentary_applause")
    op.drop_table("commentary_applause")
