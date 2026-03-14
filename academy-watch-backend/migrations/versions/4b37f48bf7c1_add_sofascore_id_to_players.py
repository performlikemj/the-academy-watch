"""add sofascore id to players

Revision ID: 4b37f48bf7c1
Revises: c035853f576b
Create Date: 2025-09-29 14:12:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4b37f48bf7c1'
down_revision = '5e044f152f2b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('players', sa.Column('sofascore_id', sa.Integer(), nullable=True))
    op.create_index('ix_players_sofascore_id', 'players', ['sofascore_id'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_players_sofascore_id', table_name='players')
    op.drop_column('players', 'sofascore_id')
