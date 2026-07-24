"""Persistent user-level blocks for contact and private interest surfaces."""

from datetime import UTC, datetime

from src.models.league import db


def _utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


class UserBlock(db.Model):
    """One user's enduring block of another ordinary user account."""

    __tablename__ = "user_blocks"
    __table_args__ = (
        db.UniqueConstraint(
            "blocker_user_id",
            "blocked_user_id",
            name="uq_user_blocks_pair",
        ),
        db.CheckConstraint(
            "blocker_user_id <> blocked_user_id",
            name="ck_user_blocks_no_self",
        ),
        db.Index(
            "ix_user_blocks_blocked_user",
            "blocked_user_id",
            "blocker_user_id",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    blocker_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user_accounts.id"),
        nullable=False,
    )
    blocked_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user_accounts.id"),
        nullable=False,
    )
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)


__all__ = ["UserBlock"]
