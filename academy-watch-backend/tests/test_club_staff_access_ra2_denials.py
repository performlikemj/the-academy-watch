# ruff: noqa: F401, F811
"""RA2 original probes, adapted and reversed by the RA2V reviewer (synthetic data only)."""

import pytest
from src.models.funding import ClubRosterMember
from src.models.league import db
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry, VideoTracklet
from test_club_console import _add_local_member, _local
from test_club_staff_access import _email, _h, _headers, _join, _match, client, club_app, env


def test_viewer_receives_private_notes_twice(env, client, club_app):
    with club_app.app_context():
        db.session.get(ClubRosterMember, env["m1"]).note = "PRIVATE safeguarding and coaching note"
        db.session.commit()
    _join(client, env, "viewer", "viewer", squads=[env["sa"]])
    h = _h(_email("viewer"))
    roster = client.get(f"{env['base']}/roster", headers=h).get_json()
    profile = client.get(f"{env['base']}/roster/{env['m1']}/profile", headers=h).get_json()
    assert "PRIVATE safeguarding and coaching note" not in str(roster)
    assert "note" not in profile
    assert "PRIVATE safeguarding and coaching note" not in str(profile)


def test_squad_a_reads_minor_in_mixed_squad_match(env, client, club_app, monkeypatch):
    with club_app.app_context():
        minor = _local(club_app.c2["users"]["a"], name="PRIVATE Squad B minor", birth_year=2010)
        minor_id = minor.id
    minor_member = _add_local_member(client, env["pid"], minor_id)
    assert (
        client.patch(
            f"{env['base']}/roster/{minor_member}", json={"squad_id": env["sb"]}, headers=_headers("a")
        ).status_code
        == 200
    )
    mid = _match(client, env, "sa")
    assert (
        client.patch(
            f"{env['base']}/roster/{minor_member}", json={"squad_id": env["sa"]}, headers=_headers("a")
        ).status_code
        == 200
    )
    resp = client.put(
        f"{env['base']}/matches/{mid}/roster",
        json={"entries": [{"club_roster_member_id": minor_member, "jersey_number": 7}]},
        headers=_headers("a"),
    )
    assert resp.status_code == 200
    assert (
        client.patch(
            f"{env['base']}/roster/{minor_member}", json={"squad_id": env["sb"]}, headers=_headers("a")
        ).status_code
        == 200
    )
    with club_app.app_context():
        entry = VideoRosterEntry.query.filter_by(video_match_id=mid).one()
        match = db.session.get(VideoMatch, mid)
        match.status = "finalized"
        db.session.add(
            VideoTracklet(
                video_match_id=mid,
                pipeline_key="minor-chain",
                kind="chain",
                roster_entry_id=entry.id,
                tag_source="human",
                first_s=0,
                last_s=10,
                visible_s=10,
            )
        )
        db.session.add(
            VideoPlayerReport(
                video_match_id=mid,
                roster_entry_id=entry.id,
                club_program_id_at_finalize=env["pid"],
                club_roster_member_id_at_finalize=minor_member,
                club_local_player_id_at_finalize=minor_id,
                identity_confidence="human_confirmed",
                minutes_visible=15,
                model_version="ra2-test",
            )
        )
        db.session.commit()
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    h = _h(_email("coach"))
    assert client.get(f"{env['base']}/roster/{minor_member}/profile", headers=h).status_code == 404
    for suffix in ("", "/report", "/reel", "/media-token"):
        result = client.get(f"{env['base']}/matches/{mid}{suffix}", headers=h)
        assert result.status_code == 404
        assert "PRIVATE Squad B minor" not in result.get_data(as_text=True)


def test_profile_leaks_out_of_scope_match_summary(env, client, club_app):
    mid = _match(client, env, "sb")
    with club_app.app_context():
        db.session.get(VideoMatch, mid).capture_meta = {
            "qwen_analysis": {
                "window_captions": [{"roster_entry_id": 999, "caption": "PRIVATE Squad B player observation"}]
            }
        }
        db.session.commit()
    assert (
        client.patch(
            f"{env['base']}/roster/{env['m1']}", json={"squad_id": env["sb"]}, headers=_headers("a")
        ).status_code
        == 200
    )
    resp = client.put(
        f"{env['base']}/matches/{mid}/roster",
        json={"entries": [{"club_roster_member_id": env["m1"], "jersey_number": 7}]},
        headers=_headers("a"),
    )
    assert resp.status_code == 200
    assert (
        client.patch(
            f"{env['base']}/roster/{env['m1']}", json={"squad_id": env["sa"]}, headers=_headers("a")
        ).status_code
        == 200
    )
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    h = _h(_email("coach"))
    assert client.get(f"{env['base']}/matches/{mid}", headers=h).status_code == 404
    payload = client.get(f"{env['base']}/roster/{env['m1']}/profile", headers=h).get_json()
    assert payload.get("film", []) == []
    assert "PRIVATE Squad B player observation" not in str(payload)


@pytest.mark.parametrize(
    "path", ["squads", "staff", "map", "available-local-players", "roster/{member}/profile", "roster/{member}/photo"]
)
def test_flag_off_head_crashes_before_auth(club_app, client, monkeypatch, path):
    monkeypatch.delenv("CLUB_STAFF_ACCESS_ENABLED", raising=False)
    member = 1
    path = path.format(member=member)
    url = f"/api/club/{club_app.c2['program_a']}/{path}"
    assert client.head(url).status_code == 401


def test_demoting_coach_to_viewer_same_squad_crashes(env, client, club_app):
    from sqlalchemy.exc import IntegrityError
    from src.models.club_access import ClubAccessGrant

    _join(client, env, "coach", "coach", squads=[env["sa"]])
    with club_app.app_context():
        grant = ClubAccessGrant.query.filter_by(program_id=env["pid"], user_account_id=env["users"]["coach"]).one()
        gid = grant.id
    result = client.patch(f"{env['base']}/access/{gid}", json={"role": "viewer"}, headers=_headers("a"))
    assert result.status_code == 200
    me = client.get(f"{env['base']}/access/me", headers=_h(_email("coach"))).get_json()
    assert me["access"]["role"] == "viewer"
    assert "feedback" not in me["access"]["capabilities"]
    assert "matches.upload" not in me["access"]["capabilities"]


def test_feedback_suggestions_read_out_of_scope_match(env, client, club_app):
    from datetime import timedelta
    from uuid import uuid4

    from src.models.club_invitation import ClubInvitation, utcnow
    from src.models.showcase import PlayerProfileClaim

    mid = _match(client, env, "sb")
    assert (
        client.patch(
            f"{env['base']}/roster/{env['m1']}", json={"squad_id": env["sb"]}, headers=_headers("a")
        ).status_code
        == 200
    )
    resp = client.put(
        f"{env['base']}/matches/{mid}/roster",
        json={"entries": [{"club_roster_member_id": env["m1"], "jersey_number": 7}]},
        headers=_headers("a"),
    )
    assert resp.status_code == 200
    assert (
        client.patch(
            f"{env['base']}/roster/{env['m1']}", json={"squad_id": env["sa"]}, headers=_headers("a")
        ).status_code
        == 200
    )
    with club_app.app_context():
        claim = PlayerProfileClaim(
            player_api_id=7001,
            user_account_id=club_app.c2["users"]["scout"],
            relationship_type="player",
            status="approved",
            reviewed_at=utcnow(),
        )
        db.session.add(claim)
        db.session.flush()
        invitation = ClubInvitation(
            program_id=env["pid"],
            player_api_id=7001,
            claim_id=claim.id,
            recipient_user_id=claim.user_account_id,
            created_by_user_id=club_app.c2["users"]["a"],
            client_request_id=str(uuid4()),
            request_hash="test",
            status="accepted",
            created_at=utcnow(),
            expires_at=utcnow() + timedelta(days=7),
            responded_at=utcnow(),
        )
        db.session.add(invitation)
        db.session.flush()
        iid = invitation.id
        match = db.session.get(VideoMatch, mid)
        match.status = "finalized"
        entry = VideoRosterEntry.query.filter_by(video_match_id=mid).one()
        match.capture_meta = {
            "qwen_analysis": {
                "window_captions": [
                    {
                        "roster_entry_id": entry.id,
                        "grounded": True,
                        "box_t": 5,
                        "caption": "PRIVATE out-of-scope match observation",
                    }
                ]
            }
        }
        db.session.add(
            VideoPlayerReport(
                video_match_id=mid,
                roster_entry_id=entry.id,
                club_program_id_at_finalize=env["pid"],
                club_player_api_id_at_finalize=7001,
                identity_confidence="human_confirmed",
                model_version="ra2-test",
            )
        )
        db.session.commit()
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    h = _h(_email("coach"))
    assert client.get(f"{env['base']}/matches/{mid}", headers=h).status_code == 404
    resp = client.get(f"{env['base']}/player-feedback/suggestions?invitation_id={iid}", headers=h)
    assert resp.status_code == 200, resp.get_json()
    assert resp.get_json()["suggestions"] == []


@pytest.mark.parametrize("change", ["removed_grant", "hidden_program", "suspended_program"])
def test_live_revocation_covers_removal_and_program_standing(env, client, club_app, monkeypatch, change):
    from src.models.club_access import ClubAccessGrant
    from src.models.funding import ClubProgram
    from src.services import video_storage

    mid = _match(client, env, "sa")
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    h = _h(_email("coach"))
    token = client.get(f"{env['base']}/matches/{mid}/media-token", headers=h).get_json()["token"]
    monkeypatch.setattr(video_storage, "is_configured", lambda: True)
    monkeypatch.setattr(
        video_storage, "mint_media_read_sas", lambda path, **kw: "https://example.invalid/private-footage"
    )
    assert client.get(f"/api/admin/video/matches/{mid}/footage?token={token}").status_code == 302
    with club_app.app_context():
        if change == "removed_grant":
            db.session.delete(
                ClubAccessGrant.query.filter_by(program_id=env["pid"], user_account_id=env["users"]["coach"]).one()
            )
        elif change == "hidden_program":
            db.session.get(ClubProgram, env["pid"]).emergency_hidden = True
        else:
            db.session.get(ClubProgram, env["pid"]).platform_status = "suspended"
        db.session.commit()
    db.session.expire_all()
    assert client.get(f"{env['base']}/roster", headers=h).status_code == 403
    assert client.get(f"/api/admin/video/matches/{mid}/footage?token={token}").get_json()["error"] == "match not found"
