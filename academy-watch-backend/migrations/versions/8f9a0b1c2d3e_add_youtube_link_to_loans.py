"""add youtube_link to loans

Revision ID: 8f9a0b1c2d3e
Revises: f6a7d8c9b0e1
Create Date: 2025-10-07 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '8f9a0b1c2d3e'
down_revision = 'f6a7d8c9b0e1'
branch_labels = None
depends_on = None


def upgrade():
    # Add youtube_link column to loaned_players table
    op.add_column('loaned_players', sa.Column('youtube_link', sa.String(length=500), nullable=True))
    
    # Add youtube_link column to supplemental_loans table
    op.add_column('supplemental_loans', sa.Column('youtube_link', sa.String(length=500), nullable=True))


def downgrade():
    # Remove youtube_link column from loaned_players table
    op.drop_column('loaned_players', 'youtube_link')
    
    # Remove youtube_link column from supplemental_loans table
    op.drop_column('supplemental_loans', 'youtube_link')


