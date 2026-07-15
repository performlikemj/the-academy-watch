"""D2 season-data (sea01) pinning tests — proposal §2 / §3 / §7 D2.

Locks the four load-bearing guarantees of the PR2 (`sea01`) work:

1. **Migration head stays single** — `sea01` chains off `aw23`, and D3's `sea02`
   now chains off `sea01`, so the single tip has advanced to `sea02`; a second head
   would make `flask db upgrade` ambiguous on deploy.
2. **`sea01` is idempotent** — every DDL is guarded, so a re-applied or
   partially-applied upgrade is a pure no-op (migrations do NOT auto-run on
   deploy; prod schema has drifted out-of-band, invariants §8).
3. **Rich extraction** — `_create_entry_from_stat` banks the full API-Football
   per-season statistics block into the sea01 columns with
   ``stats_source='journey-api'`` while the basic 4 fields stay byte-identical to
   the pre-sea01 behavior; a sparse/null payload yields NULL rich columns and
   never crashes (missing ≠ observed-zero).
4. **Duplicate-merge survival** — after a club-ID correction produces a duplicate,
   the merged survivor keeps its rich fields (journey-api / newer-synced wins the
   tie), and the primary "more appearances" rule is untouched.
5. **Backfill endpoint** — `POST /api/admin/journeys/backfill-entry-player-ids`
   fills only NULL `player_api_id` rows, converges to zero in bounded batches,
   is idempotent on re-run, never clobbers a set value, clamps its batch bound,
   and 401s without admin auth.
"""

import importlib
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import op as alembic_op
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from flask import Flask
from src.services.journey_sync import JourneySyncService, _stat_float, _stat_int

# ---------------------------------------------------------------------------
# (1) Migration head
# ---------------------------------------------------------------------------


def _script_directory():
    repo_root = Path(__file__).resolve().parent.parent
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "migrations"))
    return ScriptDirectory.from_config(cfg)


class TestMigrationHead:
    def test_single_head_is_sea03(self):
        """The whole chain resolves to exactly one head. D3's sea03 (the /status
        gauge clock indexes) now sits on top of sea02, so the tip has advanced from
        sea02 to sea03 — a second head would make `flask db upgrade` ambiguous on
        deploy."""
        heads = _script_directory().get_heads()
        assert heads == ["sea03"], f"expected the single head to be sea03, got {heads}"

    def test_sea01_chains_off_aw23(self):
        """sea01 branches from the real prod tip (aw23), keeping the line linear."""
        script = _script_directory()
        sea01 = script.get_revision("sea01")
        assert sea01.down_revision == "aw23"
        assert script.get_revision("aw23") is not None

    def test_sea02_chains_off_sea01(self):
        """sea02 (D3 rollup tables) branches from sea01 (D2), keeping the line linear."""
        script = _script_directory()
        sea02 = script.get_revision("sea02")
        assert sea02.down_revision == "sea01"
        assert script.get_revision("sea01") is not None

    def test_sea03_chains_off_sea02(self):
        """sea03 (/status gauge clock indexes) branches from sea02, keeping the line linear."""
        script = _script_directory()
        sea03 = script.get_revision("sea03")
        assert sea03.down_revision == "sea02"
        assert script.get_revision("sea02") is not None


# ---------------------------------------------------------------------------
# (2) sea01 idempotency (guarded DDL runs twice cleanly under SQLite)
# ---------------------------------------------------------------------------


@contextmanager
def _alembic_ops(engine):
    """Bind an Alembic Operations proxy to `engine` (matches the sibling
    migration tests)."""
    conn = engine.connect()
    trans = conn.begin()
    ctx = MigrationContext.configure(conn)
    operations = Operations(ctx)
    original = getattr(alembic_op, "_proxy", None)
    alembic_op._proxy = operations
    try:
        yield operations
        trans.commit()
    finally:
        alembic_op._proxy = original
        conn.close()


def _sqlite_column_exists(table, column):
    return column in {c["name"] for c in sa.inspect(alembic_op.get_bind()).get_columns(table)}


def _sqlite_index_exists(name):
    inspector = sa.inspect(alembic_op.get_bind())
    return any(name in {ix["name"] for ix in inspector.get_indexes(t)} for t in inspector.get_table_names())


# The FULL 28-column contract sea01 adds to player_journey_entries (27 rich
# columns + the server-defaulted stats_source). Pinned here as an explicit
# literal, INDEPENDENTLY of both the migration's own _COLUMNS list and the ORM
# model — so a column silently dropped or renamed on either side fails a test.
# That drift (migration omits a column the shipped model still SELECTs) is the
# exact failure mode that 500s every journey / D1-provenance read with psycopg
# UndefinedColumn; a hand-picked subset let 8 of these slip through unpinned.
_SEA01_COLUMNS = frozenset(
    {
        "player_api_id",
        "rating",
        "position",
        "lineups",
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
        "fouls_drawn",
        "fouls_committed",
        "cards_yellow",
        "cards_red",
        "penalty_scored",
        "penalty_missed",
        "penalty_saved",
        "goals_conceded",
        "saves",
        "season_phase",
        "stats_synced_at",
        "stats_source",
    }
)


@pytest.fixture
def _pje_base_engine():
    """A bare `player_journey_entries` (id/journey_id/season only) with one legacy
    row — the pre-sea01 shape the guarded migration must widen."""
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            sa.text("CREATE TABLE player_journey_entries (id INTEGER PRIMARY KEY, journey_id INTEGER, season INTEGER)")
        )
        conn.execute(sa.text("INSERT INTO player_journey_entries (id, journey_id, season) VALUES (1, 7, 2024)"))
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def _pje_partial_engine():
    """A `player_journey_entries` where a SUBSET of sea01's artifacts already
    exists out-of-band: the `player_api_id` + `rating` columns and the
    `ix_pje_player_season` index, plus a legacy row carrying a real rating.

    This is the documented drift mode (invariants §8): prod schema has had
    columns/indexes hand-added, so `flask db upgrade` runs against a schema where
    part of the migration's target already exists. upgrade() must ADD only the
    26 missing columns, SKIP the 2 pre-existing ones and the pre-existing index,
    and leave the seeded data untouched — never crash with DuplicateColumn."""
    engine = sa.create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "CREATE TABLE player_journey_entries ("
                "id INTEGER PRIMARY KEY, journey_id INTEGER, season INTEGER, "
                "player_api_id INTEGER, rating REAL)"
            )
        )
        # The read-path index sea01 also creates — already present out-of-band.
        conn.execute(sa.text("CREATE INDEX ix_pje_player_season ON player_journey_entries (player_api_id, season)"))
        conn.execute(
            sa.text(
                "INSERT INTO player_journey_entries (id, journey_id, season, player_api_id, rating) "
                "VALUES (1, 7, 2024, 303010, 6.5)"
            )
        )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def _sea01_module(monkeypatch):
    """Import the sea01 migration with its Postgres-only guards (information_schema
    / pg_indexes) swapped for SQLite-aware inspection, so upgrade() runs offline."""
    import migrations._migration_helpers as mh

    monkeypatch.setattr(mh, "column_exists", _sqlite_column_exists)
    monkeypatch.setattr(mh, "index_exists", _sqlite_index_exists)
    return importlib.import_module("migrations.versions.sea01_widen_journey_entries")


class TestSea01Idempotency:
    def test_upgrade_twice_is_a_no_op(self, _pje_base_engine, _sea01_module):
        engine = _pje_base_engine
        with _alembic_ops(engine):
            _sea01_module.upgrade()
        # Re-apply: guarded helpers must make this a clean no-op, never a crash.
        with _alembic_ops(engine):
            _sea01_module.upgrade()

        inspector = sa.inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("player_journey_entries")}
        # All 28 contract columns land (not just a hand-picked subset).
        assert columns >= _SEA01_COLUMNS
        index_names = [ix["name"] for ix in inspector.get_indexes("player_journey_entries")]
        # Created exactly once despite two upgrade passes.
        assert index_names.count("ix_pje_player_season") == 1

    def test_upgrade_over_partial_out_of_band_schema(self, _pje_partial_engine, _sea01_module):
        """Partial-application replay — the drift mode the file docstring claims
        but the double-upgrade test never exercised (that starts from a bare
        table where the first pass adds everything and the second full-skips).

        Here 2 of the 28 columns and the read-path index already exist
        out-of-band. A SINGLE upgrade() must: complete without a mid-DDL
        DuplicateColumn crash, add the other 26 columns, and leave the
        pre-existing column data and index untouched. This is what catches a
        future 'consolidate the 28 guards into one sentinel probe' refactor:
        the sentinel would be absent here, the batch would re-add `rating`, and
        upgrade() would raise instead of no-op'ing."""
        engine = _pje_partial_engine
        # A single pass (not a double-upgrade) — the crash, if any, is here.
        with _alembic_ops(engine):
            _sea01_module.upgrade()

        inspector = sa.inspect(engine)
        columns = {c["name"] for c in inspector.get_columns("player_journey_entries")}
        # Every contract column present: the 26 missing were added, the 2
        # pre-existing were skipped (no duplicate, no crash).
        assert columns >= _SEA01_COLUMNS
        # The pre-existing index survived exactly once (create_index_safe skipped it).
        index_names = [ix["name"] for ix in inspector.get_indexes("player_journey_entries")]
        assert index_names.count("ix_pje_player_season") == 1
        # The pre-existing columns' data is untouched (columns were not dropped/re-added),
        # while a freshly-added rich column defaults NULL and stats_source takes its
        # server default.
        with engine.connect() as conn:
            row = conn.execute(
                sa.text("SELECT rating, player_api_id, stats_source, saves FROM player_journey_entries WHERE id=1")
            ).one()
        assert row.rating == 6.5  # pre-existing value preserved
        assert row.player_api_id == 303010  # pre-existing value preserved
        assert row.stats_source == "legacy-basic"  # newly-added column's server default
        assert row.saves is None  # newly-added rich column defaults NULL

    def test_migration_ddl_matches_model_contract(self, _sea01_module):
        """DDL ↔ ORM-model parity. The migration's own _COLUMNS list AND the
        shipped model must both agree with the 28-column sea01 contract. Drop or
        rename a column on either side and this fails — instead of shipping a
        migration that omits a column the model still SELECTs, which 500s every
        journey / D1-provenance read with psycopg UndefinedColumn (the drift a
        prior fix on this branch already had to undo once)."""
        from src.models.journey import PlayerJourneyEntry

        migration_cols = {name for name, _ in _sea01_module._COLUMNS} | {"stats_source"}
        assert migration_cols == _SEA01_COLUMNS, (
            "sea01 _COLUMNS drifted from the 28-column contract — "
            f"missing={sorted(_SEA01_COLUMNS - migration_cols)}, "
            f"extra={sorted(migration_cols - _SEA01_COLUMNS)}"
        )

        model_cols = {c.name for c in PlayerJourneyEntry.__table__.columns}
        assert model_cols >= _SEA01_COLUMNS, (
            f"the ORM model is missing sea01 columns it will SELECT at runtime: {sorted(_SEA01_COLUMNS - model_cols)}"
        )

    def test_legacy_row_backfills_source_default(self, _pje_base_engine, _sea01_module):
        """The pre-existing row reads as 'legacy-basic' (server_default) with NULL
        rich fields — it predates the wider extraction."""
        engine = _pje_base_engine
        with _alembic_ops(engine):
            _sea01_module.upgrade()
        with engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT stats_source, rating, player_api_id, shots_total FROM player_journey_entries WHERE id=1"
                )
            ).one()
        assert row.stats_source == "legacy-basic"
        assert row.rating is None
        assert row.player_api_id is None
        assert row.shots_total is None


# ---------------------------------------------------------------------------
# (3) Rich extraction from the API-Football statistics block
# ---------------------------------------------------------------------------


def _service():
    # `object()` stands in for the API client — extraction never touches self.api,
    # and this avoids constructing a real (networked) APIFootballClient.
    return JourneySyncService(api_client=object())


def _legacy_basic_four(stat):
    """Reproduce the exact pre-sea01 4-field computation, to prove the new
    extraction leaves the basic fields byte-identical."""
    games = stat.get("games", {})
    goals = stat.get("goals", {})
    return {
        "appearances": games.get("appearences") or games.get("appearances") or 0,
        "goals": goals.get("total") or 0,
        "assists": goals.get("assists") or 0,
        "minutes": games.get("minutes") or 0,
    }


def _full_payload():
    """A faithful /players?id&season statistics[] block (British 'appearences'
    spelling, a '82%' accuracy string, an explicit-null penalty.saved, and a real
    observed goals.conceded=0)."""
    return {
        "team": {"id": 33, "name": "Manchester United", "logo": "mu.png"},
        "league": {"id": 39, "name": "Premier League", "country": "England", "logo": "pl.png"},
        "games": {"appearences": 25, "lineups": 22, "minutes": 1980, "position": "Midfielder", "rating": "7.42"},
        "shots": {"total": 30, "on": 12},
        "goals": {"total": 5, "conceded": 0, "assists": 7, "saves": 3},
        "passes": {"total": 1200, "key": 40, "accuracy": "82%"},
        "tackles": {"total": 45, "blocks": 3, "interceptions": 20},
        "duels": {"total": 200, "won": 110},
        "dribbles": {"attempts": 60, "success": 40},
        "fouls": {"drawn": 25, "committed": 18},
        "cards": {"yellow": 4, "red": 0},
        "penalty": {"scored": 1, "missed": 0, "saved": None},
    }


class TestRichExtraction:
    def test_full_payload_lands_every_rich_column(self):
        entry = _service()._create_entry_from_stat(1, 2025, _full_payload(), player_api_id=303010)

        # Provenance + denormalized id.
        assert entry.stats_source == "journey-api"
        assert entry.player_api_id == 303010
        assert isinstance(entry.stats_synced_at, datetime)

        # Every rich column landed with the coerced value.
        assert entry.rating == pytest.approx(7.42)
        assert entry.position == "Midfielder"
        assert entry.lineups == 22
        assert entry.shots_total == 30
        assert entry.shots_on == 12
        assert entry.passes_total == 1200
        assert entry.passes_key == 40
        assert entry.passes_accuracy == 82  # "82%" -> 82
        assert entry.tackles_total == 45
        assert entry.tackles_blocks == 3
        assert entry.tackles_interceptions == 20
        assert entry.duels_total == 200
        assert entry.duels_won == 110
        assert entry.dribbles_attempts == 60
        assert entry.dribbles_success == 40
        assert entry.fouls_drawn == 25
        assert entry.fouls_committed == 18
        assert entry.cards_yellow == 4
        assert entry.cards_red == 0
        assert entry.penalty_scored == 1
        assert entry.penalty_missed == 0
        assert entry.penalty_saved is None  # explicit null preserved
        assert entry.saves == 3

    def test_observed_zero_is_kept_not_nulled(self):
        """A real observed zero (goals.conceded == 0) stays 0 — only a
        missing/None field becomes NULL. Missing ≠ zero."""
        entry = _service()._create_entry_from_stat(1, 2025, _full_payload(), player_api_id=1)
        assert entry.goals_conceded == 0
        assert entry.goals_conceded is not None

    @pytest.mark.parametrize(
        "stat",
        [
            _full_payload(),
            # British spelling absent -> American 'appearances' fallback.
            {"team": {"id": 1}, "games": {"appearances": 9, "minutes": 700}, "goals": {"total": 2, "assists": 1}},
            # Everything absent -> all four default to 0.
            {"team": {"id": 1}},
            # Zeroes must survive the `or 0` guard as 0 (they already are 0).
            {"team": {"id": 1}, "games": {"appearences": 0, "minutes": 0}, "goals": {"total": 0, "assists": 0}},
        ],
    )
    def test_basic_four_unchanged_vs_legacy(self, stat):
        entry = _service()._create_entry_from_stat(1, 2025, stat, player_api_id=1)
        expected = _legacy_basic_four(stat)
        assert entry.appearances == expected["appearances"]
        assert entry.goals == expected["goals"]
        assert entry.assists == expected["assists"]
        assert entry.minutes == expected["minutes"]

    def test_sparse_payload_yields_null_rich_columns(self):
        """Blocks absent OR present-but-null both coerce to NULL rich columns
        with no crash; basic fields default to 0."""
        sparse = {
            "team": {"id": 50, "name": "Sparse FC"},
            "league": {"id": 1, "name": "Some League"},
            "games": {"minutes": None},
            "goals": {},
            "shots": None,  # present but null
            "passes": None,
        }
        entry = _service()._create_entry_from_stat(1, 2025, sparse, player_api_id=None)
        assert entry.appearances == 0
        assert entry.goals == 0
        assert entry.minutes == 0
        for field in (
            "rating",
            "position",
            "lineups",
            "shots_total",
            "shots_on",
            "passes_total",
            "tackles_total",
            "duels_won",
            "dribbles_success",
            "penalty_scored",
            "saves",
            "goals_conceded",
        ):
            assert getattr(entry, field) is None, f"{field} should be NULL for a sparse payload"

    def test_missing_team_returns_none(self):
        assert _service()._create_entry_from_stat(1, 2025, {"team": {}}) is None
        assert _service()._create_entry_from_stat(1, 2025, {}) is None


class TestStatCoercionHelpers:
    """The NULL-preserving coercion contract (missing ≠ 0)."""

    def test_stat_int(self):
        assert _stat_int("82%") == 82  # percentage string
        assert _stat_int("12.9") == 12  # numeric string, truncated
        assert _stat_int(7) == 7
        assert _stat_int(True) == 1  # bool coerces
        assert _stat_int(None) is None  # missing stays NULL
        assert _stat_int("") is None  # empty stays NULL
        assert _stat_int("  ") is None
        assert _stat_int("n/a") is None  # non-numeric -> NULL, no crash

    def test_stat_float(self):
        assert _stat_float("7.5") == pytest.approx(7.5)
        assert _stat_float(6) == pytest.approx(6.0)
        assert _stat_float(None) is None
        assert _stat_float("") is None
        assert _stat_float("x") is None


# ---------------------------------------------------------------------------
# (4) Duplicate-merge keeps rich fields
# ---------------------------------------------------------------------------


def _entry(appearances, source, synced_at, season=2025, rating=None, shots_total=None):
    """A journey entry sharing the (club, league, season) key so the merge groups
    it — simulates a club-ID correction colliding two rows."""
    from src.models.journey import PlayerJourneyEntry

    return PlayerJourneyEntry(
        journey_id=1,
        season=season,
        club_api_id=99,
        league_api_id=39,
        appearances=appearances,
        stats_source=source,
        stats_synced_at=synced_at,
        rating=rating,
        shots_total=shots_total,
    )


_NOW = datetime.now(UTC)
_OLDER = datetime(2020, 1, 1, tzinfo=UTC)


class TestMergeSurvivorKeepsRichData:
    def test_tie_appearances_prefers_journey_api_and_rich_fields_ride_along(self):
        legacy = _entry(10, "legacy-basic", _OLDER)
        rich = _entry(10, "journey-api", _NOW, rating=7.1, shots_total=30)
        survivors = _service()._merge_corrected_duplicates([legacy, rich])
        assert len(survivors) == 1
        winner = survivors[0]
        assert winner.stats_source == "journey-api"
        assert winner.rating == pytest.approx(7.1)
        assert winner.shots_total == 30  # rich data survives the merge

    def test_more_appearances_wins_even_if_legacy(self):
        """The primary 'more complete data' rule is untouched — appearances still
        beats source rank."""
        more = _entry(20, "legacy-basic", _OLDER)
        fewer = _entry(10, "journey-api", _NOW)
        survivors = _service()._merge_corrected_duplicates([more, fewer])
        assert len(survivors) == 1
        assert survivors[0].appearances == 20
        assert survivors[0].stats_source == "legacy-basic"

    def test_tie_prefers_newer_synced_at(self):
        older = _entry(10, "journey-api", _OLDER, shots_total=1)
        newer = _entry(10, "journey-api", _NOW, shots_total=99)
        survivors = _service()._merge_corrected_duplicates([older, newer])
        assert len(survivors) == 1
        assert survivors[0].shots_total == 99  # newer stats_synced_at wins

    def test_non_duplicate_entries_pass_through(self):
        a = _entry(10, "journey-api", _NOW, season=2025)
        b = _entry(5, "journey-api", _NOW, season=2024)  # different season -> not a dup
        survivors = _service()._merge_corrected_duplicates([a, b])
        assert len(survivors) == 2


# ---------------------------------------------------------------------------
# (5) Backfill endpoint
# ---------------------------------------------------------------------------

ADMIN_KEY = "test-admin-key"
_BACKFILL_URL = "/api/admin/journeys/backfill-entry-player-ids"


@pytest.fixture
def backfill_app(monkeypatch):
    monkeypatch.setenv("SKIP_API_HANDSHAKE", "1")
    monkeypatch.setenv("API_USE_STUB_DATA", "true")
    monkeypatch.setenv("ADMIN_API_KEY", ADMIN_KEY)
    monkeypatch.setenv("ADMIN_IP_WHITELIST", "")

    from src.models.league import db
    from src.routes.journey import journey_bp

    application = Flask(__name__)
    application.config.update(
        TESTING=True,
        SECRET_KEY="test-secret-key",
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
    )
    db.init_app(application)
    application.register_blueprint(journey_bp, url_prefix="/api")

    ctx = application.app_context()
    ctx.push()
    db.create_all()
    yield application
    db.session.remove()
    db.drop_all()
    ctx.pop()


@pytest.fixture
def backfill_client(backfill_app):
    return backfill_app.test_client()


@pytest.fixture
def admin_headers(backfill_app):
    from src.auth import issue_user_token

    token = issue_user_token("admin@test.com", role="admin")["token"]
    return {"Authorization": f"Bearer {token}", "X-API-Key": ADMIN_KEY}


def _seed_null_entries(count, entries_per_journey=2):
    """Create `count` PlayerJourneyEntry rows with NULL player_api_id, spread
    across journeys. Returns {entry_id: expected_player_api_id}."""
    from src.models.journey import PlayerJourney, PlayerJourneyEntry
    from src.models.league import db

    expected = {}
    made = 0
    journey_seq = 0
    while made < count:
        journey_seq += 1
        player_api_id = 5000 + journey_seq
        journey = PlayerJourney(player_api_id=player_api_id, player_name=f"P{player_api_id}")
        db.session.add(journey)
        db.session.flush()
        for _ in range(entries_per_journey):
            if made >= count:
                break
            entry = PlayerJourneyEntry(journey_id=journey.id, season=2025, club_api_id=player_api_id * 10)
            db.session.add(entry)
            db.session.flush()
            expected[entry.id] = player_api_id
            made += 1
    db.session.commit()
    return expected


def _null_count():
    from src.models.journey import PlayerJourneyEntry

    return PlayerJourneyEntry.query.filter(PlayerJourneyEntry.player_api_id.is_(None)).count()


class TestBackfillEntryPlayerIds:
    def test_batches_converge_to_zero_and_data_is_correct(self, backfill_app, backfill_client, admin_headers):
        expected = _seed_null_entries(7, entries_per_journey=2)
        assert _null_count() == 7

        remaining = None
        guard = 0
        while remaining != 0:
            guard += 1
            assert guard < 20, "backfill did not converge"
            before = _null_count()
            resp = backfill_client.post(f"{_BACKFILL_URL}?batch_size=3", headers=admin_headers)
            assert resp.status_code == 200
            body = resp.get_json()
            remaining = body["remaining"]
            # Endpoint's own count agrees with the DB, and each call fills at most
            # the batch bound (3), monotonically shrinking the NULL set.
            assert remaining == _null_count()
            assert before - remaining <= 3
            assert remaining < before or before == 0

        # Every entry now carries its parent journey's player id.
        from src.models.journey import PlayerJourneyEntry
        from src.models.league import db

        db.session.expire_all()
        for entry_id, player_api_id in expected.items():
            assert db.session.get(PlayerJourneyEntry, entry_id).player_api_id == player_api_id

    def test_respects_batch_bound(self, backfill_app, backfill_client, admin_headers):
        _seed_null_entries(5, entries_per_journey=5)
        assert _null_count() == 5
        resp = backfill_client.post(f"{_BACKFILL_URL}?batch_size=2", headers=admin_headers)
        assert resp.status_code == 200
        # Exactly 2 of 5 filled -> 3 remain.
        assert resp.get_json()["remaining"] == 3
        assert _null_count() == 3

    def test_idempotent_on_rerun(self, backfill_app, backfill_client, admin_headers):
        _seed_null_entries(4, entries_per_journey=1)
        # Drain to zero.
        for _ in range(4):
            backfill_client.post(f"{_BACKFILL_URL}?batch_size=10", headers=admin_headers)
        assert _null_count() == 0
        # Re-running after completion is a clean no-op.
        resp = backfill_client.post(f"{_BACKFILL_URL}?batch_size=10", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.get_json()["remaining"] == 0
        assert _null_count() == 0

    def test_never_overwrites_an_already_set_id(self, backfill_app, backfill_client, admin_headers):
        """The batch targets NULL rows only — a row with a value set (even a
        deliberately 'wrong' one) is never clobbered."""
        from src.models.journey import PlayerJourney, PlayerJourneyEntry
        from src.models.league import db

        journey = PlayerJourney(player_api_id=9000, player_name="P9000")
        db.session.add(journey)
        db.session.flush()
        # Pre-set to a sentinel that does NOT match the parent (9000).
        pinned = PlayerJourneyEntry(journey_id=journey.id, season=2025, club_api_id=1, player_api_id=123456)
        null_row = PlayerJourneyEntry(journey_id=journey.id, season=2024, club_api_id=2)
        db.session.add_all([pinned, null_row])
        db.session.flush()
        pinned_id, null_id = pinned.id, null_row.id
        db.session.commit()

        resp = backfill_client.post(f"{_BACKFILL_URL}?batch_size=100", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.get_json()["remaining"] == 0

        db.session.expire_all()
        assert db.session.get(PlayerJourneyEntry, pinned_id).player_api_id == 123456  # untouched
        assert db.session.get(PlayerJourneyEntry, null_id).player_api_id == 9000  # filled from parent

    @pytest.mark.parametrize(
        "requested,expected",
        [
            ("999999", 50000),  # clamped down to the 50k ceiling
            ("0", 5000),  # < 1 -> default
            ("-5", 5000),  # negative -> default
            ("abc", 5000),  # non-integer -> default
        ],
    )
    def test_clamps_batch_size(self, backfill_app, backfill_client, admin_headers, requested, expected):
        resp = backfill_client.post(f"{_BACKFILL_URL}?batch_size={requested}", headers=admin_headers)
        assert resp.status_code == 200
        assert resp.get_json()["batch_size"] == expected

    def test_requires_admin_auth(self, backfill_app, backfill_client):
        resp = backfill_client.post(_BACKFILL_URL)
        assert resp.status_code == 401
