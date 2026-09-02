"""S2 fan grain, public-adult subject gate, ownership, and reach metrics."""

from __future__ import annotations

import importlib
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta, timezone
from itertools import count
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import op as alembic_op
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy.exc import IntegrityError
from src.auth import _ensure_user_account
from src.models.follow import PlayerShadow
from src.models.league import League, Team, UserAccount, db
from src.models.player_fan import PlayerFan
from src.models.player_suppression import PlayerSuppression
from src.models.product_event import ProductEvent
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.tracked_player import TrackedPlayer
from src.services.public_player_subject import (
    owned_public_adult_subjects,
    owner_account_ids_subquery,
    resolve_public_adult_subject,
    user_owns_subject,
)
from src.services.reach_metrics import (
    fan_counts,
    is_fan,
    profile_view_counts,
    profile_view_counts_since,
    watchlist_counts,
)

_SYNTHETIC_ID = object()


def _years_ago(years: int) -> date:
    today = datetime.now(UTC).date()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, month=2, day=28)


@pytest.fixture
def tracked_factory(app):
    league = League(league_id=9_200, name="Foundation League", country="England", season=2026)
    db.session.add(league)
    db.session.flush()
    team_ids = count(9_201)

    def make(player_api_id: int, *, birth_date=None, age=None, data_source="api-football") -> TrackedPlayer:
        team_api_id = next(team_ids)
        team = Team(
            team_id=team_api_id,
            name=f"Foundation Team {team_api_id}",
            country="England",
            season=2026,
            league_id=league.id,
        )
        db.session.add(team)
        db.session.flush()
        player = TrackedPlayer(
            player_api_id=player_api_id,
            player_name=f"Player {player_api_id}",
            team_id=team.id,
            birth_date=birth_date.isoformat() if isinstance(birth_date, date) else birth_date,
            age=age,
            status="academy",
            data_source=data_source,
            is_active=True,
        )
        db.session.add(player)
        db.session.flush()
        return player

    return make


def _user(email: str) -> UserAccount:
    return _ensure_user_account(email)


def _local(
    name: str,
    *,
    birth_date: date | None,
    status: str = "approved",
    api_player_id=_SYNTHETIC_ID,
    merged_into_local_player_id=None,
) -> LocalPlayer:
    player = LocalPlayer(
        display_name=name,
        normalized_name=LocalPlayer.normalize_name(name),
        birth_date=birth_date,
        birth_year=birth_date.year if birth_date else None,
        status=status,
        merged_into_local_player_id=merged_into_local_player_id,
    )
    db.session.add(player)
    db.session.flush()
    if api_player_id is _SYNTHETIC_ID:
        player.api_player_id = -player.id
    else:
        player.api_player_id = api_player_id
    db.session.flush()
    return player


def _shadow(player_api_id: int, *, birth_date: date | None) -> PlayerShadow:
    shadow = PlayerShadow(
        player_api_id=player_api_id,
        player_name=f"Shadow {player_api_id}",
        birth_date=birth_date,
        is_active=True,
    )
    db.session.add(shadow)
    db.session.flush()
    return shadow


def _claim(
    user: UserAccount,
    *,
    player_api_id=None,
    local_player_id=None,
    status="approved",
    relationship_type="player",
) -> PlayerProfileClaim:
    claim = PlayerProfileClaim(
        player_api_id=player_api_id,
        local_player_id=local_player_id,
        user_account_id=user.id,
        relationship_type=relationship_type,
        status=status,
    )
    db.session.add(claim)
    db.session.flush()
    return claim


def _suppress(*, player_api_id=None, local_player_id=None) -> PlayerSuppression:
    suffix = player_api_id if player_api_id is not None else f"local-{local_player_id}"
    suppression = PlayerSuppression(
        player_api_id=player_api_id,
        local_player_id=local_player_id,
        reason_code="player_request",
        requester_role="player",
        requester_contact=f"{suffix}@example.com",
        request_statement="Please remove this profile.",
        status="active",
    )
    db.session.add(suppression)
    db.session.flush()
    return suppression


def test_public_adult_gate_uses_birth_date_and_stored_age_evidence(app, tracked_factory):
    tracked_factory(10_001, birth_date=_years_ago(18))
    tracked_factory(10_002)
    tracked_factory(10_003, birth_date=_years_ago(16))
    tracked_factory(10_004, age=18)
    tracked_factory(10_005, age=16)
    db.session.commit()

    assert resolve_public_adult_subject(10_001).signed_id == 10_001
    assert resolve_public_adult_subject(10_002) is None
    assert resolve_public_adult_subject(10_003) is None
    assert resolve_public_adult_subject(10_004).signed_id == 10_004
    assert resolve_public_adult_subject(10_005) is None


def test_public_adult_gate_rejects_seventeen_year_old_at_eighteen_year_boundary(app, tracked_factory):
    """Mutation guard: changing the shared ``age < 18`` rule to ``age < 17`` fails."""

    tracked_factory(10_006, age=17)
    db.session.commit()

    assert resolve_public_adult_subject(10_006) is None


def test_public_adult_gate_handles_shadow_only_age_evidence(app):
    _shadow(10_101, birth_date=_years_ago(24))
    _shadow(10_102, birth_date=_years_ago(14))
    _shadow(10_103, birth_date=None)
    db.session.commit()

    assert resolve_public_adult_subject(10_101).source == "shadow"
    assert resolve_public_adult_subject(10_102) is None
    assert resolve_public_adult_subject(10_103) is None


def test_public_adult_gate_rejects_conflicting_rows_and_bridged_minor(app, tracked_factory):
    tracked_factory(10_201, birth_date=_years_ago(25))
    tracked_factory(10_201, birth_date=_years_ago(15))
    tracked_factory(10_202, birth_date=_years_ago(25))
    _local("Bridged Minor", birth_date=_years_ago(15), api_player_id=10_202)
    db.session.commit()

    assert resolve_public_adult_subject(10_201) is None
    assert resolve_public_adult_subject(10_202) is None


def test_public_adult_gate_rejects_suppression_in_either_namespace(app, tracked_factory):
    tracked_factory(10_301, birth_date=_years_ago(25))
    _suppress(player_api_id=10_301)

    tracked_factory(10_302, birth_date=_years_ago(25))
    bridged = _local("Suppressed Bridge", birth_date=_years_ago(25), api_player_id=10_302)
    _suppress(local_player_id=bridged.id)

    local = _local("Suppressed Local", birth_date=_years_ago(25))
    _suppress(local_player_id=local.id)
    db.session.commit()

    assert resolve_public_adult_subject(10_301) is None
    assert resolve_public_adult_subject(10_302) is None
    assert resolve_public_adult_subject(local.api_player_id) is None


def test_public_adult_gate_checks_every_bridged_local_for_suppression(app, tracked_factory):
    tracked_factory(10_401, birth_date=_years_ago(25))
    first = _local("First Bridge", birth_date=_years_ago(25), api_player_id=10_401)
    second = _local("Second Bridge", birth_date=_years_ago(25), api_player_id=10_401)
    assert first.id < second.id
    _suppress(local_player_id=second.id)
    db.session.commit()

    assert resolve_public_adult_subject(10_401) is None


def test_public_adult_gate_accepts_only_approved_unmerged_adult_locals(app):
    adult = _local("Adult Local", birth_date=_years_ago(23))
    minor = _local("Minor Local", birth_date=_years_ago(15))
    pending = _local("Pending Local", birth_date=_years_ago(23), status="pending")
    merge_target = _local("Merge Target", birth_date=_years_ago(23))
    merged = _local(
        "Merged Local",
        birth_date=_years_ago(23),
        status="merged",
        merged_into_local_player_id=merge_target.id,
    )
    db.session.commit()

    subject = resolve_public_adult_subject(adult.api_player_id)
    assert subject is not None and subject.local_player_id == adult.id
    assert resolve_public_adult_subject(minor.api_player_id) is None
    assert resolve_public_adult_subject(pending.api_player_id) is None
    assert resolve_public_adult_subject(merged.api_player_id) is None


@pytest.mark.parametrize("bad_id", [0, True, "5", None, 2**40, -(2**40)])
def test_public_adult_gate_rejects_bad_input_before_resolution(app, monkeypatch, bad_id):
    from src.services import public_player_subject as subject_service

    def explode(_signed_id):
        raise AssertionError("invalid input reached the subject resolver")

    monkeypatch.setattr(subject_service, "resolve_player_subject", explode)
    assert subject_service.resolve_public_adult_subject(bad_id) is None


def test_ownership_resolves_both_namespaces_and_gates_public_collection(app, tracked_factory):
    owner = _user("foundation-owner@example.com")
    tracked_factory(11_001, birth_date=_years_ago(25))
    _claim(owner, player_api_id=11_001)

    local = _local("Owned Local", birth_date=_years_ago(25))
    _claim(owner, local_player_id=local.id)

    tracked_factory(11_002, birth_date=_years_ago(25))
    graduated_local = _local("Graduated Local", birth_date=_years_ago(25), api_player_id=11_002)
    _claim(owner, local_player_id=graduated_local.id)

    tracked_factory(11_003, birth_date=_years_ago(15))
    _claim(owner, player_api_id=11_003)
    tracked_factory(11_004, birth_date=_years_ago(25))
    _claim(owner, player_api_id=11_004)
    _suppress(player_api_id=11_004)

    no_id_local = _local("No Signed Identity", birth_date=_years_ago(25), api_player_id=None)
    _claim(owner, local_player_id=no_id_local.id)
    tracked_factory(11_005, birth_date=_years_ago(25))
    _claim(owner, player_api_id=11_005, relationship_type="agent")
    tracked_factory(11_006, birth_date=_years_ago(25))
    _claim(owner, player_api_id=11_006, status="pending")
    db.session.commit()

    assert [subject.signed_id for subject in owned_public_adult_subjects(owner.id)] == [
        local.api_player_id,
        11_001,
        11_002,
    ]
    assert user_owns_subject(owner.id, 11_001) is True
    assert user_owns_subject(owner.id, local.api_player_id) is True
    assert user_owns_subject(owner.id, 11_002) is True
    assert user_owns_subject(owner.id, 11_003) is True  # Membership is deliberately ungated.
    assert user_owns_subject(owner.id, 11_005) is False
    assert user_owns_subject(owner.id, 999_999) is False
    assert db.session.execute(owner_account_ids_subquery(local.api_player_id)).scalars().all() == [owner.id]


def test_owner_subquery_excludes_local_owner_from_fans_and_is_fan(app):
    owner = _user("local-owner@example.com")
    outsider = _user("local-fan@example.com")
    local = _local("Fan-owned Local", birth_date=_years_ago(25))
    _claim(owner, local_player_id=local.id)
    db.session.add_all(
        [
            PlayerFan(user_account_id=owner.id, player_api_id=local.api_player_id),
            PlayerFan(user_account_id=outsider.id, player_api_id=local.api_player_id),
        ]
    )
    db.session.commit()

    assert fan_counts([local.api_player_id]) == {local.api_player_id: (1, 0)}
    assert is_fan(owner.id, local.api_player_id) is False
    assert is_fan(outsider.id, local.api_player_id) is True


def test_player_fan_and_user_preference_defaults_match_contract(app):
    user = _user("defaults@example.com")
    fan = PlayerFan(user_account_id=user.id, player_api_id=12_001)
    db.session.add(fan)
    db.session.commit()

    assert user.profile_activity_email_opt_in is False
    assert user.profile_activity_email_last_sent_at is None
    assert fan.created_at.tzinfo is None
    assert fan.to_dict() == {
        "player_api_id": 12_001,
        "created_at": fan.created_at.isoformat(),
    }


def test_fan_and_watchlist_counts_are_correlated_since_aware_and_excludable(app):
    owner_a = _user("owner-a@example.com")
    owner_b = _user("owner-b@example.com")
    neutral = _user("neutral@example.com")
    excluded = _user("excluded@example.com")
    player_a, player_b = 12_101, 12_102
    _claim(owner_a, player_api_id=player_a)
    _claim(owner_b, player_api_id=player_b)

    since_aware = datetime(2026, 9, 1, 12, tzinfo=timezone(timedelta(hours=9)))
    since = since_aware.astimezone(UTC).replace(tzinfo=None)
    recent = since + timedelta(hours=1)
    old = since - timedelta(hours=1)
    memberships = [
        (owner_a, player_a, recent),
        (owner_a, player_b, recent),
        (owner_b, player_a, old),
        (owner_b, player_b, recent),
        (neutral, player_a, recent),
        (neutral, player_b, old),
        (excluded, player_a, recent),
        (excluded, player_b, recent),
    ]
    db.session.add_all(
        [
            PlayerFan(user_account_id=user.id, player_api_id=player_id, created_at=created_at)
            for user, player_id, created_at in memberships
        ]
    )
    db.session.add_all(
        [
            ScoutWatchlistEntry(user_account_id=user.id, player_api_id=player_id, created_at=created_at)
            for user, player_id, created_at in memberships
        ]
    )
    db.session.commit()

    assert fan_counts([player_a, player_b, 999_999], since=since_aware) == {
        player_a: (3, 2),
        player_b: (3, 2),
        999_999: (0, 0),
    }
    assert watchlist_counts([player_a, player_b, 999_999], since=since_aware) == {
        player_a: (3, 2),
        player_b: (3, 2),
        999_999: (0, 0),
    }
    assert fan_counts([player_a, player_b], since=since_aware, exclude_user_ids=(excluded.id,)) == {
        player_a: (2, 1),
        player_b: (2, 1),
    }
    assert watchlist_counts([player_a, player_b], since=since_aware, exclude_user_ids=(excluded.id,)) == {
        player_a: (2, 1),
        player_b: (2, 1),
    }
    assert fan_counts([player_a, player_b]) == {player_a: (3, 0), player_b: (3, 0)}
    assert is_fan(owner_a.id, player_a) is False
    assert is_fan(owner_a.id, player_b) is True
    assert is_fan(neutral.id, player_a) is True


def test_profile_view_counts_observe_inclusive_boundaries_and_aware_now(app):
    player_id = 12_201
    aware_now = datetime(2026, 9, 2, 12, tzinfo=timezone(timedelta(hours=9)))
    now = aware_now.astimezone(UTC).replace(tzinfo=None)
    timestamps = [
        now - timedelta(days=7),
        now - timedelta(days=7, microseconds=1),
        now - timedelta(days=30),
        now - timedelta(days=30, microseconds=1),
        now,
        now + timedelta(microseconds=1),
    ]
    db.session.add_all(
        [
            ProductEvent(event_name="profile_view", props={"player_api_id": player_id}, created_at=created_at)
            for created_at in timestamps
        ]
    )
    db.session.add_all(
        [
            ProductEvent(event_name="pageview", props={"player_api_id": player_id}, created_at=now),
            ProductEvent(event_name="profile_view", props={"player_api_id": 12_202}, created_at=now),
        ]
    )
    db.session.commit()

    assert profile_view_counts([player_id, 12_202, 999_999], now=aware_now) == {
        player_id: {"last_7_days": 2, "last_30_days": 4},
        12_202: {"last_7_days": 1, "last_30_days": 1},
        999_999: {"last_7_days": 0, "last_30_days": 0},
    }
    assert profile_view_counts_since(
        [player_id, 12_202, 999_999],
        since=aware_now - timedelta(days=7),
        now=aware_now,
    ) == {player_id: 2, 12_202: 1, 999_999: 0}


def test_empty_metric_inputs_execute_no_queries(app):
    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    sa.event.listen(db.engine, "before_cursor_execute", capture)
    try:
        assert fan_counts([]) == {}
        assert watchlist_counts([], since=datetime.now(UTC)) == {}
        assert profile_view_counts([]) == {}
        assert profile_view_counts_since([], since=datetime.now(UTC)) == {}
    finally:
        sa.event.remove(db.engine, "before_cursor_execute", capture)

    assert statements == []


@contextmanager
def _alembic_ops(engine):
    connection = engine.connect()
    transaction = connection.begin()
    context = MigrationContext.configure(connection)
    operations = Operations(context)
    original = getattr(alembic_op, "_proxy", None)
    alembic_op._proxy = operations
    try:
        yield
        transaction.commit()
    finally:
        alembic_op._proxy = original
        connection.close()


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


def _sqlite_add_column_safe(table, column):
    if not _sqlite_column_exists(table, column.name):
        alembic_op.add_column(table, column)


def _sqlite_create_index_safe(name, table, columns, **kwargs):
    if not _sqlite_index_exists(name):
        alembic_op.create_index(name, table, columns, **kwargs)


@pytest.fixture
def migration_engine():
    engine = sa.create_engine("sqlite:///:memory:")

    @sa.event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    metadata = sa.MetaData()
    sa.Table("user_accounts", metadata, sa.Column("id", sa.Integer(), primary_key=True))
    metadata.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def s2f1(monkeypatch):
    module = importlib.import_module("migrations.versions.s2f1_fans_reach")
    monkeypatch.setattr(module, "table_exists", _sqlite_table_exists)
    monkeypatch.setattr(module, "column_exists", _sqlite_column_exists)
    monkeypatch.setattr(module, "index_exists", _sqlite_index_exists)
    monkeypatch.setattr(module, "add_column_safe", _sqlite_add_column_safe)
    monkeypatch.setattr(module, "create_index_safe", _sqlite_create_index_safe)
    return module


def test_s2f1_upgrade_twice_and_downgrade_twice_are_executable(migration_engine, s2f1):
    with _alembic_ops(migration_engine):
        s2f1.upgrade()
    with migration_engine.begin() as connection:
        connection.execute(sa.text("INSERT INTO user_accounts (id) VALUES (1)"))
        connection.execute(sa.text("INSERT INTO player_fans (user_account_id, player_api_id) VALUES (1, 123)"))
    with _alembic_ops(migration_engine):
        s2f1.upgrade()

    inspector = sa.inspect(migration_engine)
    assert set(inspector.get_table_names()) == {"user_accounts", "player_fans"}
    assert {column["name"] for column in inspector.get_columns("player_fans")} == {
        "id",
        "user_account_id",
        "player_api_id",
        "created_at",
    }
    user_columns = {column["name"]: column for column in inspector.get_columns("user_accounts")}
    assert set(user_columns) == {
        "id",
        "profile_activity_email_opt_in",
        "profile_activity_email_last_sent_at",
    }
    assert user_columns["profile_activity_email_opt_in"]["nullable"] is False
    assert user_columns["profile_activity_email_opt_in"]["default"] is not None
    assert user_columns["profile_activity_email_last_sent_at"]["nullable"] is True
    fan_columns = {column["name"]: column for column in inspector.get_columns("player_fans")}
    assert fan_columns["created_at"]["nullable"] is False
    assert fan_columns["created_at"]["default"] is not None

    assert {index["name"] for index in inspector.get_indexes("player_fans")} == {"ix_player_fans_player_created"}
    assert {constraint["name"] for constraint in inspector.get_unique_constraints("player_fans")} == {
        "uq_player_fans_user_player"
    }
    assert {constraint["name"] for constraint in inspector.get_check_constraints("player_fans")} == {
        "ck_player_fans_nonzero"
    }
    foreign_keys = inspector.get_foreign_keys("player_fans")
    assert len(foreign_keys) == 1
    assert foreign_keys[0]["constrained_columns"] == ["user_account_id"]
    assert foreign_keys[0]["referred_table"] == "user_accounts"
    assert foreign_keys[0]["options"]["ondelete"] == "CASCADE"

    with migration_engine.connect() as connection:
        opt_in, created_at = connection.execute(
            sa.text(
                "SELECT u.profile_activity_email_opt_in, f.created_at "
                "FROM user_accounts u JOIN player_fans f ON f.user_account_id=u.id WHERE u.id=1"
            )
        ).one()
        assert opt_in in (0, False)
        assert created_at is not None

    with pytest.raises(IntegrityError):
        with migration_engine.begin() as connection:
            connection.execute(sa.text("INSERT INTO player_fans (user_account_id, player_api_id) VALUES (1, 0)"))
    with pytest.raises(IntegrityError):
        with migration_engine.begin() as connection:
            connection.execute(sa.text("INSERT INTO player_fans (user_account_id, player_api_id) VALUES (1, 123)"))

    with migration_engine.begin() as connection:
        connection.execute(sa.text("DELETE FROM user_accounts WHERE id=1"))
        assert connection.execute(sa.text("SELECT COUNT(*) FROM player_fans")).scalar_one() == 0

    with _alembic_ops(migration_engine):
        s2f1.downgrade()
    with _alembic_ops(migration_engine):
        s2f1.downgrade()
    inspector = sa.inspect(migration_engine)
    assert inspector.get_table_names() == ["user_accounts"]
    assert [column["name"] for column in inspector.get_columns("user_accounts")] == ["id"]


def test_s2f1_is_the_single_head_and_chains_through_pm01_to_lp01():
    repo_root = Path(__file__).resolve().parent.parent
    config = Config(str(repo_root / "alembic.ini"))
    config.set_main_option("script_location", str(repo_root / "migrations"))
    script = ScriptDirectory.from_config(config)

    assert script.get_heads() == ["s2f1"]
    assert script.get_revision("s2f1").down_revision == "pm01"
    assert script.get_revision("pm01").down_revision == "lp01"
