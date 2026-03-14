from datetime import datetime, timezone

from src.models.league import db


class TeamFormation(db.Model):
    __tablename__ = 'team_formations'

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=False)
    formation_type = db.Column(db.String(10), nullable=False)
    positions = db.Column(db.JSON, default=list)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        db.UniqueConstraint('team_id', 'name', name='uq_team_formation_name'),
    )

    def to_dict(self):
        return {
            'id': self.id,
            'team_id': self.team_id,
            'name': self.name,
            'formation_type': self.formation_type,
            'positions': self.positions or [],
            'notes': self.notes,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }
