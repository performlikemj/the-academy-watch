"""Add pathway tracking columns to loaned_players

Revision ID: aw01
Revises: em01
Create Date: 2026-01-29

Part of The Academy Watch refactor. Adds pathway tracking to support
academy players in addition to loan tracking:
- pathway_status: 'academy' | 'on_loan' | 'first_team' | 'released'
- current_level: 'U18' | 'U21' | 'U23' | 'Reserve' | 'Senior'
- data_depth: 'full_stats' | 'events_only' | 'profile_only'
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aw01'
down_revision = 'em01'
branch_labels = None
depends_on = None


def upgrade():
    # Add pathway_status column with default 'on_loan' for existing records
    op.add_column('loaned_players',
                  sa.Column('pathway_status', sa.String(20), nullable=False,
                            server_default='on_loan'))

    # Add current_level column (nullable, for youth players)
    op.add_column('loaned_players',
                  sa.Column('current_level', sa.String(20), nullable=True))

    # Add data_depth column with default 'full_stats' for existing records
    op.add_column('loaned_players',
                  sa.Column('data_depth', sa.String(20), nullable=False,
                            server_default='full_stats'))


def downgrade():
    op.drop_column('loaned_players', 'data_depth')
    op.drop_column('loaned_players', 'current_level')
    op.drop_column('loaned_players', 'pathway_status')
