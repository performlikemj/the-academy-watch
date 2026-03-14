"""
Academy Cohort Models

Tracks groups of players who appeared for a club in youth leagues/seasons,
with "where are they now" snapshots for each member.
"""

from datetime import datetime, timezone
from src.models.league import db


class AcademyCohort(db.Model):
    """Represents all players who appeared for a club in a youth league/season"""
    __tablename__ = 'academy_cohorts'

    id = db.Column(db.Integer, primary_key=True)
    team_api_id = db.Column(db.Integer, nullable=False, index=True)
    team_name = db.Column(db.String(200))
    team_logo = db.Column(db.String(500))
    league_api_id = db.Column(db.Integer, nullable=False)
    league_name = db.Column(db.String(200))
    league_level = db.Column(db.String(30))
    season = db.Column(db.Integer, nullable=False)

    # Analytics (denormalized)
    total_players = db.Column(db.Integer, default=0)
    players_first_team = db.Column(db.Integer, default=0)
    players_on_loan = db.Column(db.Integer, default=0)
    players_still_academy = db.Column(db.Integer, default=0)
    players_released = db.Column(db.Integer, default=0)

    # Sync tracking
    sync_status = db.Column(db.String(30), default='pending')
    seeded_at = db.Column(db.DateTime)
    journeys_synced_at = db.Column(db.DateTime)
    seed_job_id = db.Column(db.String(36))
    sync_error = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    # Relationships
    members = db.relationship('CohortMember', backref='cohort', lazy='dynamic',
                              cascade='all, delete-orphan')

    __table_args__ = (
        db.UniqueConstraint('team_api_id', 'league_api_id', 'season',
                            name='uq_academy_cohort'),
    )

    def to_dict(self, include_members=False):
        data = {
            'id': self.id,
            'team_api_id': self.team_api_id,
            'team_name': self.team_name,
            'team_logo': self.team_logo,
            'league_api_id': self.league_api_id,
            'league_name': self.league_name,
            'league_level': self.league_level,
            'season': self.season,
            'analytics': {
                'total_players': self.total_players,
                'players_first_team': self.players_first_team,
                'players_on_loan': self.players_on_loan,
                'players_still_academy': self.players_still_academy,
                'players_released': self.players_released,
            },
            'sync_status': self.sync_status,
            'seeded_at': self.seeded_at.isoformat() if self.seeded_at else None,
            'journeys_synced_at': self.journeys_synced_at.isoformat() if self.journeys_synced_at else None,
            'seed_job_id': self.seed_job_id,
            'sync_error': self.sync_error,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

        if include_members:
            data['members'] = [m.to_dict() for m in self.members.all()]

        return data


class CohortMember(db.Model):
    """Links a player to a cohort with 'where are they now' snapshot"""
    __tablename__ = 'cohort_members'

    id = db.Column(db.Integer, primary_key=True)
    cohort_id = db.Column(db.Integer, db.ForeignKey('academy_cohorts.id'), nullable=False, index=True)

    # Player identity
    player_api_id = db.Column(db.Integer, nullable=False)
    player_name = db.Column(db.String(200))
    player_photo = db.Column(db.String(500))
    nationality = db.Column(db.String(100))
    birth_date = db.Column(db.String(20))
    position = db.Column(db.String(50))

    # Cohort stats
    appearances_in_cohort = db.Column(db.Integer, default=0)
    goals_in_cohort = db.Column(db.Integer, default=0)
    assists_in_cohort = db.Column(db.Integer, default=0)
    minutes_in_cohort = db.Column(db.Integer, default=0)

    # Current snapshot (denormalized from PlayerJourney)
    current_club_api_id = db.Column(db.Integer)
    current_club_name = db.Column(db.String(200))
    current_level = db.Column(db.String(30))
    current_status = db.Column(db.String(30), default='unknown')

    # Career milestones
    first_team_debut_season = db.Column(db.Integer)
    total_first_team_apps = db.Column(db.Integer, default=0)
    total_clubs = db.Column(db.Integer, default=0)
    total_loan_spells = db.Column(db.Integer, default=0)

    # FK to PlayerJourney
    journey_id = db.Column(db.Integer, db.ForeignKey('player_journeys.id'), nullable=True)

    # Sync tracking
    journey_synced = db.Column(db.Boolean, default=False)
    journey_sync_error = db.Column(db.Text)

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('cohort_id', 'player_api_id', name='uq_cohort_member'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'cohort_id': self.cohort_id,
            'player_api_id': self.player_api_id,
            'player_name': self.player_name,
            'player_photo': self.player_photo,
            'nationality': self.nationality,
            'birth_date': self.birth_date,
            'position': self.position,
            'cohort_stats': {
                'appearances': self.appearances_in_cohort,
                'goals': self.goals_in_cohort,
                'assists': self.assists_in_cohort,
                'minutes': self.minutes_in_cohort,
            },
            'current': {
                'club_api_id': self.current_club_api_id,
                'club_name': self.current_club_name,
                'level': self.current_level,
                'status': self.current_status,
            },
            'career': {
                'first_team_debut_season': self.first_team_debut_season,
                'total_first_team_apps': self.total_first_team_apps,
                'total_clubs': self.total_clubs,
                'total_loan_spells': self.total_loan_spells,
            },
            'journey_id': self.journey_id,
            'journey_synced': self.journey_synced,
            'journey_sync_error': self.journey_sync_error,
        }
