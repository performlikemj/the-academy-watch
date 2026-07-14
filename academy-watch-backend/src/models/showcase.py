"""Talent Showcase models — player-claimed profiles, photos, and highlight reel.

A player (or their agent/guardian/club official) claims their public profile;
an admin approves the claim, after which the owner can curate a self-reported
profile card and a YouTube highlight reel. All owner-submitted content is
pre-moderated (safeguarding — many players are minors), so anything an owner
edits reverts to ``pending`` and is hidden from the public until re-approved.

- ``PlayerProfileClaim`` — one row per (player, user). Multiple *approved* claims
  per player are allowed (a player and their agent can both own it). A player's
  api-football id is used directly (no FK) to mirror ``PlayerLink``.
- ``PlayerShowcaseProfile`` — at most one self-reported card per player.
- ``PlayerShowcaseMedia`` — pre-moderated, self-hosted player photos.
- ``LocalClub`` — a moderated, user-created club outside the synced team layer.
- ``PlayerClubAffiliation`` — a pre-moderated self-reported club affiliation.

Reel storage reuses the existing ``PlayerLink`` model (``link_type='highlight'``)
plus the ``sort_order`` column added in migration ``aw19``.
"""

from datetime import UTC, datetime

from sqlalchemy.orm import validates
from src.models.league import db


class PlayerProfileClaim(db.Model):
    """A user's claim to own a player's public profile (admin-reviewed)."""

    __tablename__ = "player_profile_claims"
    __table_args__ = (
        db.UniqueConstraint("player_api_id", "user_account_id", name="uq_profile_claim_player_user"),
        db.Index("ix_profile_claims_player", "player_api_id"),
        db.Index("ix_profile_claims_user", "user_account_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False)  # API-Football player id
    user_account_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    relationship_type = db.Column(db.String(20), nullable=False)  # player | agent | guardian | club_official
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending | approved | rejected | revoked
    message = db.Column(db.Text)  # claimant note to the admin reviewer
    verification_code = db.Column(db.String(24), nullable=True)
    verification_proof_url = db.Column(db.String(500), nullable=True)
    verification_status = db.Column(
        db.String(20),
        nullable=False,
        default="unverified",
        server_default="unverified",
    )
    verification_checked_at = db.Column(db.DateTime, nullable=True)
    verification_note = db.Column(db.String(500), nullable=True)
    verification_method = db.Column(db.String(20), nullable=True)  # reserved for club vouching
    reviewed_by = db.Column(db.String(200))  # admin email
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))

    user = db.relationship("UserAccount", backref=db.backref("player_profile_claims", lazy="dynamic"))

    def to_dict(self):
        return {
            "id": self.id,
            "player_api_id": self.player_api_id,
            "user_account_id": self.user_account_id,
            "relationship_type": self.relationship_type,
            "status": self.status,
            "message": self.message,
            "verification_code": self.verification_code,
            "verification_proof_url": self.verification_proof_url,
            "verification_status": self.verification_status,
            "verification_checked_at": (
                self.verification_checked_at.isoformat() if self.verification_checked_at else None
            ),
            "verification_note": self.verification_note,
            "verification_method": self.verification_method,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PlayerShowcaseProfile(db.Model):
    """A player's self-reported profile card — pre-moderated before it goes public."""

    __tablename__ = "player_showcase_profiles"
    __table_args__ = (db.Index("ix_showcase_profiles_player", "player_api_id", unique=True),)

    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False)  # API-Football player id (unique)
    bio = db.Column(db.Text)
    positions = db.Column(db.String(100))
    preferred_foot = db.Column(db.String(10))  # left | right | both
    height_cm = db.Column(db.Integer)
    contract_status = db.Column(db.String(30))  # under_contract | expiring | free_agent
    contract_until = db.Column(db.Date)
    availability = db.Column(db.String(30))  # open_to_moves | not_looking | trial_available
    agent_name = db.Column(db.String(200))
    agent_contact_email = db.Column(db.String(320))
    nationality_secondary = db.Column(db.String(100))
    languages = db.Column(db.String(300))
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending | approved
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=True)
    reviewed_by = db.Column(db.String(200))  # admin email
    reviewed_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    def public_dict(self, *, include_agent_contact=False):
        """Fields exposed on the player page (self-reported badge).

        Agent contact email is withheld unless the caller has authenticated;
        routes opt in only after validating that authentication context.
        """
        payload = {
            "player_api_id": self.player_api_id,
            "bio": self.bio,
            "positions": self.positions,
            "preferred_foot": self.preferred_foot,
            "height_cm": self.height_cm,
            "contract_status": self.contract_status,
            "contract_until": self.contract_until.isoformat() if self.contract_until else None,
            "availability": self.availability,
            "agent_name": self.agent_name,
            "nationality_secondary": self.nationality_secondary,
            "languages": self.languages,
            "self_reported": True,
        }
        if include_agent_contact:
            payload["agent_contact_email"] = self.agent_contact_email
        return payload

    def owner_dict(self):
        """Public fields plus moderation state — for owner + admin views."""
        payload = self.public_dict(include_agent_contact=True)
        payload["id"] = self.id
        payload["status"] = self.status
        payload["updated_at"] = self.updated_at.isoformat() if self.updated_at else None
        return payload


class PlayerShowcaseMedia(db.Model):
    """A self-hosted player photo that remains private until moderation."""

    __tablename__ = "player_showcase_media"
    __table_args__ = (db.Index("ix_showcase_media_player_status", "player_api_id", "status"),)

    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False)  # API-Football player id
    kind = db.Column(db.String(20), nullable=False, default="photo", server_default="photo")
    blob_path = db.Column(db.Text, nullable=False)
    public_url = db.Column(db.Text)
    content_type = db.Column(db.String(50))
    size_bytes = db.Column(db.Integer)
    is_primary = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    sort_order = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    status = db.Column(db.String(20), nullable=False, default="pending_upload", server_default="pending_upload")
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=True)
    reviewed_by = db.Column(db.String(200))
    reviewed_at = db.Column(db.DateTime)
    review_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))


class LocalClub(db.Model):
    """A moderated local club kept separate from API-synced teams."""

    __tablename__ = "local_clubs"
    __table_args__ = (
        db.Index("ix_local_clubs_normalized_name", "normalized_name"),
        db.Index("ix_local_clubs_status", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    normalized_name = db.Column(db.String(220), nullable=False)
    country = db.Column(db.String(100))
    city = db.Column(db.String(120))
    level = db.Column(db.String(30))
    status = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    api_team_id = db.Column(db.Integer)
    merged_into_local_club_id = db.Column(db.Integer, db.ForeignKey("local_clubs.id"), nullable=True)
    provenance = db.Column(db.String(20), nullable=False, default="user", server_default="user")
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=True)
    reviewed_by = db.Column(db.String(200))
    reviewed_at = db.Column(db.DateTime)
    review_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    @staticmethod
    def normalize_name(value: str) -> str:
        """Lowercase and collapse whitespace for duplicate detection."""
        return " ".join(value.lower().split())

    @validates("name")
    def _sync_normalized_name(self, _key, value):
        if isinstance(value, str):
            self._setting_normalized_name = True
            try:
                self.normalized_name = self.normalize_name(value)
            finally:
                self._setting_normalized_name = False
        return value

    @validates("normalized_name")
    def _enforce_normalized_name(self, _key, value):
        if getattr(self, "_setting_normalized_name", False):
            return self.normalize_name(value) if isinstance(value, str) else value
        source = self.name if isinstance(self.name, str) else value
        return self.normalize_name(source) if isinstance(source, str) else source


class PlayerClubAffiliation(db.Model):
    """A player's pre-moderated self-reported club affiliation."""

    __tablename__ = "player_club_affiliations"
    __table_args__ = (
        db.Index(
            "ix_player_club_affiliations_player_status",
            "player_api_id",
            "status",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False)
    local_club_id = db.Column(db.Integer, db.ForeignKey("local_clubs.id"), nullable=True)
    team_api_id = db.Column(db.Integer)
    season = db.Column(db.String(20))
    status = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=True)
    reviewed_by = db.Column(db.String(200))
    reviewed_at = db.Column(db.DateTime)
    review_note = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
