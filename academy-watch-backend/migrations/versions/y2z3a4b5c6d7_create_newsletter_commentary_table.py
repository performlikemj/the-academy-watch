"""create newsletter_commentary table

Revision ID: y2z3a4b5c6d7
Revises: x1y2z3a4b5c6
Create Date: 2025-01-11 10:15:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision = 'y2z3a4b5c6d7'
down_revision = 'x1y2z3a4b5c6'
branch_labels = None
depends_on = None


def upgrade():
    # Create newsletter_commentary table
    op.create_table(
        'newsletter_commentary',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('newsletter_id', sa.Integer(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),  # Nullable for intro/summary commentary
        sa.Column('commentary_type', sa.String(length=20), nullable=False),  # 'player', 'intro', 'summary'
        sa.Column('content', sa.Text(), nullable=False),  # Sanitized HTML content
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.Column('author_name', sa.String(length=120), nullable=False),  # Cached display name
        sa.Column('position', sa.Integer(), nullable=False, server_default=sa.text('0')),  # For ordering multiple commentaries
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    
    # Create foreign key constraints
    op.create_foreign_key(
        'fk_newsletter_commentary_newsletter_id',
        'newsletter_commentary',
        'newsletters',
        ['newsletter_id'],
        ['id'],
        ondelete='CASCADE',
    )
    
    op.create_foreign_key(
        'fk_newsletter_commentary_author_id',
        'newsletter_commentary',
        'user_accounts',
        ['author_id'],
        ['id'],
        ondelete='CASCADE',
    )
    
    # Create indexes for efficient querying
    op.create_index('ix_newsletter_commentary_newsletter_id', 'newsletter_commentary', ['newsletter_id'])
    op.create_index('ix_newsletter_commentary_player_id', 'newsletter_commentary', ['player_id'])
    op.create_index('ix_newsletter_commentary_author_id', 'newsletter_commentary', ['author_id'])
    op.create_index('ix_newsletter_commentary_type', 'newsletter_commentary', ['commentary_type'])
    
    # Create composite index for common query pattern (newsletter + player)
    op.create_index(
        'ix_newsletter_commentary_newsletter_player',
        'newsletter_commentary',
        ['newsletter_id', 'player_id']
    )


def downgrade():
    # Drop indexes
    op.drop_index('ix_newsletter_commentary_newsletter_player', table_name='newsletter_commentary')
    op.drop_index('ix_newsletter_commentary_type', table_name='newsletter_commentary')
    op.drop_index('ix_newsletter_commentary_author_id', table_name='newsletter_commentary')
    op.drop_index('ix_newsletter_commentary_player_id', table_name='newsletter_commentary')
    op.drop_index('ix_newsletter_commentary_newsletter_id', table_name='newsletter_commentary')
    
    # Drop foreign keys
    op.drop_constraint('fk_newsletter_commentary_author_id', 'newsletter_commentary', type_='foreignkey')
    op.drop_constraint('fk_newsletter_commentary_newsletter_id', 'newsletter_commentary', type_='foreignkey')
    
    # Drop table
    op.drop_table('newsletter_commentary')






