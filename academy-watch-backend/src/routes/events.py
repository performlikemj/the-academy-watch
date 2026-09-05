"""Product analytics endpoints for The Academy Watch.

- ``POST /api/events`` — anonymous, batched event ingestion (privacy-light:
  no cookies / IP / user-agent; identity only from a verified token if present).
- ``GET /api/admin/analytics/summary`` — admin-only aggregate rollup.
"""

import json
import logging
import math
import time
from datetime import UTC, datetime, timedelta
from functools import wraps

from flask import Blueprint, g, jsonify, make_response, request
from sqlalchemy import func, text
from sqlalchemy.exc import DBAPIError
from src.auth import _get_authorized_email, require_api_key
from src.extensions import limiter
from src.models.league import db
from src.models.product_event import ProductEvent
from src.services.public_player_subject import resolve_public_adult_subject
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

events_bp = Blueprint("events", __name__)
logger = logging.getLogger(__name__)

# Exactly these names are accepted; anything else is silently dropped so one
# bad client event never fails the rest of the batch.
ALLOWED_EVENTS = frozenset(
    {
        "pageview",
        "claim_submitted",
        "checkout_completed",
        "checkout_started",
        "follow_added",
        "shadow_minted",
        "search_performed",
        "list_created",
        "profile_view",
        "pilot_ui",
    }
)

MAX_BATCH = 25

PILOT_ACTIONS = {
    "P1": {"report_requested", "report_completed", "report_failed"},
    "P2": {"invite_created", "invite_accepted", "invite_declined", "relationship_revoked", "attestation_submitted"},
    "P3": {"feedback_published", "feedback_opened", "feedback_acknowledged", "feedback_withdrawn"},
    "P4": {"result_created", "result_corrected", "result_deleted", "result_conflict"},
}
PILOT_OUTCOMES = {"requested", "success", "error", "denied", "invalid"}

# Mirrors the community-takes submit endpoint (per-IP, in-memory storage).
RATE_LIMIT_PER_MINUTE = "10 per minute"
RATE_LIMIT_PER_HOUR = "30 per hour"

# Column length caps (match the model); overlong values are clipped, not rejected.
_MAX_SESSION_ID = 64
_MAX_PATH = 512
_MAX_REFERRER = 512

# Admin summary defaults/caps.
DEFAULT_SUMMARY_DAYS = 7
MAX_SUMMARY_DAYS = 90
TOP_PATHS_LIMIT = 10


def _clip(value, length):
    """Coerce to a stripped string clipped to `length`, or None."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return text[:length]


@events_bp.route("/events", methods=["POST"])
@limiter.limit(RATE_LIMIT_PER_MINUTE)
@limiter.limit(RATE_LIMIT_PER_HOUR)
def ingest_events():
    """Ingest a batch of product-analytics events.

    Body: ``{"events": [{name, path?, referrer?, props?, session_id?}]}``.
    Works anonymously; user_email is resolved only from a verified Bearer token.
    """
    # force=True so sendBeacon payloads (non-JSON content-type) still parse.
    data = request.get_json(silent=True, force=True) or {}
    events = data.get("events")
    if not isinstance(events, list):
        return jsonify({"error": "events must be a list"}), 400
    if len(events) > MAX_BATCH:
        return jsonify({"error": f"max {MAX_BATCH} events per batch"}), 413

    user_email = _get_authorized_email()

    accepted = 0
    for ev in events:
        if not isinstance(ev, dict):
            continue
        name = ev.get("name")
        # isinstance guard first: a non-scalar JSON name (list/dict) is unhashable
        # and would raise TypeError on the frozenset membership test, 500-ing the
        # whole batch. Drop it silently instead.
        if not isinstance(name, str) or name not in ALLOWED_EVENTS:
            continue
        props = ev.get("props")
        if name == "pilot_ui":
            if not isinstance(props, dict):
                continue
            package, action, outcome = (props.get(k) for k in ("package", "action", "outcome"))
            if (
                not all(isinstance(v, str) for v in (package, action, outcome))
                or package not in PILOT_ACTIONS
                or action not in PILOT_ACTIONS[package]
                or outcome not in PILOT_OUTCOMES
            ):
                continue
            db.session.add(
                ProductEvent(
                    event_name=name,
                    user_email=None,
                    path=None,
                    referrer=None,
                    session_id=None,
                    props={"package": package, "action": action, "outcome": outcome},
                )
            )
            accepted += 1
            continue
        if name == "profile_view":
            if not isinstance(props, dict):
                continue
            player_api_id = props.get("player_api_id")
            if isinstance(player_api_id, bool) or not isinstance(player_api_id, int) or player_api_id == 0:
                continue

            # A syntactically valid view is accepted even when the fail-closed
            # public-adult gate silently omits its persistence.
            accepted += 1
            try:
                with db.session.begin_nested():
                    subject = resolve_public_adult_subject(player_api_id)
            except Exception:
                logger.exception("Failed to resolve a profile-view subject")
                continue
            if subject is None:
                continue
            db.session.add(
                ProductEvent(
                    event_name=name,
                    user_email=None,
                    session_id=None,
                    path=None,
                    referrer=None,
                    props={"player_api_id": player_api_id},
                )
            )
            continue

        if not isinstance(props, dict):
            props = None
        db.session.add(
            ProductEvent(
                event_name=name,
                user_email=user_email,
                session_id=_clip(ev.get("session_id"), _MAX_SESSION_ID),
                path=_clip(ev.get("path"), _MAX_PATH),
                referrer=_clip(ev.get("referrer"), _MAX_REFERRER),
                props=props,
            )
        )
        accepted += 1

    if accepted:
        db.session.commit()
    return jsonify({"accepted": accepted}), 202


def _private_report(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            response = make_response(view(*args, **kwargs))
        except HTTPException as exc:
            response = exc.get_response()
        response.headers["Cache-Control"] = "private, no-store"
        return response

    return wrapped


def _pilot_rate_rejected(limit):
    response = jsonify({"error": "rate_limit_exceeded"})
    response.status_code = 429
    response.headers["Retry-After"] = str(max(1, math.ceil(limit.reset_at - time.time())))
    response.headers["Cache-Control"] = "private, no-store"
    return response


def _pilot_admin_limit_key():
    return (g.user_email or "").strip().lower()


@events_bp.route("/admin/pilot-cohort/report", methods=["POST"])
@_private_report
@require_api_key
@limiter.limit("6 per minute", key_func=_pilot_admin_limit_key, on_breach=_pilot_rate_rejected)
@limiter.limit("30 per hour", key_func=_pilot_admin_limit_key, on_breach=_pilot_rate_rejected)
def pilot_cohort_report():
    from src.services.pilot_cohort import MAX_BYTES, CohortError, build_report

    try:
        # Bound reads even for chunked requests without Content-Length.
        if request.content_length is not None and request.content_length > MAX_BYTES:
            raise CohortError("register_too_large", 413)
        raw = request.stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise CohortError("register_too_large", 413)
        try:
            data = json.loads(raw)
        except (ValueError, UnicodeDecodeError, RecursionError):
            raise CohortError() from None
        with db.session.no_autoflush:
            if db.session.get_bind().dialect.name == "postgresql":
                db.session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            report = build_report(data)
        db.session.rollback()
        return jsonify(report)
    except CohortError as exc:
        db.session.rollback()
        return jsonify({"error": exc.code}), exc.status
    except RequestEntityTooLarge:
        db.session.rollback()
        return jsonify({"error": "register_too_large"}), 413
    except DBAPIError as exc:
        db.session.rollback()
        if getattr(exc.orig, "sqlstate", None) in {"40001", "40P01"} or getattr(exc.orig, "pgcode", None) in {
            "40001",
            "40P01",
        }:
            return jsonify({"error": "retry_conflict"}), 409
        logger.error("Pilot cohort database report failed")
        return jsonify({"error": "cohort_report_failed"}), 500
    except Exception:
        db.session.rollback()
        logger.error("Pilot cohort report failed")
        return jsonify({"error": "cohort_report_failed"}), 500


@events_bp.route("/admin/analytics/summary", methods=["GET"])
@require_api_key
def analytics_summary():
    """Aggregate product-event rollup over the last N days (admin only)."""
    days = min(request.args.get("days", DEFAULT_SUMMARY_DAYS, type=int), MAX_SUMMARY_DAYS)
    if days < 1:
        days = 1
    # Naive UTC cutoff to compare against the naive timestamps stored by the DB.
    cutoff = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)

    totals_rows = (
        db.session.query(ProductEvent.event_name, func.count(ProductEvent.id))
        .filter(ProductEvent.created_at >= cutoff)
        .group_by(ProductEvent.event_name)
        .all()
    )
    totals = {name: count for name, count in totals_rows}

    day_col = func.date(ProductEvent.created_at)
    daily_rows = (
        db.session.query(day_col.label("day"), func.count(ProductEvent.id))
        .filter(ProductEvent.created_at >= cutoff)
        .group_by(day_col)
        .order_by(day_col)
        .all()
    )
    daily = [
        {"date": day.isoformat() if hasattr(day, "isoformat") else str(day), "count": count}
        for day, count in daily_rows
    ]

    top_paths_rows = (
        db.session.query(ProductEvent.path, func.count(ProductEvent.id).label("cnt"))
        .filter(
            ProductEvent.created_at >= cutoff,
            ProductEvent.event_name == "pageview",
            ProductEvent.path.isnot(None),
        )
        .group_by(ProductEvent.path)
        .order_by(func.count(ProductEvent.id).desc())
        .limit(TOP_PATHS_LIMIT)
        .all()
    )
    top_paths = [{"path": path, "count": count} for path, count in top_paths_rows]

    distinct_sessions = (
        db.session.query(func.count(func.distinct(ProductEvent.session_id)))
        .filter(ProductEvent.created_at >= cutoff, ProductEvent.session_id.isnot(None))
        .scalar()
    ) or 0

    return jsonify(
        {
            "days": days,
            "totals": totals,
            "daily": daily,
            "top_paths": top_paths,
            "distinct_sessions": distinct_sessions,
        }
    )
