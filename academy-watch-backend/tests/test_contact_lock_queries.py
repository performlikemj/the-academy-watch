# ruff: noqa: F811, F401
"""RC1XV3-O: SQL statement counts on ordinary (C1 flag unset) contact routes; same file on both heads."""

import sqlalchemy as sa
from src.models.league import db
from test_contact import (  # noqa: F401
    _claim,
    _club_manager,
    _club_program,
    _create,
    _verified_scout,
    client,
    contact_app,
)


def test_counts(client):
    _club_program(101, "On Platform FC")
    _club_program(102, "Second FC")
    club_manager, club_headers = _club_manager(101, "included-manager@example.com")
    _club_manager(102, "included-manager@example.com")
    scout, scout_headers = _verified_scout("included-scout@example.com")
    player, player_headers, _ = _claim(
        "included-player@example.com",
        5802,
        contract_status="contracted",
        current_club_name="On Platform FC",
        club_program_id=101,
    )
    _, direct_headers, _ = _claim("direct-player@example.com", 5803)
    rid = _create(client, scout_headers, 5802).get_json()["contact_request"]["id"]
    rid2 = _create(client, scout_headers, 5803).get_json()["contact_request"]["id"]
    assert client.post(f"/api/contact/requests/{rid}/accept", headers=player_headers).status_code == 200
    assert client.post(f"/api/contact/requests/{rid2}/accept", headers=direct_headers).status_code == 200
    assert (
        client.post(
            f"/api/contact/requests/{rid}/club-consent", json={"action": "grant"}, headers=club_headers
        ).status_code
        == 200
    )
    db.session.remove()
    statements = []

    def before(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    sa.event.listen(db.engine, "before_cursor_execute", before)
    out = []
    # Messages GET: +3 since the thread DTO carries the viewer's ``can_send`` — one block lookup inside
    # its savepoint (SAVEPOINT / SELECT / RELEASE). Lists reuse the block lookup they already made.
    expected_counts = [13, 13, 24, 19, 19, 23, 14, 20, 13]
    for index, (name, method, url, headers, data) in enumerate(
        [
            ("list sent (scout)", "GET", "/api/contact/requests?box=sent", scout_headers, None),
            ("list inbox (player)", "GET", "/api/contact/requests?box=inbox", player_headers, None),
            ("list club box (manager of 2 clubs)", "GET", "/api/contact/requests?box=club", club_headers, None),
            ("messages GET scout, club-included", "GET", f"/api/contact/requests/{rid}/messages", scout_headers, None),
            (
                "messages GET player, club-included",
                "GET",
                f"/api/contact/requests/{rid}/messages",
                player_headers,
                None,
            ),
            ("messages GET club", "GET", f"/api/contact/requests/{rid}/messages", club_headers, None),
            ("messages GET scout, direct", "GET", f"/api/contact/requests/{rid2}/messages", scout_headers, None),
            (
                "message POST scout, club-included",
                "POST",
                f"/api/contact/requests/{rid}/messages",
                scout_headers,
                {"body": "hi"},
            ),
            (
                "message POST scout, direct",
                "POST",
                f"/api/contact/requests/{rid2}/messages",
                scout_headers,
                {"body": "hi"},
            ),
        ]
    ):
        statements.clear()
        r = client.open(url, method=method, headers=headers, json=data)
        assert r.status_code in {200, 201}, (name, r.status_code, r.json)
        assert len(statements) == expected_counts[index], (name, len(statements), expected_counts[index])
        out.append(f"RC1XV3-O COUNT {name}: status={r.status_code} statements={len(statements)}")
        db.session.remove()
    sa.event.remove(db.engine, "before_cursor_execute", before)
    print("\n" + "\n".join(out))
