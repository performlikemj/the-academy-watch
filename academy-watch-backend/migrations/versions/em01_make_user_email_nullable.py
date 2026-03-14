"""Make user email nullable for external writers

Revision ID: em01
Revises: z6b7c8d9e0f1
Create Date: 2026-01-19

External writers may not always provide an email address. This migration
makes the email column nullable while keeping the unique constraint
(PostgreSQL allows multiple NULLs with unique constraint).
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'em01'
down_revision = 'z6b7c8d9e0f1'
branch_labels = None
depends_on = None


def upgrade():
    # Make email column nullable
    op.alter_column('user_accounts', 'email',
                    existing_type=sa.String(255),
                    nullable=True)


def downgrade():
    # First, we need to handle any NULL emails before making non-nullable
    # This will fail if there are NULL emails - intentional safety check
    op.alter_column('user_accounts', 'email',
                    existing_type=sa.String(255),
                    nullable=False)
