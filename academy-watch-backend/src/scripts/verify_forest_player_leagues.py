"""Verify radar league resolution for every active TrackedPlayer at a parent club.

For each player, prints what `resolve_player_league` returns and flags rows
that look suspicious — e.g. a loanee at a sub-Premier-League club whose radar
would still compare against Premier League peers.

Usage:
    ../.loan/bin/python -m src.scripts.verify_forest_player_leagues
    ../.loan/bin/python -m src.scripts.verify_forest_player_leagues --team "Manchester United"
    ../.loan/bin/python -m src.scripts.verify_forest_player_leagues --team-api-id 65

Read-only. Safe to run against production. Hits API-Football for any team it
hasn't already resolved this session.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import dotenv
from flask import Flask
from sqlalchemy.engine.url import URL, make_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.league import db, Team, League  # noqa: E402
from src.models.tracked_player import TrackedPlayer  # noqa: E402
from src.models.journey import PlayerJourney  # noqa: E402,F401  # mapper init
from src.services.radar_stats_service import (  # noqa: E402
    resolve_player_league,
    _team_league_from_api,
)

dotenv.load_dotenv(dotenv.find_dotenv())


def _env_value(key: str) -> str | None:
    raw = os.getenv(key)
    if raw is None:
        return None
    value = raw.strip()
    return value or None


def _build_db_uri() -> str:
    raw = _env_value("SQLALCHEMY_DATABASE_URI")
    if raw:
        candidate = raw.strip().strip('"').strip("'")
        try:
            make_url(candidate)
            return candidate
        except Exception:
            pass

    port_raw = _env_value("DB_PORT") or ""
    port_value = None
    if port_raw:
        try:
            port_value = int(port_raw)
        except ValueError:
            port_value = None
    url = URL.create(
        drivername="postgresql+psycopg",
        username=_env_value("DB_USER"),
        password=_env_value("DB_PASSWORD"),
        host=_env_value("DB_HOST"),
        port=port_value,
        database=_env_value("DB_NAME"),
        query={"sslmode": _env_value("DB_SSLMODE") or "require"},
    )
    return url.render_as_string(hide_password=False)


def _make_app() -> Flask:
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = _build_db_uri()
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    return app


def _resolve_team(team_name: str | None, team_api_id: int | None) -> Team:
    query = Team.query
    if team_api_id is not None:
        team = query.filter_by(team_id=team_api_id).order_by(Team.season.desc()).first()
        if not team:
            raise SystemExit(f"No Team row for team_api_id={team_api_id}")
        return team
    name = team_name or "Nottingham Forest"
    team = query.filter(Team.name.ilike(name)).order_by(Team.season.desc()).first()
    if not team:
        team = query.filter(Team.name.ilike(f"%{name}%")).order_by(Team.season.desc()).first()
    if not team:
        raise SystemExit(f"No Team row matching name ILIKE '%{name}%'")
    return team


def _local_team_league(team_api_id: int | None) -> tuple[int | None, str | None]:
    """Return (league_api_id, league_name) from the local teams/leagues join."""
    if not team_api_id:
        return None, None
    team = Team.query.filter_by(team_id=team_api_id).first()
    if not team or not team.league_id:
        return None, None
    league = League.query.filter_by(id=team.league_id).first()
    if not league:
        return None, None
    return league.league_id, league.name


def _verdict(
    parent_api_id: int,
    parent_name: str,
    status: str,
    current_api_id: int | None,
    current_name: str | None,
    resolved: tuple[int, str] | None,
) -> str:
    """Heuristic flag for rows that look wrong at a glance."""
    if resolved is None:
        return "NO_LEAGUE"
    _, league_name = resolved
    league_lower = league_name.lower()

    # If the player is on loan/sold/released and we're returning the parent's
    # likely league (Premier League for Forest), that's the bug we just fixed.
    if status in ("on_loan", "sold", "released") and current_api_id and current_api_id != parent_api_id:
        if "premier league" in league_lower and "premier league 2" not in league_lower:
            return "SUSPECT"

    # If "current club" is None or matches the parent club, returning the
    # parent league is correct.
    return "OK"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--team", default="Nottingham Forest",
                    help="Parent club name (ILIKE match). Default: Nottingham Forest")
    ap.add_argument("--team-api-id", type=int, default=None,
                    help="Parent club API-Football ID (overrides --team if set)")
    ap.add_argument("--season", type=int, default=None,
                    help="Season for league resolution. Defaults to current Jul-Jun cycle.")
    ap.add_argument("--only-suspect", action="store_true",
                    help="Only print rows flagged SUSPECT or NO_LEAGUE.")
    args = ap.parse_args()

    app = _make_app()
    with app.app_context():
        team = _resolve_team(args.team, args.team_api_id)
        print("=" * 100)
        print(
            f"VERIFY radar league resolution for: {team.name}  "
            f"(Team.id={team.id}, team_api_id={team.team_id})"
        )
        if args.season:
            print(f"Season: {args.season}")
        print("=" * 100)

        tracked = (
            TrackedPlayer.query
            .filter(TrackedPlayer.team_id == team.id, TrackedPlayer.is_active.is_(True))
            .order_by(TrackedPlayer.status, TrackedPlayer.player_name)
            .all()
        )
        print(f"\nActive TrackedPlayer rows: {len(tracked)}\n")

        counts = {"OK": 0, "SUSPECT": 0, "NO_LEAGUE": 0}
        suspects: list[tuple[TrackedPlayer, tuple[int, str] | None, tuple[int | None, str | None]]] = []

        header = (
            f"  {'flag':<9} {'status':<11} {'name':<26} {'current club':<26} "
            f"{'resolved league':<26} {'local-DB league':<26}"
        )
        print(header)
        print("  " + "-" * (len(header) - 2))

        for tp in tracked:
            resolved = resolve_player_league(tp.player_api_id, season=args.season)
            local = _local_team_league(tp.current_club_api_id)
            verdict = _verdict(
                team.team_id,
                team.name,
                tp.status or "",
                tp.current_club_api_id,
                tp.current_club_name,
                resolved,
            )
            counts[verdict] += 1

            if args.only_suspect and verdict == "OK":
                continue

            current_label = f"{tp.current_club_name or '-'}"[:25]
            resolved_label = f"{resolved[1]} ({resolved[0]})" if resolved else "-"
            local_label = f"{local[1]} ({local[0]})" if local[0] else "-"

            line = (
                f"  [{verdict:<7}] {tp.status or '?':<11} "
                f"{(tp.player_name or '?')[:25]:<26} "
                f"{current_label:<26} "
                f"{resolved_label[:25]:<26} "
                f"{local_label[:25]:<26}"
            )
            print(line)

            if verdict in ("SUSPECT", "NO_LEAGUE"):
                suspects.append((tp, resolved, local))

        print("\nCounts:")
        for k, v in counts.items():
            print(f"  {k:<10} {v}")

        if suspects:
            print(f"\nDetail on {len(suspects)} flagged row(s):")
            for tp, resolved, local in suspects:
                print(
                    f"  - id={tp.id} api={tp.player_api_id} {tp.player_name}  "
                    f"status={tp.status}  pinned_parent={tp.pinned_parent}"
                )
                print(
                    f"      current_club_api_id={tp.current_club_api_id}  "
                    f"current_club_db_id={tp.current_club_db_id}  "
                    f"current_club_name={tp.current_club_name!r}"
                )
                print(f"      resolve_player_league → {resolved}")
                print(f"      local teams.league_id → {local}")
                if tp.current_club_api_id:
                    api_lookup = _team_league_from_api(
                        tp.current_club_api_id, args.season or _default_season()
                    )
                    print(f"      API-Football says   → {api_lookup}")

        print("\nDONE")


def _default_season() -> int:
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 7 else now.year - 1


if __name__ == "__main__":
    main()
