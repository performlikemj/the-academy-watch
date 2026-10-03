# ruff: noqa: F811, F401
"""Regressions reversed from RC1V2 executed probes."""

import pytest
from src.auth import issue_user_token
from src.models.club_player_publication import ClubPlayerPublication
from src.models.funding import ClubProgram
from src.models.league import UserAccount, db
from src.services import club_player_publication as service
from src.services.account import build_account_export
from test_club_player_publication import _admin_headers, _headers, client, club_app, env, published
from test_club_publication_rc1 import introduction
from test_club_publication_rc1v import suppress


def test_recovery_quarantines_old_content(client, env):
    result = published(client, env)
    path = f"/api/local-players/{env['local']}/showcase/profile"
    edited = client.put(path, headers=env["ph"], json={"bio": "RC1V2-X WRONG-PERSON-BIO"})
    assert edited.status_code == 200, edited.json
    approved = client.post(
        f"/api/admin/showcase/local-profiles/{env['local']}/review",
        headers=_admin_headers(),
        json={"action": "approve"},
    )
    assert approved.status_code == 200, approved.json
    from src.models.club_player_publication import RetiredClubShowcase
    from src.models.league import PlayerLink
    from src.models.showcase import PlayerClubAffiliation, PlayerShowcaseMedia

    db.session.add_all(
        [
            PlayerShowcaseMedia(
                local_player_id=env["local"],
                uploaded_by_user_id=env["player"],
                blob_path="local-players/fixture/old.jpg",
                public_url="local-players/fixture/old.jpg",
                status="approved",
            ),
            PlayerLink(
                local_player_id=env["local"],
                user_id=env["player"],
                url="https://youtu.be/abcdefghijk",
                link_type="highlight",
                status="approved",
            ),
            PlayerClubAffiliation(
                local_player_id=env["local"],
                created_by_user_id=env["player"],
                team_api_id=7001,
                status="club_confirmed",
            ),
        ]
    )
    db.session.commit()
    row = db.session.get(ClubPlayerPublication, result["id"])
    service.revoke(row, club=True)
    db.session.flush()
    assert client.put(path, headers=env["ph"], json={"bio": "Revoked owner edit"}).status_code == 403
    archive = RetiredClubShowcase.query.filter_by(user_account_id=env["player"]).one()
    assert archive.content["player_showcase_profiles"][0]["bio"] == "RC1V2-X WRONG-PERSON-BIO"
    for table in ("player_showcase_media", "player_links", "player_club_affiliations"):
        assert archive.content[table][0]["status"] in {"approved", "club_confirmed"}
    assert client.get("/api/media/published/local-players/fixture/old.jpg").status_code == 404
    person = UserAccount(
        email="rc1v2-x-new@example.test", display_name="New claimant", display_name_lower="new claimant"
    )
    db.session.add(person)
    db.session.commit()
    row, token = service.invite(
        env["pid"],
        env["local"],
        client.application.c2["users"]["a"],
        {"recipient_email": person.email, "expected_version": row.version},
    )
    service.redeem(person, {"token": token, "self_claim": True})
    service.consent(
        row,
        person.id,
        {"expected_version": row.version, "public_profile_consent": True, "consent_version": service.CONSENT_VERSION},
    )
    service.review(
        row,
        "reviewer",
        {"action": "approve", "reason": "New identity independently checked", "expected_version": row.version},
    )
    db.session.commit()
    for public_path in [f"/api/players/{-env['local']}/showcase", f"/api/local-players/{env['local']}/showcase"]:
        response = client.get(public_path)
        print(
            "O1_RECOVERY",
            public_path,
            response.status_code,
            "OLD_BIO",
            "RC1V2-X WRONG-PERSON-BIO" in response.get_data(as_text=True),
        )
        assert response.status_code == 200
        assert "RC1V2-X WRONG-PERSON-BIO" not in response.get_data(as_text=True)
    assert client.put(path, headers=env["ph"], json={"bio": "Old owner edit"}).status_code == 403
    for model in (PlayerShowcaseMedia, PlayerLink, PlayerClubAffiliation):
        assert model.query.filter_by(local_player_id=env["local"]).count() == 0
    old_export = build_account_export(db.session.get(UserAccount, env["player"]))
    assert "RC1V2-X WRONG-PERSON-BIO" in str(old_export["retired_club_showcases"])
    assert "RC1V2-X WRONG-PERSON-BIO" not in str(build_account_export(person))
    new_headers = {"Authorization": f"Bearer {issue_user_token(person.email)['token']}"}
    owner = client.get(f"/api/local-players/{env['local']}/showcase", headers=new_headers)
    assert owner.status_code == 200
    assert "RC1V2-X WRONG-PERSON-BIO" not in owner.get_data(as_text=True)
    assert client.put(path, headers=new_headers, json={"bio": "Fresh owner bio"}).status_code == 200
    assert client.get(f"/api/local-players/{env['local']}/showcase").json["profile"] is None


@pytest.mark.parametrize(
    "state", ["never_granted", "withdrawn", "revoked", "rejected", "flag_off", "suspended", "held", "suppressed"]
)
def test_scout_retains_only_own_unavailable_club_history(client, env, monkeypatch, state):
    result = published(client, env)
    contact_id = introduction(client, env)
    if state != "never_granted":
        assert (
            client.post(
                f"/api/contact/requests/{contact_id}/club-consent", headers=_headers("a"), json={"action": "grant"}
            ).status_code
            == 200
        )
        assert client.post(f"/api/contact/requests/{contact_id}/accept", headers=env["ph"]).status_code == 200
        assert (
            client.post(
                f"/api/contact/requests/{contact_id}/messages",
                headers=env["ph"],
                json={"body": "RC1V2-X PLAYER PRIVATE BODY"},
            ).status_code
            == 201
        )
        assert (
            client.post(
                f"/api/contact/requests/{contact_id}/messages",
                headers=_headers("scout"),
                json={"body": "RC1V2-X SCOUT OWN BODY"},
            ).status_code
            == 201
        )
    row = db.session.get(ClubPlayerPublication, result["id"])
    if state in ("withdrawn", "revoked"):
        service.revoke(row, club=state == "revoked")
    elif state == "rejected":
        service.review(
            row, "reviewer", {"action": "reject", "reason": "Identity mismatch", "expected_version": row.version}
        )
    elif state == "flag_off":
        monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    elif state == "suspended":
        db.session.get(UserAccount, env["player"]).account_status = "suspended"
    elif state == "held":
        db.session.get(ClubProgram, env["pid"]).emergency_hidden = True
    elif state == "suppressed":
        suppress(env["local"])
    db.session.commit()
    sent = client.get("/api/contact/requests?box=sent", headers=_headers("scout"))
    assert sent.status_code == 200, sent.json
    participant = sent.json["requests"][0]["participants"]["player"]
    user = db.session.get(UserAccount, client.application.c2["users"]["scout"])
    exported = build_account_export(user)["contact_requests"]
    print(
        "O2_STATE",
        state,
        "sent_player",
        participant,
        "export_name",
        exported["sent"][0]["participants"]["player"],
        "player_body",
        "RC1V2-X PLAYER PRIVATE BODY" in str(exported),
    )
    assert participant == {"display_name": "Unavailable"}
    assert exported["sent"][0]["participants"]["player"] == {"display_name": "Unavailable"}
    assert "RC1V2-X PLAYER PRIVATE BODY" not in str(exported)
    if state != "never_granted":
        assert str(exported).count("RC1V2-X SCOUT OWN BODY") == 1
    assert client.get(f"/api/contact/requests/{contact_id}/messages", headers=_headers("scout")).status_code == (
        409 if state == "never_granted" else 404
    )


def test_dark_nonclub_export_preserves_payload(client, env, monkeypatch):
    from src.models.contact import ContactMessage, ContactRequest

    result = published(client, env)
    cid = introduction(client, env)
    row = db.session.get(ContactRequest, cid)
    row.club_first = False
    scout = db.session.get(UserAccount, client.application.c2["users"]["scout"])
    db.session.add(
        ContactMessage(
            contact_request_id=cid, sender_user_id=scout.id, sender_role="scout", body="RC1V2-X NONCLUB OWN MESSAGE"
        )
    )
    db.session.commit()
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    data = build_account_export(scout)["contact_requests"]
    assert "authored_messages" not in data
    assert data["sent"][0]["messages"][0]["body"] == "RC1V2-X NONCLUB OWN MESSAGE"
    assert str(data).count("RC1V2-X NONCLUB OWN MESSAGE") == 1
    print("O5_DARK_DUPLICATE", list(data), "body occurrences", str(data).count("RC1V2-X NONCLUB OWN MESSAGE"))


from datetime import date

from src.models.follow import PlayerShadow
from src.services.public_adult import public_adult_ids


def test_conflicting_child_dob_cannot_be_erased_by_reapproval(client, env):
    result = published(client, env)
    pid = -env["local"]
    shadow = PlayerShadow.query.filter_by(player_api_id=pid).one()
    shadow.birth_date = date(2015, 1, 1)
    db.session.commit()
    assert public_adult_ids([pid]) == set()
    response = client.post(
        f"/api/admin/player-publications/{result['id']}/review",
        headers=_admin_headers(),
        json={"expected_version": result["version"], "action": "approve", "reason": "Repeat moderation probe"},
    )
    assert response.status_code == 409
    assert response.json["error"] == "publication_not_pending"
    assert db.session.get(PlayerShadow, shadow.id).birth_date == date(2015, 1, 1)
    print(
        "CHILD_REAPPROVAL",
        response.status_code,
        response.json,
        "shadow DOB",
        db.session.get(PlayerShadow, shadow.id).birth_date,
    )
    assert not public_adult_ids([pid]), "reapproval must preserve conflicting child evidence"


@pytest.mark.parametrize("mode", ["reconsent", "recovery"])
def test_child_conflict_survives_normal_pending_moderation(client, env, mode):
    result = published(client, env)
    row = db.session.get(ClubPlayerPublication, result["id"])
    if mode == "recovery":
        service.revoke(row, club=True)
        row, token = service.invite(
            env["pid"],
            env["local"],
            client.application.c2["users"]["a"],
            {"recipient_email": "adult@c1.example", "expected_version": row.version},
        )
        service.redeem(db.session.get(UserAccount, env["player"]), {"token": token, "self_claim": True})
    else:
        service.review(
            row, "reviewer", {"action": "reject", "expected_version": row.version, "reason": "Conflict identity review"}
        )
    service.consent(
        row,
        env["player"],
        {"public_profile_consent": True, "consent_version": service.CONSENT_VERSION, "expected_version": row.version},
    )
    shadow = PlayerShadow.query.filter_by(player_api_id=-env["local"]).one()
    shadow.birth_date = date(2015, 1, 1)
    db.session.commit()
    assert public_adult_ids([-env["local"]]) == set()
    response = client.post(
        f"/api/admin/player-publications/{row.id}/review",
        headers=_admin_headers(),
        json={"action": "approve", "expected_version": row.version, "reason": "Ordinary pending moderation"},
    )
    assert response.status_code == 409
    assert response.json["error"] == "birth_evidence_conflict"
    assert db.session.get(PlayerShadow, shadow.id).birth_date == date(2015, 1, 1)
    evidence = service.dto(row, admin=True)["moderation_evidence"]
    assert evidence["birth_evidence_conflict"] is True and evidence["adult"] is False
    print(
        "NORMAL_CHILD_REVIEW",
        mode,
        response.status_code,
        response.json["publication"]["public"] if response.status_code == 200 else response.json,
    )
    assert not public_adult_ids([-env["local"]])


@pytest.mark.parametrize("path,count", [("/api/players/{id}/showcase", 3), ("/p/{id}", 2), ("/p/{id}/card.png", 2)])
def test_dark_signed_club_reads_match_reviewed_main(client, env, monkeypatch, path, count):
    from test_club_publication_flag_parity import measured

    published(client, env)
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    response, statements = measured(client, path.format(id=-env["local"]))
    assert response.status_code == 404
    assert len(statements) == count


def test_mint_does_not_overwrite_child_evidence(client, env):
    from src.services.player_shadow_service import mint_shadow

    published(client, env)
    shadow = PlayerShadow.query.filter_by(player_api_id=-env["local"]).one()
    shadow.birth_date = date(2015, 1, 1)
    db.session.commit()
    with pytest.raises(ValueError, match="birth_evidence_conflict"):
        mint_shadow(-env["local"])
    assert shadow.birth_date == date(2015, 1, 1)


@pytest.mark.parametrize("erasure", [False, True])
def test_retired_content_privacy_maintenance_runs_while_dark(client, env, monkeypatch, erasure):
    from datetime import timedelta

    from src.models.club_player_publication import RetiredClubShowcase
    from src.services.account import delete_account
    from src.services.club_player_publication_account import purge_invited_emails

    result = published(client, env)
    client.put(
        f"/api/local-players/{env['local']}/showcase/profile", headers=env["ph"], json={"bio": "Retired private proof"}
    )
    service.revoke(db.session.get(ClubPlayerPublication, result["id"]), club=True)
    db.session.commit()
    assert RetiredClubShowcase.query.count() == 1
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    if erasure:
        delete_account(db.session.get(UserAccount, env["player"]))
    else:
        purge_invited_emails(at=service.now() + timedelta(days=181))
    db.session.commit()
    assert RetiredClubShowcase.query.count() == 0
