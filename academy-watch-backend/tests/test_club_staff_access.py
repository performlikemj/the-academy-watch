# ruff: noqa: F811

"""Club staff access (p2a2): roles, squad scope, invites and live revocation.

Every scoped route gets a negative test.  All data is fictional.
"""

from datetime import timedelta

import pytest
from flask import g
from src.auth import issue_user_token
from src.models.club_access import ClubAccessGrant, ClubAccessGrantSquad, ClubStaffInvite
from src.models.funding import ClubRosterMember, ClubSquad, FundingAdminEvent
from src.models.league import UserAccount, db
from src.models.video import VideoMatch
from src.routes.club_access import club_access_bp
from src.routes.feedback import feedback_bp
from src.services import club_access as access_service
from test_club_console import _add_api_member, _admin_headers, _headers, client, club_app  # noqa: F401

STAFF = ("coach", "analyst", "viewer", "invmgr", "stranger", "allcoach")


def _h(email):
    return {"Authorization": f"Bearer {issue_user_token(email)['token']}"}


def _email(key):
    return f"{key}@staff.example"


@pytest.fixture
def env(club_app, client, monkeypatch):
    monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "true")
    monkeypatch.setenv("PILOT_CLUB_RELATIONSHIPS_ENABLED", "true")
    monkeypatch.setenv("CLUB_MATCH_QUOTA_DEFAULT", "20")
    club_app.register_blueprint(club_access_bp, url_prefix="/api")
    club_app.register_blueprint(feedback_bp, url_prefix="/api")
    sent = []
    monkeypatch.setattr(
        access_service, "send_invite_email", lambda invite, token, name: sent.append((invite.email, token)) or True
    )
    pid = club_app.c2["program_a"]
    with club_app.app_context():
        users = {}
        for key in STAFF:
            user = UserAccount(email=_email(key), display_name=f"Staff {key}", display_name_lower=f"staff {key}")
            db.session.add(user)
            users[key] = user
        sa_ = ClubSquad(program_id=pid, name="Squad A", kind="other", sort_order=0)
        sb_ = ClubSquad(program_id=pid, name="Squad B", kind="other", sort_order=1)
        db.session.add_all([sa_, sb_])
        db.session.commit()
        ids = {"users": {k: u.id for k, u in users.items()}, "sa": sa_.id, "sb": sb_.id}
    m1 = _add_api_member(client, pid, 7001)
    m2 = _add_api_member(client, pid, 7002)
    base = f"/api/club/{pid}"
    assert client.patch(f"{base}/roster/{m1}", json={"squad_id": ids["sa"]}, headers=_headers("a")).status_code == 200
    assert client.patch(f"{base}/roster/{m2}", json={"squad_id": ids["sb"]}, headers=_headers("a")).status_code == 200
    ids.update(pid=pid, base=base, m1=m1, m2=m2, sent=sent)
    # Explicit, audited owner bootstrap for the verified manager "a".
    resp = client.post(
        f"/api/admin/programs/{pid}/owner",
        json={"user_account_id": club_app.c2["users"]["a"], "reason": "Verified with the club secretary"},
        headers=_admin_headers(),
    )
    assert resp.status_code == 200, resp.get_json()
    return ids


def _invite(client, env, email, role, *, squads=None, all_squads=False, key="a"):
    body = {"email": email, "role": role, "all_squads": all_squads, "squad_ids": squads or []}
    resp = client.post(f"{env['base']}/staff-invites", json=body, headers=_headers(key))
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["invite"], env["sent"][-1][1]


def _accept(client, token, key):
    return client.post("/api/me/staff-invites/accept", json={"token": token}, headers=_h(_email(key)))


def _join(client, env, key, role, **kw):
    _, token = _invite(client, env, _email(key), role, **kw)
    resp = _accept(client, token, key)
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _match(client, env, squad_key):
    resp = client.post(
        f"{env['base']}/matches",
        json={"opponent_name": "Fictional Rovers", "match_date": "2026-09-01", "squad_id": env[squad_key]},
        headers=_headers("a"),
    )
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["id"]


# ---------------------------------------------------------------------------
# Flag off: byte-for-byte today
# ---------------------------------------------------------------------------


def test_flag_off_is_todays_behaviour(club_app, client, monkeypatch):
    monkeypatch.delenv("CLUB_STAFF_ACCESS_ENABLED", raising=False)
    club_app.register_blueprint(club_access_bp, url_prefix="/api")
    pid = club_app.c2["program_a"]
    with club_app.app_context():
        user = UserAccount(email=_email("coach"), display_name="Coach", display_name_lower="coach")
        db.session.add(user)
        db.session.flush()
        db.session.add(ClubAccessGrant(program_id=pid, user_account_id=user.id, role="manager", all_squads=True))
        db.session.commit()
    # A stray grant row confers nothing while dark.
    assert client.get(f"/api/club/{pid}/roster", headers=_h(_email("coach"))).status_code == 403
    assert client.get(f"/api/club/{pid}/roster", headers=_h(_email("coach"))).get_json() == {
        "error": "Club manager access denied"
    }
    for path in (f"/api/club/{pid}/access/me", f"/api/club/{pid}/access", "/api/me/club-access"):
        assert client.get(path, headers=_headers("a")).status_code == 404
    assert client.post("/api/me/staff-invites/accept", json={"token": "x" * 40}, headers=_headers("a")).status_code == (
        404
    )
    # Manager payloads carry no new keys.
    match = client.post(
        f"/api/club/{pid}/matches", json={"opponent_name": "Fictional FC", "squad_id": 1}, headers=_headers("a")
    )
    assert match.status_code == 201 and "squad_id" not in match.get_json()
    with club_app.app_context():
        assert db.session.get(VideoMatch, match.get_json()["id"]).squad_id is None
    token = client.get(f"/api/club/{pid}/matches/{match.get_json()['id']}/media-token", headers=_headers("a"))
    from src.auth import media_token_claims

    with club_app.app_context():
        assert "club_user_id" not in media_token_claims(token.get_json()["token"], match.get_json()["id"])


def test_features_flag_key_only_when_on(monkeypatch):
    from flask import Flask
    from src.routes.api import features

    app = Flask(__name__)
    with app.test_request_context():
        monkeypatch.delenv("CLUB_STAFF_ACCESS_ENABLED", raising=False)
        assert features().get_json() == {"contact_rail": False}
        monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "true")
        assert features().get_json()["club_staff_access"] is True


# ---------------------------------------------------------------------------
# Owner bootstrap
# ---------------------------------------------------------------------------


def test_owner_is_admin_only_and_audited(env, client, club_app):
    pid = env["pid"]
    # No admin credentials → denied.
    assert (
        client.post(
            f"/api/admin/programs/{pid}/owner", json={"user_account_id": 1, "reason": "x"}, headers=_headers("a")
        ).status_code
        != 200
    )
    # Owner must already be a claim-verified manager; never inferred for invited staff.
    resp = client.post(
        f"/api/admin/programs/{pid}/owner",
        json={"user_account_id": env["users"]["coach"], "reason": "test"},
        headers=_admin_headers(),
    )
    assert resp.status_code == 409 and resp.get_json()["error"] == "owner_must_be_verified_manager"
    assert (
        client.post(
            f"/api/admin/programs/{pid}/owner",
            json={"user_account_id": env["users"]["coach"]},
            headers=_admin_headers(),
        ).status_code
        == 422
    )
    with club_app.app_context():
        event = FundingAdminEvent.query.filter_by(action="club_access.owner_assigned", target_id=pid).one()
        assert event.reason == "Verified with the club secretary"
    me = client.get(f"{env['base']}/access/me", headers=_headers("a")).get_json()["access"]
    assert me["role"] == "owner" and "access.manage" in me["capabilities"]


def test_verified_manager_without_owner_keeps_full_access_but_cannot_invite(env, client):
    resp = client.delete(f"/api/admin/programs/{env['pid']}/owner", json={"reason": "t"}, headers=_admin_headers())
    assert resp.status_code == 200
    me = client.get(f"{env['base']}/access/me", headers=_headers("a")).get_json()["access"]
    assert me["role"] == "manager" and me["verified"]
    for method, path, body in (
        ("get", "roster", None),
        ("get", "map", None),
        ("get", "staff", None),
        ("get", "profile", None),
        ("get", "matches", None),
        ("get", "results", None),
        ("get", "invitations", None),
        ("patch", "branding", {"primary_color": "#0F3D2E"}),
        ("get", "access", None),
    ):
        assert getattr(client, method)(f"{env['base']}/{path}", json=body, headers=_headers("a")).status_code == 200
    assert (
        client.post(
            f"{env['base']}/staff-invites", json={"email": "x@staff.example", "role": "viewer"}, headers=_headers("a")
        ).status_code
        == 403
    )


# ---------------------------------------------------------------------------
# Invites: replay, expiry, wrong email, revocation, reissue
# ---------------------------------------------------------------------------


def test_invite_is_bound_to_verified_email_and_one_use(env, client, club_app):
    invite, token = _invite(client, env, _email("coach"), "coach", squads=[env["sa"]])
    with club_app.app_context():
        row = db.session.get(ClubStaffInvite, invite["id"])
        assert row.token_hash != token and token not in str(row.to_dict())
        assert len(row.token_hash) == 64
    # Receipt/click grants nothing: no grant until an authenticated accept.
    assert client.get(f"{env['base']}/roster", headers=_h(_email("coach"))).status_code == 403
    wrong = _accept(client, token, "stranger")
    assert wrong.status_code == 403 and wrong.get_json()["error"] == "invite_wrong_account"
    preview = client.post("/api/me/staff-invites/preview", json={"token": token}, headers=_h(_email("stranger")))
    assert preview.get_json()["state"] == "invite_wrong_account" and "program" not in preview.get_json()
    assert (
        client.post("/api/me/staff-invites/preview", json={"token": token}, headers=_h(_email("coach"))).get_json()[
            "state"
        ]
        == "ready"
    )
    ok = _accept(client, token, "coach")
    assert ok.status_code == 200 and ok.get_json()["access"]["role"] == "coach"
    replay = _accept(client, token, "coach")
    assert replay.status_code == 409 and replay.get_json()["error"] == "invite_used"
    assert _accept(client, "not-a-real-token-" * 3, "coach").status_code == 404
    assert client.post("/api/me/staff-invites/accept", json={"token": token}).status_code == 401


def test_invite_expiry_revocation_and_reissue(env, client, club_app):
    invite, token = _invite(client, env, _email("viewer"), "viewer", squads=[env["sa"]])
    with club_app.app_context():
        row = db.session.get(ClubStaffInvite, invite["id"])
        row.expires_at = row.created_at - timedelta(seconds=1)
        db.session.commit()
    expired = _accept(client, token, "viewer")
    assert expired.status_code == 410 and expired.get_json()["error"] == "invite_expired"

    invite, token = _invite(client, env, _email("viewer"), "viewer", squads=[env["sa"]])
    assert client.post(f"{env['base']}/staff-invites/{invite['id']}/revoke", headers=_headers("a")).status_code == 200
    revoked = _accept(client, token, "viewer")
    assert revoked.status_code == 410 and revoked.get_json()["error"] == "invite_revoked"

    _, old_token = _invite(client, env, _email("viewer"), "viewer", squads=[env["sa"]])
    _, new_token = _invite(client, env, _email("viewer"), "viewer", squads=[env["sa"]])
    assert _accept(client, old_token, "viewer").get_json()["error"] == "invite_revoked"
    assert _accept(client, new_token, "viewer").status_code == 200


def test_invite_validation(env, client):
    base = f"{env['base']}/staff-invites"
    for body, code in (
        ({"email": "not-an-email", "role": "coach", "all_squads": True}, 422),
        ({"email": _email("coach"), "role": "owner", "all_squads": True}, 422),
        ({"email": _email("coach"), "role": "coach"}, 422),  # scoped role needs a scope
        ({"email": _email("coach"), "role": "coach", "squad_ids": [999999]}, 404),
        ({"email": "manager-a@c2.example", "role": "viewer", "all_squads": True}, 409),
    ):
        resp = client.post(base, json=body, headers=_headers("a"))
        assert resp.status_code == code, (body, resp.get_json())
    # A squad from another club can never be scoped in.
    foreign = client.post(
        f"/api/club/{env['pid'] + 0}/squads", json={"name": "Other", "kind": "other"}, headers=_headers("b")
    )
    assert foreign.status_code == 403


def test_deleted_squad_invite_scope_unavailable(env, client, club_app):
    _, token = _invite(client, env, _email("coach"), "coach", squads=[env["sb"]])
    assert client.delete(f"{env['base']}/squads/{env['sb']}", headers=_headers("a")).status_code == 200
    resp = _accept(client, token, "coach")
    assert resp.status_code == 409 and resp.get_json()["error"] == "invite_scope_unavailable"


# ---------------------------------------------------------------------------
# Squad scope — coach of squad A can't read squad B, on every scoped route
# ---------------------------------------------------------------------------


def test_coach_scoped_players(env, client):
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    h = _h(_email("coach"))
    base = env["base"]
    roster = client.get(f"{base}/roster", headers=h).get_json()["members"]
    assert [m["id"] for m in roster] == [env["m1"]]
    assert client.get(f"{base}/roster?squad_id={env['sb']}", headers=h).status_code == 404
    assert client.get(f"{base}/roster?squad_id=none", headers=h).get_json()["members"] == []
    assert [s["id"] for s in client.get(f"{base}/squads", headers=h).get_json()["squads"]] == [env["sa"]]
    body = client.get(f"{base}/map", headers=h).get_json()
    assert [s["id"] for s in body["squads"]] == [env["sa"]] and body["unassigned_count"] == 0
    assert client.get(f"{base}/roster/{env['m1']}/profile", headers=h).status_code == 200
    assert client.get(f"{base}/roster/{env['m2']}/profile", headers=h).status_code == 404
    assert client.get(f"{base}/roster/{env['m2']}/photo", headers=h).status_code == 404


@pytest.mark.parametrize("role", ["coach", "analyst", "viewer"])
def test_scoped_roles_denied_manager_routes(env, client, role):
    _join(client, env, role, role, squads=[env["sa"]])
    h = _h(_email(role))
    base = env["base"]
    denied = [
        ("post", "roster", {"player_api_id": 7001}),
        ("put", f"roster/{env['m1']}/brief", {"body": "x"}),
        ("put", "system-brief", {"body": "x"}),
        ("delete", f"roster/{env['m1']}", None),
        ("patch", f"roster/{env['m1']}", {"shirt_number": 4}),
        ("get", "available-local-players", None),
        ("post", "squads", {"name": "New", "kind": "other"}),
        ("patch", f"squads/{env['sa']}", {"name": "Renamed"}),
        ("delete", f"squads/{env['sa']}", None),
        ("post", "squads/reorder", {"ids": [env["sa"], env["sb"]]}),
        ("post", "squads/template", {}),
        ("get", "staff", None),
        ("post", "staff", {"display_name": "X", "title": "Y"}),
        ("patch", "branding", {"primary_color": "#0F3D2E"}),
        ("post", "branding/banner", {"content_type": "image/jpeg"}),
        ("post", "branding/banner/complete", {}),
        ("get", "profile", None),
        ("put", "profile", {}),
        ("get", "updates", None),
        ("post", "updates", {}),
        ("get", "results", None),
        ("post", "results", {}),
        ("get", "invitations", None),
        ("post", "invitations", {}),
        ("post", f"roster/{env['m1']}/photo", {"content_type": "image/jpeg"}),
        ("delete", f"roster/{env['m1']}/photo", None),
        ("post", f"roster/{env['m1']}/photo/complete", {}),
        ("get", "access", None),
        ("post", "staff-invites", {"email": "x@staff.example", "role": "viewer", "all_squads": True}),
    ]
    for method, path, body in denied:
        resp = getattr(client, method)(f"{base}/{path}", json=body, headers=h)
        assert resp.status_code == 403, (role, method, path, resp.status_code)
    assert client.get(f"{base}/roster", headers=h).status_code == 200


def test_coach_scoped_matches_and_media(env, client, club_app):
    match_a = _match(client, env, "sa")
    match_b = _match(client, env, "sb")
    with club_app.app_context():
        whole = VideoMatch(club_program_id=env["pid"], status="created", opponent_name="Unscoped")
        db.session.add(whole)
        db.session.commit()
        whole_id = whole.id
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    h = _h(_email("coach"))
    base = env["base"]
    listed = client.get(f"{base}/matches", headers=h).get_json()["matches"]
    assert [m["id"] for m in listed] == [match_a] and listed[0]["squad_id"] == env["sa"]
    for mid in (match_b, whole_id):
        for method, path, body in (
            ("get", f"matches/{mid}", None),
            ("get", f"matches/{mid}/media-token", None),
            ("get", f"matches/{mid}/reel", None),
            ("get", f"matches/{mid}/report", None),
            ("patch", f"matches/{mid}", {"opponent_name": "X"}),
            ("post", f"matches/{mid}/sas", {}),
            ("post", f"matches/{mid}/upload-complete", {}),
            ("put", f"matches/{mid}/roster", {"entries": [{"club_roster_member_id": env["m1"], "jersey_number": 9}]}),
            ("post", f"matches/{mid}/process", {}),
        ):
            resp = getattr(client, method)(f"{base}/{path}", json=body, headers=h)
            assert resp.status_code == 404, (mid, method, path, resp.status_code)
    assert client.get(f"{base}/matches/{match_a}", headers=h).status_code == 200
    # Scoped staff must file footage inside their squads, and can't move it out.
    assert client.post(f"{base}/matches", json={"opponent_name": "X"}, headers=h).status_code == 400
    assert client.post(
        f"{base}/matches", json={"opponent_name": "X", "squad_id": env["sb"]}, headers=h
    ).status_code == (400)
    own = client.post(f"{base}/matches", json={"opponent_name": "X", "squad_id": env["sa"]}, headers=h)
    assert own.status_code == 201
    assert client.patch(f"{base}/matches/{match_a}", json={"squad_id": env["sb"]}, headers=h).status_code == 400
    # Match roster only from the coach's squads.
    other = client.put(
        f"{base}/matches/{match_a}/roster",
        json={"entries": [{"club_roster_member_id": env["m2"], "jersey_number": 9}]},
        headers=h,
    )
    assert other.status_code == 400
    mine = client.put(
        f"{base}/matches/{match_a}/roster",
        json={"entries": [{"club_roster_member_id": env["m1"], "jersey_number": 9}]},
        headers=h,
    )
    assert mine.status_code == 200


def test_viewer_is_read_only(env, client, club_app):
    match_a = _match(client, env, "sa")
    with club_app.app_context():
        member = db.session.get(ClubRosterMember, env["m1"])
        member.coach_brief_body = "Private coaching note"
        db.session.commit()
    _join(client, env, "viewer", "viewer", squads=[env["sa"]])
    h = _h(_email("viewer"))
    base = env["base"]
    roster = client.get(f"{base}/roster", headers=h).get_json()
    assert roster["members"][0]["brief"]["body"] is None and roster["system_brief"]["body"] is None
    assert client.get(f"{base}/matches/{match_a}", headers=h).status_code == 200
    assert client.get(f"{base}/matches/{match_a}/media-token", headers=h).status_code == 200
    for method, path, body in (
        ("post", "matches", {"opponent_name": "X", "squad_id": env["sa"]}),
        ("patch", f"matches/{match_a}", {"opponent_name": "X"}),
        ("post", f"matches/{match_a}/sas", {}),
        ("post", f"matches/{match_a}/upload-complete", {}),
        ("put", f"matches/{match_a}/roster", {"entries": []}),
        ("post", f"matches/{match_a}/process", {}),
        ("get", "player-feedback", None),
        ("post", "player-feedback", {}),
    ):
        assert getattr(client, method)(f"{base}/{path}", json=body, headers=h).status_code == 403, path


def test_analyst_has_no_feedback_coach_does(env, client):
    _join(client, env, "analyst", "analyst", squads=[env["sa"]])
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    base = env["base"]
    assert client.get(f"{base}/player-feedback", headers=_h(_email("analyst"))).status_code == 403
    assert client.get(f"{base}/player-feedback/suggestions", headers=_h(_email("analyst"))).status_code == 403
    assert client.get(f"{base}/player-feedback", headers=_h(_email("coach"))).status_code == 200
    assert client.post(
        f"{base}/matches", json={"opponent_name": "X", "squad_id": env["sa"]}, headers=_h(_email("analyst"))
    ).status_code == (201)


def test_feedback_actor_scope(env, client, club_app):
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    with club_app.test_request_context():
        g.user_id = env["users"]["coach"]
        allowed = access_service.club_actor_allowed
        assert allowed(db.session, env["pid"], env["users"]["coach"], "feedback", subject_signed_id=7001)
        assert not allowed(db.session, env["pid"], env["users"]["coach"], "feedback", subject_signed_id=7002)
        assert not allowed(db.session, club_app.c2["program_b"], env["users"]["coach"], "feedback")
        assert not allowed(db.session, env["pid"], env["users"]["stranger"], "feedback")


def test_all_squads_coach_sees_everything_squad_side_but_not_unassigned(env, client):
    _join(client, env, "allcoach", "coach", all_squads=True)
    h = _h(_email("allcoach"))
    ids = {m["id"] for m in client.get(f"{env['base']}/roster", headers=h).get_json()["members"]}
    assert ids == {env["m1"], env["m2"]}
    assert client.patch(f"{env['base']}/branding", json={}, headers=h).status_code == 403


def test_cross_club_is_denied(env, client, club_app):
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    other = club_app.c2["program_b"]
    for path in ("roster", "map", "matches", "squads", "access/me"):
        assert client.get(f"/api/club/{other}/{path}", headers=_h(_email("coach"))).status_code == 403


# ---------------------------------------------------------------------------
# Revocation and narrowing take effect immediately, including media tokens
# ---------------------------------------------------------------------------


def _footage(client, match_id, token):
    return client.get(f"/api/admin/video/matches/{match_id}/footage?token={token}").get_json()


def test_revoked_grant_loses_access_immediately(env, client):
    match_a = _match(client, env, "sa")
    joined = _join(client, env, "coach", "coach", squads=[env["sa"]])
    assert joined["program_id"] == env["pid"]
    h = _h(_email("coach"))
    token = client.get(f"{env['base']}/matches/{match_a}/media-token", headers=h).get_json()["token"]
    before = _footage(client, match_a, token)
    assert before["error"] != "match not found"  # token accepted; footage simply absent in tests
    people = client.get(f"{env['base']}/access", headers=_headers("a")).get_json()["people"]
    grant_id = next(p["grant_id"] for p in people if p["email"] == _email("coach"))
    assert client.delete(f"{env['base']}/access/{grant_id}", headers=_headers("a")).status_code == 200
    assert client.get(f"{env['base']}/roster", headers=h).status_code == 403
    assert client.get(f"{env['base']}/matches/{match_a}", headers=h).status_code == 403
    assert _footage(client, match_a, token)["error"] == "match not found"
    assert client.get("/api/me/club-access", headers=h).get_json()["programs"] == []


def test_narrowed_scope_revokes_old_squad_media(env, client):
    match_a = _match(client, env, "sa")
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    h = _h(_email("coach"))
    token = client.get(f"{env['base']}/matches/{match_a}/media-token", headers=h).get_json()["token"]
    people = client.get(f"{env['base']}/access", headers=_headers("a")).get_json()["people"]
    grant = next(p for p in people if p["email"] == _email("coach"))
    resp = client.patch(
        f"{env['base']}/access/{grant['grant_id']}",
        json={"role": "coach", "all_squads": False, "squad_ids": [env["sb"]], "expected_version": grant["version"]},
        headers=_headers("a"),
    )
    assert resp.status_code == 200
    assert _footage(client, match_a, token)["error"] == "match not found"
    assert client.get(f"{env['base']}/roster/{env['m1']}/profile", headers=h).status_code == 404
    assert client.get(f"{env['base']}/roster/{env['m2']}/profile", headers=h).status_code == 200
    stale = client.patch(
        f"{env['base']}/access/{grant['grant_id']}",
        json={"role": "viewer", "expected_version": grant["version"]},
        headers=_headers("a"),
    )
    assert stale.status_code == 409


def test_manager_token_rechecked_when_manager_revoked(env, client, club_app):
    from src.models.funding import ClubProgramManager

    match_a = _match(client, env, "sa")
    token = client.get(f"{env['base']}/matches/{match_a}/media-token", headers=_headers("a")).get_json()["token"]
    with club_app.app_context():
        row = ClubProgramManager.query.filter_by(user_account_id=club_app.c2["users"]["a"]).first()
        row.status = "revoked"
        db.session.commit()
    assert _footage(client, match_a, token)["error"] == "match not found"


def test_squad_delete_drops_scope_row(env, client, club_app):
    _join(client, env, "coach", "coach", squads=[env["sa"], env["sb"]])
    assert client.delete(f"{env['base']}/squads/{env['sb']}", headers=_headers("a")).status_code == 200
    with club_app.app_context():
        # SQLite fixtures don't enforce FK cascades; Postgres does (ondelete=CASCADE). Mirror it here.
        ClubAccessGrantSquad.query.filter_by(squad_id=env["sb"]).delete()
        db.session.commit()
    ids = {m["id"] for m in client.get(f"{env['base']}/roster", headers=_h(_email("coach"))).get_json()["members"]}
    assert ids == {env["m1"]}


# ---------------------------------------------------------------------------
# Invited manager, owner protections, listing
# ---------------------------------------------------------------------------


def test_invited_manager(env, client):
    _join(client, env, "invmgr", "manager")
    h = _h(_email("invmgr"))
    base = env["base"]
    assert client.post(f"{base}/squads", json={"name": "Invited", "kind": "other"}, headers=h).status_code == 201
    assert client.patch(f"{base}/branding", json={}, headers=h).status_code == 200
    assert client.get(f"{base}/staff", headers=h).status_code == 200
    assert client.get(f"{base}/access", headers=h).status_code == 200
    me = client.get(f"{base}/access/me", headers=h).get_json()["access"]
    assert me["role"] == "manager" and not me["verified"]
    # Staff access, billing and claim-verified club actions stay out of reach.
    for method, path in (("post", "staff-invites"), ("get", "results"), ("get", "invitations")):
        assert getattr(client, method)(f"{base}/{path}", json={}, headers=h).status_code == 403
    assert {"access.manage", "billing", "results", "contact", "player_invitations"}.isdisjoint(me["capabilities"])
    local = client.post(
        "/api/local-players",
        json={
            "display_name": "Fictional Local",
            "birth_year": 2001,
            "position": "Forward",
            "country": "Japan",
            "club_program_id": env["pid"],
        },
        headers=h,
    )
    assert local.status_code != 403, local.get_json()


def test_owner_protections_and_listing(env, client, club_app):
    _join(client, env, "coach", "coach", squads=[env["sa"]])
    with club_app.app_context():
        owner = ClubAccessGrant.query.filter_by(program_id=env["pid"], role="owner").one()
        owner_id = owner.id
    assert client.delete(f"{env['base']}/access/{owner_id}", headers=_headers("a")).get_json()["error"] == (
        "owner_admin_only"
    )
    assert client.patch(f"{env['base']}/access/{owner_id}", json={"role": "viewer"}, headers=_headers("a")).get_json()[
        "error"
    ] == ("owner_admin_only")
    listing = client.get(f"{env['base']}/access", headers=_headers("a")).get_json()
    roles = {p["email"]: p["role"] for p in listing["people"]}
    assert roles["manager-a@c2.example"] == "owner" and roles[_email("coach")] == "coach"
    assert listing["matrix"]["roles"]["viewer"] == [True, False, False, False, False, False, False]
    assert listing["matrix"]["roles"]["coach"] == [True, True, True, False, False, False, False]
    assert listing["matrix"]["roles"]["manager"][-1] is False
    assert any(a["action"] == "invite_accepted" for a in listing["activity"])
    programs = client.get("/api/me/club-access", headers=_h(_email("coach"))).get_json()["programs"]
    assert [p["program"]["id"] for p in programs] == [env["pid"]]


def test_hidden_program_denies_staff(env, client, club_app):
    from src.models.funding import ClubProgram

    _join(client, env, "coach", "coach", squads=[env["sa"]])
    # The fixture's app context is shared with requests; edit through that session.
    db.session.get(ClubProgram, env["pid"]).emergency_hidden = True
    db.session.commit()
    assert client.get(f"{env['base']}/roster", headers=_h(_email("coach"))).status_code == 403


def test_account_erasure_and_export(env, client, club_app):
    from src.services.account import _club_access_export, _erase_club_access_rows, _SchemaView

    _join(client, env, "coach", "coach", squads=[env["sa"]])
    _invite(client, env, _email("viewer"), "viewer", all_squads=True)
    coach = db.session.get(UserAccount, env["users"]["coach"])
    exported = _club_access_export(coach)
    assert exported["grants"][0]["role"] == "coach"
    assert exported["invites_received"][0]["status"] == "accepted"
    assert "token_hash" not in str(exported)
    assert _club_access_export(db.session.get(UserAccount, env["users"]["stranger"])) is None
    counts = _erase_club_access_rows(_SchemaView(), coach.id, coach.email)
    assert counts == {"club_access_grants": 1, "club_staff_invites": 1}
    counts = _erase_club_access_rows(_SchemaView(), env["users"]["viewer"], _email("viewer"))
    assert counts == {"club_access_grants": 0, "club_staff_invites": 1}
    owner_id = club_app.c2["users"]["a"]
    _erase_club_access_rows(_SchemaView(), owner_id, "manager-a@c2.example")
    db.session.commit()
    assert ClubAccessGrant.query.filter_by(user_account_id=env["users"]["coach"]).count() == 0
    assert ClubAccessGrantSquad.query.count() == 0
    assert ClubStaffInvite.query.filter(ClubStaffInvite.invited_by_user_id == owner_id).count() == 0


def test_player_profile_redacted_by_role(env, client):
    member = db.session.get(ClubRosterMember, env["m1"])
    member.coach_brief_body = "Private coaching note"
    member.note = "Private manager note"
    db.session.commit()
    full = client.get(f"{env['base']}/roster/{env['m1']}/profile", headers=_headers("a")).get_json()
    assert full["note"] == "Private manager note" and "coach_brief" in full
    _join(client, env, "viewer", "viewer", squads=[env["sa"]])
    _join(client, env, "analyst", "analyst", squads=[env["sa"]])
    viewer = client.get(f"{env['base']}/roster/{env['m1']}/profile", headers=_h(_email("viewer"))).get_json()
    assert {"note", "coach_brief", "development"}.isdisjoint(viewer) and "brief" not in viewer["identity"]
    assert set(viewer.get("scout_interest", {})) <= {"locked", "reason"}
    analyst = client.get(f"{env['base']}/roster/{env['m1']}/profile", headers=_h(_email("analyst"))).get_json()
    assert "development" not in analyst and analyst["coach_brief"]
