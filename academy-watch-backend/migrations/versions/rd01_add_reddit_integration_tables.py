"""Add Reddit integration tables

Revision ID: rd01_reddit_integration
Revises: sc01_stats_coverage
Create Date: 2024-12-14

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'rd01_reddit_integration'
down_revision = 'sc01_stats_coverage'
branch_labels = None
depends_on = None


def upgrade():
    # Create team_subreddits table
    op.create_table(
        'team_subreddits',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('subreddit_name', sa.String(50), nullable=False),
        sa.Column('post_format', sa.String(20), nullable=False, server_default='full'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('team_id', 'subreddit_name', name='uq_team_subreddit')
    )

    # Create reddit_posts table
    op.create_table(
        'reddit_posts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('newsletter_id', sa.Integer(), nullable=False),
        sa.Column('team_subreddit_id', sa.Integer(), nullable=False),
        sa.Column('reddit_post_id', sa.String(20), nullable=True),
        sa.Column('reddit_post_url', sa.String(255), nullable=True),
        sa.Column('post_title', sa.String(300), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('posted_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['newsletter_id'], ['newsletters.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_subreddit_id'], ['team_subreddits.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('newsletter_id', 'team_subreddit_id', name='uq_newsletter_subreddit_post')
    )
    
    # Create index for status lookups
    op.create_index('ix_reddit_posts_status', 'reddit_posts', ['status'])


def downgrade():
    op.drop_index('ix_reddit_posts_status', table_name='reddit_posts')
    op.drop_table('reddit_posts')
    op.drop_table('team_subreddits')









