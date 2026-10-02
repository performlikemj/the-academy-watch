# ruff: noqa: F811
"""The same approved club record and probe execute against real origin/main."""

from datetime import date

import pytest
from sqlalchemy import event
from src.models.league import db
from src.models.showcase import LocalPlayer
from test_club_console import client, club_app  # noqa: F401


@pytest.mark.parametrize("path,count", [("/api/players/{id}/showcase", 3), ("/p/{id}", 2), ("/p/{id}/card.png", 2)])
def test_signed_negative_dark_reads_match_main(club_app, client, monkeypatch, path, count):
    from src.routes.share import share_bp

    monkeypatch.setenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false")
    club_app.register_blueprint(share_bp)
    local = LocalPlayer(
        display_name="Dark signed fixture",
        provenance="club",
        origin_program_id=club_app.c2["program_a"],
        birth_date=date(2000, 1, 1),
        birth_year=2000,
        status="approved",
    )
    db.session.add(local)
    db.session.flush()
    local.api_player_id = -local.id
    db.session.commit()
    id_ = local.api_player_id
    db.session.expire_all()
    statements = []

    def count_sql(connection, cursor, statement, params, context, many):
        statements.append(statement)

    event.listen(db.engine, "before_cursor_execute", count_sql)
    try:
        response = client.get(path.format(id=id_))
    finally:
        event.remove(db.engine, "before_cursor_execute", count_sql)
    assert response.status_code == 404
    assert len(statements) == count, statements
    print(path, response.status_code, len(statements))
