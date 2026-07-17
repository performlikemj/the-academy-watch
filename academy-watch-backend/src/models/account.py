"""Append-only records for completed self-service account deletions."""

from src.models.league import db


class AccountDeletionEvent(db.Model):
    """PII-free audit record for one atomically completed account deletion.

    ``tombstone_user_id`` points at the per-deletion anonymous account that
    replaces the deleted user's non-null integrity references. The original
    user id and email are deliberately never copied into this table.
    """

    __tablename__ = "account_deletion_events"
    __table_args__ = (
        db.Index(
            "uq_account_deletion_events_tombstone_user",
            "tombstone_user_id",
            unique=True,
        ),
        db.Index("ix_account_deletion_events_requested_at", "requested_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    tombstone_user_id = db.Column(
        db.Integer,
        db.ForeignKey("user_accounts.id"),
        nullable=False,
    )
    requested_at = db.Column(db.DateTime, nullable=False)
    completed_at = db.Column(db.DateTime, nullable=False)
    counts = db.Column(db.JSON, nullable=False, default=dict)

    tombstone_user = db.relationship("UserAccount", foreign_keys=[tombstone_user_id])

    def to_dict(self):
        return {
            "id": self.id,
            "tombstone_user_id": self.tombstone_user_id,
            "requested_at": self.requested_at.isoformat() if self.requested_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "counts": self.counts or {},
        }


__all__ = ["AccountDeletionEvent"]
