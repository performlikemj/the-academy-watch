"""Player takedown requests and reversible publication suppressions."""

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import validates
from src.models.league import db
from src.services.player_suppression_crypto import EncryptedSuppressionText


def _iso(value):
    return value.isoformat() if value else None


class PlayerSuppression(db.Model):
    """One request lifecycle for an API-Football player identity.

    The partial unique index permits history after a rejection/lift while
    ensuring only one open (requested or active) lifecycle can exist at once.
    ``player_api_id`` deliberately has no foreign key: neutral public intake
    must accept the same request whether or not the platform knows the player.
    """

    __tablename__ = "player_suppressions"
    __table_args__ = (
        db.CheckConstraint(
            "reason_code IN ('guardian_request','player_request','legal','admin_other')",
            name="ck_player_suppressions_reason",
        ),
        db.CheckConstraint(
            "requester_role IN ('player','guardian','club','other')",
            name="ck_player_suppressions_requester_role",
        ),
        db.CheckConstraint(
            "status IN ('requested','active','lifted','rejected')",
            name="ck_player_suppressions_status",
        ),
        db.Index(
            "uq_player_suppressions_open_player",
            "player_api_id",
            unique=True,
            postgresql_where=sa.text("status IN ('requested', 'active')"),
            sqlite_where=sa.text("status IN ('requested', 'active')"),
        ),
        db.Index("ix_player_suppressions_status_created", "status", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False)
    reason_code = db.Column(db.String(30), nullable=False)
    requester_role = db.Column(db.String(20), nullable=False)
    # Plaintext is bounded by the route before this encrypted-at-rest field is bound.
    requester_contact = db.Column(EncryptedSuppressionText(), nullable=False)
    request_statement = db.Column(EncryptedSuppressionText(), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="requested", server_default="requested")
    notes = db.Column(EncryptedSuppressionText())
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    decided_at = db.Column(db.DateTime)
    decided_by = db.Column(db.String(200))

    @validates("requester_contact")
    def _validate_requester_contact(self, key, value):
        if not isinstance(value, str) or not value or len(value) > 254:
            raise ValueError("requester_contact must be a non-empty string of at most 254 characters")
        return value

    @validates("request_statement", "notes")
    def _validate_bounded_text(self, key, value):
        if value is not None and (not isinstance(value, str) or len(value) > 2000):
            raise ValueError(f"{key} must be a string of at most 2000 characters")
        return value

    def admin_dict(self) -> dict:
        return {
            "id": self.id,
            "player_api_id": self.player_api_id,
            "reason_code": self.reason_code,
            "requester_role": self.requester_role,
            "requester_contact": self.requester_contact,
            "request_statement": self.request_statement,
            "status": self.status,
            "notes": self.notes,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "decided_at": _iso(self.decided_at),
            "decided_by": self.decided_by,
        }


__all__ = ["PlayerSuppression"]
