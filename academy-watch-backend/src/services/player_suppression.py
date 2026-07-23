"""Central suppression predicates and neutral player-surface enforcement."""

from __future__ import annotations

from collections.abc import Iterable
from functools import wraps

from flask import current_app, jsonify
from sqlalchemy import and_, exists
from src.models.league import db
from src.models.player_suppression import PlayerSuppression

ACTIVE_SUPPRESSION_STATUS = "active"
NEUTRAL_PLAYER_NOT_FOUND = {"error": "Player not found"}


class PlayerSuppressedError(RuntimeError):
    """Raised when an internal creation path targets a suppressed player."""


def active_suppression_exists(player_api_id):
    """Correlated ``EXISTS`` for a player-id SQL expression (or scalar id).

    Callers compose this into their existing query, so suppression enforcement
    adds no round trip and cannot become a per-row Python filter.
    """

    return exists().where(
        and_(
            PlayerSuppression.player_api_id == player_api_id,
            PlayerSuppression.status == ACTIVE_SUPPRESSION_STATUS,
        )
    )


def without_active_suppression(player_api_id):
    """SQL predicate retaining only players without an active suppression."""

    return ~active_suppression_exists(player_api_id)


def is_player_suppressed(player_api_id: int) -> bool:
    """Scalar check for single-player routes and write guards."""

    return bool(db.session.query(active_suppression_exists(int(player_api_id))).scalar())


def active_suppressed_player_ids(player_api_ids: Iterable[int]) -> set[int]:
    """One batched lookup for serializers/search results; never an N+1."""

    ids = {int(player_id) for player_id in player_api_ids if player_id is not None}
    if not ids:
        return set()
    return {
        row[0]
        for row in db.session.query(PlayerSuppression.player_api_id)
        .filter(
            PlayerSuppression.player_api_id.in_(ids),
            PlayerSuppression.status == ACTIVE_SUPPRESSION_STATUS,
        )
        .all()
    }


def neutral_player_not_found():
    """The same minimal response used for suppressed and unknown players."""

    return jsonify(NEUTRAL_PLAYER_NOT_FOUND), 404


def hide_suppressed_player(argument_name: str):
    """Route decorator returning the neutral 404 before any player data loads."""

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            # A few narrow unit fixtures mount a public blueprint without any
            # SQLAlchemy extension because the tested endpoint is API-only.
            # The production app always registers this repository's db.
            if current_app.extensions.get("sqlalchemy") is not db:
                return view(*args, **kwargs)
            player_api_id = kwargs.get(argument_name)
            if player_api_id is not None and is_player_suppressed(player_api_id):
                return neutral_player_not_found()
            return view(*args, **kwargs)

        return wrapped

    return decorator


__all__ = [
    "ACTIVE_SUPPRESSION_STATUS",
    "PlayerSuppressedError",
    "active_suppressed_player_ids",
    "active_suppression_exists",
    "hide_suppressed_player",
    "is_player_suppressed",
    "neutral_player_not_found",
    "without_active_suppression",
]
