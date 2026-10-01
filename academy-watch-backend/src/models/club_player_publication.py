"""Independent player consent for an identity whose origin remains club-private."""

from datetime import UTC, datetime

from src.models.league import db


def now():
    return datetime.now(UTC).replace(tzinfo=None)


class ClubPlayerPublication(db.Model):
    __tablename__ = "club_player_publications"
    __table_args__ = (
        db.UniqueConstraint("program_id", "local_player_id", name="uq_club_player_publication"),
        db.CheckConstraint("moderation_status IN ('pending','approved','rejected')", name="ck_publication_moderation"),
        db.CheckConstraint("version > 0", name="ck_publication_version"),
        db.Index("ix_publication_recipient", "recipient_user_id"),
    )

    id = db.Column(db.Integer, primary_key=True)
    program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id"), nullable=False)
    local_player_id = db.Column(db.Integer, db.ForeignKey("local_players.id"), nullable=False)
    recipient_email = db.Column(db.String(254), nullable=False)
    recipient_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"))
    claim_id = db.Column(db.Integer, db.ForeignKey("player_profile_claims.id"))
    invite_token_hash = db.Column(db.String(64), unique=True)
    invite_expires_at = db.Column(db.DateTime)
    adult_invited_at = db.Column(db.DateTime, nullable=False)
    claimed_at = db.Column(db.DateTime)
    association_confirmed_at = db.Column(db.DateTime)
    association_confirmed_by = db.Column(db.Integer, db.ForeignKey("user_accounts.id"))
    consent_version = db.Column(db.String(40))
    consented_at = db.Column(db.DateTime)
    moderation_status = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    reviewed_by = db.Column(db.String(254))
    reviewed_at = db.Column(db.DateTime)
    withdrawn_at = db.Column(db.DateTime)
    club_revoked_at = db.Column(db.DateTime)
    creator_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"))
    version = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    updated_at = db.Column(db.DateTime, nullable=False, default=now)
