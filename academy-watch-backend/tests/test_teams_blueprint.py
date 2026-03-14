"""Tests for teams blueprint endpoints in src/routes/teams.py."""

import os
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

from src.models.league import db, Team, League, LoanedPlayer
import src.models.weekly  # Ensure weekly models are registered for db.create_all()


@pytest.fixture
def teams_app():
    """Create a minimal Flask app with teams blueprint registered."""
    # Ensure stub mode for API client
    os.environ.setdefault('SKIP_API_HANDSHAKE', '1')
    os.environ.setdefault('API_USE_STUB_DATA', 'true')

    from src.routes.teams import teams_bp

    root_dir = os.path.dirname(os.path.dirname(__file__))
    template_dir = os.path.join(root_dir, 'src', 'templates')

    app = Flask(__name__, template_folder=template_dir)
    app.config.update(
        TESTING=True,
        SECRET_KEY='test-secret-key',
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )

    db.init_app(app)
    app.register_blueprint(teams_bp, url_prefix='/api')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def teams_client(teams_app):
    return teams_app.test_client()


@pytest.fixture
def sample_league(teams_app):
    """Create a sample league for testing."""
    with teams_app.app_context():
        league = League(
            league_id=39,
            name='Premier League',
            country='England',
            season=2024,
            is_european_top_league=True,
            logo='https://example.com/pl.png'
        )
        db.session.add(league)
        db.session.commit()
        return league.id


@pytest.fixture
def sample_team(teams_app, sample_league):
    """Create a sample team for testing."""
    with teams_app.app_context():
        team = Team(
            team_id=33,
            name='Manchester United',
            country='England',
            season=2024,
            league_id=sample_league,
            is_active=True,
            logo='https://example.com/manu.png'
        )
        db.session.add(team)
        db.session.commit()
        return team.id


class TestGetLeagues:
    """Tests for GET /leagues endpoint."""

    def test_get_leagues_returns_european_leagues(self, teams_app, teams_client, sample_league):
        """Should return all European top leagues."""
        res = teams_client.get('/api/leagues')
        assert res.status_code == 200
        data = res.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]['name'] == 'Premier League'

    def test_get_leagues_empty_database(self, teams_client):
        """Should return empty list when no leagues exist."""
        res = teams_client.get('/api/leagues')
        assert res.status_code == 200
        data = res.get_json()
        assert data == []


class TestGetGameweeks:
    """Tests for GET /gameweeks endpoint."""

    def test_get_gameweeks_returns_list(self, teams_client):
        """Should return gameweeks for the season."""
        res = teams_client.get('/api/gameweeks?season=2024')
        assert res.status_code == 200
        data = res.get_json()
        assert isinstance(data, list)


class TestGetTeams:
    """Tests for GET /teams endpoint."""

    def test_get_teams_returns_active_teams(self, teams_app, teams_client, sample_team):
        """Should return active teams."""
        res = teams_client.get('/api/teams')
        assert res.status_code == 200
        data = res.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]['name'] == 'Manchester United'

    def test_get_teams_filter_by_season(self, teams_app, teams_client, sample_team):
        """Should filter teams by season."""
        res = teams_client.get('/api/teams?season=2024')
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) >= 1

        # Non-existent season should return empty
        res = teams_client.get('/api/teams?season=1990')
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) == 0

    def test_get_teams_search_filter(self, teams_app, teams_client, sample_team):
        """Should filter teams by search term."""
        res = teams_client.get('/api/teams?search=Manchester')
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) >= 1

        res = teams_client.get('/api/teams?search=NonExistent')
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) == 0


class TestGetTeamById:
    """Tests for GET /teams/<id> endpoint."""

    def test_get_team_returns_team_details(self, teams_app, teams_client, sample_team):
        """Should return team details including loans."""
        res = teams_client.get(f'/api/teams/{sample_team}')
        assert res.status_code == 200
        data = res.get_json()
        assert data['name'] == 'Manchester United'
        assert 'active_loans' in data

    def test_get_team_not_found(self, teams_client):
        """Should return 404 for non-existent team."""
        res = teams_client.get('/api/teams/99999')
        assert res.status_code == 404


class TestGetTeamLoans:
    """Tests for GET /teams/<id>/loans endpoint."""

    def test_get_team_loans_returns_loans(self, teams_app, teams_client, sample_team, sample_league):
        """Should return loans for the team."""
        with teams_app.app_context():
            # Create a loan team
            loan_team = Team(
                team_id=50,
                name='Loan FC',
                country='England',
                season=2024,
                league_id=sample_league,
                is_active=True,
            )
            db.session.add(loan_team)
            db.session.flush()

            # Create a loan
            loan = LoanedPlayer(
                player_id=123,
                player_name='Test Player',
                primary_team_id=sample_team,
                primary_team_name='Manchester United',
                loan_team_id=loan_team.id,
                loan_team_name='Loan FC',
                window_key='2024-25::FULL',
                is_active=True,
                data_source='test',
            )
            db.session.add(loan)
            db.session.commit()

        res = teams_client.get(f'/api/teams/{sample_team}/loans')
        if res.status_code != 200:
            print(f"Response data: {res.get_json()}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.get_json()}"
        data = res.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]['player_name'] == 'Test Player'

    def test_get_team_loans_empty(self, teams_client, sample_team):
        """Should return empty list when no loans exist."""
        res = teams_client.get(f'/api/teams/{sample_team}/loans')
        assert res.status_code == 200
        data = res.get_json()
        assert data == []

    def test_get_team_loans_direction_filter(self, teams_app, teams_client, sample_team, sample_league):
        """Should filter loans by direction."""
        res = teams_client.get(f'/api/teams/{sample_team}/loans?direction=loaned_from')
        assert res.status_code == 200

        res = teams_client.get(f'/api/teams/{sample_team}/loans?direction=loaned_to')
        assert res.status_code == 200


class TestGetTeamLoansBySeason:
    """Tests for GET /teams/<id>/loans/season/<season> endpoint."""

    def test_get_team_loans_by_season(self, teams_app, teams_client, sample_team, sample_league):
        """Should return loans for specific season."""
        with teams_app.app_context():
            loan_team = Team(
                team_id=51,
                name='Season FC',
                country='England',
                season=2024,
                league_id=sample_league,
                is_active=True,
            )
            db.session.add(loan_team)
            db.session.flush()

            loan = LoanedPlayer(
                player_id=456,
                player_name='Season Player',
                primary_team_id=sample_team,
                primary_team_name='Manchester United',
                loan_team_id=loan_team.id,
                loan_team_name='Season FC',
                window_key='2024-25::FULL',
                is_active=True,
                data_source='test',
            )
            db.session.add(loan)
            db.session.commit()

        res = teams_client.get(f'/api/teams/{sample_team}/loans/season/2024')
        assert res.status_code == 200
        data = res.get_json()
        assert isinstance(data, list)


class TestGetTeamsForSeason:
    """Tests for GET /teams/season/<season> endpoint."""

    def test_get_teams_for_season(self, teams_client):
        """Should return teams mapping for season."""
        with patch('src.routes.teams.api_client') as mock_client:
            mock_client.get_teams_for_season.return_value = {
                '33': 'Manchester United',
                '34': 'Newcastle United',
            }
            res = teams_client.get('/api/teams/season/2024')
            assert res.status_code == 200
            data = res.get_json()
            assert data['season'] == 2024
            assert 'teams' in data
            assert 'count' in data


class TestGetTeamApiInfo:
    """Tests for GET /teams/<id>/api-info endpoint."""

    def test_get_team_api_info(self, teams_client):
        """Should return team info from API."""
        with patch('src.routes.teams.api_client') as mock_client:
            mock_client.current_season_start_year = 2024
            mock_client.get_team_by_id.return_value = {
                'team': {'id': 33, 'name': 'Manchester United'},
            }
            res = teams_client.get('/api/teams/33/api-info')
            assert res.status_code == 200
            data = res.get_json()
            assert data['team_id'] == 33
            assert 'data' in data

    def test_get_team_api_info_not_found(self, teams_client):
        """Should return 404 when team not found in API."""
        with patch('src.routes.teams.api_client') as mock_client:
            mock_client.current_season_start_year = 2024
            mock_client.get_team_by_id.return_value = None
            res = teams_client.get('/api/teams/99999/api-info')
            assert res.status_code == 404
