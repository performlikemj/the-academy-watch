"""Moderated local routing and exact relationship withdrawal boundaries."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from src.models.club_invitation import ClubInvitation, utcnow
from src.models.contact import ContactRequest
from src.models.funding import ClubRosterMember
from src.models.league import db
from src.models.showcase import PlayerShowcaseProfile
from src.services.contact import messaging_is_open, routing_mode_for_claim
from test_club_console import _admin_headers, _headers
from test_club_console import client as client
from test_club_console import club_app as club_app
from test_club_invitations import decide, invitation
from test_club_invitations import pilot as pilot


def stage(client, pilot, status="contracted", program=True, **fields):
    return client.put(
        f"/api/local-players/{pilot['local'].id}/showcase/profile",
        json={"contract_status": status, "club_program_id": pilot["program"] if program else None, **fields},
        headers=_headers("scout"),
    )


def review(client, pilot, action="approve"):
    return client.post(
        f"/api/admin/showcase/local-profiles/{pilot['local'].id}/review",
        json={"action": action},
        headers=_admin_headers(),
    )


def accept_local(client, pilot):
    row_id = invitation(client, pilot, -pilot["local"].id)
    assert decide(client, row_id).status_code == 200
    return row_id


def test_stage_reject_approve_owner_and_admin_payloads(client, pilot):
    accept_local(client, pilot)
    claim = pilot["local_claim"]
    profile = PlayerShowcaseProfile(
        local_player_id=pilot["local"].id, bio="Existing biography", positions="Forward", status="approved"
    )
    db.session.add(profile)
    db.session.commit()
    assert routing_mode_for_claim(claim) == "club_notified"
    response = stage(client, pilot)
    assert response.status_code == 200, response.json
    assert response.json["profile"]["contract_attestation_review_status"] == "pending"
    assert response.json["profile"]["current_club_name"] == "Club A"
    assert response.json["profile"]["bio"] == "Existing biography"
    assert claim.club_program_id is None and claim.contract_status == "unknown"
    listing = client.get("/api/admin/showcase/profiles", headers=_admin_headers())
    assert listing.json["profiles"][0]["club_program_id"] == pilot["program"]
    assert listing.headers["Cache-Control"] == "private, no-store"
    assert review(client, pilot, "reject").status_code == 200
    assert claim.club_program_id is None
    assert review(client, pilot).status_code == 200
    assert claim.club_program_id == pilot["program"] and routing_mode_for_claim(claim) == "club_included"
    from flask import g

    g.pop("user_id", None)
    g.pop("user_email", None)
    owner = client.get(f"/api/local-players/{pilot['local'].id}/showcase", headers=_headers("scout"))
    assert owner.json["profile"]["contract_attestation_review_status"] == "approved"
    assert owner.headers["Cache-Control"] == "private, no-store"


@pytest.mark.parametrize(
    "status,expected", [("contracted", "club_included"), ("unknown", "club_included"), ("free_agent", "direct")]
)
def test_local_routing_never_calls_provider_status(client, pilot, status, expected):
    accept_local(client, pilot)
    with patch("src.services.contact.player_facing_status", side_effect=AssertionError("provider lookup")):
        assert stage(client, pilot, status).status_code == 200
        assert review(client, pilot).status_code == 200
        assert routing_mode_for_claim(pilot["local_claim"]) == expected
    if status == "free_agent":
        assert pilot["local_claim"].club_program_id is None and pilot["local_claim"].current_club_name is None


@pytest.mark.parametrize("state", ["withdrawn", "revoked-claim", "suppressed", "hidden"])
def test_review_rechecks_relationship_and_subject(client, pilot, state):
    row_id = accept_local(client, pilot)
    assert stage(client, pilot).status_code == 200
    if state == "withdrawn":
        assert decide(client, row_id, "revoke").status_code == 200
    elif state == "revoked-claim":
        pilot["local_claim"].status = "revoked"
    elif state == "hidden":
        from src.models.funding import ClubProgram

        db.session.get(ClubProgram, pilot["program"]).emergency_hidden = True
    else:
        from src.models.player_suppression import PlayerSuppression

        db.session.add(
            PlayerSuppression(
                local_player_id=pilot["local"].id,
                reason_code="player_request",
                requester_role="player",
                requester_contact="synthetic@example.com",
                request_statement="Synthetic suppression",
                status="active",
            )
        )
    db.session.commit()
    assert review(client, pilot).json == {"error": "club_relationship_required"}
    assert pilot["local_claim"].club_program_id is None


def test_wrong_relationship_unknown_fields_and_contradictory_name(client, pilot):
    assert stage(client, pilot).json == {"error": "club_relationship_required"}
    accept_local(client, pilot)
    assert stage(client, pilot, current_club_name="Other club").json == {"error": "invalid_request"}
    assert stage(client, pilot, recipient_user_id=999).json == {"error": "invalid_request"}
    pilot["local_claim"].relationship_type = "agent"
    db.session.commit()
    assert stage(client, pilot).status_code == 403


def contacts(pilot, club_app):
    rows = []
    for program, claim in (
        (pilot["program"], pilot["local_claim"]),
        (club_app.c2["program_b"], pilot["local_claim"]),
        (pilot["program"], pilot["claim"]),
    ):
        row = ContactRequest(
            scout_user_id=club_app.c2["users"]["b"],
            claim_id=claim.id,
            player_api_id=-pilot["local"].id if claim.local_player_id else 7001,
            message="Synthetic introduction",
            status="accepted",
            routing_mode="club_included",
            club_program_id=program,
            club_consent_status="granted",
            created_at=utcnow(),
            expires_at=utcnow() + timedelta(days=14),
        )
        # Different scouts avoid the existing scout/subject active uniqueness rule.
        row.scout_user_id = list(club_app.c2["users"].values())[len(rows)]
        db.session.add(row)
        rows.append(row)
    db.session.commit()
    return rows


def test_revocation_closes_only_exact_threads_and_rolls_back_on_failure(client, pilot, club_app):
    from sqlalchemy import event

    row_id = accept_local(client, pilot)
    assert stage(client, pilot).status_code == 200
    assert review(client, pilot).status_code == 200
    rows = contacts(pilot, club_app)

    def fail(*args):
        raise RuntimeError("synthetic contact failure")

    event.listen(ContactRequest, "before_update", fail)
    try:
        assert decide(client, row_id, "revoke").json == {"error": "invitation_operation_failed"}
    finally:
        event.remove(ContactRequest, "before_update", fail)
    assert db.session.get(ClubInvitation, row_id).status == "accepted"
    assert ClubRosterMember.query.count() == 1 and pilot["local_claim"].club_program_id == pilot["program"]
    assert decide(client, row_id, "revoke").status_code == 200
    assert rows[0].status == "declined" and rows[0].club_consent_status == "declined"
    assert all(row.status == "accepted" and messaging_is_open(row) for row in rows[1:])
    assert not messaging_is_open(rows[0])
    assert pilot["local_claim"].contract_status == "contracted" and pilot["local_claim"].club_program_id is None
    assert routing_mode_for_claim(pilot["local_claim"]) == "club_notified"


@pytest.mark.parametrize(
    "player_consent,club_consent,expected",
    [
        ("pending", "granted", False),
        ("accepted", "pending", False),
        ("accepted", "declined", False),
        ("accepted", "granted", True),
    ],
)
def test_both_consents_required_and_refreshed(client, pilot, club_app, player_consent, club_consent, expected):
    row = contacts(pilot, club_app)[0]
    db.session.execute(
        db.update(ContactRequest)
        .where(ContactRequest.id == row.id)
        .values(status=player_consent, club_consent_status=club_consent),
        execution_options={"synchronize_session": False},
    )
    assert messaging_is_open(row) is expected


def test_revocation_removes_finalized_report_reel_and_roster(client, pilot, club_app):
    from src.models.player_match_entry import PlayerMatchEntry
    from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry
    from test_club_console import _result_payload

    row_id = accept_local(client, pilot)
    member = ClubRosterMember.query.one()
    # Historical result persistence is independent of the private relationship.
    result = client.post(
        f"/api/club/{pilot['program']}/results", json=_result_payload([member.id]), headers=_headers("a")
    )
    assert result.status_code == 201, result.json
    match = VideoMatch(
        club_program_id=pilot["program"],
        status="finalized",
        opponent_name="Synthetic opponent",
    )
    db.session.add(match)
    db.session.flush()
    entry = VideoRosterEntry(
        video_match_id=match.id, jersey_number=8, player_name="Synthetic player", club_roster_member_id=member.id
    )
    db.session.add(entry)
    db.session.flush()
    report = VideoPlayerReport(
        video_match_id=match.id,
        roster_entry_id=entry.id,
        club_program_id_at_finalize=pilot["program"],
        club_local_player_id_at_finalize=pilot["local"].id,
        model_version="synthetic-p2",
    )
    db.session.add(report)
    db.session.commit()
    path = f"/api/club/{pilot['program']}/matches/{match.id}"
    assert len(client.get(path + "/report", headers=_headers("a")).json["reports"]) == 1
    assert decide(client, row_id, "revoke").status_code == 200
    assert client.get(path + "/report", headers=_headers("a")).json["reports"] == []
    assert client.get(path + "/reel", headers=_headers("a")).json["players"] == []
    assert client.get(f"/api/club/{pilot['program']}/roster", headers=_headers("a")).json["members"] == []
    assert entry.club_roster_member_id is None and PlayerMatchEntry.query.count() == 1


@pytest.mark.parametrize(
    "body",
    [
        [],
        True,
        {"contract_status": True, "club_program_id": 7},
        {"contract_status": "invalid", "club_program_id": 7},
        {"contract_status": "contracted", "club_program_id": True},
        {"contract_status": "contracted", "club_program_id": 2147483648},
        {"contract_status": "contracted", "current_club_name": "x" * 181},
    ],
)
def test_local_attestation_strict_request_validation(client, pilot, body):
    response = client.put(
        f"/api/local-players/{pilot['local'].id}/showcase/profile", json=body, headers=_headers("scout")
    )
    assert response.status_code == 400 and response.json == {"error": "invalid_request"}
    assert PlayerShowcaseProfile.query.count() == 0


def test_unrelated_profile_edit_preserves_approved_routing(client, pilot):
    accept_local(client, pilot)
    assert stage(client, pilot).status_code == 200
    assert review(client, pilot).status_code == 200
    owner = client.get(f"/api/local-players/{pilot['local'].id}/showcase", headers=_headers("scout")).json["profile"]
    assert owner["profile_contract_status"] is None and owner["contract_status"] == "contracted"
    edited = client.put(
        f"/api/local-players/{pilot['local'].id}/showcase/profile",
        json={"bio": "Updated biography", "contract_status": owner["profile_contract_status"], "contract_until": None},
        headers=_headers("scout"),
    )
    assert edited.status_code == 200, edited.json
    assert edited.json["profile"]["bio"] == "Updated biography"
    assert pilot["local_claim"].contract_status == "contracted"
    assert pilot["local_claim"].club_program_id == pilot["program"]
