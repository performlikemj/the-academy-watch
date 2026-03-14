"""Add team_aliases table

Revision ID: ja02
Revises: ja01
Create Date: 2025-12-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ja02'
down_revision = 'ja01'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('team_aliases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('canonical_name', sa.String(length=100), nullable=False),
        sa.Column('alias', sa.String(length=100), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    # Add index for fast lookups by alias
    op.create_index(op.f('ix_team_aliases_alias'), 'team_aliases', ['alias'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_team_aliases_alias'), table_name='team_aliases')
    op.drop_table('team_aliases')
