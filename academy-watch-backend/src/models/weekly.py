from datetime import datetime, timezone
from src.models.league import db

# ------------------------------------------------------------------
# 📊 WEEKLY REPORT / FIXTURE PERSISTENCE TABLES
# ------------------------------------------------------------------

class WeeklyLoanReport(db.Model):
    __tablename__ = 'weekly_loan_reports'
    id = db.Column(db.Integer, primary_key=True)
    parent_team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False)
    parent_team_api_id = db.Column(db.Integer, nullable=False)
    season = db.Column(db.Integer, nullable=False)
    week_start_date = db.Column(db.Date, nullable=False)
    week_end_date = db.Column(db.Date, nullable=False)
    include_team_stats = db.Column(db.Boolean, default=False)
    generated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    meta_json = db.Column(db.Text)
    __table_args__ = (
        db.UniqueConstraint('parent_team_id', 'week_start_date', 'week_end_date',
                            name='uq_weekly_parent_week'),
    )


class Fixture(db.Model):
    __tablename__ = 'fixtures'
    id = db.Column(db.Integer, primary_key=True)
    fixture_id_api = db.Column(db.Integer, unique=True, nullable=False)
    date_utc = db.Column(db.DateTime)
    season = db.Column(db.Integer, nullable=False)
    competition_name = db.Column(db.String(100))
    home_team_api_id = db.Column(db.Integer)
    away_team_api_id = db.Column(db.Integer)
    home_goals = db.Column(db.Integer, default=0)
    away_goals = db.Column(db.Integer, default=0)
    raw_json = db.Column(db.Text)


class FixtureTeamStats(db.Model):
    __tablename__ = 'fixture_team_stats'
    id = db.Column(db.Integer, primary_key=True)
    fixture_id = db.Column(db.Integer, db.ForeignKey('fixtures.id'), nullable=False)
    team_api_id = db.Column(db.Integer, nullable=False)
    stats_json = db.Column(db.Text)
    __table_args__ = (
        db.UniqueConstraint('fixture_id', 'team_api_id', name='uq_fixture_team'),
    )


class FixturePlayerStats(db.Model):
    __tablename__ = 'fixture_player_stats'
    id = db.Column(db.Integer, primary_key=True)
    fixture_id = db.Column(db.Integer, db.ForeignKey('fixtures.id'), nullable=False)
    player_api_id = db.Column(db.Integer, nullable=False)
    team_api_id = db.Column(db.Integer, nullable=False)
    
    # Basic game info
    minutes = db.Column(db.Integer, default=0)
    position = db.Column(db.String(10))  # G, D, M, F
    number = db.Column(db.Integer)  # Jersey number
    rating = db.Column(db.Float)  # Match rating
    captain = db.Column(db.Boolean, default=False)
    substitute = db.Column(db.Boolean, default=False)
    
    # Goals and assists
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    goals_conceded = db.Column(db.Integer)  # For goalkeepers
    saves = db.Column(db.Integer)  # For goalkeepers
    
    # Cards
    yellows = db.Column(db.Integer, default=0)
    reds = db.Column(db.Integer, default=0)
    
    # Shots
    shots_total = db.Column(db.Integer)
    shots_on = db.Column(db.Integer)
    
    # Passes
    passes_total = db.Column(db.Integer)
    passes_key = db.Column(db.Integer)  # Key passes
    passes_accuracy = db.Column(db.String(10))  # e.g. "68%"
    
    # Tackles
    tackles_total = db.Column(db.Integer)
    tackles_blocks = db.Column(db.Integer)
    tackles_interceptions = db.Column(db.Integer)
    
    # Duels
    duels_total = db.Column(db.Integer)
    duels_won = db.Column(db.Integer)
    
    # Dribbles
    dribbles_attempts = db.Column(db.Integer)
    dribbles_success = db.Column(db.Integer)
    dribbles_past = db.Column(db.Integer)
    
    # Fouls
    fouls_drawn = db.Column(db.Integer)
    fouls_committed = db.Column(db.Integer)
    
    # Penalties
    penalty_won = db.Column(db.Integer)
    penalty_committed = db.Column(db.Integer)
    penalty_scored = db.Column(db.Integer)
    penalty_missed = db.Column(db.Integer)
    penalty_saved = db.Column(db.Integer)  # For goalkeepers
    
    # Other
    offsides = db.Column(db.Integer)
    
    # Raw JSON for future expansion
    raw_json = db.Column(db.Text)
    
    __table_args__ = (
        db.UniqueConstraint('fixture_id', 'player_api_id',
                            name='uq_fixture_player'),
    )
    
    def to_dict(self):
        """Convert player stats to dictionary for API responses."""
        return {
            'id': self.id,
            'fixture_id': self.fixture_id,
            'player_api_id': self.player_api_id,
            'team_api_id': self.team_api_id,
            'minutes': self.minutes,
            'position': self.position,
            'number': self.number,
            'rating': self.rating,
            'captain': self.captain,
            'substitute': self.substitute,
            'goals': self.goals,
            'assists': self.assists,
            'goals_conceded': self.goals_conceded,
            'saves': self.saves,
            'yellows': self.yellows,
            'reds': self.reds,
            'shots': {
                'total': self.shots_total,
                'on': self.shots_on
            },
            'passes': {
                'total': self.passes_total,
                'key': self.passes_key,
                'accuracy': self.passes_accuracy
            },
            'tackles': {
                'total': self.tackles_total,
                'blocks': self.tackles_blocks,
                'interceptions': self.tackles_interceptions
            },
            'duels': {
                'total': self.duels_total,
                'won': self.duels_won
            },
            'dribbles': {
                'attempts': self.dribbles_attempts,
                'success': self.dribbles_success,
                'past': self.dribbles_past
            },
            'fouls': {
                'drawn': self.fouls_drawn,
                'committed': self.fouls_committed
            },
            'penalty': {
                'won': self.penalty_won,
                'committed': self.penalty_committed,
                'scored': self.penalty_scored,
                'missed': self.penalty_missed,
                'saved': self.penalty_saved
            },
            'offsides': self.offsides,
            'raw_json': self.raw_json
        }


class WeeklyLoanAppearance(db.Model):
    __tablename__ = 'weekly_loan_appearances'
    id = db.Column(db.Integer, primary_key=True)
    weekly_report_id = db.Column(db.Integer,
                                 db.ForeignKey('weekly_loan_reports.id'),
                                 nullable=False)
    loaned_player_id = db.Column(db.Integer,
                                 db.ForeignKey('loaned_players.id'),
                                 nullable=False)
    player_api_id = db.Column(db.Integer, nullable=False)
    fixture_id = db.Column(db.Integer, db.ForeignKey('fixtures.id'),
                           nullable=False)
    team_api_id = db.Column(db.Integer, nullable=False)
    appeared = db.Column(db.Boolean, default=False)
    minutes = db.Column(db.Integer, default=0)
    goals = db.Column(db.Integer, default=0)
    assists = db.Column(db.Integer, default=0)
    yellows = db.Column(db.Integer, default=0)
    reds = db.Column(db.Integer, default=0)
    __table_args__ = (
        db.UniqueConstraint('weekly_report_id', 'loaned_player_id',
                            'fixture_id', name='uq_week_player_fixture'),
    )

