"""Public club directory route (dark behind CLUB_DIRECTORY_ENABLED; answers as if unrouted while off)."""

from flask import Blueprint, abort, current_app, jsonify, request
from src.extensions import limiter
from src.services import club_directory

club_directory_bp = Blueprint("club_directory", __name__)


def _as_before_this_route():
    """Flag off = today: hand the request to the app's catch-all, exactly as when no route matched."""
    fallback = current_app.view_functions.get("serve")
    if fallback is None:
        abort(404)
    return fallback(path=request.path.lstrip("/"))


@club_directory_bp.route("/programs", methods=["GET"])
@limiter.limit("60 per minute", exempt_when=lambda: not club_directory.directory_enabled())
def list_programs():
    if not club_directory.directory_enabled():
        return _as_before_this_route()
    try:
        params = club_directory.parse_search(request.args)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    response = jsonify(club_directory.search(params))
    # A hidden club must drop out at once, and a visitor's position is never cached.
    response.headers["Cache-Control"] = "no-store"
    return response
