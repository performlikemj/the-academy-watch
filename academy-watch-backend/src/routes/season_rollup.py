"""Admin operations for the season-rollup read surface.

Both endpoints are pure database operations. Rebuilds are keyset-paged by
``player_api_id`` and delegate every derived-row write to the public
``season_rollup_service.refresh_player`` API.

Rows-behind uses the mutation clocks the source schema actually exposes:
``PlayerJourneyEntry.stats_synced_at``,
``AcademyPlayerSeasonStats.updated_at``, and
``PlayerShadowStats.updated_at``. ``PlayerSeasonCell.synced_at`` also catches a
derived cell that is newer than (or missing) its matching total. Fixture rows
have no created/updated/synced clock, so they can be identified as stale only
when their player-season has no fixture cell; steady-state fixture freshness is
enforced by the D3b FPS write choke point. Legacy/manual journey rows with a
null ``stats_synced_at`` have the same schema-limited blind spot after an
existing total; ``scope=all`` is the repair fallback for both cases.
"""

import logging

from flask import Blueprint, jsonify, request
from sqlalchemy import DateTime, and_, case, func, literal, or_, select, type_coerce, union_all
from src.auth import _safe_error_payload, require_api_key
from src.models.follow import PlayerShadowStats
from src.models.journey import PlayerJourney, PlayerJourneyEntry
from src.models.league import AcademyPlayerSeasonStats, db
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.weekly import Fixture, FixturePlayerStats
from src.services import season_rollup_service

season_rollup_bp = Blueprint("season_rollup", __name__)
logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 25
_MAX_BATCH_SIZE = 100
_VALID_SCOPES = {"player", "season", "stale", "all"}


def _has_stats(model):
    """Match the rollup service's apps/minutes/goals noise boundary."""
    return or_(
        func.coalesce(model.appearances, 0) != 0,
        func.coalesce(model.minutes, 0) != 0,
        func.coalesce(model.goals, 0) != 0,
    )


def _has_fixture_stats():
    """FPS appearances are derived from positive minutes by the feeder."""
    return or_(
        func.coalesce(FixturePlayerStats.minutes, 0) != 0,
        func.coalesce(FixturePlayerStats.goals, 0) != 0,
    )


def _had_source_cell(player_column, season_column, source: str, level_group=None):
    """Include a zeroed source only while its old cell still needs deletion."""
    conditions = (
        PlayerSeasonCell.player_api_id == player_column,
        PlayerSeasonCell.season == season_column,
        PlayerSeasonCell.source == source,
    )
    if level_group is not None:
        conditions += (PlayerSeasonCell.level_group == level_group,)
    return select(literal(1)).select_from(PlayerSeasonCell).where(*conditions).exists()


def _utc_source_clock(column):
    """Interpret legacy naive source clocks as UTC on PostgreSQL.

    The application writes these columns with ``datetime.now(UTC)`` even though
    APSS/shadow predate timezone-aware column types. PostgreSQL otherwise
    promotes them to TIMESTAMPTZ using the connection's session timezone when
    unioned with PJE/cell clocks. SQLite stores all four clocks uniformly and
    needs the original column expression for portable comparisons.
    """
    if db.session.get_bind().dialect.name == "postgresql":
        return type_coerce(column.op("AT TIME ZONE")(literal("UTC")), DateTime(timezone=True))
    return column


def _candidate_player_ids(
    season: int | None = None,
    *,
    after: int | None = None,
    per_source_limit: int | None = None,
):
    """All rebuildable player ids, including orphan derived rows."""
    fixture_rows = (
        select(FixturePlayerStats.player_api_id.label("player_api_id"))
        .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
        .where(
            or_(
                _has_fixture_stats(),
                _had_source_cell(FixturePlayerStats.player_api_id, Fixture.season, "fixtures"),
            )
        )
    )
    journey_rows = (
        select(PlayerJourney.player_api_id.label("player_api_id"))
        .join(PlayerJourneyEntry, PlayerJourneyEntry.journey_id == PlayerJourney.id)
        .where(
            or_(
                _has_stats(PlayerJourneyEntry),
                _had_source_cell(PlayerJourney.player_api_id, PlayerJourneyEntry.season, "journey"),
            )
        )
    )
    apss_rows = select(AcademyPlayerSeasonStats.player_api_id.label("player_api_id")).where(
        or_(
            _has_stats(AcademyPlayerSeasonStats),
            _had_source_cell(
                AcademyPlayerSeasonStats.player_api_id,
                AcademyPlayerSeasonStats.season,
                "apss",
            ),
        )
    )
    shadow_rows = select(PlayerShadowStats.player_api_id.label("player_api_id")).where(
        or_(
            _has_stats(PlayerShadowStats),
            _had_source_cell(PlayerShadowStats.player_api_id, PlayerShadowStats.season, "shadow"),
        )
    )
    cell_rows = select(PlayerSeasonCell.player_api_id.label("player_api_id"))
    total_rows = select(PlayerSeasonTotal.player_api_id.label("player_api_id"))

    if season is not None:
        fixture_rows = fixture_rows.where(Fixture.season == season)
        journey_rows = journey_rows.where(PlayerJourneyEntry.season == season)
        apss_rows = apss_rows.where(AcademyPlayerSeasonStats.season == season)
        shadow_rows = shadow_rows.where(PlayerShadowStats.season == season)
        cell_rows = cell_rows.where(PlayerSeasonCell.season == season)
        total_rows = total_rows.where(PlayerSeasonTotal.season == season)

    source_queries = (
        (fixture_rows, FixturePlayerStats.player_api_id),
        (journey_rows, PlayerJourney.player_api_id),
        (apss_rows, AcademyPlayerSeasonStats.player_api_id),
        (shadow_rows, PlayerShadowStats.player_api_id),
        (cell_rows, PlayerSeasonCell.player_api_id),
        (total_rows, PlayerSeasonTotal.player_api_id),
    )
    bounded_queries = []
    for query, player_column in source_queries:
        if after is not None:
            query = query.where(player_column > after)
        if per_source_limit is not None:
            # DISTINCT is deliberate: these WHERE clauses contain correlated
            # season checks in ``_had_source_cell``. PostgreSQL rejects the
            # equivalent GROUP BY shape because that outer season is not a
            # grouping column, while DISTINCT safely deduplicates the one
            # projected player id before applying the source-local cap.
            query = query.distinct().order_by(player_column).limit(per_source_limit)
            limited = query.subquery()
            query = select(limited.c.player_api_id)
        bounded_queries.append(query)

    # A page query reads at most ``per_source_limit`` ids from each indexed
    # source, then merges/deduplicates at most 6N ids.
    rows = union_all(*bounded_queries).subquery()
    return select(rows.c.player_api_id).where(rows.c.player_api_id.is_not(None)).group_by(rows.c.player_api_id)


def _stale_player_ids(player_ids: tuple[int, ...] | None = None):
    """Players with a source cell/row newer than its matching total.

    Timed sources compare at the exact ``(player, season, level_group)`` grain.
    Fixture rows have no mutation clock, so that branch can only identify a
    player-season for which no fixture-derived cell exists at all.
    """
    journey_level = case(
        (PlayerJourneyEntry.is_international.is_(True), literal("international")),
        (PlayerJourneyEntry.is_youth.is_(True), literal("youth")),
        else_=literal("senior"),
    )

    journey_rows = (
        select(
            PlayerJourney.player_api_id.label("player_api_id"),
            PlayerJourneyEntry.season.label("season"),
            journey_level.label("level_group"),
            PlayerJourneyEntry.stats_synced_at.label("source_updated_at"),
        )
        .join(PlayerJourneyEntry, PlayerJourneyEntry.journey_id == PlayerJourney.id)
        .where(
            or_(
                _has_stats(PlayerJourneyEntry),
                _had_source_cell(
                    PlayerJourney.player_api_id,
                    PlayerJourneyEntry.season,
                    "journey",
                    journey_level,
                ),
            )
        )
    )
    apss_rows = select(
        AcademyPlayerSeasonStats.player_api_id.label("player_api_id"),
        AcademyPlayerSeasonStats.season.label("season"),
        literal("youth").label("level_group"),
        _utc_source_clock(AcademyPlayerSeasonStats.updated_at).label("source_updated_at"),
    ).where(
        or_(
            _has_stats(AcademyPlayerSeasonStats),
            _had_source_cell(
                AcademyPlayerSeasonStats.player_api_id,
                AcademyPlayerSeasonStats.season,
                "apss",
                "youth",
            ),
        )
    )
    shadow_rows = select(
        PlayerShadowStats.player_api_id.label("player_api_id"),
        PlayerShadowStats.season.label("season"),
        literal("senior").label("level_group"),
        _utc_source_clock(PlayerShadowStats.updated_at).label("source_updated_at"),
    ).where(
        or_(
            _has_stats(PlayerShadowStats),
            _had_source_cell(
                PlayerShadowStats.player_api_id,
                PlayerShadowStats.season,
                "shadow",
                "senior",
            ),
        )
    )
    cell_rows = select(
        PlayerSeasonCell.player_api_id.label("player_api_id"),
        PlayerSeasonCell.season.label("season"),
        PlayerSeasonCell.level_group.label("level_group"),
        PlayerSeasonCell.synced_at.label("source_updated_at"),
    )

    if player_ids is not None:
        journey_rows = journey_rows.where(PlayerJourney.player_api_id.in_(player_ids))
        apss_rows = apss_rows.where(AcademyPlayerSeasonStats.player_api_id.in_(player_ids))
        shadow_rows = shadow_rows.where(PlayerShadowStats.player_api_id.in_(player_ids))
        cell_rows = cell_rows.where(PlayerSeasonCell.player_api_id.in_(player_ids))

    timed_rows = union_all(journey_rows, apss_rows, shadow_rows, cell_rows).subquery()
    source_freshness = (
        select(
            timed_rows.c.player_api_id,
            timed_rows.c.season,
            timed_rows.c.level_group,
            func.max(timed_rows.c.source_updated_at).label("source_updated_at"),
        )
        .group_by(timed_rows.c.player_api_id, timed_rows.c.season, timed_rows.c.level_group)
        .subquery()
    )
    total_freshness_query = select(
        PlayerSeasonTotal.player_api_id,
        PlayerSeasonTotal.season,
        PlayerSeasonTotal.level_group,
        func.max(PlayerSeasonTotal.computed_at).label("computed_at"),
    )
    if player_ids is not None:
        total_freshness_query = total_freshness_query.where(PlayerSeasonTotal.player_api_id.in_(player_ids))
    total_freshness = total_freshness_query.group_by(
        PlayerSeasonTotal.player_api_id,
        PlayerSeasonTotal.season,
        PlayerSeasonTotal.level_group,
    ).subquery()
    timed_stale = (
        select(source_freshness.c.player_api_id)
        .select_from(
            source_freshness.outerjoin(
                total_freshness,
                and_(
                    total_freshness.c.player_api_id == source_freshness.c.player_api_id,
                    total_freshness.c.season == source_freshness.c.season,
                    total_freshness.c.level_group == source_freshness.c.level_group,
                ),
            )
        )
        .where(
            or_(
                total_freshness.c.computed_at.is_(None),
                source_freshness.c.source_updated_at > total_freshness.c.computed_at,
            )
        )
    )

    fixture_keys_query = (
        select(FixturePlayerStats.player_api_id.label("player_api_id"), Fixture.season.label("season"))
        .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
        .where(
            or_(
                _has_fixture_stats(),
                _had_source_cell(FixturePlayerStats.player_api_id, Fixture.season, "fixtures"),
            )
        )
    )
    fixture_cell_keys_query = select(PlayerSeasonCell.player_api_id, PlayerSeasonCell.season).where(
        PlayerSeasonCell.source == "fixtures"
    )
    if player_ids is not None:
        fixture_keys_query = fixture_keys_query.where(FixturePlayerStats.player_api_id.in_(player_ids))
        fixture_cell_keys_query = fixture_cell_keys_query.where(PlayerSeasonCell.player_api_id.in_(player_ids))
    fixture_keys = fixture_keys_query.group_by(FixturePlayerStats.player_api_id, Fixture.season).subquery()
    fixture_cell_keys = fixture_cell_keys_query.group_by(
        PlayerSeasonCell.player_api_id, PlayerSeasonCell.season
    ).subquery()
    fixture_missing_cell = (
        select(fixture_keys.c.player_api_id)
        .select_from(
            fixture_keys.outerjoin(
                fixture_cell_keys,
                and_(
                    fixture_cell_keys.c.player_api_id == fixture_keys.c.player_api_id,
                    fixture_cell_keys.c.season == fixture_keys.c.season,
                ),
            )
        )
        .where(fixture_cell_keys.c.player_api_id.is_(None))
    )

    stale_rows = union_all(timed_stale, fixture_missing_cell).subquery()
    return select(stale_rows.c.player_api_id).group_by(stale_rows.c.player_api_id)


def _page_ids(id_statement, cursor: int, batch_size: int) -> list[int]:
    ids = id_statement.subquery()
    return list(
        db.session.execute(
            select(ids.c.player_api_id)
            .where(ids.c.player_api_id > cursor)
            .order_by(ids.c.player_api_id)
            .limit(batch_size)
        ).scalars()
    )


def _count_ids(id_statement) -> int:
    ids = id_statement.subquery()
    return int(db.session.execute(select(func.count()).select_from(ids)).scalar() or 0)


def _batch_size_arg() -> int:
    batch_size = request.args.get("batch_size", _DEFAULT_BATCH_SIZE, type=int)
    if not isinstance(batch_size, int) or batch_size < 1:
        batch_size = _DEFAULT_BATCH_SIZE
    return min(batch_size, _MAX_BATCH_SIZE)


def _cursor_arg() -> tuple[int | None, int, str | None]:
    raw_cursor = request.args.get("cursor")
    if raw_cursor is None or raw_cursor == "":
        return 0, 0, None

    # A normal cursor is the last scanned player id. If a per-player savepoint
    # failed during a batched sweep, the response carries ``<id>:r<count>``.
    # The retry count is propagated while higher ids are scanned, then causes a
    # wrap to zero at the end. This keeps a poison row from front-blocking the
    # population without forgetting that a lower id still needs another sweep.
    retry_count = 0
    cursor_part = raw_cursor
    if ":r" in raw_cursor:
        cursor_part, retry_part = raw_cursor.rsplit(":r", 1)
        try:
            retry_count = int(retry_part)
        except (TypeError, ValueError):
            return None, 0, "cursor must be a non-negative player_api_id or server-issued retry cursor"
        if retry_count < 1:
            return None, 0, "cursor must be a non-negative player_api_id or server-issued retry cursor"
    try:
        cursor = int(cursor_part)
    except (TypeError, ValueError):
        return None, 0, "cursor must be a non-negative player_api_id or server-issued retry cursor"
    if cursor < 0:
        return None, 0, "cursor must be a non-negative player_api_id or server-issued retry cursor"
    return cursor, retry_count, None


def _positive_int_arg(name: str) -> int | None:
    value = request.args.get(name, type=int)
    if not isinstance(value, int) or value < 1:
        return None
    return value


@season_rollup_bp.route("/admin/season-rollup/rebuild", methods=["POST"])
@require_api_key
def admin_rebuild_season_rollup():
    """Rebuild rollups for one player or a bounded player-id page.

    Query params:
    - ``scope=player&player_api_id=<positive int>``
    - ``scope=season&season=<start-year int>[&batch_size&cursor]``
    - ``scope=stale[&batch_size&cursor]``
    - ``scope=all[&batch_size&cursor]``

    ``cursor`` is normally the last scanned player_api_id and is null when the
    selected sweep has converged. A server-issued ``<id>:r<count>`` cursor carries
    retry state past a failed player; callers must pass it back unchanged. A zero
    cursor restarts a sweep after lower-id stale/failing work is found. Season
    sweeps are also bounded even though only stale and all require it, keeping
    every request safe for the production container. ``remaining`` is a bounded
    continuation gauge: zero means the sweep converged; a positive value is the
    carried failure count plus one when the capped lookahead found another page.
    """
    scope = (request.args.get("scope") or "").strip().lower()
    if scope not in _VALID_SCOPES:
        return jsonify({"error": "scope must be one of: player, season, stale, all"}), 400

    if scope == "player":
        player_api_id = _positive_int_arg("player_api_id")
        if player_api_id is None:
            return jsonify({"error": "player_api_id must be a positive integer"}), 400
        try:
            season_rollup_service.refresh_player(player_api_id, season=None, session=db.session)
            db.session.commit()
            return jsonify({"processed": 1, "remaining": 0, "cursor": None})
        except Exception as exc:
            db.session.rollback()
            logger.exception("season-rollup player rebuild failed for player=%s", player_api_id)
            return jsonify(_safe_error_payload(exc, "Failed to rebuild season rollup")), 500

    season = None
    if scope == "season":
        season = _positive_int_arg("season")
        if season is None:
            return jsonify({"error": "season must be a positive integer start-year"}), 400

    cursor, pending_retries, cursor_error = _cursor_arg()
    if cursor_error:
        return jsonify({"error": cursor_error}), 400
    batch_size = _batch_size_arg()

    try:
        # Keyset-page a capped set from every source before any stale aggregate.
        # The merged input to a rebuild is therefore at most 6N ids; stale scope
        # evaluates clocks only for that bounded candidate page. One extra id is
        # a bounded lookahead used to determine whether another page exists;
        # rebuild requests never run a platform-wide remainder count.
        scan_limit = batch_size + 1
        scan_candidates = _candidate_player_ids(
            season=season,
            after=cursor,
            per_source_limit=scan_limit,
        )
        scanned_window = _page_ids(scan_candidates, cursor, scan_limit)
        has_more = len(scanned_window) > batch_size
        scanned_ids = scanned_window[:batch_size]
        player_ids = (
            _page_ids(_stale_player_ids(tuple(scanned_ids)), cursor, batch_size)
            if scope == "stale" and scanned_ids
            else ([] if scope == "stale" else scanned_ids)
        )

        processed = 0
        failures = 0
        for player_api_id in player_ids:
            try:
                with db.session.begin_nested():
                    season_rollup_service.refresh_player(
                        player_api_id,
                        season=season if scope == "season" else None,
                        session=db.session,
                    )
                processed += 1
            except Exception:
                failures += 1
                logger.exception("season-rollup %s rebuild failed for player=%s", scope, player_api_id)
        db.session.commit()

        last_scanned = scanned_ids[-1] if scanned_ids else None
        retry_count = pending_retries + failures
        remaining = retry_count + int(has_more)
        if has_more and last_scanned is not None:
            next_cursor = f"{last_scanned}:r{retry_count}" if retry_count else last_scanned
        elif retry_count:
            next_cursor = 0
        elif scope == "stale" and not scanned_ids and cursor:
            # A caller can resume with an obsolete/high cursor. One bounded wrap
            # makes the operation restartable without a global stale scan; a
            # normal server-issued terminal page never reaches this branch.
            remaining = 1
            next_cursor = 0
        else:
            next_cursor = None

        return jsonify({"processed": processed, "remaining": remaining, "cursor": next_cursor})
    except Exception as exc:
        db.session.rollback()
        logger.exception("season-rollup %s rebuild failed", scope)
        return jsonify(_safe_error_payload(exc, "Failed to rebuild season rollup")), 500


@season_rollup_bp.route("/admin/season-rollup/status", methods=["GET"])
@require_api_key
def admin_season_rollup_status():
    """Return the cheap aggregate rows-behind gauge."""
    try:
        total_totals_rows, last_computed_at = db.session.query(
            func.count(PlayerSeasonTotal.id),
            func.max(PlayerSeasonTotal.computed_at),
        ).one()
        stale_players = _count_ids(_stale_player_ids())
        source_counts = (
            db.session.query(PlayerSeasonCell.source, func.count(PlayerSeasonCell.id))
            .group_by(PlayerSeasonCell.source)
            .all()
        )
        return jsonify(
            {
                "total_totals_rows": int(total_totals_rows or 0),
                "stale_players": stale_players,
                "last_computed_at": last_computed_at.isoformat() if last_computed_at else None,
                "by_source_cells": {source: int(count) for source, count in source_counts},
            }
        )
    except Exception as exc:
        logger.exception("season-rollup status failed")
        return jsonify(_safe_error_payload(exc, "Failed to read season rollup status")), 500
