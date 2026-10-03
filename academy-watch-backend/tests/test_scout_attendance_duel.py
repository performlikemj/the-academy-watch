# ruff: noqa: F811
"""REVIEW-DUEL probes reversed into expected lifecycle and scoped queue behavior."""

from datetime import date, timedelta

import pytest
from src.auth import issue_user_token
from src.models.club_access import ClubAccessGrant
from src.models.contact import ContactRequest
from src.models.funding import ClubProgram, ClubSquad
from src.models.league import UserAccount, db
from src.models.opportunities import ClubOpportunity, now
from src.models.p2_foundation import NotificationOutbox
from src.models.scout_attendance import ScoutAttendance
from src.models.showcase import LocalPlayer
from src.models.trust import ScoutVerification
from src.models.video import VideoMatch
from src.services import scout_attendance as service
from src.services.account import _SchemaView
from src.services.club_access import record_coverage
from src.services.scout_attendance_account import export_attendance
from test_club_console import _headers, client, club_app  # noqa: F401
from test_opportunities import create, env  # noqa: F401
from test_scout_attendance import answer, ask, c4, trial  # noqa: F401


def today(client, c4, headers=None):
    response = client.get(f"/api/club/{c4['pid']}/today", headers=headers or _headers("a"))
    assert response.status_code == 200
    return response.get_json()


def test_x1_authorised_match_behind_31_inaccessible_matches(client, c4):
    user = UserAccount(email="duel-coach@example.test", display_name="Test Coach", display_name_lower="test coach")
    squad = ClubSquad(program_id=c4["pid"], name="Coach squad", kind="first_team")
    db.session.add_all([user, squad])
    db.session.flush()
    db.session.add(
        ClubAccessGrant(program_id=c4["pid"], user_account_id=user.id, role="coach", all_squads=True, status="active")
    )
    match = VideoMatch(
        club_program_id=c4["pid"],
        squad_id=squad.id,
        status="processing",
        opponent_name="Authorised older",
        uploaded_at=now(),
        blob_etag="x",
        scoped_ready_etag="x",
        scoped_snapshot="x",
        created_at=now() - timedelta(days=2),
    )
    db.session.add(match)
    db.session.flush()
    record_coverage(match, origin=True)
    db.session.commit()
    headers = {"Authorization": "Bearer " + issue_user_token(user.email)["token"]}
    assert today(client, c4, headers)["queues"]["analysing"][0]["id"] == match.id
    for i in range(31):
        db.session.add(
            VideoMatch(
                club_program_id=c4["pid"],
                status="processing",
                opponent_name=f"Inaccessible {i}",
                uploaded_at=now(),
                blob_etag="x",
            )
        )
    db.session.commit()
    summary = today(client, c4, headers)
    assert [m["id"] for m in summary["queues"]["analysing"]] == [match.id]
    assert summary["matches_has_more"] is False


@pytest.mark.parametrize("unavailable", ["held", "unlisted", "cancelled", "retyped", "expired"])
def test_x2_export_redacts_instructions_when_event_unavailable(client, c4, monkeypatch, unavailable):
    post = trial(client, c4)
    row = ask(client, c4, post).get_json()["attendance"]
    assert answer(client, c4, row).status_code == 200
    user = db.session.get(UserAccount, c4["scout"])
    assert export_attendance(user, _SchemaView())["scout_attendance"][0]["arrival_instructions"]
    if unavailable == "held":
        db.session.get(ClubProgram, c4["pid"]).emergency_hidden = True
    elif unavailable == "unlisted":
        db.session.get(ClubProgram, c4["pid"]).platform_status = "pending"
    elif unavailable == "cancelled":
        db.session.get(ClubOpportunity, post["id"]).status = "cancelled"
    elif unavailable == "retyped":
        db.session.get(ClubOpportunity, post["id"]).type = "position"
    else:
        db.session.get(ScoutAttendance, row["id"]).retention_expires_at = now() - timedelta(seconds=1)
    db.session.commit()
    monkeypatch.setenv("SCOUT_ATTEND_ENABLED", "false")
    exported = export_attendance(user, _SchemaView())["scout_attendance"][0]
    assert exported["id"] == row["id"]
    assert "arrival_instructions" not in exported


@pytest.mark.parametrize("state", ["pending", "accepted"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("type", "position"),
        ("starts_at", "2026-10-20T10:00:00Z"),
        ("ends_at", "2026-10-20T12:00:00Z"),
        ("timezone", "Asia/Tokyo"),
        ("venue", "New ground"),
        ("address", "New address"),
    ],
)
def test_x4_o1_live_attendance_locks_session_terms_without_applications(client, c4, state, field, value):
    post = create(client, c4, birth_year_min=now().year - 12, birth_year_max=now().year - 10)
    row = ask(client, c4, post).get_json()["attendance"]
    if state == "accepted":
        assert answer(client, c4, row).status_code == 200
    before = NotificationOutbox.query.count()
    response = client.patch(
        f"/api/club/{c4['pid']}/opportunities/{post['id']}",
        headers=_headers("a"),
        json={"expected_version": post["version"], field: value},
    )
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["error"] == "advertised_terms_locked"
    assert ScoutAttendance.query.one().status == state
    assert NotificationOutbox.query.count() == before


@pytest.mark.parametrize("loss", ["verification", "suspension", "tombstone"])
@pytest.mark.parametrize("flush", ["explicit", "automatic", "rollback"])
def test_o2_flushed_trust_loss_reconciles_atomically(client, c4, monkeypatch, loss, flush):
    post = trial(client, c4)
    row = ask(client, c4, post).get_json()["attendance"]
    assert answer(client, c4, row).status_code == 200
    monkeypatch.setenv("SCOUT_ATTEND_ENABLED", "false")
    if loss == "verification":
        ScoutVerification.query.filter_by(user_account_id=c4["scout"]).one().status = "revoked"
    elif loss == "suspension":
        db.session.get(UserAccount, c4["scout"]).account_status = "suspended"
    else:
        db.session.get(UserAccount, c4["scout"]).is_tombstone = True
    if flush == "automatic":
        ClubOpportunity.query.count()
    else:
        db.session.flush()
    if flush == "rollback":
        db.session.rollback()
    db.session.commit()
    stored = db.session.get(ScoutAttendance, row["id"])
    assert stored.status == ("accepted" if flush == "rollback" else "revoked")
    assert stored.arrival_instructions == ("Report to reception." if flush == "rollback" else "")
    notices = [
        i for i in NotificationOutbox.query.filter_by(template="c4_attendance") if i.payload["state"] == "revoked"
    ]
    assert len(notices) == (0 if flush == "rollback" else 2)


def test_o3_intake_closed_copy_matches_recipient(client, c4):
    post = trial(client, c4)
    row = ask(client, c4, post).get_json()["attendance"]
    assert answer(client, c4, row).status_code == 200
    response = client.post(
        f"/api/club/{c4['pid']}/opportunities/{post['id']}/close",
        headers=_headers("a"),
        json={"expected_version": 1, "status": "closed"},
    )
    assert response.status_code == 200
    notices = [i for i in NotificationOutbox.query.filter_by(template="c4_attendance") if i.payload["version"] == 3]
    for intent in notices:
        text = service.render(intent, db.session.get(UserAccount, intent.recipient_user_id))["text"]
        if intent.recipient_user_id == c4["scout"]:
            assert "Your accepted attendance permission remains valid" in text
        else:
            assert "Accepted scout attendance permissions remain valid" in text
            assert "Your accepted attendance permission" not in text


@pytest.mark.parametrize("with_end", [False, True])
@pytest.mark.parametrize("elapsed", [False, True])
def test_n1_ended_session_absent_but_ongoing_session_visible(client, c4, with_end, elapsed):
    post = trial(client, c4)
    row = ask(client, c4, post).get_json()["attendance"]
    assert answer(client, c4, row).status_code == 200
    opp = db.session.get(ClubOpportunity, post["id"])
    opp.starts_at = now() - timedelta(days=30) if elapsed else now() - timedelta(minutes=1)
    opp.ends_at = opp.starts_at + timedelta(hours=2) if with_end else None
    db.session.commit()
    result = today(client, c4)
    assert [r["id"] for r in result["queues"]["accepted_attendance"]] == ([] if elapsed else [row["id"]])
    assert result["accepted_attendance_has_more"] is False
    assert ScoutAttendance.query.one().status == "accepted"


@pytest.mark.parametrize("ineligible", ["minor", "unknown", "suppressed", "held"])
def test_n1_introductions_eligibility_precedes_cap(client, c4, monkeypatch, ineligible):
    monkeypatch.setenv("CONTACT_RAIL_ENABLED", "true")
    adult = c4["people"]["adult"]
    adult2 = c4["people"]["adult2"]
    for i in range(31):
        user = UserAccount(
            email=f"duel-intro-{i}@example.test", display_name=f"Test {i}", display_name_lower=f"test {i}"
        )
        db.session.add(user)
        db.session.flush()
        db.session.add(
            ContactRequest(
                scout_user_id=user.id,
                player_api_id=-adult["local"],
                claim_id=adult["claim"],
                message="Test only",
                club_program_id=c4["pid"],
                club_consent_status="pending",
                created_at=now() - timedelta(days=2),
                expires_at=now() + timedelta(days=2),
            )
        )
    eligible = ContactRequest(
        scout_user_id=c4["scout"],
        player_api_id=-adult2["local"],
        claim_id=adult2["claim"],
        message="Test only",
        club_program_id=c4["pid"],
        club_consent_status="pending",
        expires_at=now() + timedelta(days=2),
    )
    db.session.add(eligible)
    db.session.commit()
    subject = db.session.get(LocalPlayer, adult["local"])
    if ineligible == "minor":
        subject.birth_date, subject.birth_year = date(now().year - 16, 1, 1), now().year - 16
    elif ineligible == "unknown":
        subject.birth_date, subject.birth_year = None, None
    elif ineligible == "held":
        subject.origin_program_id = c4["other"]
        db.session.get(ClubProgram, c4["other"]).emergency_hidden = True
    else:
        from src.models.player_suppression import PlayerSuppression

        db.session.add(
            PlayerSuppression(
                local_player_id=adult["local"],
                status="active",
                reason_code="player_request",
                requester_role="player",
                requester_contact="test@example.test",
                request_statement="Test only request",
            )
        )
    db.session.commit()
    result = today(client, c4)
    assert [r["id"] for r in result["queues"]["introductions"]] == [eligible.id]
    assert result["introductions_has_more"] is False


@pytest.mark.parametrize("restore", ["savepoint_rollback", "restore_before_commit"])
def test_o2_reverted_flushed_trust_change_preserves_permission(client, c4, restore):
    post = trial(client, c4)
    row = ask(client, c4, post).get_json()["attendance"]
    assert answer(client, c4, row).status_code == 200
    nested = db.session.begin_nested() if restore == "savepoint_rollback" else None
    verification = ScoutVerification.query.filter_by(user_account_id=c4["scout"]).one()
    verification.status = "revoked"
    db.session.flush()
    if nested:
        nested.rollback()
    else:
        verification.status = "approved"
    db.session.commit()
    assert db.session.get(ScoutAttendance, row["id"]).status == "accepted"
    assert db.session.get(ScoutAttendance, row["id"]).arrival_instructions == "Report to reception."
    assert not any(
        i.payload["state"] == "revoked" for i in NotificationOutbox.query.filter_by(template="c4_attendance")
    )


def test_x1_current_and_durable_member_scope_before_metadata(client, c4):
    from types import SimpleNamespace

    from src.models.club_access import VideoMatchCoverage
    from src.models.funding import ClubRosterMember
    from src.models.video import VideoRosterEntry
    from src.services.club_access import filter_match_bytes_query, match_visible_to

    squad = ClubSquad(program_id=c4["pid"], name="Permitted squad", kind="first_team")
    other = ClubSquad(program_id=c4["pid"], name="Other squad", kind="first_team")
    db.session.add_all([squad, other])
    db.session.flush()
    member = ClubRosterMember(
        program_id=c4["pid"],
        squad_id=squad.id,
        local_player_id=c4["people"]["adult"]["local"],
        added_by_user_id=c4["actor"],
    )
    foreign = ClubRosterMember(
        program_id=c4["other"], squad_id=squad.id, player_api_id=70001, added_by_user_id=c4["actor"]
    )
    db.session.add_all([member, foreign])
    db.session.flush()
    access = SimpleNamespace(whole_club=False, squad_ids={squad.id})
    matches = []
    for kind in (
        "eligible",
        "uncertain",
        "missing_member",
        "foreign_member",
        "roster_null",
        "unpublished",
        "wrong_squad",
    ):
        match = VideoMatch(
            club_program_id=c4["pid"],
            squad_id=other.id if kind == "wrong_squad" else squad.id,
            status="processing",
            uploaded_at=now(),
            blob_etag="x",
            scoped_ready_etag="x",
            scoped_snapshot=None if kind == "unpublished" else "x",
        )
        db.session.add(match)
        db.session.flush()
        record_coverage(match, origin=True)
        if kind == "uncertain":
            db.session.add(VideoMatchCoverage(video_match_id=match.id, kind="uncertain"))
        elif kind in {"missing_member", "foreign_member", "eligible"}:
            mid = 999999 if kind == "missing_member" else foreign.id if kind == "foreign_member" else member.id
            db.session.add(VideoMatchCoverage(video_match_id=match.id, kind="member", club_roster_member_id=mid))
        elif kind == "roster_null":
            db.session.add(VideoRosterEntry(video_match_id=match.id, player_name="Test only", jersey_number=1))
        matches.append(match)
    db.session.commit()
    query = VideoMatch.query.filter(VideoMatch.id.in_([m.id for m in matches]))
    expected = {m.id for m in matches if match_visible_to(access, m, require_bytes=True)}
    assert expected == {matches[0].id}
    assert {m.id for m in filter_match_bytes_query(query, access)} == expected
    # Moving an old participant out of scope also vetoes the durable covered match.
    member.squad_id = other.id
    db.session.commit()
    assert filter_match_bytes_query(query, access).count() == 0
