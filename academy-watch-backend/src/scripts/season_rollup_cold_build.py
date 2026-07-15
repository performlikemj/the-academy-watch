#!/usr/bin/env python3
"""Cold-build the season-rollup read surface from an off-container checkout.

This is a pure-database runner: it discovers the same player population as the
admin rebuild endpoint and delegates every write to
``season_rollup_service.refresh_player``. It must be run from a local checkout
or dedicated job connected through the Supabase pooler, never in the small
production web container.

Usage (from ``academy-watch-backend``)::

    python -m src.scripts.season_rollup_cold_build --players 303010,12345
    python -m src.scripts.season_rollup_cold_build --all --season 2025
    python -m src.scripts.season_rollup_cold_build --all --after 303010 --limit 500
    python -m src.scripts.season_rollup_cold_build --all --dry-run

Database configuration comes from the normal application ``DB_*`` environment
variables. No API-Football client is used.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from time import perf_counter

import dotenv
from flask import Flask
from sqlalchemy import func, inspect, select
from sqlalchemy.engine import URL

# Support both ``python -m src.scripts...`` and direct-file invocation.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.league import db  # noqa: E402
from src.routes.season_rollup import _candidate_player_ids  # noqa: E402
from src.services import season_rollup_service  # noqa: E402

logger = logging.getLogger(__name__)

_DEFAULT_BATCH_SIZE = 50
_MAX_BATCH_SIZE = 200
_CONTAINER_APP_ENV_KEYS = (
    "CONTAINER_APP_NAME",
    "CONTAINER_APP_REPLICA_NAME",
    "CONTAINER_APP_REVISION",
)
_REQUIRED_TABLES = {
    "academy_player_season_stats",
    "fixture_player_stats",
    "fixtures",
    "player_journey_entries",
    "player_journeys",
    "player_season_cells",
    "player_season_totals",
    "player_shadow_stats",
}


def _positive_int(raw: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _non_negative_int(raw: str) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError("must be a non-negative integer player_api_id") from exc
    if value < 0:
        raise argparse.ArgumentTypeError("must be a non-negative integer player_api_id")
    return value


def _player_id_list(raw: str) -> tuple[int, ...]:
    parts = [part.strip() for part in raw.split(",")]
    if not parts or any(not part for part in parts):
        raise argparse.ArgumentTypeError("must be a comma-separated list of positive player_api_ids")
    try:
        player_ids = {int(part) for part in parts}
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a comma-separated list of positive player_api_ids") from exc
    if any(player_id < 1 for player_id in player_ids):
        raise argparse.ArgumentTypeError("player_api_ids must be positive integers")
    return tuple(sorted(player_ids))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Cold-build player season cells/totals off-container using only the configured database.",
    )
    population = parser.add_mutually_exclusive_group(required=True)
    population.add_argument(
        "--players",
        type=_player_id_list,
        metavar="ID,ID",
        help="explicit comma-separated player_api_ids (pilot mode)",
    )
    population.add_argument(
        "--all",
        dest="all_players",
        action="store_true",
        help="discover the full rebuild candidate population, including orphan derived rows",
    )
    parser.add_argument(
        "--season",
        type=_positive_int,
        help="optional season start-year restriction (for example, 2025 means 2025-26)",
    )
    parser.add_argument(
        "--after",
        type=_non_negative_int,
        default=0,
        metavar="PLAYER_API_ID",
        help="strict keyset resume cursor (default: 0)",
    )
    parser.add_argument("--limit", type=_positive_int, help="stop after attempting this many players")
    parser.add_argument(
        "--batch-size",
        type=_positive_int,
        default=_DEFAULT_BATCH_SIZE,
        metavar="N",
        help=f"players per commit (default: {_DEFAULT_BATCH_SIZE}, capped at {_MAX_BATCH_SIZE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print candidate count and first/last ids without writing",
    )
    return parser


def _env_value(key: str, *, allow_inline_comment: bool = False) -> str | None:
    raw = os.getenv(key)
    if raw is None:
        return None
    value = raw.strip()
    if allow_inline_comment and "#" in value:
        for index, character in enumerate(value):
            if character == "#" and (index == 0 or value[index - 1].isspace()):
                value = value[:index].rstrip()
                break
    return value or None


def _build_db_uri_from_components() -> str:
    """Mirror ``src.main``'s psycopg-v3 ``DB_*`` URL construction."""
    port_raw = _env_value("DB_PORT", allow_inline_comment=True) or ""
    port_value = None
    if port_raw:
        try:
            port_value = int(port_raw)
        except ValueError:
            logger.warning("DB_PORT value %r is invalid; ignoring port", port_raw)
    url = URL.create(
        drivername="postgresql+psycopg",
        username=_env_value("DB_USER"),
        password=_env_value("DB_PASSWORD"),
        host=_env_value("DB_HOST", allow_inline_comment=True),
        port=port_value,
        database=_env_value("DB_NAME", allow_inline_comment=True),
        query={"sslmode": _env_value("DB_SSLMODE") or "require"},
    )
    return url.render_as_string(hide_password=False)


def _assert_off_container() -> None:
    if any(_env_value(key) for key in _CONTAINER_APP_ENV_KEYS):
        raise RuntimeError(
            "refusing to run inside Azure Container Apps; run this bulk build from an off-container checkout"
        )


def get_app() -> Flask:
    """Build a database-only app without importing integration-bearing routes."""
    dotenv.load_dotenv(dotenv.find_dotenv())
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = _build_db_uri_from_components()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }
    db.init_app(app)

    return app


def _validate_setup() -> None:
    existing_tables = set(inspect(db.session.get_bind()).get_table_names())
    missing_tables = sorted(_REQUIRED_TABLES - existing_tables)
    if missing_tables:
        raise RuntimeError(f"database is missing required season-rollup tables: {', '.join(missing_tables)}")


def _ordered_candidate_select(
    *,
    season: int | None,
    after: int,
    limit: int | None = None,
    per_source_limit: int | None = None,
):
    candidates = _candidate_player_ids(
        season=season,
        after=after,
        per_source_limit=per_source_limit,
    ).subquery()
    statement = (
        select(candidates.c.player_api_id)
        .where(candidates.c.player_api_id > after)
        .order_by(candidates.c.player_api_id)
    )
    if limit is not None:
        statement = statement.limit(limit)
    return statement


def _all_candidate_page(*, season: int | None, after: int, page_size: int) -> list[int]:
    statement = _ordered_candidate_select(
        season=season,
        after=after,
        limit=page_size,
        per_source_limit=page_size,
    )
    return list(db.session.execute(statement).scalars())


def _all_candidate_bounds(*, season: int | None, after: int, limit: int | None) -> tuple[int, int | None, int | None]:
    candidates = _candidate_player_ids(season=season, after=after).subquery()
    selected = select(candidates.c.player_api_id).where(candidates.c.player_api_id > after)
    if limit is not None:
        selected = selected.order_by(candidates.c.player_api_id).limit(limit)
        candidates = selected.subquery()

    count, first_id, last_id = db.session.execute(
        select(
            func.count(candidates.c.player_api_id),
            func.min(candidates.c.player_api_id),
            func.max(candidates.c.player_api_id),
        )
    ).one()
    return int(count or 0), first_id, last_id


def _explicit_player_ids(args: argparse.Namespace) -> list[int]:
    player_ids = [player_id for player_id in args.players if player_id > args.after]
    if args.limit is not None:
        player_ids = player_ids[: args.limit]
    return player_ids


def _print_dry_run(args: argparse.Namespace) -> None:
    if args.players is not None:
        player_ids = _explicit_player_ids(args)
        count = len(player_ids)
        first_id = player_ids[0] if player_ids else None
        last_id = player_ids[-1] if player_ids else None
    else:
        count, first_id, last_id = _all_candidate_bounds(
            season=args.season,
            after=args.after,
            limit=args.limit,
        )
    print(f"candidates={count} first_id={first_id} last_id={last_id}", flush=True)


def _process_batch(
    player_ids: list[int],
    *,
    season: int | None,
    started_at: float,
    successful: int,
    attempted: int,
    failed_ids: list[int],
) -> tuple[int, int]:
    for player_api_id in player_ids:
        attempted += 1
        try:
            with db.session.begin_nested():
                season_rollup_service.refresh_player(
                    player_api_id,
                    season=season,
                    session=db.session,
                )
            successful += 1
        except Exception:
            failed_ids.append(player_api_id)
            logger.exception(
                "season-rollup cold-build skipped player=%s season=%s",
                player_api_id,
                season,
            )

    db.session.commit()
    elapsed = perf_counter() - started_at
    average_ms = elapsed * 1000 / attempted if attempted else 0.0
    print(
        f"processed={successful} failed={len(failed_ids)} last_id={player_ids[-1]} "
        f"elapsed={elapsed:.1f}s avg_per_player={average_ms:.1f}ms",
        flush=True,
    )
    return successful, attempted


def run(args: argparse.Namespace) -> int:
    _validate_setup()
    args.batch_size = min(args.batch_size, _MAX_BATCH_SIZE)
    started_at = perf_counter()

    if args.dry_run:
        _print_dry_run(args)
        db.session.rollback()
        return 0

    successful = 0
    attempted = 0
    failed_ids: list[int] = []

    if args.players is not None:
        player_ids = _explicit_player_ids(args)
        for start in range(0, len(player_ids), args.batch_size):
            successful, attempted = _process_batch(
                player_ids[start : start + args.batch_size],
                season=args.season,
                started_at=started_at,
                successful=successful,
                attempted=attempted,
                failed_ids=failed_ids,
            )
    else:
        cursor = args.after
        remaining = args.limit
        while remaining is None or remaining > 0:
            page_size = args.batch_size if remaining is None else min(args.batch_size, remaining)
            player_ids = _all_candidate_page(
                season=args.season,
                after=cursor,
                page_size=page_size,
            )
            if not player_ids:
                db.session.rollback()
                break
            successful, attempted = _process_batch(
                player_ids,
                season=args.season,
                started_at=started_at,
                successful=successful,
                attempted=attempted,
                failed_ids=failed_ids,
            )
            cursor = player_ids[-1]
            if remaining is not None:
                remaining -= len(player_ids)

    elapsed = perf_counter() - started_at
    average_ms = elapsed * 1000 / attempted if attempted else 0.0
    print(
        f"summary processed={successful} failed={len(failed_ids)} failed_ids={failed_ids} "
        f"total_elapsed={elapsed:.1f}s avg_per_player={average_ms:.1f}ms",
        flush=True,
    )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        _assert_off_container()
        app = get_app()
        with app.app_context():
            try:
                return run(args)
            except Exception:
                db.session.rollback()
                raise
    except Exception:
        logger.exception("season-rollup cold-build fatal error")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
