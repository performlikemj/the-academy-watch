"""Add writer coverage tables for dual-coverage system

Revision ID: wc01
Revises: rd01_add_reddit_integration_tables
Create Date: 2025-12-26

Creates:
- journalist_loan_team_assignments: Writers assigned to loan destination teams
- writer_coverage_requests: Request/approval workflow for coverage
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'wc01'
down_revision = 'rd01_reddit_integration'
branch_labels = None
depends_on = None


def upgrade():
    # Create journalist_loan_team_assignments table
    op.create_table(
        'journalist_loan_team_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('loan_team_name', sa.String(length=100), nullable=False),
        sa.Column('loan_team_id', sa.Integer(), nullable=True),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),
        sa.Column('assigned_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user_accounts.id'], ),
        sa.ForeignKeyConstraint(['loan_team_id'], ['teams.id'], ),
        sa.ForeignKeyConstraint(['assigned_by'], ['user_accounts.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'loan_team_name', name='uq_journalist_loan_team_assignment')
    )

    # Create writer_coverage_requests table
    op.create_table(
        'writer_coverage_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('coverage_type', sa.String(length=20), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('team_name', sa.String(length=100), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('request_message', sa.Text(), nullable=True),
        sa.Column('denial_reason', sa.Text(), nullable=True),
        sa.Column('requested_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['user_accounts.id'], ),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.ForeignKeyConstraint(['reviewed_by'], ['user_accounts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes
    op.create_index('ix_coverage_requests_status', 'writer_coverage_requests', ['status'])
    op.create_index('ix_coverage_requests_user', 'writer_coverage_requests', ['user_id'])


def downgrade():
    # Drop indexes
    op.drop_index('ix_coverage_requests_user', table_name='writer_coverage_requests')
    op.drop_index('ix_coverage_requests_status', table_name='writer_coverage_requests')
    
    # Drop tables
    op.drop_table('writer_coverage_requests')
    op.drop_table('journalist_loan_team_assignments')

