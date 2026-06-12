"""Scout watchlist model — per-user saved players for the scout hub.

One row per (user, player). `last_snapshot` stores the stats JSON captured
at the last digest send so the next digest can render deltas.
"""

from datetime import UTC, datetime

from src.models.league import db


class ScoutWatchlistEntry(db.Model):
    __tablename__ = "scout_watchlist_entries"

    id = db.Column(db.Integer, primary_key=True)
    # No standalone indexes: the composite unique below leads on
    # user_account_id, which serves every user-scoped query.
    user_account_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    player_api_id = db.Column(db.Integer, nullable=False)
    note = db.Column(db.Text)
    last_snapshot = db.Column(db.Text)  # JSON string of stats at last digest send
    last_digest_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    __table_args__ = (db.UniqueConstraint("user_account_id", "player_api_id", name="uq_scout_watchlist_user_player"),)

    user = db.relationship("UserAccount", backref=db.backref("scout_watchlist_entries", lazy="dynamic"))

    def to_dict(self):
        return {
            "player_api_id": self.player_api_id,
            "note": self.note,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
