"""Durable transfer-event persistence regressions."""

import importlib
from copy import deepcopy
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from src.models.league import db
from src.models.transfer_event import PlayerTransferEvent
from src.services.transfer_events import record_transfer_events

PLAYER_ID = 284492
HALL_TRANSFERS = [
    {
        "date": "2023-08-22",
        "type": "Loan",
        "teams": {
            "out": {"id": 49, "name": "Chelsea", "logo": "chelsea.png"},
            "in": {"id": 34, "name": "Newcastle", "logo": "newcastle.png"},
        },
    },
    {
        "date": "2024-07-01",
        "type": "€ 33M",
        "teams": {
            "out": {"id": 49, "name": "Chelsea", "logo": "chelsea.png"},
            "in": {"id": 34, "name": "Newcastle", "logo": "newcastle.png"},
        },
    },
]


def _utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def test_tre01_migration_matches_model_metadata(monkeypatch):
    migration = importlib.import_module("migrations.versions.tre01_player_transfer_events")
    captured = {}

    def capture_table(name, *elements):
        captured["table"] = sa.Table(name, sa.MetaData(), *elements)

    def capture_index(name, table_name, columns, **kwargs):
        captured["index"] = (name, table_name, tuple(columns), kwargs)

    monkeypatch.setattr(migration, "table_exists", lambda table_name: False)
    monkeypatch.setattr(migration.op, "create_table", capture_table)
    monkeypatch.setattr(migration, "create_index_safe", capture_index)
    monkeypatch.setattr(migration.op, "execute", lambda statement: captured.setdefault("rls", statement))

    migration.upgrade()

    migration_table = captured["table"]
    model_table = PlayerTransferEvent.__table__
    dialect = postgresql.dialect()

    assert migration_table.name == model_table.name == "player_transfer_events"
    assert list(migration_table.c.keys()) == list(model_table.c.keys())
    for name in migration_table.c.keys():
        migration_column = migration_table.c[name]
        model_column = model_table.c[name]
        assert migration_column.type.compile(dialect=dialect) == model_column.type.compile(dialect=dialect)
        assert migration_column.nullable == model_column.nullable
        assert migration_column.primary_key == model_column.primary_key
        assert migration_column.autoincrement == model_column.autoincrement

    def unique_contract(table):
        return {
            (
                constraint.name,
                tuple(column.name for column in constraint.columns),
                constraint.dialect_options["postgresql"].get("nulls_not_distinct"),
            )
            for constraint in table.constraints
            if isinstance(constraint, sa.UniqueConstraint)
        }

    assert unique_contract(migration_table) == unique_contract(model_table)

    model_indexes = {(index.name, tuple(column.name for column in index.columns)) for index in model_table.indexes}
    index_name, table_name, columns, kwargs = captured["index"]
    assert (index_name, columns) in model_indexes
    assert table_name == model_table.name
    assert kwargs == {}
    assert captured["rls"] == "ALTER TABLE player_transfer_events ENABLE ROW LEVEL SECURITY"


def test_record_transfer_events_is_idempotent_and_advances_last_seen(app):
    first_observation = datetime(2026, 7, 16, 9, 0, tzinfo=UTC)
    second_observation = datetime(2026, 7, 16, 10, 0, tzinfo=UTC)

    assert record_transfer_events(PLAYER_ID, HALL_TRANSFERS, db.session, observed_at=first_observation) == 2
    db.session.commit()

    original = PlayerTransferEvent.query.order_by(PlayerTransferEvent.transfer_date).all()
    original_ids = [row.id for row in original]
    assert len(original) == 2
    assert all(_utc(row.first_seen_at) == first_observation for row in original)
    assert all(_utc(row.last_seen_at) == first_observation for row in original)
    assert [row.raw for row in original] == HALL_TRANSFERS

    assert record_transfer_events(PLAYER_ID, HALL_TRANSFERS, db.session, observed_at=second_observation) == 2
    db.session.commit()

    repeated = PlayerTransferEvent.query.order_by(PlayerTransferEvent.transfer_date).all()
    assert PlayerTransferEvent.query.count() == 2
    assert [row.id for row in repeated] == original_ids
    assert all(_utc(row.first_seen_at) == first_observation for row in repeated)
    assert all(_utc(row.last_seen_at) == second_observation for row in repeated)


def test_provider_revision_conflict_only_advances_last_seen(app):
    initial = datetime(2026, 7, 16, 9, 0, tzinfo=UTC)
    revised = datetime(2026, 7, 16, 11, 0, tzinfo=UTC)
    event = deepcopy(HALL_TRANSFERS[1])
    record_transfer_events(PLAYER_ID, [event], db.session, observed_at=initial)
    db.session.commit()

    event["teams"]["out"]["name"] = "Chelsea FC"
    event["teams"]["in"]["name"] = "Newcastle United"
    event["provider_revision"] = 2
    record_transfer_events(PLAYER_ID, [event], db.session, observed_at=revised)
    db.session.commit()

    row = PlayerTransferEvent.query.one()
    assert row.out_club_name == "Chelsea"
    assert row.in_club_name == "Newcastle"
    assert row.raw == HALL_TRANSFERS[1]
    assert _utc(row.first_seen_at) == initial
    assert _utc(row.last_seen_at) == revised


def test_older_observation_cannot_move_last_seen_backward(app):
    newer = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
    older = datetime(2026, 7, 16, 8, 0, tzinfo=UTC)

    record_transfer_events(PLAYER_ID, [HALL_TRANSFERS[1]], db.session, observed_at=newer)
    db.session.commit()
    record_transfer_events(PLAYER_ID, [HALL_TRANSFERS[1]], db.session, observed_at=older)
    db.session.commit()

    row = PlayerTransferEvent.query.one()
    assert _utc(row.last_seen_at) == newer


def test_nullable_natural_key_remains_idempotent(app):
    """Malformed evidence remains durable under SQLite's NULL-distinct UNIQUE."""

    first_observation = datetime(2026, 7, 16, 9, 0, tzinfo=UTC)
    second_observation = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)
    incomplete = {
        "date": "2025-07-01",
        "type": None,
        "teams": {"out": {"name": "Unknown"}, "in": {"id": 34, "name": "Newcastle"}},
    }

    record_transfer_events(PLAYER_ID, [incomplete], db.session, observed_at=first_observation)
    db.session.commit()
    record_transfer_events(PLAYER_ID, [incomplete], db.session, observed_at=second_observation)
    db.session.commit()
    record_transfer_events(PLAYER_ID, [incomplete], db.session, observed_at=first_observation)
    db.session.commit()

    row = PlayerTransferEvent.query.one()
    assert _utc(row.first_seen_at) == first_observation
    assert _utc(row.last_seen_at) == second_observation
