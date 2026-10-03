#!/usr/bin/env python3
"""OFF-container PC2 reported rollup rebuild; no integrations or app startup.

PC2_DATABASE_URL must explicitly point at PostgreSQL through psycopg v3. Hosted
operations use the IPv4 pooler. Never invoke this from the production web image.
Each player is one transaction; a durable checkpoint follows each commit. The
append-only undo file is fsynced BEFORE the commit it protects. Dry-run does
only SELECTs. Re-running from the start is safe and skips identical derived data.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from time import perf_counter, sleep

from flask import Flask
from sqlalchemy import select, union
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.models.league import db
from src.models.player_match_entry import PlayerMatchEntry
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.services.season_rollup_service import _lock_player_refresh, build_player_rollup, refresh_player

MODELS = (PlayerSeasonCell, PlayerSeasonTotal)
CLOCKS = {"synced_at", "computed_at"}


def snapshot(session, player_id):
    return {
        model.__tablename__: [
            {column.name: getattr(row, column.name) for column in model.__table__.columns}
            for row in session.query(model).filter_by(player_api_id=player_id).order_by(model.id)
        ]
        for model in MODELS
    }


def comparable(rows):
    return sorted(
        [
            json.dumps(
                {
                    k: float(v) if k == "avg_rating" and v is not None else v
                    for k, v in row.items()
                    if k not in CLOCKS | {"id", "_rating_wsum", "_rating_min"}
                },
                sort_keys=True,
                default=lambda value: float(value) if isinstance(value, Decimal) else str(value),
            )
            for row in rows
        ]
    )


def candidate_ids(session, after, limit):
    candidates = union(
        select(PlayerMatchEntry.player_api_id),
        select(PlayerSeasonTotal.player_api_id).where(
            PlayerSeasonTotal.primary_source.in_(("club", "user", "matches"))
        ),
        select(PlayerSeasonCell.player_api_id).where(PlayerSeasonCell.source.in_(("club", "user"))),
    ).subquery()
    return list(
        session.execute(
            select(candidates.c.player_api_id)
            .where(candidates.c.player_api_id > after)
            .order_by(candidates.c.player_api_id)
            .limit(limit)
        ).scalars()
    )


def append_undo(path, payload):
    with path.open("a") as out:
        out.write(json.dumps(payload, default=str) + "\n")
        out.flush()
        os.fsync(out.fileno())


def restore(session, path):
    # Earliest snapshot wins if a process died after saving undo but before its
    # checkpoint. This is safe across retries and multiple rebuild invocations.
    originals = {}
    for line in path.read_text().splitlines():
        record = json.loads(line)
        originals.setdefault(record["player_id"], record)
    result = {"players_restored": 0, "players_skipped": []}
    for player_id, record in originals.items():
        _lock_player_refresh(session, player_id)
        before = record["before"]
        current = snapshot(session, player_id)
        if any(
            comparable(current[model.__tablename__])
            not in (comparable(before[model.__tablename__]), comparable(record["after"][model.__tablename__]))
            for model in MODELS
        ):
            session.rollback()
            result["players_skipped"].append(player_id)
            continue
        for model in MODELS:
            session.query(model).filter_by(player_api_id=player_id).delete(synchronize_session=False)
            for values in before[model.__tablename__]:
                values = {k: datetime.fromisoformat(v) if k in CLOCKS and v else v for k, v in values.items()}
                session.add(model(**values))
        session.commit()
        result["players_restored"] += 1
    return result


def run(session, *, dry_run, limit, after, delay, checkpoint=None, undo=None):
    started = perf_counter()
    result = {
        "players_scanned": 0,
        "players_changed": 0,
        "seasons_changed": 0,
        "samples": [],
        "players_figures_changed": 0,
        "seasons_figures_changed": 0,
        "seasons_losing_totals": 0,
        "losses": [],
    }
    for player_id in candidate_ids(session, after, limit):
        if not dry_run:
            _lock_player_refresh(session, player_id)
        before = snapshot(session, player_id)
        cells, totals = build_player_rollup(player_id, session=session)
        changed = any(
            comparable(before[model.__tablename__]) != comparable(rows)
            for model, rows in zip(MODELS, (cells, totals), strict=True)
        )
        result["players_scanned"] += 1
        if changed:
            result["players_changed"] += 1
            changed_seasons = sorted(
                {
                    row["season"]
                    for model, rows in zip(MODELS, (cells, totals), strict=True)
                    for row in before[model.__tablename__] + rows
                    if comparable([r for r in before[model.__tablename__] if r["season"] == row["season"]])
                    != comparable([r for r in rows if r["season"] == row["season"]])
                }
            )
            result["seasons_changed"] += len(changed_seasons)
            old = {
                row["season"]: row for row in before[PlayerSeasonTotal.__tablename__] if row["level_group"] == "senior"
            }
            new = {row["season"]: row for row in totals if row["level_group"] == "senior"}
            stat_keys = ("appearances", "minutes", "goals", "assists", "yellows", "reds", "saves", "goals_conceded")
            figure_changes = 0
            for season in sorted(set(old) | set(new)):
                before_total, after_total = old.get(season), new.get(season)
                before_figures = {k: before_total.get(k) for k in stat_keys} if before_total else None
                after_figures = {k: after_total.get(k) for k in stat_keys} if after_total else None
                if before_figures != after_figures:
                    figure_changes += 1
                if before_total and (
                    not after_total
                    or (any(before_total.get(k) for k in stat_keys) and not any(after_total.get(k) for k in stat_keys))
                ):
                    result["seasons_losing_totals"] += 1
                    result["losses"].append(
                        {
                            "player_id": player_id,
                            "season": season,
                            "before": before_figures,
                            "after": after_figures,
                            "before_source": before_total["primary_source"],
                        }
                    )
            result["seasons_figures_changed"] += figure_changes
            result["players_figures_changed"] += int(figure_changes > 0)
            for season in changed_seasons:
                if len(result["samples"]) >= 5:
                    break

                def figures(row):
                    return (
                        {k: row.get(k) for k in ("appearances", "minutes", "goals", "assists", "primary_source")}
                        if row
                        else None
                    )

                result["samples"].append(
                    {
                        "player_id": player_id,
                        "season": season,
                        "before": figures(old.get(season)),
                        "after": figures(new.get(season)),
                    }
                )
            if not dry_run:
                append_undo(
                    undo,
                    {
                        "player_id": player_id,
                        "before": before,
                        "after": {PlayerSeasonCell.__tablename__: cells, PlayerSeasonTotal.__tablename__: totals},
                    },
                )
                refresh_player(player_id, session=session)
        if dry_run:
            session.rollback()
        else:
            session.commit()
            temporary = checkpoint.with_suffix(".tmp")
            temporary.write_text(json.dumps({"after": player_id}))
            temporary.replace(checkpoint)
        result["after"] = player_id
        sleep(delay)
    result["runtime_seconds"] = round(perf_counter() - started, 3)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--after", type=int, default=-(2**31))
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--undo", type=Path)
    mode.add_argument("--rollback", type=Path)
    args = parser.parse_args(argv)
    if any(os.getenv(k) for k in ("CONTAINER_APP_NAME", "CONTAINER_APP_REPLICA_NAME", "CONTAINER_APP_REVISION")):
        parser.error("run from an off-container checkout")
    if args.limit < 1 or not 0.05 <= args.delay <= 60:
        parser.error("limit must be positive; delay must be between 0.05 and 60 seconds")
    uri = os.getenv("PC2_DATABASE_URL", "")
    url = make_url(uri) if uri else None
    if url is None or url.drivername != "postgresql+psycopg":
        parser.error("set PC2_DATABASE_URL explicitly with postgresql+psycopg://")
    # A libpq service/environment target can replace the URL authority. Keep
    # hostless local rehearsals only when no implicit target is present.
    if "service" in url.query or any(os.getenv(k) for k in ("PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE")):
        parser.error("libpq environment/service targets are not allowed; use only PC2_DATABASE_URL")
    # libpq query hosts override the authority, including socket-style URLs.
    hosts = [url.host] if url.host else []
    for value in url.normalized_query.get("host", ()):
        hosts.extend(value.split(","))
    if url.query.get("hostaddr"):
        parser.error("hostaddr overrides are not allowed; use the IPv4 pooler hostname")
    if any(
        host not in ("localhost", "127.0.0.1", "::1") and not host.endswith(".pooler.supabase.com") for host in hosts
    ):
        parser.error("hosted databases must use the IPv4 pooler")
    if not args.dry_run and not args.rollback and (args.checkpoint is None or args.undo is None):
        parser.error("writes require --checkpoint and --undo paths")
    application = Flask(__name__)
    application.config.update(
        SQLALCHEMY_DATABASE_URI=uri,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
    )
    db.init_app(application)
    with application.app_context():
        if args.rollback:
            result = restore(db.session, args.rollback)
        else:
            if args.checkpoint and args.checkpoint.exists() and not args.dry_run:
                args.after = max(args.after, json.loads(args.checkpoint.read_text())["after"])
            result = run(
                db.session,
                dry_run=args.dry_run,
                limit=args.limit,
                after=args.after,
                delay=args.delay,
                checkpoint=args.checkpoint,
                undo=args.undo,
            )
        print(json.dumps(result, indent=2))
    return 2 if result.get("players_skipped") else 0


if __name__ == "__main__":
    raise SystemExit(main())
