"""Add background_jobs table for multi-worker job state persistence

Revision ID: bj01
Revises: 
Create Date: 2025-12-02

This migration adds a background_jobs table to store job state in the database
instead of in-memory storage. This fixes the issue where gunicorn with multiple
workers (-w 4) could not share job state, causing seeding operations to appear
to timeout when the frontend polled a different worker than the one running the job.
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'bj01'
down_revision = None  # Will be filled in by alembic heads merge if needed
branch_labels = ('background_jobs',)
depends_on = None


def upgrade():
    # Create background_jobs table
    op.create_table('background_jobs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('job_type', sa.String(length=50), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='running'),
        sa.Column('progress', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('total', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('current_player', sa.String(length=200), nullable=True),
        sa.Column('results_json', sa.Text(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    
    # Create indexes for efficient querying
    op.create_index('ix_background_jobs_status', 'background_jobs', ['status'], unique=False)
    op.create_index('ix_background_jobs_created', 'background_jobs', ['created_at'], unique=False)


def downgrade():
    op.drop_index('ix_background_jobs_created', table_name='background_jobs')
    op.drop_index('ix_background_jobs_status', table_name='background_jobs')
    op.drop_table('background_jobs')













