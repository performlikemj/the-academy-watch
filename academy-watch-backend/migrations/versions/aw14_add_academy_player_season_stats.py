"""Add academy_player_season_stats table

Revision ID: aw14
Revises: aw13
Create Date: 2026-04-01

Stores season-level aggregated stats for academy players fetched from
API-Football /players endpoint. Youth league fixture endpoints return
empty lineups/events, so this table captures the rich data available
at the season level instead.
"""

from alembic import op
import sqlalchemy as sa
from migrations._migration_helpers import table_exists

revision = 'aw14'
down_revision = 'z9a1b2c3d4e5'
branch_labels = None
depends_on = None


def upgrade():
    if table_exists('academy_player_season_stats'):
        return

    op.create_table(
        'academy_player_season_stats',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('player_api_id', sa.Integer(), nullable=False, index=True),
        sa.Column('player_name', sa.String(200)),
        sa.Column('league_api_id', sa.Integer(), nullable=False),
        sa.Column('league_name', sa.String(200)),
        sa.Column('team_api_id', sa.Integer()),
        sa.Column('team_name', sa.String(200)),
        sa.Column('season', sa.Integer(), nullable=False),

        # Core stats
        sa.Column('appearances', sa.Integer(), server_default='0'),
        sa.Column('lineups', sa.Integer(), server_default='0'),
        sa.Column('minutes', sa.Integer(), server_default='0'),
        sa.Column('rating', sa.Float()),
        sa.Column('goals', sa.Integer(), server_default='0'),
        sa.Column('assists', sa.Integer(), server_default='0'),
        sa.Column('yellow_cards', sa.Integer(), server_default='0'),
        sa.Column('red_cards', sa.Integer(), server_default='0'),

        # Extended stats
        sa.Column('shots_total', sa.Integer()),
        sa.Column('shots_on', sa.Integer()),
        sa.Column('passes_total', sa.Integer()),
        sa.Column('passes_key', sa.Integer()),
        sa.Column('passes_accuracy', sa.Float()),
        sa.Column('tackles_total', sa.Integer()),
        sa.Column('interceptions', sa.Integer()),
        sa.Column('duels_total', sa.Integer()),
        sa.Column('duels_won', sa.Integer()),
        sa.Column('dribbles_attempts', sa.Integer()),
        sa.Column('dribbles_success', sa.Integer()),
        sa.Column('fouls_drawn', sa.Integer()),
        sa.Column('fouls_committed', sa.Integer()),
        sa.Column('penalty_scored', sa.Integer()),
        sa.Column('penalty_missed', sa.Integer()),

        # Link to tracked player
        sa.Column('tracked_player_id', sa.Integer(),
                  sa.ForeignKey('tracked_players.id'), nullable=True),

        sa.Column('updated_at', sa.DateTime()),

        sa.UniqueConstraint('player_api_id', 'league_api_id', 'season',
                            name='uq_academy_player_season_stats'),
    )


def downgrade():
    op.drop_table('academy_player_season_stats')
