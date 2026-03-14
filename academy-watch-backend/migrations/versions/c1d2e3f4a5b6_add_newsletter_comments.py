"""add newsletter_comments table

Revision ID: c1d2e3f4a5b6
Revises: b7e1a2c3d4e5
Create Date: 2025-09-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c1d2e3f4a5b6'
down_revision = 'b7e1a2c3d4e5'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'newsletter_comments',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('newsletter_id', sa.Integer(), sa.ForeignKey('newsletters.id'), nullable=False),
        sa.Column('author_email', sa.String(length=255), nullable=False),
        sa.Column('author_name', sa.String(length=120), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), nullable=True, server_default=sa.text('false')),
    )
    op.create_index('ix_newsletter_comments_newsletter_id', 'newsletter_comments', ['newsletter_id'])
    op.create_index('ix_newsletter_comments_created_at', 'newsletter_comments', ['created_at'])


def downgrade():
    op.drop_index('ix_newsletter_comments_created_at', table_name='newsletter_comments')
    op.drop_index('ix_newsletter_comments_newsletter_id', table_name='newsletter_comments')
    op.drop_table('newsletter_comments')

