"""club_registry._table_columns introspects once per HTTP request, and every call outside one."""

from flask import Flask
from sqlalchemy import text
from src.models.league import db
from src.services import club_registry


def test_table_columns_is_memoized_per_request_only(monkeypatch):
    app = Flask(__name__)
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(app)
    with app.app_context():
        db.session.execute(
            text("CREATE TABLE probe_table (id INTEGER PRIMARY KEY, name VARCHAR(40))")
        )
        calls = []
        real = club_registry._introspect_table_columns

        def counting(table_name):
            calls.append(table_name)
            return real(table_name)

        monkeypatch.setattr(club_registry, "_introspect_table_columns", counting)

        with app.test_request_context("/"):
            first = club_registry._table_columns("probe_table")
            second = club_registry._table_columns("probe_table")
        assert first == {"id", "name"}
        assert second == first
        assert calls == ["probe_table"]

        with app.test_request_context("/"):
            club_registry._table_columns("probe_table")
        assert calls == ["probe_table", "probe_table"]

        club_registry._table_columns("probe_table")
        club_registry._table_columns("probe_table")
        assert len(calls) == 4
        db.session.remove()
