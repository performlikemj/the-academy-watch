# ruff: noqa: F811, F401
"""C1F5: reverse the final duel's search, title, outcome and contention probes."""

from datetime import date
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError
from src.models.club_player_publication import ClubPlayerPublication as Publication
from src.models.contact import ContactAuditEvent, ContactOutcome, ContactRequest
from src.models.funding import ClubProgram
from src.models.league import Team, UserAccount, db
from src.models.showcase import LocalPlayer
from src.models.tracked_player import TrackedPlayer
from src.services import club_player_publication as service
from test_club_player_publication import _headers, client, club_app, env, published
from test_club_publication_rc1 import introduction
from test_club_publication_rc1v import seed_publication, suppress


@pytest.mark.parametrize("community", ["true", "false"])
@pytest.mark.parametrize("providers", [3, 9])
def test_club_search_membership_and_one_cap(client, env, monkeypatch, community, providers):
    monkeypatch.setenv("SCOUT_INCLUDE_LOCAL_PLAYERS", community)
    locals = [seed_publication(env, i)[0] for i in range(10)]
    for i in range(providers):
        db.session.add(
            TrackedPlayer(
                player_api_id=80000 + i,
                player_name=f"C1 search fixture provider {i}",
                birth_date="2000-01-01",
                is_active=True,
                team_id=db.session.query(Team.id).first()[0],
                data_source="fixture",
            )
        )
    db.session.commit()
    rows = client.get("/api/players/search?q=C1%20search%20fixture").json
    assert [r["player_api_id"] for r in rows] == [-p.id for p in locals[:8]]
    assert len({r["player_api_id"] for r in rows}) == len(rows) == 8


def grant(client, cid):
    response = client.post(f"/api/contact/requests/{cid}/club-consent", headers=_headers("a"), json={"action": "grant"})
    assert response.status_code == 200, response.json


@pytest.mark.parametrize(
    "state",
    [
        "waiting",
        "granted",
        "accepted",
        "withdrawn",
        "revoked",
        "held",
        "suppressed",
        "flag_off",
        "claim_changed",
        "program_changed",
        "expired",
        "scout_withdrawn",
    ],
)
def test_public_title_is_pinned_and_never_account_identity(client, env, monkeypatch, state):
    result = published(client, env)
    local = db.session.get(LocalPlayer, env["local"])
    local.display_name = "Distinct public profile title"
    person = db.session.get(UserAccount, env["player"])
    person.display_name = "Private account name"
    db.session.commit()
    cid = introduction(client, env)
    contact = db.session.get(ContactRequest, cid)
    publication = db.session.get(Publication, result["id"])
    if state in {"granted", "accepted"}:
        grant(client, cid)
        if state == "accepted":
            assert client.post(f"/api/contact/requests/{cid}/accept", headers=env["ph"]).status_code == 200
    elif state in {"withdrawn", "revoked"}:
        service.revoke(publication, club=state == "revoked")
    elif state == "held":
        db.session.get(ClubProgram, env["pid"]).emergency_hidden = True
    elif state == "suppressed":
        suppress(env["local"])
    elif state == "flag_off":
        monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    elif state == "claim_changed":
        contact.claim_id = None
    elif state == "program_changed":
        contact.club_program_id = None
    elif state in {"expired", "scout_withdrawn"}:
        contact.status = "expired" if state == "expired" else "withdrawn"
    db.session.commit()
    sent = client.get("/api/contact/requests?box=sent", headers=_headers("scout")).json["requests"][0]
    from src.routes.contact import _contact_request_payload

    detail = _contact_request_payload(contact, viewer_user_id=client.application.c2["users"]["scout"])
    for data in (sent, detail):
        if state in {"waiting", "granted", "accepted"}:
            assert data["public_profile"] == {"display_name": local.display_name, "player_api_id": -local.id}
        else:
            assert "public_profile" not in data
        if state not in {"granted", "accepted"}:
            assert data["participants"]["player"] == {"display_name": "Unavailable"}
            assert "Private account name" not in str(data)


@pytest.mark.parametrize(
    "state",
    [
        "waiting",
        "granted",
        "accepted",
        "accepted_without_grant",
        "withdrawn",
        "revoked",
        "held",
        "suppressed",
        "flag_off",
        "expired",
    ],
)
def test_club_outcomes_require_both_permissions_and_availability(client, env, monkeypatch, state):
    result = published(client, env)
    cid = introduction(client, env)
    contact = db.session.get(ContactRequest, cid)
    if state != "waiting":
        grant(client, cid)
    if state in {"accepted", "accepted_without_grant", "held", "suppressed", "flag_off", "expired"}:
        assert client.post(f"/api/contact/requests/{cid}/accept", headers=env["ph"]).status_code == 200
    if state == "accepted_without_grant":
        contact.club_consent_status = "pending"
    elif state in {"withdrawn", "revoked"}:
        service.revoke(db.session.get(Publication, result["id"]), club=state == "revoked")
    elif state == "held":
        db.session.get(ClubProgram, env["pid"]).emergency_hidden = True
    elif state == "suppressed":
        suppress(env["local"])
    elif state == "flag_off":
        monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    elif state == "expired":
        contact.status = "expired"
    db.session.commit()
    before = ContactAuditEvent.query.filter_by(contact_request_id=cid).count()
    response = client.post(
        f"/api/contact/requests/{cid}/outcome", headers=_headers("scout"), json={"stage": "contacted"}
    )
    allowed = state == "accepted"
    assert response.status_code == (201 if allowed else 409), response.json
    assert ContactOutcome.query.filter_by(contact_request_id=cid).count() == int(allowed)
    assert ContactAuditEvent.query.filter_by(contact_request_id=cid).count() == before + int(allowed)
    if not allowed:
        assert response.json["code"] == "outcome_unavailable"


@pytest.mark.parametrize("sqlstate,status", [("40P01", 409), ("40001", 409), ("55P03", 503)])
def test_publication_database_contention_is_retryable(client, env, monkeypatch, sqlstate, status):
    def contention(*args, **kwargs):
        raise OperationalError("private SQL", {}, SimpleNamespace(sqlstate=sqlstate))

    monkeypatch.setattr(service, "invite", contention)
    response = client.post(
        f"/api/club/{env['pid']}/players/{env['local']}/publication-invite",
        headers=_headers("a"),
        json={"recipient_email": "fixture@example.test"},
    )
    assert response.status_code == status, response.json
    assert response.json == {"error": "publication_conflict" if status == 409 else "publication_busy"}
    assert db.session.execute(db.select(db.literal(1))).scalar() == 1


@pytest.mark.parametrize("community", ["true", "false"])
def test_search_normalized_insert_keeps_provider_order_and_unique_ids(client, env, monkeypatch, community):
    monkeypatch.setenv("SCOUT_INCLUDE_LOCAL_PLAYERS", community)
    club1, _ = seed_publication(env, 0)
    club2, _ = seed_publication(env, 1)
    club1.display_name, club2.display_name = "Needle B club", "Needle D club"
    provider_names = ["Needle A provider", "Needle C provider", "Needle Z provider"]
    team_id = db.session.query(Team.id).first()[0]
    for i, name in enumerate(provider_names):
        db.session.add(
            TrackedPlayer(
                player_api_id=81000 + i,
                player_name=name,
                birth_date="2000-01-01",
                is_active=True,
                team_id=team_id,
                data_source="fixture",
            )
        )
    # One eligible community row sorts ahead of the club row; it is absent OFF.
    local = LocalPlayer(
        display_name="Needle A community", birth_date=date(2000, 1, 1), status="approved", provenance="user"
    )
    db.session.add(local)
    db.session.flush()
    local.api_player_id = -local.id
    db.session.commit()
    rows = client.get("/api/players/search?q=Needle").json
    ids = [r["player_api_id"] for r in rows]
    expected = [81000, -club1.id, 81001, -club2.id, 81002]
    if community == "true":
        expected.insert(0, -local.id)
    assert ids == expected
    assert len(set(ids)) == len(ids)
    assert [i for i in ids if i > 0] == [81000, 81001, 81002]


@pytest.mark.parametrize("sqlstate,status", [("40P01", 409), ("40001", 409), ("55P03", 503)])
def test_introduction_database_contention_is_retryable(client, env, monkeypatch, sqlstate, status):
    published(client, env)

    def contention(*args, **kwargs):
        raise OperationalError("private SQL", {}, SimpleNamespace(sqlstate=sqlstate))

    monkeypatch.setattr(service, "lock_introduction_publication", contention)
    response = client.post(
        "/api/contact/requests", headers=_headers("scout"), json={"player_api_id": -env["local"], "message": "Fixture"}
    )
    assert response.status_code == status, response.json
    assert response.json == {"error": "publication_conflict" if status == 409 else "publication_busy"}
    assert ContactRequest.query.count() == 0
