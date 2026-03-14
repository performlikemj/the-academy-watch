from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '6c1a2b3d4e5f'
down_revision = '4b37f48bf7c1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('supplemental_loans', sa.Column('api_player_id', sa.Integer(), nullable=True))
    op.create_index('ix_supplemental_loans_api_player_id', 'supplemental_loans', ['api_player_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_supplemental_loans_api_player_id', table_name='supplemental_loans')
    op.drop_column('supplemental_loans', 'api_player_id')
