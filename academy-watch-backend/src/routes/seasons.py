"""Public season-directory endpoint for season pickers."""

from flask import Blueprint, jsonify
from src.auth import _safe_error_payload
from src.models.league import db
from src.services.reported_match_totals import rollup_metadata_relations
from src.utils.academy_window import current_stats_season, season_bounds, stats_season_with_data

_total_meta, _cell_meta = rollup_metadata_relations()

seasons_bp = Blueprint("seasons", __name__)


@seasons_bp.route("/seasons", methods=["GET"])
def get_seasons():
    """List valid season start-years that have rollup coverage."""
    try:
        current = current_stats_season()
        display = stats_season_with_data(db.session)
        low, high = season_bounds(db.session, include_rollup_history=True)
        covered = {
            int(row.season)
            for row in db.session.query(_total_meta.c.season)
            .filter(_total_meta.c.season.between(low, high))
            .distinct()
            .all()
        }
        available = covered | {current, display}
        return jsonify(
            {
                "current_season": current,
                "display_season": display,
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
