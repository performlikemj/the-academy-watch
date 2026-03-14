"""remove supplemental_loan_id from youtube links

Revision ID: w2x3y4z5a6b7
Revises: v1w2x3y4z5a6
Create Date: 2025-11-09 11:00:00.000000

Remove supplemental_loan_id column from newsletter_player_youtube_links table
as we've unified manual player handling into LoanedPlayer with can_fetch_stats=False.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'w2x3y4z5a6b7'
down_revision = 'v1w2x3y4z5a6'
branch_labels = None
depends_on = None


def upgrade():
    """Remove supplemental_loan_id column and associated indexes."""
    # Drop indexes related to supplemental_loan_id
    try:
        op.drop_index('ix_newsletter_youtube_supplemental_id', table_name='newsletter_player_youtube_links')
    except Exception:
        pass  # Index might not exist
    
    try:
        op.drop_index('ix_newsletter_youtube_unique_supplemental', table_name='newsletter_player_youtube_links')
    except Exception:
        pass  # Index might not exist
    
    # Drop the foreign key constraint if it exists
    try:
        op.drop_constraint('newsletter_player_youtube_links_supplemental_loan_id_fkey', 
                          'newsletter_player_youtube_links', type_='foreignkey')
    except Exception:
        pass  # Constraint might not exist or have different name
    
    # Drop the column
    op.drop_column('newsletter_player_youtube_links', 'supplemental_loan_id')


def downgrade():
    """Restore supplemental_loan_id column and indexes."""
    # Add the column back
    op.add_column('newsletter_player_youtube_links',
                  sa.Column('supplemental_loan_id', sa.Integer(), 
                           sa.ForeignKey('supplemental_loans.id', ondelete='CASCADE'),
                           nullable=True))
    
    # Recreate indexes
    op.create_index('ix_newsletter_youtube_supplemental_id', 
                    'newsletter_player_youtube_links', 
                    ['supplemental_loan_id'])
    
    op.create_index('ix_newsletter_youtube_unique_supplemental', 
                    'newsletter_player_youtube_links',
                    ['newsletter_id', 'supplemental_loan_id'], 
                    unique=True,
                    postgresql_where=sa.text('supplemental_loan_id IS NOT NULL'))






