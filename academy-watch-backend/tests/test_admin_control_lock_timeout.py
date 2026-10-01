"""O5: shipped SQL/migration release queued account reads on contention."""

import importlib.util
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


@pytest.fixture
def lock_database():
    uri = os.getenv("P2_B3_TEST_DATABASE_URL")
    if not uri:
        pytest.skip("set P2_B3_TEST_DATABASE_URL for PostgreSQL regression")
    url = sa.engine.make_url(uri)
    assert url.host in {"localhost", "127.0.0.1"} and url.database == "aw_p2_b3"
    name = "aw_p2_b3_lock_" + uuid4().hex
    admin = sa.create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.exec_driver_sql(f"CREATE DATABASE {name}")
    engine = sa.create_engine(url.set(database=name))
    try:
        with engine.begin() as conn:
            for ddl in (
                "CREATE TABLE user_accounts(id integer primary key,email varchar(254))",
                "INSERT INTO user_accounts VALUES(1,'main@example.test')",
                "CREATE TABLE club_programs(id integer primary key)",
                "CREATE TABLE content_reports(id integer primary key,subject_type varchar(40),subject_id varchar(200),status varchar(20),created_at timestamp,resolved_at timestamp)",
                "CREATE TABLE player_suppressions(id integer primary key,player_api_id integer,local_player_id integer,status varchar(20),created_at timestamp,decided_at timestamp)",
            ):
                conn.exec_driver_sql(ddl)
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.exec_driver_sql(f"DROP DATABASE {name} WITH (FORCE)")
        admin.dispose()


def waiting(observer, pid):
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        if observer.exec_driver_sql(
            "SELECT 1 FROM pg_locks WHERE pid=%s AND relation='user_accounts'::regclass AND NOT granted", (pid,)
        ).scalar():
            return
        time.sleep(0.01)
    pytest.fail("account lock waiter never appeared")


@pytest.mark.parametrize("path", ["preapply", "migration"])
def test_contended_upgrade_rolls_back_and_releases_account_reads(lock_database, path):
    engine = lock_database
    spec = importlib.util.spec_from_file_location(
        "lock_test_p2b3", Path(__file__).parents[1] / "migrations/versions/p2b3_admin_control.py"
    )
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    sql_path = Path.home() / "codex-runs/aw-redesign/p2b3_preapply.sql"
    if path == "preapply" and not sql_path.exists():
        pytest.skip("external preapply is a release-machine artifact")
    with engine.connect() as older, engine.connect() as ddl, engine.connect() as reader, engine.connect() as observer:
        observer = observer.execution_options(isolation_level="AUTOCOMMIT")
        older.exec_driver_sql("SELECT id,email FROM user_accounts").all()
        ddl_pid = ddl.exec_driver_sql("SELECT pg_backend_pid()").scalar()
        reader_pid = reader.exec_driver_sql("SELECT pg_backend_pid()").scalar()
        ddl.commit()
        reader.commit()

        def apply():
            started = time.monotonic()
            try:
                if path == "preapply":
                    ddl.exec_driver_sql(sql_path.read_text())
                else:
                    with Operations.context(MigrationContext.configure(ddl)):
                        migration.upgrade()
                ddl.commit()
            except sa.exc.DBAPIError as exc:
                assert getattr(exc.orig, "sqlstate", getattr(exc.orig, "pgcode", None)) == "55P03"
                ddl.rollback()
                return time.monotonic() - started
            pytest.fail("contended ALTER must fail within explicit lock timeout")

        with ThreadPoolExecutor(max_workers=2) as pool:
            upgrade = pool.submit(apply)
            waiting(observer, ddl_pid)
            lookup = pool.submit(lambda: reader.exec_driver_sql("SELECT id,email FROM user_accounts WHERE id=1").one())
            waiting(observer, reader_pid)
            assert 4 <= upgrade.result(timeout=9) < 8
            assert lookup.result(timeout=2) == (1, "main@example.test")
            assert older.in_transaction()
            assert not sa.inspect(observer).has_table("safeguarding_cases")
            assert "account_status" not in {c["name"] for c in sa.inspect(observer).get_columns("user_accounts")}
        reader.rollback()
        older.rollback()
        if path == "preapply":
            ddl.exec_driver_sql(sql_path.read_text())
        else:
            with Operations.context(MigrationContext.configure(ddl)):
                migration.upgrade()
        ddl.commit()
        assert "account_status" in {c["name"] for c in sa.inspect(observer).get_columns("user_accounts")}
