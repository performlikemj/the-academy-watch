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

    # If on loan, where
    loan_club_api_id = db.Column(db.Integer)
    loan_club_name = db.Column(db.String(200))

    # Provenance
    data_source = db.Column(db.String(30), nullable=False, default='api-football')
    #   'api-football' | 'manual' | 'cohort-seed'
    data_depth = db.Column(db.String(20), nullable=False, default='full_stats')

    # Link to rich career data
    journey_id = db.Column(db.Integer, db.ForeignKey('player_journeys.id'))

    # Link to active AcademyPlayer row (if on loan)
    loaned_player_id = db.Column(db.Integer, db.ForeignKey('loaned_players.id'), nullable=True)

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
    team = db.relationship('Team', backref='tracked_players', lazy=True)
    journey = db.relationship('PlayerJourney', backref='tracked_player', lazy=True,
                             foreign_keys=[journey_id])
    loaned_player = db.relationship('AcademyPlayer', backref='tracked_player_link', lazy=True,
                                    foreign_keys=[loaned_player_id])

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
            'loan_club_api_id': self.loan_club_api_id,
            'loan_club_name': self.loan_club_name,
            'data_source': self.data_source,
            'data_depth': self.data_depth,
            'journey_id': self.journey_id,
            'loaned_player_id': self.loaned_player_id,
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
            'loan_team_name': self.loan_club_name,
            'loan_team_api_id': self.loan_club_api_id,
            'loan_team_logo': None,  # Caller can enrich
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
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
