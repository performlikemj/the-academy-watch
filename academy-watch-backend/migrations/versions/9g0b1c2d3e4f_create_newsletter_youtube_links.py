"""create newsletter_youtube_links table

Revision ID: 9g0b1c2d3e4f
Revises: 8f9a0b1c2d3e
Create Date: 2025-10-07 14:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9g0b1c2d3e4f'
down_revision = '8f9a0b1c2d3e'
branch_labels = None
depends_on = None


def upgrade():
    # Remove youtube_link columns from the previous migration
    op.drop_column('loaned_players', 'youtube_link')
    op.drop_column('supplemental_loans', 'youtube_link')
    
    # Create new junction table for newsletter-player YouTube links
    op.create_table(
        'newsletter_player_youtube_links',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('newsletter_id', sa.Integer(), sa.ForeignKey('newsletters.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),  # API-Football player ID for tracked players
        sa.Column('supplemental_loan_id', sa.Integer(), sa.ForeignKey('supplemental_loans.id', ondelete='CASCADE'), nullable=True),
        sa.Column('player_name', sa.String(120), nullable=False),  # For easy reference
        sa.Column('youtube_link', sa.String(500), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    
    # Create indexes
    op.create_index('ix_newsletter_youtube_newsletter_id', 'newsletter_player_youtube_links', ['newsletter_id'])
    op.create_index('ix_newsletter_youtube_player_id', 'newsletter_player_youtube_links', ['player_id'])
    op.create_index('ix_newsletter_youtube_supplemental_id', 'newsletter_player_youtube_links', ['supplemental_loan_id'])
    
    # Create unique constraint for newsletter + player combination
    op.create_index('ix_newsletter_youtube_unique_tracked', 'newsletter_player_youtube_links', 
                    ['newsletter_id', 'player_id'], unique=True,
                    postgresql_where=sa.text('player_id IS NOT NULL'))
    op.create_index('ix_newsletter_youtube_unique_supplemental', 'newsletter_player_youtube_links',
                    ['newsletter_id', 'supplemental_loan_id'], unique=True,
                    postgresql_where=sa.text('supplemental_loan_id IS NOT NULL'))


def downgrade():
    # Drop the new table
    op.drop_index('ix_newsletter_youtube_unique_supplemental', table_name='newsletter_player_youtube_links')
    op.drop_index('ix_newsletter_youtube_unique_tracked', table_name='newsletter_player_youtube_links')
    op.drop_index('ix_newsletter_youtube_supplemental_id', table_name='newsletter_player_youtube_links')
    op.drop_index('ix_newsletter_youtube_player_id', table_name='newsletter_player_youtube_links')
    op.drop_index('ix_newsletter_youtube_newsletter_id', table_name='newsletter_player_youtube_links')
    op.drop_table('newsletter_player_youtube_links')
    
    # Restore youtube_link columns
    op.add_column('loaned_players', sa.Column('youtube_link', sa.String(length=500), nullable=True))
    op.add_column('supplemental_loans', sa.Column('youtube_link', sa.String(length=500), nullable=True))


