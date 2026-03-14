"""Add contributor_profiles table and contributor fields to newsletter_commentary

Revision ID: cp01
Revises: ja03
Create Date: 2025-01-07

Allows journalists to create profiles for external contributors (scouts, guest analysts)
who can be credited on commentaries without needing a full user account.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'cp01'
down_revision = 'ja03'
branch_labels = None
depends_on = None


def upgrade():
    # Create contributor_profiles table
    op.create_table('contributor_profiles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('bio', sa.Text(), nullable=True),
        sa.Column('photo_url', sa.Text(), nullable=True),
        sa.Column('attribution_url', sa.String(length=500), nullable=True),
        sa.Column('attribution_name', sa.String(length=120), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['user_accounts.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_contributor_profiles_created_by_id'), 'contributor_profiles', ['created_by_id'], unique=False)
    op.create_index(op.f('ix_contributor_profiles_is_active'), 'contributor_profiles', ['is_active'], unique=False)

    # Add contributor fields to newsletter_commentary
    op.add_column('newsletter_commentary', sa.Column('contributor_id', sa.Integer(), nullable=True))
    op.add_column('newsletter_commentary', sa.Column('contributor_name', sa.String(length=120), nullable=True))
    op.create_foreign_key(
        'fk_newsletter_commentary_contributor_id',
        'newsletter_commentary',
        'contributor_profiles',
        ['contributor_id'],
        ['id'],
        ondelete='SET NULL'
    )
    op.create_index(op.f('ix_newsletter_commentary_contributor_id'), 'newsletter_commentary', ['contributor_id'], unique=False)


def downgrade():
    # Remove contributor fields from newsletter_commentary
    op.drop_index(op.f('ix_newsletter_commentary_contributor_id'), table_name='newsletter_commentary')
    op.drop_constraint('fk_newsletter_commentary_contributor_id', 'newsletter_commentary', type_='foreignkey')
    op.drop_column('newsletter_commentary', 'contributor_name')
    op.drop_column('newsletter_commentary', 'contributor_id')

    # Drop contributor_profiles table
    op.drop_index(op.f('ix_contributor_profiles_is_active'), table_name='contributor_profiles')
    op.drop_index(op.f('ix_contributor_profiles_created_by_id'), table_name='contributor_profiles')
    op.drop_table('contributor_profiles')
