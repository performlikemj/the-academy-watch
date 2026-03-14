"""Add editor role and placeholder account fields

Revision ID: ed02
Revises: ja03
Create Date: 2026-01-07

Adds support for:
- Editor role: Users who can manage external writers
- Placeholder accounts: External writers that can be claimed later
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'ed02'
down_revision = 'ja03'
branch_labels = None
depends_on = None


def upgrade():
    # Add editor flag
    op.add_column('user_accounts', sa.Column('is_editor', sa.Boolean(), server_default='false', nullable=False))

    # Add placeholder/claim fields
    op.add_column('user_accounts', sa.Column('managed_by_user_id', sa.Integer(), nullable=True))
    op.add_column('user_accounts', sa.Column('claimed_at', sa.DateTime(), nullable=True))
    op.add_column('user_accounts', sa.Column('claim_token', sa.String(100), nullable=True))
    op.add_column('user_accounts', sa.Column('claim_token_expires_at', sa.DateTime(), nullable=True))

    # Foreign key for managed_by (self-referential)
    op.create_foreign_key(
        'fk_user_managed_by',
        'user_accounts',
        'user_accounts',
        ['managed_by_user_id'],
        ['id'],
        ondelete='SET NULL'
    )

    # Unique index on claim_token for fast lookup
    op.create_index('ix_user_accounts_claim_token', 'user_accounts', ['claim_token'], unique=True)

    # Index on managed_by_user_id for listing managed writers
    op.create_index('ix_user_accounts_managed_by', 'user_accounts', ['managed_by_user_id'])


def downgrade():
    op.drop_index('ix_user_accounts_managed_by', table_name='user_accounts')
    op.drop_index('ix_user_accounts_claim_token', table_name='user_accounts')
    op.drop_constraint('fk_user_managed_by', 'user_accounts', type_='foreignkey')
    op.drop_column('user_accounts', 'claim_token_expires_at')
    op.drop_column('user_accounts', 'claim_token')
    op.drop_column('user_accounts', 'claimed_at')
    op.drop_column('user_accounts', 'managed_by_user_id')
    op.drop_column('user_accounts', 'is_editor')
