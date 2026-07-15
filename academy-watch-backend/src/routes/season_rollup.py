"""Admin operations for the season-rollup read surface.

Both endpoints are pure database operations. Rebuilds are keyset-paged by
``player_api_id`` and delegate every derived-row write to the public
``season_rollup_service.refresh_player`` API.

``GET /status`` defaults to a CHEAP rows-behind gauge whose only per-source cost is
one index-served ``MAX`` per timed clock: ``PlayerJourneyEntry.stats_synced_at``
(ix_pje_stats_synced_at), ``AcademyPlayerSeasonStats.updated_at``
(ix_apss_updated_at), ``PlayerShadowStats.updated_at`` (ix_pss_updated_at) and
``PlayerSeasonCell.synced_at`` (ix_psc_synced_at) — sea02/sea03 give every one of
those columns a b-tree so each ``MAX`` is an ORDER BY … LIMIT 1 lookup, not a seq
scan. Those four are compared against the totals' newest ``computed_at``, which
rides along the single ``count(id), max(computed_at)`` pass over
``player_season_totals`` (the smallest rollup table, already scanned for the
``total_totals_rows`` count) — so the default is four index lookups plus one
bounded single-table scan, no joins and no per-grain set difference. Everything
genuinely expensive is behind ``?exact=1``: the exact per-player stale count (a
full multi-table aggregation) and the ``by_source_cells`` per-source breakdown (a
full group-by over the largest table, ``player_season_cells``). ``?exact=1`` also
powers occasional reconciliation and the paged ``scope=stale`` rebuild (which
evaluates clocks only for its bounded candidate page). Fixture rows carry no clock,
so the cheap gauge cannot see a fixture-missing-cell; ``?exact=1`` and the
``scope=stale`` sweep are the reconciliation paths for that blind spot, and
``scope=all`` is the repair fallback for legacy/manual journey rows with a null
``stats_synced_at``.

Deleting a timed source row can leave its surviving cell/total pair looking
fresh when their clocks are equal, so neither ``?exact=1`` nor ``scope=stale``
can see that deletion. Use ``scope=all`` to repair it.
"""

import logging
from datetime import UTC

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
    ``(player, season, level_group)`` for which no fixture-derived cell exists.
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

    fixture_name = func.lower(func.coalesce(Fixture.competition_name, literal("")))
    fixture_level = case(
        (
            or_(*(fixture_name.contains(token, autoescape=True) for token in season_rollup_service._YOUTH_COMP_TOKENS)),
            literal(season_rollup_service.LEVEL_YOUTH),
        ),
        else_=literal(season_rollup_service.LEVEL_SENIOR),
    )
    fixture_rows_query = (
        select(
            FixturePlayerStats.player_api_id.label("player_api_id"),
            Fixture.season.label("season"),
            fixture_level.label("level_group"),
        )
        .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
        .where(
            or_(
                _has_fixture_stats(),
                _had_source_cell(
                    FixturePlayerStats.player_api_id,
                    Fixture.season,
                    "fixtures",
                    fixture_level,
                ),
            )
        )
    )
    fixture_cell_keys_query = select(
        PlayerSeasonCell.player_api_id,
        PlayerSeasonCell.season,
        PlayerSeasonCell.level_group,
    ).where(PlayerSeasonCell.source == "fixtures")
    if player_ids is not None:
        fixture_rows_query = fixture_rows_query.where(FixturePlayerStats.player_api_id.in_(player_ids))
        fixture_cell_keys_query = fixture_cell_keys_query.where(PlayerSeasonCell.player_api_id.in_(player_ids))
    fixture_rows = fixture_rows_query.subquery()
    fixture_keys = (
        select(fixture_rows.c.player_api_id, fixture_rows.c.season, fixture_rows.c.level_group)
        .group_by(fixture_rows.c.player_api_id, fixture_rows.c.season, fixture_rows.c.level_group)
        .subquery()
    )
    fixture_cell_keys = fixture_cell_keys_query.group_by(
        PlayerSeasonCell.player_api_id,
        PlayerSeasonCell.season,
        PlayerSeasonCell.level_group,
    ).subquery()
    fixture_missing_cell = (
        select(fixture_keys.c.player_api_id)
        .select_from(
            fixture_keys.outerjoin(
                fixture_cell_keys,
                and_(
                    fixture_cell_keys.c.player_api_id == fixture_keys.c.player_api_id,
                    fixture_cell_keys.c.season == fixture_keys.c.season,
                    fixture_cell_keys.c.level_group == fixture_keys.c.level_group,
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


def _as_utc(value):
    """Order naive (APSS/shadow) and aware (PJE/cell) clocks together as UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _max_source_change():
    """Newest mutation across the timed sources — the cheap freshness clock.

    Each source contributes ONE ``MAX`` and each of the four clock columns carries
    a single-column b-tree (``stats_synced_at``/``updated_at``/``synced_at`` via
    sea01+sea03/sea02), so PostgreSQL serves every ``MAX`` as an ORDER BY … LIMIT 1
    index lookup — no seq scan, no join, no per-grain group-by — and this stays
    sub-second on the prod box. Fixture rows carry no clock, so it deliberately
    cannot see a fixture-missing-cell; ``?exact=1`` or a ``scope=stale`` sweep
    reconciles that blind spot.
    """
    clocks = [
        db.session.query(func.max(PlayerJourneyEntry.stats_synced_at)).scalar(),
        db.session.query(func.max(AcademyPlayerSeasonStats.updated_at)).scalar(),
        db.session.query(func.max(PlayerShadowStats.updated_at)).scalar(),
        db.session.query(func.max(PlayerSeasonCell.synced_at)).scalar(),
    ]
    present = [clock for clock in clocks if clock is not None]
    return max(present, key=_as_utc) if present else None


def _batch_size_arg() -> int:
    batch_size = request.args.get("batch_size", _DEFAULT_BATCH_SIZE, type=int)
    if not isinstance(batch_size, int) or batch_size < 1:
        batch_size = _DEFAULT_BATCH_SIZE
    return min(batch_size, _MAX_BATCH_SIZE)


def _cursor_arg() -> tuple[int | None, str | None]:
    """Parse the keyset cursor: the last player_api_id scanned by the sweep.

    The cursor only ever moves forward (the max id of the previous page), so a
    sweep always terminates: once no candidate id remains above it, the endpoint
    returns ``cursor=null``. A player whose per-row rebuild raises is reported in
    ``failed`` and retried out-of-band via ``scope=player`` — a failure never
    rewinds the cursor, so there is no poison-row livelock.
    """
    raw_cursor = request.args.get("cursor")
    if raw_cursor is None or raw_cursor == "":
        return 0, None
    try:
        cursor = int(raw_cursor)
    except (TypeError, ValueError):
        return None, "cursor must be a non-negative integer player_api_id"
    if cursor < 0:
        return None, "cursor must be a non-negative integer player_api_id"
    return cursor, None


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

    ``cursor`` is the last player_api_id scanned and is null once the sweep has
    converged. It only moves forward, so the sweep always terminates: a player
    whose per-row rebuild raises is listed in ``failed`` (retry it out-of-band
    with ``scope=player``) and never rewinds the cursor. ``remaining`` is a
    bounded 0/1 hint — one means the capped lookahead saw another page — never a
    platform-wide count. Season sweeps are bounded like stale/all so every
    request stays safe for the production container.
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
            return jsonify({"processed": 1, "failed": [], "remaining": 0, "cursor": None})
        except Exception as exc:
            db.session.rollback()
            logger.exception("season-rollup player rebuild failed for player=%s", player_api_id)
            return jsonify(_safe_error_payload(exc, "Failed to rebuild season rollup")), 500

    season = None
    if scope == "season":
        season = _positive_int_arg("season")
        if season is None:
            return jsonify({"error": "season must be a positive integer start-year"}), 400

    cursor, cursor_error = _cursor_arg()
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
        failed: list[int] = []
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
                failed.append(player_api_id)
                logger.exception("season-rollup %s rebuild failed for player=%s", scope, player_api_id)
        db.session.commit()

        # Forward-only cursor: null once no candidate id remains above the last
        # scanned page, so every sweep terminates even when a poison row keeps
        # failing. ``remaining`` is a bounded 0/1 "another page exists" hint, not
        # a platform-wide count; ``failed`` carries the ids to retry via
        # ``scope=player``.
        last_scanned = scanned_ids[-1] if scanned_ids else None
        next_cursor = last_scanned if has_more else None
        remaining = int(has_more)

        return jsonify({"processed": processed, "failed": failed, "remaining": remaining, "cursor": next_cursor})
    except Exception as exc:
        db.session.rollback()
        logger.exception("season-rollup %s rebuild failed", scope)
        return jsonify(_safe_error_payload(exc, "Failed to rebuild season rollup")), 500


@season_rollup_bp.route("/admin/season-rollup/status", methods=["GET"])
@require_api_key
def admin_season_rollup_status():
    """Return the rows-behind gauge.

    Default = the CHEAP gauge: ``behind`` compares the newest timed-source clock
    (four index-served ``MAX`` lookups — sea02/sea03 index every clock column)
    against the totals' own newest ``computed_at``, which rides along the single
    ``count(id), max(computed_at)`` pass over the small ``player_season_totals``
    table (already needed for ``total_totals_rows``) — so the default is four index
    lookups plus one bounded single-table scan, no joins and no per-grain set
    difference. Pass ``?exact=1`` for the reconciliation extras that DO scan the
    largest table: the exact per-player stale count (``stale_players``, a full
    multi-table aggregation) and the ``by_source_cells`` per-source cell breakdown
    (a full ``player_season_cells`` group-by).
    """
    exact = (request.args.get("exact") or "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        total_totals_rows, last_computed_at = db.session.query(
            func.count(PlayerSeasonTotal.id),
            func.max(PlayerSeasonTotal.computed_at),
        ).one()
        last_source_change_at = _max_source_change()
        behind = last_source_change_at is not None and (
            last_computed_at is None or _as_utc(last_source_change_at) > _as_utc(last_computed_at)
        )
        body = {
            "total_totals_rows": int(total_totals_rows or 0),
            "behind": behind,
            "last_computed_at": last_computed_at.isoformat() if last_computed_at else None,
            "last_source_change_at": last_source_change_at.isoformat() if last_source_change_at else None,
        }
        if exact:
            # Both scan the largest rollup table, so they stay off the pollable
            # default path: the per-source cell breakdown (full group-by) and the
            # exact per-player stale count (full multi-table aggregation).
            source_counts = (
                db.session.query(PlayerSeasonCell.source, func.count(PlayerSeasonCell.id))
                .group_by(PlayerSeasonCell.source)
                .all()
            )
            body["by_source_cells"] = {source: int(count) for source, count in source_counts}
            body["stale_players"] = _count_ids(_stale_player_ids())
        return jsonify(body)
    except Exception as exc:
        logger.exception("season-rollup status failed")
        return jsonify(_safe_error_payload(exc, "Failed to read season rollup status")), 500
