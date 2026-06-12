"""Tests for the academy_watch payload assembled by _academy_watch_for_team.

Covers Deliverable 1 of the newsletter upgrade: academy players (status='academy')
joined to AcademyPlayerSeasonStats flow into the weekly report payload as
'academy_watch', with week-window AcademyAppearance rows as
'academy_appearances_week'.
"""

import os
from datetime import date

import pytest
from flask import Flask
from src.api_football_client import _academy_watch_for_team
from src.models.league import AcademyAppearance, AcademyPlayerSeasonStats, League, Team, db
from src.models.tracked_player import TrackedPlayer


@pytest.fixture
def academy_app():
    """Minimal Flask app + in-memory SQLite for model-level tests."""
    os.environ.setdefault("SKIP_API_HANDSHAKE", "1")
    os.environ.setdefault("API_USE_STUB_DATA", "true")

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _make_parent(team_api_id=33, name="Manchester United"):
    league = League(
        league_id=39,
        name="Premier League",
        country="England",
        season=2025,
        is_european_top_league=True,
    )
    db.session.add(league)
    db.session.flush()
    parent = Team(
        team_id=team_api_id,
        name=name,
        country="England",
        season=2025,
        league_id=league.id,
        is_active=True,
    )
    db.session.add(parent)
    db.session.flush()
    return parent


def _make_academy_player(parent, *, api_id, name, level="U21", status="academy", is_active=True):
    tp = TrackedPlayer(
        player_api_id=api_id,
        player_name=name,
        team_id=parent.id,
        status=status,
        current_level=level,
        is_active=is_active,
    )
    db.session.add(tp)
    db.session.flush()
    return tp


def _make_season_stats(
    *,
    player_api_id,
    season,
    minutes,
    league_api_id=999,
    league_name="Premier League 2",
    tracked_player_id=None,
    player_name="Player",
    appearances=10,
    goals=3,
    assists=2,
    rating=7.25,
    yellow_cards=1,
    red_cards=0,
):
    row = AcademyPlayerSeasonStats(
        player_api_id=player_api_id,
        player_name=player_name,
        league_api_id=league_api_id,
        league_name=league_name,
        season=season,
        appearances=appearances,
        minutes=minutes,
        goals=goals,
        assists=assists,
        rating=rating,
        yellow_cards=yellow_cards,
        red_cards=red_cards,
        tracked_player_id=tracked_player_id,
    )
    db.session.add(row)
    db.session.flush()
    return row


@pytest.fixture
def seeded_academy(academy_app):
    """Parent team, 2 academy players (2 seasons of stats each), 1 on-loan player."""
    with academy_app.app_context():
        parent = _make_parent()

        # Academy player 1: linked via tracked_player_id FK
        striker = _make_academy_player(parent, api_id=5001, name="Young Striker", level="U21")
        _make_season_stats(
            player_api_id=5001,
            season=2024,
            minutes=2000,
            tracked_player_id=striker.id,
            player_name="Young Striker",
            goals=9,
        )
        _make_season_stats(
            player_api_id=5001,
            season=2025,
            minutes=900,
            tracked_player_id=striker.id,
            player_name="Young Striker",
            appearances=12,
            goals=6,
            assists=4,
            rating=7.46,
        )

        # Academy player 2: linked only via player_api_id (no FK set)
        keeper = _make_academy_player(parent, api_id=5002, name="Young Keeper", level="U18")
        _make_season_stats(
            player_api_id=5002,
            season=2024,
            minutes=1800,
            player_name="Young Keeper",
        )
        _make_season_stats(
            player_api_id=5002,
            season=2025,
            minutes=1350,
            player_name="Young Keeper",
            appearances=15,
            goals=0,
            assists=1,
            rating=None,
        )

        # On-loan player must NOT appear in academy_watch
        loanee = _make_academy_player(parent, api_id=5003, name="Loaned Out", level=None, status="on_loan")
        _make_season_stats(
            player_api_id=5003,
            season=2025,
            minutes=2500,
            tracked_player_id=loanee.id,
            player_name="Loaned Out",
        )

        db.session.commit()
        yield {"parent_id": parent.id}


def test_payload_shape_and_latest_season(academy_app, seeded_academy):
    with academy_app.app_context():
        result = _academy_watch_for_team(seeded_academy["parent_id"], db.session)

    watch = result["academy_watch"]
    assert isinstance(watch, list)
    assert result["academy_appearances_week"] == []

    # Only the two academy players — never the on-loan player
    assert {e["player_api_id"] for e in watch} == {5001, 5002}

    by_id = {e["player_api_id"]: e for e in watch}
    striker = by_id[5001]
    # Latest season (2025) is used, not the bigger-minutes 2024 row
    assert striker["season"] == 2025
    assert striker["minutes"] == 900
    assert striker["appearances"] == 12
    assert striker["goals"] == 6
    assert striker["assists"] == 4
    assert striker["rating"] == 7.5  # rounded to 1dp
    assert striker["level"] == "U21"
    assert striker["competition"] == "Premier League 2"
    assert striker["player_name"] == "Young Striker"
    assert striker["yellow_cards"] == 1
    assert striker["red_cards"] == 0

    keeper = by_id[5002]
    assert keeper["season"] == 2025
    assert keeper["level"] == "U18"
    assert keeper["rating"] is None


def test_ordering_by_minutes_desc(academy_app, seeded_academy):
    with academy_app.app_context():
        result = _academy_watch_for_team(seeded_academy["parent_id"], db.session)

    minutes = [e["minutes"] for e in result["academy_watch"]]
    assert minutes == sorted(minutes, reverse=True)
    # Keeper (1350') ahead of striker (900')
    assert [e["player_api_id"] for e in result["academy_watch"]] == [5002, 5001]


def test_cap_at_ten_players(academy_app):
    with academy_app.app_context():
        parent = _make_parent()
        for i in range(12):
            api_id = 7000 + i
            tp = _make_academy_player(parent, api_id=api_id, name=f"Prospect {i}", level="U18")
            _make_season_stats(
                player_api_id=api_id,
                season=2025,
                minutes=100 * (i + 1),
                tracked_player_id=tp.id,
                player_name=f"Prospect {i}",
            )
        db.session.commit()

        result = _academy_watch_for_team(parent.id, db.session)

    watch = result["academy_watch"]
    assert len(watch) == 10
    # The two lowest-minute players (100', 200') fell off the cap
    assert min(e["minutes"] for e in watch) == 300


def test_empty_when_no_academy_players(academy_app):
    with academy_app.app_context():
        parent = _make_parent()
        # Only an on-loan player exists
        loanee = _make_academy_player(parent, api_id=8001, name="Only Loanee", status="on_loan")
        _make_season_stats(player_api_id=8001, season=2025, minutes=1000, tracked_player_id=loanee.id)
        db.session.commit()

        result = _academy_watch_for_team(parent.id, db.session)

    assert result == {"academy_watch": [], "academy_appearances_week": []}


def test_empty_when_no_session():
    assert _academy_watch_for_team(1, None) == {"academy_watch": [], "academy_appearances_week": []}


def test_graceful_empty_on_model_import_failure(academy_app, seeded_academy, monkeypatch):
    # `from src.models.league import AcademyPlayerSeasonStats` resolves via getattr
    # on the already-imported module — removing the attribute raises ImportError.
    monkeypatch.delattr("src.models.league.AcademyPlayerSeasonStats")
    with academy_app.app_context():
        result = _academy_watch_for_team(seeded_academy["parent_id"], db.session)

    assert result == {"academy_watch": [], "academy_appearances_week": []}


def test_inactive_academy_players_excluded(academy_app):
    with academy_app.app_context():
        parent = _make_parent()
        tp = _make_academy_player(parent, api_id=9001, name="Gone Boy", is_active=False)
        _make_season_stats(player_api_id=9001, season=2025, minutes=1000, tracked_player_id=tp.id)
        db.session.commit()

        result = _academy_watch_for_team(parent.id, db.session)

    assert result["academy_watch"] == []


def test_academy_appearances_week_window(academy_app, seeded_academy):
    week_start, week_end = date(2025, 12, 15), date(2025, 12, 21)
    with academy_app.app_context():
        # In-window appearance for an academy player
        db.session.add(
            AcademyAppearance(
                player_id=5001,
                player_name="Young Striker",
                fixture_id=111,
                fixture_date=date(2025, 12, 17),
                home_team="Manchester United U21",
                away_team="Leeds United U21",
                competition="Premier League 2",
                started=True,
                goals=2,
                assists=0,
            )
        )
        # Out-of-window appearance must be excluded
        db.session.add(
            AcademyAppearance(
                player_id=5001,
                player_name="Young Striker",
                fixture_id=112,
                fixture_date=date(2025, 12, 28),
                home_team="Arsenal U21",
                away_team="Manchester United U21",
                competition="Premier League 2",
                started=False,
                goals=0,
                assists=1,
            )
        )
        # Appearance for a non-academy (on-loan) player must be excluded
        db.session.add(
            AcademyAppearance(
                player_id=5003,
                player_name="Loaned Out",
                fixture_id=113,
                fixture_date=date(2025, 12, 17),
                home_team="Manchester United U21",
                away_team="Everton U21",
                competition="Premier League 2",
                started=True,
                goals=1,
                assists=0,
            )
        )
        db.session.commit()

        result = _academy_watch_for_team(
            seeded_academy["parent_id"],
            db.session,
            week_start=week_start,
            week_end=week_end,
        )

    apps = result["academy_appearances_week"]
    assert len(apps) == 1
    assert apps[0] == {
        "player_name": "Young Striker",
        "home_team": "Manchester United U21",
        "away_team": "Leeds United U21",
        "competition": "Premier League 2",
        "started": True,
        "goals": 2,
        "assists": 0,
    }


def test_summarize_report_includes_academy_keys(academy_app, seeded_academy, monkeypatch):
    """summarize_parent_loans_week surfaces academy_watch keys in its report dict."""
    from src.api_football_client import APIFootballClient

    client = APIFootballClient.__new__(APIFootballClient)  # skip network handshake
    monkeypatch.setattr(APIFootballClient, "get_team_name", lambda self, *a, **k: "Manchester United")

    with academy_app.app_context():
        # Deactivate every tracked player so the loanee loop makes no API calls,
        # then re-add academy rows for the academy snapshot.
        TrackedPlayer.query.update({TrackedPlayer.is_active: False})
        db.session.flush()
        striker = TrackedPlayer.query.filter_by(player_api_id=5001).first()
        striker.is_active = True
        striker.status = "academy"
        db.session.commit()

        report = client.summarize_parent_loans_week(
            parent_team_db_id=seeded_academy["parent_id"],
            parent_team_api_id=33,
            season=2025,
            week_start=date(2025, 12, 15),
            week_end=date(2025, 12, 21),
            db_session=db.session,
        )

    assert "academy_watch" in report
    assert "academy_appearances_week" in report
    assert [e["player_api_id"] for e in report["academy_watch"]] == [5001]
    assert report["loanees"] == []


def test_lint_and_enrich_tolerates_academy_items(academy_app):
    """Academy Watch items (no 'stats' dict) must pass through lint_and_enrich unharmed."""
    from src.agents.weekly_agent import lint_and_enrich

    news = {
        "title": "Weekly",
        "summary": "A week of football.",
        "sections": [
            {
                "title": "Active Loans",
                "items": [
                    {
                        "player_id": 1001,
                        "player_name": "Alfie Striker",
                        "week_summary": "Scored twice against Hull.",
                        "stats": {"minutes": 90, "goals": 2, "assists": 0, "yellows": 0, "reds": 0},
                    }
                ],
            },
            {
                "title": "Academy Watch",
                "items": [
                    {
                        "player_id": 5001,
                        "player_name": "Young Striker",
                        "current_level": "U21",
                        "week_summary": "Started 12 of 15 games for the U21s with six goals.",
                    }
                ],
            },
        ],
    }

    with academy_app.app_context():
        out = lint_and_enrich(news)

    academy_items = out["sections"][1]["items"]
    assert len(academy_items) == 1
    item = academy_items[0]
    assert item["player_id"] == 5001
    assert item["current_level"] == "U21"
    # week_summary untouched — "Started" must NOT be rewritten to "Did not play"
    assert item["week_summary"] == "Started 12 of 15 games for the U21s with six goals."
    # Academy items never enter highlights or by_numbers leaderboards
    assert all("Young Striker" not in h for h in out.get("highlights", []))
    for leaders in out.get("by_numbers", {}).values():
        assert all(row.get("player") != "Y. Striker" for row in leaders)
