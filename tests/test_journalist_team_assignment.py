import os
import sys
from importlib import import_module

import pytest


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    """
    Configure the Flask app to use an isolated SQLite database and
    return the app, client, and db session for tests.
    """
    # Ensure backend package is importable
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    backend_root = os.path.join(repo_root, "academy-watch-backend")
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    # Isolate DB + secrets for test
    db_file = tmp_path / "test.sqlite"
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", f"sqlite:///{db_file}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.delenv("ADMIN_IP_WHITELIST", raising=False)

    # Fresh import so config/env is picked up
    sys.modules.pop("src.main", None)
    main = import_module("src.main")

    app = main.app
    db = main.db
    app.config.update(TESTING=True)

    with app.app_context():
        db.drop_all()
        db.create_all()

    with app.test_client() as client:
        yield app, client, db, main


def _admin_token(app):
    """Create a short-lived admin token that passes require_api_key."""
    from src.routes.api import _user_serializer

    with app.app_context():
        return _user_serializer().dumps(
            {"email": "admin@example.com", "role": "admin", "user_id": 0}
        )


def test_assign_teams_uses_api_team_ids_not_db_ids(app_client):
    """
    When an admin assigns teams using API team_ids, the correct club should be linked
    even if another record happens to share that database primary key.
    """
    app, client, db, main = app_client
    from src.models.league import (
        JournalistTeamAssignment,
        Team,
        UserAccount,
    )

    with app.app_context():
        journalist = UserAccount(
            email="writer@example.com",
            display_name="WriterOne",
            display_name_lower="writerone",
            is_journalist=True,
            can_author_commentary=True,
        )

        # Manchester United – api team_id 33 (latest season id intentionally NOT 33)
        manu_latest = Team(
            id=101,
            team_id=33,
            name="Manchester United",
            country="England",
            season=2024,
            newsletters_active=True,
        )
        # Another club whose *database id* collides with the api team_id above
        getafe = Team(
            id=33,
            team_id=82,
            name="Getafe",
            country="Spain",
            season=2024,
            newsletters_active=True,
        )

        db.session.add_all([journalist, manu_latest, getafe])
        db.session.commit()

        journalist_id = journalist.id
        token = _admin_token(app)

    resp = client.post(
        f"/api/journalists/{journalist_id}/assign-teams",
        json={"team_ids": [33]},  # api team_id for Manchester United
        headers={
            "Authorization": f"Bearer {token}",
            "X-API-Key": "test-admin-key",
        },
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)

    with app.app_context():
        assignments = JournalistTeamAssignment.query.filter_by(
            user_id=journalist_id
        ).all()
        assert len(assignments) == 1

        assigned_team = Team.query.get(assignments[0].team_id)
        assert assigned_team.team_id == 33
        assert assigned_team.name == "Manchester United"
