"""Marketplace trust prerequisites: scout verification and content reports.

These rows deliberately establish identity and moderation state without
persisting a scout role on ``UserAccount``.  Scout status is derived from an
approved verification row at serialization time by the auth layer.
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from src.models.league import db


def _iso(value):
    return value.isoformat() if value else None


class ScoutVerification(db.Model):
    """Admin-reviewed evidence that a user is a legitimate football scout."""

    __tablename__ = "scout_verifications"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending','approved','rejected','revoked')",
            name="ck_scout_verifications_status",
        ),
        db.Index(
            "uq_scout_verifications_active_user",
            "user_account_id",
            unique=True,
            postgresql_where=sa.text("status IN ('pending', 'approved')"),
            sqlite_where=sa.text("status IN ('pending', 'approved')"),
        ),
        db.Index(
            "ix_scout_verifications_user_submitted",
            "user_account_id",
            "submitted_at",
        ),
        db.Index(
            "ix_scout_verifications_status_submitted",
            "status",
            "submitted_at",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_account_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    organization = db.Column(db.String(200), nullable=False)
    role_title = db.Column(db.String(120), nullable=False)
    statement = db.Column(db.String(2000), nullable=False)
    evidence_urls = db.Column(db.JSON, nullable=False, default=list)
    status = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    submitted_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))
    reviewed_at = db.Column(db.DateTime)
    reviewed_by = db.Column(db.String(200))
    review_notes = db.Column(db.String(2000))
    revocation_reason = db.Column(db.String(1000))

    user = db.relationship(
        "UserAccount",
        foreign_keys=[user_account_id],
        backref=db.backref("scout_verifications", lazy="dynamic"),
    )

    def to_dict(self, *, admin=False):
        """Serialize the applicant-facing view, optionally with admin identity."""
        payload = {
            "id": self.id,
            "full_name": self.full_name,
            "organization": self.organization,
            "role_title": self.role_title,
            "statement": self.statement,
            "evidence_urls": list(self.evidence_urls or []),
            "status": self.status,
            "submitted_at": _iso(self.submitted_at),
            "reviewed_at": _iso(self.reviewed_at),
            "review_notes": self.review_notes,
            "revocation_reason": self.revocation_reason,
        }
        if admin:
            payload.update(
                {
                    "user_account_id": self.user_account_id,
                    "user_email": self.user.email if self.user else None,
                    "reviewed_by": self.reviewed_by,
                }
            )
        return payload

    def admin_dict(self):
        return self.to_dict(admin=True)


class ContentReport(db.Model):
    """A user-submitted moderation report spanning several subject types."""

    __tablename__ = "content_reports"
    __table_args__ = (
        db.CheckConstraint(
            "subject_type IN ('player_profile','showcase_content','club_program','contact_message','other')",
            name="ck_content_reports_subject_type",
        ),
        db.CheckConstraint(
            "status IN ('open','reviewing','resolved','dismissed')",
            name="ck_content_reports_status",
        ),
        db.Index(
            "ix_content_reports_reporter_created",
            "reporter_user_id",
            "created_at",
        ),
        db.Index("ix_content_reports_status_created", "status", "created_at"),
        db.Index("ix_content_reports_subject", "subject_type", "subject_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    reporter_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    subject_type = db.Column(db.String(40), nullable=False)
    subject_id = db.Column(db.String(200), nullable=False)
    reason_code = db.Column(db.String(80), nullable=False)
    details = db.Column(db.String(2000))
    status = db.Column(db.String(20), nullable=False, default="open", server_default="open")
    resolution_notes = db.Column(db.String(2000))
    created_at = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))
    resolved_at = db.Column(db.DateTime)

    reporter = db.relationship(
        "UserAccount",
        foreign_keys=[reporter_user_id],
        backref=db.backref("content_reports", lazy="dynamic"),
    )

    def to_dict(self, *, admin=False):
        """Serialize the reporter-facing view, optionally with reporter identity."""
        payload = {
            "id": self.id,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "reason_code": self.reason_code,
            "details": self.details,
            "status": self.status,
            "resolution_notes": self.resolution_notes,
            "created_at": _iso(self.created_at),
            "resolved_at": _iso(self.resolved_at),
        }
        if admin:
            payload.update(
                {
                    "reporter_user_id": self.reporter_user_id,
                    "reporter_email": self.reporter.email if self.reporter else None,
                }
            )
        return payload

    def admin_dict(self):
        return self.to_dict(admin=True)
