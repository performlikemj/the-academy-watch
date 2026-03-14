"""Tests for loans blueprint endpoints in src/routes/loans.py."""

import os
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

import pytest
from flask import Flask

from src.models.league import db, Team, League, LoanedPlayer, LoanFlag
import src.models.weekly  # Ensure weekly models are registered for db.create_all()


ADMIN_KEY = 'test-admin-key'


@pytest.fixture(autouse=True)
def _set_admin_key(monkeypatch):
    """Set admin API key for all tests."""
    monkeypatch.setenv('ADMIN_API_KEY', ADMIN_KEY)


@pytest.fixture
def loans_app():
    """Create a minimal Flask app with loans blueprint registered."""
    # Ensure stub mode for API client
    os.environ.setdefault('SKIP_API_HANDSHAKE', '1')
    os.environ.setdefault('API_USE_STUB_DATA', 'true')

    from src.routes.loans import loans_bp

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
    app.register_blueprint(loans_bp, url_prefix='/api')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def loans_client(loans_app):
    return loans_app.test_client()


@pytest.fixture
def sample_league(loans_app):
    """Create a sample league for testing."""
    with loans_app.app_context():
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
def sample_teams(loans_app, sample_league):
    """Create sample teams for testing."""
    with loans_app.app_context():
        parent = Team(
            team_id=33,
            name='Manchester United',
            country='England',
            season=2024,
            league_id=sample_league,
            is_active=True,
        )
        loan_team = Team(
            team_id=50,
            name='Loan FC',
            country='England',
            season=2024,
            league_id=sample_league,
            is_active=True,
        )
        db.session.add_all([parent, loan_team])
        db.session.commit()
        return {'parent_id': parent.id, 'loan_team_id': loan_team.id}


@pytest.fixture
def sample_loan(loans_app, sample_teams):
    """Create a sample loan for testing."""
    with loans_app.app_context():
        loan = LoanedPlayer(
            player_id=123,
            player_name='Test Player',
            primary_team_id=sample_teams['parent_id'],
            primary_team_name='Manchester United',
            loan_team_id=sample_teams['loan_team_id'],
            loan_team_name='Loan FC',
            window_key='2024-25::FULL',
            is_active=True,
            data_source='test',
        )
        db.session.add(loan)
        db.session.commit()
        return loan.id


def _admin_headers(app):
    """Return headers for admin authentication."""
    with app.app_context():
        from src.auth import issue_user_token
        token = issue_user_token('admin@example.com', role='admin')['token']
        return {
            'Authorization': f'Bearer {token}',
            'X-API-Key': ADMIN_KEY,
        }


class TestGetLoans:
    """Tests for GET /loans endpoint."""

    def test_get_loans_returns_list(self, loans_client, sample_loan):
        """Should return list of loans."""
        res = loans_client.get('/api/loans')
        assert res.status_code == 200
        data = res.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_loans_filter_by_season(self, loans_client, sample_loan):
        """Should filter loans by season."""
        res = loans_client.get('/api/loans?season=2024')
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) >= 1

        # Non-matching season should return empty
        res = loans_client.get('/api/loans?season=2020')
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) == 0

    def test_get_loans_filter_active_only(self, loans_client, sample_loan):
        """Should filter to active loans only."""
        res = loans_client.get('/api/loans?active_only=true')
        assert res.status_code == 200
        data = res.get_json()
        assert len(data) >= 1
        assert all(loan['is_active'] for loan in data)

    def test_get_loans_empty_database(self, loans_client):
        """Should return empty list when no loans exist."""
        res = loans_client.get('/api/loans')
        assert res.status_code == 200
        data = res.get_json()
        assert data == []


class TestGetActiveLoans:
    """Tests for GET /loans/active endpoint."""

    def test_get_active_loans_returns_active(self, loans_client, sample_loan):
        """Should return only active loans."""
        res = loans_client.get('/api/loans/active')
        assert res.status_code == 200
        data = res.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert all(loan['is_active'] for loan in data)

    def test_get_active_loans_empty(self, loans_client):
        """Should return empty list when no active loans."""
        res = loans_client.get('/api/loans/active')
        assert res.status_code == 200
        data = res.get_json()
        assert data == []


class TestGetLoansBySeason:
    """Tests for GET /loans/season/<season> endpoint."""

    def test_get_loans_by_season(self, loans_client, sample_loan):
        """Should return loans for specific season."""
        res = loans_client.get('/api/loans/season/2024')
        assert res.status_code == 200
        data = res.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_loans_by_season_empty(self, loans_client, sample_loan):
        """Should return empty for non-matching season."""
        res = loans_client.get('/api/loans/season/2020')
        assert res.status_code == 200
        data = res.get_json()
        assert data == []


class TestTerminateLoan:
    """Tests for POST /loans/<id>/terminate endpoint."""

    def test_terminate_loan_requires_auth(self, loans_client, sample_loan):
        """Should require authentication."""
        res = loans_client.post(f'/api/loans/{sample_loan}/terminate')
        assert res.status_code == 401

    def test_terminate_loan_success(self, loans_app, loans_client, sample_loan):
        """Should terminate loan successfully."""
        res = loans_client.post(
            f'/api/loans/{sample_loan}/terminate',
            json={'reason': 'Recalled by parent club'},
            headers=_admin_headers(loans_app)
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data['message'] == 'Loan terminated successfully'
        assert data['loan']['is_active'] is False

    def test_terminate_loan_not_found(self, loans_app, loans_client):
        """Should return 404 for non-existent loan."""
        res = loans_client.post(
            '/api/loans/99999/terminate',
            json={'reason': 'Test'},
            headers=_admin_headers(loans_app)
        )
        assert res.status_code == 404


class TestUpdateLoanPerformance:
    """Tests for PUT /loans/<id>/performance endpoint."""

    def test_update_performance_requires_auth(self, loans_client, sample_loan):
        """Should require authentication."""
        res = loans_client.put(f'/api/loans/{sample_loan}/performance')
        assert res.status_code == 401

    def test_update_performance_success(self, loans_app, loans_client, sample_loan):
        """Should update performance successfully."""
        res = loans_client.put(
            f'/api/loans/{sample_loan}/performance',
            json={'goals': 5, 'assists': 3, 'appearances': 10},
            headers=_admin_headers(loans_app)
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data['message'] == 'Performance updated successfully'

    def test_update_performance_not_found(self, loans_app, loans_client):
        """Should return 404 for non-existent loan."""
        res = loans_client.put(
            '/api/loans/99999/performance',
            json={'goals': 1},
            headers=_admin_headers(loans_app)
        )
        assert res.status_code == 404


class TestGetCsvTemplate:
    """Tests for GET /loans/csv-template endpoint."""

    def test_get_csv_template_returns_csv(self, loans_client):
        """Should return CSV file."""
        res = loans_client.get('/api/loans/csv-template')
        assert res.status_code == 200
        assert 'text/csv' in res.content_type
        assert 'attachment' in res.headers.get('Content-Disposition', '')

    def test_csv_template_has_headers(self, loans_client):
        """Should contain expected CSV headers."""
        res = loans_client.get('/api/loans/csv-template')
        assert res.status_code == 200
        content = res.data.decode('utf-8')
        assert 'player_id' in content
        assert 'parent_team_id' in content
        assert 'loan_team_id' in content


class TestLoanFlags:
    """Tests for loan flag endpoints."""

    def test_create_flag_success(self, loans_client):
        """Should create a loan flag."""
        res = loans_client.post(
            '/api/loans/flags',
            json={
                'player_id': 123,
                'primary_team_api_id': 33,
                'reason': 'Player returned early',
            }
        )
        assert res.status_code == 201
        data = res.get_json()
        assert data['message'] == 'Flag submitted'
        assert 'id' in data

    def test_create_flag_missing_fields(self, loans_client):
        """Should return 400 for missing required fields."""
        res = loans_client.post(
            '/api/loans/flags',
            json={'player_id': 123}
        )
        assert res.status_code == 400
        data = res.get_json()
        assert 'error' in data

    def test_list_pending_flags_requires_auth(self, loans_client):
        """Should require authentication."""
        res = loans_client.get('/api/loans/flags/pending')
        assert res.status_code == 401

    def test_list_pending_flags_success(self, loans_app, loans_client):
        """Should list pending flags."""
        # Create a flag first
        with loans_app.app_context():
            flag = LoanFlag(
                player_api_id=123,
                primary_team_api_id=33,
                reason='Test flag',
                status='pending',
            )
            db.session.add(flag)
            db.session.commit()

        res = loans_client.get(
            '/api/loans/flags/pending',
            headers=_admin_headers(loans_app)
        )
        assert res.status_code == 200
        data = res.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_resolve_flag_requires_auth(self, loans_client):
        """Should require authentication."""
        res = loans_client.post('/api/loans/flags/1/resolve')
        assert res.status_code == 401

    def test_resolve_flag_success(self, loans_app, loans_client):
        """Should resolve a flag."""
        with loans_app.app_context():
            flag = LoanFlag(
                player_api_id=123,
                primary_team_api_id=33,
                reason='Test flag',
                status='pending',
            )
            db.session.add(flag)
            db.session.commit()
            flag_id = flag.id

        res = loans_client.post(
            f'/api/loans/flags/{flag_id}/resolve',
            json={'action': 'resolved', 'note': 'Handled'},
            headers=_admin_headers(loans_app)
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data['message'] == 'Flag resolved'

    def test_resolve_flag_not_found(self, loans_app, loans_client):
        """Should return 404 for non-existent flag."""
        res = loans_client.post(
            '/api/loans/flags/99999/resolve',
            json={'action': 'resolved'},
            headers=_admin_headers(loans_app)
        )
        assert res.status_code == 404


class TestWeeklyReport:
    """Tests for GET /loans/weekly-report endpoint."""

    def test_weekly_report_requires_auth(self, loans_client):
        """Should require authentication."""
        res = loans_client.get('/api/loans/weekly-report')
        assert res.status_code == 401

    def test_weekly_report_requires_params(self, loans_app, loans_client):
        """Should require team_id and date params."""
        res = loans_client.get(
            '/api/loans/weekly-report',
            headers=_admin_headers(loans_app)
        )
        assert res.status_code == 400
        data = res.get_json()
        assert 'error' in data
