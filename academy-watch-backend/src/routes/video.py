"""Video-analysis API (Phase A — concierge MVP).

Lifecycle: create match (mint SAS) → browser uploads direct to blob →
upload-complete (verify + ETag) → roster upsert → process (debit + enqueue) →
worker runs pipeline → tag review (tracklets/tags) → finalize → report.

Phase A posture: EVERY endpoint is admin-key gated (concierge — we operate it
with the club on a call). Phase B introduces VideoTeamAccess + is_team_manager.
Player video reports are AUTHENTICATED + team-scoped, never public (children's
performance data).

Credit safety: VideoCreditLedger is append-only; debit + job-create + status
flip commit atomically in Postgres, THEN the queue signal fires — a lost signal
degrades to worker DB-polling, never a lost job.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from flask import Blueprint, jsonify, request
from src.models.league import Team, db
from src.models.video import (
    CREDIT_REASONS,
    VideoAnalysisJob,
    VideoCreditLedger,
    VideoMatch,
    VideoPlayerReport,
    VideoRosterEntry,
    VideoTracklet,
)
from src.routes.api import require_api_key
from src.services import video_queue, video_storage
from src.services.video_report import build_player_report, tracklet_to_bound

video_bp = Blueprint("video", __name__)
logger = logging.getLogger(__name__)

RAW_RETENTION_DAYS = 90  # ToS: raw footage deleted at 90d; derived numbers kept
PIPELINE_VERSION = "phase-a-v1"


def _get_match_or_404(match_id: int) -> "VideoMatch | tuple":
    match = db.session.get(VideoMatch, match_id)
    if match is None:
        return None
    return match


def _bad_request(msg: str):
    return jsonify({"error": msg}), 400


# ---------------------------------------------------------------------------
# Match lifecycle
# ---------------------------------------------------------------------------


@video_bp.route("/admin/video/matches", methods=["POST"])
@require_api_key
def create_video_match():
    """Create a match shell and mint the upload SAS.

    Body: {team_id, opponent_name?, match_date?, competition?, our_kit_color?,
           opponent_kit_color?, capture_meta?}
    """
    data = request.get_json() or {}
    team_id = data.get("team_id")
    if not team_id or db.session.get(Team, team_id) is None:
        return _bad_request("team_id must reference an existing team")

    match_date = None
    if data.get("match_date"):
        try:
            match_date = datetime.strptime(data["match_date"], "%Y-%m-%d").date()
        except ValueError:
            return _bad_request("match_date must be YYYY-MM-DD")

    match = VideoMatch(
        team_id=team_id,
        opponent_name=data.get("opponent_name"),
        match_date=match_date,
        competition=data.get("competition"),
        our_kit_color=data.get("our_kit_color"),
        opponent_kit_color=data.get("opponent_kit_color"),
        capture_meta=data.get("capture_meta"),
        status="created",
    )
    db.session.add(match)
    db.session.flush()
    match.blob_path = f"matches/{match.id}/{uuid.uuid4().hex}.mp4"
    db.session.commit()

    payload = match.to_dict()
    if video_storage.is_configured():
        payload["upload"] = video_storage.mint_upload_sas(match.blob_path)
    else:
        payload["upload"] = None
        payload["upload_unavailable"] = "blob storage not configured"
    return jsonify(payload), 201


@video_bp.route("/admin/video/matches/<int:match_id>/sas", methods=["POST"])
@require_api_key
def remint_upload_sas(match_id: int):
    """Re-mint the write SAS — 6GB at club uplink speeds outlives 60 minutes."""
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    if match.status not in ("created", "uploaded"):
        return _bad_request(f"cannot re-mint SAS in status '{match.status}'")
    if not video_storage.is_configured():
        return jsonify({"error": "blob storage not configured"}), 503
    return jsonify(video_storage.mint_upload_sas(match.blob_path))


@video_bp.route("/admin/video/matches/<int:match_id>/upload-complete", methods=["POST"])
@require_api_key
def upload_complete(match_id: int):
    """Verify the uploaded blob (exists, size cap), record ETag for the
    job-start content-swap check, optionally capture timeline markers."""
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    if match.status not in ("created", "uploaded"):
        return _bad_request(f"cannot complete upload in status '{match.status}'")
    if not video_storage.is_configured():
        return jsonify({"error": "blob storage not configured"}), 503

    check = video_storage.verify_uploaded_blob(match.blob_path)
    if not check["ok"]:
        return jsonify({"error": check["error"]}), 422

    data = request.get_json(silent=True) or {}
    for field in ("kickoff_s", "halftime_s", "second_half_kickoff_s", "duration_s"):
        if data.get(field) is not None:
            try:
                setattr(match, field, float(data[field]))
            except (TypeError, ValueError):
                return _bad_request(f"{field} must be a number")

    match.blob_etag = check["etag"]
    match.status = "uploaded"
    match.uploaded_at = datetime.now(UTC)
    match.expires_at = datetime.now(UTC) + timedelta(days=RAW_RETENTION_DAYS)
    db.session.commit()
    return jsonify(match.to_dict() | {"size_bytes": check["size_bytes"]})


@video_bp.route("/admin/video/matches/<int:match_id>", methods=["PATCH"])
@require_api_key
def update_video_match(match_id: int):
    """Update metadata / timeline markers / our-team-cluster confirmation."""
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    data = request.get_json() or {}
    for field in ("opponent_name", "competition", "our_kit_color", "opponent_kit_color"):
        if field in data:
            setattr(match, field, data[field])
    for field in ("kickoff_s", "halftime_s", "second_half_kickoff_s"):
        if field in data:
            try:
                setattr(match, field, None if data[field] is None else float(data[field]))
            except (TypeError, ValueError):
                return _bad_request(f"{field} must be a number")
    auto_bound = None
    if "our_team_cluster" in data:
        if data["our_team_cluster"] not in (0, 1, None):
            return _bad_request("our_team_cluster must be 0, 1 or null")
        match.our_team_cluster = data["our_team_cluster"]
    if "capture_meta" in data:
        match.capture_meta = data["capture_meta"]
    db.session.commit()
    if data.get("our_team_cluster") in (0, 1) and match.status in ("needs_tagging", "finalized"):
        from src.services.video_identity import auto_bind

        auto_bound = auto_bind(match)
    out = match.to_dict()
    if auto_bound is not None:
        out["auto_bound"] = auto_bound
    return jsonify(out)


@video_bp.route("/admin/video/matches/<int:match_id>", methods=["GET"])
@require_api_key
def get_video_match(match_id: int):
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    out = match.to_dict(include_job=True)
    out["roster"] = [r.to_dict() for r in match.roster_entries]
    out["credit_balance"] = VideoCreditLedger.balance(match.team_id)
    return jsonify(out)


# ---------------------------------------------------------------------------
# Roster
# ---------------------------------------------------------------------------


@video_bp.route("/admin/video/matches/<int:match_id>/roster", methods=["PUT"])
@require_api_key
def upsert_roster(match_id: int):
    """Replace-style upsert of the uploading team's squad list.

    Body: {entries: [{player_name, jersey_number, position?, tracked_player_id?}]}
    Own-side only carries names in v1; opposition never gets roster rows.
    """
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    if match.status == "finalized":
        return _bad_request("cannot edit roster after finalize")

    entries = (request.get_json() or {}).get("entries")
    if not isinstance(entries, list) or not entries:
        return _bad_request("entries must be a non-empty list")
    seen_numbers: set[int] = set()
    for e in entries:
        name = (e.get("player_name") or "").strip()
        number = e.get("jersey_number")
        if not name or not isinstance(number, int) or not 1 <= number <= 99:
            return _bad_request("each entry needs player_name and jersey_number 1-99")
        if number in seen_numbers:
            return _bad_request(f"duplicate jersey_number {number}")
        seen_numbers.add(number)

    existing = {r.jersey_number: r for r in match.roster_entries}
    kept_numbers = set()
    for e in entries:
        number = e["jersey_number"]
        kept_numbers.add(number)
        row = existing.get(number)
        if row is None:
            row = VideoRosterEntry(video_match_id=match.id, jersey_number=number, player_name=e["player_name"].strip())
            db.session.add(row)
        row.player_name = e["player_name"].strip()
        row.position = e.get("position")
        row.tracked_player_id = e.get("tracked_player_id")
    removed = 0
    for number, row in existing.items():
        if number not in kept_numbers:
            # unbind any tracklets pointing at the removed entry first
            db.session.query(VideoTracklet).filter(VideoTracklet.roster_entry_id == row.id).update(
                {"roster_entry_id": None, "tag_source": None}, synchronize_session=False
            )
            db.session.query(VideoPlayerReport).filter(VideoPlayerReport.roster_entry_id == row.id).delete(
                synchronize_session=False
            )
            db.session.delete(row)
            removed += 1
    db.session.commit()
    return jsonify(
        {
            "roster": [r.to_dict() for r in match.roster_entries],
            "removed": removed,
        }
    )


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------


@video_bp.route("/admin/video/matches/<int:match_id>/process", methods=["POST"])
@require_api_key
def process_match(match_id: int):
    """Debit one credit and queue the GPU job. 402 when the team has no credits."""
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    if match.status not in ("uploaded", "preflight"):
        return _bad_request(f"cannot process in status '{match.status}' (upload first)")
    if match.kickoff_s is None:
        return _bad_request("kickoff_s must be marked before processing")

    if VideoCreditLedger.balance(match.team_id) < 1:
        return jsonify({"error": "no credits", "credit_balance": 0}), 402

    job = VideoAnalysisJob(
        video_match_id=match.id,
        status="queued",
        pipeline_version=PIPELINE_VERSION,
    )
    db.session.add(job)
    db.session.add(
        VideoCreditLedger(
            team_id=match.team_id,
            delta=-1,
            reason="debit",
            video_match_id=match.id,
            note=f"processing job {job.id}",
        )
    )
    match.status = "queued"
    db.session.commit()  # debit + job + status are atomic; signal comes after
    mode = video_queue.enqueue(job.id)
    logger.info("video match %s queued as job %s via %s", match.id, job.id, mode)
    return jsonify({"job": job.to_dict(), "dispatch": mode}), 202


@video_bp.route("/admin/video/matches/<int:match_id>/requeue", methods=["POST"])
@require_api_key
def requeue_match(match_id: int):
    """Admin: re-run a failed job WITHOUT a new debit."""
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    last = match.latest_job()
    if last is None or last.status not in ("failed", "cancelled"):
        return _bad_request("requeue requires a failed or cancelled job")
    job = VideoAnalysisJob(
        video_match_id=match.id,
        status="queued",
        attempt=last.attempt + 1,
        pipeline_version=PIPELINE_VERSION,
    )
    db.session.add(job)
    match.status = "queued"
    db.session.commit()
    mode = video_queue.enqueue(job.id)
    return jsonify({"job": job.to_dict(), "dispatch": mode}), 202


# ---------------------------------------------------------------------------
# Tag review
# ---------------------------------------------------------------------------


@video_bp.route("/admin/video/matches/<int:match_id>/tracklets", methods=["GET"])
@require_api_key
def list_tracklets(match_id: int):
    """Tracklets for the review UI, untagged-first then by minutes visible
    (the queue is ranked uncertainty x visibility)."""
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    q = db.session.query(VideoTracklet).filter(VideoTracklet.video_match_id == match.id)
    kind = request.args.get("kind")
    if kind in ("chain", "fragment"):
        q = q.filter(VideoTracklet.kind == kind)
    if request.args.get("untagged") == "true":
        q = q.filter(VideoTracklet.roster_entry_id.is_(None), VideoTracklet.dismissed.is_(False))
    rows = q.order_by(
        VideoTracklet.roster_entry_id.isnot(None),
        VideoTracklet.dismissed,
        VideoTracklet.visible_s.desc().nulls_last(),
    ).all()
    return jsonify({"tracklets": [t.to_dict() for t in rows], "count": len(rows)})


@video_bp.route("/admin/video/matches/<int:match_id>/tags", methods=["POST"])
@require_api_key
def bind_tags(match_id: int):
    """Bulk tag bindings from the review UI.

    Body: {tags: [{tracklet_id, roster_entry_id?|null, dismissed?}]}
    roster_entry_id null unbinds; dismissed=true marks not-a-player.
    """
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    if match.status not in ("needs_tagging", "finalized"):
        return _bad_request(f"tagging unavailable in status '{match.status}'")

    tags = (request.get_json() or {}).get("tags")
    if not isinstance(tags, list) or not tags:
        return _bad_request("tags must be a non-empty list")

    tracklets = {t.id: t for t in db.session.query(VideoTracklet).filter(VideoTracklet.video_match_id == match.id)}
    roster_ids = {r.id for r in match.roster_entries}
    applied = 0
    for tag in tags:
        t = tracklets.get(tag.get("tracklet_id"))
        if t is None:
            return _bad_request(f"tracklet {tag.get('tracklet_id')} not in this match")
        if "roster_entry_id" in tag:
            rid = tag["roster_entry_id"]
            if rid is not None and rid not in roster_ids:
                return _bad_request(f"roster entry {rid} not in this match")
            t.roster_entry_id = rid
            t.tag_source = "human" if rid is not None else None
        if tag.get("dismissed") is not None:
            t.dismissed = bool(tag["dismissed"])
            if t.dismissed:
                t.roster_entry_id = None
                t.tag_source = None
        applied += 1
    db.session.commit()
    return jsonify({"applied": applied})


@video_bp.route("/admin/video/matches/<int:match_id>/finalize", methods=["POST"])
@require_api_key
def finalize_match(match_id: int):
    """Aggregate tagged tracklets into per-player reports (CPU re-aggregation —
    tag fixes never re-run the GPU). Idempotent: re-finalizing rebuilds reports."""
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    if match.status not in ("needs_tagging", "finalized"):
        return _bad_request(f"cannot finalize in status '{match.status}'")

    job = match.latest_job()
    model_version = (job.pipeline_version if job else None) or PIPELINE_VERSION

    db.session.query(VideoPlayerReport).filter(VideoPlayerReport.video_match_id == match.id).delete(
        synchronize_session=False
    )

    reports = []
    for entry in match.roster_entries:
        bound = (
            db.session.query(VideoTracklet)
            .filter(
                VideoTracklet.video_match_id == match.id,
                VideoTracklet.roster_entry_id == entry.id,
                VideoTracklet.dismissed.is_(False),
            )
            .all()
        )
        # A roster player with no confident tracklets still gets a report — an
        # "unverified / 0 on-camera" row is more honest than silent omission (the
        # coach can tell "we saw nothing of them" from "not in the squad").
        # Build the structured confidence-per-field report. Phase A v1: identity +
        # coverage + on-camera minutes are real; distance/speed/heatmaps are emitted
        # as `suppressed` (value null) until the homography stage — never fabricated.
        team_cluster = next((t.team_cluster for t in bound if t.team_cluster in (0, 1)), None)
        structured = build_player_report(
            jersey_number=entry.jersey_number,
            team_cluster=team_cluster,
            our_team_cluster=match.our_team_cluster,
            bound=[tracklet_to_bound(t) for t in bound],
            match_duration_s=match.duration_s,
        )
        identity = structured["identity"]
        report = VideoPlayerReport(
            video_match_id=match.id,
            roster_entry_id=entry.id,
            tracked_player_id=entry.tracked_player_id,
            minutes_visible=structured["coverage"]["on_camera_min"],
            touches_is_beta=True,
            identity_confidence=identity["confidence"],
            identity_evidence={
                "source": identity["source"],
                "votes": identity["votes"],
                "splice_risk": identity["splice_risk"],
                "human_reviewed": identity["human_reviewed"],
            },
            coverage=structured["coverage"],
            metrics=structured["metrics"],
            events=structured["events"],
            model_version=model_version,
        )
        db.session.add(report)
        reports.append(report)

    match.status = "finalized"
    match.finalized_at = datetime.now(UTC)
    db.session.commit()
    return jsonify({"reports": len(reports), "match": match.to_dict()})


@video_bp.route("/admin/video/matches/<int:match_id>/report", methods=["GET"])
@require_api_key
def get_report(match_id: int):
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    reports = db.session.query(VideoPlayerReport).filter(VideoPlayerReport.video_match_id == match.id).all()
    roster_by_id = {r.id: r for r in match.roster_entries}
    out = []
    for rep in reports:
        d = rep.to_dict()
        entry = roster_by_id.get(rep.roster_entry_id)
        d["player_name"] = entry.player_name if entry else None
        d["jersey_number"] = entry.jersey_number if entry else None
        out.append(d)
    out.sort(key=lambda d: -(d["minutes_visible"] or 0))
    return jsonify({"match": match.to_dict(), "reports": out})


# ---------------------------------------------------------------------------
# Team views + credits
# ---------------------------------------------------------------------------


@video_bp.route("/admin/video/teams/<int:team_id>/matches", methods=["GET"])
@require_api_key
def team_matches(team_id: int):
    rows = (
        db.session.query(VideoMatch).filter(VideoMatch.team_id == team_id).order_by(VideoMatch.created_at.desc()).all()
    )
    return jsonify(
        {
            "matches": [m.to_dict(include_job=True) for m in rows],
            "credit_balance": VideoCreditLedger.balance(team_id),
        }
    )


@video_bp.route("/admin/video/teams/<int:team_id>/credits", methods=["GET"])
@require_api_key
def team_credits(team_id: int):
    rows = (
        db.session.query(VideoCreditLedger)
        .filter(VideoCreditLedger.team_id == team_id)
        .order_by(VideoCreditLedger.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify(
        {
            "balance": VideoCreditLedger.balance(team_id),
            "ledger": [r.to_dict() for r in rows],
        }
    )


@video_bp.route("/admin/video/teams/<int:team_id>/credits/grant", methods=["POST"])
@require_api_key
def grant_credits(team_id: int):
    """Admin credit movement. Body: {delta, reason?, note?}. Stripe purchases
    arrive via the webhook in Phase B; concierge sales are recorded here."""
    if db.session.get(Team, team_id) is None:
        return _bad_request("team not found")
    data = request.get_json() or {}
    delta = data.get("delta")
    if not isinstance(delta, int) or delta == 0:
        return _bad_request("delta must be a non-zero integer")
    reason = data.get("reason", "grant")
    if reason not in CREDIT_REASONS:
        return _bad_request(f"reason must be one of {CREDIT_REASONS}")
    db.session.add(
        VideoCreditLedger(
            team_id=team_id,
            delta=delta,
            reason=reason,
            note=data.get("note"),
            created_by="admin-api",
        )
    )
    db.session.commit()
    return jsonify({"balance": VideoCreditLedger.balance(team_id)})


@video_bp.route("/admin/video/matches/<int:match_id>/refund", methods=["POST"])
@require_api_key
def refund_match(match_id: int):
    """Refund the processing debit for a failed/poor-quality match (one per match)."""
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    already = (
        db.session.query(VideoCreditLedger)
        .filter(
            VideoCreditLedger.video_match_id == match.id,
            VideoCreditLedger.reason == "refund",
        )
        .first()
    )
    if already:
        return _bad_request("match already refunded")
    db.session.add(
        VideoCreditLedger(
            team_id=match.team_id,
            delta=1,
            reason="refund",
            video_match_id=match.id,
            note=(request.get_json(silent=True) or {}).get("note"),
            created_by="admin-api",
        )
    )
    db.session.commit()
    return jsonify({"balance": VideoCreditLedger.balance(match.team_id)})


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


@video_bp.route("/admin/video/reap-stale-jobs", methods=["POST"])
@require_api_key
def reap_stale():
    return jsonify({"stale_failed": video_queue.reap_stale_jobs()})
