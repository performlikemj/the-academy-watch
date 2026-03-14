"""add unique constraint to loaned_players

Revision ID: b7e1a2c3d4e5
Revises: 5e4d3c2b1a90
Create Date: 2025-09-08 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b7e1a2c3d4e5'
down_revision = '5e4d3c2b1a90'
branch_labels = None
depends_on = None


def upgrade():
    # Ensure no duplicate rows exist before adding the constraint
    conn = op.get_bind()
    # Find duplicates by key
    dup_query = sa.text(
        """
        SELECT player_id, primary_team_id, loan_team_id, window_key, COUNT(*) AS c
        FROM loaned_players
        GROUP BY player_id, primary_team_id, loan_team_id, window_key
        HAVING COUNT(*) > 1
        """
    )
    dups = conn.execute(dup_query).fetchall()
    for row in dups:
        player_id, primary_team_id, loan_team_id, window_key, _ = row
        # Keep the most recently updated row (prefer active when tie)
        keep_id = conn.execute(sa.text(
            """
            SELECT id FROM loaned_players
            WHERE player_id = :player_id AND primary_team_id = :primary_team_id
              AND loan_team_id = :loan_team_id AND window_key = :window_key
            ORDER BY is_active DESC, updated_at DESC NULLS LAST, id DESC
            LIMIT 1
            """
        ), dict(player_id=player_id, primary_team_id=primary_team_id, loan_team_id=loan_team_id, window_key=window_key)).scalar()

        # Delete other rows with same key
        conn.execute(sa.text(
            """
            DELETE FROM loaned_players
            WHERE player_id = :player_id AND primary_team_id = :primary_team_id
              AND loan_team_id = :loan_team_id AND window_key = :window_key
              AND id <> :keep_id
            """
        ), dict(player_id=player_id, primary_team_id=primary_team_id, loan_team_id=loan_team_id, window_key=window_key, keep_id=keep_id))

    # Add the unique constraint
    op.create_unique_constraint(
        'uq_loans_player_parent_loan_window',
        'loaned_players',
        ['player_id', 'primary_team_id', 'loan_team_id', 'window_key']
    )


def downgrade():
    op.drop_constraint('uq_loans_player_parent_loan_window', 'loaned_players', type_='unique')

