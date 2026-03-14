"""add week dates to commentary

Revision ID: c6d7e8f9g0h1
Revises: b49cbe6e8267
Create Date: 2025-11-21 21:20:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c6d7e8f9g0h1'
down_revision = 'b49cbe6e8267'
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns to newsletter_commentary
    with op.batch_alter_table('newsletter_commentary', schema=None) as batch_op:
        batch_op.add_column(sa.Column('team_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('week_start_date', sa.Date(), nullable=True))
        batch_op.add_column(sa.Column('week_end_date', sa.Date(), nullable=True))
        batch_op.create_foreign_key('fk_commentary_team', 'teams', ['team_id'], ['id'])
        batch_op.alter_column('newsletter_id', existing_type=sa.Integer(), nullable=True)


def downgrade():
    # Remove columns
    with op.batch_alter_table('newsletter_commentary', schema=None) as batch_op:
        batch_op.alter_column('newsletter_id', existing_type=sa.Integer(), nullable=False)
        batch_op.drop_constraint('fk_commentary_team', type_='foreignkey')
        batch_op.drop_column('week_end_date')
        batch_op.drop_column('week_start_date')
        batch_op.drop_column('team_id')
