"""add display name cooldown and legacy comment author names

Revision ID: f6a7d8c9b0e1
Revises: e4f5d6c7b8a9
Create Date: 2025-09-18 15:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision = 'f6a7d8c9b0e1'
down_revision = 'e4f5d6c7b8a9'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('user_accounts', sa.Column('last_display_name_change_at', sa.DateTime(), nullable=True))
    op.add_column('newsletter_comments', sa.Column('author_name_legacy', sa.String(length=120), nullable=True))

    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    connection.execute(sa.text(
        "UPDATE newsletter_comments SET author_name_legacy = author_name "
        "WHERE author_name_legacy IS NULL AND author_name IS NOT NULL"
    ))
    connection.execute(sa.text(
        "UPDATE user_accounts SET last_display_name_change_at = "
        "COALESCE(last_display_name_change_at, updated_at, created_at, :now)"
    ), {'now': now})


def downgrade():
    op.drop_column('newsletter_comments', 'author_name_legacy')
    op.drop_column('user_accounts', 'last_display_name_change_at')

