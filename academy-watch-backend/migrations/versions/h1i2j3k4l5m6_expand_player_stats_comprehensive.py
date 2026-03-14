"""expand player stats comprehensive

Revision ID: h1i2j3k4l5m6
Revises: ab12cd34ef56
Create Date: 2025-10-07 20:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'h1i2j3k4l5m6'
down_revision = 'ab12cd34ef56'
branch_labels = None
depends_on = None


def _ensure_weekly_tables(inspector):
    """Recreate weekly reporting tables when they were dropped by earlier revisions."""

    if not inspector.has_table('fixtures'):
        op.create_table(
            'fixtures',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('fixture_id_api', sa.Integer, nullable=False),
            sa.Column('date_utc', sa.DateTime()),
            sa.Column('season', sa.Integer, nullable=False),
            sa.Column('competition_name', sa.String(100)),
            sa.Column('home_team_api_id', sa.Integer),
            sa.Column('away_team_api_id', sa.Integer),
            sa.Column('home_goals', sa.Integer),
            sa.Column('away_goals', sa.Integer),
            sa.Column('raw_json', sa.Text),
            sa.UniqueConstraint('fixture_id_api', name='fixtures_fixture_id_api_key'),
        )
        inspector = sa.inspect(op.get_bind())

    if not inspector.has_table('fixture_team_stats'):
        op.create_table(
            'fixture_team_stats',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('fixture_id', sa.Integer, sa.ForeignKey('fixtures.id', ondelete='CASCADE'), nullable=False),
            sa.Column('team_api_id', sa.Integer, nullable=False),
            sa.Column('stats_json', sa.Text),
            sa.UniqueConstraint('fixture_id', 'team_api_id', name='uq_fixture_team'),
        )
        inspector = sa.inspect(op.get_bind())

    if not inspector.has_table('weekly_loan_reports'):
        op.create_table(
            'weekly_loan_reports',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('parent_team_id', sa.Integer, sa.ForeignKey('teams.id', ondelete='CASCADE'), nullable=False),
            sa.Column('parent_team_api_id', sa.Integer, nullable=False),
            sa.Column('season', sa.Integer, nullable=False),
            sa.Column('week_start_date', sa.Date, nullable=False),
            sa.Column('week_end_date', sa.Date, nullable=False),
            sa.Column('include_team_stats', sa.Boolean()),
            sa.Column('generated_at', sa.DateTime()),
            sa.Column('meta_json', sa.Text),
            sa.UniqueConstraint('parent_team_id', 'week_start_date', 'week_end_date', name='uq_weekly_parent_week'),
        )
        inspector = sa.inspect(op.get_bind())

    if not inspector.has_table('weekly_loan_appearances'):
        op.create_table(
            'weekly_loan_appearances',
            sa.Column('id', sa.Integer, primary_key=True),
            sa.Column('weekly_report_id', sa.Integer, sa.ForeignKey('weekly_loan_reports.id', ondelete='CASCADE'), nullable=False),
            sa.Column('loaned_player_id', sa.Integer, sa.ForeignKey('loaned_players.id', ondelete='CASCADE'), nullable=False),
            sa.Column('player_api_id', sa.Integer, nullable=False),
            sa.Column('fixture_id', sa.Integer, sa.ForeignKey('fixtures.id', ondelete='CASCADE'), nullable=False),
            sa.Column('team_api_id', sa.Integer, nullable=False),
            sa.Column('appeared', sa.Boolean()),
            sa.Column('minutes', sa.Integer),
            sa.Column('goals', sa.Integer),
            sa.Column('assists', sa.Integer),
            sa.Column('yellows', sa.Integer),
            sa.Column('reds', sa.Integer),
            sa.UniqueConstraint('weekly_report_id', 'loaned_player_id', 'fixture_id', name='uq_week_player_fixture'),
        )


def _ensure_fixture_player_stats(inspector):
    """Create fixture_player_stats or expand it in place."""

    base_columns = [
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('fixture_id', sa.Integer, sa.ForeignKey('fixtures.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_api_id', sa.Integer, nullable=False),
        sa.Column('team_api_id', sa.Integer, nullable=False),
        sa.Column('minutes', sa.Integer),
        sa.Column('goals', sa.Integer),
        sa.Column('assists', sa.Integer),
        sa.Column('yellows', sa.Integer),
        sa.Column('reds', sa.Integer),
        sa.Column('raw_json', sa.Text),
    ]

    extra_columns = [
        ('position', sa.Column('position', sa.String(10))),
        ('number', sa.Column('number', sa.Integer())),
        ('rating', sa.Column('rating', sa.Float())),
        ('captain', sa.Column('captain', sa.Boolean())),
        ('substitute', sa.Column('substitute', sa.Boolean())),
        ('goals_conceded', sa.Column('goals_conceded', sa.Integer())),
        ('saves', sa.Column('saves', sa.Integer())),
        ('shots_total', sa.Column('shots_total', sa.Integer())),
        ('shots_on', sa.Column('shots_on', sa.Integer())),
        ('passes_total', sa.Column('passes_total', sa.Integer())),
        ('passes_key', sa.Column('passes_key', sa.Integer())),
        ('passes_accuracy', sa.Column('passes_accuracy', sa.String(10))),
        ('tackles_total', sa.Column('tackles_total', sa.Integer())),
        ('tackles_blocks', sa.Column('tackles_blocks', sa.Integer())),
        ('tackles_interceptions', sa.Column('tackles_interceptions', sa.Integer())),
        ('duels_total', sa.Column('duels_total', sa.Integer())),
        ('duels_won', sa.Column('duels_won', sa.Integer())),
        ('dribbles_attempts', sa.Column('dribbles_attempts', sa.Integer())),
        ('dribbles_success', sa.Column('dribbles_success', sa.Integer())),
        ('dribbles_past', sa.Column('dribbles_past', sa.Integer())),
        ('fouls_drawn', sa.Column('fouls_drawn', sa.Integer())),
        ('fouls_committed', sa.Column('fouls_committed', sa.Integer())),
        ('penalty_won', sa.Column('penalty_won', sa.Integer())),
        ('penalty_committed', sa.Column('penalty_committed', sa.Integer())),
        ('penalty_scored', sa.Column('penalty_scored', sa.Integer())),
        ('penalty_missed', sa.Column('penalty_missed', sa.Integer())),
        ('penalty_saved', sa.Column('penalty_saved', sa.Integer())),
        ('offsides', sa.Column('offsides', sa.Integer())),
    ]

    if not inspector.has_table('fixture_player_stats'):
        op.create_table(
            'fixture_player_stats',
            *base_columns,
            *[column for _, column in extra_columns],
            sa.UniqueConstraint('fixture_id', 'player_api_id', name='uq_fixture_player'),
        )
        return

    existing_columns = {col['name'] for col in inspector.get_columns('fixture_player_stats')}
    for name, column in extra_columns:
        if name not in existing_columns:
            op.add_column('fixture_player_stats', column)


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    _ensure_weekly_tables(inspector)
    inspector = sa.inspect(op.get_bind())
    _ensure_fixture_player_stats(inspector)


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table('fixture_player_stats'):
        existing_columns = {col['name'] for col in inspector.get_columns('fixture_player_stats')}
        for column_name in [
            'offsides',
            'penalty_saved',
            'penalty_missed',
            'penalty_scored',
            'penalty_committed',
            'penalty_won',
            'fouls_committed',
            'fouls_drawn',
            'dribbles_past',
            'dribbles_success',
            'dribbles_attempts',
            'duels_won',
            'duels_total',
            'tackles_interceptions',
            'tackles_blocks',
            'tackles_total',
            'passes_accuracy',
            'passes_key',
            'passes_total',
            'shots_on',
            'shots_total',
            'saves',
            'goals_conceded',
            'substitute',
            'captain',
            'rating',
            'number',
            'position',
        ]:
            if column_name in existing_columns:
                op.drop_column('fixture_player_stats', column_name)
