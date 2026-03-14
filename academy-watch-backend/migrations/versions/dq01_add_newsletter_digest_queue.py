"""Add newsletter_digest_queue table for weekly digest emails

Revision ID: dq01_digest_queue
Revises: ed01_email_delivery_pref
Create Date: 2025-11-28 23:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'dq01_digest_queue'
down_revision = 'ed01_email_delivery_pref'
branch_labels = None
depends_on = None


def upgrade():
    # Create newsletter_digest_queue table
    op.create_table(
        'newsletter_digest_queue',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('user_accounts.id'), nullable=False),
        sa.Column('newsletter_id', sa.Integer(), sa.ForeignKey('newsletters.id'), nullable=False),
        sa.Column('week_key', sa.String(20), nullable=False),  # e.g., '2025-W48'
        sa.Column('queued_at', sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column('sent', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
    )
    
    # Create unique constraint for user + newsletter
    op.create_unique_constraint(
        'uq_digest_queue_user_newsletter',
        'newsletter_digest_queue',
        ['user_id', 'newsletter_id']
    )
    
    # Create index for efficient querying of unsent items by week
    op.create_index(
        'ix_digest_queue_week_sent',
        'newsletter_digest_queue',
        ['week_key', 'sent']
    )


def downgrade():
    op.drop_index('ix_digest_queue_week_sent', 'newsletter_digest_queue')
    op.drop_constraint('uq_digest_queue_user_newsletter', 'newsletter_digest_queue')
    op.drop_table('newsletter_digest_queue')

