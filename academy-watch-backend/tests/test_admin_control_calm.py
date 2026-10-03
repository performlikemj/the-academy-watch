"""Server-side list filters behind the shared filter bar: people by club, type, status; clubs by status and place."""

from datetime import timedelta

import pytest
import sqlalchemy as sa
from src.models.admin_control import now
from src.models.club_access import ClubAccessGrant
from src.models.funding import ClubProgram, ClubProgramClaim, ClubProgramManager
from src.models.league import UserAccount, db
from src.models.showcase import PlayerProfileClaim
from src.models.trust import ScoutVerification
from test_admin_control import control_app as _control_app
from test_admin_control import headers, program
from test_admin_control_postgres import pg_control as _pg_control

control_app = _control_app
pg_control = _pg_control


def account(name, **fields):
    row = UserAccount(
        email=f"{name.lower()}@example.test", display_name=name, display_name_lower=name.lower(), **fields
    )
    db.session.add(row)
    db.session.flush()
    return row


def club(first, name, country="JP", **fields):
    row = ClubProgram(
        funding_league_id=first.funding_league_id,
        name=name,
        legal_name=name,
        slug=name.lower().replace(" ", "-"),
        country=country,
        region="Test",
        **fields,
    )
    db.session.add(row)
    db.session.flush()
    return row


def manager(person, at, claim_status="approved"):
    claim = ClubProgramClaim(program_id=at.id, user_account_id=person.id, status=claim_status)
    db.session.add(claim)
    db.session.flush()
    if claim_status == "approved":
        db.session.add(
            ClubProgramManager(
                program_id=at.id,
                user_account_id=person.id,
                source_claim_id=claim.id,
                status="active",
                granted_by="admin@example.test",
            )
        )


def scout(person, status):
    db.session.add(
        ScoutVerification(
            user_account_id=person.id,
            full_name=person.display_name,
            organization="Test",
            role_title="Scout",
            statement="Evidence",
            evidence_urls=[],
            status=status,
        )
    )


def build_world(app):
    first = program()
    second = club(first, "Second Club", country="GB", platform_status="pending")
    hidden = club(
        first, "Hidden Club", country="GB", platform_status="approved", emergency_hidden=True, verified_at=now()
    )
    old = now() - timedelta(days=200)
    people = {
        "Alpha": account("Alpha", created_at=old, last_login_at=now()),
        "Bravo": account("Bravo", created_at=old, last_login_at=old),
        "Charlie": account("Charlie", created_at=old),
        "Delta": account("Delta"),
        "Echo": account("Echo", created_at=old, account_status="suspended"),
        "Foxtrot": account("Foxtrot", created_at=old),
    }
    manager(people["Alpha"], first)
    manager(people["Bravo"], first)
    manager(people["Bravo"], second)
    manager(people["Charlie"], second, claim_status="pending")
    scout(people["Delta"], "pending")
    scout(people["Echo"], "approved")
    db.session.add(
        PlayerProfileClaim(
            player_api_id=999, user_account_id=people["Foxtrot"].id, status="pending", relationship_type="player"
        )
    )
    db.session.commit()
    return {"app": app, "first": first, "second": second, "hidden": hidden, "people": people}


@pytest.fixture
def world(control_app):
    return build_world(control_app)


def names(client, query):
    response = client.get("/api/admin/people?" + query, headers=headers())
    assert response.status_code == 200, response.text
    assert response.json["total"] == len(response.json["rows"])
    return [row["display_name"] for row in response.json["rows"]]


def test_people_filter_by_club_no_club_and_waiting(world):
    client = world["app"].test_client()
    assert names(client, f"club={world['first'].id}") == ["Alpha", "Bravo"]
    assert names(client, f"club={world['second'].id}") == ["Bravo"]
    assert names(client, "club=none") == ["Charlie", "Delta", "Echo", "Foxtrot", "Test Admin", "Test Person"]
    assert names(client, f"club={world['first'].id}&role=clubs&q=brav") == ["Bravo"]
    assert names(client, "standing=waiting") == ["Charlie", "Delta", "Foxtrot"]
    assert names(client, "standing=suspended") == ["Echo"]
    rows = client.get("/api/admin/people", headers=headers()).json["rows"]
    assert {row["display_name"] for row in rows if row["waiting"]} == {"Charlie", "Delta", "Foxtrot"}


def test_people_filter_by_verified_joined_and_last_seen(world):
    client = world["app"].test_client()
    assert names(client, "verified=yes") == ["Echo"]
    assert "Echo" not in names(client, "verified=no") and "Delta" in names(client, "verified=no")
    assert names(client, "joined=7d") == ["Delta", "Test Admin", "Test Person"]
    assert names(client, "seen=7d") == ["Alpha"]
    assert "Alpha" not in names(client, "seen=quiet") and "Bravo" in names(client, "seen=quiet")
    for query in ("club=abc", "club=0", "standing=nope", "verified=maybe", "joined=1y", "seen=never"):
        refused = client.get("/api/admin/people?" + query, headers=headers())
        assert refused.status_code == 400 and refused.json["error"]


def test_staff_grants_count_as_club_members_only_when_staff_access_is_on(world, monkeypatch):
    client = world["app"].test_client()
    db.session.add(
        ClubAccessGrant(program_id=world["first"].id, user_account_id=world["people"]["Delta"].id, role="coach")
    )
    db.session.commit()
    assert names(client, f"club={world['first'].id}") == ["Alpha", "Bravo"]
    monkeypatch.setenv("CLUB_STAFF_ACCESS_ENABLED", "1")
    assert names(client, f"club={world['first'].id}") == ["Alpha", "Bravo", "Delta"]


def test_club_options_count_people_in_one_statement_under_the_other_filters(world):
    client = world["app"].test_client()
    auth = headers()
    statements = []

    def record(_conn, _cursor, statement, *_args):
        statements.append(statement)

    sa.event.listen(db.engine, "before_cursor_execute", record)
    try:
        response = client.get("/api/admin/people/clubs", headers=auth)
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", record)
    assert response.status_code == 200, response.text
    assert len([statement for statement in statements if "club_programs" in statement]) == 1
    assert response.headers["Cache-Control"] == "no-store"
    assert response.json == {
        "clubs": [
            {"id": world["first"].id, "name": "Test Program", "count": 2},
            {"id": world["second"].id, "name": "Second Club", "count": 1},
        ],
        "no_club": 6,
    }
    # The chosen club stays in the choices even when the other filters leave nobody in it.
    kept = client.get(f"/api/admin/people/clubs?standing=suspended&club={world['second'].id}", headers=auth).json
    assert kept == {"clubs": [{"id": world["second"].id, "name": "Second Club", "count": 0}], "no_club": 1}
    narrowed = client.get("/api/admin/people/clubs?q=alph&club=none", headers=auth).json
    assert narrowed == {"clubs": [{"id": world["first"].id, "name": "Test Program", "count": 1}], "no_club": 0}
    typed = client.get("/api/admin/people/clubs?club_q=seco", headers=auth).json
    assert [row["name"] for row in typed["clubs"]] == ["Second Club"] and typed["no_club"] == 6
    assert client.get("/api/admin/people/clubs?club_q=%25", headers=auth).json["clubs"] == []
    assert client.get("/api/admin/people/clubs", headers=headers(role="user")).status_code == 401


def test_people_list_stays_inside_its_statement_budget_with_every_filter(world):
    client = world["app"].test_client()
    auth = headers()
    calls = []

    def before(*_args):
        calls.append(1)

    query = f"club={world['first'].id}&role=clubs&standing=active&verified=no&joined=year&seen=quiet&q=a"
    sa.event.listen(db.engine, "before_cursor_execute", before)
    try:
        response = client.get("/api/admin/people?" + query, headers=auth)
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", before)
    assert response.status_code == 200 and len(calls) <= 12


def test_clubs_filter_by_status_verified_and_country_with_counts(world):
    client = world["app"].test_client()

    def clubs(query):
        response = client.get("/api/admin/programs?" + query, headers=headers())
        assert response.status_code == 200, response.text
        assert response.json["total"] == len(response.json["rows"])
        return [row["name"] for row in response.json["rows"]]

    assert clubs("status=pending") == ["Second Club"]
    assert clubs("status=hidden") == ["Hidden Club"]
    assert clubs("status=approved") == ["Hidden Club", "Test Program"]
    assert clubs("verified=yes") == ["Hidden Club"]
    assert clubs("country=GB") == ["Hidden Club", "Second Club"]
    assert clubs("country=GB&status=pending&verified=no&q=second") == ["Second Club"]
    assert clubs("country=ZZ") == []
    counts = client.get("/api/admin/programs/countries?country=JP", headers=headers()).json
    assert counts == {"countries": [{"value": "GB", "count": 2}, {"value": "JP", "count": 1}]}
    counts = client.get("/api/admin/programs/countries?status=pending", headers=headers()).json
    assert counts == {"countries": [{"value": "GB", "count": 1}]}
    for query in ("status=nope", "verified=maybe", "country=" + "x" * 81):
        refused = client.get("/api/admin/programs?" + query, headers=headers())
        assert refused.status_code == 400 and refused.json["error"]


@pytest.mark.parametrize(
    "path,flag",
    [("/api/admin/people/clubs", "ADMIN_PEOPLE_ENABLED"), ("/api/admin/programs/countries", "ADMIN_PROGRAMS_ENABLED")],
)
def test_option_count_endpoints_are_dark_with_their_page_flag(world, monkeypatch, path, flag):
    client = world["app"].test_client()
    monkeypatch.delenv(flag)
    assert client.get(path, headers=headers()).status_code == 404
    assert client.get("/api/admin/definitely-not-a-route", headers=headers()).status_code == 404


def test_filters_and_option_counts_run_on_postgresql(pg_control):
    world = build_world(pg_control)
    client = pg_control.test_client()
    first, second = world["first"].id, world["second"].id
    assert names(client, f"club={first}") == ["Alpha", "Bravo"]
    assert names(client, "club=none&standing=waiting") == ["Charlie", "Delta", "Foxtrot"]
    assert names(client, "verified=yes&standing=suspended&joined=year&seen=quiet") == ["Echo"]
    assert names(client, f"club={second}&role=clubs&verified=no&seen=quiet&q=brav") == ["Bravo"]
    options = client.get("/api/admin/people/clubs?club_q=o", headers=headers()).json
    assert options == {
        "clubs": [{"id": first, "name": "Test Program", "count": 2}, {"id": second, "name": "Second Club", "count": 1}],
        "no_club": 6,
    }
    places = client.get("/api/admin/programs/countries?verified=no", headers=headers()).json
    assert places == {"countries": [{"value": "GB", "count": 1}, {"value": "JP", "count": 1}]}
    listed = client.get("/api/admin/programs?country=GB&status=hidden&verified=yes", headers=headers()).json
    assert [row["name"] for row in listed["rows"]] == ["Hidden Club"] and listed["total"] == 1
