import importlib
import types
from contextlib import contextmanager
from datetime import datetime

import pytest
import sqlalchemy as sa
from alembic import op as alembic_op
from alembic.migration import MigrationContext
from alembic.operations import Operations


@contextmanager
def alembic_ops(engine, connection_patch=None):
    """Provide Alembic Operations bound to the given engine, optionally patching the SQLAlchemy connection."""
    conn = engine.connect()
    cleanup = None
    if connection_patch:
        cleanup = connection_patch(conn)
    trans = conn.begin()
    ctx = MigrationContext.configure(conn)
    operations = Operations(ctx)
    original_proxy = getattr(alembic_op, "_proxy", None)
    alembic_op._proxy = operations
    try:
        yield operations
        trans.commit()
    finally:
        if cleanup:
            cleanup()
        alembic_op._proxy = original_proxy
        conn.close()


def _load_migration_module():
    return importlib.import_module("migrations.versions.v1w2x3y4z5a6_deprecate_supplemental_loans")


def _prepare_base_tables(metadata):
    players = sa.Table(
        "players",
        metadata,
        sa.Column("player_id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
        sa.Column("sofascore_id", sa.Integer, nullable=True),
        sa.UniqueConstraint("player_id"),
    )
    sa.Index("ix_players_sofascore_id", players.c.sofascore_id, unique=True)

    sa.Table(
        "teams",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("team_id", sa.Integer, nullable=False),
    )

    sa.Table(
        "loaned_players",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("player_id", sa.Integer, nullable=False),
        sa.Column("player_name", sa.String(255)),
        sa.Column("age", sa.Integer),
        sa.Column("nationality", sa.String(64)),
        sa.Column("primary_team_id", sa.Integer),
        sa.Column("primary_team_name", sa.String(255)),
        sa.Column("loan_team_id", sa.Integer),
        sa.Column("loan_team_name", sa.String(255)),
        sa.Column("team_ids", sa.String(255)),
        sa.Column("window_key", sa.String(64)),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("1")),
        sa.Column("data_source", sa.String(64)),
        sa.Column("can_fetch_stats", sa.Boolean, nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime, nullable=False, default=datetime.utcnow),
        sa.Column("updated_at", sa.DateTime, nullable=False, default=datetime.utcnow),
    )

    sa.Table(
        "supplemental_loans",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("player_name", sa.String(255)),
        sa.Column("parent_team_id", sa.Integer),
        sa.Column("parent_team_name", sa.String(255)),
        sa.Column("loan_team_id", sa.Integer),
        sa.Column("loan_team_name", sa.String(255)),
        sa.Column("season_year", sa.Integer),
        sa.Column("api_player_id", sa.Integer),
        sa.Column("sofascore_player_id", sa.Integer),
        sa.Column("data_source", sa.String(64)),
        sa.Column("source_url", sa.String(255)),
        sa.Column("wiki_title", sa.String(255)),
        sa.Column("is_verified", sa.Boolean, default=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("updated_at", sa.DateTime, nullable=False),
    )


def _skip_sofascore_lookup(conn):
    """Patch the SQLAlchemy connection so sofascore lookups return empty results."""
    original_execute = conn.execute
    state = {'skipped': False}

    def fake_execute(self, clauseelement, *multiparams, **params):
        sql_text = str(clauseelement)
        if "SELECT player_id FROM players WHERE sofascore_id" in sql_text and not state['skipped']:
            state['skipped'] = True
            return original_execute(sa.text("SELECT player_id FROM players WHERE 1=0"))
        return original_execute(clauseelement, *multiparams, **params)

    conn.execute = types.MethodType(fake_execute, conn)

    def cleanup():
        conn.execute = original_execute

    return cleanup


def test_upgrade_reuses_existing_player_when_sofascore_matches(sqlite_memory_engine):
    engine = sqlite_memory_engine
    metadata = sa.MetaData()
    _prepare_base_tables(metadata)
    metadata.create_all(engine)

    players = metadata.tables["players"]
    teams = metadata.tables["teams"]
    supplemental_loans = metadata.tables["supplemental_loans"]

    existing_player_id = 5001
    sofascore_id = 1018321
    created_ts = datetime(2025, 9, 29, 12, 47, 40)
    updated_ts = datetime(2025, 9, 30, 4, 54, 48)

    with engine.begin() as conn:
        conn.execute(
            players.insert().values(
                player_id=existing_player_id,
                name="Joe Hugill",
                created_at=created_ts,
                updated_at=updated_ts,
                sofascore_id=sofascore_id,
            )
        )
        conn.execute(teams.insert(), [{"id": 1, "team_id": 100}, {"id": 2, "team_id": 200}])
        conn.execute(
            supplemental_loans.insert().values(
                id=1,
                player_name="Joe Hugill",
                parent_team_id=1,
                parent_team_name="Manchester United",
                loan_team_id=2,
                loan_team_name="Altrincham",
                season_year=2025,
                api_player_id=None,
                sofascore_player_id=sofascore_id,
                data_source="brave",
                source_url=None,
                wiki_title=None,
                is_verified=True,
                created_at=created_ts,
                updated_at=updated_ts,
            )
        )

    migration = _load_migration_module()
    with alembic_ops(engine):
        migration.upgrade()

    with engine.connect() as conn:
        player_count = conn.execute(sa.text("SELECT COUNT(*) FROM players")).scalar()
        assert player_count == 1, "No duplicate players should be created for shared sofascore_id"

        loan_row = conn.execute(
            sa.text(
                "SELECT player_id, migration_source FROM loaned_players "
                "WHERE player_name = 'Joe Hugill'"
            )
        ).one()
        assert loan_row.player_id == existing_player_id
        assert loan_row.migration_source == "supplemental_loan"


def test_upgrade_handles_sofascore_conflict_even_if_lookup_skipped(sqlite_memory_engine):
    engine = sqlite_memory_engine
    metadata = sa.MetaData()
    _prepare_base_tables(metadata)
    metadata.create_all(engine)

    players = metadata.tables["players"]
    teams = metadata.tables["teams"]
    supplemental_loans = metadata.tables["supplemental_loans"]

    sofascore_id = 1018321
    created_ts = datetime(2025, 9, 29, 12, 47, 40)
    updated_ts = datetime(2025, 9, 30, 4, 54, 48)

    with engine.begin() as conn:
        conn.execute(
            players.insert().values(
                player_id=7001,
                name="Existing Joe Hugill",
                created_at=created_ts,
                updated_at=updated_ts,
                sofascore_id=sofascore_id,
            )
        )
        conn.execute(teams.insert(), [{"id": 1, "team_id": 100}, {"id": 2, "team_id": 200}])
        conn.execute(
            supplemental_loans.insert().values(
                id=1,
                player_name="Joe Hugill",
                parent_team_id=1,
                parent_team_name="Manchester United",
                loan_team_id=2,
                loan_team_name="Altrincham",
                season_year=2025,
                api_player_id=None,
                sofascore_player_id=sofascore_id,
                data_source="brave",
                source_url=None,
                wiki_title=None,
                is_verified=True,
                created_at=created_ts,
                updated_at=updated_ts,
            )
        )

    migration = _load_migration_module()
    with alembic_ops(engine, connection_patch=_skip_sofascore_lookup):
        migration.upgrade()

    with engine.connect() as conn:
        player_rows = conn.execute(
            sa.text("SELECT player_id FROM players WHERE sofascore_id = :sid"),
            {"sid": sofascore_id},
        ).fetchall()
        assert len(player_rows) == 1

        loan_row = conn.execute(
            sa.text(
                "SELECT player_id, migration_source FROM loaned_players "
                "WHERE player_name = 'Joe Hugill'"
            )
        ).one()
        assert loan_row.player_id == player_rows[0][0]
        assert loan_row.migration_source == "supplemental_loan"
