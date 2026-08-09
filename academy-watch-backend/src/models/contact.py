"""Scout-to-player contact rail models.

Contact requests and messages use opaque UUID primary keys because their
identifiers cross the API boundary. Audit events and outcomes are append-only
records: the application exposes no update or delete path for either table.
"""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from src.models.league import db


def _utcnow():
    # Columns are ``timestamp without time zone`` throughout this repository;
    # store a naive UTC value so SQLite and Postgres compare identically.
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value):
    return value.isoformat() if value else None


class ContactRequest(db.Model):
    """A verified scout's introduction request to an adult player claimant."""

    __tablename__ = "contact_requests"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending','accepted','declined','withdrawn','expired')",
            name="ck_contact_requests_status",
        ),
        db.CheckConstraint(
            "routing_mode IN ('direct','club_included','club_notified')",
            name="ck_contact_requests_routing_mode",
        ),
        db.CheckConstraint(
            "club_consent_status IS NULL OR club_consent_status IN ('pending','granted','declined')",
            name="ck_contact_requests_club_consent",
        ),
        db.Index(
            "uq_contact_requests_active_scout_player",
            "scout_user_id",
            "player_api_id",
            unique=True,
            postgresql_where=sa.text("status IN ('pending', 'accepted')"),
            sqlite_where=sa.text("status IN ('pending', 'accepted')"),
        ),
        db.Index("ix_contact_requests_scout_created", "scout_user_id", "created_at"),
        db.Index("ix_contact_requests_claim_created", "claim_id", "created_at"),
        db.Index("ix_contact_requests_player_created", "player_api_id", "created_at"),
        db.Index("ix_contact_requests_status_expires", "status", "expires_at"),
        db.Index("ix_contact_requests_club_program_created", "club_program_id", "created_at"),
    )

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    scout_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    player_api_id = db.Column(db.Integer, nullable=False)
    claim_id = db.Column(db.Integer, db.ForeignKey("player_profile_claims.id"), nullable=True)
    message = db.Column(db.String(2000), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    routing_mode = db.Column(db.String(20), nullable=False, default="direct", server_default="direct")
    # Logical soft link to independently ordered gf01 (no hard FK by design).
    club_program_id = db.Column(db.Integer)
    club_consent_status = db.Column(db.String(20))
    club_consent_at = db.Column(db.DateTime)
    club_consent_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"))
    club_consent_note = db.Column(db.String(1000))
    permission_attestation = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=sa.false(),
    )
    permission_attested_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)
    responded_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime, nullable=False)

    scout = db.relationship("UserAccount", foreign_keys=[scout_user_id])
    claim = db.relationship("PlayerProfileClaim", foreign_keys=[claim_id])
    club_consent_by = db.relationship("UserAccount", foreign_keys=[club_consent_by_user_id])
    messages = db.relationship(
        "ContactMessage",
        back_populates="contact_request",
        lazy="dynamic",
        order_by="ContactMessage.created_at",
    )
    audit_events = db.relationship(
        "ContactAuditEvent",
        back_populates="contact_request",
        lazy="dynamic",
        order_by="ContactAuditEvent.created_at",
    )
    outcomes = db.relationship(
        "ContactOutcome",
        back_populates="contact_request",
        lazy="dynamic",
        order_by="ContactOutcome.created_at",
    )

    @property
    def player_user(self):
        return self.claim.user if self.claim is not None else None

    def latest_outcome(self):
        return (
            self.outcomes.order_by(None)
            .order_by(
                ContactOutcome.occurred_at.desc(),
                ContactOutcome.created_at.desc(),
                ContactOutcome.id.desc(),
            )
            .first()
        )

    def to_dict(self, *, include_user_ids: bool = False):
        latest = self.latest_outcome()
        club_participant = None
        if self.routing_mode == "club_included" and self.club_program_id is not None:
            from src.services.club_registry import get_club_program

            program = get_club_program(self.club_program_id)
            club_participant = {
                "club_program_id": self.club_program_id,
                "display_name": program.get("name") if program else None,
            }
        scout_participant = {
            "display_name": self.scout.display_name if self.scout else None,
        }
        player_participant = {
            "display_name": self.player_user.display_name if self.player_user else "Account deleted",
        }
        if include_user_ids:
            scout_participant["user_id"] = self.scout_user_id
            player_participant["user_id"] = self.claim.user_account_id if self.claim is not None else None
        return {
            "id": self.id,
            "player_api_id": self.player_api_id,
            "message": self.message,
            "status": self.status,
            "routing_mode": self.routing_mode,
            "club_program_id": self.club_program_id,
            "club_consent_status": self.club_consent_status,
            "club_consent_at": _iso(self.club_consent_at),
            "club_consent_note": self.club_consent_note,
            "permission_attestation": bool(self.permission_attestation),
            "permission_attested_at": _iso(self.permission_attested_at),
            "messaging_open": self.status == "accepted"
            and (self.routing_mode != "club_included" or self.club_consent_status == "granted"),
            "created_at": _iso(self.created_at),
            "responded_at": _iso(self.responded_at),
            "expires_at": _iso(self.expires_at),
            "participants": {
                "scout": scout_participant,
                "player": player_participant,
                "club": club_participant,
            },
            "latest_outcome": latest.to_dict() if latest else None,
        }


class ContactMessage(db.Model):
    """One sanitized plain-text message in an accepted contact request."""

    __tablename__ = "contact_messages"
    __table_args__ = (
        db.CheckConstraint(
            "sender_role IN ('scout','player','club')",
            name="ck_contact_messages_sender_role",
        ),
        db.Index("ix_contact_messages_request_created", "contact_request_id", "created_at"),
    )

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    contact_request_id = db.Column(db.String(36), db.ForeignKey("contact_requests.id"), nullable=False)
    sender_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    sender_role = db.Column(db.String(20), nullable=False)
    body = db.Column(db.String(2000), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    contact_request = db.relationship("ContactRequest", back_populates="messages")
    sender = db.relationship("UserAccount", foreign_keys=[sender_user_id])

    def to_dict(self, *, include_user_ids: bool = False):
        payload = {
            "id": self.id,
            "contact_request_id": self.contact_request_id,
            "sender_role": self.sender_role,
            "sender_display_name": self.sender.display_name if self.sender else None,
            "body": self.body,
            "created_at": _iso(self.created_at),
        }
        if include_user_ids:
            payload["sender_user_id"] = self.sender_user_id
        return payload


class ContactAuditEvent(db.Model):
    """Append-only record of every state-changing contact-rail action."""

    __tablename__ = "contact_audit_events"
    __table_args__ = (
        db.CheckConstraint(
            "event_type IN ("
            "'created','accepted','declined','withdrawn','expired','message_sent','outcome_reported',"
            "'club_consent_granted','club_consent_declined','club_notice_sent','scout_permission_attested'"
            ")",
            name="ck_contact_audit_events_type",
        ),
        db.Index("ix_contact_audit_events_request_created", "contact_request_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    contact_request_id = db.Column(db.String(36), db.ForeignKey("contact_requests.id"), nullable=False)
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"))
    event_type = db.Column(db.String(30), nullable=False)
    # ``metadata`` is reserved by SQLAlchemy's declarative API, so the Python
    # attribute is named event_metadata while the physical column matches the contract.
    event_metadata = db.Column("metadata", db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    contact_request = db.relationship("ContactRequest", back_populates="audit_events")
    actor = db.relationship("UserAccount", foreign_keys=[actor_user_id])


class ContactOutcome(db.Model):
    """Append-only progression reported by either contact participant."""

    __tablename__ = "contact_outcomes"
    __table_args__ = (
        db.CheckConstraint(
            "stage IN ('contacted','trial_scheduled','trial_completed','signed','no_fit')",
            name="ck_contact_outcomes_stage",
        ),
        db.Index("ix_contact_outcomes_request_created", "contact_request_id", "created_at"),
        db.Index("ix_contact_outcomes_request_occurred", "contact_request_id", "occurred_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    contact_request_id = db.Column(db.String(36), db.ForeignKey("contact_requests.id"), nullable=False)
    stage = db.Column(db.String(30), nullable=False)
    reported_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    notes = db.Column(db.String(2000))
    occurred_at = db.Column(db.DateTime, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=_utcnow)

    contact_request = db.relationship("ContactRequest", back_populates="outcomes")
    reporter = db.relationship("UserAccount", foreign_keys=[reported_by_user_id])

    def to_dict(self):
        return {
            "stage": self.stage,
            "notes": self.notes,
            "occurred_at": _iso(self.occurred_at),
            "created_at": _iso(self.created_at),
        }


__all__ = [
    "ContactAuditEvent",
    "ContactMessage",
    "ContactOutcome",
    "ContactRequest",
]
