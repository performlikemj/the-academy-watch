"""Add structured_blocks column to newsletter_commentary table

Revision ID: sb01_structured_blocks
Revises: 9ed6b55674a4
Create Date: 2024-11-26 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'sb01_structured_blocks'
down_revision = '9ed6b55674a4'
branch_labels = None
depends_on = None


def upgrade():
    """Add structured_blocks JSON column to newsletter_commentary table.
    
    This column stores an array of block objects for the modular content builder.
    Each block has: id, type (text|chart|divider), content, is_premium, position, chart_config
    """
    op.add_column('newsletter_commentary', 
        sa.Column('structured_blocks', sa.JSON(), nullable=True))


def downgrade():
    """Remove structured_blocks column."""
    op.drop_column('newsletter_commentary', 'structured_blocks')

