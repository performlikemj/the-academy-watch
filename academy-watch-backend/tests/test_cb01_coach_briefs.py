"""cb01 guarded migration, owning-row schema, and head pins."""

import importlib
from contextlib import contextmanager
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import op as alembic_op
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

MEMBER_COLUMNS = {
    "id",
    "program_id",
    "coach_brief_body",
    "brief_updated_at",
    "brief_updated_by_user_id",
}
PROGRAM_COLUMNS = {
    "id",
    "system_brief_body",
    "system_brief_updated_at",
    "system_brief_updated_by_user_id",
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


def _sqlite_add_column_safe(table, column):
    if not _sqlite_column_exists(table, column.name):
        alembic_op.add_column(table, column)


@pytest.fixture
def engine():
    database = sa.create_engine("sqlite:///:memory:")
    metadata = sa.MetaData()
    sa.Table("user_accounts", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    sa.Table("club_programs", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    sa.Table(
        "club_roster_members",
        metadata,
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("program_id", sa.Integer(), nullable=False),
    )
    metadata.create_all(database)
    try:
        yield database
    finally:
        database.dispose()


@pytest.fixture
def cb01(monkeypatch):
    module = importlib.import_module("migrations.versions.cb01_coach_briefs")
    constraints = set()
    created_constraints = []
    monkeypatch.setattr(module, "table_exists", _sqlite_table_exists)
    monkeypatch.setattr(module, "column_exists", _sqlite_column_exists)
    monkeypatch.setattr(module, "add_column_safe", _sqlite_add_column_safe)
    monkeypatch.setattr(module, "_constraint_exists", lambda _table, name: name in constraints)

    def create_foreign_key(name, source, referent, local_cols, remote_cols, *, ondelete):
        created_constraints.append((name, source, referent, tuple(local_cols), tuple(remote_cols), ondelete))
        constraints.add(name)

    def drop_constraint(name, _table, *, type_):
        assert type_ == "foreignkey"
        constraints.remove(name)

    monkeypatch.setattr(module.op, "create_foreign_key", create_foreign_key)
    monkeypatch.setattr(module.op, "drop_constraint", drop_constraint)
    return module, constraints, created_constraints


def test_cb01_upgrade_twice_is_idempotent_and_keeps_owning_tables(engine, cb01):
    module, constraints, created_constraints = cb01
    original_tables = set(sa.inspect(engine).get_table_names())
    with _alembic_ops(engine):
        module.upgrade()
    with engine.begin() as conn:
        conn.execute(sa.text("INSERT INTO club_programs (id,system_brief_body) VALUES (1,'keep shape')"))
        conn.execute(
            sa.text(
                "INSERT INTO club_roster_members (id,program_id,coach_brief_body) VALUES (1,1,'scan before receiving')"
            )
        )
    with _alembic_ops(engine):
        module.upgrade()

    inspector = sa.inspect(engine)
    assert set(inspector.get_table_names()) == original_tables
    assert {column["name"] for column in inspector.get_columns("club_programs")} == PROGRAM_COLUMNS
    assert {column["name"] for column in inspector.get_columns("club_roster_members")} == MEMBER_COLUMNS
    assert constraints == {name for _table, _column, name in module.AUDIT_FOREIGN_KEYS}
    assert created_constraints == [
        (
            "fk_club_roster_members_brief_updated_by_user_id",
            "club_roster_members",
            "user_accounts",
            ("brief_updated_by_user_id",),
            ("id",),
            "SET NULL",
        ),
        (
            "fk_club_programs_system_brief_updated_by_user_id",
            "club_programs",
            "user_accounts",
            ("system_brief_updated_by_user_id",),
            ("id",),
            "SET NULL",
        ),
    ]
    with engine.connect() as conn:
        assert (
            conn.execute(sa.text("SELECT system_brief_body FROM club_programs WHERE id=1")).scalar_one() == "keep shape"
        )
        assert (
            conn.execute(sa.text("SELECT coach_brief_body FROM club_roster_members WHERE id=1")).scalar_one()
            == "scan before receiving"
        )


def test_cb01_downgrade_drops_all_six_columns_guardedly(engine, cb01):
    module, constraints, _created_constraints = cb01
    with _alembic_ops(engine):
        module.upgrade()
    with _alembic_ops(engine):
        module.downgrade()
    with _alembic_ops(engine):
        module.downgrade()

    inspector = sa.inspect(engine)
    assert constraints == set()
    assert {column["name"] for column in inspector.get_columns("club_programs")} == {"id"}
    assert {column["name"] for column in inspector.get_columns("club_roster_members")} == {"id", "program_id"}


def test_cb01_repairs_fks_when_audit_columns_were_preapplied_without_them(engine, cb01):
    module, constraints, created_constraints = cb01
    with _alembic_ops(engine):
        alembic_op.add_column(
            "club_roster_members",
            sa.Column("brief_updated_by_user_id", sa.Integer(), nullable=True),
        )
        alembic_op.add_column(
            "club_programs",
            sa.Column("system_brief_updated_by_user_id", sa.Integer(), nullable=True),
        )
    with _alembic_ops(engine):
        module.upgrade()

    assert constraints == {name for _table, _column, name in module.AUDIT_FOREIGN_KEYS}
    assert len(created_constraints) == 2
    assert {column["name"] for column in sa.inspect(engine).get_columns("club_programs")} == PROGRAM_COLUMNS
    assert {column["name"] for column in sa.inspect(engine).get_columns("club_roster_members")} == MEMBER_COLUMNS


def test_cb01_creates_no_table_and_inherits_existing_rls():
    source = (Path(__file__).resolve().parents[1] / "migrations/versions/cb01_coach_briefs.py").read_text()
    assert "op.create_table" not in source
    assert "RLS is inherited" in source
    assert "table_exists(table)" in source
    assert "add_column_safe(table, column)" in source
    assert "_constraint_exists(table, constraint)" in source
    assert 'ondelete="SET NULL"' in source


def test_cb01_is_the_single_head_and_chains_from_current_pm01_head():
    repo_root = Path(__file__).resolve().parent.parent
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "migrations"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["cb01"]
    assert script.get_revision("cb01").down_revision == "pm01"
    assert script.get_revision("pm01").down_revision == "lp01"
