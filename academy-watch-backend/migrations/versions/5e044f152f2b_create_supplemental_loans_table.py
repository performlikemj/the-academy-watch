"""create supplemental loans table

Revision ID: 5e044f152f2b
Revises: c035853f576b
Create Date: 2025-09-27 00:02:47.044078

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '5e044f152f2b'
down_revision = 'c035853f576b'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'supplemental_loans',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('player_name', sa.String(length=120), nullable=False),
        sa.Column('parent_team_id', sa.Integer(), sa.ForeignKey('teams.id'), nullable=True),
        sa.Column('parent_team_name', sa.String(length=120), nullable=False),
        sa.Column('loan_team_id', sa.Integer(), sa.ForeignKey('teams.id'), nullable=True),
        sa.Column('loan_team_name', sa.String(length=120), nullable=False),
        sa.Column('season_year', sa.Integer(), nullable=False),
        sa.Column('data_source', sa.String(length=50), nullable=False, server_default='wikipedia'),
        sa.Column('can_fetch_stats', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('source_url', sa.String(length=255), nullable=True),
        sa.Column('wiki_title', sa.String(length=255), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_supplemental_loans_parent', 'supplemental_loans', ['parent_team_id'])
    op.create_index('ix_supplemental_loans_season', 'supplemental_loans', ['season_year'])


def downgrade():
    op.drop_index('ix_supplemental_loans_season', table_name='supplemental_loans')
    op.drop_index('ix_supplemental_loans_parent', table_name='supplemental_loans')
    op.drop_table('supplemental_loans')
