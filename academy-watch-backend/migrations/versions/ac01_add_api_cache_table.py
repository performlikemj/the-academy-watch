"""Add api_cache and api_usage_daily tables

Revision ID: ac01
Revises: fb01
Create Date: 2026-02-07
"""
from alembic import op
import sqlalchemy as sa

revision = 'ac01'
down_revision = 'fb01'
branch_labels = None
depends_on = None


def upgrade():
    # --- api_cache: persistent response cache for API-Football ---
    op.create_table(
        'api_cache',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('endpoint', sa.String(100), nullable=False),
        sa.Column('params_hash', sa.String(64), nullable=False),
        sa.Column('response_json', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('endpoint', 'params_hash', name='uq_api_cache_endpoint_hash'),
    )
    op.create_index('ix_api_cache_expires_at', 'api_cache', ['expires_at'])

    # --- api_usage_daily: daily call counter per endpoint ---
    op.create_table(
        'api_usage_daily',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('endpoint', sa.String(100), nullable=False),
        sa.Column('call_count', sa.Integer(), nullable=False, server_default='0'),
        sa.UniqueConstraint('date', 'endpoint', name='uq_api_usage_daily_date_endpoint'),
    )


def downgrade():
    op.drop_table('api_usage_daily')
    op.drop_index('ix_api_cache_expires_at', table_name='api_cache')
    op.drop_table('api_cache')
