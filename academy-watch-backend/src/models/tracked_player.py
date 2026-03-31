"""
Tracked Player Model

Represents a player being tracked by a parent academy club.
One row per player per parent club — no duplication per window/season.
Replaces the old AcademyPlayer model for the Academy Watch redesign.
"""

from datetime import datetime, timezone
from src.models.league import db


class TrackedPlayer(db.Model):
    __tablename__ = 'tracked_players'

    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False, index=True)
    player_name = db.Column(db.String(200), nullable=False)
    photo_url = db.Column(db.String(500))
    position = db.Column(db.String(50))        # Goalkeeper, Defender, Midfielder, Attacker
    nationality = db.Column(db.String(100))
    birth_date = db.Column(db.String(20))
    age = db.Column(db.Integer)

    # Parent academy club
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False, index=True)

    # Current pathway status
    status = db.Column(db.String(20), nullable=False, default='academy')
    #   'academy' | 'on_loan' | 'first_team' | 'released' | 'sold'
    current_level = db.Column(db.String(20))
    #   'U18' | 'U21' | 'U23' | 'Reserve' | 'Senior'

    # Current club (loan club if on_loan, buying club if sold, new club if released)
    current_club_api_id = db.Column(db.Integer)
    current_club_name = db.Column(db.String(200))
    current_club_db_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)

    # Transfer fee when sold (raw string from API-Football, e.g. "€50M", "Free")
    sale_fee = db.Column(db.String(100))

    # Provenance
    data_source = db.Column(db.String(30), nullable=False, default='api-football')
    #   'api-football' | 'manual' | 'cohort-seed'
    data_depth = db.Column(db.String(20), nullable=False, default='full_stats')

    # Link to rich career data
    journey_id = db.Column(db.Integer, db.ForeignKey('player_journeys.id'))

    # When True, refresh-statuses will never change team_id — prevents
    # the classifier from reassigning parent club based on stale API data.
    pinned_parent = db.Column(db.Boolean, default=False, server_default='false')

    notes = db.Column(db.Text)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                          onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('player_api_id', 'team_id', name='uq_tracked_player_team'),
    )

    # Relationships
    team = db.relationship('Team', backref='tracked_players', lazy=True,
                           foreign_keys=[team_id])
    current_club = db.relationship('Team', foreign_keys=[current_club_db_id], lazy=True)
    journey = db.relationship('PlayerJourney', backref='tracked_player', lazy=True,
                             foreign_keys=[journey_id])
    def compute_stats(self):
        """Compute stats independently of AcademyPlayer.

        - full_stats: aggregate from FixturePlayerStats
        - events_only / limited: read from PlayerStatsCache
        """
        default_stats = {
            'appearances': 0,
            'goals': 0,
            'assists': 0,
            'minutes_played': 0,
            'saves': 0,
            'yellows': 0,
            'reds': 0,
            'stats_coverage': self.data_depth or 'full_stats',
        }

        if not self.current_club_api_id:
            return default_stats

        # Limited / events-only coverage → read from PlayerStatsCache
        if self.data_depth in ('events_only', 'profile_only'):
            from src.models.league import PlayerStatsCache
            cache = PlayerStatsCache.query.filter_by(
                player_api_id=self.player_api_id,
                team_api_id=self.current_club_api_id,
            ).order_by(PlayerStatsCache.season.desc()).first()
            if cache:
                return {
                    'appearances': cache.appearances or 0,
                    'goals': cache.goals or 0,
                    'assists': cache.assists or 0,
                    'minutes_played': cache.minutes_played or 0,
                    'saves': cache.saves or 0,
                    'yellows': cache.yellows or 0,
                    'reds': cache.reds or 0,
                    'stats_coverage': cache.stats_coverage or 'limited',
                }
            return default_stats

        # Full stats → aggregate from FixturePlayerStats
        from src.models.weekly import FixturePlayerStats
        from sqlalchemy import func

        stats = db.session.query(
            func.count().label('appearances'),
            func.coalesce(func.sum(FixturePlayerStats.goals), 0).label('goals'),
            func.coalesce(func.sum(FixturePlayerStats.assists), 0).label('assists'),
            func.coalesce(func.sum(FixturePlayerStats.minutes), 0).label('minutes_played'),
            func.coalesce(func.sum(FixturePlayerStats.saves), 0).label('saves'),
            func.coalesce(func.sum(FixturePlayerStats.yellows), 0).label('yellows'),
            func.coalesce(func.sum(FixturePlayerStats.reds), 0).label('reds'),
        ).filter(
            FixturePlayerStats.player_api_id == self.player_api_id,
            FixturePlayerStats.team_api_id == self.current_club_api_id,
        ).first()

        if not stats:
            return default_stats

        return {
            'appearances': stats.appearances or 0,
            'goals': int(stats.goals or 0),
            'assists': int(stats.assists or 0),
            'minutes_played': int(stats.minutes_played or 0),
            'saves': int(stats.saves or 0),
            'yellows': int(stats.yellows or 0),
            'reds': int(stats.reds or 0),
            'stats_coverage': 'full',
        }

    def to_dict(self):
        return {
            'id': self.id,
            'player_api_id': self.player_api_id,
            'player_name': self.player_name,
            'photo_url': self.photo_url,
            'position': self.position,
            'nationality': self.nationality,
            'birth_date': self.birth_date,
            'age': self.age,
            'team_id': self.team_id,
            'team_name': self.team.name if self.team else None,
            'team_logo': self.team.logo if self.team else None,
            'team_api_id': self.team.team_id if self.team else None,
            'status': self.status,
            'current_level': self.current_level,
            'current_club_api_id': self.current_club_api_id,
            'current_club_name': self.current_club_name,
            'current_club_db_id': self.current_club_db_id,
            'current_club_logo': self.current_club.logo if self.current_club else None,
            'sale_fee': self.sale_fee,
            'data_source': self.data_source,
            'data_depth': self.data_depth,
            'journey_id': self.journey_id,
            'pinned_parent': self.pinned_parent,
            'notes': self.notes,
            'is_active': self.is_active,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_public_dict(self):
        """Return a public-facing dict with fields expected by the frontend.
        Stats default to 0 here — the endpoint enriches them via batch query."""
        return {
            'id': self.id,
            'player_id': self.player_api_id,
            'player_name': self.player_name,
            'player_photo': self.photo_url,
            'position': self.position,
            'age': self.age,
            'nationality': self.nationality,
            'primary_team_id': self.team_id,
            'primary_team_name': self.team.name if self.team else None,
            'primary_team_api_id': self.team.team_id if self.team else None,
            'loan_team_name': self.current_club_name,
            'loan_team_api_id': self.current_club_api_id,
            'loan_team_db_id': self.current_club_db_id,
            'loan_team_logo': self.current_club.logo if self.current_club else None,
            'is_active': self.is_active,
            'status': self.status,
            'pathway_status': self.status,
            'current_level': self.current_level,
            'data_source': self.data_source,
            'data_depth': self.data_depth,
            'appearances': 0,
            'goals': 0,
            'assists': 0,
            'minutes_played': 0,
            'saves': 0,
            'yellows': 0,
            'reds': 0,
            'sale_fee': self.sale_fee,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
