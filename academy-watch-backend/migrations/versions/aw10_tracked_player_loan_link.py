"""Add loaned_player_id FK and backfill TrackedPlayer from journey data

Revision ID: aw10
Revises: aw09
Create Date: 2026-02-07

Adds loaned_player_id column to tracked_players and backfills rows
from PlayerJourney.academy_club_ids for teams that haven't been seeded yet.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'aw10'
down_revision = 'aw09'
branch_labels = None
depends_on = None


def upgrade():
    # ── Schema change: add loaned_player_id FK ──
    op.add_column(
        'tracked_players',
        sa.Column('loaned_player_id', sa.Integer(), sa.ForeignKey('loaned_players.id'), nullable=True),
    )

    conn = op.get_bind()

    # ── Backfill TrackedPlayer rows from PlayerJourney.academy_club_ids ──
    #
    # For every journey with non-empty academy_club_ids, create a TrackedPlayer
    # row per academy club if one doesn't already exist.
    #
    # We use raw SQL to avoid importing models (Alembic best practice).
    journeys = conn.execute(text("""
        SELECT pj.id, pj.player_api_id, pj.player_name, pj.player_photo,
               pj.nationality, pj.birth_date, pj.academy_club_ids,
               pj.current_club_api_id, pj.current_club_name, pj.current_level
        FROM player_journeys pj
        WHERE pj.academy_club_ids IS NOT NULL
          AND pj.academy_club_ids != '[]'::jsonb
    """)).fetchall()

    for j in journeys:
        academy_ids = j.academy_club_ids  # JSONB → Python list
        if not academy_ids:
            continue

        for academy_api_id in academy_ids:
            # Find the Team row for this academy club (latest season, active)
            team_row = conn.execute(text("""
                SELECT id, name FROM teams
                WHERE team_id = :api_id AND is_active = true
                ORDER BY season DESC
                LIMIT 1
            """), {'api_id': academy_api_id}).fetchone()

            if not team_row:
                continue

            team_db_id = team_row.id
            team_name = team_row.name

            # Check unique constraint: skip if already exists
            existing = conn.execute(text("""
                SELECT id FROM tracked_players
                WHERE player_api_id = :pid AND team_id = :tid
            """), {'pid': j.player_api_id, 'tid': team_db_id}).fetchone()

            if existing:
                continue

            # Derive status: simple logic matching academy_classifier.py
            status = 'academy'
            loan_club_api_id = None
            loan_club_name = None
            if j.current_club_api_id and j.current_club_api_id != academy_api_id:
                # Check if current club is same org (youth suffix)
                current_name = (j.current_club_name or '').lower()
                parent_name = team_name.lower()
                if current_name != parent_name and not current_name.startswith(parent_name):
                    status = 'on_loan'
                    loan_club_api_id = j.current_club_api_id
                    loan_club_name = j.current_club_name
                elif j.current_level == 'First Team':
                    status = 'first_team'
            elif j.current_club_api_id == academy_api_id and j.current_level == 'First Team':
                status = 'first_team'

            conn.execute(text("""
                INSERT INTO tracked_players
                    (player_api_id, player_name, photo_url, nationality, birth_date,
                     team_id, status, loan_club_api_id, loan_club_name,
                     journey_id, data_source, data_depth, is_active,
                     created_at, updated_at)
                VALUES
                    (:pid, :pname, :photo, :nationality, :birth_date,
                     :team_id, :status, :loan_api_id, :loan_name,
                     :journey_id, 'journey-sync', 'full_stats', true,
                     NOW(), NOW())
            """), {
                'pid': j.player_api_id,
                'pname': j.player_name or f'Player {j.player_api_id}',
                'photo': j.player_photo,
                'nationality': j.nationality,
                'birth_date': j.birth_date,
                'team_id': team_db_id,
                'status': status,
                'loan_api_id': loan_club_api_id,
                'loan_name': loan_club_name,
                'journey_id': j.id,
            })

    # ── Backfill loaned_player_id for on-loan TrackedPlayers ──
    # Link each on-loan TrackedPlayer to the most recent active LoanedPlayer row
    conn.execute(text("""
        UPDATE tracked_players tp
        SET loaned_player_id = sub.lp_id
        FROM (
            SELECT DISTINCT ON (tp2.id)
                tp2.id AS tp_id,
                lp.id AS lp_id
            FROM tracked_players tp2
            JOIN teams t ON t.id = tp2.team_id
            JOIN loaned_players lp
                ON lp.player_id = tp2.player_api_id
                AND lp.primary_team_id = tp2.team_id
            WHERE tp2.status = 'on_loan'
              AND lp.is_active = true
            ORDER BY tp2.id, lp.updated_at DESC
        ) sub
        WHERE tp.id = sub.tp_id
    """))


def downgrade():
    op.drop_column('tracked_players', 'loaned_player_id')
