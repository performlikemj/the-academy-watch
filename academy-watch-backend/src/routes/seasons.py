"""Public season-directory endpoint for season pickers."""

from flask import Blueprint, jsonify
from src.auth import _safe_error_payload
from src.models.league import db
from src.models.season_rollup import PlayerSeasonTotal
from src.utils.academy_window import current_stats_season, season_bounds

seasons_bp = Blueprint("seasons", __name__)


@seasons_bp.route("/seasons", methods=["GET"])
def get_seasons():
    """List valid season start-years that have rollup coverage."""
    try:
        current = current_stats_season()
        low, high = season_bounds(db.session)
        covered = {
            int(row.season)
            for row in db.session.query(PlayerSeasonTotal.season)
            .filter(PlayerSeasonTotal.season.between(low, high))
            .distinct()
            .all()
        }
        available = covered | {current}
        return jsonify(
            {
                "current_season": current,
                "bounds": {"min": low, "max": high},
                "seasons": [
                    {
                        "season": season,
                        "label": f"{season}/{str(season + 1)[-2:]}",
                        "has_rollup": season in covered,
                        "is_current": season == current,
                    }
                    for season in sorted(available, reverse=True)
                    if low <= season <= high
                ],
            }
        )
    except Exception as error:
        return jsonify(_safe_error_payload(error, "Failed to fetch seasons")), 500
