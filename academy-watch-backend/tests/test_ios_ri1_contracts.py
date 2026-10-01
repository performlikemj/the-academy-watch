# ruff: noqa: F401, F811
"""Native RI1: independently gated recruiting probes and exact private date bounds."""

from datetime import timedelta

from src.models.league import db
from src.models.opportunities import ClubOpportunity
from src.routes.club_access import club_access_bp
from src.services import opportunities as service
from test_club_console import _headers, client, club_app
from test_opportunities import create, env


def test_recruiting_access_probe_without_staff_admin(client, club_app, env, monkeypatch):
    club_app.register_blueprint(club_access_bp, url_prefix="/api")
    monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "false")
    base = f"/api/club/{env['pid']}/access"
    response = client.get(base + "/me", headers=_headers("a"))
    assert response.status_code == 200
    access = response.get_json()["access"]
    assert "recruiting" in access["capabilities"]
    assert client.get(base, headers=_headers("a")).status_code == 404
    assert client.get(base + "/me", headers=_headers("b")).status_code == 403
    assert client.get(base + "/me").status_code == 401
    monkeypatch.setenv("OPPORTUNITIES_ENABLED", "false")
    assert client.get(base + "/me", headers=_headers("a")).status_code == 404
    assert client.get(base + "/me").status_code == 404


def test_private_trial_invite_deadline_matches_server_rules(client, env):
    trial = create(client, env)
    row = db.session.get(ClubOpportunity, trial["id"])
    assert trial["trial_invite_deadline"] == service.iso(row.created_at + timedelta(days=90))
    public = client.get(f"/api/opportunities/{row.id}").get_json()["opportunity"]
    assert "trial_invite_deadline" not in public
    position = create(client, env, type="position", starts_at=None, ends_at=None)
    row = db.session.get(ClubOpportunity, position["id"])
    assert position["trial_invite_deadline"] == service.iso(row.closes_at + timedelta(days=14))
