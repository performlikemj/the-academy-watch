"""Public player fans — one row per account and signed player identity."""

from datetime import UTC, datetime

from src.models.league import db


def _utcnow_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class PlayerFan(db.Model):
    __tablename__ = "player_fans"

    id = db.Column(db.Integer, primary_key=True)
    user_account_id = db.Column(
        db.Integer,
        db.ForeignKey("user_accounts.id", ondelete="CASCADE"),
        nullable=False,
    )
    player_api_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=_utcnow_naive,
        server_default=db.func.now(),
    )

    __table_args__ = (
        db.CheckConstraint("player_api_id <> 0", name="ck_player_fans_nonzero"),
        db.UniqueConstraint("user_account_id", "player_api_id", name="uq_player_fans_user_player"),
        db.Index("ix_player_fans_player_created", "player_api_id", "created_at"),
    )

    user = db.relationship("UserAccount", backref=db.backref("player_fans", lazy="dynamic"))

    def to_dict(self):
        return {
            "player_api_id": self.player_api_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


__all__ = ["PlayerFan"]
