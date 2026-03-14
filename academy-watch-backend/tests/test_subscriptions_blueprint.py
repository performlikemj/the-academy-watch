"""Tests for subscriptions blueprint endpoints in src/routes/subscriptions.py."""

import os
import uuid
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta, timezone

import pytest
from flask import Flask

from src.models.league import db, Team, League, UserSubscription, EmailToken
import src.models.weekly  # Ensure weekly models are registered for db.create_all()


ADMIN_KEY = 'test-admin-key'


@pytest.fixture(autouse=True)
def _set_admin_key(monkeypatch):
    """Set admin API key for all tests."""
    monkeypatch.setenv('ADMIN_API_KEY', ADMIN_KEY)
    # Disable email verification for most tests
    monkeypatch.setenv('SUBSCRIPTIONS_REQUIRE_VERIFY', '0')


@pytest.fixture
def subscriptions_app():
    """Create a minimal Flask app with subscriptions blueprint registered."""
    os.environ.setdefault('SKIP_API_HANDSHAKE', '1')
    os.environ.setdefault('API_USE_STUB_DATA', 'true')

    from src.routes.subscriptions import subscriptions_bp

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
    app.register_blueprint(subscriptions_bp, url_prefix='/api')

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def subscriptions_client(subscriptions_app):
    return subscriptions_app.test_client()


@pytest.fixture
def sample_league(subscriptions_app):
    """Create a sample league for testing."""
    with subscriptions_app.app_context():
        league = League(
            league_id=39,
            name='Premier League',
            country='England',
            season=2024,
            is_european_top_league=True,
        )
        db.session.add(league)
        db.session.commit()
        return league.id


@pytest.fixture
def sample_team(subscriptions_app, sample_league):
    """Create a sample team for testing."""
    with subscriptions_app.app_context():
        team = Team(
            team_id=33,
            name='Manchester United',
            country='England',
            season=2024,
            league_id=sample_league,
            is_active=True,
            newsletters_active=True,
        )
        db.session.add(team)
        db.session.commit()
        return team.id


@pytest.fixture
def sample_subscription(subscriptions_app, sample_team):
    """Create a sample subscription for testing."""
    with subscriptions_app.app_context():
        sub = UserSubscription(
            email='test@example.com',
            team_id=sample_team,
            preferred_frequency='weekly',
            active=True,
            unsubscribe_token=str(uuid.uuid4()),
        )
        db.session.add(sub)
        db.session.commit()
        return {'id': sub.id, 'token': sub.unsubscribe_token}


def _admin_headers(app):
    """Return headers for admin authentication."""
    with app.app_context():
        from src.auth import issue_user_token
        token = issue_user_token('admin@example.com', role='admin')['token']
        return {
            'Authorization': f'Bearer {token}',
            'X-API-Key': ADMIN_KEY,
        }


def _user_headers(app, email='user@example.com'):
    """Return headers for regular user authentication."""
    with app.app_context():
        from src.auth import issue_user_token
        token = issue_user_token(email, role='user')['token']
        return {
            'Authorization': f'Bearer {token}',
        }


class TestGetSubscriptions:
    """Tests for GET /subscriptions endpoint (admin)."""

    def test_get_subscriptions_requires_auth(self, subscriptions_client):
        """Should require authentication."""
        res = subscriptions_client.get('/api/subscriptions')
        assert res.status_code == 401

    def test_get_subscriptions_returns_list(self, subscriptions_app, subscriptions_client, sample_subscription):
        """Should return list of subscriptions."""
        res = subscriptions_client.get(
            '/api/subscriptions',
            headers=_admin_headers(subscriptions_app)
        )
        assert res.status_code == 200
        data = res.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_get_subscriptions_filter_active_only(self, subscriptions_app, subscriptions_client, sample_subscription):
        """Should filter to active subscriptions only."""
        res = subscriptions_client.get(
            '/api/subscriptions?active_only=true',
            headers=_admin_headers(subscriptions_app)
        )
        assert res.status_code == 200
        data = res.get_json()
        assert all(sub['active'] for sub in data)


class TestCreateSubscription:
    """Tests for POST /subscriptions endpoint."""

    def test_create_subscription_success(self, subscriptions_client, sample_team):
        """Should create a new subscription."""
        res = subscriptions_client.post(
            '/api/subscriptions',
            json={'email': 'new@example.com', 'team_id': sample_team}
        )
        assert res.status_code == 201
        data = res.get_json()
        assert data['created_count'] == 1

    def test_create_subscription_missing_fields(self, subscriptions_client):
        """Should return 400 for missing required fields."""
        res = subscriptions_client.post(
            '/api/subscriptions',
            json={'email': 'new@example.com'}
        )
        assert res.status_code == 400
        data = res.get_json()
        assert 'error' in data


class TestBulkCreateSubscriptions:
    """Tests for POST /subscriptions/bulk_create endpoint."""

    def test_bulk_create_success(self, subscriptions_client, sample_team):
        """Should create subscriptions for multiple teams."""
        res = subscriptions_client.post(
            '/api/subscriptions/bulk_create',
            json={'email': 'bulk@example.com', 'team_ids': [sample_team]}
        )
        assert res.status_code == 201
        data = res.get_json()
        assert data['created_count'] >= 1

    def test_bulk_create_missing_fields(self, subscriptions_client):
        """Should return 400 for missing required fields."""
        res = subscriptions_client.post(
            '/api/subscriptions/bulk_create',
            json={'email': 'bulk@example.com'}
        )
        assert res.status_code == 400


class TestUnsubscribeByEmail:
    """Tests for POST /subscriptions/unsubscribe endpoint."""

    def test_unsubscribe_success(self, subscriptions_client, sample_subscription):
        """Should unsubscribe by email."""
        res = subscriptions_client.post(
            '/api/subscriptions/unsubscribe',
            json={'email': 'test@example.com'}
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data['count'] >= 1

    def test_unsubscribe_no_match(self, subscriptions_client):
        """Should handle no matching subscriptions."""
        res = subscriptions_client.post(
            '/api/subscriptions/unsubscribe',
            json={'email': 'nonexistent@example.com'}
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data['count'] == 0

    def test_unsubscribe_missing_email(self, subscriptions_client):
        """Should return 400 for missing email."""
        res = subscriptions_client.post(
            '/api/subscriptions/unsubscribe',
            json={}
        )
        assert res.status_code == 400


class TestTokenUnsubscribe:
    """Tests for /subscriptions/unsubscribe/<token> endpoint."""

    def test_token_unsubscribe_post_success(self, subscriptions_client, sample_subscription):
        """Should unsubscribe via POST with valid token."""
        res = subscriptions_client.post(
            f'/api/subscriptions/unsubscribe/{sample_subscription["token"]}'
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data['message'] == 'Unsubscribed successfully'

    def test_token_unsubscribe_post_invalid_token(self, subscriptions_client):
        """Should return 404 for invalid token."""
        res = subscriptions_client.post(
            '/api/subscriptions/unsubscribe/invalid-token-123'
        )
        assert res.status_code == 404

    def test_token_unsubscribe_get_renders_page(self, subscriptions_client, sample_subscription):
        """Should render confirmation page on GET."""
        res = subscriptions_client.get(
            f'/api/subscriptions/unsubscribe/{sample_subscription["token"]}'
        )
        assert res.status_code == 200
        # Should return HTML
        assert 'text/html' in res.content_type


class TestOneClickUnsubscribe:
    """Tests for POST /subscriptions/one-click-unsubscribe/<token> endpoint."""

    def test_one_click_unsubscribe_success(self, subscriptions_client, sample_subscription):
        """Should unsubscribe and return 200."""
        res = subscriptions_client.post(
            f'/api/subscriptions/one-click-unsubscribe/{sample_subscription["token"]}',
            data='List-Unsubscribe=One-Click',
            content_type='application/x-www-form-urlencoded'
        )
        # RFC 8058 requires 200 response
        assert res.status_code == 200

    def test_one_click_unsubscribe_invalid_token_still_returns_200(self, subscriptions_client):
        """Should return 200 even for invalid token (RFC 8058 compliance)."""
        res = subscriptions_client.post(
            '/api/subscriptions/one-click-unsubscribe/invalid-token-xyz',
            data='List-Unsubscribe=One-Click'
        )
        # Must return 200 per RFC 8058
        assert res.status_code == 200


class TestDeleteSubscription:
    """Tests for DELETE /subscriptions/<id> endpoint."""

    def test_delete_subscription_success(self, subscriptions_client, sample_subscription):
        """Should deactivate subscription."""
        res = subscriptions_client.delete(
            f'/api/subscriptions/{sample_subscription["id"]}'
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data['message'] == 'Unsubscribed successfully'

    def test_delete_subscription_not_found(self, subscriptions_client):
        """Should return 404 for non-existent subscription."""
        res = subscriptions_client.delete('/api/subscriptions/99999')
        assert res.status_code == 404


class TestManageSubscriptions:
    """Tests for /subscriptions/manage/<token> endpoints."""

    def test_request_manage_link_success(self, subscriptions_client):
        """Should create manage token."""
        res = subscriptions_client.post(
            '/api/subscriptions/request-manage-link',
            json={'email': 'manage@example.com'}
        )
        assert res.status_code == 200
        data = res.get_json()
        assert 'token' in data
        assert 'expires_at' in data

    def test_request_manage_link_missing_email(self, subscriptions_client):
        """Should return 400 for missing email."""
        res = subscriptions_client.post(
            '/api/subscriptions/request-manage-link',
            json={}
        )
        assert res.status_code == 400

    def test_get_manage_state_success(self, subscriptions_app, subscriptions_client, sample_subscription):
        """Should return subscriptions for valid manage token."""
        # Create manage token
        with subscriptions_app.app_context():
            token = EmailToken(
                token=str(uuid.uuid4()),
                email='test@example.com',
                purpose='manage',
                expires_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
            db.session.add(token)
            db.session.commit()
            token_str = token.token

        res = subscriptions_client.get(f'/api/subscriptions/manage/{token_str}')
        assert res.status_code == 200
        data = res.get_json()
        assert 'email' in data
        assert 'subscriptions' in data

    def test_get_manage_state_invalid_token(self, subscriptions_client):
        """Should return 400 for invalid token."""
        res = subscriptions_client.get('/api/subscriptions/manage/invalid-token')
        assert res.status_code == 400


class TestMySubscriptions:
    """Tests for /subscriptions/me endpoints."""

    def test_my_subscriptions_requires_auth(self, subscriptions_client):
        """Should require authentication."""
        res = subscriptions_client.get('/api/subscriptions/me')
        assert res.status_code == 401

    def test_my_subscriptions_returns_list(self, subscriptions_app, subscriptions_client, sample_team):
        """Should return user's subscriptions."""
        # Create subscription for user
        with subscriptions_app.app_context():
            sub = UserSubscription(
                email='user@example.com',
                team_id=sample_team,
                active=True,
                unsubscribe_token=str(uuid.uuid4()),
            )
            db.session.add(sub)
            db.session.commit()

        res = subscriptions_client.get(
            '/api/subscriptions/me',
            headers=_user_headers(subscriptions_app, 'user@example.com')
        )
        assert res.status_code == 200
        data = res.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1

    def test_update_my_subscriptions_success(self, subscriptions_app, subscriptions_client, sample_team):
        """Should update user's subscriptions."""
        res = subscriptions_client.post(
            '/api/subscriptions/me',
            json={'team_ids': [sample_team]},
            headers=_user_headers(subscriptions_app, 'updater@example.com')
        )
        assert res.status_code == 200
        data = res.get_json()
        assert 'subscriptions' in data

    def test_update_my_subscriptions_requires_auth(self, subscriptions_client):
        """Should require authentication."""
        res = subscriptions_client.post(
            '/api/subscriptions/me',
            json={'team_ids': [1]}
        )
        assert res.status_code == 401
