"""Drop foreign keys pointing to loaned_players table

Revision ID: aw12
Revises: aw11
Create Date: 2026-03-31

Removes loaned_player_id FK columns from tracked_players,
weekly_loan_appearances, and academy_appearances in preparation
for dropping the loaned_players table.
"""
from alembic import op
import sqlalchemy as sa
from migrations._migration_helpers import column_exists


# revision identifiers, used by Alembic.
revision = 'aw12'
down_revision = 'aw11'
branch_labels = None
depends_on = None


def upgrade():
    # Drop loaned_player_id from tracked_players
    if column_exists('tracked_players', 'loaned_player_id'):
        op.drop_constraint('tracked_players_loaned_player_id_fkey',
                           'tracked_players', type_='foreignkey')
        op.drop_column('tracked_players', 'loaned_player_id')

    # Drop loaned_player_id from weekly_loan_appearances
    if column_exists('weekly_loan_appearances', 'loaned_player_id'):
        # Drop unique constraint that includes loaned_player_id first
        try:
            op.drop_constraint('uq_weekly_appearance', 'weekly_loan_appearances',
                               type_='unique')
        except Exception:
            pass
        try:
            op.drop_constraint('weekly_loan_appearances_loaned_player_id_fkey',
                               'weekly_loan_appearances', type_='foreignkey')
        except Exception:
            pass
        op.drop_column('weekly_loan_appearances', 'loaned_player_id')

    # Drop loaned_player_id from academy_appearances
    if column_exists('academy_appearances', 'loaned_player_id'):
        try:
            op.drop_constraint('academy_appearances_loaned_player_id_fkey',
                               'academy_appearances', type_='foreignkey')
        except Exception:
            pass
        op.drop_column('academy_appearances', 'loaned_player_id')


def downgrade():
    # Re-add columns (without data)
    op.add_column('academy_appearances',
                  sa.Column('loaned_player_id', sa.Integer(), nullable=True))
    op.create_foreign_key('academy_appearances_loaned_player_id_fkey',
                          'academy_appearances', 'loaned_players',
                          ['loaned_player_id'], ['id'])

    op.add_column('weekly_loan_appearances',
                  sa.Column('loaned_player_id', sa.Integer(), nullable=True))
    op.create_foreign_key('weekly_loan_appearances_loaned_player_id_fkey',
                          'weekly_loan_appearances', 'loaned_players',
                          ['loaned_player_id'], ['id'])

    op.add_column('tracked_players',
                  sa.Column('loaned_player_id', sa.Integer(), nullable=True))
    op.create_foreign_key('tracked_players_loaned_player_id_fkey',
                          'tracked_players', 'loaned_players',
                          ['loaned_player_id'], ['id'])
