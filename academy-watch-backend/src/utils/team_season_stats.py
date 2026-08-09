"""Batch season-stat projections shared by public team read surfaces."""

from sqlalchemy import func
from src.models.league import PlayerStatsCache, db
from src.models.season_rollup import PlayerSeasonTotal
from src.models.weekly import Fixture, FixturePlayerStats


def rollup_provenance(total: PlayerSeasonTotal) -> dict:
    """The stable five-key public provenance contract."""
    return {
        "primary_source": total.primary_source,
        "reconcile_flag": total.reconcile_flag,
        "fixtures_minutes": total.fixtures_minutes,
        "journey_minutes": total.journey_minutes,
        "computed_at": total.computed_at.isoformat() if total.computed_at else None,
    }


def rollup_stats_by_player(player_api_ids: list[int], season: int) -> tuple[dict[int, dict], dict[int, list]]:
    """Read one source-selected totals row per current roster member."""
    if not player_api_ids:
        return {}, {}
    rows = PlayerSeasonTotal.query.filter(
        PlayerSeasonTotal.player_api_id.in_(player_api_ids),
        PlayerSeasonTotal.season == season,
        PlayerSeasonTotal.level_group == "senior",
    ).all()
    stats = {}
    clubs = {}
    for total in rows:
        stats[total.player_api_id] = {
            "appearances": total.appearances,
            "goals": total.goals,
            "assists": total.assists,
            "minutes_played": total.minutes,
            "saves": total.saves,
            "goals_conceded": total.goals_conceded,
            "yellows": total.yellows,
            "reds": total.reds,
            "avg_rating": float(total.avg_rating) if total.avg_rating is not None else None,
            "stats_coverage": "season-rollup",
            "rollup_missing": False,
            "provenance": rollup_provenance(total),
        }
        clubs[total.player_api_id] = total.clubs or []
    return stats, clubs


def missing_rollup_stats() -> dict:
    """Represent absent rollup coverage without fabricating zero production."""
    return {
        "appearances": None,
        "goals": None,
        "assists": None,
        "minutes_played": None,
        "saves": None,
        "goals_conceded": None,
        "yellows": None,
        "reds": None,
        "avg_rating": None,
        "stats_coverage": "season-rollup",
        "rollup_missing": True,
        "provenance": None,
    }


def live_stats_by_player(tracked_players: list, season: int) -> dict[int, dict]:
    """Batch fixture/cache stats for an exact season on the compatibility path."""
    player_api_ids = [player.player_api_id for player in tracked_players]
    if not player_api_ids:
        return {}

    stats = {}
    fixture_rows = (
        db.session.query(
            FixturePlayerStats.player_api_id,
            func.count(FixturePlayerStats.id).label("appearances"),
            func.coalesce(func.sum(FixturePlayerStats.goals), 0).label("goals"),
            func.coalesce(func.sum(FixturePlayerStats.assists), 0).label("assists"),
            func.coalesce(func.sum(FixturePlayerStats.minutes), 0).label("minutes_played"),
            func.coalesce(func.sum(FixturePlayerStats.saves), 0).label("saves"),
            func.coalesce(func.sum(FixturePlayerStats.yellows), 0).label("yellows"),
            func.coalesce(func.sum(FixturePlayerStats.reds), 0).label("reds"),
        )
        .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
        .filter(
            FixturePlayerStats.player_api_id.in_(player_api_ids),
            Fixture.season == season,
        )
        .group_by(FixturePlayerStats.player_api_id)
        .all()
    )
    for row in fixture_rows:
        stats[row.player_api_id] = {
            "appearances": int(row.appearances or 0),
            "goals": int(row.goals or 0),
            "assists": int(row.assists or 0),
            "minutes_played": int(row.minutes_played or 0),
            "saves": int(row.saves or 0),
            "yellows": int(row.yellows or 0),
            "reds": int(row.reds or 0),
        }

    limited_ids = [
        player.player_api_id for player in tracked_players if player.data_depth in ("events_only", "profile_only")
    ]
    if not limited_ids:
        return stats
    for player_api_id in limited_ids:
        stats.pop(player_api_id, None)

    cache_query = db.session.query(
        PlayerStatsCache.player_api_id,
        func.coalesce(func.sum(PlayerStatsCache.appearances), 0).label("appearances"),
        func.coalesce(func.sum(PlayerStatsCache.goals), 0).label("goals"),
        func.coalesce(func.sum(PlayerStatsCache.assists), 0).label("assists"),
        func.coalesce(func.sum(PlayerStatsCache.minutes_played), 0).label("minutes_played"),
        func.coalesce(func.sum(PlayerStatsCache.saves), 0).label("saves"),
        func.coalesce(func.sum(PlayerStatsCache.yellows), 0).label("yellows"),
        func.coalesce(func.sum(PlayerStatsCache.reds), 0).label("reds"),
    ).filter(
        PlayerStatsCache.player_api_id.in_(limited_ids),
        PlayerStatsCache.season == season,
    )

    for row in cache_query.group_by(PlayerStatsCache.player_api_id).all():
        stats[row.player_api_id] = {
            "appearances": int(row.appearances or 0),
            "goals": int(row.goals or 0),
            "assists": int(row.assists or 0),
            "minutes_played": int(row.minutes_played or 0),
            "saves": int(row.saves or 0),
            "yellows": int(row.yellows or 0),
            "reds": int(row.reds or 0),
        }
    return stats
