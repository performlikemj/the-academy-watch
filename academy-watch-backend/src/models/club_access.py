"""Club staff access: role grants, squad scope and emailed staff invites.

``ClubStaff`` stays organisational/display data.  These rows are the only
thing that turns an invited person into someone who may open Club Home, and
only while ``CLUB_STAFF_ACCESS_ENABLED`` is on (see ``services/club_access``).
Claim-backed ``ClubProgramManager`` grants keep working exactly as before.
"""

from datetime import UTC, datetime
from uuid import uuid4

from src.models.league import db

GRANT_ROLES = ("owner", "manager", "coach", "analyst", "viewer")
INVITE_ROLES = ("manager", "coach", "analyst", "viewer")


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


def _iso(value):
    return value.isoformat() + "Z" if value else None


class ClubAccessGrant(db.Model):
    __tablename__ = "club_access_grants"
    __table_args__ = (
        db.CheckConstraint(
            "role IN ('owner','manager','coach','analyst','viewer')",
            name="ck_club_access_grants_role",
        ),
        db.CheckConstraint("status IN ('active','revoked')", name="ck_club_access_grants_status"),
        db.UniqueConstraint("program_id", "user_account_id", name="uq_club_access_grants_program_user"),
        db.Index("ix_club_access_grants_user_status", "user_account_id", "status"),
    )

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id", ondelete="CASCADE"), nullable=False)
    user_account_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    all_squads = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    status = db.Column(db.String(20), nullable=False, default="active", server_default="active")
    source = db.Column(db.String(20), nullable=False, default="invite", server_default="invite")
    source_invite_id = db.Column(
        db.String(36), db.ForeignKey("club_staff_invites.id", ondelete="SET NULL"), nullable=True
    )
    granted_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    updated_at = db.Column(db.DateTime, nullable=False, default=_now, onupdate=_now)
    revoked_at = db.Column(db.DateTime)
    revoked_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    version = db.Column(db.Integer, nullable=False, default=1, server_default="1")

    squads = db.relationship(
        "ClubAccessGrantSquad",
        backref="grant",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ClubAccessGrantSquad.squad_id",
    )

    @property
    def squad_ids(self):
        return sorted(row.squad_id for row in self.squads)

    def to_dict(self):
        return {
            "id": self.id,
            "program_id": self.program_id,
            "user_account_id": self.user_account_id,
            "role": self.role,
            "all_squads": bool(self.all_squads),
            "squad_ids": self.squad_ids,
            "status": self.status,
            "source": self.source,
            "created_at": _iso(self.created_at),
            "updated_at": _iso(self.updated_at),
            "revoked_at": _iso(self.revoked_at),
            "version": self.version,
        }


class ClubAccessGrantSquad(db.Model):
    """One squad a scoped grant may see; deleting the squad deletes the scope row."""

    __tablename__ = "club_access_grant_squads"
    __table_args__ = (db.UniqueConstraint("grant_id", "squad_id", name="uq_club_access_grant_squads"),)

    id = db.Column(db.Integer, primary_key=True)
    grant_id = db.Column(db.Integer, db.ForeignKey("club_access_grants.id", ondelete="CASCADE"), nullable=False)
    squad_id = db.Column(db.Integer, db.ForeignKey("club_squads.id", ondelete="CASCADE"), nullable=False, index=True)


class ClubStaffInvite(db.Model):
    """A one-use emailed invite.  Only the SHA-256 of the token is stored."""

    __tablename__ = "club_staff_invites"
    __table_args__ = (
        db.CheckConstraint("role IN ('manager','coach','analyst','viewer')", name="ck_club_staff_invites_role"),
        db.CheckConstraint("status IN ('pending','accepted','revoked')", name="ck_club_staff_invites_status"),
        db.UniqueConstraint("token_hash", name="uq_club_staff_invites_token_hash"),
        db.Index("ix_club_staff_invites_program_status", "program_id", "status"),
        db.Index("ix_club_staff_invites_email", "email"),
    )

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id", ondelete="CASCADE"), nullable=False)
    email = db.Column(db.String(254), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    all_squads = db.Column(db.Boolean, nullable=False, default=False, server_default=db.false())
    squad_ids = db.Column(db.JSON, nullable=False, default=list)
    token_hash = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    invited_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    created_at = db.Column(db.DateTime, nullable=False, default=_now)
    expires_at = db.Column(db.DateTime, nullable=False)
    accepted_at = db.Column(db.DateTime)
    accepted_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    revoked_at = db.Column(db.DateTime)
    revoked_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))

    def effective_status(self, now=None):
        if self.status == "pending" and self.expires_at <= (now or _now()):
            return "expired"
        return self.status

    def to_dict(self):
        return {
            "id": self.id,
            "program_id": self.program_id,
            "email": self.email,
            "role": self.role,
            "all_squads": bool(self.all_squads),
            "squad_ids": sorted(int(s) for s in (self.squad_ids or [])),
            "status": self.effective_status(),
            "created_at": _iso(self.created_at),
            "expires_at": _iso(self.expires_at),
            "accepted_at": _iso(self.accepted_at),
            "revoked_at": _iso(self.revoked_at),
        }
