"""Talent Showcase models — player-claimed profiles + curated highlight reel.

A player (or their agent/guardian/club official) claims their public profile;
an admin approves the claim, after which the owner can curate a self-reported
profile card and a YouTube highlight reel. All owner-submitted content is
pre-moderated (safeguarding — many players are minors), so anything an owner
edits reverts to ``pending`` and is hidden from the public until re-approved.

- ``PlayerProfileClaim`` — one row per (player, user). Multiple *approved* claims
  per player are allowed (a player and their agent can both own it). A player's
  api-football id is used directly (no FK) to mirror ``PlayerLink``.
- ``PlayerShowcaseProfile`` — at most one self-reported card per player.

Reel storage reuses the existing ``PlayerLink`` model (``link_type='highlight'``)
plus the ``sort_order`` column added in migration ``aw19``.
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from src.models.league import db


class PlayerProfileClaim(db.Model):
    """A user's claim to own a player's public profile (admin-reviewed)."""

    __tablename__ = "player_profile_claims"
    __table_args__ = (
        db.CheckConstraint(
            "contract_status IN ('free_agent','contracted','unknown')",
            name="ck_profile_claims_contract_status",
        ),
        db.UniqueConstraint("player_api_id", "user_account_id", name="uq_profile_claim_player_user"),
        db.Index("ix_profile_claims_player", "player_api_id"),
        db.Index("ix_profile_claims_user", "user_account_id"),
        db.Index("ix_profile_claims_club_program", "club_program_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False)  # API-Football player id
    user_account_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    relationship_type = db.Column(db.String(20), nullable=False)  # player | agent | guardian | club_official
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending | approved | rejected | revoked
    message = db.Column(db.Text)  # claimant note to the admin reviewer
    contract_status = db.Column(
        db.String(20),
        nullable=False,
        default="unknown",
        server_default="unknown",
    )
    current_club_name = db.Column(db.String(180))
    # Logical soft link: gf01 is independently ordered and may run after fc03.
    club_program_id = db.Column(db.Integer)
    status_contradiction = db.Column(
        db.Boolean,
        nullable=False,
        default=False,
        server_default=sa.false(),
    )
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
            "contract_status": self.contract_status,
            "current_club_name": self.current_club_name,
            "club_program_id": self.club_program_id,
            "status_contradiction": bool(self.status_contradiction),
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class PlayerShowcaseProfile(db.Model):
    """A player's self-reported profile card — pre-moderated before it goes public."""

    __tablename__ = "player_showcase_profiles"
    __table_args__ = (
        db.CheckConstraint(
            "pending_contract_status IS NULL OR pending_contract_status IN ('free_agent','contracted','unknown')",
            name="ck_showcase_profiles_pending_contract_status",
        ),
        db.Index("ix_showcase_profiles_player", "player_api_id", unique=True),
    )

    id = db.Column(db.Integer, primary_key=True)
    player_api_id = db.Column(db.Integer, nullable=False)  # API-Football player id (unique)
    bio = db.Column(db.Text)
    positions = db.Column(db.String(100))
    preferred_foot = db.Column(db.String(10))  # left | right | both
    height_cm = db.Column(db.Integer)
    status = db.Column(db.String(20), nullable=False, default="pending")  # pending | approved
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=True)
    reviewed_by = db.Column(db.String(200))  # admin email
    reviewed_at = db.Column(db.DateTime)
    # Contract-attestation edits are staged on the already-moderated profile
    # row, then copied to the authoritative claim only when an admin approves.
    pending_contract_claim_id = db.Column(db.Integer)
    pending_contract_status = db.Column(db.String(20))
    pending_current_club_name = db.Column(db.String(180))
    pending_club_program_id = db.Column(db.Integer)
    pending_status_contradiction = db.Column(db.Boolean, nullable=False, default=False, server_default=sa.false())
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    def public_dict(self):
        """Fields exposed on the public player page (self-reported badge)."""
        return {
            "player_api_id": self.player_api_id,
            "bio": self.bio,
            "positions": self.positions,
            "preferred_foot": self.preferred_foot,
            "height_cm": self.height_cm,
            "self_reported": True,
        }

    def owner_dict(self):
        """Public fields plus moderation state — for owner + admin views."""
        payload = self.public_dict()
        payload["id"] = self.id
        payload["status"] = self.status
        payload["updated_at"] = self.updated_at.isoformat() if self.updated_at else None
        return payload

    def pending_contract_dict(self):
        if self.pending_contract_status is None:
            return None
        return {
            "claim_id": self.pending_contract_claim_id,
            "contract_status": self.pending_contract_status,
            "current_club_name": self.pending_current_club_name,
            "club_program_id": self.pending_club_program_id,
            "status_contradiction": bool(self.pending_status_contradiction),
        }
