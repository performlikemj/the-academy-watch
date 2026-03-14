"""add can_author_commentary to user_accounts

Revision ID: x1y2z3a4b5c6
Revises: w2x3y4z5a6b7
Create Date: 2025-01-11 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'x1y2z3a4b5c6'
down_revision = 'w2x3y4z5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    # Add can_author_commentary field to user_accounts table
    op.add_column('user_accounts', sa.Column('can_author_commentary', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    
    # Note: Admins should be granted author permissions manually after migration
    # via the admin UI or by running:
    # UPDATE user_accounts SET can_author_commentary = true WHERE email = 'your@email.com';


def downgrade():
    op.drop_column('user_accounts', 'can_author_commentary')

