"""Staging club polish regressions, using existing synthetic authorization fixtures."""

# ruff: noqa: F811
from datetime import date, timedelta

import pytest
from src.models.club_access import ClubStaffInvite
from src.models.funding import ClubRosterMember, ClubRosterSquadHistory
from src.models.league import db
from src.models.player_match_entry import ClubResult, PlayerMatchEntry
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.utils.sanitize import sanitize_plain_text
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


@pytest.mark.parametrize(
    "opponent", ["Wendle & District", "Less < More", '"Quoted" Rovers', "O'Brien Town", "R&D &copy; FC", "&notin Town"]
)
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
    assert saved.opponent == sanitize_plain_text(opponent)
    assert saved.competition == sanitize_plain_text(opponent)
    # Newly stored and main-format rows share the exact same fixture key.
    assert saved.opponent_key == sanitize_plain_text(opponent).lower()
    duplicate = client.post(
        f"/api/club/{pid}/results",
        json=_result_payload([mid], opponent=opponent, competition=opponent),
        headers=_headers("a"),
    )
    assert duplicate.status_code == 409, duplicate.json
    assert duplicate.json["error"] == "result_already_exists"
    assert ClubResult.query.count() == PlayerMatchEntry.query.count() == 1
    listed = client.get(f"/api/club/{pid}/results", headers=_headers("a"))
    assert listed.status_code == 200
    assert listed.json["results"][0]["result"]["opponent"] == opponent
    assert listed.json["results"][0]["matches"][0]["opponent"] == opponent


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


@pytest.mark.parametrize("local", [False, True])
def test_relationship_names_add_no_database_queries(client, pilot, local):
    from sqlalchemy import event
    from src.models.club_invitation import list_invitations

    signed_id = -pilot["local"].id if local else 7001
    iid = invitation(client, pilot, signed_id)
    assert decide(client, iid).status_code == 200
    program_id = pilot["program"]

    def measured(include_names):
        db.session.remove()  # Equal cold identity-map state for both requests.
        statements = []

        def capture(conn, cursor, statement, params, context, executemany):
            statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", capture)
        try:
            result = list_invitations(db.session, program_id=program_id, include_player_names=include_names)
        finally:
            event.remove(db.engine, "before_cursor_execute", capture)
        return result, len(statements)

    baseline, original_count = measured(False)
    named, named_count = measured(True)
    assert named_count == original_count
    assert "player_name" not in baseline["invitations"][0]
    assert named["invitations"][0]["player_name"]
    # The HTTP endpoint must use that service payload, without another lookup.
    from unittest.mock import patch

    with patch("src.routes.club.list_invitations", return_value=named):
        response = client.get(f"/api/club/{program_id}/invitations", headers=_headers("a"))
    assert response.json == named


def test_scoped_brief_rejects_all_club_names_with_generic_error(client, env):
    from src.models.tracked_player import TrackedPlayer
    from src.models.video import VideoRosterEntry

    member = db.session.get(ClubRosterMember, env["m2"])
    TrackedPlayer.query.filter_by(player_api_id=member.player_api_id).update({"player_name": "Outside Privateperson"})
    match = _match(env["pid"])
    db.session.add(VideoRosterEntry(video_match_id=match.id, player_name="Sheetonly Secretperson", jersey_number=9))
    db.session.commit()
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    url = f"{env['base']}/roster/{env['m1']}/brief"
    for body in ["Outside checks shoulders", "Privateperson scans", "Sheetonly scans", "Secretperson scans"]:
        assert client.put(url, json={"body": body}, headers=_headers("a")).status_code == 400
        response = client.put(url, json={"body": body}, headers=_h(_email("coach")))
        assert response.status_code == 400
        assert response.json == {"error": "Briefs describe behaviours, not people — remove player names."}
        assert body.split()[0] not in response.get_data(as_text=True)
    assert db.session.get(ClubRosterMember, env["m1"]).coach_brief_body is None


def test_old_and_new_result_entries_share_one_public_competition(client, club_app):
    from src.services import season_rollup_service

    pid = club_app.c2["program_a"]
    mid = _add_api_member(client, pid)
    # Simulate an already committed main-format entry (no ClubResult header).
    db.session.add(
        PlayerMatchEntry(
            player_api_id=7001,
            season=2025,
            match_date=date(2025, 8, 31),
            opponent="Old &amp; Rovers",
            home_away="home",
            competition="Wendle &amp; District",
            source="club",
            status="club_confirmed",
            club_program_id=pid,
            reported_by_user_id=club_app.c2["users"]["a"],
            minutes=90,
            goals=1,
        )
    )
    db.session.commit()
    response = client.post(
        f"/api/club/{pid}/results",
        headers=_headers("a"),
        json=_result_payload([mid], opponent="New & Rovers", competition="Wendle & District"),
    )
    assert response.status_code == 201, response.json
    assert {entry.competition for entry in PlayerMatchEntry.query.all()} == {"Wendle &amp; District"}
    season_rollup_service.refresh_player(7001, 2025, session=db.session)
    cells = PlayerSeasonCell.query.filter_by(player_api_id=7001, season=2025, source="club").all()
    assert len(cells) == 1
    assert cells[0].detail == {"competition": "Wendle &amp; District"}
    assert cells[0].to_dict()["detail"] == {"competition": "Wendle & District"}
    assert (cells[0].appearances, cells[0].goals, cells[0].minutes) == (2, 2, 180)
    total = PlayerSeasonTotal.query.filter_by(player_api_id=7001, season=2025).one()
    assert (total.appearances, total.goals, total.minutes) == (2, 2, 180)


def test_display_decode_is_single_pass_and_preserves_literal_entities():
    from src.utils.sanitize import display_plain_text

    assert display_plain_text("R&amp;D &copy; FC") == "R&D &copy; FC"
    assert display_plain_text("&amp;notin Town") == "&notin Town"
    assert display_plain_text("&amp;copy; &amp;amp;") == "&copy; &amp;"
    assert display_plain_text(None) is None


@pytest.mark.parametrize("legacy_header", [False, True])
def test_existing_main_format_fixture_rejects_duplicate(client, club_app, legacy_header):
    from unittest.mock import patch

    from src.routes import club as club_routes

    pid = club_app.c2["program_a"]
    mid = _add_api_member(client, pid)
    payload = _result_payload([mid], opponent="Wendle & District", competition="Wendle & District")
    # Pin main's historical sanitizer independently of the current write helper.
    current_header = club_routes._result_header_values

    def main_header(body):
        header = current_header(body)
        header.update(
            opponent=sanitize_plain_text(body["opponent"]), competition=sanitize_plain_text(body["competition"])
        )
        return header

    with patch.object(club_routes, "_result_header_values", main_header):
        first = client.post(f"/api/club/{pid}/results", json=payload, headers=_headers("a"))
    assert first.status_code == 201
    if not legacy_header:
        entry = PlayerMatchEntry.query.one()
        entry.club_result_id = None
        db.session.delete(db.session.get(ClubResult, first.json["result"]["id"]))
        db.session.commit()
    duplicate = client.post(
        f"/api/club/{pid}/results",
        headers=_headers("a"),
        json=_result_payload([mid], opponent="Wendle & District", competition="Wendle & District"),
    )
    assert duplicate.status_code == 409, duplicate.json
    assert PlayerMatchEntry.query.count() == 1
