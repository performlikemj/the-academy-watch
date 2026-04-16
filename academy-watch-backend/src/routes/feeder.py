"""Feeder blueprint for squad origins endpoints.

Public read-only endpoints that show which academies feed a club's squad.
"""

import logging

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

feeder_bp = Blueprint("feeder", __name__)


def _get_feeder_service():
    """Lazy-load FeederService to avoid circular imports."""
    from src.services.feeder_service import FeederService

    return FeederService()


@feeder_bp.route("/feeder/competitions", methods=["GET"])
def get_competitions():
    """Return supported competitions for browsing."""
    service = _get_feeder_service()
    return jsonify({"competitions": service.get_competitions()})


@feeder_bp.route("/feeder/competitions/<int:league_api_id>/teams", methods=["GET"])
def get_competition_teams(league_api_id):
    """Return teams in a competition for a given season."""
    season = request.args.get("season", type=int)
    if not season:
        return jsonify({"error": "season parameter is required"}), 400

    service = _get_feeder_service()
    try:
        teams = service.get_competition_teams(league_api_id, season)
        return jsonify({"teams": teams, "season": season, "league_api_id": league_api_id})
    except Exception as e:
        logger.error(f"Failed to fetch competition teams: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch teams"}), 500


@feeder_bp.route("/feeder/teams/<int:team_api_id>/origins", methods=["GET"])
def get_squad_origins(team_api_id):
    """Return academy breakdown for a team's squad.

    Query params:
        season (optional): defaults to current season
        league (optional): filter to a specific competition
    """
    league = request.args.get("league", type=int)
    season = request.args.get("season", type=int)

    service = _get_feeder_service()
    try:
        result = service.get_squad_origins(team_api_id, league_api_id=league, season=season)
        return jsonify(result)
    except Exception as e:
        logger.error(f"Failed to fetch squad origins for team {team_api_id}: {e}", exc_info=True)
        return jsonify({"error": "Failed to fetch squad origins"}), 500
