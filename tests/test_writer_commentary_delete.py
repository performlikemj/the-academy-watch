import os
import sys
from importlib import import_module

import pytest


@pytest.fixture
def app_client(monkeypatch, tmp_path):
    """
    Provide Flask test client with isolated SQLite DB and skipped API handshakes.
    """
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    backend_root = os.path.join(repo_root, "academy-watch-backend")
    if backend_root not in sys.path:
        sys.path.insert(0, backend_root)

    db_file = tmp_path / "test.sqlite"
    monkeypatch.setenv("FLASK_ENV", "production")
    monkeypatch.setenv("SQLALCHEMY_DATABASE_URI", f"sqlite:///{db_file}")
    monkeypatch.setenv("SECRET_KEY", "test-secret")
    monkeypatch.setenv("ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.delenv("ADMIN_IP_WHITELIST", raising=False)

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


def _user_token(app, email):
    from src.routes.api import _user_serializer

    with app.app_context():
        serializer = _user_serializer()
        return serializer.dumps({"email": email, "role": "journalist"})


def _seed_journalist(db, UserAccount, email, display_name, is_journalist=True):
    user = UserAccount(
        email=email,
        display_name=display_name,
        display_name_lower=display_name.lower(),
        is_journalist=is_journalist,
        can_author_commentary=is_journalist,
    )
    db.session.add(user)
    db.session.flush()
    return user


def _seed_team(db, Team, team_id=33, name="Manchester United"):
    team = Team(
        team_id=team_id,
        name=name,
        country="England",
        season=2024,
        newsletters_active=True,
    )
    db.session.add(team)
    db.session.flush()
    return team


def test_writer_can_delete_own_commentary(app_client):
    app, client, db, main = app_client
    from src.models.league import (
        UserAccount,
        Team,
        NewsletterCommentary,
        JournalistTeamAssignment,
    )

    with app.app_context():
        writer = _seed_journalist(db, UserAccount, "writer@example.com", "WriterOne")
        team = _seed_team(db, Team)
        db.session.add(JournalistTeamAssignment(user_id=writer.id, team_id=team.id))
        commentary = NewsletterCommentary(
            author_id=writer.id,
            author_name=writer.display_name,
            team_id=team.id,
            commentary_type="summary",
            content="<p>Great match</p>",
            title="Recap",
        )
        db.session.add(commentary)
        db.session.commit()

        token = _user_token(app, writer.email)
        commentary_id = commentary.id

    resp = client.delete(
        f"/api/writer/commentaries/{commentary_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 200, resp.get_data(as_text=True)

    with app.app_context():
        remaining = NewsletterCommentary.query.filter_by(id=commentary_id).first()
        assert remaining is None


def test_writer_cannot_delete_others_commentary(app_client):
    app, client, db, main = app_client
    from src.models.league import (
        UserAccount,
        Team,
        NewsletterCommentary,
        JournalistTeamAssignment,
    )

    with app.app_context():
        writer = _seed_journalist(db, UserAccount, "writer@example.com", "WriterOne")
        other = _seed_journalist(db, UserAccount, "other@example.com", "Other")
        team = _seed_team(db, Team)
        db.session.add(JournalistTeamAssignment(user_id=other.id, team_id=team.id))
        commentary = NewsletterCommentary(
            author_id=other.id,
            author_name=other.display_name,
            team_id=team.id,
            commentary_type="summary",
            content="<p>Other writeup</p>",
            title="Other recap",
        )
        db.session.add(commentary)
        db.session.commit()

        token = _user_token(app, writer.email)
        commentary_id = commentary.id

    resp = client.delete(
        f"/api/writer/commentaries/{commentary_id}",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert resp.status_code == 403

    with app.app_context():
        remaining = NewsletterCommentary.query.filter_by(id=commentary_id).first()
        assert remaining is not None
