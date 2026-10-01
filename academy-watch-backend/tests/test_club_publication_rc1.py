# ruff: noqa: F811
"""RC1 probes: privacy, independent moderation, terminal permissions and retention."""

import json
from datetime import timedelta

import pytest
from src.models.club_player_publication import ClubPlayerPublication as Publication
from src.models.contact import ContactRequest
from src.models.funding import ClubRosterMember, ClubSquad
from src.models.league import UserAccount, db
from src.models.p2_foundation import AdminActionEvent, NotificationOutbox  # noqa: F401
from src.services import club_player_publication as service
from src.services.account import delete_account
from src.services.club_player_publication_account import purge_invited_emails
from test_club_player_publication import (  # noqa: F401
    _admin_headers,
    _headers,
    claimed,
    client,
    club_app,
    consented,
    env,
    invite,
    published,
    surface_ids,
)


def introduction(client, env):
    response = client.post(
        "/api/contact/requests",
        headers=_headers("scout"),
        json={"player_api_id": -env["local"], "message": "RC1 confidential scout pitch"},
    )
    assert response.status_code == 201, response.json
    return response.json["contact_request"]["id"]


@pytest.mark.parametrize("decision", ["pending", "decline", "grant", "flag_off"])
def test_export_withholds_club_first_and_erasure_still_deletes(client, env, monkeypatch, decision):
    from src.routes.account import account_bp

    club_app = client.application
    club_app.register_blueprint(account_bp, url_prefix="/api")
    published(client, env)
    contact_id = introduction(client, env)
    if decision in {"grant", "decline"}:
        assert (
            client.post(
                f"/api/contact/requests/{contact_id}/club-consent", headers=_headers("a"), json={"action": decision}
            ).status_code
            == 200
        )
    if decision == "flag_off":
        monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    exported = client.get("/api/account/export", headers=env["ph"])
    assert exported.status_code == 200, exported.json
    received = exported.json["contact_requests"]["received"]
    assert len(received) == (1 if decision == "grant" else 0)
    if decision != "grant":
        assert contact_id not in exported.get_data(as_text=True)
        assert "RC1 confidential scout pitch" not in exported.get_data(as_text=True)
    delete_account(db.session.get(UserAccount, env["player"]))
    db.session.commit()
    assert ContactRequest.query.filter_by(id=contact_id).count() == 0


@pytest.mark.parametrize("self_claim", [False, True])
def test_admin_authenticity_evidence_is_masked_scoped_and_self_invite_blocked(client, env, self_claim):
    squad = ClubSquad(program_id=env["pid"], name="Adult first team", kind="first_team")
    db.session.add(squad)
    db.session.flush()
    ClubRosterMember.query.filter_by(local_player_id=env["local"]).one().squad_id = squad.id
    db.session.commit()
    if self_claim:
        owner = UserAccount.query.filter_by(email="manager-a@c2.example").one()
        result = client.post(
            f"/api/club/{env['pid']}/players/{env['local']}/publication-invite",
            headers=_headers("a"),
            json={"recipient_email": owner.email},
        )
        assert result.status_code == 201, result.json
        row = service.redeem(owner, {"token": result.json["token"], "self_claim": True})
        service.consent(
            row,
            owner.id,
            {
                "expected_version": row.version,
                "public_profile_consent": True,
                "consent_version": service.CONSENT_VERSION,
            },
        )
        db.session.commit()
        row = service.dto(row)
    else:
        row = consented(client, env)
    assert "moderation_evidence" not in row
    rows = client.get("/api/admin/player-publications", headers=_admin_headers()).json["publications"]
    evidence = rows[0]["moderation_evidence"]
    assert evidence["club_name"] == "Club A" and evidence["squads"] == ["Adult first team"]
    assert evidence["adult"] and evidence["adult_evidence_source"] == "club_birth_date"
    assert (
        evidence["invited_email_masked"]
        == evidence["claimant_email_masked"]
        == ("m***@c2.example" if self_claim else "a***@c1.example")
    )
    assert evidence["same_account"] is evidence["same_email"] is evidence["self_invitation"] is self_claim
    assert all(evidence[key] for key in ["invited_at", "claimed_at", "consented_at"])
    assert "2000-01-01" not in json.dumps(rows) and "adult@c1.example" not in json.dumps(rows)
    response = client.post(
        f"/api/admin/player-publications/{row['id']}/review",
        headers=_admin_headers(),
        json={"expected_version": row["version"], "action": "approve", "reason": "RC1 independent review"},
    )
    assert response.status_code == (409 if self_claim else 200), response.json
    if self_claim:
        assert response.json["error"] == "self_invitation_review_required"
        assert not service.live_publication(env["local"])


def test_reinvitation_uses_current_inviter_for_self_claim_guard(client, env):
    from src.models.funding import ClubProgramClaim, ClubProgramManager

    original = invite(client, env)
    other = UserAccount.query.filter_by(email="manager-b@c2.example").one()
    claim = ClubProgramClaim(
        program_id=env["pid"], user_account_id=other.id, relationship_type="club_official", status="approved"
    )
    db.session.add(claim)
    db.session.flush()
    db.session.add(
        ClubProgramManager(
            program_id=env["pid"],
            user_account_id=other.id,
            source_claim_id=claim.id,
            status="active",
            granted_by="fixture",
        )
    )
    db.session.commit()
    response = client.post(
        f"/api/club/{env['pid']}/players/{env['local']}/publication-invite",
        headers=_headers("b"),
        json={"recipient_email": other.email, "expected_version": original["publication"]["version"]},
    )
    assert response.status_code == 201, response.json
    row = service.redeem(other, {"token": response.json["token"], "self_claim": True})
    service.consent(
        row,
        other.id,
        {"expected_version": row.version, "public_profile_consent": True, "consent_version": service.CONSENT_VERSION},
    )
    db.session.commit()
    assert row.creator_user_id != other.id and row.association_confirmed_by == other.id
    evidence = client.get("/api/admin/player-publications", headers=_admin_headers()).json["publications"][0][
        "moderation_evidence"
    ]
    assert evidence["same_account"] and evidence["same_email"] and evidence["self_invitation"]
    response = client.post(
        f"/api/admin/player-publications/{row.id}/review",
        headers=_admin_headers(),
        json={"expected_version": row.version, "action": "approve", "reason": "Independent review"},
    )
    assert response.status_code == 409 and response.json["error"] == "self_invitation_review_required"


@pytest.mark.parametrize("stage", ["invited", "claimed", "consented", "withdrawn", "club_revoked"])
def test_admin_queue_never_names_unclaimed_or_inactive_invites(client, env, stage):
    if stage == "invited":
        invite(client, env)
    elif stage == "claimed":
        claimed(client, env)
    else:
        consented(client, env)
        if stage in {"withdrawn", "club_revoked"}:
            service.revoke(Publication.query.one(), club=stage == "club_revoked")
            db.session.commit()
    response = client.get("/api/admin/player-publications", headers=_admin_headers())
    assert response.status_code == 200
    assert len(response.json["publications"]) == (1 if stage == "consented" else 0)
    if stage != "consented":
        assert "C1 adult fixture" not in response.get_data(as_text=True)


def test_club_revoke_is_decline_with_cooldown(client, env):
    published(client, env)
    id_ = introduction(client, env)
    response = client.post(f"/api/contact/requests/{id_}/revoke", headers=_headers("a"))
    assert response.status_code == 200
    contact = db.session.get(ContactRequest, id_)
    assert contact.status == contact.club_consent_status == "declined"
    assert contact.responded_at and contact.club_consent_at
    response = client.post(
        "/api/contact/requests",
        headers=_headers("scout"),
        json={"player_api_id": -env["local"], "message": "Immediate repeat"},
    )
    assert response.status_code == 409
    assert response.json["code"] == "decline_cooldown_active"


def test_rejected_publication_permanently_closes_threads_after_reapproval(client, env):
    row = published(client, env)
    id_ = introduction(client, env)
    assert (
        client.post(
            f"/api/contact/requests/{id_}/club-consent", headers=_headers("a"), json={"action": "grant"}
        ).status_code
        == 200
    )
    assert client.post(f"/api/contact/requests/{id_}/accept", headers=env["ph"]).status_code == 200
    response = client.post(
        f"/api/admin/player-publications/{row['id']}/review",
        headers=_admin_headers(),
        json={"expected_version": row["version"], "action": "reject", "reason": "Independent authenticity concern"},
    )
    assert response.status_code == 200
    assert db.session.get(ContactRequest, id_).status == "withdrawn"
    row = response.json["publication"]
    response = client.post(
        f"/api/admin/player-publications/{row['id']}/review",
        headers=_admin_headers(),
        json={"expected_version": row["version"], "action": "approve", "reason": "Fresh independent evidence checked"},
    )
    assert response.status_code == 200
    assert response.json["publication"]["public"]
    for headers in [env["ph"], _headers("scout")]:
        assert (
            client.post(
                f"/api/contact/requests/{id_}/messages", headers=headers, json={"body": "Must stay closed"}
            ).status_code
            == 409
        )


@pytest.mark.parametrize("case", ["expired", "withdrawn", "club_revoked", "retained", "live", "claimed"])
def test_invited_email_purge_works_dark_without_discarding_consent(client, env, monkeypatch, case):
    if case in {"claimed", "withdrawn", "retained"}:
        consented(client, env)
    else:
        invite(client, env)
    row = Publication.query.one()
    if case == "expired":
        row.invite_expires_at = service.now() - timedelta(seconds=1)
    elif case in {"withdrawn", "club_revoked"}:
        service.revoke(row, club=case == "club_revoked")
        assert row.recipient_email is None
    elif case == "retained":
        row.created_at = service.now() - timedelta(days=180, seconds=1)
    db.session.commit()
    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    purge_invited_emails(limit=1)
    db.session.commit()
    assert (row.recipient_email is None) is (case not in {"live", "claimed"})
    assert row.adult_invited_at
    if case in {"claimed", "withdrawn", "retained"}:
        assert row.claimed_at and row.consented_at and row.consent_version


@pytest.mark.parametrize(
    "state", ["never_invited", "claimed", "consented", "rejected", "withdrawn", "club_revoked", "flag_off", "published"]
)
def test_compact_private_state_leak_sweep(client, env, monkeypatch, state):
    # Reverse the reviewer's 2,289-request sweep: each representative serializer,
    # signed/local alias, query selector and audience; published control proves sensitivity.
    from src.routes.journey import journey_bp
    from src.routes.players import players_bp

    client.application.register_blueprint(journey_bp, url_prefix="/api")
    client.application.register_blueprint(players_bp, url_prefix="/api")
    from src.models.follow import Follow, FollowList
    from src.models.scout_watchlist import ScoutWatchlistEntry

    def seed_saved():
        scout_id = client.application.c2["users"]["scout"]
        saved = FollowList(user_account_id=scout_id, name="C1 saved fixture")
        db.session.add(saved)
        db.session.flush()
        db.session.add(
            Follow(list_id=saved.id, kind="player", selector={"player_api_id": -env["local"]}, label="C1 adult fixture")
        )
        db.session.add(ScoutWatchlistEntry(user_account_id=scout_id, player_api_id=-env["local"]))
        db.session.commit()

    if state == "claimed":
        claimed(client, env)
    elif state == "consented":
        consented(client, env)
    elif state != "never_invited":
        result = published(client, env)
        row = db.session.get(Publication, result["id"])
        seed_saved()
        if state == "rejected":
            service.review(
                row, "reviewer", {"expected_version": row.version, "action": "reject", "reason": "RC1 sweep"}
            )
        elif state in {"withdrawn", "club_revoked"}:
            service.revoke(row, club=state == "club_revoked")
        elif state == "flag_off":
            monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
        db.session.commit()
    if state in {"never_invited", "claimed", "consented"}:
        seed_saved()
    pid, lid = -env["local"], env["local"]
    paths = [
        f"/api/local-players/{lid}",
        f"/api/local-players/{lid}/showcase",
        f"/api/players/{pid}/showcase",
        f"/api/players/{pid}/profile",
        f"/api/players/{pid}/journey",
        f"/api/players/{pid}/season-stats",
        f"/p/{pid}",
        "/api/players/search?q=C1",
        "/api/scout/players?search=C1",
        f"/api/scout/compare?ids={pid}",
        f"/api/scout/export.csv?ids={pid}",
        "/api/scout/watchlist",
        "/api/scout/lists",
    ]
    hits = 0
    for headers in [{}, _headers("scout"), _headers("b")]:
        for path in paths:
            for extra in ["", f"{'&' if '?' in path else '?'}player_api_id={pid}&search=C1"]:
                response = client.get(path + extra, headers=headers)
                assert response.status_code < 500, (state, path, response.json)
                named = "C1 adult fixture" in response.get_data(as_text=True)
                hits += named
                if state != "published":
                    assert not named, (state, path, response.get_data(as_text=True))
    assert hits > 0 if state == "published" else hits == 0
    assert all(ids == ({pid} if state == "published" else set()) for ids in surface_ids(client, env).values())
