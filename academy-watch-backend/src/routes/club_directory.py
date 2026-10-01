"""Public club directory routes (dark behind CLUB_DIRECTORY_ENABLED; answer as if unrouted while off).

``GET /api/programs`` browses by the plain filters. Anything that says where a
visitor is, or what they typed, goes in the body of
``POST /api/club-directory/search`` so it never lands in a URL (access logs,
browser history, analytics).
"""

import json

from flask import Blueprint, abort, current_app, jsonify, request
from src.extensions import limiter
from src.services import club_directory
from werkzeug.exceptions import MethodNotAllowed, RequestEntityTooLarge

club_directory_bp = Blueprint("club_directory", __name__)

MAX_SEARCH_BODY_BYTES = 2048
SEARCH_METHODS = ["OPTIONS", "POST"]

# One budget for the directory, however it is asked.
_directory_limit = limiter.shared_limit(
    "60 per minute",
    scope="club_directory",
    exempt_when=lambda: not club_directory.directory_enabled(),
)


def _as_before_this_route():
    """Flag off = today: answer exactly as when no route matched (the app's catch-all, GET/HEAD only)."""
    fallback = current_app.view_functions.get("serve")
    if fallback is None:
        abort(404)
    if request.method in ("GET", "HEAD"):
        return fallback(path=request.path.lstrip("/"))
    allowed = set()
    for rule in current_app.url_map.iter_rules("serve"):
        allowed.update(rule.methods or ())
    if request.method == "OPTIONS":
        response = current_app.response_class()
        response.allow.update(allowed)
        return response
    raise MethodNotAllowed(valid_methods=sorted(allowed))


def _page(params):
    response = jsonify(club_directory.search(params))
    # A hidden club must drop out at once, and a visitor's position is never cached.
    response.headers["Cache-Control"] = "no-store"
    return response


@club_directory_bp.route("/programs", methods=["GET"])
@_directory_limit
def list_programs():
    if not club_directory.directory_enabled():
        return _as_before_this_route()
    try:
        club_directory.refuse_url_search_terms(request.args)
        params = club_directory.parse_search(request.args)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return _page(params)


# Every method is routed here so that, flag off, each one is answered exactly as an unrouted path was.
@club_directory_bp.route(
    "/club-directory/search",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    provide_automatic_options=False,
)
@_directory_limit
def search_programs():
    if not club_directory.directory_enabled():
        return _as_before_this_route()
    if request.method == "OPTIONS":
        response = current_app.response_class()
        response.allow.update(SEARCH_METHODS)
        return response
    if request.method != "POST":
        raise MethodNotAllowed(valid_methods=SEARCH_METHODS)
    # A hard cap on the stream itself: a chunked body announces no length, so a Content-Length check alone is no limit.
    # Werkzeug cuts a chunked stream off at the cap without saying so, so the cap sits one byte past the limit: at most
    # 2049 bytes are ever read, and reaching the 2049th is what "too large" means.
    request.max_content_length = MAX_SEARCH_BODY_BYTES + 1
    try:
        raw = request.get_data(cache=False)
    except RequestEntityTooLarge:
        raw = None
    if raw is None or len(raw) > MAX_SEARCH_BODY_BYTES:
        return jsonify({"error": "the search is too large"}), 413
    try:
        data = json.loads(raw) if request.is_json else None
    except (ValueError, RecursionError):
        data = None
    try:
        params = club_directory.parse_search(club_directory.search_args_from_body(data))
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400
    return _page(params)
