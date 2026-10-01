"""Highlight APIs. Public bytes are proxied; no raw match/storage capabilities leave this blueprint."""

import json
import re

from flask import Blueprint, abort, g, jsonify, request
from src.auth import require_user_auth
from src.extensions import limiter
from src.models.funding import ClubProgram
from src.models.highlights import HighlightFootageReview, PlayerHighlight, now
from src.models.league import db
from src.models.video import VideoMatch
from src.services import highlights as service
from src.services.admin_audit import record_admin_event
from src.services.club_access import match_bytes_in_scope, require_club_permission, scoped_recording_intact

highlights_bp = Blueprint("highlights", __name__)


@highlights_bp.before_request
def rollout_gate():
    if not service.enabled():
        abort(404)


@highlights_bp.after_request
def private_cache(response):
    response.headers["Cache-Control"] = "private, no-store, max-age=0"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def payload():
    raw = request.stream.read(4097)
    if len(raw) > 4096:
        abort(413)
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        abort(400)
    if not isinstance(data, dict):
        abort(400)
    return data


def club_match(program_id, match_id):
    match = VideoMatch.query.filter_by(id=match_id, club_program_id=program_id).first()
    if not match or not match_bytes_in_scope(match) or not scoped_recording_intact(match):
        abort(404)
    return match


def locked_row(highlight_id, user_id=None):
    row = db.session.get(PlayerHighlight, highlight_id)
    if not row or (user_id is not None and row.recipient_user_id != user_id):
        abort(404)
    if row.video_match_id:
        db.session.query(VideoMatch).filter_by(id=row.video_match_id).with_for_update().first()
    return PlayerHighlight.query.filter_by(id=highlight_id).populate_existing().with_for_update().one()


def result_error(exc):
    db.session.rollback()
    code = str(exc)
    return jsonify(error=code), 409 if code in {
        "version_conflict",
        "pick_removed_choose_new_window",
        "highlight_limit_reached",
    } else 422


@highlights_bp.get("/highlights/features")
@service.gated
def features():
    return jsonify(highlights=True)


@highlights_bp.post("/club/<int:program_id>/matches/<int:match_id>/highlight-review")
@service.gated
@require_club_permission("matches.upload")
def review_recording(program_id, match_id):
    match = club_match(program_id, match_id)
    if not g.club_access.whole_club:
        abort(403)
    data = payload()
    classification = data.get("classification")
    if classification not in {"adult_only", "private"}:
        return jsonify(error="invalid_classification"), 400
    if classification == "adult_only" and data.get("all_visible_people_adults") is not True:
        return jsonify(error="whole_recording_review_required"), 422
    db.session.refresh(match, with_for_update=True)
    row = db.session.get(HighlightFootageReview, match.id)
    if row is None:
        row = HighlightFootageReview(video_match_id=match.id)
        db.session.add(row)
    # A changed review is a new source version. Never resurrect old player consent.
    if (
        row.classification != classification
        or row.source_etag != match.blob_etag
        or row.source_snapshot != match.scoped_snapshot
    ):
        for highlight in PlayerHighlight.query.filter_by(video_match_id=match.id).with_for_update():
            service.revoke(highlight, g.user_id, "review_changed")
    row.classification = classification
    row.source_etag = match.blob_etag
    row.source_snapshot = match.scoped_snapshot
    row.reviewer_user_id = g.user_id
    # Idempotent same-source reviews preserve the frozen fingerprint.
    if not row.reviewed_at or db.session.is_modified(row):
        row.reviewed_at = now()
    record_admin_event(
        g.user,
        "highlight_recording_review",
        "video_match",
        match.id,
        "All visible people reviewed" if classification == "adult_only" else "Recording kept private",
        meta={"program_id": program_id, "adult_only": classification == "adult_only"},
    )
    db.session.commit()
    return jsonify(classification=classification)


@highlights_bp.route("/club/<int:program_id>/matches/<int:match_id>/highlights", methods=["GET", "POST"])
@service.gated
@require_club_permission(("matches.view", "matches.upload"))
@limiter.limit("60/minute")
def club_highlights(program_id, match_id):
    match = club_match(program_id, match_id)
    if request.method == "POST":
        try:
            row, created = service.pick(match, payload(), g.user)
            db.session.commit()
            return jsonify(service.dto(row, private=True)), 201 if created else 200
        except ValueError as exc:
            return result_error(exc)
    rows = (
        PlayerHighlight.query.filter_by(program_id=program_id, video_match_id=match_id)
        .order_by(PlayerHighlight.created_at)
        .all()
    )
    return jsonify(
        highlights=[service.dto(row, private=True) for row in rows],
        adult_recording=service.adult_recording(match),
        can_review=g.club_access.whole_club,
        candidates=service.candidates(match),
    )


@highlights_bp.delete("/club/<int:program_id>/matches/<int:match_id>/highlights/<highlight_id>")
@service.gated
@require_club_permission("matches.upload")
def remove_pick(program_id, match_id, highlight_id):
    club_match(program_id, match_id)
    row = locked_row(highlight_id)
    if row.program_id != program_id or row.video_match_id != match_id:
        abort(404)
    service.revoke(row, g.user_id, "club_remove")
    record_admin_event(g.user, "highlight_remove", "player_highlight", row.id, "Club withdrew its publication key")
    db.session.commit()
    return jsonify(service.dto(row, private=True))


@highlights_bp.get("/me/highlight-requests")
@service.gated
@require_user_auth
def inbox():
    try:
        page = int(request.args.get("page", "1"))
        if not 1 <= page <= 100:
            raise ValueError()
    except ValueError:
        return jsonify(error="invalid_page"), 400
    rows = (
        PlayerHighlight.query.filter_by(recipient_user_id=g.user_id)
        .order_by(PlayerHighlight.created_at.desc(), PlayerHighlight.id)
        .offset((page - 1) * 30)
        .limit(31)
        .all()
    )
    return jsonify(highlights=[service.dto(row, private=True) for row in rows[:30]], page=page, has_more=len(rows) > 30)


@highlights_bp.post("/me/highlight-requests/<highlight_id>/decision")
@service.gated
@require_user_auth
def decision(highlight_id):
    row = locked_row(highlight_id, g.user_id)
    data = payload()
    try:
        service.decide(row, g.user, data.get("decision"), data.get("version"))
        db.session.commit()
        return jsonify(service.dto(row, private=True))
    except ValueError as exc:
        return result_error(exc)


@highlights_bp.post("/me/highlight-requests/<highlight_id>/revoke")
@service.gated
@require_user_auth
def revoke(highlight_id):
    row = locked_row(highlight_id, g.user_id)
    service.revoke(row, g.user_id, "player_revoke")
    db.session.commit()
    return jsonify(service.dto(row, private=True))


@highlights_bp.post("/me/highlight-requests/<highlight_id>/retry")
@service.gated
@require_user_auth
def retry(highlight_id):
    row = locked_row(highlight_id, g.user_id)
    if not service.eligible(row) or row.render_status != "failed":
        return jsonify(error="retry_unavailable"), 409
    service.queue_cut(row)
    db.session.commit()
    return jsonify(service.dto(row, private=True)), 202


@highlights_bp.get("/players/<int(signed=True):player_id>/highlights")
@service.gated
@limiter.limit("60/minute")
def player_highlights(player_id):
    if not service.is_public_adult(player_id):
        abort(404)
    return public_list(
        PlayerHighlight.query.filter(
            PlayerHighlight.player_api_id == player_id
            if player_id > 0
            else PlayerHighlight.local_player_id == -player_id
        )
    )


@highlights_bp.get("/programs/<slug>/highlights")
@service.gated
@limiter.limit("60/minute")
def program_highlights(slug):
    program = ClubProgram.query.filter_by(slug=slug).first()
    if not program or not service.is_listed(program):
        abort(404)
    return public_list(PlayerHighlight.query.filter_by(program_id=program.id))


def public_list(query):
    rows = (
        query.filter(
            PlayerHighlight.revoked_at.is_(None),
            PlayerHighlight.player_decision == "approve",
            PlayerHighlight.render_status == "ready",
        )
        .order_by(PlayerHighlight.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify(highlights=[service.dto(row) for row in rows if service.public(row)])


def clip_response(row):
    from flask import Response
    from src.services.highlights_storage import read_output

    # Only our generated path can be read, even if a DB field is corrupted.
    if not row.output_blob_path or not re.fullmatch(
        r"highlights/[a-f0-9-]{36}/[a-f0-9-]{36}\.mp4", row.output_blob_path
    ):
        abort(404)
    if not row.output_blob_path.startswith(f"highlights/{row.id}/"):
        abort(404)
    size = row.output_bytes or 0
    if not 0 < size <= 30 * 1024 * 1024:
        abort(404)
    start, end = 0, size - 1
    partial = False
    range_header = request.headers.get("Range")
    if range_header:
        m = re.fullmatch(r"bytes=(\d*)-(\d*)", range_header)
        if not m or not any(m.groups()):
            return Response(status=416, headers={"Content-Range": f"bytes */{size}"})
        if m[1]:
            start = int(m[1])
            end = min(int(m[2]) if m[2] else size - 1, size - 1)
        else:
            start = max(0, size - int(m[2]))
        if not 0 <= start <= end < size:
            return Response(status=416, headers={"Content-Range": f"bytes */{size}"})
        partial = True
    if request.method == "HEAD":
        body = b""
    else:
        try:
            body = read_output(row.output_blob_path, row.output_etag, start, end - start + 1)
        except Exception:
            abort(404)
    response = Response(body, status=206 if partial else 200, mimetype="video/mp4")
    response.headers.update(
        {"Accept-Ranges": "bytes", "Content-Length": str(end - start + 1), "Content-Disposition": "inline"}
    )
    if partial:
        response.headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    return response


@highlights_bp.get("/highlights/<highlight_id>/clip")
@service.gated
@limiter.limit("120/minute")
def public_clip(highlight_id):
    row = db.session.get(PlayerHighlight, highlight_id)
    if not row or not service.public(row):
        abort(404)
    return clip_response(row)


@highlights_bp.get("/me/highlight-requests/<highlight_id>/preview")
@service.gated
@require_user_auth
def preview(highlight_id):
    row = db.session.get(PlayerHighlight, highlight_id)
    if (
        not row
        or row.recipient_user_id != g.user_id
        or not service.eligible(row)
        or row.render_status != "ready"
        or row.render_source_version != row.source_version
    ):
        abort(404)
    return clip_response(row)


@highlights_bp.get("/club/<int:program_id>/matches/<int:match_id>/highlights/<highlight_id>/preview")
@service.gated
@require_club_permission("matches.view")
def club_preview(program_id, match_id, highlight_id):
    club_match(program_id, match_id)
    row = db.session.get(PlayerHighlight, highlight_id)
    if (
        not row
        or row.program_id != program_id
        or row.video_match_id != match_id
        or not service.eligible(row)
        or row.render_status != "ready"
        or row.render_source_version != row.source_version
    ):
        abort(404)
    return clip_response(row)
