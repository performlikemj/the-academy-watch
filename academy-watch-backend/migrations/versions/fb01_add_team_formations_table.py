"""Add team_formations table

Revision ID: fb01
Revises: aw07
Create Date: 2026-02-06
"""
from alembic import op
import sqlalchemy as sa

revision = 'fb01'
down_revision = 'aw07'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'team_formations',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id'), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('formation_type', sa.String(10), nullable=False),
        sa.Column('positions', sa.JSON(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_team_formations_team_id', 'team_formations', ['team_id'])
    op.create_unique_constraint('uq_team_formation_name', 'team_formations', ['team_id', 'name'])


def downgrade():
    op.drop_table('team_formations')
