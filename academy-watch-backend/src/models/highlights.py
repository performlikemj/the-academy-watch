"""Two independent publication keys and fenced, private standalone cuts."""

import uuid
from datetime import UTC, datetime

from src.models.league import db


def now():
    return datetime.now(UTC).replace(tzinfo=None)


def uuid4():
    return str(uuid.uuid4())


class PlayerHighlight(db.Model):
    __tablename__ = "player_highlights"
    __table_args__ = (
        db.UniqueConstraint("pick_key", name="uq_player_highlights_pick"),
        db.CheckConstraint(
            "(player_api_id IS NOT NULL AND local_player_id IS NULL) OR (player_api_id IS NULL AND local_player_id IS NOT NULL)",
            name="ck_highlight_subject_xor",
        ),
        db.CheckConstraint("start_s >= 0 AND end_s > start_s AND end_s-start_s <= 60", name="ck_highlight_range"),
        db.CheckConstraint("player_decision IN ('pending','approve','private')", name="ck_highlight_decision"),
        db.CheckConstraint(
            "render_status IN ('queued','running','ready','failed','stale')", name="ck_highlight_render"
        ),
    )
    id = db.Column(db.String(36), primary_key=True, default=uuid4)
    program_id = db.Column(
        db.Integer, db.ForeignKey("club_programs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id", ondelete="SET NULL"), index=True)
    roster_entry_id = db.Column(db.Integer, db.ForeignKey("video_roster_entries.id", ondelete="SET NULL"))
    tracklet_id = db.Column(db.Integer, db.ForeignKey("video_tracklets.id", ondelete="SET NULL"))
    player_api_id = db.Column(db.Integer, index=True)
    local_player_id = db.Column(db.Integer, db.ForeignKey("local_players.id", ondelete="CASCADE"), index=True)
    claim_id = db.Column(db.Integer, db.ForeignKey("player_profile_claims.id", ondelete="SET NULL"))
    recipient_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"), index=True)
    picker_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    pick_key = db.Column(db.String(64), nullable=False)
    source_etag = db.Column(db.String(100), nullable=False)
    source_snapshot = db.Column(db.String(64), nullable=False)
    source_fingerprint = db.Column(db.String(64), nullable=False)
    source_version = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    start_s = db.Column(db.Float, nullable=False)
    end_s = db.Column(db.Float, nullable=False)
    title = db.Column(db.String(160), nullable=False)
    version = db.Column(db.Integer, nullable=False, default=1, server_default="1")
    club_picked_at = db.Column(db.DateTime, nullable=False, default=now)
    player_decision = db.Column(db.String(20), nullable=False, default="pending", server_default="pending")
    decision_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    decision_at = db.Column(db.DateTime)
    approved_source_version = db.Column(db.Integer)
    revoked_at = db.Column(db.DateTime)
    revoke_reason = db.Column(db.String(30))
    admin_taken_down = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    render_status = db.Column(db.String(20), nullable=False, default="queued", server_default="queued")
    output_blob_path = db.Column(db.String(500))
    output_etag = db.Column(db.String(100))
    output_bytes = db.Column(db.Integer)
    render_source_version = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, nullable=False, default=now)

    @property
    def signed_id(self):
        return self.player_api_id if self.player_api_id is not None else -self.local_player_id


class HighlightConsentEvent(db.Model):
    __tablename__ = "highlight_consent_events"
    id = db.Column(db.Integer, primary_key=True)
    highlight_id = db.Column(
        db.String(36), db.ForeignKey("player_highlights.id", ondelete="CASCADE"), nullable=False, index=True
    )
    actor_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    action = db.Column(db.String(30), nullable=False)
    version = db.Column(db.Integer, nullable=False)
    source_version = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=now)


class HighlightFootageReview(db.Model):
    """Whole-club human review covers opposition and bystanders, not just our roster."""

    __tablename__ = "highlight_footage_reviews"
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id", ondelete="CASCADE"), primary_key=True)
    reviewer_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    classification = db.Column(db.String(20), nullable=False, default="private")
    source_etag = db.Column(db.String(100), nullable=False)
    source_snapshot = db.Column(db.String(64), nullable=False)
    reviewed_at = db.Column(db.DateTime, nullable=False, default=now)
    source_context = db.Column(db.String(64))
    squad_adult_attested = db.Column(db.Boolean, nullable=False, default=False, server_default="false")
    __table_args__ = (
        db.CheckConstraint("classification IN ('adult_only','private')", name="ck_highlight_footage_review"),
    )


class HighlightRenderJob(db.Model):
    __tablename__ = "highlight_render_jobs"
    id = db.Column(db.String(36), primary_key=True, default=uuid4)
    highlight_id = db.Column(db.String(36), db.ForeignKey("player_highlights.id", ondelete="SET NULL"), index=True)
    kind = db.Column(db.String(30), nullable=False, default="highlight_cut")
    source_version = db.Column(db.Integer)
    status = db.Column(db.String(20), nullable=False, default="queued", server_default="queued", index=True)
    attempt = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    lease_token = db.Column(db.String(36))
    lease_expires_at = db.Column(db.DateTime)
    # Attempt-specific path: stale workers can only leave inaccessible garbage, never overwrite a live cut.
    blob_path = db.Column(db.String(500))
    error_code = db.Column(db.String(40))
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    completed_at = db.Column(db.DateTime)
    __table_args__ = (
        db.CheckConstraint("kind IN ('highlight_cut','highlight_delete')", name="ck_highlight_job_kind"),
        db.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')", name="ck_highlight_job_status"
        ),
    )


class HighlightTakedown(db.Model):
    """Minimal recording-window moderation hold; survives subject erasure."""

    __tablename__ = "highlight_takedowns"
    id = db.Column(db.String(36), primary_key=True)
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id", ondelete="CASCADE"), nullable=False)
    start_s = db.Column(db.Float, nullable=False)
    end_s = db.Column(db.Float, nullable=False)
    lifted_at = db.Column(db.DateTime)
    __table_args__ = (
        db.Index("ix_highlight_takedown_window", "video_match_id", "start_s", "end_s"),
        db.CheckConstraint(
            "start_s >= 0 AND end_s > start_s AND end_s-start_s <= 60", name="ck_highlight_takedown_range"
        ),
    )
