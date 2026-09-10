"""Partial P4 installations must still support legacy report evidence."""

import pytest
import sqlalchemy as sa
from src.models.league import db
from test_pilot_cohort import action, observe, report, result_table
from test_pilot_cohort import app as app
from test_pilot_cohort import client as client
from test_pilot_cohort import register as register


@pytest.mark.parametrize("has_link_column", [False, True])
@pytest.mark.parametrize("has_observation", [False, True])
def test_legacy_evidence_with_optional_result_link(client, register, has_link_column, has_observation):
    row = action()
    if has_observation:
        observe(register, row)
    table = result_table()
    if not has_link_column:
        db.session.execute(sa.text("ALTER TABLE player_match_entries DROP COLUMN club_result_id"))
        db.session.commit()
    # Force observation validation to fetch its row, not reuse the seeded object.
    db.session.expunge_all()
    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT") and "FROM player_match_entries" in statement:
            statements.append(statement)

    sa.event.listen(db.engine, "before_cursor_execute", capture)
    try:
        payload = report(client, register)
        assert payload["capabilities"]["stable_results"] is has_link_column
        assert payload["summary"]["qualifying_people"] == int(has_observation)
        assert statements
        if not has_link_column:
            assert all("club_result_id" not in statement for statement in statements)
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", capture)
        db.session.rollback()
        table.drop(db.engine)
