"""Tests for auth blueprint endpoints in src/routes/auth_routes.py."""

import os
from unittest.mock import MagicMock, patch

import pytest
from flask import Flask
from src.extensions import limiter
from src.models.league import EmailToken, UserAccount, db
from src.models.showcase import PlayerProfileClaim
from src.services.account_roles import derive_account_role


@pytest.fixture
def auth_bp_app():
    """Create a minimal Flask app with auth blueprint registered."""
    from src.routes.auth_routes import auth_bp

    root_dir = os.path.dirname(os.path.dirname(__file__))
    template_dir = os.path.join(root_dir, "src", "templates")

    app = Flask(__name__, template_folder=template_dir)
    app.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        RATELIMIT_ENABLED=False,
    )

    db.init_app(app)
    limiter.init_app(app)
    app.register_blueprint(auth_bp, url_prefix="/api")

    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def auth_bp_client(auth_bp_app):
    return auth_bp_app.test_client()


@pytest.fixture
def mock_email_service():
    """Mock the email service to prevent actual email sending."""
    with patch("src.routes.auth_routes.email_service") as mock:
        mock.is_configured.return_value = True
        mock_result = MagicMock()
        mock_result.success = True
        mock_result.provider = "test"
        mock.send_email.return_value = mock_result
        yield mock


class TestRequestLoginCode:
    """Tests for POST /auth/request-code endpoint."""

    def test_request_code_creates_email_token(self, auth_bp_app, auth_bp_client, mock_email_service):
        """Should create an email token in the database."""
        with auth_bp_app.app_context():
            res = auth_bp_client.post("/api/auth/request-code", json={"email": "test@example.com"})
            assert res.status_code == 200
            data = res.get_json()
            assert data["message"] == "Login code sent"

            # Verify token was created
            token = EmailToken.query.filter_by(email="test@example.com", purpose="login").first()
            assert token is not None
            assert token.token is not None

    def test_request_code_missing_email_returns_400(self, auth_bp_client):
        """Should return 400 if email is missing."""
        res = auth_bp_client.post("/api/auth/request-code", json={})
        assert res.status_code == 400
        data = res.get_json()
        assert "error" in data

    def test_request_code_normalizes_email(self, auth_bp_app, auth_bp_client, mock_email_service):
        """Should lowercase and strip email."""
        with auth_bp_app.app_context():
            res = auth_bp_client.post("/api/auth/request-code", json={"email": "  TEST@Example.COM  "})
            assert res.status_code == 200

            token = EmailToken.query.filter_by(email="test@example.com").first()
            assert token is not None


class TestVerifyLoginCode:
    """Tests for POST /auth/verify-code endpoint."""

    def test_verify_code_creates_user_account(self, auth_bp_app, auth_bp_client, mock_email_service):
        """Should create a user account on successful verification."""
        with auth_bp_app.app_context():
            # First request a code
            auth_bp_client.post("/api/auth/request-code", json={"email": "newuser@example.com"})

            # Get the token from DB
            token = EmailToken.query.filter_by(email="newuser@example.com", purpose="login").first()
            assert token is not None

            # Verify the code
            res = auth_bp_client.post(
                "/api/auth/verify-code", json={"email": "newuser@example.com", "code": token.token}
            )
            assert res.status_code == 200

            # Check user was created
            user = UserAccount.query.filter_by(email="newuser@example.com").first()
            assert user is not None

    def test_verify_code_returns_jwt_token(self, auth_bp_app, auth_bp_client, mock_email_service):
        """Should return a JWT token on successful verification."""
        with auth_bp_app.app_context():
            auth_bp_client.post("/api/auth/request-code", json={"email": "user@example.com"})
            token = EmailToken.query.filter_by(email="user@example.com", purpose="login").first()

            res = auth_bp_client.post("/api/auth/verify-code", json={"email": "user@example.com", "code": token.token})
            assert res.status_code == 200
            data = res.get_json()
            assert "token" in data
            assert "expires_in" in data
            assert data["message"] == "Logged in"
            assert data["account_role"] == "scout"
            assert data["is_verified_scout"] is False

    def test_verify_code_returns_player_for_approved_self_claim(self, auth_bp_app, auth_bp_client, mock_email_service):
        """Login returns the role derived from an existing approved claim."""
        with auth_bp_app.app_context():
            user = UserAccount(
                email="claimed-player@example.com",
                display_name="ClaimedPlayer",
                display_name_lower="claimedplayer",
            )
            db.session.add(user)
            db.session.flush()
            db.session.add(
                PlayerProfileClaim(
                    player_api_id=5001,
                    user_account_id=user.id,
                    relationship_type="player",
                    status="approved",
                )
            )
            db.session.commit()

            auth_bp_client.post("/api/auth/request-code", json={"email": user.email})
            token = EmailToken.query.filter_by(email=user.email, purpose="login").first()
            res = auth_bp_client.post("/api/auth/verify-code", json={"email": user.email, "code": token.token})

            assert res.status_code == 200
            assert res.get_json()["account_role"] == "player"

    def test_verify_code_invalid_code_returns_400(self, auth_bp_app, auth_bp_client, mock_email_service):
        """Should return 400 for invalid code."""
        with auth_bp_app.app_context():
            auth_bp_client.post("/api/auth/request-code", json={"email": "user@example.com"})

            res = auth_bp_client.post("/api/auth/verify-code", json={"email": "user@example.com", "code": "wrong-code"})
            assert res.status_code == 400

    def test_verify_code_missing_fields_returns_400(self, auth_bp_client):
        """Should return 400 if email or code missing."""
        res = auth_bp_client.post("/api/auth/verify-code", json={"email": "user@example.com"})
        assert res.status_code == 400

        res = auth_bp_client.post("/api/auth/verify-code", json={"code": "12345"})
        assert res.status_code == 400


class TestAuthMe:
    """Tests for GET /auth/me endpoint."""

    def test_auth_me_returns_user_profile(self, auth_bp_app, auth_bp_client, mock_email_service):
        """Should return user profile when authenticated."""
        from src.auth import issue_user_token

        with auth_bp_app.app_context():
            # Create a user
            user = UserAccount(
                email="me@example.com",
                display_name="TestUser",
                display_name_lower="testuser",
            )
            db.session.add(user)
            db.session.commit()

            token = issue_user_token("me@example.com")["token"]

            res = auth_bp_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert res.status_code == 200
            data = res.get_json()
            assert data["email"] == "me@example.com"
            assert data["display_name"] == "TestUser"
            assert data["role"] == "user"
            assert data["account_role"] == "scout"
            assert data["is_verified_scout"] is False

    def test_auth_me_returns_player_for_approved_self_claim(self, auth_bp_app, auth_bp_client):
        """An approved player relationship is reflected in the auth payload."""
        from src.auth import issue_user_token

        with auth_bp_app.app_context():
            user = UserAccount(
                email="player@example.com",
                display_name="PlayerUser",
                display_name_lower="playeruser",
            )
            db.session.add(user)
            db.session.flush()
            db.session.add(
                PlayerProfileClaim(
                    player_api_id=5001,
                    user_account_id=user.id,
                    relationship_type="player",
                    status="approved",
                )
            )
            db.session.commit()

            token = issue_user_token(user.email)["token"]
            res = auth_bp_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})

            assert res.status_code == 200
            assert res.get_json()["account_role"] == "player"

    def test_auth_me_without_token_returns_401(self, auth_bp_client):
        """Should return 401 without auth token."""
        res = auth_bp_client.get("/api/auth/me")
        assert res.status_code == 401


class TestAccountRoleDerivation:
    """Role labels come only from authoritative, approved self-claims."""

    def test_user_without_claim_defaults_to_scout(self, auth_bp_app):
        with auth_bp_app.app_context():
            user = UserAccount(email="scout@example.com", display_name="Scout", display_name_lower="scout")
            db.session.add(user)
            db.session.commit()

            assert derive_account_role(user) == "scout"

    @pytest.mark.parametrize(
        ("relationship_type", "status"),
        (("player", "pending"), ("agent", "approved")),
    )
    def test_non_player_or_pending_claim_stays_scout(self, auth_bp_app, relationship_type, status):
        with auth_bp_app.app_context():
            user = UserAccount(
                email=f"{relationship_type}-{status}@example.com",
                display_name=f"{relationship_type}-{status}",
                display_name_lower=f"{relationship_type}-{status}",
            )
            db.session.add(user)
            db.session.flush()
            db.session.add(
                PlayerProfileClaim(
                    player_api_id=5002,
                    user_account_id=user.id,
                    relationship_type=relationship_type,
                    status=status,
                )
            )
            db.session.commit()

            assert derive_account_role(user) == "scout"


class TestDisplayName:
    """Tests for POST /auth/display-name endpoint."""

    def test_display_name_validates_uniqueness(self, auth_bp_app, auth_bp_client):
        """Should reject duplicate display names."""
        from src.auth import issue_user_token

        with auth_bp_app.app_context():
            # Create two users
            user1 = UserAccount(
                email="user1@example.com",
                display_name="TakenName",
                display_name_lower="takenname",
                display_name_confirmed=True,
            )
            user2 = UserAccount(
                email="user2@example.com",
                display_name="OtherName",
                display_name_lower="othername",
            )
            db.session.add_all([user1, user2])
            db.session.commit()

            token = issue_user_token("user2@example.com")["token"]

            res = auth_bp_client.post(
                "/api/auth/display-name",
                headers={"Authorization": f"Bearer {token}"},
                json={"display_name": "TakenName"},
            )
            assert res.status_code == 409  # Conflict

    def test_display_name_minimum_length(self, auth_bp_app, auth_bp_client):
        """Should reject display names shorter than 3 characters."""
        from src.auth import issue_user_token

        with auth_bp_app.app_context():
            user = UserAccount(
                email="user@example.com",
                display_name="Current",
                display_name_lower="current",
            )
            db.session.add(user)
            db.session.commit()

            token = issue_user_token("user@example.com")["token"]

            res = auth_bp_client.post(
                "/api/auth/display-name", headers={"Authorization": f"Bearer {token}"}, json={"display_name": "AB"}
            )
            assert res.status_code == 400


class TestAuthStatus:
    """Tests for GET /auth/status endpoint."""

    def test_auth_status_requires_admin_auth(self, auth_bp_client):
        """Should require admin authentication."""
        res = auth_bp_client.get("/api/auth/status")
        assert res.status_code == 401

    def test_auth_status_returns_config_info(self, auth_bp_app, auth_bp_client):
        """Should return authentication configuration status."""
        from src.auth import issue_user_token

        with auth_bp_app.app_context():
            token = issue_user_token("admin@example.com", role="admin")["token"]

            with patch.dict(os.environ, {"ADMIN_API_KEY": "test-key"}):
                res = auth_bp_client.get(
                    "/api/auth/status", headers={"Authorization": f"Bearer {token}", "X-API-Key": "test-key"}
                )
                assert res.status_code == 200
                data = res.get_json()
                assert "api_key_configured" in data
                assert "client_ip" in data
