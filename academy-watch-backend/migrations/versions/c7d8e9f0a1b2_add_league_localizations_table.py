"""add league localizations table

Revision ID: c7d8e9f0a1b2
Revises: 1b2c3d4e5f6a
Create Date: 2025-08-07 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'c7d8e9f0a1b2'
down_revision = '1b2c3d4e5f6a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'league_localizations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('league_name', sa.String(length=100), nullable=False),
        sa.Column('country', sa.String(length=2), nullable=False),
        sa.Column('search_lang', sa.String(length=5), nullable=False),
        sa.Column('ui_lang', sa.String(length=10), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('league_name')
    )


def downgrade():
    op.drop_table('league_localizations')
