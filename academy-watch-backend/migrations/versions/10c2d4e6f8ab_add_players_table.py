"""add players table

Revision ID: 10c2d4e6f8ab
Revises: f6a7d8c9b0e1
Create Date: 2025-09-22 10:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '10c2d4e6f8ab'
down_revision = 'f6a7d8c9b0e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'players',
        sa.Column('player_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('firstname', sa.String(length=160), nullable=True),
        sa.Column('lastname', sa.String(length=160), nullable=True),
        sa.Column('nationality', sa.String(length=80), nullable=True),
        sa.Column('age', sa.Integer(), nullable=True),
        sa.Column('height', sa.String(length=32), nullable=True),
        sa.Column('weight', sa.String(length=32), nullable=True),
        sa.Column('position', sa.String(length=80), nullable=True),
        sa.Column('photo_url', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('player_id')
    )
    op.create_index('ix_players_name', 'players', ['name'])


def downgrade():
    op.drop_index('ix_players_name', table_name='players')
    op.drop_table('players')
