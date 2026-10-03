"""Dark C4 endpoints, never granting scouts any applicant/roster capability."""

import json
import re
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request
from flask.globals import request_ctx
from sqlalchemy.exc import IntegrityError
from src.auth import require_user_auth
from src.extensions import limiter
from src.models.league import db
from src.models.opportunities import now
from src.models.scout_attendance import ScoutAttendance
from src.services import scout_attendance as service
from src.services.club_access import require_club_permission
from src.services.club_directory import directory_enabled
from src.services.club_today import summary
from src.services.opportunity_distance import search
from werkzeug.routing import Map

scout_attendance_bp = Blueprint("scout_attendance", __name__)


@scout_attendance_bp.record_once
def install(state):
    @state.app.before_request
    def dark():
        paths = (
            r"/api/scout-attendance/features",
            r"/api/opportunities/search",
            r"/api/opportunities/[^/]+/attendance",
            r"/api/me/scout-attendance(?:/[^/]+/withdraw)?",
            r"/api/club/\d+/(?:today|attendance/[^/]+/decision)",
        )
        if not service.enabled() and any(re.fullmatch(p, request.path) for p in paths):
            # Re-route through the real SPA/error handlers with the C4 rules absent.
            rules = tuple(current_app.url_map.iter_rules())
            cached = current_app.extensions.get("c4_dark_map")
            if cached is None or cached[0] != rules:
                visible = []
                for original in rules:
                    if original.endpoint.startswith("scout_attendance."):
                        continue
                    copied = original.empty()
                    copied.methods = original.methods
                    copied.provide_automatic_options = getattr(original, "provide_automatic_options", False)
                    visible.append(copied)
                original_map = current_app.url_map
                routing = Map(
                    visible,
                    converters=original_map.converters,
                    strict_slashes=original_map.strict_slashes,
                    merge_slashes=original_map.merge_slashes,
                    redirect_defaults=original_map.redirect_defaults,
                    host_matching=original_map.host_matching,
                    default_subdomain=original_map.default_subdomain,
                )
                current_app.extensions["c4_dark_map"] = (rules, routing)
            else:
                routing = cached[1]
            request_ctx.url_adapter = routing.bind_to_environ(request.environ)
            request.routing_exception = None
            request.url_rule = None
            request.view_args = None
            request_ctx.match_request()

    @state.app.after_request
    def private(response):
        if service.enabled() and request.endpoint and request.endpoint.startswith("scout_attendance."):
            response.headers["Cache-Control"] = "no-store"
        return response


def key():
    return f"c4:{getattr(g, 'user_id', None) or request.remote_addr}"


def guarded(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except service.Error as exc:
            db.session.rollback()
            return jsonify(error=exc.code), exc.status
        except IntegrityError:
            db.session.rollback()
            return jsonify(error="request_conflict"), 409

    return wrapped


def payload():
    if (request.content_length or 0) > 4096:
        raise service.Error("payload_too_large", 413)
    raw = request.stream.read(4097)
    if len(raw) > 4096:
        raise service.Error("payload_too_large", 413)
    try:
        data = json.loads(raw) if request.is_json else None
    except (ValueError, UnicodeDecodeError, RecursionError):
        data = None
    if not isinstance(data, dict):
        raise service.Error("invalid_payload", 400)
    return data


@scout_attendance_bp.get("/scout-attendance/features")
@limiter.limit("60/minute", exempt_when=lambda: not service.enabled())
def features():
    return jsonify(scout_attend=True)


@scout_attendance_bp.post("/opportunities/search")
@guarded
@limiter.limit("60/minute", exempt_when=lambda: not service.enabled())
def distance_search():
    if not service.opportunity_service.enabled("OPPORTUNITIES_ENABLED") or not directory_enabled():
        return jsonify(error="Not found"), 404
    try:
        return jsonify(search(payload()))
    except ValueError as exc:
        if isinstance(exc, service.Error):
            raise
        return jsonify(error=str(exc)), 400


@scout_attendance_bp.post("/opportunities/<uuid:opportunity_id>/attendance")
@guarded
@require_user_auth
@limiter.limit("10/hour;30/day", key_func=key, exempt_when=lambda: not service.enabled())
def submit(opportunity_id):
    row, created = service.submit(str(opportunity_id), g.user_id, payload())
    result = service.serialize(row)
    db.session.commit()
    return jsonify(attendance=result), 201 if created else 200


@scout_attendance_bp.get("/me/scout-attendance")
@guarded
@require_user_auth
@limiter.limit("60/minute", key_func=key, exempt_when=lambda: not service.enabled())
def mine():
    service.verified(g.user_id)
    service.expire_pending(user_id=g.user_id)
    db.session.commit()
    # Cursor paging scans one bounded page; unavailable events are omitted, not replaced by stale data.
    after = request.args.get("after")
    if after and (len(after) != 36 or not re.fullmatch(r"[a-f0-9-]+", after)):
        raise service.Error("invalid_cursor", 400)
    query = ScoutAttendance.query.filter_by(scout_user_id=g.user_id).filter(
        ScoutAttendance.retention_expires_at > now()
    )
    if after:
        query = query.filter(ScoutAttendance.id > after)
    rows = query.order_by(ScoutAttendance.id).limit(31).all()
    visible = [
        r
        for r in rows[:30]
        if service.visible_event(db.session.get(service.ClubOpportunity, r.opportunity_id), history=True)
    ]
    return jsonify(
        attendance=[service.serialize(r) for r in visible], next_cursor=rows[29].id if len(rows) > 30 else None
    )


@scout_attendance_bp.post("/me/scout-attendance/<uuid:request_id>/withdraw")
@guarded
@require_user_auth
@limiter.limit("30/hour", key_func=key, exempt_when=lambda: not service.enabled())
def withdraw(request_id):
    row = service.withdraw(str(request_id), g.user_id, payload())
    result = service.serialize(row)
    db.session.commit()
    return jsonify(attendance=result)


@scout_attendance_bp.post("/club/<int:program_id>/attendance/<uuid:request_id>/decision")
@guarded
@require_club_permission("contact")
@limiter.limit("60/hour", key_func=key, exempt_when=lambda: not service.enabled())
def decision(program_id, request_id):
    data = payload()
    service.expire_pending(program_id=program_id)
    service.revoke_ineligible(program_id=program_id)
    db.session.commit()
    row = service.decide(str(request_id), program_id, g.user_id, data)
    result = service.serialize(row, club=True)
    db.session.commit()
    return jsonify(attendance=result)


@scout_attendance_bp.get("/club/<int:program_id>/today")
@guarded
@require_club_permission("players.view")
@limiter.limit("60/minute", key_func=key, exempt_when=lambda: not service.enabled())
def today(program_id):
    after = request.args.get("accepted_after")
    if after and (len(after) != 36 or not re.fullmatch(r"[a-f0-9-]+", after)):
        raise service.Error("invalid_cursor", 400)
    return jsonify(summary(program_id, accepted_after=after))
