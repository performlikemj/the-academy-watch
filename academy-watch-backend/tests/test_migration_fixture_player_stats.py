import importlib
from contextlib import contextmanager

import sqlalchemy as sa
from alembic import op as alembic_op
from alembic.migration import MigrationContext
from alembic.operations import Operations


@contextmanager
def alembic_ops(engine):
    """Yield an Alembic Operations proxy bound to the given engine."""
    conn = engine.connect()
    trans = conn.begin()
    ctx = MigrationContext.configure(conn)
    operations = Operations(ctx)
    original_proxy = getattr(alembic_op, "_proxy", None)
    alembic_op._proxy = operations
    try:
        yield operations
        trans.commit()
    finally:
        alembic_op._proxy = original_proxy
        conn.close()


def _load_migration_module():
    return importlib.import_module(
        "migrations.versions.h1i2j3k4l5m6_expand_player_stats_comprehensive"
    )


def _prepare_base_tables(metadata):
    sa.Table(
        "teams",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )
    sa.Table(
        "loaned_players",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )


def test_upgrade_creates_missing_fixture_stats_tables(sqlite_memory_engine):
    engine = sqlite_memory_engine
    metadata = sa.MetaData()
    _prepare_base_tables(metadata)
    metadata.create_all(engine)

    migration = _load_migration_module()

    with alembic_ops(engine):
        migration.upgrade()

    inspector = sa.inspect(engine)
    assert inspector.has_table("fixtures")
    assert inspector.has_table("fixture_player_stats")
    assert inspector.has_table("fixture_team_stats")
    assert inspector.has_table("weekly_loan_reports")
    assert inspector.has_table("weekly_loan_appearances")

    columns = {col["name"] for col in inspector.get_columns("fixture_player_stats")}
    expected = {
        "position",
        "number",
        "rating",
        "captain",
        "substitute",
        "goals_conceded",
        "saves",
        "shots_total",
        "shots_on",
        "passes_total",
        "passes_key",
        "passes_accuracy",
        "tackles_total",
        "tackles_blocks",
        "tackles_interceptions",
        "duels_total",
        "duels_won",
        "dribbles_attempts",
        "dribbles_success",
        "dribbles_past",
        "fouls_drawn",
        "fouls_committed",
        "penalty_won",
        "penalty_committed",
        "penalty_scored",
        "penalty_missed",
        "penalty_saved",
        "offsides",
    }
    assert expected.issubset(columns)


def test_upgrade_adds_missing_columns_without_dropping_data(sqlite_memory_engine):
    engine = sqlite_memory_engine
    metadata = sa.MetaData()
    _prepare_base_tables(metadata)

    fixtures = sa.Table(
        "fixtures",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("fixture_id_api", sa.Integer, nullable=False, unique=True),
    )

    fixture_player_stats = sa.Table(
        "fixture_player_stats",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("fixture_id", sa.Integer, sa.ForeignKey("fixtures.id"), nullable=False),
        sa.Column("player_api_id", sa.Integer, nullable=False),
        sa.Column("team_api_id", sa.Integer, nullable=False),
        sa.Column("minutes", sa.Integer),
        sa.Column("goals", sa.Integer),
        sa.Column("assists", sa.Integer),
        sa.Column("yellows", sa.Integer),
        sa.Column("reds", sa.Integer),
        sa.Column("raw_json", sa.Text),
    )

    metadata.create_all(engine)

    with engine.begin() as conn:
        conn.execute(fixtures.insert().values(id=1, fixture_id_api=1234))
        conn.execute(
            fixture_player_stats.insert().values(
                id=1,
                fixture_id=1,
                player_api_id=101,
                team_api_id=55,
                minutes=90,
                goals=1,
                assists=0,
                yellows=0,
                reds=0,
                raw_json="{}",
            )
        )

    migration = _load_migration_module()
    with alembic_ops(engine):
        migration.upgrade()

    inspector = sa.inspect(engine)
    columns = {col["name"] for col in inspector.get_columns("fixture_player_stats")}
    assert "position" in columns
    assert "passes_total" in columns
    assert "penalty_saved" in columns

    with engine.connect() as conn:
        row = conn.execute(
            sa.text("SELECT minutes, position, passes_total FROM fixture_player_stats WHERE id = 1")
        ).one()
        assert row.minutes == 90
        assert row.position is None
        assert row.passes_total is None
