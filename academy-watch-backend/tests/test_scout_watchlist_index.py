"""sw01: the scout watchlist gains a per-player index; the migration chains from head c201 and guards DDL."""

from pathlib import Path

from src.models.scout_watchlist import ScoutWatchlistEntry

MIGRATION = Path(__file__).resolve().parents[1] / "migrations/versions/sw01_scout_watchlist_player_index.py"


def test_model_declares_player_index():
    index = next(
        (i for i in ScoutWatchlistEntry.__table__.indexes if i.name == "ix_scout_watchlist_player"),
        None,
    )
    assert index is not None
    assert [column.name for column in index.columns] == ["player_api_id"]


def test_migration_chains_from_c201_and_guards_ddl():
    source = MIGRATION.read_text()
    assert 'revision = "sw01"' in source
    assert 'down_revision = "c201"' in source
    assert "create_index_safe(INDEX, TABLE" in source
    assert "table_exists(TABLE)" in source
    assert "index_exists(INDEX)" in source
    assert "op.create_index(" not in source
