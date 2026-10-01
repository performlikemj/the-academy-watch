"""Highlight APIs. Standalone clip grants expire after 60s; raw match capabilities never leave this blueprint."""

import json
import re
from datetime import UTC, timedelta
from functools import wraps

from flask import Blueprint, abort, current_app, g, jsonify, request
from sqlalchemy.exc import DBAPIError
from src.auth import require_api_key, require_user_auth
from src.extensions import limiter
from src.models.funding import ClubProgram, ClubProgramClaim, ClubProgramManager
from src.models.highlights import HighlightFootageReview, HighlightTakedown, PlayerHighlight, now
from src.models.league import db
from src.models.video import VideoMatch
from src.services import highlights as service
from src.services.admin_audit import record_admin_event
from src.services.club_access import ROLE_CAPABILITIES, ClubAccess, match_bytes_in_scope, scoped_recording_intact

highlights_bp = Blueprint("highlights", __name__)


@highlights_bp.before_app_request
def hide_dark_routes():
    if service.enabled():
        # A test/CLI may reuse an app context across HTTP requests. Evidence is
        # still scoped to this request, including the final grant recheck.
        service.clear_read_evidence()
        return
    # The real application has a SPA fallback and automatic OPTIONS. Re-match
    # with this blueprint absent, including wrong-method requests.
    from flask.globals import request_ctx
    from werkzeug.exceptions import MethodNotAllowed, NotFound
    from werkzeug.routing import Map, RequestRedirect

    adapter = current_app.url_map.bind_to_environ(request.environ)
    try:
        rule, _ = adapter.match(method=request.method, return_rule=True)
    except MethodNotAllowed as error:
        for method in error.valid_methods:
            rule, _ = adapter.match(method=method, return_rule=True)
            if rule.endpoint.startswith("highlights."):
                break
        else:
            return
    except (NotFound, RequestRedirect):
        return
    if not rule.endpoint.startswith("highlights."):
        return

    original = current_app.url_map
    rules = tuple(original.iter_rules())
    cached = current_app.extensions.get("highlights_dark_map")
    if cached is None or cached[0] != rules:
        visible = []
        for rule in rules:
            if rule.endpoint.startswith("highlights."):
                continue
            copy = rule.empty()
            copy.methods = rule.methods
            copy.provide_automatic_options = getattr(rule, "provide_automatic_options", False)
            visible.append(copy)
        mapped = Map(
            visible,
            converters=original.converters,
            strict_slashes=original.strict_slashes,
            merge_slashes=original.merge_slashes,
            redirect_defaults=original.redirect_defaults,
            host_matching=original.host_matching,
            default_subdomain=original.default_subdomain,
        )
        current_app.extensions["highlights_dark_map"] = (rules, mapped)
    else:
        mapped = cached[1]
    request_ctx.url_adapter = mapped.bind_to_environ(request.environ)
    request.routing_exception = None
    request.url_rule = None
    request.view_args = None
    request_ctx.match_request()


@highlights_bp.errorhandler(DBAPIError)
def transaction_conflict(exc):
    db.session.rollback()
    if getattr(exc.orig, "sqlstate", None) in {"40P01", "40001"}:
        return jsonify(error="version_conflict"), 409
    raise exc


def valid_id(value):
    if not re.fullmatch(r"[a-f0-9]{8}-(?:[a-f0-9]{4}-){3}[a-f0-9]{12}", value):
        abort(400)


def require_club_key(view):
    """C2 safe default: only A2 claim-verified, active club managers hold this key.

    C2 requires the Phase 2 schema; use A2's strict relational predicate without
    repeated schema introspection or loading invite-only grants.
    """

    @wraps(view)
    def checked(program_id, *args, **kwargs):
        manager = (
            db.session.query(ClubProgramManager.id)
            .join(ClubProgram, ClubProgram.id == ClubProgramManager.program_id)
            .join(
                ClubProgramClaim,
                (ClubProgramClaim.id == ClubProgramManager.source_claim_id)
                & (ClubProgramClaim.program_id == ClubProgramManager.program_id)
                & (ClubProgramClaim.user_account_id == ClubProgramManager.user_account_id),
            )
            .filter(
                ClubProgramManager.program_id == program_id,
                ClubProgramManager.user_account_id == g.user_id,
                ClubProgramManager.status == "active",
                ClubProgramClaim.status == "approved",
                ClubProgram.platform_status == "approved",
                ClubProgram.emergency_hidden.is_(False),
            )
            .first()
        )
        if manager is None:
            abort(403)
        g.club_access = ClubAccess(
            program_id=program_id,
            user_id=g.user_id,
            role="manager",
            verified=True,
            capabilities=ROLE_CAPABILITIES["manager"],
        )
        return view(program_id, *args, **kwargs)

    return require_user_auth(checked)


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


def club_match(program_id, match_id, *, source_required=True):
    match = VideoMatch.query.filter_by(id=match_id, club_program_id=program_id).first()
    if not match or not match_bytes_in_scope(match) or (source_required and not scoped_recording_intact(match)):
        abort(404)
    return match


def locked_row(highlight_id, user_id=None):
    valid_id(highlight_id)
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
@require_club_key
@limiter.limit("10/hour")
def review_recording(program_id, match_id):
    data = payload()
    classification = data.get("classification")
    match = club_match(program_id, match_id, source_required=classification != "private")
    if not g.club_access.whole_club:
        abort(403)
    if classification not in {"adult_only", "private"}:
        return jsonify(error="invalid_classification"), 400
    if classification == "adult_only" and data.get("all_visible_people_adults") is not True:
        return jsonify(error="whole_recording_review_required"), 422
    db.session.refresh(match, with_for_update=True)
    row = db.session.get(HighlightFootageReview, match.id)
    new_review = row is None
    if new_review:
        row = HighlightFootageReview(video_match_id=match.id)
    attested = data.get("squad_adult_attested") is True
    same_source = (
        row.classification == classification
        and row.source_etag == match.blob_etag
        and row.source_snapshot == match.scoped_snapshot
        and row.squad_adult_attested == attested
    )
    if classification == "adult_only":
        reason = service.recording_date_error(match)
        if reason:
            return jsonify(error=reason), 422
        squad = db.session.get(service.ClubSquad, match.squad_id) if match.squad_id else None
        if service.squad_classification(squad) == "youth":
            return jsonify(error="youth_recording_private"), 422
        if service.squad_classification(squad) == "unknown" and not attested:
            return jsonify(error="senior_squad_attestation_required"), 422
    if same_source:
        return jsonify(classification=classification)
    for highlight in (
        PlayerHighlight.query.filter_by(video_match_id=match.id).order_by(PlayerHighlight.id).with_for_update()
    ):
        service.revoke(highlight, g.user_id, "review_changed")
    row.classification = classification
    # Private withdrawal must work after the original recording is gone.
    row.source_etag = match.blob_etag or row.source_etag or "withdrawn"
    row.source_snapshot = match.scoped_snapshot or row.source_snapshot or "withdrawn"
    row.reviewer_user_id = g.user_id
    row.squad_adult_attested = attested
    row.reviewed_at = now()
    if new_review:
        db.session.add(row)
    record_admin_event(
        g.user,
        "highlight_recording_review",
        "video_match",
        match.id,
        "All visible people reviewed" if classification == "adult_only" else "Recording kept private",
        meta={"program_id": program_id, "adult_only": classification == "adult_only", "squad_adult_attested": attested},
    )
    db.session.commit()
    return jsonify(classification=classification)


@highlights_bp.route("/club/<int:program_id>/matches/<int:match_id>/highlights", methods=["GET", "POST"])
@service.gated
@require_club_key
@limiter.limit("60/minute")
def club_highlights(program_id, match_id):
    match = club_match(program_id, match_id, source_required=request.method == "POST")
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
    service.prepare_reads(rows, matches=[match], candidates=True)
    intact = scoped_recording_intact(match)
    reason = service.recording_block_reason(match)
    return jsonify(
        highlights=[service.dto(row, private=True) for row in rows],
        adult_recording=service.adult_recording(match),
        can_review=g.club_access.whole_club
        and intact
        and reason in {None, "review_required", "senior_squad_attestation_required"},
        review_classification=service.lookup(HighlightFootageReview, match.id).classification
        if service.lookup(HighlightFootageReview, match.id)
        else "private",
        recording_block_reason=reason if intact else "source_unavailable",
        unknown_squad=service.squad_classification(service.lookup(service.ClubSquad, match.squad_id)) == "unknown",
        candidates=service.candidates(match) if intact else [],
    )


@highlights_bp.delete("/club/<int:program_id>/matches/<int:match_id>/highlights/<highlight_id>")
@service.gated
@require_club_key
def remove_pick(program_id, match_id, highlight_id):
    club_match(program_id, match_id, source_required=False)
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
    service.prepare_reads(rows[:30])
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
@limiter.limit("5/hour")
def retry(highlight_id):
    row = locked_row(highlight_id, g.user_id)
    if not service.eligible(row) or row.render_status not in {"failed", "stale"}:
        return jsonify(error="retry_unavailable"), 409
    row.player_decision = "pending"
    row.decision_user_id = None
    row.approved_source_version = None
    row.version += 1
    service.event(row, g.user_id, "preview_retry")
    service.queue_cut(row)
    db.session.commit()
    return jsonify(service.dto(row, private=True)), 202


@highlights_bp.get("/players/<int(signed=True):player_id>/highlights")
@service.gated
@limiter.limit("60/minute")
def player_highlights(player_id):
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
    if not program:
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
    service.prepare_reads(rows)
    return jsonify(highlights=[service.dto(row) for row in rows if service.public(row)])


def clip_response(row, *, expires_at, audience, program_id=None, match_id=None):
    from flask import redirect
    from src.services.highlights_storage import output_read_url

    if (
        not row.output_blob_path
        or not re.fullmatch(r"highlights/[a-f0-9-]{36}/[a-f0-9-]{36}\.mp4", row.output_blob_path)
        or not row.output_blob_path.startswith(f"highlights/{row.id}/")
    ):
        abort(404)
    if not row.output_etag or not 0 < (row.output_bytes or 0) <= 30 * 1024 * 1024:
        abort(404)
    hid, version, source_version, path, etag = (
        row.id,
        row.version,
        row.source_version,
        row.output_blob_path,
        row.output_etag,
    )
    actor_id = getattr(g, "user_id", None)
    actor_epoch = getattr(getattr(g, "user", None), "auth_epoch", None)
    try:
        url = output_read_url(row.output_blob_path, row.output_etag, expires_at=expires_at)
    except Exception:
        abort(404)
    # End the pre-storage read transaction and discard every ORM/request cache.
    # A READ COMMITTED re-read must see revocation committed during storage I/O.
    db.session.rollback()
    service.clear_read_evidence()
    row = db.session.get(PlayerHighlight, hid)
    if (
        not row
        or now().replace(tzinfo=UTC) >= expires_at
        or (row.version, row.source_version, row.output_blob_path, row.output_etag)
        != (version, source_version, path, etag)
    ):
        abort(404)
    service.prepare_reads([row])
    if audience == "public":
        allowed = service.public(row)
    else:
        from src.models.league import UserAccount

        actor = db.session.get(UserAccount, actor_id, populate_existing=True)
        if not actor or not service.account_can_act(actor) or actor.auth_epoch != actor_epoch:
            abort(404)
        allowed = service.eligible(row) and service.preview_ready(row)
        if audience == "player":
            allowed = allowed and row.recipient_user_id == actor_id
        else:
            allowed = allowed and row.program_id == program_id and row.video_match_id == match_id
            manager = (
                db.session.query(ClubProgramManager.id)
                .join(ClubProgramClaim, ClubProgramClaim.id == ClubProgramManager.source_claim_id)
                .filter(
                    ClubProgramManager.program_id == program_id,
                    ClubProgramManager.user_account_id == actor_id,
                    ClubProgramManager.status == "active",
                    ClubProgramClaim.status == "approved",
                    ClubProgramClaim.program_id == program_id,
                    ClubProgramClaim.user_account_id == actor_id,
                )
                .first()
            )
            allowed = allowed and bool(manager)
    if not allowed:
        abort(404)
    # Web preview requests ask for a URL then use native video transport. Other
    # clients retain the redirect contract; no authenticated fetch reaches storage.
    response = (
        jsonify(url=url) if audience != "public" and request.args.get("transport") == "url" else redirect(url, code=302)
    )
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@highlights_bp.post("/admin/highlights/<highlight_id>/takedown")
@service.gated
@require_api_key
@require_user_auth
def admin_takedown(highlight_id):
    row = locked_row(highlight_id)
    row.admin_taken_down = True
    if row.video_match_id:
        hold = db.session.get(HighlightTakedown, row.id)
        if hold is None:
            db.session.add(
                HighlightTakedown(id=row.id, video_match_id=row.video_match_id, start_s=row.start_s, end_s=row.end_s)
            )
        else:
            hold.lifted_at = None
    service.revoke(row, g.user_id, "admin_takedown")
    if row.video_match_id:
        for sibling in (
            PlayerHighlight.query.filter_by(video_match_id=row.video_match_id, start_s=row.start_s, end_s=row.end_s)
            .order_by(PlayerHighlight.id)
            .with_for_update()
        ):
            if sibling.id != row.id:
                service.revoke(sibling, g.user_id, "admin_window_hold")
    record_admin_event(g.user, "highlight_takedown", "player_highlight", row.id, "Admin withdrew clip publication")
    db.session.commit()
    return jsonify(id=row.id, revoked=True)


@highlights_bp.post("/admin/highlights/<highlight_id>/lift")
@service.gated
@require_api_key
@require_user_auth
def admin_lift(highlight_id):
    valid_id(highlight_id)
    hold = db.session.get(HighlightTakedown, highlight_id)
    row = db.session.get(PlayerHighlight, highlight_id)
    mid = hold.video_match_id if hold else row.video_match_id if row else None
    if not hold and not row:
        abort(404)
    if mid:
        VideoMatch.query.filter_by(id=mid).with_for_update().first()
    if hold:
        hold = HighlightTakedown.query.filter_by(id=highlight_id).populate_existing().with_for_update().one()
        hold.lifted_at = now()
    if row:
        row = PlayerHighlight.query.filter_by(id=highlight_id).populate_existing().with_for_update().one()
        row.admin_taken_down = False
        if row.revoke_reason == "admin_takedown":
            row.revoke_reason = "admin_lift"
        service.event(row, g.user_id, "admin_lift")
    record_admin_event(
        g.user, "highlight_takedown_lift", "player_highlight", highlight_id, "Admin lifted clip takedown"
    )
    db.session.commit()
    return jsonify(id=highlight_id, revoked=True)


@highlights_bp.get("/highlights/<highlight_id>/clip")
@service.gated
@limiter.limit("120/minute")
def public_clip(highlight_id):
    valid_id(highlight_id)
    expires_at = now().replace(tzinfo=UTC) + timedelta(seconds=60)
    row = db.session.get(PlayerHighlight, highlight_id)
    service.prepare_reads([row] if row else [])
    if not row or not service.public(row):
        abort(404)
    return clip_response(row, expires_at=expires_at, audience="public")


@highlights_bp.get("/me/highlight-requests/<highlight_id>/preview")
@service.gated
@require_user_auth
def preview(highlight_id):
    valid_id(highlight_id)
    expires_at = now().replace(tzinfo=UTC) + timedelta(seconds=60)
    row = db.session.get(PlayerHighlight, highlight_id)
    service.prepare_reads([row] if row else [])
    if (
        not row
        or row.recipient_user_id != g.user_id
        or not service.eligible(row)
        or row.render_status != "ready"
        or row.render_source_version != row.source_version
    ):
        abort(404)
    return clip_response(row, expires_at=expires_at, audience="player")


@highlights_bp.get("/club/<int:program_id>/matches/<int:match_id>/highlights/<highlight_id>/preview")
@service.gated
@require_club_key
def club_preview(program_id, match_id, highlight_id):
    valid_id(highlight_id)
    expires_at = now().replace(tzinfo=UTC) + timedelta(seconds=60)
    club_match(program_id, match_id)
    row = db.session.get(PlayerHighlight, highlight_id)
    service.prepare_reads([row] if row else [])
    if (
        not row
        or row.program_id != program_id
        or row.video_match_id != match_id
        or not service.eligible(row)
        or row.render_status != "ready"
        or row.render_source_version != row.source_version
    ):
        abort(404)
    return clip_response(row, expires_at=expires_at, audience="club", program_id=program_id, match_id=match_id)
