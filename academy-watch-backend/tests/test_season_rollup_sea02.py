"""sea02 migration replay and partial-application safety pins."""

import importlib
from collections import Counter
from contextlib import contextmanager

import pytest
import sqlalchemy as sa
from alembic import op as alembic_op
from alembic.migration import MigrationContext
from alembic.operations import Operations
from src.models.season_rollup import LeagueSeasonConfig, PlayerSeasonCell, PlayerSeasonTotal

_TABLE_COLUMNS = {
    "player_season_cells": {
        "id",
        "player_api_id",
        "season",
        "source",
        "club_api_id",
        "club_name",
        "competition_tier",
        "level_group",
        "appearances",
        "goals",
        "assists",
        "minutes",
        "yellows",
        "reds",
        "saves",
        "goals_conceded",
        "avg_rating",
        "detail",
        "synced_at",
    },
    "player_season_totals": {
        "id",
        "player_api_id",
        "season",
        "level_group",
        "appearances",
        "goals",
        "assists",
        "minutes",
        "yellows",
        "reds",
        "saves",
        "goals_conceded",
        "avg_rating",
        "primary_source",
        "fixtures_minutes",
        "journey_minutes",
        "reconcile_flag",
        "source_breakdown",
        "clubs",
        "computed_at",
    },
    "league_season_config": {"league_api_id", "season_type", "rollover_month"},
}
_INDEXES = {
    "player_season_cells": {"ix_psc_player_season"},
    "player_season_totals": {"ix_pst_season_group", "ix_pst_player"},
}
_UNIQUE_CONSTRAINTS = {
    "player_season_cells": "uq_psc_player_season_source_club_tier",
    "player_season_totals": "uq_pst_player_season_group",
}
_RLS_STATEMENTS = {
    "ALTER TABLE player_season_cells ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE player_season_totals ENABLE ROW LEVEL SECURITY",
    "ALTER TABLE league_season_config ENABLE ROW LEVEL SECURITY",
}
_CALENDAR_SEEDS = [
    (71, "calendar", 1),
    (98, "calendar", 1),
    (128, "calendar", 1),
    (253, "calendar", 1),
    (262, "calendar", 1),
]


@contextmanager
def _alembic_ops(engine):
    """Bind Alembic's operation proxy to a disposable SQLite engine."""
    conn = engine.connect()
    trans = conn.begin()
    context = MigrationContext.configure(conn)
    operations = Operations(context)
    original = getattr(alembic_op, "_proxy", None)
    alembic_op._proxy = operations
    try:
        yield
        trans.commit()
    finally:
        alembic_op._proxy = original
        conn.close()


def _sqlite_table_exists(name):
    return name in sa.inspect(alembic_op.get_bind()).get_table_names()


def _sqlite_index_exists(name):
    inspector = sa.inspect(alembic_op.get_bind())
    return any(
        name in {index["name"] for index in inspector.get_indexes(table)} for table in inspector.get_table_names()
    )


def _sqlite_create_index_safe(name, table, columns, **kwargs):
    if not _sqlite_index_exists(name):
        alembic_op.create_index(name, table, columns, **kwargs)


@pytest.fixture
def engine():
    database = sa.create_engine("sqlite:///:memory:")
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def sea02(monkeypatch):
    """Run PostgreSQL migration control flow against SQLite and capture RLS."""
    module = importlib.import_module("migrations.versions.sea02_season_rollup_tables")
    rls_statements = []

    monkeypatch.setattr(module, "table_exists", _sqlite_table_exists)
    monkeypatch.setattr(module, "index_exists", _sqlite_index_exists)
    monkeypatch.setattr(module, "create_index_safe", _sqlite_create_index_safe)

    def _execute(statement):
        sql = str(statement).strip()
        if sql.startswith("ALTER TABLE ") and sql.endswith(" ENABLE ROW LEVEL SECURITY"):
            rls_statements.append(sql)
            return None
        return alembic_op.get_bind().execute(sa.text(sql))

    monkeypatch.setattr(module.op, "execute", _execute)
    return module, rls_statements


def _assert_contract(database):
    inspector = sa.inspect(database)
    assert set(inspector.get_table_names()) == set(_TABLE_COLUMNS)
    for table, expected_columns in _TABLE_COLUMNS.items():
        assert {column["name"] for column in inspector.get_columns(table)} == expected_columns
    for table, expected_indexes in _INDEXES.items():
        index_names = [index["name"] for index in inspector.get_indexes(table)]
        assert set(index_names) == expected_indexes
        assert all(index_names.count(name) == 1 for name in expected_indexes)
    for table, expected_name in _UNIQUE_CONSTRAINTS.items():
        names = {constraint["name"] for constraint in inspector.get_unique_constraints(table)}
        assert expected_name in names


def _config_rows(database):
    with database.connect() as conn:
        return [
            tuple(row)
            for row in conn.execute(
                sa.text(
                    "SELECT league_api_id, season_type, rollover_month FROM league_season_config ORDER BY league_api_id"
                )
            )
        ]


def test_sea02_upgrade_twice_is_idempotent(engine, sea02):
    module, rls_statements = sea02

    with _alembic_ops(engine):
        module.upgrade()
    with _alembic_ops(engine):
        module.upgrade()

    _assert_contract(engine)
    assert _config_rows(engine) == _CALENDAR_SEEDS
    assert Counter(rls_statements) == Counter({statement: 2 for statement in _RLS_STATEMENTS})


def test_sea02_upgrade_completes_partial_application_without_clobbering(engine, sea02):
    """Existing tables/indexes/data survive while missing statements complete."""
    PlayerSeasonCell.__table__.create(engine)
    PlayerSeasonTotal.__table__.create(engine)
    LeagueSeasonConfig.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(sa.text("DROP INDEX ix_pst_player"))
        conn.execute(
            sa.text(
                "INSERT INTO player_season_cells "
                "(id, player_api_id, season, source, club_api_id, competition_tier, level_group, minutes, synced_at) "
                "VALUES (900, 303010, 2025, 'fixtures', 73, 'league', 'senior', 2941, '2026-07-15')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO player_season_totals "
                "(id, player_api_id, season, level_group, minutes, primary_source, computed_at) "
                "VALUES (901, 303010, 2025, 'senior', 2941, 'fixtures', '2026-07-15')"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO league_season_config (league_api_id, season_type, rollover_month) VALUES (71, 'custom', 9)"
            )
        )

    module, rls_statements = sea02
    with _alembic_ops(engine):
        module.upgrade()

    _assert_contract(engine)
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT minutes FROM player_season_cells WHERE id = 900")).scalar_one() == 2941
        assert conn.execute(sa.text("SELECT minutes FROM player_season_totals WHERE id = 901")).scalar_one() == 2941
    assert _config_rows(engine) == [
        (71, "custom", 9),
        (98, "calendar", 1),
        (128, "calendar", 1),
        (253, "calendar", 1),
        (262, "calendar", 1),
    ]
    assert Counter(rls_statements) == Counter(_RLS_STATEMENTS)
