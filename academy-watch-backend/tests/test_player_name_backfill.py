"""Tests for placeholder player-name resolution and the backfill endpoint.

Covers:
- is_placeholder_name / resolve_player_name priority order
- POST /api/admin/players/backfill-names repair endpoint
"""

import pytest
from flask import Flask
from src.models.cohort import AcademyCohort, CohortMember
from src.models.journey import PlayerJourney
from src.models.league import AcademyPlayerSeasonStats, League, Player, Team, db
from src.models.tracked_player import TrackedPlayer
from src.utils.player_names import is_placeholder_name, resolve_player_name

ADMIN_KEY = "test-admin-key"


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")

    from src.routes.journey import journey_bp

    flask_app = Flask(__name__)
    flask_app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    db.init_app(flask_app)
    flask_app.register_blueprint(journey_bp, url_prefix="/api")

    with flask_app.app_context():
        db.create_all()
        yield flask_app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_headers(app):
    from src.auth import issue_user_token

    token = issue_user_token("admin@test.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _seed_team():
    league = League(league_id=39, name="Premier League", country="England", season=2025)
    db.session.add(league)
    db.session.flush()
    team = Team(
        team_id=33, name="Manchester United", country="England", season=2025, league_id=league.id, is_active=True
    )
    db.session.add(team)
    db.session.flush()
    return team


def _seed_cohort_member(player_api_id, name, photo=None, nationality=None):
    cohort = AcademyCohort.query.first()
    if cohort is None:
        cohort = AcademyCohort(team_api_id=33, team_name="Manchester United", league_api_id=700, season=2020)
        db.session.add(cohort)
        db.session.flush()
    member = CohortMember(
        cohort_id=cohort.id,
        player_api_id=player_api_id,
        player_name=name,
        player_photo=photo,
        nationality=nationality,
    )
    db.session.add(member)
    db.session.flush()
    return member


class TestPlaceholderRegex:
    def test_placeholder_names(self):
        assert is_placeholder_name("Player 12345") is True
        assert is_placeholder_name("Player 1") is True
        assert is_placeholder_name(" Player 99 ") is True  # stripped before matching
        assert is_placeholder_name("") is True
        assert is_placeholder_name(None) is True
        assert is_placeholder_name("   ") is True

    def test_real_names(self):
        assert is_placeholder_name("Tyrell Malacia") is False
        assert is_placeholder_name("Player One") is False
        assert is_placeholder_name("Player 12 Jr") is False
        assert is_placeholder_name("player 123") is False  # case-sensitive regex


class TestResolvePriorityOrder:
    def test_explicit_candidate_wins(self, app):
        assert resolve_player_name(605, "Real Candidate") == "Real Candidate"

    def test_placeholder_candidates_skipped(self, app):
        _seed_cohort_member(600, "Cohort Name")
        assert resolve_player_name(600, "Player 600", None, "") == "Cohort Name"

    def test_cohort_member_first(self, app):
        _seed_cohort_member(600, "Cohort Name")
        db.session.add(
            AcademyPlayerSeasonStats(player_api_id=600, player_name="Stats Name", league_api_id=701, season=2021)
        )
        db.session.add(Player(player_id=600, name="Player Row Name"))
        db.session.add(PlayerJourney(player_api_id=600, player_name="Journey Name"))
        db.session.flush()
        assert resolve_player_name(600) == "Cohort Name"

    def test_season_stats_second(self, app):
        db.session.add(
            AcademyPlayerSeasonStats(player_api_id=601, player_name="Stats Name", league_api_id=701, season=2021)
        )
        db.session.add(Player(player_id=601, name="Player Row Name"))
        db.session.add(PlayerJourney(player_api_id=601, player_name="Journey Name"))
        db.session.flush()
        assert resolve_player_name(601) == "Stats Name"

    def test_players_table_third(self, app):
        db.session.add(Player(player_id=602, name="Player Row Name"))
        db.session.add(PlayerJourney(player_api_id=602, player_name="Journey Name"))
        db.session.flush()
        assert resolve_player_name(602) == "Player Row Name"

    def test_journey_fourth(self, app):
        db.session.add(PlayerJourney(player_api_id=603, player_name="Journey Name"))
        db.session.flush()
        assert resolve_player_name(603) == "Journey Name"

    def test_placeholder_source_rows_skipped(self, app):
        _seed_cohort_member(606, "Player 606")  # placeholder in cohort
        db.session.add(Player(player_id=606, name="Real Player Name"))
        db.session.flush()
        assert resolve_player_name(606) == "Real Player Name"

    def test_last_resort_placeholder(self, app):
        assert resolve_player_name(604) == "Player 604"


class TestBackfillNamesEndpoint:
    def _seed(self):
        team = _seed_team()
        # Inactive TrackedPlayer with placeholder — backfill covers inactive rows too
        tp_placeholder = TrackedPlayer(
            player_api_id=700,
            player_name="Player 700",
            team_id=team.id,
            status="academy",
            data_source="api-football",
            is_active=False,
        )
        # TrackedPlayer with a real name — must be left alone
        tp_real = TrackedPlayer(
            player_api_id=701,
            player_name="Player One Hundred",
            team_id=team.id,
            status="academy",
            data_source="api-football",
            is_active=True,
        )
        # TrackedPlayer placeholder with no source anywhere — unresolved
        tp_unresolved = TrackedPlayer(
            player_api_id=704,
            player_name="Player 704",
            team_id=team.id,
            status="academy",
            data_source="api-football",
            is_active=True,
        )
        db.session.add_all([tp_placeholder, tp_real, tp_unresolved])

        _seed_cohort_member(700, "Seven Hundred", photo="https://img/700.png", nationality="England")
        _seed_cohort_member(703, "Seven O Three")

        # players table placeholder, resolvable via AcademyPlayerSeasonStats
        db.session.add(Player(player_id=702, name="Player 702"))
        db.session.add(
            AcademyPlayerSeasonStats(player_api_id=702, player_name="Seven O Two", league_api_id=701, season=2021)
        )
        # player_journeys placeholder, resolvable via CohortMember
        db.session.add(PlayerJourney(player_api_id=703, player_name="Player 703"))
        db.session.commit()
        return tp_placeholder.id, tp_real.id, tp_unresolved.id

    def test_dry_run_reports_but_mutates_nothing(self, app, client, admin_headers):
        tp_id, _real_id, _unresolved_id = self._seed()

        resp = client.post("/api/admin/players/backfill-names", json={"dry_run": True}, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["dry_run"] is True
        assert data["tracked_updated"] == 1
        assert data["players_updated"] == 1
        assert data["journeys_updated"] == 1
        assert data["unresolved"] == 1

        db.session.expire_all()
        assert db.session.get(TrackedPlayer, tp_id).player_name == "Player 700"
        assert db.session.get(Player, 702).name == "Player 702"
        assert PlayerJourney.query.filter_by(player_api_id=703).first().player_name == "Player 703"

    def test_real_run_fixes_placeholders(self, app, client, admin_headers):
        tp_id, real_id, unresolved_id = self._seed()

        resp = client.post("/api/admin/players/backfill-names", json={"dry_run": False}, headers=admin_headers)
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["dry_run"] is False
        assert data["tracked_updated"] == 1
        assert data["players_updated"] == 1
        assert data["journeys_updated"] == 1
        assert data["unresolved"] == 1
        assert {"player_api_id": 700, "old": "Player 700", "new": "Seven Hundred"} in data["examples"]

        db.session.expire_all()
        fixed = db.session.get(TrackedPlayer, tp_id)
        assert fixed.player_name == "Seven Hundred"
        # photo/nationality backfilled from CohortMember when NULL
        assert fixed.photo_url == "https://img/700.png"
        assert fixed.nationality == "England"
        # Real name untouched
        assert db.session.get(TrackedPlayer, real_id).player_name == "Player One Hundred"
        # Unresolved placeholder unchanged
        assert db.session.get(TrackedPlayer, unresolved_id).player_name == "Player 704"
        # players table and player_journeys fixed
        assert db.session.get(Player, 702).name == "Seven O Two"
        assert PlayerJourney.query.filter_by(player_api_id=703).first().player_name == "Seven O Three"

    def test_requires_admin_auth(self, app, client):
        resp = client.post("/api/admin/players/backfill-names", json={"dry_run": True})
        assert resp.status_code == 401
