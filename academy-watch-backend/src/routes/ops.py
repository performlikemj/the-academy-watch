"""Operations overview — one cheap aggregate pass for the admin cockpit.

Single endpoint, GET /api/admin/ops/overview, returning the counts the
Operations page needs to decide whether repairs are required and whether
they were actually applied (the dry-run trap: run counters look identical,
only these before/after counts prove a live run happened).

Aggregate SQL only — no per-row work, no API-Football calls.
"""

import logging

from flask import Blueprint, jsonify
from sqlalchemy import case, func
from src.auth import _safe_error_payload, require_api_key
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import AdminSetting, BackgroundJob, db
from src.models.tracked_player import TrackedPlayer
from src.utils.supported_leagues import get_crawl_league_ids, get_supported_leagues

ops_bp = Blueprint("ops", __name__)
logger = logging.getLogger(__name__)


def _runs_paused() -> bool:
    """Read the runs_paused flag from AdminSetting (same source as
    GET /api/admin/run-status)."""
    try:
        row = AdminSetting.query.filter_by(key="runs_paused").first()
        if row and row.value_json is not None:
            return row.value_json.strip().lower() in ("1", "true", "yes", "y")
    except Exception:
        pass
    return False


@ops_bp.route("/admin/ops/overview", methods=["GET"])
@require_api_key
def admin_ops_overview():
    """System-status snapshot for the admin Operations page.

    Tracked-player hygiene counts are scoped to ACTIVE rows (the rows the
    repair endpoints operate on for operational purposes): placeholder
    names (the 'Player NNNN' prefix backfill-names repairs), NULL
    position/birth_date/age, and deprecated owning-club rows that
    recompute-academy deactivates.
    """
    try:
        active = TrackedPlayer.is_active.is_(True)

        def _active_and(cond):
            return func.coalesce(func.sum(case((db.and_(active, cond), 1), else_=0)), 0)

        tracked_row = db.session.query(
            func.count(TrackedPlayer.id),
            func.coalesce(func.sum(case((active, 1), else_=0)), 0),
            _active_and(TrackedPlayer.player_name.like("Player %")),
            _active_and(TrackedPlayer.position.is_(None)),
            _active_and(TrackedPlayer.birth_date.is_(None)),
            _active_and(TrackedPlayer.age.is_(None)),
            _active_and(TrackedPlayer.data_source == "owning-club"),
        ).one()
        (
            total,
            active_count,
            placeholder_names,
            null_position,
            null_birth_date,
            null_age,
            owning_club_active,
        ) = (int(v or 0) for v in tracked_row)

        journeys_total = int(db.session.query(func.count(PlayerJourney.id)).scalar() or 0)
        journeys_with_entries = int(
            db.session.query(func.count(func.distinct(PlayerJourneyEntry.journey_id))).scalar() or 0
        )

        jobs_active = int(
            db.session.query(func.count(BackgroundJob.id)).filter(BackgroundJob.status == "running").scalar() or 0
        )

        api_usage_today = None
        try:
            from src.models.api_cache import APIUsageDaily

            api_usage_today = int(APIUsageDaily.today_total())
        except Exception:
            api_usage_today = None

        supported_leagues = [
            {"id": league_id, "name": info["name"], "region": info["region"]}
            for league_id, info in get_supported_leagues().items()
        ]

        return jsonify(
            {
                "tracked": {
                    "active": active_count,
                    "inactive": total - active_count,
                    "placeholder_names": placeholder_names,
                    "null_position": null_position,
                    "null_birth_date": null_birth_date,
                    "null_age": null_age,
                    "owning_club_active": owning_club_active,
                },
                "journeys": {
                    "total": journeys_total,
                    "with_entries": journeys_with_entries,
                },
                "crawl": {
                    "supported_leagues": supported_leagues,
                    "crawl_league_ids": get_crawl_league_ids(),
                },
                "jobs": {"active": jobs_active},
                "runs_paused": _runs_paused(),
                "api_usage_today": api_usage_today,
            }
        )
    except Exception as e:
        logger.exception("admin_ops_overview failed")
        return jsonify(_safe_error_payload(e, "Failed to build ops overview")), 500
