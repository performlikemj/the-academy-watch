"""backfill players from existing loan records

Revision ID: 11d3f5b7c9da
Revises: 10c2d4e6f8ab
Create Date: 2025-09-22 11:05:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision = '11d3f5b7c9da'
down_revision = '10c2d4e6f8ab'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    now = datetime.now(timezone.utc)

    loan_rows = connection.execute(sa.text(
        """
        SELECT DISTINCT
            player_id,
            player_name,
            nationality,
            age
        FROM loaned_players
        WHERE player_id IS NOT NULL
        """
    )).fetchall()

    if not loan_rows:
        return

    existing_ids = {
        row[0]
        for row in connection.execute(sa.text("SELECT player_id FROM players"))
    }

    insert_stmt = sa.text(
        """
        INSERT INTO players (
            player_id,
            name,
            firstname,
            lastname,
            nationality,
            age,
            created_at,
            updated_at
        )
        VALUES (
            :player_id,
            :name,
            :firstname,
            :lastname,
            :nationality,
            :age,
            :created_at,
            :updated_at
        )
        ON CONFLICT (player_id) DO UPDATE
        SET
            name = EXCLUDED.name,
            firstname = EXCLUDED.firstname,
            lastname = EXCLUDED.lastname,
            nationality = EXCLUDED.nationality,
            age = EXCLUDED.age,
            updated_at = EXCLUDED.updated_at
        """
    )

    for player_id, player_name, nationality, age in loan_rows:
        if player_id in existing_ids:
            continue
        name = player_name or f"Player {player_id}"
        parts = name.split()
        firstname = parts[0] if parts else None
        lastname = parts[-1] if len(parts) > 1 else None
        connection.execute(
            insert_stmt,
            {
                'player_id': player_id,
                'name': name,
                'firstname': firstname,
                'lastname': lastname,
                'nationality': nationality,
                'age': age,
                'created_at': now,
                'updated_at': now,
            }
        )


def downgrade():
    pass
