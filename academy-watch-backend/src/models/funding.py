"""Grassroots league admission and verified club-program identity models.

F2 deliberately stops before money movement.  These rows establish the league,
organization, authority, moderation, and Connect-readiness gates that F3 may
later reference.  Public APIs serialize narrow projections; evidence, manager,
Connect, and audit rows remain server-only/default-deny under RLS.
"""

from datetime import UTC, datetime

from src.models.league import db
from src.services.funding_evidence_crypto import EncryptedEvidenceText


def _iso(value):
    return value.isoformat() if value else None


class FundingLeague(db.Model):
    """MJ-controlled league registry, optionally bridged to API-Football."""

    __tablename__ = "funding_leagues"
    __table_args__ = (
        db.CheckConstraint(
            "level IN ('pro_academy','youth_national','youth_regional','recreational')",
            name="ck_funding_leagues_level",
        ),
        db.CheckConstraint(
            "gender_program IN ('boys','girls','both')",
            name="ck_funding_leagues_gender",
        ),
        db.CheckConstraint(
            "season_calendar IN ('aug_may','calendar_year','fall_spring')",
            name="ck_funding_leagues_calendar",
        ),
        db.CheckConstraint(
            "data_tier IN ('api_football','film_room','self_reported')",
            name="ck_funding_leagues_data_tier",
        ),
        db.CheckConstraint(
            "registry_status IN ('proposed','approved','rejected')",
            name="ck_funding_leagues_registry_status",
        ),
        db.CheckConstraint(
            "admission_state IN ('open','waitlisted','closed')",
            name="ck_funding_leagues_admission_state",
        ),
        db.UniqueConstraint("name", "country", "region", name="uq_funding_league_identity"),
        db.UniqueConstraint("league_api_id", name="uq_funding_league_api_id"),
        db.UniqueConstraint("existing_league_id", name="uq_funding_league_bridge"),
        db.Index("ix_funding_leagues_admission", "registry_status", "admission_state"),
        db.Index("ix_funding_leagues_location", "country", "region"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    country = db.Column(db.String(80), nullable=False)
    region = db.Column(db.String(120), nullable=False)
    level = db.Column(db.String(30), nullable=False)
    age_bands = db.Column(db.JSON, nullable=False, default=list)
    gender_program = db.Column(db.String(10), nullable=False)
    season_calendar = db.Column(db.String(20), nullable=False)
    data_tier = db.Column(db.String(20), nullable=False)
    league_api_id = db.Column(db.Integer)
    existing_league_id = db.Column(db.Integer, db.ForeignKey("leagues.id"))
    registry_status = db.Column(db.String(20), nullable=False, default="approved", server_default="approved")
    admission_state = db.Column(db.String(20), nullable=False, default="waitlisted", server_default="waitlisted")
    proposed_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"))
    reviewed_by = db.Column(db.String(200))
    review_reason = db.Column(db.Text)
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    existing_league = db.relationship("League", foreign_keys=[existing_league_id])

    @property
    def data_tier_key(self):
        if self.data_tier == "api_football" and self.league_api_id is not None:
            return f"api_football:{self.league_api_id}"
        return self.data_tier

    def to_dict(self, *, admin=False):
        payload = {
            "id": self.id,
            "name": self.name,
            "country": self.country,
            "region": self.region,
            "level": self.level,
            "age_bands": self.age_bands or [],
            "gender_program": self.gender_program,
            "season_calendar": self.season_calendar,
            "data_tier": self.data_tier_key,
            "league_api_id": self.league_api_id,
            "existing_league_id": self.existing_league_id,
            "is_provider_bridge": self.existing_league_id is not None,
            "registry_status": self.registry_status,
            "admission_state": self.admission_state,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
        }
        if admin:
            payload.update(
                {
                    "proposed_by_user_id": self.proposed_by_user_id,
                    "reviewed_by": self.reviewed_by,
                    "review_reason": self.review_reason,
                    "reviewed_at": _iso(self.reviewed_at),
                }
            )
        return payload


class ClubProgram(db.Model):
    """One public program and one future legal recipient per v1 row."""

    __tablename__ = "club_programs"
    __table_args__ = (
        db.CheckConstraint(
            "provenance_tier IN ('provider_covered','film_room_verified','self_reported')",
            name="ck_club_programs_provenance",
        ),
        db.CheckConstraint(
            "platform_status IN ('pending','approved','rejected','suspended')",
            name="ck_club_programs_status",
        ),
        db.UniqueConstraint("slug", name="uq_club_programs_slug"),
        db.UniqueConstraint("team_api_id", name="uq_club_programs_team_api_id"),
        db.Index("ix_club_programs_league", "funding_league_id"),
        db.Index("ix_club_programs_location", "country", "region"),
        db.Index("ix_club_programs_status", "platform_status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    funding_league_id = db.Column(db.Integer, db.ForeignKey("funding_leagues.id"), nullable=False)
    team_api_id = db.Column(db.Integer, db.ForeignKey("team_profiles.team_id"))
    name = db.Column(db.String(180), nullable=False)
    legal_name = db.Column(db.String(220), nullable=False)
    slug = db.Column(db.String(200), nullable=False)
    crest_url = db.Column(db.String(500))
    country = db.Column(db.String(80), nullable=False)
    region = db.Column(db.String(120), nullable=False)
    city = db.Column(db.String(120))
    currency = db.Column(db.String(3), nullable=False, default="USD", server_default="USD")
    provenance_tier = db.Column(db.String(30), nullable=False, default="self_reported", server_default="self_reported")
    platform_status = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    donations_enabled = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    emergency_hidden = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    approved_profile_revision_id = db.Column(
        db.Integer,
        db.ForeignKey(
            "club_program_profile_revisions.id",
            name="fk_club_programs_approved_revision",
            use_alter=True,
        ),
    )
    reviewed_by = db.Column(db.String(200))
    review_reason = db.Column(db.Text)
    reviewed_at = db.Column(db.DateTime)
    verified_at = db.Column(db.DateTime)
    next_review_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    league = db.relationship("FundingLeague", backref=db.backref("programs", lazy="dynamic"))
    team_profile = db.relationship("TeamProfile", foreign_keys=[team_api_id])

    @property
    def has_active_manager(self):
        return any(manager.status == "active" for manager in self.managers)

    @property
    def connect_account(self):
        return self.connect_accounts[0] if self.connect_accounts else None

    @property
    def is_verified_program(self):
        if self.platform_status != "approved" or self.emergency_hidden or not self.has_active_manager:
            return False
        if self.country.strip().upper() not in {"US", "USA", "UNITED STATES", "UNITED STATES OF AMERICA"}:
            return True
        return bool(self.connect_account and self.connect_account.is_ready)

    def public_dict(self):
        provenance_labels = {
            "provider_covered": "Provider-covered",
            "film_room_verified": "Film Room-verified",
            "self_reported": "Self-reported",
        }
        return {
            "id": self.id,
            "slug": self.slug,
            "name": self.name,
            "crest_url": self.crest_url,
            "country": self.country,
            "region": self.region,
            "city": self.city,
            "league": self.league.to_dict() if self.league else None,
            "team_api_id": self.team_api_id,
            "team_slug": self.team_profile.slug if self.team_profile else None,
            "team_name": self.team_profile.name if self.team_profile else None,
            "is_verified_program": self.is_verified_program,
            "verified_at": _iso(self.verified_at),
            "provenance": {
                "tier": self.provenance_tier,
                "label": provenance_labels[self.provenance_tier],
            },
            "is_fundable": False,
        }


class ClubProgramClaim(db.Model):
    __tablename__ = "club_program_claims"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending','approved','rejected','revoked')",
            name="ck_club_program_claims_status",
        ),
        db.UniqueConstraint("program_id", "user_account_id", name="uq_club_claim_program_user"),
        db.Index("ix_club_claims_status", "status", "created_at"),
        db.Index("ix_club_claims_user", "user_account_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id", ondelete="CASCADE"), nullable=False)
    user_account_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    relationship_type = db.Column(db.String(30), nullable=False, default="club_official")
    status = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    applicant_message = db.Column(db.Text)
    reviewed_by = db.Column(db.String(200))
    review_reason = db.Column(db.Text)
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    program = db.relationship("ClubProgram", backref=db.backref("claims", lazy="dynamic"))
    user = db.relationship("UserAccount", foreign_keys=[user_account_id])


class ClubClaimEvidence(db.Model):
    """Private evidence metadata; identity documents stay with Stripe/off-platform."""

    __tablename__ = "club_claim_evidence"
    __table_args__ = (
        db.UniqueConstraint("claim_id", name="uq_club_claim_evidence_claim"),
        db.Index("ix_club_claim_evidence_retention", "retention_expires_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    claim_id = db.Column(db.Integer, db.ForeignKey("club_program_claims.id", ondelete="CASCADE"), nullable=False)
    adult_authority_attested = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    official_email = db.Column(EncryptedEvidenceText())
    authorization_method = db.Column(db.String(40), nullable=False)
    authorization_reference = db.Column(EncryptedEvidenceText())
    organization_form = db.Column(db.String(40), nullable=False)
    registration_reference = db.Column(EncryptedEvidenceText(), nullable=False)
    official_contact_name = db.Column(EncryptedEvidenceText(), nullable=False)
    official_contact_reference = db.Column(EncryptedEvidenceText(), nullable=False)
    safeguarding_contact_email = db.Column(EncryptedEvidenceText(), nullable=False)
    safeguarding_policy_url = db.Column(EncryptedEvidenceText())
    safeguarding_policy_attested = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    eligible_organization_attested = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    payout_control_attested = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    evidence_notes = db.Column(EncryptedEvidenceText())
    retention_expires_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    claim = db.relationship(
        "ClubProgramClaim",
        backref=db.backref("evidence", uselist=False, cascade="all, delete-orphan"),
    )


class ClubProgramManager(db.Model):
    __tablename__ = "club_program_managers"
    __table_args__ = (
        db.CheckConstraint("status IN ('active','revoked')", name="ck_club_program_managers_status"),
        db.UniqueConstraint("program_id", "user_account_id", name="uq_club_manager_program_user"),
        db.Index("ix_club_managers_user_status", "user_account_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id", ondelete="CASCADE"), nullable=False)
    user_account_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    source_claim_id = db.Column(db.Integer, db.ForeignKey("club_program_claims.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="active", server_default="active")
    granted_by = db.Column(db.String(200), nullable=False)
    granted_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    revoked_by = db.Column(db.String(200))
    revoked_reason = db.Column(db.Text)
    revoked_at = db.Column(db.DateTime)

    program = db.relationship("ClubProgram", backref=db.backref("managers", lazy=True))
    user = db.relationship("UserAccount", foreign_keys=[user_account_id])


class ClubProgramProfileRevision(db.Model):
    __tablename__ = "club_program_profile_revisions"
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending','approved','rejected','withdrawn')",
            name="ck_club_program_revisions_status",
        ),
        db.Index("ix_club_program_revisions_program", "program_id", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id", ondelete="CASCADE"), nullable=False)
    submitted_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    summary = db.Column(db.Text)
    age_groups = db.Column(db.JSON, nullable=False, default=list)
    activities = db.Column(db.JSON, nullable=False, default=list)
    funding_purpose = db.Column(db.Text)
    official_url = db.Column(db.String(500))
    safeguarding_url = db.Column(db.String(500))
    media_urls = db.Column(db.JSON, nullable=False, default=list)
    reviewed_by = db.Column(db.String(200))
    review_reason = db.Column(db.Text)
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

    program = db.relationship(
        "ClubProgram",
        foreign_keys=[program_id],
        backref=db.backref("profile_revisions", lazy="dynamic"),
    )


class ClubConnectAccount(db.Model):
    __tablename__ = "club_connect_accounts"
    __table_args__ = (
        db.UniqueConstraint("program_id", name="uq_club_connect_program"),
        db.UniqueConstraint("stripe_account_id", name="uq_club_connect_stripe_account"),
        db.Index("ix_club_connect_readiness", "transfers_active", "payouts_enabled"),
    )

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id", ondelete="CASCADE"), nullable=False)
    stripe_account_id = db.Column(db.String(255))
    account_type = db.Column(db.String(20), nullable=False, default="express", server_default="express")
    country = db.Column(db.String(2), nullable=False, default="US", server_default="US")
    business_type = db.Column(db.String(30), nullable=False, default="company", server_default="company")
    livemode = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    transfers_active = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    details_submitted = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    payouts_enabled = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    charges_enabled = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    requirements_due = db.Column(db.JSON, nullable=False, default=list)
    disabled_reason = db.Column(db.String(255))
    onboarding_url = db.Column(db.String(1000))
    onboarding_expires_at = db.Column(db.DateTime)
    deauthorized_at = db.Column(db.DateTime)
    last_synced_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    program = db.relationship("ClubProgram", backref=db.backref("connect_accounts", lazy=True))

    @property
    def is_ready(self):
        return bool(
            self.stripe_account_id
            and not self.livemode
            and self.transfers_active
            and self.details_submitted
            and self.payouts_enabled
            and not (self.requirements_due or [])
            and not self.disabled_reason
            and not self.deauthorized_at
        )


class FundingAdminEvent(db.Model):
    """Append-only audit event for every registry and claim transition."""

    __tablename__ = "funding_admin_events"
    __table_args__ = (
        db.Index("ix_funding_admin_events_target", "target_type", "target_id"),
        db.Index("ix_funding_admin_events_created", "created_at"),
    )

    id = db.Column(db.Integer, primary_key=True)
    actor_email = db.Column(db.String(254), nullable=False)
    action = db.Column(db.String(80), nullable=False)
    target_type = db.Column(db.String(40), nullable=False)
    target_id = db.Column(db.Integer, nullable=False)
    reason = db.Column(db.Text, nullable=False)
    event_metadata = db.Column(db.JSON, nullable=False, default=dict)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
