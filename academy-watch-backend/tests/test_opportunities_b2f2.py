"""RB2V regressions: reversible holds, bounded IDs, modern zones and follow-up."""

# ruff: noqa: F811
import json
from datetime import timedelta
from pathlib import Path
from zoneinfo import available_timezones

import pytest
from src.models.funding import ClubProgram
from src.models.league import db
from src.models.opportunities import ApplicationEvent, OpportunityApplication, now
from src.services import opportunities as service
from src.services.opportunities_account import purge_retained
from test_opportunities import _headers, apply, client, club_app, create, env, move  # noqa: F401
from test_opportunities_rb2 import invalidate


@pytest.mark.parametrize("read", ["board", "detail", "mine", "postings", "sweep"])
def test_subject_hold_preserves_invitation_and_restores_pipeline(client, env, read):
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    app = move(client, env, app, "shortlisted").get_json()["application"]
    app = move(client, env, app, "invited", trial_at=row["starts_at"], trial_venue="Ground").get_json()["application"]
    stored = db.session.get(OpportunityApplication, app["id"])
    before = (stored.status, stored.version, stored.reservation_state, stored.trial_at, stored.retention_expires_at)
    count = ApplicationEvent.query.count()
    invalidate(env, app, "held")
    if read == "board":
        assert (
            client.get(
                f"/api/club/{env['pid']}/opportunities/{row['id']}/applications", headers=_headers("a")
            ).get_json()["applications"]
            == []
        )
    elif read == "detail":
        assert client.get(f"/api/club/{env['pid']}/applications/{app['id']}", headers=_headers("a")).status_code == 404
    elif read == "mine":
        assert (
            client.get(f"/api/me/applications/{app['id']}", headers=env["people"]["adult"]["headers"]).get_json()[
                "application"
            ]["status"]
            == "invited"
        )
    elif read == "postings":
        assert (
            client.get(f"/api/club/{env['pid']}/opportunities", headers=_headers("a")).get_json()["opportunities"][0][
                "places_left"
            ]
            == 0
        )
    else:
        assert purge_retained(at=now() + timedelta(days=2))["applications"] == 0
        db.session.commit()
    for action in ("notes", "transition"):
        response = client.post(
            f"/api/club/{env['pid']}/applications/{app['id']}/{action}",
            headers=_headers("a"),
            json={"body": "private", "status": "rejected", "expected_version": app["version"]},
        )
        assert response.status_code == 404 and response.get_json() == {"error": "Not found"}
    assert (
        client.post(
            f"/api/me/applications/{app['id']}/trial-response",
            headers=env["people"]["adult"]["headers"],
            json={"expected_version": app["version"], "response": "accept"},
        ).status_code
        == 403
    )
    stored = db.session.get(OpportunityApplication, app["id"])
    assert (
        stored.status,
        stored.version,
        stored.reservation_state,
        stored.trial_at,
        stored.retention_expires_at,
    ) == before
    assert ApplicationEvent.query.count() == count
    db.session.get(ClubProgram, env["other"]).emergency_hidden = False
    db.session.commit()
    board = client.get(
        f"/api/club/{env['pid']}/opportunities/{row['id']}/applications", headers=_headers("a")
    ).get_json()["applications"]
    assert len(board) == 1 and board[0]["status"] == "invited" and board[0]["version"] == app["version"]


@pytest.mark.parametrize("cause", ["minor", "unknown", "revoked", "suppressed"])
@pytest.mark.parametrize("action", ["notes", "transition"])
def test_actions_reconcile_permanent_failure_and_return_neutral_404(client, env, cause, action):
    row = create(client, env)
    app = apply(client, env, row).get_json()["application"]
    app = move(client, env, app, "shortlisted").get_json()["application"]
    app = move(client, env, app, "invited", trial_at=row["starts_at"], trial_venue="Ground").get_json()["application"]
    invalidate(env, app, "held")  # A concurrent hold must not mask permanent failure.
    invalidate(env, app, cause)
    response = client.post(
        f"/api/club/{env['pid']}/applications/{app['id']}/{action}",
        headers=_headers("a"),
        json={"body": "private", "status": "rejected", "expected_version": 1},
    )
    assert response.status_code == 404 and response.get_json() == {"error": "Not found"}
    stored = db.session.get(OpportunityApplication, app["id"])
    assert stored.status == "rejected" and stored.reservation_state == "released" and stored.trial_at is None
    assert stored.retention_expires_at <= now() + timedelta(days=7)
    assert ApplicationEvent.query.filter_by(application_id=app["id"], reason_code="profile_unavailable").count() == 1


@pytest.mark.parametrize("value", ["99999999999999999999", "2147483648", "-1", "0", "bad"])
def test_public_program_id_out_of_range_is_400(client, env, value):
    response = client.get(f"/api/opportunities?program_id={value}")
    assert response.status_code == 400 and response.get_json() == {"error": "invalid_program_id"}


@pytest.mark.parametrize(
    "zone", ["Asia/Kolkata", "Europe/Kyiv", "America/Indiana/Indianapolis", "Asia/Kathmandu", "Pacific/Kanton"]
)
def test_current_iana_names_are_accepted(client, env, zone):
    assert create(client, env, timezone=zone)["timezone"] == zone


def test_allowlist_is_runtime_intersection_with_browser_snapshot_and_aliases():
    data = Path(service.__file__).parents[1] / "data"
    snapshot = json.loads((data / "opportunity_timezone_browser_snapshot.json").read_text())
    aliases = json.loads((data / "opportunity_timezone_aliases.json").read_text())
    assert available_timezones() & (set(snapshot) | set(aliases) | {"UTC"}) == service.TIMEZONES
    assert set(aliases.values()) <= set(snapshot) | {"UTC"}


@pytest.mark.parametrize("offset,accepted", [(14, True), (15, False)])
def test_position_followup_at_close_plus_14_and_privacy_cap(client, env, offset, accepted):
    row = create(
        client, env, type="position", starts_at=None, ends_at=None, closes_at=service.iso(now() + timedelta(days=89))
    )
    app = apply(client, env, row).get_json()["application"]
    stored = db.session.get(OpportunityApplication, app["id"])
    stored.submitted_at += timedelta(days=20)  # Simulate intake later in the advertised window.
    db.session.commit()
    app = move(client, env, app, "shortlisted").get_json()["application"]
    result = move(
        client,
        env,
        app,
        "invited",
        trial_at=service.iso(service.timestamp(row["closes_at"], "close") + timedelta(days=offset)),
        trial_venue="Ground",
    )
    assert result.status_code == (200 if accepted else 422)
    if accepted:
        assert result.get_json()["application"]["reservation_state"] == "pending"


def test_trial_after_creation_horizon_still_requires_privacy_cap(client, env):
    row = create(
        client, env, type="position", starts_at=None, ends_at=None, closes_at=service.iso(now() + timedelta(days=89))
    )
    app = apply(client, env, row).get_json()["application"]
    app = move(client, env, app, "shortlisted").get_json()["application"]
    assert (
        move(
            client, env, app, "invited", trial_at=service.iso(now() + timedelta(days=95)), trial_venue="Ground"
        ).status_code
        == 422
    )
    stored = db.session.get(OpportunityApplication, app["id"])
    stored.submitted_at += timedelta(days=10)
    db.session.commit()
    assert (
        move(
            client, env, app, "invited", trial_at=service.iso(now() + timedelta(days=95)), trial_venue="Ground"
        ).status_code
        == 200
    )
