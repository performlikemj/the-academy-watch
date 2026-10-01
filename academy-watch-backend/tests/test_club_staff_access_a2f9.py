# ruff: noqa: F401, F811
"""A2F9 regressions (synthetic data only).

1. The Staff & access board's permission marks are the capabilities ``resolve_club_access`` returns
   for that person — for every role x verified state — so an invited (unverified) manager is never
   shown a verified-only right such as deciding scout requests.
2. A multi-squad grant keeps its whole squad set through a role-only change, and loses exactly the
   squad that was removed (what the access editor now sends).
"""

import pytest
from src.models.funding import ClubProgram, ClubSquad
from src.models.league import db
from src.services import club_access as access_service
from src.services.club_access import BOARD_MATRIX, ROLE_CAPABILITIES, VERIFIED_ONLY
from test_club_console import _admin_headers, _headers
from test_club_staff_access import _email, _h, _join, client, club_app, env

ROWS = [label for label, _ in BOARD_MATRIX]
SCOUT_ROW = ROWS.index("Decide on scout requests")
INVITED = (("invmgr", "manager"), ("coach", "coach"), ("analyst", "analyst"), ("viewer", "viewer"))


def _board(client, env, key="a"):
    resp = client.get(f"{env['base']}/access", headers=_headers(key))
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


def _resolved_marks(env, user_id):
    access = access_service.resolve_club_access(user_id, env["pid"])
    capabilities = access.capabilities if access is not None else frozenset()
    return access, [cap in capabilities for _, cap in BOARD_MATRIX]


def _join_everyone(client, env):
    for key, role in INVITED:
        _join(client, env, key, role, all_squads=True)


def _assert_board_matches_resolver(env, board, expected_states):
    seen = set()
    for person in board["people"]:
        access, marks = _resolved_marks(env, person["user_account_id"])
        assert access is not None
        assert person["permissions"] == marks, person
        assert (person["role"], person["verified"]) == (access.role, access.verified), person
        seen.add((access.role, access.verified))
    assert seen == expected_states


def test_board_marks_equal_resolved_capabilities_for_every_role_and_verified_state(env, client, club_app):
    _join_everyone(client, env)
    board = _board(client, env)
    assert board["matrix"] == {"rows": ROWS}
    # Owner in place: verified owner + every invited (unverified) role.
    _assert_board_matches_resolver(
        env,
        board,
        {("owner", True), ("manager", False), ("coach", False), ("analyst", False), ("viewer", False)},
    )
    # Owner removed: the same account is now a verified manager next to the invited, unverified one.
    resp = client.delete(f"/api/admin/programs/{env['pid']}/owner", json={"reason": "t"}, headers=_admin_headers())
    assert resp.status_code == 200
    board = _board(client, env)
    _assert_board_matches_resolver(
        env,
        board,
        {("manager", True), ("manager", False), ("coach", False), ("analyst", False), ("viewer", False)},
    )
    by_email = {p["email"]: p for p in board["people"]}
    verified = by_email["manager-a@c2.example"]["permissions"]
    invited = by_email[_email("invmgr")]["permissions"]
    assert verified[SCOUT_ROW] is True and invited[SCOUT_ROW] is False
    # Apart from the verified-only row the two managers read the same.
    assert [m for i, m in enumerate(verified) if i != SCOUT_ROW] == [m for i, m in enumerate(invited) if i != SCOUT_ROW]


def test_invited_manager_board_matches_what_the_api_enforces(env, client):
    _join(client, env, "invmgr", "manager")
    person = next(p for p in _board(client, env)["people"] if p["email"] == _email("invmgr"))
    marks = dict(zip(ROWS, person["permissions"], strict=True))
    assert marks == {
        "See their squads' players": True,
        "Upload matches & see reports": True,
        "Send feedback to players": True,
        "Recruiting & trials": True,
        "Decide on scout requests": False,
        "Edit club page & branding": True,
        "Billing & staff access": False,
    }
    me = client.get(f"{env['base']}/access/me", headers=_h(_email("invmgr"))).get_json()["access"]
    assert "contact" not in me["capabilities"]
    # The invited manager's own view of the board says the same thing.
    own = next(p for p in _board_as(client, env, "invmgr")["people"] if p["email"] == _email("invmgr"))
    assert own["permissions"] == person["permissions"]


def _board_as(client, env, key):
    resp = client.get(f"{env['base']}/access", headers=_h(_email(key)))
    assert resp.status_code == 200, resp.get_json()
    return resp.get_json()


@pytest.mark.parametrize("role", ["owner", "manager", "coach", "analyst", "viewer"])
@pytest.mark.parametrize("verified", [True, False])
def test_board_permissions_is_a_pure_view_of_the_resolved_capabilities(role, verified):
    capabilities = ROLE_CAPABILITIES[role] if verified else ROLE_CAPABILITIES[role] - VERIFIED_ONLY
    access = access_service.ClubAccess(program_id=1, user_id=1, role=role, verified=verified, capabilities=capabilities)
    assert access_service.board_permissions(access) == [cap in capabilities for _, cap in BOARD_MATRIX]
    if not verified:
        assert access_service.board_permissions(access)[SCOUT_ROW] is False
    assert access_service.board_permissions(None) == [False] * len(BOARD_MATRIX)


def test_inert_grants_show_no_rights_on_the_admin_board(env, client, club_app):
    """A hidden club's invited staff resolve to no access; the admin board says so instead of promising rights."""
    _join_everyone(client, env)
    db.session.get(ClubProgram, env["pid"]).emergency_hidden = True
    db.session.commit()
    resp = client.get(f"/api/admin/programs/{env['pid']}/access", headers=_admin_headers())
    assert resp.status_code == 200, resp.get_json()
    invited = [p for p in resp.get_json()["people"] if p["email"].endswith("@staff.example")]
    assert len(invited) == len(INVITED)
    for person in invited:
        assert access_service.resolve_club_access(person["user_account_id"], env["pid"]) is None
        assert person["permissions"] == [False] * len(BOARD_MATRIX)


def _three_squad_coach(client, env, club_app):
    third = ClubSquad(program_id=env["pid"], name="Squad C", kind="other", sort_order=2)
    db.session.add(third)
    db.session.commit()
    squads = sorted([env["sa"], env["sb"], third.id])
    _join(client, env, "coach", "coach", squads=squads)
    person = next(p for p in _board(client, env)["people"] if p["email"] == _email("coach"))
    assert person["squad_ids"] == squads and person["all_squads"] is False
    return person, squads


def test_role_only_change_keeps_every_squad_and_removal_drops_exactly_one(env, client, club_app):
    person, squads = _three_squad_coach(client, env, club_app)
    url = f"{env['base']}/access/{person['grant_id']}"
    # What the editor sends for "change role only": the full, unchanged squad set.
    resp = client.patch(
        url,
        json={"role": "analyst", "all_squads": False, "squad_ids": squads, "expected_version": person["version"]},
        headers=_headers("a"),
    )
    assert resp.status_code == 200, resp.get_json()
    person = next(p for p in _board(client, env)["people"] if p["email"] == _email("coach"))
    assert (person["role"], person["squad_ids"], person["all_squads"]) == ("analyst", squads, False)
    me = client.get(f"{env['base']}/access/me", headers=_h(_email("coach"))).get_json()["access"]
    assert me["squad_ids"] == squads
    # Remove one squad: exactly the other two remain.
    resp = client.patch(
        url,
        json={"role": "analyst", "all_squads": False, "squad_ids": squads[1:], "expected_version": person["version"]},
        headers=_headers("a"),
    )
    assert resp.status_code == 200, resp.get_json()
    me = client.get(f"{env['base']}/access/me", headers=_h(_email("coach"))).get_json()["access"]
    assert me["squad_ids"] == squads[1:]
