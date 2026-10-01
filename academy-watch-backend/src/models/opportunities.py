"""Private adult recruiting; public opportunity DTOs never include applicants."""

from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from src.models.league import db


def now():
    return datetime.now(UTC).replace(tzinfo=None)


def uid():
    return str(uuid4())


STATES = ("new", "shortlisted", "invited", "attended", "offer", "signed", "rejected", "withdrawn")
TERMINAL = ("signed", "rejected", "withdrawn")


class ClubOpportunity(db.Model):
    __tablename__ = "club_opportunities"
    __table_args__ = (
        sa.CheckConstraint("status IN ('draft','published','closed','cancelled')", name="ck_opportunity_status"),
        sa.CheckConstraint("type IN ('trial','open_session','position')", name="ck_opportunity_type"),
        sa.CheckConstraint("capacity IS NULL OR capacity > 0", name="ck_opportunity_capacity"),
        sa.CheckConstraint("version > 0", name="ck_opportunity_version"),
        sa.Index("ix_opportunity_public", "status", "closes_at", "id"),
        sa.Index("ix_opportunity_program", "program_id", "created_at"),
    )
    id = db.Column(db.String(36), primary_key=True, default=uid)
    program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id"), nullable=False)
    squad_id = db.Column(db.Integer, db.ForeignKey("club_squads.id", ondelete="SET NULL"))
    creator_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    type = db.Column(db.String(20), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, nullable=False)
    instructions = db.Column(db.Text, nullable=False, default="")
    position_requirements = db.Column(db.String(200), nullable=False, default="All positions")
    birth_year_min = db.Column(db.Integer)
    birth_year_max = db.Column(db.Integer)
    gender_program = db.Column(db.String(20), nullable=False, default="all")
    starts_at = db.Column(db.DateTime)
    ends_at = db.Column(db.DateTime)
    timezone = db.Column(db.String(80), nullable=False, default="UTC")
    venue = db.Column(db.String(200), nullable=False)
    address = db.Column(db.String(300), nullable=False, default="")
    capacity = db.Column(db.Integer)
    closes_at = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="draft")
    published_at = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    updated_at = db.Column(db.DateTime, nullable=False, default=now)
    version = db.Column(db.Integer, nullable=False, default=1)


class OpportunityApplication(db.Model):
    __tablename__ = "opportunity_applications"
    __table_args__ = (
        sa.CheckConstraint("status IN (" + ",".join(repr(x) for x in STATES) + ")", name="ck_application_status"),
        sa.CheckConstraint("applicant_kind = 'adult_player'", name="ck_application_adult"),
        sa.CheckConstraint("signed_player_id <> 0", name="ck_application_subject"),
        sa.CheckConstraint("version > 0", name="ck_application_version"),
        sa.CheckConstraint(
            "reservation_state IN ('none','pending','confirmed','declined','released')",
            name="ck_application_reservation",
        ),
        sa.UniqueConstraint("applicant_user_id", "client_request_id", name="uq_application_request"),
        sa.Index("uq_application_subject", "opportunity_id", "signed_player_id", unique=True),
        sa.Index("ix_application_applicant", "applicant_user_id", "submitted_at"),
        sa.Index("ix_application_retention", "retention_expires_at"),
    )
    id = db.Column(db.String(36), primary_key=True, default=uid)
    opportunity_id = db.Column(db.String(36), db.ForeignKey("club_opportunities.id"), nullable=False)
    program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id"), nullable=False)
    applicant_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    applicant_kind = db.Column(db.String(20), nullable=False, default="adult_player")
    claim_id = db.Column(db.Integer, db.ForeignKey("player_profile_claims.id"), nullable=False)
    signed_player_id = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), nullable=False, default="new")
    position = db.Column(db.String(80), nullable=False)
    current_club = db.Column(db.String(180), nullable=False, default="")
    contact_consent_at = db.Column(db.DateTime, nullable=False)
    submitted_at = db.Column(db.DateTime, nullable=False, default=now)
    withdrawn_at = db.Column(db.DateTime)
    retention_expires_at = db.Column(db.DateTime, nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1)
    client_request_id = db.Column(db.String(36), nullable=False)
    request_hash = db.Column(db.String(64), nullable=False)
    trial_at = db.Column(db.DateTime)
    trial_venue = db.Column(db.String(200))
    trial_instructions = db.Column(db.Text)
    reservation_state = db.Column(db.String(20), nullable=False, default="none")


class ApplicationEvent(db.Model):
    __tablename__ = "application_events"
    __table_args__ = (sa.UniqueConstraint("application_id", "version", name="uq_application_event_version"),)
    id = db.Column(db.String(36), primary_key=True, default=uid)
    application_id = db.Column(
        db.String(36), db.ForeignKey("opportunity_applications.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    from_state = db.Column(db.String(20))
    to_state = db.Column(db.String(20), nullable=False)
    reason_code = db.Column(db.String(40), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)


class ApplicationNote(db.Model):
    __tablename__ = "application_notes"
    id = db.Column(db.String(36), primary_key=True, default=uid)
    application_id = db.Column(
        db.String(36), db.ForeignKey("opportunity_applications.id", ondelete="CASCADE"), nullable=False, index=True
    )
    author_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)
