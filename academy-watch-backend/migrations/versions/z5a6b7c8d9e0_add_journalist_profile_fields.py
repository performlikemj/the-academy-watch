"""add journalist/profile fields to users and commentary

Revision ID: z5a6b7c8d9e0
Revises: 196536e958f5
Create Date: 2025-11-21 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "z5a6b7c8d9e0"
down_revision = "196536e958f5"
branch_labels = None
depends_on = None


def upgrade():
    # User profile/journalist fields
    op.add_column(
        "user_accounts",
        sa.Column("is_journalist", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("user_accounts", sa.Column("bio", sa.Text(), nullable=True))
    op.add_column(
        "user_accounts",
        sa.Column("profile_image_url", sa.String(length=255), nullable=True),
    )

    # Newsletter commentary metadata
    op.add_column("newsletter_commentary", sa.Column("title", sa.String(length=200), nullable=True))
    op.add_column(
        "newsletter_commentary",
        sa.Column("is_premium", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )

def downgrade():
    op.drop_column("newsletter_commentary", "is_premium")
    op.drop_column("newsletter_commentary", "title")
    op.drop_column("user_accounts", "profile_image_url")
    op.drop_column("user_accounts", "bio")
    op.drop_column("user_accounts", "is_journalist")
