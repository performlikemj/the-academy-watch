"""Canonical read-only player-facing status selection."""

from __future__ import annotations

from src.models.journey import PlayerJourney
from src.models.tracked_player import TrackedPlayer

_UNSET = object()


def player_facing_status(
    player_api_id: int,
    *,
    journey: PlayerJourney | None | object = _UNSET,
    tracked: TrackedPlayer | None | object = _UNSET,
) -> str | None:
    """Return the persisted status used by player/scout-facing surfaces.

    ``PlayerJourney.current_status`` has precedence. When it is absent, use
    the preferred active academy-origin ``TrackedPlayer`` row: owning-club
    rows are excluded and the lowest row id wins, matching the scout surface.
    Callers that already loaded the two rows may pass them to avoid repeat
    queries.
    """
    if journey is _UNSET:
        journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()
    if isinstance(journey, PlayerJourney) and journey.current_status:
        return journey.current_status

    if tracked is _UNSET:
        tracked = (
            TrackedPlayer.query.filter_by(player_api_id=player_api_id, is_active=True)
            .filter(TrackedPlayer.data_source != "owning-club")
            .order_by(TrackedPlayer.id)
            .first()
        )
    return tracked.status if isinstance(tracked, TrackedPlayer) else None


__all__ = ["player_facing_status"]
