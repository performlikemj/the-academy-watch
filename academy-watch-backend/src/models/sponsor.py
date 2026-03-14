from datetime import datetime, timezone
from src.models.league import db


class Sponsor(db.Model):
    __tablename__ = 'sponsors'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    image_url = db.Column(db.Text, nullable=False)
    link_url = db.Column(db.Text, nullable=False)
    description = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    display_order = db.Column(db.Integer, default=0, nullable=False)
    click_count = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'image_url': self.image_url,
            'link_url': self.link_url,
            'description': self.description,
            'is_active': self.is_active,
            'display_order': self.display_order,
            'click_count': self.click_count,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

    def to_public_dict(self):
        """Return only fields needed for public display."""
        return {
            'id': self.id,
            'name': self.name,
            'image_url': self.image_url,
            'link_url': self.link_url,
            'description': self.description,
        }

    def __repr__(self):
        return f'<Sponsor {self.name}>'

