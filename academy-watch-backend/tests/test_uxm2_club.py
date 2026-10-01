"""Staging club polish regressions, using existing synthetic authorization fixtures."""

# ruff: noqa: F811
from datetime import date, timedelta

import pytest
from src.models.club_access import ClubStaffInvite
from src.models.funding import ClubRosterMember, ClubRosterSquadHistory
from src.models.league import db
from src.models.player_match_entry import ClubResult
from test_club_console import _add_api_member, _headers, _match, _result_payload
from test_club_console import client as client
from test_club_console import club_app as club_app
from test_club_invitations import decide, invitation
from test_club_invitations import pilot as pilot
from test_club_staff_access import _accept, _email, _h, _invite, _join
from test_club_staff_access import env as env


@pytest.mark.parametrize("local", [False, True])
def test_relationship_names_for_pending_and_accepted(client, pilot, local):
    signed_id = -pilot["local"].id if local else 7001
    iid = invitation(client, pilot, signed_id)
    url = f"/api/club/{pilot['program']}/invitations"
    pending = client.get(url, headers=_headers("a"))
    assert pending.status_code == 200
    expected = pilot["local"].display_name if local else "C2 Tracked Adult"
    # Existing synthetic tracked fixture is authoritative for its display name.
    if not local:
        from src.models.tracked_player import TrackedPlayer

        expected = TrackedPlayer.query.filter_by(player_api_id=signed_id).first().player_name
    assert pending.json["invitations"][0]["player_name"] == expected
    assert decide(client, iid).status_code == 200
    accepted = client.get(url, headers=_headers("a"))
    assert accepted.json["invitations"][0]["player_name"] == expected
    assert accepted.json["invitations"][0]["status"] == "accepted"
    assert client.get(url, headers=_headers("b")).status_code == 403


def test_current_assignment_without_history_does_not_invent_a_date(client, env):
    member = db.session.get(ClubRosterMember, env["m1"])
    ClubRosterSquadHistory.query.filter_by(roster_member_id=member.id).delete()
    db.session.commit()
    response = client.get(f"{env['base']}/roster/{member.id}/profile", headers=_headers("a"))
    assert response.status_code == 200
    assert response.json["pathway"] == [
        {
            "id": f"current-{member.id}",
            "squad_id": env["sa"],
            "squad_name": "Squad A",
            "started_at": None,
            "ended_at": None,
        }
    ]
    assert not ClubRosterSquadHistory.query.filter_by(roster_member_id=member.id).count()


def test_scoped_coach_brief_write_and_viewer_redaction(client, env):
    assert (
        client.put(
            f"{env['base']}/roster/{env['m1']}/brief", json={"body": "Check both shoulders"}, headers=_headers("a")
        ).status_code
        == 200
    )
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    _join(client, env, "viewer", "viewer", squads=[env["sa"]])
    _join(client, env, "analyst", "analyst", squads=[env["sa"]])
    url = f"{env['base']}/roster/{env['m1']}/profile"
    coach = client.get(url, headers=_h(_email("coach")))
    assert coach.status_code == 200
    assert coach.json["coach_brief"]["lines"] == ["Check both shoulders"]
    assert coach.json["pathway"][-1]["squad_id"] == env["sa"]
    assert (
        client.put(
            f"{env['base']}/roster/{env['m1']}/brief", json={"body": "Changed"}, headers=_h(_email("coach"))
        ).status_code
        == 200
    )
    assert client.get(f"{env['base']}/roster/{env['m2']}/profile", headers=_h(_email("coach"))).status_code == 404
    assert (
        client.put(
            f"{env['base']}/roster/{env['m2']}/brief", json={"body": "Out of scope"}, headers=_h(_email("coach"))
        ).status_code
        == 404
    )
    assert (
        "note"
        not in client.put(
            f"{env['base']}/roster/{env['m1']}/brief", json={"body": "Updated"}, headers=_h(_email("coach"))
        ).json["member"]
    )
    for role in ["viewer", "analyst"]:
        assert (
            client.put(
                f"{env['base']}/roster/{env['m1']}/brief", json={"body": "Denied"}, headers=_h(_email(role))
            ).status_code
            == 403
        )
    for path, method, body in [
        (f"roster/{env['m1']}", "patch", {"note": "Denied"}),
        ("system-brief", "put", {"body": "Denied"}),
    ]:
        assert (
            getattr(client, method)(f"{env['base']}/{path}", json=body, headers=_h(_email("coach"))).status_code == 403
        )
    viewer = client.get(url, headers=_h(_email("viewer")))
    assert viewer.status_code == 200
    assert "coach_brief" not in viewer.json and "brief" not in viewer.json["identity"]
    assert client.get(f"{env['base']}/invitations", headers=_h(_email("viewer"))).status_code == 403
    assert client.get(f"{env['base']}/invitations", headers=_h(_email("coach"))).status_code == 403


def test_expired_staff_invite_reinvite_supersedes_token_and_preserves_scope(client, env):
    old, token = _invite(client, env, _email("coach"), "coach", squads=[env["sa"], env["sb"]])
    stored = db.session.get(ClubStaffInvite, old["id"])
    stored.expires_at = stored.created_at - timedelta(days=1)
    db.session.commit()
    board = client.get(f"{env['base']}/access", headers=_headers("a"))
    expired = next(i for i in board.json["invites"] if i["id"] == old["id"])
    assert expired["status"] == "expired"
    assert _accept(client, token, "coach").status_code == 410
    new, replacement = _invite(
        client, env, expired["email"], expired["role"], squads=expired["squad_ids"], all_squads=expired["all_squads"]
    )
    assert new["id"] != old["id"] and new["squad_ids"] == sorted([env["sa"], env["sb"]])
    assert replacement != token
    assert _accept(client, token, "coach").json["error"] == "invite_revoked"
    assert _accept(client, replacement, "coach").status_code == 200
    assert db.session.get(ClubStaffInvite, old["id"]).status == "revoked"


@pytest.mark.parametrize("opponent", ["Wendle & District", "Less < More", '"Quoted" Rovers', "O'Brien Town"])
def test_results_plain_text_roundtrip_and_legacy_entities(client, club_app, opponent):
    pid = club_app.c2["program_a"]
    mid = _add_api_member(client, pid)
    response = client.post(
        f"/api/club/{pid}/results",
        json=_result_payload([mid], opponent=opponent, competition=opponent),
        headers=_headers("a"),
    )
    assert response.status_code == 201, response.json
    assert response.json["result"]["opponent"] == opponent
    assert response.json["result"]["competition"] == opponent
    saved = db.session.get(ClubResult, response.json["result"]["id"])
    assert saved.opponent == opponent
    from html import escape

    saved.opponent = escape(escape(opponent))
    db.session.commit()
    listed = client.get(f"/api/club/{pid}/results", headers=_headers("a"))
    assert listed.status_code == 200
    assert listed.json["results"][0]["result"]["opponent"] == opponent


def test_results_strip_tags_at_the_server_boundary(client, club_app):
    pid = club_app.c2["program_a"]
    mid = _add_api_member(client, pid)
    response = client.post(
        f"/api/club/{pid}/results",
        json=_result_payload([mid], opponent="<b>Wendle</b> & District <img src=x onerror=alert(1)>"),
        headers=_headers("a"),
    )
    assert response.status_code == 201
    assert response.json["result"]["opponent"] == "Wendle & District"


def test_match_date_order_nulls_last_with_stable_id_tie_break(client, club_app):
    pid = club_app.c2["program_a"]
    rows = [_match(pid) for _ in range(4)]
    for match, value in zip(rows, [date(2026, 9, 27), date(2026, 9, 20), None, date(2026, 9, 27)], strict=True):
        match.match_date = value
    db.session.commit()
    expected = [rows[3].id, rows[0].id, rows[1].id, rows[2].id]
    for _ in range(2):
        response = client.get(f"/api/club/{pid}/matches", headers=_headers("a"))
        assert response.status_code == 200
        assert [r["id"] for r in response.json["matches"]] == expected
