"""Root-level public player share surfaces."""

from __future__ import annotations

from flask import Blueprint, make_response, render_template, send_file
from src.services.player_share_card import (
    build_share_meta,
    public_share_origin,
    render_share_card,
)
from src.services.player_suppression import neutral_player_not_found
from src.services.public_player_subject import resolve_public_adult_subject
from src.services.sitemap_service import get_sitemap_response

share_bp = Blueprint("share", __name__)


def _no_store(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def _neutral_not_found():
    response, status = neutral_player_not_found()
    return _no_store(response), status


@share_bp.route("/p/<int(signed=True):player_api_id>", methods=["GET"])
def player_share_page(player_api_id: int):
    subject = resolve_public_adult_subject(player_api_id)
    if subject is None:
        return _neutral_not_found()

    response = make_response(render_template("player_share.html", meta=build_share_meta(subject)))
    return _no_store(response)


@share_bp.route("/p/<int(signed=True):player_api_id>/card.png", methods=["GET"])
def player_share_card(player_api_id: int):
    subject = resolve_public_adult_subject(player_api_id)
    if subject is None:
        return _neutral_not_found()

    response = send_file(render_share_card(subject), mimetype="image/png", download_name="card.png")
    return _no_store(response)


@share_bp.route("/sitemap.xml", methods=["GET"])
def sitemap_xml():
    return get_sitemap_response()


@share_bp.route("/robots.txt", methods=["GET"])
def robots_txt():
    body = "\n".join(
        (
            "User-agent: *",
            "Allow: /p/",
            "Disallow: /api/",
            f"Sitemap: {public_share_origin()}/sitemap.xml",
            "",
        )
    )
    response = make_response(body)
    response.mimetype = "text/plain"
    return response


@share_bp.route("/p", methods=["GET"])
@share_bp.route("/p/", methods=["GET"])
def empty_player_share_path():
    return _neutral_not_found()


@share_bp.route("/p/<path:rest>", methods=["GET"])
def invalid_player_share_path(rest: str):
    del rest
    return _neutral_not_found()


__all__ = ["share_bp"]
