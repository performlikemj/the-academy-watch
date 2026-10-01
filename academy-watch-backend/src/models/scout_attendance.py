"""Scout-to-club attendance, separate from every player/application relationship."""

import sqlalchemy as sa
from src.models.league import db
from src.models.opportunities import now, uid


class ScoutAttendance(db.Model):
    __tablename__ = "scout_attendance_requests"
    __table_args__ = (
        sa.UniqueConstraint("opportunity_id", "scout_user_id", name="uq_scout_attendance_subject"),
        sa.CheckConstraint(
            "status IN ('pending','accepted','declined','withdrawn')", name="ck_scout_attendance_status"
        ),
        sa.CheckConstraint("version > 0", name="ck_scout_attendance_version"),
        sa.Index("ix_scout_attendance_inbox", "program_id", "status", "created_at"),
        sa.Index("ix_scout_attendance_retention", "retention_expires_at"),
    )
    id = db.Column(db.String(36), primary_key=True, default=uid)
    opportunity_id = db.Column(
        db.String(36), db.ForeignKey("club_opportunities.id", ondelete="CASCADE"), nullable=False
    )
    program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id"), nullable=False)
    scout_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False)
    note = db.Column(db.String(500), nullable=False, default="")
    status = db.Column(db.String(20), nullable=False, default="pending")
    version = db.Column(db.Integer, nullable=False, default=1)
    decision_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id", ondelete="SET NULL"))
    arrival_instructions = db.Column(db.String(500), nullable=False, default="")
    created_at = db.Column(db.DateTime, nullable=False, default=now)
    updated_at = db.Column(db.DateTime, nullable=False, default=now)
    retention_expires_at = db.Column(db.DateTime, nullable=False)
