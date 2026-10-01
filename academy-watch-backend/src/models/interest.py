"""Floodlight interest intake: no account creation or email delivery."""

from datetime import UTC, datetime

from src.models.league import db

INTEREST_FEATURES = (
    "early_access",
    "clubs_near_you",
    "opportunities",
    "player_applications",
    "recruiting",
    "club_staff",
)
INTEREST_ROLES = ("club", "player", "parent", "scout", "coach", "other")


class InterestSignup(db.Model):
    __tablename__ = "interest_signups"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(254), nullable=False)
    feature = db.Column(db.String(40), nullable=False)
    role = db.Column(db.String(20), nullable=True)
    source_path = db.Column(db.String(500), nullable=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        server_default=db.func.now(),
    )
    __table_args__ = (
        db.UniqueConstraint("email", "feature", name="uq_interest_signups_email_feature"),
        db.Index("ix_interest_signups_feature", "feature"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "email": self.email,
            "feature": self.feature,
            "role": self.role,
            "source_path": self.source_path,
            "created_at": self.created_at.isoformat() + "Z",
        }
