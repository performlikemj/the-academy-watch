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
            raise RuntimeError("derived data changed after rebuild; reconstruct from current source facts instead")
        for model in MODELS:
            session.query(model).filter_by(player_api_id=player_id).delete(synchronize_session=False)
            for values in before[model.__tablename__]:
                values = {k: datetime.fromisoformat(v) if k in CLOCKS and v else v for k, v in values.items()}
                session.add(model(**values))
        session.commit()
    return len(originals)


def run(session, *, dry_run, limit, after, delay, checkpoint=None, undo=None):
    started = perf_counter()
    result = {"players_scanned": 0, "players_changed": 0, "seasons_changed": 0, "samples": []}
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
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--after", type=int, default=-(2**31))
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--checkpoint", type=Path)
    parser.add_argument("--undo", type=Path)
    parser.add_argument("--rollback", type=Path)
    args = parser.parse_args(argv)
    if any(os.getenv(k) for k in ("CONTAINER_APP_NAME", "CONTAINER_APP_REPLICA_NAME", "CONTAINER_APP_REVISION")):
        parser.error("run from an off-container checkout")
    if args.limit < 1 or not 0.05 <= args.delay <= 60:
        parser.error("limit must be positive; delay must be between 0.05 and 60 seconds")
    uri = os.getenv("PC2_DATABASE_URL", "")
    url = make_url(uri) if uri else None
    if url is None or url.drivername != "postgresql+psycopg":
        parser.error("set PC2_DATABASE_URL explicitly with postgresql+psycopg://")
    if url.host and url.host not in ("localhost", "127.0.0.1", "::1") and not url.host.endswith(".pooler.supabase.com"):
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
            result = {"players_restored": restore(db.session, args.rollback)}
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
