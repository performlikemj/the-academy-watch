"""Add team tracking support - is_tracked field and team_tracking_requests table

Revision ID: tt01_team_tracking
Revises: sb01_structured_blocks
Create Date: 2025-11-28 23:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'tt01_team_tracking'
down_revision = 'sb01_structured_blocks'
branch_labels = None
depends_on = None


def upgrade():
    # Add is_tracked column to teams table
    op.add_column('teams', sa.Column('is_tracked', sa.Boolean(), nullable=True, server_default=sa.text('false')))
    
    # Create team_tracking_requests table
    op.create_table(
        'team_tracking_requests',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('team_id', sa.Integer(), sa.ForeignKey('teams.id'), nullable=False),
        sa.Column('team_api_id', sa.Integer(), nullable=False),
        sa.Column('team_name', sa.String(100), nullable=False),
        sa.Column('email', sa.String(255)),
        sa.Column('reason', sa.Text()),
        sa.Column('ip_address', sa.String(64)),
        sa.Column('user_agent', sa.String(512)),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('admin_note', sa.Text()),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('resolved_at', sa.DateTime()),
    )
    
    # Create indexes for faster lookups
    op.create_index('ix_team_tracking_requests_status', 'team_tracking_requests', ['status'])
    op.create_index('ix_team_tracking_requests_team_id', 'team_tracking_requests', ['team_id'])


def downgrade():
    op.drop_index('ix_team_tracking_requests_team_id', 'team_tracking_requests')
    op.drop_index('ix_team_tracking_requests_status', 'team_tracking_requests')
    op.drop_table('team_tracking_requests')
    op.drop_column('teams', 'is_tracked')

