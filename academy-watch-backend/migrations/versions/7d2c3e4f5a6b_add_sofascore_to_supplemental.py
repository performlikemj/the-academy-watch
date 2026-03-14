from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '7d2c3e4f5a6b'
down_revision = '6c1a2b3d4e5f'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('supplemental_loans', sa.Column('sofascore_player_id', sa.Integer(), nullable=True))
    op.create_index('ix_supplemental_loans_sofascore', 'supplemental_loans', ['sofascore_player_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_supplemental_loans_sofascore', table_name='supplemental_loans')
    op.drop_column('supplemental_loans', 'sofascore_player_id')


