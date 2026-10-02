# ruff: noqa: F811, F401
"""C1F4: reviewer probes reversed at every response and retirement boundary."""

import ast
from pathlib import Path

import pytest
from src.models.club_player_publication import ClubPlayerPublication as Publication
from src.models.club_player_publication import RetiredClubShowcase
from src.models.contact import ContactRequest
from src.models.follow import PlayerShadow
from src.models.funding import ClubProgram
from src.models.league import PlayerLink, UserAccount, db
from src.models.showcase import LocalPlayer, PlayerClubAffiliation, PlayerProfileClaim
from src.services import club_player_publication as service
from src.services.account import build_account_export, delete_account
from src.services.public_adult import public_adult_ids
from test_club_player_publication import _headers, client, club_app, env, published
from test_club_publication_rc1 import introduction
from test_club_publication_rc1v import suppress


def next_claimant(client, env, version=None):
    person = UserAccount(
        email="c1f4-new@example.test", display_name="Fresh claimant", display_name_lower="fresh claimant"
    )
    db.session.add(person)
    db.session.commit()
    payload = {"recipient_email": person.email}
    if version is not None:
        payload["expected_version"] = version
    row, token = service.invite(env["pid"], env["local"], client.application.c2["users"]["a"], payload)
    service.redeem(person, {"token": token, "self_claim": True})
    service.consent(
        row,
        person.id,
        {"expected_version": row.version, "public_profile_consent": True, "consent_version": service.CONSENT_VERSION},
    )
    service.review(
        row,
        "reviewer",
        {"expected_version": row.version, "action": "approve", "reason": "Fresh independent identity review"},
    )
    db.session.commit()
    return person, row


@pytest.mark.parametrize("action", ["create", "duplicate", "withdraw", "outcome", "revoke", "messages"])
def test_never_granted_response_identity(client, env, action):
    published(client, env)
    payload = {"player_api_id": -env["local"], "message": "Scout authored pitch"}
    if action == "create":
        response = client.post("/api/contact/requests", headers=_headers("scout"), json=payload)
    else:
        cid = introduction(client, env)
        if action == "duplicate":
            response = client.post("/api/contact/requests", headers=_headers("scout"), json=payload)
        elif action == "messages":
            response = client.get(f"/api/contact/requests/{cid}/messages", headers=_headers("scout"))
        else:
            response = client.post(
                f"/api/contact/requests/{cid}/{action}", headers=_headers("scout"), json={"stage": "contacted"}
            )
    assert (
        response.status_code
        == {"create": 201, "duplicate": 409, "withdraw": 200, "outcome": 201, "revoke": 200, "messages": 409}[action]
    ), response.json
    if action == "messages":
        assert "contact_request" not in response.json
    else:
        assert response.json["contact_request"]["participants"]["player"] == {"display_name": "Unavailable"}


def test_every_contact_serializer_call_identifies_viewer():
    calls = []
    for source in (Path(__file__).parents[1] / "src").rglob("*.py"):
        tree = ast.parse(source.read_text())
        names = {"_contact_request_payload"}
        names.update(
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
            if alias.name == "_contact_request_payload"
        )
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and (
                (isinstance(node.func, ast.Name) and node.func.id in names)
                or (isinstance(node.func, ast.Attribute) and node.func.attr == "_contact_request_payload")
            ):
                calls.append((source, node))
    assert len(calls) >= 12
    assert any(source.name == "club_player_profile.py" for source, _ in calls)
    assert not [
        f"{source}:{call.lineno}"
        for source, call in calls
        if not any(keyword.arg == "viewer_user_id" for keyword in call.keywords)
    ]


@pytest.mark.parametrize("action", ["outcome", "withdraw"])
def test_retained_dark_never_granted_mutation_identity(client, env, monkeypatch, action):
    published(client, env)
    cid = introduction(client, env)
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    response = client.post(
        f"/api/contact/requests/{cid}/{action}", headers=_headers("scout"), json={"stage": "contacted"}
    )
    assert response.status_code == (201 if action == "outcome" else 200)
    assert response.json["contact_request"]["participants"]["player"] == {"display_name": "Unavailable"}


@pytest.mark.parametrize(
    "state",
    [
        "available",
        "never_granted",
        "withdrawn",
        "revoked",
        "rejected",
        "flag_off",
        "suspended",
        "held",
        "suppressed",
        "declined",
        "expired",
        "scout_withdrawn",
    ],
)
def test_scout_club_note_visibility(client, env, monkeypatch, state):
    result = published(client, env)
    cid = introduction(client, env)
    note = "Club authored note with private player context"
    if state != "never_granted":
        reply = client.post(
            f"/api/contact/requests/{cid}/club-consent",
            headers=_headers("a"),
            json={"action": "decline" if state == "declined" else "grant", "note": note},
        )
        assert reply.status_code == 200, reply.json
    else:
        db.session.get(ContactRequest, cid).club_consent_note = note
    row = db.session.get(Publication, result["id"])
    if state in ("withdrawn", "revoked"):
        service.revoke(row, club=state == "revoked")
    elif state == "rejected":
        service.review(
            row, "reviewer", {"expected_version": row.version, "action": "reject", "reason": "Independent rejection"}
        )
    elif state == "flag_off":
        monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    elif state == "suspended":
        db.session.get(UserAccount, env["player"]).account_status = "suspended"
    elif state == "held":
        db.session.get(ClubProgram, env["pid"]).emergency_hidden = True
    elif state == "suppressed":
        suppress(env["local"])
    elif state in ("expired", "scout_withdrawn"):
        db.session.get(ContactRequest, cid).status = "expired" if state == "expired" else "withdrawn"
    db.session.commit()
    sent = client.get("/api/contact/requests?box=sent", headers=_headers("scout")).json["requests"][0]
    scout = db.session.get(UserAccount, client.application.c2["users"]["scout"])
    exported = build_account_export(scout)["contact_requests"]["sent"][0]
    expected = note if state in ("available", "declined") else None
    for data in (sent, exported):
        assert data["club_consent_note"] == expected
        if state != "available":
            assert data["participants"]["player"] == {"display_name": "Unavailable"}
    # Player and club keep their own history under the separate participant policy.
    player = db.session.get(UserAccount, env["player"])
    assert db.session.get(ContactRequest, cid).to_dict(viewer_user_id=player.id)["club_consent_note"] == note


@pytest.mark.parametrize("club_fact", [False, True])
def test_retirement_quarantines_self_reports_and_rebuilds_season(client, env, club_fact):
    from datetime import date

    from src.models.player_match_entry import PlayerMatchEntry
    from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal

    result = published(client, env)
    if club_fact:
        db.session.add(
            PlayerMatchEntry(
                player_api_id=-env["local"],
                season=2026,
                source="club",
                status="club_confirmed",
                reported_by_user_id=client.application.c2["users"]["a"],
                club_program_id=env["pid"],
                match_date=date(2026, 9, 2),
                opponent="Verified club fact",
                home_away="home",
                minutes=60,
                goals=1,
            )
        )
        db.session.commit()
    path = f"/api/players/{-env['local']}/matches"
    response = client.post(
        path,
        headers=env["ph"],
        json={
            "match_date": "2026-09-01",
            "opponent": "Former claimant opponent",
            "home_away": "home",
            "minutes": 90,
            "goals": 3,
            "note": "Former claimant private note",
        },
    )
    assert response.status_code == 201, response.json
    assert PlayerSeasonCell.query.filter_by(player_api_id=-env["local"], source="user").count() > 0
    row = db.session.get(Publication, result["id"])
    service.revoke(row, club=True)
    db.session.commit()
    assert PlayerMatchEntry.query.filter_by(player_api_id=-env["local"], source="self").count() == 0
    assert PlayerSeasonCell.query.filter_by(player_api_id=-env["local"], source="user").count() == 0
    person, _ = next_claimant(client, env, row.version)
    public = client.get(path)
    assert public.status_code == 200 and public.json["total"] == (1 if club_fact else 0)
    totals = PlayerSeasonTotal.query.filter_by(player_api_id=-env["local"]).all()
    if club_fact:
        assert len(totals) == 1 and totals[0].minutes == 60 and totals[0].goals == 1
    else:
        assert totals == []
    assert "Former claimant" not in str(public.json)
    old = build_account_export(db.session.get(UserAccount, env["player"]))
    assert "Former claimant private note" in str(old["retired_club_showcases"])
    assert "Former claimant private note" not in str(build_account_export(person))


def test_erasure_allows_canonical_club_namespace_reapproval(client, env, monkeypatch):
    published(client, env)
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    delete_account(db.session.get(UserAccount, env["player"]))
    db.session.commit()
    assert Publication.query.count() == 0
    assert PlayerProfileClaim.query.filter_by(local_player_id=env["local"]).count() == 0
    assert PlayerShadow.query.filter_by(player_api_id=-env["local"]).count() == 1
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "true")
    next_claimant(client, env)
    assert public_adult_ids([-env["local"]]) == {-env["local"]}


@pytest.mark.parametrize("kind", ["link", "affiliation"])
@pytest.mark.parametrize("legacy", [False, True])
@pytest.mark.parametrize("other_first", [False, True])
def test_retired_archives_stay_with_each_author(client, env, monkeypatch, kind, legacy, other_first):
    result = published(client, env)
    other = client.application.c2["users"]["b"]
    content = "https://example.test/another-authors-evidence"
    if kind == "link":
        item = PlayerLink(
            local_player_id=env["local"], user_id=other, url=content, link_type="article", status="pending"
        )
    else:
        item = PlayerClubAffiliation(
            local_player_id=env["local"],
            created_by_user_id=other,
            team_api_id=7001,
            status="club_confirmed",
            review_note=content,
        )
    db.session.add(item)
    db.session.commit()
    if legacy:
        snapshot = {
            c.name: value.isoformat() if hasattr(value, "isoformat") else value
            for c in item.__table__.columns
            if (value := getattr(item, c.name)) is not None
        }
        db.session.add(
            RetiredClubShowcase(
                local_player_id=env["local"],
                claim_id=result["claim_id"]
                if "claim_id" in result
                else db.session.get(Publication, result["id"]).claim_id,
                user_account_id=env["player"],
                content={item.__tablename__: [snapshot]},
            )
        )
        db.session.delete(item)
    else:
        service.revoke(db.session.get(Publication, result["id"]), club=True)
    db.session.commit()
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    if other_first:
        assert content in str(build_account_export(db.session.get(UserAccount, other)))
    old = build_account_export(db.session.get(UserAccount, env["player"]))
    assert content not in str(old)
    authored = build_account_export(db.session.get(UserAccount, other))["retired_club_showcases"]
    assert content in str(authored)
    assert "user_id" not in str(authored) and "reviewed_by" not in str(authored)
    assert type(item).query.filter_by(local_player_id=env["local"]).count() == 0
    # Erasing the former claimant cannot erase somebody else's retained evidence.
    delete_account(db.session.get(UserAccount, env["player"]))
    db.session.commit()
    assert content in str(build_account_export(db.session.get(UserAccount, other))["retired_club_showcases"])
    delete_account(db.session.get(UserAccount, other))
    db.session.commit()
    assert RetiredClubShowcase.query.count() == 0


@pytest.mark.parametrize("conflict", ["missing_audit", "foreign_signed_claim", "different_shadow"])
def test_erasure_reapproval_does_not_waive_namespace_collisions(client, env, conflict):
    import sqlalchemy as sa
    from src.models.p2_foundation import AdminActionEvent

    published(client, env)
    delete_account(db.session.get(UserAccount, env["player"]))
    db.session.commit()
    if conflict == "missing_audit":
        # Fixture-only removal of provenance; production audit history is append-only.
        db.session.execute(
            sa.delete(AdminActionEvent).where(AdminActionEvent.action == "club_player_publication_review")
        )
    elif conflict == "foreign_signed_claim":
        db.session.add(
            PlayerProfileClaim(
                player_api_id=-env["local"],
                user_account_id=client.application.c2["users"]["b"],
                relationship_type="player",
                status="approved",
            )
        )
    else:
        PlayerShadow.query.filter_by(player_api_id=-env["local"]).one().player_name = "An unrelated legacy identity"
    db.session.commit()
    with pytest.raises(service.PublicationError, match="identity_review_required"):
        next_claimant(client, env)
    assert not public_adult_ids([-env["local"]])


@pytest.mark.parametrize("state", ["flag_off", "withdrawn", "held", "suppressed"])
def test_decline_exemption_does_not_survive_other_unavailability(client, env, monkeypatch, state):
    result = published(client, env)
    cid = introduction(client, env)
    note = "A plain club decline stays visible only while the publication is eligible"
    assert (
        client.post(
            f"/api/contact/requests/{cid}/club-consent", headers=_headers("a"), json={"action": "decline", "note": note}
        ).status_code
        == 200
    )
    if state == "flag_off":
        monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    elif state == "withdrawn":
        service.revoke(db.session.get(Publication, result["id"]))
    elif state == "held":
        db.session.get(ClubProgram, env["pid"]).emergency_hidden = True
    else:
        suppress(env["local"])
    db.session.commit()
    sent = client.get("/api/contact/requests?box=sent", headers=_headers("scout")).json["requests"][0]
    scout = db.session.get(UserAccount, client.application.c2["users"]["scout"])
    exported = build_account_export(scout)["contact_requests"]["sent"][0]
    for data in (sent, exported):
        assert data["status"] == "declined"
        assert data["club_consent_note"] is None
