"""Append-only moderation decisions used by showcase trust rules."""

from datetime import UTC, datetime

from src.models.league import db

MODERATION_ACTIONS = frozenset({"approved", "rejected", "revoked", "suppressed"})


class ShowcaseModerationEvent(db.Model):
    """One immutable moderation decision.

    Callers append through :func:`record_moderation_event`; no update or delete
    helper is intentionally exposed.
    """

    __tablename__ = "showcase_moderation_events"
    __table_args__ = (
        db.CheckConstraint(
            "action IN ('approved','rejected','revoked','suppressed')",
            name="ck_showcase_moderation_events_action",
        ),
        db.Index(
            "ix_showcase_moderation_events_user_created",
            "user_account_id",
            "created_at",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_account_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=True)
    target_kind = db.Column(db.String(32), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    action = db.Column(db.String(32), nullable=False)
    actor_email = db.Column(db.String(255))
    event_metadata = db.Column("metadata", db.JSON)
    created_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        server_default=db.func.now(),
    )

    user_account = db.relationship("UserAccount", foreign_keys=[user_account_id])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user_account_id": self.user_account_id,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "action": self.action,
            "actor_email": self.actor_email,
            "metadata": self.event_metadata,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


def record_moderation_event(
    *,
    user_account_id: int | None,
    target_kind: str,
    target_id: int,
    action: str,
    actor_email: str | None = None,
    metadata: dict | None = None,
    session=None,
) -> ShowcaseModerationEvent:
    """Append an event to the caller's transaction without committing it."""
    if action not in MODERATION_ACTIONS:
        raise ValueError(f"action must be one of {sorted(MODERATION_ACTIONS)}")
    session = session or db.session
    event = ShowcaseModerationEvent(
        user_account_id=user_account_id,
        target_kind=target_kind,
        target_id=target_id,
        action=action,
        actor_email=actor_email,
        event_metadata=metadata,
    )
    session.add(event)
    return event


__all__ = ["ShowcaseModerationEvent", "record_moderation_event"]
