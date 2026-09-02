"""Dialect-neutral aggregate queries for player reach signals."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import case, func, literal
from src.models.league import db
from src.models.player_fan import PlayerFan
from src.models.product_event import ProductEvent
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.services.public_player_subject import owner_account_ids_subquery


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is not None:
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


def _now_naive(now: datetime | None) -> datetime:
    return _naive_utc(now or datetime.now(UTC))


def _unique_ids(signed_ids) -> tuple[int, ...]:
    return tuple(dict.fromkeys(signed_ids))


def _excluded_ids(exclude_user_ids) -> tuple[int, ...]:
    return tuple(dict.fromkeys(exclude_user_ids))


def fan_counts(signed_ids, *, since=None, exclude_user_ids=()) -> dict[int, tuple[int, int]]:
    """Return total fans and fans added since a timestamp for each signed id."""

    player_ids = _unique_ids(signed_ids)
    if not player_ids:
        return {}
    since = _naive_utc(since) if since is not None else None
    added = func.count(case((PlayerFan.created_at >= since, 1))) if since is not None else literal(0)
    query = db.session.query(
        PlayerFan.player_api_id,
        func.count(PlayerFan.id),
        added,
    ).filter(
        PlayerFan.player_api_id.in_(player_ids),
        PlayerFan.user_account_id.not_in(owner_account_ids_subquery(PlayerFan.player_api_id)),
    )
    excluded = _excluded_ids(exclude_user_ids)
    if excluded:
        query = query.filter(PlayerFan.user_account_id.not_in(excluded))
    rows = query.group_by(PlayerFan.player_api_id).all()
    counts = {player_id: (int(total), int(added_since)) for player_id, total, added_since in rows}
    return {player_id: counts.get(player_id, (0, 0)) for player_id in player_ids}


def watchlist_counts(signed_ids, *, since, exclude_user_ids=()) -> dict[int, tuple[int, int]]:
    """Return distinct watchlisting accounts and newly watchlisting accounts."""

    player_ids = _unique_ids(signed_ids)
    if not player_ids:
        return {}
    since = _naive_utc(since)
    query = db.session.query(
        ScoutWatchlistEntry.player_api_id,
        func.count(func.distinct(ScoutWatchlistEntry.user_account_id)),
        func.count(
            func.distinct(
                case(
                    (ScoutWatchlistEntry.created_at >= since, ScoutWatchlistEntry.user_account_id),
                    else_=None,
                )
            )
        ),
    ).filter(
        ScoutWatchlistEntry.player_api_id.in_(player_ids),
        ScoutWatchlistEntry.user_account_id.not_in(owner_account_ids_subquery(ScoutWatchlistEntry.player_api_id)),
    )
    excluded = _excluded_ids(exclude_user_ids)
    if excluded:
        query = query.filter(ScoutWatchlistEntry.user_account_id.not_in(excluded))
    rows = query.group_by(ScoutWatchlistEntry.player_api_id).all()
    counts = {player_id: (int(total), int(added_since)) for player_id, total, added_since in rows}
    return {player_id: counts.get(player_id, (0, 0)) for player_id in player_ids}


def profile_view_counts(signed_ids, *, now=None) -> dict[int, dict[str, int]]:
    """Return anonymous profile-view totals over rolling 7- and 30-day windows."""

    player_ids = _unique_ids(signed_ids)
    if not player_ids:
        return {}
    now = _now_naive(now)
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)
    player_id = case((ProductEvent.event_name == "profile_view", ProductEvent.props["player_api_id"].as_integer()))
    rows = (
        db.session.query(
            player_id.label("player_api_id"),
            func.count(case((ProductEvent.created_at >= seven_days_ago, 1))),
            func.count(ProductEvent.id),
        )
        .filter(
            ProductEvent.event_name == "profile_view",
            player_id.in_(player_ids),
            ProductEvent.created_at >= thirty_days_ago,
            ProductEvent.created_at <= now,
        )
        .group_by(player_id)
        .all()
    )
    counts = {
        row_player_id: {"last_7_days": int(last_7_days), "last_30_days": int(last_30_days)}
        for row_player_id, last_7_days, last_30_days in rows
    }
    return {player_id: counts.get(player_id, {"last_7_days": 0, "last_30_days": 0}) for player_id in player_ids}


def profile_view_counts_since(signed_ids, *, since, now=None) -> dict[int, int]:
    """Return anonymous profile views in the inclusive ``since``/``now`` window."""

    player_ids = _unique_ids(signed_ids)
    if not player_ids:
        return {}
    since = _naive_utc(since)
    now = _now_naive(now)
    player_id = case((ProductEvent.event_name == "profile_view", ProductEvent.props["player_api_id"].as_integer()))
    rows = (
        db.session.query(player_id.label("player_api_id"), func.count(ProductEvent.id))
        .filter(
            ProductEvent.event_name == "profile_view",
            player_id.in_(player_ids),
            ProductEvent.created_at >= since,
            ProductEvent.created_at <= now,
        )
        .group_by(player_id)
        .all()
    )
    counts = {row_player_id: int(count) for row_player_id, count in rows}
    return {player_id: counts.get(player_id, 0) for player_id in player_ids}


def is_fan(user_account_id, signed_id) -> bool:
    """Return whether a non-owner account follows one signed player identity."""

    return (
        db.session.query(PlayerFan.id)
        .filter(
            PlayerFan.user_account_id == user_account_id,
            PlayerFan.player_api_id == signed_id,
            PlayerFan.user_account_id.not_in(owner_account_ids_subquery(PlayerFan.player_api_id)),
        )
        .first()
        is not None
    )


__all__ = [
    "fan_counts",
    "is_fan",
    "profile_view_counts",
    "profile_view_counts_since",
    "watchlist_counts",
]
