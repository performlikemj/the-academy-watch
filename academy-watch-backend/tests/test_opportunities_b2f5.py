"""Combined B1/B2 release refresh: real dark counts never appear on directory cards."""

# ruff: noqa: F811
import pytest
import sqlalchemy as sa
from src.models.league import db
from src.services import club_directory, opportunities
from test_club_directory import _club, _league, app, client, on  # noqa: F401


@pytest.mark.parametrize("flag", [None, "false"])
def test_real_dark_counts_are_none_and_b1_card_omits_field(client, on, monkeypatch, flag):
    if flag is None:
        monkeypatch.delenv("OPPORTUNITIES_ENABLED", raising=False)
    else:
        monkeypatch.setenv("OPPORTUNITIES_ENABLED", flag)
    program = _club(_league(), "B2F5 Synthetic Club")
    program_id = program.id
    queries = []

    def record(*args):
        queries.append(args[2])

    sa.event.listen(db.engine, "before_cursor_execute", record)
    try:
        assert opportunities.open_opportunity_counts([program_id]) is None
        assert club_directory.open_opportunity_counts([program_id]) is None
        assert queries == []
        response = client.get("/api/programs")
        assert response.status_code == 200
        (card,) = response.get_json()["clubs"]
        assert card["id"] == program_id
        assert "open_opportunities" not in card
        assert not any("club_opportunities" in query.lower() for query in queries)
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", record)
