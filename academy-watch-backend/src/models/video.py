"""
Video Analysis Models (Phase A — concierge MVP)

Match-video upload → GPU pipeline → tag review → per-player reports.
Spec: ledgers/CONTINUITY_video-analysis.md "Data model" section.

Key invariants:
- VideoMatch.team_id is the PAYING club (NOT NULL). Opposition is free text and
  is only ever identified by jersey number — never names (legal posture).
- VideoCreditLedger is append-only; a team's balance is SUM(delta). The Stripe
  session id carries a unique constraint so webhook replays cannot double-credit.
- VideoTracklet rows are what human tags bind to. `kind` distinguishes
  number-anchored chains (pre-merged players) from leftover fragments the
  review UI may still attach.
- VideoPlayerReport carries model_version so Phase D trend views never silently
  mix numbers produced by different pipeline versions.
"""

import uuid
from datetime import UTC, datetime

from src.models.league import db

# VideoMatch.status lifecycle (forward-only except admin requeue)
VIDEO_MATCH_STATUSES = (
    "created",  # row exists, SAS issued, nothing uploaded yet
    "uploaded",  # client reported upload-complete; blob verified
    "preflight",  # CPU sample quality gate running
    "queued",  # debited, waiting for a GPU worker
    "processing",  # GPU worker owns it
    "needs_tagging",  # pipeline done; awaiting human tag review
    "finalized",  # tags confirmed; reports generated
    "failed",  # terminal error (credit refunded by admin/auto policy)
    "expired",  # raw footage past retention; derived data kept
)

VIDEO_JOB_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")

# Pipeline stages reported by the worker for progress display
VIDEO_JOB_STAGES = (
    "claimed",
    "decode",
    "detect",
    "track",
    "team_cluster",
    "merge",
    "identity",
    "artifacts",
    "persist",
)

CREDIT_REASONS = ("purchase", "debit", "refund", "grant")

# Per-player report identity gate. A stat is only as trustworthy as this.
IDENTITY_CONFIDENCE = ("human_confirmed", "high", "low", "unverified")

# What KIND of number a metric is — so a biased partial is never shown as a full total.
#   point           direct, trustworthy measurement (minutes on camera, fastest sustained speed)
#   lower_bound     only confident windows seen, so counts are floors ("at least N")
#   partial_observed aggregate over a biased (near-side) sample — never a full-match total
#   beta            experimental; suppressed below a quality threshold
#   suppressed      cannot be measured reliably yet → value null, never fabricated
METRIC_KINDS = ("point", "lower_bound", "partial_observed", "beta", "suppressed")


def _utcnow() -> datetime:
    return datetime.now(UTC)


class VideoMatch(db.Model):
    __tablename__ = "video_matches"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True)

    # Match metadata (opponent stays free text — opposition players are numbers only)
    opponent_name = db.Column(db.String(200))
    match_date = db.Column(db.Date)
    competition = db.Column(db.String(200))
    our_kit_color = db.Column(db.String(50))
    opponent_kit_color = db.Column(db.String(50))
    capture_meta = db.Column(db.JSON)  # camera questionnaire: type, position, resolution

    # Footage
    blob_path = db.Column(db.String(500))  # container-relative path of the raw upload
    blob_etag = db.Column(db.String(100))  # recorded at upload-complete, verified at job start
    duration_s = db.Column(db.Float)
    # Uploader-marked timeline points (10s of human input beats fragile inference)
    kickoff_s = db.Column(db.Float)
    halftime_s = db.Column(db.Float)
    second_half_kickoff_s = db.Column(db.Float)

    # Which KMeans cluster (0/1) is the uploader's team — confirmed during tagging
    our_team_cluster = db.Column(db.Integer)

    status = db.Column(db.String(20), nullable=False, default="created", index=True)
    quality_score = db.Column(db.Float)  # preflight + pipeline quality signal, 0..1
    quality_flags = db.Column(db.JSON)  # e.g. ["kit_clash", "pitch_level_camera"]

    created_at = db.Column(db.DateTime, default=_utcnow)
    uploaded_at = db.Column(db.DateTime)
    finalized_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)  # raw-footage retention deadline (90d policy)

    team = db.relationship("Team", foreign_keys=[team_id])
    jobs = db.relationship(
        "VideoAnalysisJob",
        backref="match",
        lazy="dynamic",
        order_by="VideoAnalysisJob.created_at.desc()",
    )
    roster_entries = db.relationship("VideoRosterEntry", backref="match", lazy="dynamic")
    tracklets = db.relationship("VideoTracklet", backref="match", lazy="dynamic")

    def latest_job(self):
        return self.jobs.first()

    def to_dict(self, include_job: bool = False) -> dict:
        out = {
            "id": self.id,
            "team_id": self.team_id,
            "opponent_name": self.opponent_name,
            "match_date": self.match_date.isoformat() if self.match_date else None,
            "competition": self.competition,
            "our_kit_color": self.our_kit_color,
            "opponent_kit_color": self.opponent_kit_color,
            "capture_meta": self.capture_meta,
            "blob_path": self.blob_path,
            "duration_s": self.duration_s,
            "kickoff_s": self.kickoff_s,
            "halftime_s": self.halftime_s,
            "second_half_kickoff_s": self.second_half_kickoff_s,
            "our_team_cluster": self.our_team_cluster,
            "status": self.status,
            "quality_score": self.quality_score,
            "quality_flags": self.quality_flags,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "finalized_at": self.finalized_at.isoformat() if self.finalized_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
        }
        if include_job:
            job = self.latest_job()
            out["job"] = job.to_dict() if job else None
        return out


class VideoAnalysisJob(db.Model):
    __tablename__ = "video_analysis_jobs"

    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id"), nullable=False, index=True)

    status = db.Column(db.String(20), nullable=False, default="queued", index=True)
    stage = db.Column(db.String(30))  # one of VIDEO_JOB_STAGES while running
    progress = db.Column(db.Integer, default=0)  # 0..100 within the current stage
    attempt = db.Column(db.Integer, nullable=False, default=1)
    worker_id = db.Column(db.String(100))  # replica name that claimed the job
    error = db.Column(db.Text)

    # COGS telemetry — the cost dashboard consumes this (ledger requirement)
    gpu_seconds = db.Column(db.Float)
    pipeline_version = db.Column(db.String(40))

    created_at = db.Column(db.DateTime, default=_utcnow)
    started_at = db.Column(db.DateTime)
    heartbeat_at = db.Column(db.DateTime)  # stale-fail reaper checks this
    completed_at = db.Column(db.DateTime)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "video_match_id": self.video_match_id,
            "status": self.status,
            "stage": self.stage,
            "progress": self.progress,
            "attempt": self.attempt,
            "error": self.error,
            "gpu_seconds": self.gpu_seconds,
            "pipeline_version": self.pipeline_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class VideoRosterEntry(db.Model):
    """One squad member of the UPLOADING team for one match. Own-side only
    carries names in v1; opposition is numbers-only and never gets roster rows."""

    __tablename__ = "video_roster_entries"
    __table_args__ = (db.UniqueConstraint("video_match_id", "jersey_number", name="uq_video_roster_match_number"),)

    id = db.Column(db.Integer, primary_key=True)
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id"), nullable=False, index=True)
    player_name = db.Column(db.String(200), nullable=False)
    jersey_number = db.Column(db.Integer, nullable=False)
    position = db.Column(db.String(50))
    # Optional link into the existing tracking universe (club-owned record → pro journey hook)
    tracked_player_id = db.Column(db.Integer, db.ForeignKey("tracked_players.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=_utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "video_match_id": self.video_match_id,
            "player_name": self.player_name,
            "jersey_number": self.jersey_number,
            "position": self.position,
            "tracked_player_id": self.tracked_player_id,
        }


class VideoTracklet(db.Model):
    """A merged on-pitch entity the tagging UI binds to a roster entry.

    kind='chain'    number-anchored player chain (pre-merged by the identity pass)
    kind='fragment' unanchored fragment awaiting human attachment or dismissal
    """

    __tablename__ = "video_tracklets"

    id = db.Column(db.Integer, primary_key=True)
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id"), nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False, default="fragment")
    pipeline_key = db.Column(db.String(40))  # e.g. "T0#10" or "E1234" from the worker

    team_cluster = db.Column(db.Integer)  # 0/1 KMeans side, -1 unknown
    suggested_number = db.Column(db.Integer)
    suggested_role = db.Column(db.String(20))  # outfield|goalkeeper|referee|not_a_player
    confidence = db.Column(db.String(10))  # high|low|None
    merge_confidence = db.Column(db.Float)
    contaminated = db.Column(db.Boolean, nullable=False, default=False)  # splice suspect

    first_s = db.Column(db.Float)
    last_s = db.Column(db.Float)
    visible_s = db.Column(db.Float)
    thumbnail_paths = db.Column(db.JSON)  # blob paths of the sharpest crops
    evidence = db.Column(db.JSON)  # vote tallies, member fragments, conflict flags

    # The tag: binding to a roster entry (own team) — set by human review or
    # auto-accepted high-confidence suggestion
    roster_entry_id = db.Column(db.Integer, db.ForeignKey("video_roster_entries.id"), nullable=True, index=True)
    tag_source = db.Column(db.String(10))  # auto|human|None
    dismissed = db.Column(db.Boolean, nullable=False, default=False)  # marked not-a-player

    roster_entry = db.relationship("VideoRosterEntry", foreign_keys=[roster_entry_id])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "video_match_id": self.video_match_id,
            "kind": self.kind,
            "pipeline_key": self.pipeline_key,
            "team_cluster": self.team_cluster,
            "suggested_number": self.suggested_number,
            "suggested_role": self.suggested_role,
            "confidence": self.confidence,
            "merge_confidence": self.merge_confidence,
            "contaminated": self.contaminated,
            "first_s": self.first_s,
            "last_s": self.last_s,
            "visible_s": self.visible_s,
            "thumbnail_paths": self.thumbnail_paths,
            "evidence": self.evidence,
            "roster_entry_id": self.roster_entry_id,
            "tag_source": self.tag_source,
            "dismissed": self.dismissed,
        }


class VideoPlayerReport(db.Model):
    __tablename__ = "video_player_reports"
    __table_args__ = (db.UniqueConstraint("video_match_id", "roster_entry_id", name="uq_video_report_match_roster"),)

    id = db.Column(db.Integer, primary_key=True)
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id"), nullable=False, index=True)
    roster_entry_id = db.Column(db.Integer, db.ForeignKey("video_roster_entries.id"), nullable=False)
    # Denormalized for the PlayerPage join (authed + team-scoped, never public)
    tracked_player_id = db.Column(db.Integer, db.ForeignKey("tracked_players.id"), nullable=True, index=True)

    minutes_visible = db.Column(db.Float)  # on-camera minutes — NEVER implied as full-match
    distance_m = db.Column(db.Float)  # on-camera distance, clamped
    distance_confidence = db.Column(db.String(10))  # high|low (far-side flagging)
    fastest_sustained_kmh = db.Column(db.Float)  # sustained only; jitter fakes instantaneous
    sprint_count = db.Column(db.Integer)
    speed_bands = db.Column(db.JSON)  # seconds per band
    heatmap_path = db.Column(db.String(500))
    touches = db.Column(db.Integer)
    touches_is_beta = db.Column(db.Boolean, nullable=False, default=True)

    # Structured confidence-per-field report (the contract; see services/video_report.py).
    # identity is the GATE — every metric below is only as true as the identity it hangs on.
    identity_confidence = db.Column(db.String(20))  # one of IDENTITY_CONFIDENCE
    identity_evidence = db.Column(db.JSON)  # {source, votes, splice_risk, human_reviewed}
    coverage = db.Column(db.JSON)  # {on_camera_min, confident_windows, pct_of_match, span_s, near_side_pct, sampling}
    metrics = db.Column(db.JSON)  # [{key, value, unit, confidence, kind, note, suppressed}]
    events = db.Column(db.JSON)  # [{type, t, confidence, clip}]

    model_version = db.Column(db.String(40), nullable=False)
    created_at = db.Column(db.DateTime, default=_utcnow)

    roster_entry = db.relationship("VideoRosterEntry", foreign_keys=[roster_entry_id])

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "video_match_id": self.video_match_id,
            "roster_entry_id": self.roster_entry_id,
            "tracked_player_id": self.tracked_player_id,
            "minutes_visible": self.minutes_visible,
            "distance_m": self.distance_m,
            "distance_confidence": self.distance_confidence,
            "fastest_sustained_kmh": self.fastest_sustained_kmh,
            "sprint_count": self.sprint_count,
            "speed_bands": self.speed_bands,
            "heatmap_path": self.heatmap_path,
            "touches": self.touches,
            "touches_is_beta": self.touches_is_beta,
            "identity_confidence": self.identity_confidence,
            "identity_evidence": self.identity_evidence,
            "coverage": self.coverage,
            "metrics": self.metrics,
            "events": self.events,
            "model_version": self.model_version,
        }


class VideoCreditLedger(db.Model):
    """Append-only credit movements. Balance(team) = SUM(delta). Never UPDATE rows."""

    __tablename__ = "video_credit_ledger"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("teams.id"), nullable=False, index=True)
    delta = db.Column(db.Integer, nullable=False)  # +purchase/+grant/+refund, -debit
    reason = db.Column(db.String(20), nullable=False)  # one of CREDIT_REASONS
    note = db.Column(db.String(500))
    video_match_id = db.Column(db.Integer, db.ForeignKey("video_matches.id"), nullable=True)
    # Unique => a replayed Stripe webhook cannot double-credit
    stripe_session_id = db.Column(db.String(255), unique=True, nullable=True)
    created_by = db.Column(db.String(100))  # admin identifier for grants/refunds

    created_at = db.Column(db.DateTime, default=_utcnow)

    @staticmethod
    def balance(team_id: int) -> int:
        total = (
            db.session.query(db.func.coalesce(db.func.sum(VideoCreditLedger.delta), 0))
            .filter(VideoCreditLedger.team_id == team_id)
            .scalar()
        )
        return int(total or 0)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "team_id": self.team_id,
            "delta": self.delta,
            "reason": self.reason,
            "note": self.note,
            "video_match_id": self.video_match_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
