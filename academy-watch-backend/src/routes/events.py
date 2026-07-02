"""Product analytics endpoints for The Academy Watch.

- ``POST /api/events`` — anonymous, batched event ingestion (privacy-light:
  no cookies / IP / user-agent; identity only from a verified token if present).
- ``GET /api/admin/analytics/summary`` — admin-only aggregate rollup.
"""

import logging
from datetime import UTC, datetime, timedelta

from flask import Blueprint, jsonify, request
from sqlalchemy import func
from src.auth import _get_authorized_email, require_api_key
from src.extensions import limiter
from src.models.league import db
from src.models.product_event import ProductEvent

events_bp = Blueprint("events", __name__)
logger = logging.getLogger(__name__)

# Exactly these names are accepted; anything else is silently dropped so one
# bad client event never fails the rest of the batch.
ALLOWED_EVENTS = frozenset(
    {
        "pageview",
        "claim_submitted",
        "follow_added",
        "shadow_minted",
        "search_performed",
        "list_created",
    }
)

MAX_BATCH = 25

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
