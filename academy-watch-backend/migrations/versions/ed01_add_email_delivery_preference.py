"""Add email_delivery_preference to user_accounts

Revision ID: ed01_email_delivery_pref
Revises: tt01_team_tracking
Create Date: 2025-11-28 23:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ed01_email_delivery_pref'
down_revision = 'tt01_team_tracking'
branch_labels = None
depends_on = None


def upgrade():
    # Add email_delivery_preference column to user_accounts table
    # Default is 'individual' - users receive separate emails per newsletter
    # Alternative is 'digest' - users receive combined weekly digest
    op.add_column(
        'user_accounts',
        sa.Column(
            'email_delivery_preference',
            sa.String(20),
            nullable=False,
            server_default='individual'
        )
    )


def downgrade():
    op.drop_column('user_accounts', 'email_delivery_preference')

