"""Read-only audit of TrackedPlayer state for a parent club (default: Nottingham Forest).

Prints every is_active=True TrackedPlayer with its linked PlayerJourney freshness
and classifier inputs, so we can spot stale/incorrect rows before generating a
newsletter. Specifically highlights any player matching "%hammond%" for the
pre-demo investigation.

Usage:
    ../.loan/bin/python -m src.scripts.audit_forest_tracked_players
    ../.loan/bin/python -m src.scripts.audit_forest_tracked_players --team "Manchester United"
    ../.loan/bin/python -m src.scripts.audit_forest_tracked_players --team-api-id 65

No writes are performed. Safe to run against production.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import dotenv
from flask import Flask
from sqlalchemy.engine.url import URL, make_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.models.journey import PlayerJourney, PlayerJourneyEntry  # noqa: E402
from src.models.league import Team, db  # noqa: E402
from src.models.tracked_player import TrackedPlayer  # noqa: E402
from src.utils.academy_classifier import _get_latest_season  # noqa: E402

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


def _days_since(ts: datetime | None) -> str:
    if not ts:
        return "NEVER"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - ts
    return f"{delta.days}d"


def _fmt_bool(b) -> str:
    return "Y" if b else "n"


def _dup_counts() -> dict[int, int]:
    """Return {player_api_id: count_of_active_rows} for rows with duplicates."""
    from sqlalchemy import func

    rows = (
        db.session.query(
            TrackedPlayer.player_api_id,
            func.count(TrackedPlayer.id).label("n"),
        )
        .filter(TrackedPlayer.is_active.is_(True))
        .group_by(TrackedPlayer.player_api_id)
        .having(func.count(TrackedPlayer.id) > 1)
        .all()
    )
    return {row.player_api_id: int(row.n) for row in rows}


def _print_row(tp: TrackedPlayer, journey: PlayerJourney | None, dup_n: int) -> None:
    j_synced = _days_since(journey.last_synced_at) if journey else "NO_JOURNEY"
    j_current_id = journey.current_club_api_id if journey else None
    j_current_name = journey.current_club_name if journey else None
    j_level = journey.current_level if journey else None
    j_academy_ids = (journey.academy_club_ids if journey else None) or []

    latest_season = None
    if journey:
        try:
            latest_season = _get_latest_season(
                journey.id,
                parent_api_id=tp.team.team_id if tp.team else None,
                parent_club_name=tp.team.name if tp.team else None,
            )
        except Exception as exc:  # noqa: BLE001
            latest_season = f"ERR:{exc}"

    updated_age = _days_since(tp.updated_at)

    print(
        f"  id={tp.id:<6} api={tp.player_api_id:<8} "
        f"{(tp.player_name or '?')[:28]:<28} "
        f"status={tp.status:<10} src={tp.data_source:<14} "
        f"pinned={_fmt_bool(tp.pinned_parent)} active={_fmt_bool(tp.is_active)} "
        f"dup={dup_n if dup_n else '-'}"
    )
    print(
        f"      tp.current_club={tp.current_club_api_id}|{(tp.current_club_name or '-')[:30]:<30} "
        f"level={tp.current_level or '-':<6} updated={updated_age}"
    )
    print(
        f"      journey.last_synced={j_synced:<7} "
        f"journey.current_club={j_current_id}|{(j_current_name or '-')[:30]:<30} "
        f"level={j_level or '-':<6}"
    )
    print(f"      journey.academy_club_ids={j_academy_ids}  latest_entry_season={latest_season}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--team", default="Nottingham Forest", help="Parent club name (ILIKE match). Default: Nottingham Forest"
    )
    ap.add_argument(
        "--team-api-id", type=int, default=None, help="Parent club API-Football ID (overrides --team if set)"
    )
    ap.add_argument(
        "--highlight", default="hammond", help="Case-insensitive substring to highlight at the end. Default: hammond"
    )
    args = ap.parse_args()

    app = _make_app()
    with app.app_context():
        team = _resolve_team(args.team, args.team_api_id)
        print("=" * 100)
        print(f"AUDIT: {team.name}  (Team.id={team.id}, team_api_id={team.team_id}, season={team.season})")
        print("=" * 100)

        dups = _dup_counts()

        # 1. All active tracked players for this parent club
        tracked = (
            TrackedPlayer.query.filter(TrackedPlayer.team_id == team.id, TrackedPlayer.is_active.is_(True))
            .order_by(TrackedPlayer.status, TrackedPlayer.player_name)
            .all()
        )
        print(f"\n[1] Active TrackedPlayer rows: {len(tracked)}")
        by_status: dict[str, list[TrackedPlayer]] = {}
        for tp in tracked:
            by_status.setdefault(tp.status or "?", []).append(tp)

        for status in sorted(by_status.keys()):
            rows = by_status[status]
            print(f"\n--- status={status}  ({len(rows)}) ---")
            for tp in rows:
                journey = None
                if tp.journey_id:
                    journey = db.session.get(PlayerJourney, tp.journey_id)
                if not journey:
                    journey = PlayerJourney.query.filter_by(player_api_id=tp.player_api_id).first()
                _print_row(tp, journey, dups.get(tp.player_api_id, 0))

        # 2. Staleness summary
        stale_buckets = {"<=7d": 0, "8-30d": 0, "31-90d": 0, ">90d": 0, "never": 0}
        never_synced: list[TrackedPlayer] = []
        oldest: list[tuple[int, TrackedPlayer]] = []
        for tp in tracked:
            journey = None
            if tp.journey_id:
                journey = db.session.get(PlayerJourney, tp.journey_id)
            if not journey or not journey.last_synced_at:
                stale_buckets["never"] += 1
                never_synced.append(tp)
                continue
            ts = journey.last_synced_at
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            age = (datetime.now(UTC) - ts).days
            oldest.append((age, tp))
            if age <= 7:
                stale_buckets["<=7d"] += 1
            elif age <= 30:
                stale_buckets["8-30d"] += 1
            elif age <= 90:
                stale_buckets["31-90d"] += 1
            else:
                stale_buckets[">90d"] += 1

        print("\n[2] Journey staleness buckets:")
        for k, v in stale_buckets.items():
            print(f"    {k:<8} {v}")

        oldest.sort(reverse=True)
        if oldest:
            print("\n[3] Top 10 oldest journey syncs:")
            for age, tp in oldest[:10]:
                print(f"    {age:>4}d  id={tp.id:<6} {tp.player_name} (status={tp.status})")

        # 3. Duplicate rows for this team's players
        print("\n[4] Players with multiple active TrackedPlayer rows (across ALL teams):")
        seen_dups = [tp for tp in tracked if dups.get(tp.player_api_id, 0) > 1]
        if not seen_dups:
            print("    (none)")
        else:
            for tp in seen_dups:
                all_rows = TrackedPlayer.query.filter_by(player_api_id=tp.player_api_id, is_active=True).all()
                print(f"    api={tp.player_api_id} {tp.player_name}")
                for r in all_rows:
                    parent = Team.query.get(r.team_id)
                    pn = parent.name if parent else f"team_id={r.team_id}"
                    print(
                        f"      - row id={r.id} team={pn!r:<28} status={r.status:<10} "
                        f"src={r.data_source:<14} current_club={r.current_club_name!r}"
                    )

        # 4. Highlight
        needle = args.highlight.lower()
        print(f"\n[5] Highlight '{needle}':")
        matches = [tp for tp in tracked if needle in (tp.player_name or "").lower()]
        if not matches:
            # search across the whole DB, not just this team, in case row is under a different team_id
            cross = TrackedPlayer.query.filter(TrackedPlayer.player_name.ilike(f"%{needle}%")).all()
            if cross:
                print(f"    (no match under {team.name}; found {len(cross)} across all teams)")
                for tp in cross:
                    parent = Team.query.get(tp.team_id)
                    pn = parent.name if parent else f"team_id={tp.team_id}"
                    journey = None
                    if tp.journey_id:
                        journey = db.session.get(PlayerJourney, tp.journey_id)
                    print(f"    - parent={pn}")
                    _print_row(tp, journey, dups.get(tp.player_api_id, 0))
            else:
                print("    (no match anywhere)")
        else:
            for tp in matches:
                journey = None
                if tp.journey_id:
                    journey = db.session.get(PlayerJourney, tp.journey_id)
                _print_row(tp, journey, dups.get(tp.player_api_id, 0))

                if journey:
                    entries = (
                        PlayerJourneyEntry.query.filter_by(journey_id=journey.id)
                        .order_by(PlayerJourneyEntry.season.desc())
                        .limit(8)
                        .all()
                    )
                    print("      recent journey entries:")
                    for e in entries:
                        print(
                            f"        season={e.season}  club={e.club_api_id}|{e.club_name}  "
                            f"level={getattr(e, 'level', None)}  "
                            f"youth={getattr(e, 'is_youth', None)}  "
                            f"priority={getattr(e, 'sort_priority', None)}"
                        )

        print("\nDONE")


if __name__ == "__main__":
    main()
