# ruff: noqa: F811
"""Staging polish uses authenticated applicant evidence and preserves public DTOs."""

from datetime import timedelta

import pytest
from src.models.league import UserAccount, db
from src.models.opportunities import ApplicationEvent, ClubOpportunity, now
from src.models.p2_foundation import NotificationOutbox
from src.services import opportunities as service
from test_opportunities import _headers, apply, client, club_app, create, env, move  # noqa: F401


def context(client, env, row, person="adult"):
    return client.get(
        f"/api/me/application-claims?opportunity_id={row['id']}", headers=env["people"][person]["headers"]
    )


def test_private_context_matches_duplicate_and_invitation_rules(client, env):
    row = create(client, env)
    assert context(client, env, row).get_json()["claims"][0]["application"] is None
    app = apply(client, env, row).get_json()["application"]
    app = move(client, env, app, "shortlisted").get_json()["application"]
    app = move(
        client,
        env,
        app,
        "invited",
        trial_at=service.iso(now() + timedelta(days=10)),
        trial_venue="Private trial venue",
        trial_instructions="Private next step",
    ).get_json()["application"]
    claim = context(client, env, row).get_json()["claims"][0]
    assert claim["application"]["id"] == app["id"]
    assert claim["application"]["status"] == "invited"
    assert claim["application"]["trial_instructions"] == "Private next step"
    assert claim["profile_path"] == f"/local-players/{env['people']['adult']['local']}"
    assert apply(client, env, row).status_code == 409
    assert context(client, env, row, "adult2").get_json()["claims"][0]["application"] is None
    public = client.get(f"/api/opportunities/{row['id']}").get_json()["opportunity"]
    assert (
        not {"application", "claim_id", "applicant_name", "trial_instructions", "outside_age_band", "profile_path"}
        & public.keys()
    )


@pytest.mark.parametrize(
    "minimum,maximum,outside", [(2001, 2008, True), (1990, 1999, True), (2000, 2000, False), (None, None, False)]
)
def test_private_age_hint_matches_submission(client, env, minimum, maximum, outside):
    row = create(client, env, birth_year_min=minimum, birth_year_max=maximum)
    claim = context(client, env, row).get_json()["claims"][0]
    assert claim["outside_age_band"] is outside
    response = apply(client, env, row)
    assert response.status_code == (403 if outside else 201)
    if outside:
        assert response.get_json()["error"] == "outside_age_band"


def test_context_auth_minor_hidden_and_dark_boundaries(client, env, monkeypatch):
    row = create(client, env)
    assert client.get(f"/api/me/application-claims?opportunity_id={row['id']}").status_code == 401
    for person in ("minor", "guardian", "pending", "unknown", "year18"):
        assert context(client, env, row, person).get_json()["claims"] == []
    for flag in ("APPLICATIONS_ENABLED", "OPPORTUNITIES_ENABLED"):
        monkeypatch.setenv(flag, "false")
        assert client.get(f"/api/me/application-claims?opportunity_id={row['id']}").status_code == 404
        monkeypatch.setenv(flag, "true")
    posting = db.session.get(ClubOpportunity, row["id"])
    posting.status = "draft"
    db.session.commit()
    assert context(client, env, row).status_code == 404


def test_recruiting_published_recent_activity_first_drafts_last(client, env):
    older = create(client, env, title="Older published")
    newer = create(client, env, title="Newer published")
    draft = create(client, env, title="Latest empty draft", status="draft")
    row = db.session.get(ClubOpportunity, older["id"])
    row.updated_at = now() - timedelta(days=1)
    db.session.commit()
    app = apply(client, env, older).get_json()["application"]
    event = ApplicationEvent.query.filter_by(application_id=app["id"]).one()
    event.created_at = now() + timedelta(seconds=1)
    db.session.commit()
    result = client.get(f"/api/club/{env['pid']}/opportunities", headers=_headers("a")).get_json()["opportunities"]
    assert [r["id"] for r in result] == [older["id"], newer["id"], draft["id"]]
    # Ordering runs before pagination, not just on the first thirty returned rows.
    for n in range(31):
        create(client, env, title=f"Draft {n}", status="draft")
    response = client.get(f"/api/club/{env['pid']}/opportunities", headers=_headers("a")).get_json()
    assert response["has_more"] and response["opportunities"][0]["id"] == older["id"]


def test_new_applicant_email_has_club_subject_and_no_pii(client, env):
    row = create(client, env)
    apply(client, env, row)
    for intent in NotificationOutbox.query.all():
        user = db.session.get(UserAccount, intent.recipient_user_id)
        rendered = service.notification_render(intent, user)
        assert rendered["subject"] == (
            "Your application update" if user.id == env["people"]["adult"]["user"] else "New player application"
        )
        assert "Test Player" not in str(rendered) and "b2-adult" not in str(rendered)
        assert set(intent.payload) <= {"application_id", "version", "state"}
