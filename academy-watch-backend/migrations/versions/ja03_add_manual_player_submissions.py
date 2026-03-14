"""Add manual_player_submissions table

Revision ID: ja03
Revises: ja02
Create Date: 2025-12-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'ja03'
down_revision = 'ja02'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('manual_player_submissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('player_name', sa.String(length=100), nullable=False),
        sa.Column('team_name', sa.String(length=100), nullable=False),
        sa.Column('league_name', sa.String(length=100), nullable=True),
        sa.Column('position', sa.String(length=50), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('admin_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user_accounts.id'], ),
        sa.ForeignKeyConstraint(['reviewed_by'], ['user_accounts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_manual_player_submissions_status'), 'manual_player_submissions', ['status'], unique=False)
    op.create_index(op.f('ix_manual_player_submissions_user_id'), 'manual_player_submissions', ['user_id'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_manual_player_submissions_user_id'), table_name='manual_player_submissions')
    op.drop_index(op.f('ix_manual_player_submissions_status'), table_name='manual_player_submissions')
    op.drop_table('manual_player_submissions')
