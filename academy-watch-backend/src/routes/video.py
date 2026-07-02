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

import hashlib
import json
import logging
import math
import os
import uuid
from datetime import UTC, datetime, timedelta

from flask import Blueprint, Response, g, jsonify, redirect, request, send_file
from src.auth import mint_media_token, verify_media_token
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
from src.services import video_dev_artifacts, video_queue, video_storage
from src.services.video_feedback import build_feedback_labels
from src.services.video_identity import NUMBER_AGREEMENT_MIN, split_chain
from src.services.video_learning import match_accuracy, recalibration_signals, training_manifest
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
    for field in ("kickoff_s", "halftime_s", "second_half_kickoff_s", "duration_s"):
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
    q = db.session.query(VideoTracklet).filter(
        VideoTracklet.video_match_id == match.id,
        VideoTracklet.kind != "tombstone",  # internal: a split's replaced original
    )
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
    now = datetime.now(UTC)
    reviewer = getattr(g, "user_email", None)
    for tag in tags:
        t = tracklets.get(tag.get("tracklet_id"))
        if t is None:
            return _bad_request(f"tracklet {tag.get('tracklet_id')} not in this match")
        prev_rid = t.roster_entry_id
        action = None
        if tag.get("dismissed"):  # not-a-player wins outright
            t.dismissed = True
            t.roster_entry_id = None
            t.tag_source = None
            action = "dismissed"
        else:
            if tag.get("dismissed") is False:
                t.dismissed = False
            if "roster_entry_id" in tag:
                rid = tag["roster_entry_id"]
                if rid is not None and rid not in roster_ids:
                    return _bad_request(f"roster entry {rid} not in this match")
                t.roster_entry_id = rid
                if rid is not None:
                    t.dismissed = False  # binding a player and "not a player" are exclusive
                    t.tag_source = "human"
                    action = "confirmed" if rid == prev_rid else "reassigned"
                else:
                    t.tag_source = None
                    action = "reassigned"  # explicit unbind is still a human correction
            # an explicit "looks right" affirm makes an auto-binding a human signal
            if tag.get("action") == "confirmed" and t.roster_entry_id is not None:
                t.tag_source = "human"
                action = "confirmed"
        # ONLY a real decision stamps the audit fields — a no-op tag (e.g. a bulk
        # save re-sending unchanged rows) must never promote an auto row to
        # "human-reviewed" and leak the model's own guess into the feedback corpus.
        if action is not None:
            t.reviewed_at = now
            t.reviewer_email = reviewer
            t.review_action = action
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
# Review media — footage window, crop strip, bbox overlay (DEV: local; PROD: SAS)
# ---------------------------------------------------------------------------


@video_bp.route("/admin/video/matches/<int:match_id>/media-token", methods=["GET"])
@require_api_key
def media_token(match_id: int):
    """Mint a short-lived match-scoped token for <video>/<img> URLs (they can't
    send the admin Authorization + X-API-Key headers)."""
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    return jsonify(mint_media_token(match.id, email=getattr(g, "user_email", None)))


def _media_match_or_error(match_id: int):
    """Validate ?token= then load the match. Returns (match, None) or (None, resp)."""
    if not verify_media_token(request.args.get("token", ""), match_id):
        return None, (jsonify({"error": "invalid or expired media token"}), 403)
    match = _get_match_or_404(match_id)
    if match is None:
        return None, (jsonify({"error": "match not found"}), 404)
    return match, None


@video_bp.route("/admin/video/matches/<int:match_id>/footage", methods=["GET"])
def stream_footage(match_id: int):
    """Stream the match video with HTTP Range. DEV: local file (send_file conditional
    → 206/Accept-Ranges so <video> seeks without downloading GBs); PROD: 302 → read SAS."""
    match, err = _media_match_or_error(match_id)
    if err:
        return err
    if video_storage.is_configured():
        if not match.blob_path:
            return jsonify({"error": "no footage"}), 404
        return redirect(video_storage.mint_read_sas(match.blob_path))
    art = video_dev_artifacts.local_artifacts(match)
    path = (art or {}).get("footage")
    if not path or not os.path.exists(path):
        return jsonify({"error": "footage not available locally"}), 404
    resp = send_file(path, mimetype="video/mp4", conditional=True)
    resp.headers["Cache-Control"] = "private, no-store"  # token rides the URL — don't cache/leak
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


@video_bp.route("/admin/video/matches/<int:match_id>/crops/<crop_file>", methods=["GET"])
def serve_crop(match_id: int, crop_file: str):
    """Serve a tracklet crop JPEG. DEV: local crops dir (allowlist + realpath containment);
    PROD: 302 → blob thumbnail SAS."""
    match, err = _media_match_or_error(match_id)
    if err:
        return err
    if video_storage.is_configured():
        # PROD FOLLOW-UP: the vision worker does not yet persist crop JPEGs to blob,
        # so there is nothing to redirect to — fail honestly rather than 302 to a
        # phantom SAS. (Worker must upload crops/<match_id>/<key>/<file>.)
        return jsonify({"error": "crop serving not available in this environment"}), 501
    art = video_dev_artifacts.local_artifacts(match)
    path = video_dev_artifacts.crop_path(art, crop_file) if art else None
    if not path:
        return jsonify({"error": "crop not found"}), 404
    resp = send_file(path, mimetype="image/jpeg", conditional=True)
    resp.headers["Cache-Control"] = "private, no-store"
    resp.headers["Referrer-Policy"] = "no-referrer"
    return resp


def _tracklet_in_match_or_404(match_id: int, tracklet_id: int):
    t = db.session.get(VideoTracklet, tracklet_id)
    if t is None or t.video_match_id != match_id:
        return None, (jsonify({"error": "tracklet not in this match"}), 404)
    return t, None


@video_bp.route("/admin/video/matches/<int:match_id>/tracklets/<int:tracklet_id>/crops", methods=["GET"])
@require_api_key
def list_tracklet_crops(match_id: int, tracklet_id: int):
    """Sharpest-first crop list for one tracklet (URLs built client-side with the media token)."""
    t, err = _tracklet_in_match_or_404(match_id, tracklet_id)
    if err:
        return err
    match = db.session.get(VideoMatch, match_id)
    art = video_dev_artifacts.local_artifacts(match) if match else None
    if not art:  # prod: crops are blob thumbnail paths — return bare leaf names so the
        # crop route's string converter (no slashes) matches
        return jsonify({"crops": [{"file": os.path.basename(p)} for p in (t.thumbnail_paths or [])]})
    return jsonify({"crops": video_dev_artifacts.tracklet_crops(t, art)})


@video_bp.route("/admin/video/matches/<int:match_id>/tracklets/<int:tracklet_id>/bbox-track", methods=["GET"])
@require_api_key
def get_tracklet_bbox(match_id: int, tracklet_id: int):
    """Per-frame [t, x1, y1, x2, y2] (absolute seconds, source pixels) to overlay a box
    on the exact player. DEV-only (built from local tracks.npz); empty in prod."""
    t, err = _tracklet_in_match_or_404(match_id, tracklet_id)
    if err:
        return err
    match = db.session.get(VideoMatch, match_id)
    art = video_dev_artifacts.local_artifacts(match) if match else None
    if not art:
        return jsonify({"boxes": [], "available": False})
    return jsonify({"boxes": video_dev_artifacts.tracklet_bbox_track(t, art), "available": True})


def _clamp_pipeline_key(key: str, limit: int = 40) -> str:
    """Keep a composed split key within VideoTracklet.pipeline_key (String(40)).
    Nested splits append '|<seg>@<t>' each time and would eventually overflow the
    column → 500 on insert. When too long, keep a truncated prefix + a short stable
    hash of the full key so distinct segments stay distinct."""
    if len(key) <= limit:
        return key
    digest = hashlib.sha1(key.encode()).hexdigest()[:8]
    return f"{key[: limit - len(digest) - 1]}~{digest}"


@video_bp.route("/admin/video/matches/<int:match_id>/tracklets/<int:tracklet_id>/split", methods=["POST"])
@require_api_key
def split_tracklet(match_id: int, tracklet_id: int):
    """Cut a contaminated chain at `at_s` seconds into two segments the human can tag
    separately — when the auto-merge fused two players. Replaces the original; each
    segment is review_action='split' (survives pipeline re-runs) and carries a
    re-tallied number. The split itself is high-value training signal."""
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    if match.status not in ("needs_tagging", "finalized"):
        return _bad_request(f"split unavailable in status '{match.status}'")
    t, err = _tracklet_in_match_or_404(match_id, tracklet_id)
    if err:
        return err
    if t.kind != "chain":
        return _bad_request("only a chain can be split")
    try:
        at_s = float((request.get_json() or {})["at_s"])
    except (KeyError, TypeError, ValueError):
        return _bad_request("at_s (seconds) is required")
    if not math.isfinite(at_s):
        return _bad_request("at_s must be a finite number")
    art = video_dev_artifacts.local_artifacts(match)
    if not art:
        return jsonify({"error": "split needs local artifacts (dev only)"}), 501

    ev = t.evidence or {}
    members = [int(x) for x in ev.get("member_fragment_ids", [])]
    strong = [int(x) for x in ev.get("strong_fragment_ids", [])]
    votes_by_member = {int(k): v for k, v in (ev.get("votes") or {}).items()}
    segs = split_chain(members, strong, votes_by_member, video_dev_artifacts.fragment_spans(art), at_s)
    if len(segs) < 2:
        return _bad_request("that split point leaves a single segment — pick a time inside the window")

    now = datetime.now(UTC)
    reviewer = getattr(g, "user_email", None)
    # carry a human binding forward to the dominant segment (most strong fragments,
    # then most visible) instead of silently dropping it.
    carry_to = None
    if t.roster_entry_id and t.tag_source == "human":
        carry_to = max(range(len(segs)), key=lambda i: (len(segs[i]["strong_fragment_ids"]), segs[i]["visible_s"]))
    new_rows = []
    for i, seg in enumerate(segs):
        carries = carry_to == i
        row = VideoTracklet(
            video_match_id=match.id,
            kind="chain",
            pipeline_key=_clamp_pipeline_key(f"{t.pipeline_key}|{seg['key']}@{int(at_s)}"),
            team_cluster=t.team_cluster,
            suggested_number=seg["suggested_number"],
            suggested_role=t.suggested_role,
            confidence="low",  # a split piece is never auto-bound — it needs human review
            contaminated=seg["number_agreement"] < NUMBER_AGREEMENT_MIN,
            first_s=seg["first_s"],
            last_s=seg["last_s"],
            visible_s=seg["visible_s"],
            roster_entry_id=t.roster_entry_id if carries else None,
            tag_source="human" if carries else None,
            evidence={
                "member_fragment_ids": seg["member_fragment_ids"],
                "strong_fragment_ids": seg["strong_fragment_ids"],
                "number_agreement": seg["number_agreement"],
                "modal_shirt_color": ev.get("modal_shirt_color"),
                "votes": {str(fid): votes_by_member.get(fid) for fid in seg["member_fragment_ids"]},
                "split_from": t.pipeline_key,
                "split_at_s": at_s,
            },
            reviewed_at=now,
            reviewer_email=reviewer,
            review_action="split",
        )
        db.session.add(row)
        new_rows.append(row)
    # Tombstone the original (NOT delete) under its own pipeline_key, so a pipeline
    # re-run finds it in `prior` and skips rebuilding the chain → no duplicate /
    # double-count. Hidden from the review list by its kind.
    t.kind = "tombstone"  # String(10): keep short
    t.dismissed = True
    t.roster_entry_id = None
    t.tag_source = None
    t.review_action = "split"
    t.reviewed_at = now
    t.reviewer_email = reviewer
    t.evidence = {**ev, "split_into": [r.pipeline_key for r in new_rows], "split_at_s": at_s}
    # a split invalidates the finalized per-player reports — force a re-finalize
    if match.status == "finalized":
        match.status = "needs_tagging"
    db.session.commit()
    return jsonify({"segments": [r.to_dict() for r in new_rows], "match_status": match.status}), 201


@video_bp.route("/admin/video/matches/<int:match_id>/feedback-export", methods=["GET"])
@require_api_key
def feedback_export(match_id: int):
    """Per-crop labelled NDJSON from human-reviewed tracklets (our-side only by default).
    Each row pairs the human truth with the model's original prediction — one artifact for
    fine-tuning, vote-threshold recalibration, and auto-tag precision/recall."""
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    if match.status != "finalized":
        return _bad_request("finalize the match before exporting feedback")
    side = request.args.get("side", "ours")
    tracklets = list(db.session.query(VideoTracklet).filter(VideoTracklet.video_match_id == match.id))
    roster_by_id = {r.id: r for r in match.roster_entries}
    art = video_dev_artifacts.local_artifacts(match)

    def crops_for(t):
        if art:
            return video_dev_artifacts.tracklet_crops(t, art)
        return [{"file": p, "t": 0, "frame": 0, "laplacian_var": 0} for p in (t.thumbnail_paths or [])]

    rows = list(
        build_feedback_labels(
            match=match, tracklets=tracklets, roster_by_id=roster_by_id, crops_for_tracklet=crops_for, side=side
        )
    )
    body = "".join(json.dumps(r) + "\n" for r in rows)
    return Response(
        body,
        mimetype="application/x-ndjson",
        headers={
            "Content-Disposition": f'attachment; filename="match-{match_id}-feedback.ndjson"',
            "X-Feedback-Rows": str(len(rows)),
        },
    )


# ---------------------------------------------------------------------------
# Learning loop — measure the model against human truth, recalibrate, retrain
# ---------------------------------------------------------------------------


@video_bp.route("/admin/video/matches/<int:match_id>/accuracy", methods=["GET"])
@require_api_key
def model_accuracy(match_id: int):
    """How the model did on THIS match vs the human's corrections, plus
    threshold-tuning signals (the recalibration half of the learning loop)."""
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    tracklets = list(db.session.query(VideoTracklet).filter(VideoTracklet.video_match_id == match.id))
    roster_by_id = {r.id: r for r in match.roster_entries}
    return jsonify(
        {
            "accuracy": match_accuracy(tracklets, roster_by_id, match.our_team_cluster),
            "recalibration": recalibration_signals(tracklets),
        }
    )


@video_bp.route("/admin/video/matches/<int:match_id>/training-manifest", methods=["GET"])
@require_api_key
def training_manifest_route(match_id: int):
    """Supervised fine-tune manifest from confirmed crops — the retrain half of the
    loop (reader: crop→number; ReID: identity→crops). Consent-gated, our-side only."""
    match = _get_match_or_404(match_id)
    if match is None:
        return jsonify({"error": "match not found"}), 404
    if match.status != "finalized":
        return _bad_request("finalize the match before building a training manifest")
    tracklets = list(db.session.query(VideoTracklet).filter(VideoTracklet.video_match_id == match.id))
    roster_by_id = {r.id: r for r in match.roster_entries}
    art = video_dev_artifacts.local_artifacts(match)

    def crops_for(t):
        if art:
            return video_dev_artifacts.tracklet_crops(t, art)
        return [{"file": p, "t": 0, "frame": 0, "laplacian_var": 0} for p in (t.thumbnail_paths or [])]

    rows = list(
        build_feedback_labels(
            match=match, tracklets=tracklets, roster_by_id=roster_by_id, crops_for_tracklet=crops_for, side="ours"
        )
    )
    return jsonify(training_manifest(rows))


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------


@video_bp.route("/admin/video/reap-stale-jobs", methods=["POST"])
@require_api_key
def reap_stale():
    return jsonify({"stale_failed": video_queue.reap_stale_jobs()})
