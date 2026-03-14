"""make team ids nullable for custom teams

Revision ID: m7n8o9p0q1r2
Revises: h1i2j3k4l5m6
Create Date: 2025-10-07 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'm7n8o9p0q1r2'
down_revision = 'h1i2j3k4l5m6'
branch_labels = None
depends_on = None


def upgrade():
    """Make team_id foreign keys nullable to support custom teams not in database."""
    
    # Need to drop and recreate foreign key constraints to make columns nullable
    with op.batch_alter_table('loaned_players', schema=None) as batch_op:
        # Drop existing foreign key constraints
        batch_op.drop_constraint('loaned_players_primary_team_id_fkey', type_='foreignkey')
        batch_op.drop_constraint('loaned_players_loan_team_id_fkey', type_='foreignkey')
        
        # Alter columns to be nullable
        batch_op.alter_column('primary_team_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.alter_column('loan_team_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        
        # Recreate foreign key constraints (now nullable)
        batch_op.create_foreign_key('loaned_players_primary_team_id_fkey',
                                     'teams', ['primary_team_id'], ['id'])
        batch_op.create_foreign_key('loaned_players_loan_team_id_fkey',
                                     'teams', ['loan_team_id'], ['id'])


def downgrade():
    """Revert team_id columns to not nullable (may fail if NULL values exist)."""
    
    with op.batch_alter_table('loaned_players', schema=None) as batch_op:
        # Drop foreign key constraints
        batch_op.drop_constraint('loaned_players_primary_team_id_fkey', type_='foreignkey')
        batch_op.drop_constraint('loaned_players_loan_team_id_fkey', type_='foreignkey')
        
        # Alter columns to not be nullable
        batch_op.alter_column('primary_team_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
        batch_op.alter_column('loan_team_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
        
        # Recreate foreign key constraints
        batch_op.create_foreign_key('loaned_players_primary_team_id_fkey',
                                     'teams', ['primary_team_id'], ['id'])
        batch_op.create_foreign_key('loaned_players_loan_team_id_fkey',
                                     'teams', ['loan_team_id'], ['id'])

