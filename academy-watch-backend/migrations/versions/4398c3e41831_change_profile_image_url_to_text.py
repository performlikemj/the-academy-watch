"""change profile_image_url to text

Revision ID: 4398c3e41831
Revises: c6d7e8f9g0h1
Create Date: 2025-11-22 20:55:37.987177

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '4398c3e41831'
down_revision = 'c6d7e8f9g0h1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('user_accounts', schema=None) as batch_op:
        batch_op.alter_column('profile_image_url',
               existing_type=sa.VARCHAR(length=255),
               type_=sa.Text(),
               existing_nullable=True)


def downgrade():
    with op.batch_alter_table('user_accounts', schema=None) as batch_op:
        batch_op.alter_column('profile_image_url',
               existing_type=sa.Text(),
               type_=sa.VARCHAR(length=255),
               existing_nullable=True)
