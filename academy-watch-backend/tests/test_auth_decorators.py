"""Tests for auth decorators and utilities extracted to src/auth.py."""

import os
import time
from unittest.mock import patch

import pytest
from flask import Flask, g, jsonify

from src.models.league import db, UserAccount


@pytest.fixture
def auth_app():
    """Create a minimal Flask app for testing auth decorators."""
    from src.auth import auth_utilities_bp

    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SECRET_KEY='test-secret-key',
        SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )

    db.init_app(app)
    app.register_blueprint(auth_utilities_bp)

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def auth_client(auth_app):
    return auth_app.test_client()


class TestRequireApiKey:
    """Tests for the require_api_key decorator."""

    def test_require_api_key_missing_token_returns_401(self, auth_app, auth_client):
        """Missing Bearer token should return 401."""
        from src.auth import require_api_key

        @auth_app.route('/test-admin')
        @require_api_key
        def test_endpoint():
            return jsonify({'ok': True})

        with patch.dict(os.environ, {'ADMIN_API_KEY': 'test-key'}):
            res = auth_client.get('/test-admin')
            assert res.status_code == 401
            data = res.get_json()
            assert 'error' in data

    def test_require_api_key_invalid_bearer_returns_401(self, auth_app, auth_client):
        """Invalid Bearer token should return 401."""
        from src.auth import require_api_key

        @auth_app.route('/test-admin-invalid')
        @require_api_key
        def test_endpoint():
            return jsonify({'ok': True})

        with patch.dict(os.environ, {'ADMIN_API_KEY': 'test-key'}):
            res = auth_client.get(
                '/test-admin-invalid',
                headers={'Authorization': 'Bearer invalid-token'},
            )
            assert res.status_code == 401

    def test_require_api_key_missing_x_api_key_returns_401(self, auth_app, auth_client):
        """Valid Bearer but missing X-API-Key should return 401."""
        from src.auth import require_api_key, issue_user_token

        @auth_app.route('/test-admin-no-key')
        @require_api_key
        def test_endpoint():
            return jsonify({'ok': True})

        with auth_app.app_context():
            # Create a valid admin token
            token_data = issue_user_token('admin@example.com', role='admin')
            token = token_data['token']

        with patch.dict(os.environ, {'ADMIN_API_KEY': 'test-key'}):
            res = auth_client.get(
                '/test-admin-no-key',
                headers={'Authorization': f'Bearer {token}'},
            )
            assert res.status_code == 401
            data = res.get_json()
            assert 'API key' in data.get('error', '') or 'API key' in data.get('message', '')

    def test_require_api_key_wrong_key_returns_403(self, auth_app, auth_client):
        """Valid Bearer but wrong X-API-Key should return 403."""
        from src.auth import require_api_key, issue_user_token

        @auth_app.route('/test-admin-wrong-key')
        @require_api_key
        def test_endpoint():
            return jsonify({'ok': True})

        with auth_app.app_context():
            token_data = issue_user_token('admin@example.com', role='admin')
            token = token_data['token']

        with patch.dict(os.environ, {'ADMIN_API_KEY': 'correct-key'}):
            res = auth_client.get(
                '/test-admin-wrong-key',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-API-Key': 'wrong-key',
                },
            )
            assert res.status_code == 403

    def test_require_api_key_success(self, auth_app, auth_client):
        """Valid Bearer + correct X-API-Key should succeed."""
        from src.auth import require_api_key, issue_user_token

        @auth_app.route('/test-admin-success')
        @require_api_key
        def test_endpoint():
            return jsonify({'ok': True, 'user': getattr(g, 'user_email', None)})

        with auth_app.app_context():
            token_data = issue_user_token('admin@example.com', role='admin')
            token = token_data['token']

        with patch.dict(os.environ, {'ADMIN_API_KEY': 'correct-key'}):
            res = auth_client.get(
                '/test-admin-success',
                headers={
                    'Authorization': f'Bearer {token}',
                    'X-API-Key': 'correct-key',
                },
            )
            assert res.status_code == 200
            data = res.get_json()
            assert data['ok'] is True
            assert data['user'] == 'admin@example.com'

    def test_require_api_key_options_passes_through(self, auth_app, auth_client):
        """OPTIONS requests should pass through without authentication."""
        from src.auth import require_api_key

        @auth_app.route('/test-admin-options', methods=['GET', 'OPTIONS'])
        @require_api_key
        def test_endpoint():
            return jsonify({'ok': True})

        res = auth_client.options('/test-admin-options')
        assert res.status_code == 204


class TestRequireUserAuth:
    """Tests for the require_user_auth decorator."""

    def test_require_user_auth_missing_token_returns_401(self, auth_app, auth_client):
        """Missing token should return 401."""
        from src.auth import require_user_auth

        @auth_app.route('/test-user-missing')
        @require_user_auth
        def test_endpoint():
            return jsonify({'ok': True})

        res = auth_client.get('/test-user-missing')
        assert res.status_code == 401
        data = res.get_json()
        assert 'error' in data

    def test_require_user_auth_invalid_token_returns_401(self, auth_app, auth_client):
        """Invalid token should return 401."""
        from src.auth import require_user_auth

        @auth_app.route('/test-user-invalid')
        @require_user_auth
        def test_endpoint():
            return jsonify({'ok': True})

        res = auth_client.get(
            '/test-user-invalid',
            headers={'Authorization': 'Bearer invalid-garbage'},
        )
        assert res.status_code == 401

    def test_require_user_auth_sets_g_user_email(self, auth_app, auth_client):
        """Valid token should set g.user_email."""
        from src.auth import require_user_auth, issue_user_token, _ensure_user_account

        @auth_app.route('/test-user-email')
        @require_user_auth
        def test_endpoint():
            return jsonify({
                'user_email': getattr(g, 'user_email', None),
                'user_id': getattr(g, 'user_id', None),
            })

        with auth_app.app_context():
            _ensure_user_account('testuser@example.com')
            db.session.commit()
            token_data = issue_user_token('testuser@example.com')
            token = token_data['token']

        res = auth_client.get(
            '/test-user-email',
            headers={'Authorization': f'Bearer {token}'},
        )
        assert res.status_code == 200
        data = res.get_json()
        assert data['user_email'] == 'testuser@example.com'
        assert data['user_id'] is not None


class TestIssueUserToken:
    """Tests for the issue_user_token function."""

    def test_issue_user_token_contains_email_and_role(self, auth_app):
        """Token should contain email and role."""
        from src.auth import issue_user_token, _user_serializer

        with auth_app.app_context():
            result = issue_user_token('user@example.com', role='user')
            assert 'token' in result
            assert 'expires_in' in result

            # Decode and verify payload
            serializer = _user_serializer()
            payload = serializer.loads(result['token'])
            assert payload['email'] == 'user@example.com'
            assert payload['role'] == 'user'
            assert 'iat' in payload

    def test_issue_user_token_admin_role(self, auth_app):
        """Admin role should be included in token."""
        from src.auth import issue_user_token, _user_serializer

        with auth_app.app_context():
            result = issue_user_token('admin@example.com', role='admin')
            serializer = _user_serializer()
            payload = serializer.loads(result['token'])
            assert payload['role'] == 'admin'


class TestGetAuthorizedEmail:
    """Tests for the _get_authorized_email function."""

    def test_get_authorized_email_from_g(self, auth_app):
        """Should return email from g.user_email if set."""
        from src.auth import _get_authorized_email

        with auth_app.test_request_context():
            g.user_email = 'cached@example.com'
            result = _get_authorized_email()
            assert result == 'cached@example.com'

    def test_get_authorized_email_from_bearer(self, auth_app):
        """Should decode Bearer token if g.user_email not set."""
        from src.auth import _get_authorized_email, issue_user_token

        with auth_app.app_context():
            token_data = issue_user_token('bearer@example.com')
            token = token_data['token']

        with auth_app.test_request_context(headers={'Authorization': f'Bearer {token}'}):
            result = _get_authorized_email()
            assert result == 'bearer@example.com'

    def test_get_authorized_email_returns_none_for_invalid(self, auth_app):
        """Should return None for invalid token."""
        from src.auth import _get_authorized_email

        with auth_app.test_request_context(headers={'Authorization': 'Bearer invalid'}):
            result = _get_authorized_email()
            assert result is None


class TestAdminEmailList:
    """Tests for _admin_email_list function."""

    def test_admin_email_list_parses_env(self, auth_app):
        """Should parse comma-separated admin emails from env."""
        from src.auth import _admin_email_list

        with patch.dict(os.environ, {'ADMIN_EMAILS': 'admin1@example.com, admin2@example.com'}):
            result = _admin_email_list()
            assert result == ['admin1@example.com', 'admin2@example.com']

    def test_admin_email_list_empty_env(self, auth_app):
        """Should return empty list when env not set."""
        from src.auth import _admin_email_list

        with patch.dict(os.environ, {'ADMIN_EMAILS': ''}):
            result = _admin_email_list()
            assert result == []

    def test_admin_email_list_removes_duplicates(self, auth_app):
        """Should remove duplicates while preserving order."""
        from src.auth import _admin_email_list

        with patch.dict(os.environ, {'ADMIN_EMAILS': 'a@x.com, b@x.com, a@x.com'}):
            result = _admin_email_list()
            assert result == ['a@x.com', 'b@x.com']


class TestDisplayNameHelpers:
    """Tests for display name helper functions."""

    def test_normalize_display_name_strips_special_chars(self, auth_app):
        """Should strip disallowed characters."""
        from src.auth import _normalize_display_name

        result = _normalize_display_name("Test<script>User")
        assert '<' not in result
        assert '>' not in result

    def test_normalize_display_name_truncates_to_40(self, auth_app):
        """Should truncate to 40 characters."""
        from src.auth import _normalize_display_name

        long_name = "A" * 100
        result = _normalize_display_name(long_name)
        assert len(result) == 40

    def test_make_display_name_unique_appends_suffix(self, auth_app):
        """Should append numeric suffix if name exists."""
        from src.auth import _make_display_name_unique

        with auth_app.app_context():
            # Create an existing user
            user = UserAccount(
                email='existing@example.com',
                display_name='TestUser',
                display_name_lower='testuser',
            )
            db.session.add(user)
            db.session.commit()

            # Try to make a unique name with the same base
            result = _make_display_name_unique('TestUser')
            assert result != 'TestUser'
            assert result.startswith('TestUser')

    def test_generate_default_display_name_from_email(self, auth_app):
        """Should generate display name from email local part."""
        from src.auth import _generate_default_display_name

        with auth_app.app_context():
            result = _generate_default_display_name('john.doe@example.com')
            assert 'john' in result.lower() or 'doe' in result.lower()


class TestGetClientIp:
    """Tests for get_client_ip function."""

    def test_get_client_ip_from_forwarded_for(self, auth_app):
        """Should extract IP from X-Forwarded-For header."""
        from src.auth import get_client_ip

        with auth_app.test_request_context(
            headers={'X-Forwarded-For': '203.0.113.1, 10.0.0.1'}
        ):
            result = get_client_ip()
            assert result == '203.0.113.1'

    def test_get_client_ip_from_real_ip(self, auth_app):
        """Should extract IP from X-Real-IP header."""
        from src.auth import get_client_ip

        with auth_app.test_request_context(headers={'X-Real-IP': '198.51.100.42'}):
            result = get_client_ip()
            assert result == '198.51.100.42'

    def test_get_client_ip_fallback_to_remote_addr(self, auth_app):
        """Should fall back to remote_addr."""
        from src.auth import get_client_ip

        with auth_app.test_request_context(environ_base={'REMOTE_ADDR': '127.0.0.1'}):
            result = get_client_ip()
            assert result == '127.0.0.1'


class TestEnsureUserAccount:
    """Tests for _ensure_user_account function."""

    def test_ensure_user_account_creates_new_user(self, auth_app):
        """Should create new user if doesn't exist."""
        from src.auth import _ensure_user_account

        with auth_app.app_context():
            user = _ensure_user_account('newuser@example.com')
            db.session.commit()

            assert user is not None
            assert user.email == 'newuser@example.com'
            assert user.display_name is not None

    def test_ensure_user_account_returns_existing_user(self, auth_app):
        """Should return existing user if exists."""
        from src.auth import _ensure_user_account

        with auth_app.app_context():
            # Create user first
            user1 = _ensure_user_account('existing@example.com')
            db.session.commit()
            user1_id = user1.id

            # Get same user again
            user2 = _ensure_user_account('existing@example.com')
            assert user2.id == user1_id


class TestSafeErrorPayload:
    """Tests for _safe_error_payload function."""

    def test_safe_error_payload_hides_details_in_production(self, auth_app):
        """Should hide exception details in production."""
        from src.auth import _safe_error_payload

        with patch.dict(os.environ, {'ENV': 'production'}):
            result = _safe_error_payload(
                ValueError("secret database error"),
                "Something went wrong"
            )
            assert result['error'] == "Something went wrong"
            assert 'secret database error' not in str(result)
            assert 'reference' in result

    def test_safe_error_payload_shows_details_in_dev(self, auth_app):
        """Should show exception details in development."""
        from src.auth import _safe_error_payload

        with patch.dict(os.environ, {'ENV': 'development'}):
            result = _safe_error_payload(
                ValueError("debug info"),
                "Something went wrong"
            )
            assert result['error'] == "Something went wrong"
            assert result.get('detail') == "debug info"
