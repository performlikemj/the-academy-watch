# ruff: noqa: F811
"""Reverse REVIEW-DUEL probes for privacy, recovery and bounded reads."""

from datetime import date, timedelta

import pytest
from sqlalchemy import event
from src.models.club_player_publication import ClubPlayerPublication as Publication
from src.models.contact import ContactRequest
from src.models.follow import Follow
from src.models.funding import ClubProgram, ClubRosterMember
from src.models.league import Team, UserAccount, db
from src.models.p2_foundation import AdminActionEvent
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.services import club_player_publication as service
from src.services.account import build_account_export, delete_account
from src.services.public_adult import public_adult_ids
from test_club_player_publication import (  # noqa: F401
    _admin_headers,
    _headers,
    claimed,
    client,
    club_app,
    consented,
    env,
    published,
)
from test_club_publication_rc1 import introduction


def seed_publication(env, index):
    user = UserAccount(
        email=f"rc1v-{index}@example.test", display_name=f"RC1V user {index}", display_name_lower=f"rc1v user {index}"
    )
    local = LocalPlayer(
        display_name=f"C1 search fixture {index:02}",
        birth_date=date(2000, 1, 1),
        birth_year=2000,
        provenance="club",
        origin_program_id=env["pid"],
        status="approved",
    )
    db.session.add_all([user, local])
    db.session.flush()
    local.api_player_id = -local.id
    claim = PlayerProfileClaim(
        local_player_id=local.id,
        user_account_id=user.id,
        relationship_type="player",
        status="approved",
        club_program_id=env["pid"],
    )
    db.session.add(claim)
    db.session.flush()
    db.session.add(ClubRosterMember(program_id=env["pid"], local_player_id=local.id, added_by_user_id=env["player"]))
    row = Publication(
        program_id=env["pid"],
        local_player_id=local.id,
        recipient_user_id=user.id,
        claim_id=claim.id,
        recipient_email=user.email,
        adult_invited_at=service.now(),
        claimed_at=service.now(),
        association_confirmed_at=service.now(),
        consented_at=service.now(),
        consent_version=service.CONSENT_VERSION,
        moderation_status="approved",
    )
    db.session.add(row)
    db.session.flush()
    return local, row


def suppress(local_id):
    db.session.add(
        PlayerSuppression(
            local_player_id=local_id,
            reason_code="player_request",
            requester_role="player",
            requester_contact="private@example.test",
            request_statement="Private fixture",
            status="active",
        )
    )


@pytest.mark.parametrize(
    "state", ["withdrawn", "revoked", "rejected", "flag_off", "erased", "suspended", "held", "suppressed", "published"]
)
def test_export_and_stored_club_name_labels(client, env, monkeypatch, state):
    result = published(client, env)
    assert client.post(
        "/api/scout/watchlist", headers=_headers("scout"), json={"player_api_id": -env["local"]}
    ).status_code in (200, 201)
    follow = Follow.query.filter_by(kind="player").one()
    follow_id = follow.id
    db.session.execute(Follow.__table__.update().where(Follow.id == follow_id).values(label="C1 adult fixture"))
    db.session.commit()
    row = db.session.get(Publication, result["id"])
    if state in ("withdrawn", "revoked"):
        service.revoke(row, club=state == "revoked")
    elif state == "rejected":
        service.review(row, "reviewer", {"expected_version": row.version, "action": "reject", "reason": "RC1V privacy"})
    elif state == "flag_off":
        monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    elif state == "suspended":
        db.session.get(UserAccount, env["player"]).account_status = "suspended"
    elif state == "held":
        db.session.get(ClubProgram, env["pid"]).emergency_hidden = True
    elif state == "suppressed":
        suppress(env["local"])
    elif state == "erased":
        delete_account(db.session.get(UserAccount, env["player"]))
    db.session.commit()
    if state in ("withdrawn", "revoked", "rejected", "erased"):
        assert db.session.get(Follow, follow_id).label != "C1 adult fixture"
    user = db.session.get(UserAccount, client.application.c2["users"]["scout"])
    body = build_account_export(user)
    assert "C1 adult fixture" not in [f["label"] for saved in body["follow_lists"] for f in saved["follows"]]
    db.session.commit()
    db.session.expire_all()
    assert db.session.get(Follow, follow_id).label != "C1 adult fixture"
    if state != "published":
        assert body["follow_lists"][0]["follows"][0]["unavailable"]


def test_new_follow_keeps_live_name_but_stores_no_name(client, env):
    published(client, env)
    assert client.post(
        "/api/scout/watchlist", headers=_headers("scout"), json={"player_api_id": -env["local"]}
    ).status_code in (200, 201)
    assert Follow.query.filter_by(kind="player").one().label is None
    assert "C1 adult fixture" in str(client.get("/api/scout/lists", headers=_headers("scout")).json)


@pytest.mark.parametrize("phase", ["claimed", "published", "wrong_person_withdraws"])
def test_guarded_recovery_fresh_keys_history_closed_threads(client, env, phase):
    result = published(client, env) if phase == "published" else claimed(client, env)
    row = db.session.get(Publication, result["id"])
    old_claim_id = row.claim_id
    old_contact = introduction(client, env) if phase == "published" else None
    service.revoke(row, club=phase != "wrong_person_withdraws")
    db.session.commit()
    assert row.claimed_at
    actor = client.application.c2["users"]["a"]
    version = row.version
    with pytest.raises(service.PublicationError, match="version_conflict"):
        service.invite(
            env["pid"], env["local"], actor, {"recipient_email": "adult@c1.example", "expected_version": version - 1}
        )
    db.session.rollback()
    row, token = service.invite(
        env["pid"], env["local"], actor, {"recipient_email": "adult@c1.example", "expected_version": version}
    )
    db.session.commit()
    assert not row.claim_id and not row.claimed_at and not row.consented_at and row.moderation_status == "pending"
    assert db.session.get(PlayerProfileClaim, old_claim_id).status == "revoked"
    assert db.session.get(PlayerProfileClaim, old_claim_id).local_player_id == env["local"]
    assert not public_adult_ids([-env["local"]])
    user = db.session.get(UserAccount, env["player"])
    service.redeem(user, {"token": token, "self_claim": True})
    db.session.commit()
    assert row.claim_id != old_claim_id and not service.dto(row)["public"]
    service.consent(
        row,
        user.id,
        {"expected_version": row.version, "public_profile_consent": True, "consent_version": service.CONSENT_VERSION},
    )
    service.review(
        row,
        "reviewer",
        {"expected_version": row.version, "action": "approve", "reason": "Fresh independent identity checked"},
    )
    db.session.commit()
    assert service.dto(row)["public"]
    history = AdminActionEvent.query.filter_by(action="club_publication_recovery").one().event_metadata
    assert history["claim_id"] == old_claim_id and history["claimed_at"]
    if phase == "published":
        assert history["consent_version"] == service.CONSENT_VERSION and history["consented_at"]
    if old_contact:
        contact = db.session.get(ContactRequest, old_contact)
        assert contact.claim_id == old_claim_id and contact.status == "withdrawn"
        assert not service.club_request_available(contact)


def test_consented_withdrawal_cannot_be_reassigned(client, env):
    result = published(client, env)
    row = db.session.get(Publication, result["id"])
    assert client.get(f"/api/club/{env['pid']}/publication-candidates", headers=_headers("a")).json["players"] == []
    service.revoke(row)
    db.session.commit()
    with pytest.raises(service.PublicationError, match="already_claimed"):
        service.invite(
            env["pid"],
            env["local"],
            client.application.c2["users"]["a"],
            {"recipient_email": "someone@example.test", "expected_version": row.version},
        )
    assert client.get(f"/api/club/{env['pid']}/publication-candidates", headers=_headers("a")).json["players"] == []


@pytest.mark.parametrize("state", ["withdrawn", "flag_off", "rejected", "revoked"])
def test_own_authored_export_after_access_ends(client, env, monkeypatch, state):
    result = published(client, env)
    id_ = introduction(client, env)
    assert (
        client.post(
            f"/api/contact/requests/{id_}/club-consent", headers=_headers("a"), json={"action": "grant"}
        ).status_code
        == 200
    )
    assert client.post(f"/api/contact/requests/{id_}/accept", headers=env["ph"]).status_code == 200
    for headers, body in [
        (env["ph"], "RC1V own authored export proof"),
        (_headers("scout"), "RC1V withheld counterpart proof"),
    ]:
        assert (
            client.post(f"/api/contact/requests/{id_}/messages", headers=headers, json={"body": body}).status_code
            == 201
        )
    row = db.session.get(Publication, result["id"])
    if state == "flag_off":
        monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    elif state == "rejected":
        service.review(
            row, "reviewer", {"expected_version": row.version, "action": "reject", "reason": "Export fixture"}
        )
    else:
        service.revoke(row, club=state == "revoked")
    db.session.commit()
    body = build_account_export(db.session.get(UserAccount, env["player"]))
    assert body["contact_requests"]["received"] == []
    assert "RC1V own authored export proof" in str(body)
    assert "RC1V withheld counterpart proof" not in str(body) and "RC1 confidential scout pitch" not in str(body)
    assert body["contact_requests"]["authored_messages"][0]["body"] == "RC1V own authored export proof"


@pytest.mark.parametrize("surface", ["public", "follow"])
def test_eligibility_before_search_limit(client, env, monkeypatch, surface):
    from src.services.player_shadow_service import search_players

    rows = [seed_publication(env, i)[0] for i in range(12)]
    for local in rows[:10]:
        suppress(local.id)
    db.session.commit()
    expected = {-p.id for p in rows[10:]}
    assert public_adult_ids([-p.id for p in rows]) == expected
    results = (
        client.get("/api/players/search?q=C1%20search%20fixture").json
        if surface == "public"
        else search_players("C1 search fixture")
    )
    assert {r["player_api_id"] for r in results} == expected


@pytest.mark.parametrize("surface,cap", [("public", 8), ("follow", 10)])
def test_combined_search_deduplicates_and_caps(client, env, monkeypatch, surface, cap):
    from src.models.tracked_player import TrackedPlayer
    from src.services.player_shadow_service import search_players

    for i in range(12):
        seed_publication(env, i)
    for i in range(10):
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
    results = (
        client.get("/api/players/search?q=C1%20search%20fixture").json
        if surface == "public"
        else search_players("C1 search fixture")
    )
    ids = [r["player_api_id"] for r in results]
    assert len(ids) == len(set(ids)) == cap


@pytest.mark.parametrize("state", ["claimed", "published", "rejected", "dark", "retired"])
def test_no_competing_legacy_moderation(client, env, monkeypatch, state):
    import src.services.trust_decision_email_service as emails

    calls = []
    monkeypatch.setattr(emails, "send_player_claim_decision_email", lambda *args, **kwargs: calls.append(args))
    result = claimed(client, env) if state == "claimed" else published(client, env)
    row = db.session.get(Publication, result["id"])
    claim_id = row.claim_id
    if state == "rejected":
        service.review(
            row, "reviewer", {"expected_version": row.version, "action": "reject", "reason": "Legacy exclusion"}
        )
    elif state == "dark":
        monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    elif state == "retired":
        service.revoke(row, club=True)
        service.invite(
            env["pid"],
            env["local"],
            client.application.c2["users"]["a"],
            {"recipient_email": "adult@c1.example", "expected_version": row.version},
        )
    db.session.commit()
    assert claim_id not in [
        c["id"] for c in client.get("/api/admin/showcase/claims", headers=_admin_headers()).json["claims"]
    ]
    for action in ("approve", "reject", "revoke"):
        assert (
            client.post(
                f"/api/admin/showcase/claims/{claim_id}/review", headers=_admin_headers(), json={"action": action}
            ).status_code
            == 409
        )
    assert client.post(f"/api/admin/showcase/claims/{claim_id}/recheck", headers=_admin_headers()).status_code == 409
    assert calls == []


def test_reconsent_shows_rejection_history(client, env):
    result = published(client, env)
    id_ = introduction(client, env)
    row = db.session.get(Publication, result["id"])
    service.review(
        row,
        "reviewer",
        {"expected_version": row.version, "action": "reject", "reason": "Previous authenticity rejection"},
    )
    service.consent(
        row,
        env["player"],
        {"expected_version": row.version, "public_profile_consent": True, "consent_version": service.CONSENT_VERSION},
    )
    db.session.commit()
    assert not service.dto(row)["public"]
    evidence = client.get("/api/admin/player-publications", headers=_admin_headers()).json["publications"][0][
        "moderation_evidence"
    ]
    assert any(
        r["decision"] == "rejected" and r["reason"] == "Previous authenticity rejection"
        for r in evidence["review_history"]
    )
    assert db.session.get(ContactRequest, id_).status == "withdrawn"


def measured(client, path, headers):
    sql = []

    def count(conn, cursor, statement, params, context, many):
        sql.append(statement)

    db.session.expire_all()
    event.listen(db.engine, "before_cursor_execute", count)
    try:
        response = client.get(path, headers=headers)
    finally:
        event.remove(db.engine, "before_cursor_execute", count)
    assert response.status_code == 200, response.json
    return response, sql


@pytest.mark.parametrize("audience", ["club", "admin", "player"])
def test_publication_query_growth(client, env, audience):
    consented(client, env)
    path, headers = {
        "club": (f"/api/club/{env['pid']}/player-publications", _headers("a")),
        "admin": ("/api/admin/player-publications", _admin_headers()),
        "player": ("/api/me/player-publications", env["ph"]),
    }[audience]
    _, small = measured(client, path, headers)
    for i in range(20):
        _, row = seed_publication(env, i)
        row.moderation_status = "pending"
        if audience == "player":
            row.recipient_user_id = env["player"]
    db.session.commit()
    response, large = measured(client, path, headers)
    assert len(response.json["publications"]) == 21
    assert len(large) <= len(small) + 4, (len(small), len(large))


def test_contact_docstring():
    assert ContactRequest.__doc__ and "introduction request" in ContactRequest.__doc__


@pytest.mark.parametrize("box", ["sent", "club", "inbox"])
def test_contact_list_query_growth_and_binding(client, env, box):
    published(client, env)
    first = introduction(client, env)
    if box == "inbox":
        assert (
            client.post(
                f"/api/contact/requests/{first}/club-consent", headers=_headers("a"), json={"action": "grant"}
            ).status_code
            == 200
        )
    headers = {"sent": _headers("scout"), "club": _headers("a"), "inbox": env["ph"]}[box]
    path = f"/api/contact/requests?box={box}"
    response, small = measured(client, path, headers)
    assert len(response.json["requests"]) == 1
    scout_id = client.application.c2["users"]["scout"]
    for i in range(10):
        local, row = seed_publication(env, i)
        if box == "inbox":
            row.recipient_user_id = env["player"]
            db.session.get(PlayerProfileClaim, row.claim_id).user_account_id = env["player"]
        db.session.add(
            ContactRequest(
                scout_user_id=scout_id,
                player_api_id=-local.id,
                claim_id=row.claim_id,
                club_first=True,
                routing_mode="club_included",
                club_program_id=env["pid"],
                club_consent_status="granted" if box == "inbox" else "pending",
                message="Batch fixture pitch",
                expires_at=service.now() + timedelta(days=7),
            )
        )
    db.session.commit()
    response, large = measured(client, path, headers)
    assert len(response.json["requests"]) == 11
    assert len(large) <= len(small) + 4, (len(small), len(large))
    assert all(not r["messaging_open"] for r in response.json["requests"])
    if box == "inbox":
        # An old/replaced claim must not reappear through the same signed player id.
        old = db.session.get(ContactRequest, first)
        old.claim_id = PlayerProfileClaim.query.filter(PlayerProfileClaim.id != old.claim_id).first().id
        db.session.commit()
        response = client.get(path, headers=headers)
        assert first not in [r["id"] for r in response.json["requests"]]


@pytest.mark.parametrize("linked", [False, True])
@pytest.mark.parametrize("suffix", ["", "/showcase"])
def test_dark_local_query_count_matches_main(club_app, client, monkeypatch, linked, suffix):
    monkeypatch.delenv("CLUB_PLAYER_PUBLICATION_ENABLED", raising=False)
    local = LocalPlayer(
        display_name="RC1V dark fixture",
        provenance="club",
        origin_program_id=club_app.c2["program_a"],
        birth_date=date(2000, 1, 1),
        birth_year=2000,
        status="approved" if linked else "pending",
    )
    db.session.add(local)
    db.session.flush()
    local.api_player_id = 7001 if linked else -local.id
    db.session.commit()
    lid = local.id
    db.session.expire_all()
    statements = []

    def count(conn, cursor, statement, params, context, many):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", count)
    try:
        response = client.get(f"/api/local-players/{lid}{suffix}")
    finally:
        event.remove(db.engine, "before_cursor_execute", count)
    assert response.status_code == 404 and response.json == {"error": "local player not found"}
    assert len(statements) == 5, statements


def test_wrong_invitee_recovery_does_not_transfer_permissions(client, env):
    wrong = UserAccount(email="wrong@c1.example", display_name="Wrong fixture", display_name_lower="wrong fixture")
    db.session.add(wrong)
    db.session.commit()
    actor = client.application.c2["users"]["a"]
    row, token = service.invite(env["pid"], env["local"], actor, {"recipient_email": wrong.email})
    service.redeem(wrong, {"token": token, "self_claim": True})
    old_id = row.claim_id
    service.revoke(row, club=True)
    db.session.commit()
    row, token = service.invite(
        env["pid"], env["local"], actor, {"recipient_email": "adult@c1.example", "expected_version": row.version}
    )
    db.session.commit()
    with pytest.raises(service.PublicationError, match="invite_unavailable"):
        service.redeem(wrong, {"token": token, "self_claim": True})
    assert not row.recipient_user_id and not row.claim_id
    user = db.session.get(UserAccount, env["player"])
    service.redeem(user, {"token": token, "self_claim": True})
    db.session.commit()
    assert row.recipient_user_id == user.id and row.claim_id != old_id
    old = db.session.get(PlayerProfileClaim, old_id)
    assert old.user_account_id == wrong.id and old.local_player_id == env["local"] and old.status == "revoked"
    with pytest.raises(service.PublicationError, match="publication_unavailable"):
        service.consent(
            row,
            wrong.id,
            {
                "expected_version": row.version,
                "public_profile_consent": True,
                "consent_version": service.CONSENT_VERSION,
            },
        )


def test_dark_retention_repairs_old_stored_labels(client, env, monkeypatch):
    from src.services.club_player_publication_account import purge_invited_emails

    published(client, env)
    assert client.post(
        "/api/scout/watchlist", headers=_headers("scout"), json={"player_api_id": -env["local"]}
    ).status_code in (200, 201)
    follow = Follow.query.one()
    id_ = follow.id
    db.session.execute(Follow.__table__.update().where(Follow.id == id_).values(label="C1 adult fixture"))
    db.session.commit()
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    assert purge_invited_emails(limit=1)["follow_labels_cleared"] == 1
    db.session.commit()
    db.session.expire_all()
    assert db.session.get(Follow, id_).label is None


@pytest.mark.parametrize(
    "state",
    ["private", "claimed", "revoked", "withdrawn_before_consent", "provider_bridge", "suppressed", "other_claim"],
)
def test_candidates_only_offer_guarded_invitable_identities(client, env, state):
    if state in ("claimed", "revoked", "withdrawn_before_consent"):
        result = claimed(client, env)
        row = db.session.get(Publication, result["id"])
        if state != "claimed":
            service.revoke(row, club=state == "revoked")
    elif state == "provider_bridge":
        db.session.get(LocalPlayer, env["local"]).api_player_id = 7001
    elif state == "suppressed":
        suppress(env["local"])
    elif state == "other_claim":
        db.session.add(
            PlayerProfileClaim(
                local_player_id=env["local"],
                user_account_id=env["player"],
                relationship_type="player",
                status="pending",
            )
        )
    db.session.commit()
    response = client.get(f"/api/club/{env['pid']}/publication-candidates", headers=_headers("a"))
    assert response.status_code == 200, response.json
    assert [p["id"] for p in response.json["players"]] == (
        [env["local"]] if state in ("private", "revoked", "withdrawn_before_consent") else []
    )


def test_ordinary_legacy_club_claim_remains_in_legacy_queue(client, env):
    claim = PlayerProfileClaim(
        local_player_id=env["local"],
        user_account_id=env["player"],
        relationship_type="player",
        status="pending",
        club_program_id=env["pid"],
    )
    db.session.add(claim)
    db.session.commit()
    response = client.get("/api/admin/showcase/claims", headers=_admin_headers())
    assert response.status_code == 200
    assert claim.id in [row["id"] for row in response.json["claims"]]
