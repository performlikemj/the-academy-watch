"""Add community takes and quick take submissions tables

Revision ID: aw02
Revises: aw01
Create Date: 2026-01-30

Part of The Academy Watch refactor Phase 2. Creates tables for community
content aggregation:
- community_takes: Curated takes from Reddit, Twitter, user submissions, or editor
- quick_take_submissions: User-submitted takes pending moderation
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'aw02'
down_revision = 'aw01'
branch_labels = None
depends_on = None


def upgrade():
    # Create community_takes table
    op.create_table(
        'community_takes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.String(20), nullable=False),
        sa.Column('source_url', sa.String(500), nullable=True),
        sa.Column('source_author', sa.String(100), nullable=False),
        sa.Column('source_platform', sa.String(50), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.Column('player_name', sa.String(100), nullable=True),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('newsletter_id', sa.Integer(), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('curated_by', sa.Integer(), nullable=True),
        sa.Column('curated_at', sa.DateTime(), nullable=True),
        sa.Column('rejection_reason', sa.String(255), nullable=True),
        sa.Column('scraped_at', sa.DateTime(), nullable=True),
        sa.Column('original_posted_at', sa.DateTime(), nullable=True),
        sa.Column('upvotes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id']),
        sa.ForeignKeyConstraint(['newsletter_id'], ['newsletters.id']),
        sa.ForeignKeyConstraint(['curated_by'], ['user_accounts.id']),
    )

    # Create indexes for community_takes
    op.create_index('ix_community_takes_status', 'community_takes', ['status'])
    op.create_index('ix_community_takes_player', 'community_takes', ['player_id'])
    op.create_index('ix_community_takes_team', 'community_takes', ['team_id'])

    # Create quick_take_submissions table
    op.create_table(
        'quick_take_submissions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('submitter_name', sa.String(100), nullable=True),
        sa.Column('submitter_email', sa.String(255), nullable=True),
        sa.Column('player_id', sa.Integer(), nullable=True),
        sa.Column('player_name', sa.String(100), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('reviewed_by', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.Column('rejection_reason', sa.String(255), nullable=True),
        sa.Column('community_take_id', sa.Integer(), nullable=True),
        sa.Column('ip_hash', sa.String(64), nullable=True),
        sa.Column('user_agent', sa.String(512), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id']),
        sa.ForeignKeyConstraint(['reviewed_by'], ['user_accounts.id']),
        sa.ForeignKeyConstraint(['community_take_id'], ['community_takes.id']),
    )

    # Create indexes for quick_take_submissions
    op.create_index('ix_quick_take_submissions_status', 'quick_take_submissions', ['status'])
    op.create_index('ix_quick_take_submissions_ip', 'quick_take_submissions', ['ip_hash'])


def downgrade():
    # Drop quick_take_submissions table first (has FK to community_takes)
    op.drop_index('ix_quick_take_submissions_ip', 'quick_take_submissions')
    op.drop_index('ix_quick_take_submissions_status', 'quick_take_submissions')
    op.drop_table('quick_take_submissions')

    # Drop community_takes table
    op.drop_index('ix_community_takes_team', 'community_takes')
    op.drop_index('ix_community_takes_player', 'community_takes')
    op.drop_index('ix_community_takes_status', 'community_takes')
    op.drop_table('community_takes')
