"""pm01 guarded migration, schema contract, RLS, and head pins."""

import importlib
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import op as alembic_op
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

MATCH_COLUMNS = {
    "id",
    "player_api_id",
    "season",
    "source",
    "status",
    "reported_by_user_id",
    "club_program_id",
    "match_date",
    "competition",
    "opponent",
    "home_away",
    "result_for",
    "result_against",
    "minutes",
    "goals",
    "assists",
    "yellows",
    "reds",
    "saves",
    "goals_conceded",
    "note",
    "created_at",
    "updated_at",
}
MODERATION_COLUMNS = {
    "id",
    "user_account_id",
    "target_kind",
    "target_id",
    "action",
    "actor_email",
    "metadata",
    "created_at",
}
RLS_STATEMENTS = {
    'ALTER TABLE "player_match_entries" ENABLE ROW LEVEL SECURITY',
    'ALTER TABLE "showcase_moderation_events" ENABLE ROW LEVEL SECURITY',
}


@contextmanager
def _alembic_ops(engine):
    conn = engine.connect()
    transaction = conn.begin()
    context = MigrationContext.configure(conn)
    operations = Operations(context)
    original = getattr(alembic_op, "_proxy", None)
    alembic_op._proxy = operations
    try:
        yield
        transaction.commit()
    finally:
        alembic_op._proxy = original
        conn.close()


def _sqlite_table_exists(name):
    return name in sa.inspect(alembic_op.get_bind()).get_table_names()


def _sqlite_column_exists(table, column):
    inspector = sa.inspect(alembic_op.get_bind())
    return table in inspector.get_table_names() and column in {item["name"] for item in inspector.get_columns(table)}


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
    metadata = sa.MetaData()
    sa.Table(
        "user_accounts",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
    )
    sa.Table(
        "club_programs",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
    )
    sa.Table(
        "local_players",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("api_player_id", sa.Integer(), nullable=True),
    )
    metadata.create_all(database)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def pm01(monkeypatch):
    module = importlib.import_module("migrations.versions.pm01_player_match_entries")
    rls_statements = []
    monkeypatch.setattr(module, "table_exists", _sqlite_table_exists)
    monkeypatch.setattr(module, "column_exists", _sqlite_column_exists)
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
    assert set(inspector.get_table_names()) == {
        "user_accounts",
        "club_programs",
        "local_players",
        "player_match_entries",
        "showcase_moderation_events",
    }
    assert {column["name"] for column in inspector.get_columns("player_match_entries")} == MATCH_COLUMNS
    assert {column["name"] for column in inspector.get_columns("showcase_moderation_events")} == MODERATION_COLUMNS

    match_indexes = {index["name"] for index in inspector.get_indexes("player_match_entries")}
    assert match_indexes == {
        "ix_player_match_entries_player_season",
        "ix_player_match_entries_club_program",
    }
    moderation_indexes = {index["name"] for index in inspector.get_indexes("showcase_moderation_events")}
    assert moderation_indexes == {"ix_showcase_moderation_events_user_created"}
    local_indexes = {index["name"] for index in inspector.get_indexes("local_players")}
    assert "ux_local_players_api_player_id" in local_indexes

    unique_names = {constraint["name"] for constraint in inspector.get_unique_constraints("player_match_entries")}
    assert "uq_player_match_entries_identity" in unique_names
    check_names = {constraint["name"] for constraint in inspector.get_check_constraints("player_match_entries")}
    assert check_names == {
        "ck_player_match_entries_source",
        "ck_player_match_entries_status",
        "ck_player_match_entries_home_away",
        "ck_player_match_entries_minutes",
        "ck_player_match_entries_counts",
        "ck_player_match_entries_optional_counts",
    }
    assert {constraint["name"] for constraint in inspector.get_check_constraints("showcase_moderation_events")} == {
        "ck_showcase_moderation_events_action"
    }
    foreign_keys = {
        (tuple(fk["constrained_columns"]), fk["referred_table"])
        for fk in inspector.get_foreign_keys("player_match_entries")
    }
    assert foreign_keys == {
        (("reported_by_user_id",), "user_accounts"),
        (("club_program_id",), "club_programs"),
    }


def test_pm01_upgrade_twice_is_idempotent_and_rls_is_exact(engine, pm01):
    module, rls_statements = pm01
    with _alembic_ops(engine):
        module.upgrade()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO player_match_entries "
                "(id,player_api_id,season,source,status,reported_by_user_id,match_date,opponent,home_away) "
                "VALUES (1,-7,2025,'self','self_reported',1,'2025-09-01','Rivals','home')"
            )
        )
    with _alembic_ops(engine):
        module.upgrade()

    _assert_contract(engine)
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT player_api_id FROM player_match_entries WHERE id=1")).scalar_one() == -7
    assert Counter(rls_statements) == Counter({statement: 2 for statement in RLS_STATEMENTS})


def test_pm01_duplicate_local_links_skip_partial_unique_index(engine, pm01):
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO local_players (id,api_player_id) VALUES (1,9001),(2,9001)"))
    module, rls_statements = pm01

    with _alembic_ops(engine):
        module.upgrade()

    assert "ux_local_players_api_player_id" not in {
        index["name"] for index in sa.inspect(engine).get_indexes("local_players")
    }
    assert Counter(rls_statements) == Counter(RLS_STATEMENTS)


def test_pm01_downgrade_twice_is_guarded_and_keeps_existing_tables(engine, pm01):
    module, _ = pm01
    with _alembic_ops(engine):
        module.upgrade()
    with _alembic_ops(engine):
        module.downgrade()
    with _alembic_ops(engine):
        module.downgrade()

    inspector = sa.inspect(engine)
    assert set(inspector.get_table_names()) == {"user_accounts", "club_programs", "local_players"}
    assert "ux_local_players_api_player_id" not in {index["name"] for index in inspector.get_indexes("local_players")}


def test_pm01_downgrade_refuses_to_discard_moderation_history(engine, pm01):
    module, _ = pm01
    with _alembic_ops(engine):
        module.upgrade()
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO showcase_moderation_events "
                "(id,target_kind,target_id,action) VALUES (1,'profile',44,'rejected')"
            )
        )

    with pytest.raises(RuntimeError, match="downgrade refused: showcase moderation history exists"):
        with _alembic_ops(engine):
            module.downgrade()

    assert {
        "player_match_entries",
        "showcase_moderation_events",
    }.issubset(sa.inspect(engine).get_table_names())
    assert "ux_local_players_api_player_id" in {
        index["name"] for index in sa.inspect(engine).get_indexes("local_players")
    }


def test_cb01_to_s2f1_to_pm01_is_the_single_head():
    repo_root = Path(__file__).resolve().parent.parent
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "migrations"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["cb01"]
    assert script.get_revision("cb01").down_revision == "s2f1"
    assert script.get_revision("s2f1").down_revision == "pm01"
    assert script.get_revision("pm01").down_revision == "lp01"
