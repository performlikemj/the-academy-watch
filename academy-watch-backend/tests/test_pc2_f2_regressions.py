"""Review-duel probes: stale cells, policy memo, pooler and safe partial undo."""

import ast
from pathlib import Path

import pytest
from src.models.league import db
from src.models.season_rollup import PlayerSeasonTotal
from src.services import public_adult
from test_pc2_review_regressions import headers
from test_pc2_surface_equality import SEASON, seed_personas
from test_pc2_surface_equality import app as pc2_app


@pytest.fixture
def app(monkeypatch):
    yield from pc2_app.__wrapped__(monkeypatch)


# Definitions are not readers. All storage access lives in the single projection
# module, including narrow metadata and writer/merge I/O. No caller exemptions.
PROJECTION_MODULE = "services/reported_match_totals.py"
MODEL_NAMES = {"PlayerSeasonTotal", "PlayerSeasonCell"}
TABLE_NAMES = {"player_season_totals", "player_season_cells"}


def rollup_boundary_violations(root):
    violations = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root).as_posix()
        if relative in {"models/season_rollup.py", PROJECTION_MODULE}:
            continue
        tree = ast.parse(path.read_text())
        # Catch imported model names regardless of absolute/relative/re-export
        # module spelling. Qualified access and table literals are also banned.
        model_access = any(
            (isinstance(n, ast.Name) and n.id in MODEL_NAMES)
            or (isinstance(n, ast.Constant) and isinstance(n.value, str) and n.value in MODEL_NAMES)
            or (isinstance(n, ast.Attribute) and n.attr in MODEL_NAMES)
            or (
                isinstance(n, ast.ImportFrom)
                and any(
                    a.name in MODEL_NAMES or (a.name == "*" and "season_rollup" in (n.module or "")) for a in n.names
                )
            )
            for n in ast.walk(tree)
        )
        documentation = {
            id(n.value)
            for n in ast.walk(tree)
            if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant) and isinstance(n.value.value, str)
        }
        raw_sql = any(
            isinstance(n, ast.Constant)
            and id(n) not in documentation
            and isinstance(n.value, str)
            and any(t in n.value for t in TABLE_NAMES)
            for n in ast.walk(tree)
        )
        if model_access:
            violations.append((relative, "stored model access outside projection"))
        if raw_sql:
            violations.append((relative, "stored table access outside projection"))
    return violations


def test_public_readers_cannot_query_raw_stored_report_figures():
    root = Path(__file__).resolve().parents[1] / "src"
    assert not rollup_boundary_violations(root)


@pytest.mark.parametrize(
    "directory", ["routes", "services", "utils", "jobs", "agents", "mcp", "workers", "admin", "routes/players.py"]
)
@pytest.mark.parametrize(
    "source",
    [
        "from src.services.reported_match_totals import PlayerSeasonTotal as T\ndef read():\n return T.query.first().minutes",
        "from .season_rollup import PlayerSeasonCell as T\ndef read():\n return T.query.first().detail",
        "def read():\n return getattr(module, 'PlayerSeasonCell').query.first().detail",
        "def read():\n return db.Model.registry._class_registry['PlayerSeasonTotal'].query.first().minutes",
        "from src.models.season_rollup import PlayerSeasonTotal as PST\ndef read():\n return db.session.get(PST, 123).minutes",
        "from src.models import season_rollup\ndef read():\n return season_rollup.PlayerSeasonTotal.query.first().source_breakdown",
        "import src.models.season_rollup as sr\ndef read():\n M = sr.PlayerSeasonTotal\n return M.query.all()",
        "from src.models.season_rollup import PlayerSeasonTotal\ndef read():\n M = aliased(PlayerSeasonTotal)\n return select(M)",
        "from src.models.season_rollup import PlayerSeasonTotal\ndef read():\n return query.outerjoin(PlayerSeasonTotal).add_entity(PlayerSeasonTotal)",
        "from src.models.season_rollup import PlayerSeasonCell as Cell\ndef read():\n return Cell.query.first().minutes",
        "def read():\n return session.execute(text('SELECT source_breakdown FROM player_season_totals'))",
    ],
)
def test_planted_review_bypasses_fail_actual_reader_boundary(tmp_path, directory, source):
    path = tmp_path / directory if directory.endswith(".py") else tmp_path / directory / "planted.py"
    path.parent.mkdir(parents=True)
    path.write_text(source)
    assert rollup_boundary_violations(tmp_path)


def test_desk_reuses_policy_evidence_within_request_but_not_between_requests(app, monkeypatch):
    ids, _user, _list = seed_personas()
    calls = []
    original = public_adult.public_adult_ids

    def counted(ids, **kw):
        ids = set(ids)
        calls.append(ids)
        return original(ids, **kw)

    monkeypatch.setattr(public_adult, "public_adult_ids", counted)
    client = app.test_client()
    for _ in range(2):
        calls.clear()
        assert client.get(f"/api/scout/players?season={SEASON}", headers=headers()).status_code == 200
        seen = set()
        for batch in calls:
            assert not seen & batch, calls
            seen.update(batch)
        assert ids["Kofi Asante-Reid"] in seen  # fresh policy on each request


@pytest.mark.parametrize(
    "uri",
    [
        "postgresql+psycopg:///aw_pc2?host=remote.invalid",
        "postgresql+psycopg://allowed.pooler.supabase.com/aw_pc2?host=remote.invalid",
        "postgresql+psycopg:///aw_pc2?host=localhost&host=remote.invalid",
        "postgresql+psycopg:///aw_pc2?host=localhost,remote.invalid",
        "postgresql+psycopg:///aw_pc2?hostaddr=192.0.2.1",
    ],
)
def test_pooler_host_validation_rejects_query_overrides_before_connect(monkeypatch, uri):
    from scripts import rebuild_reported_match_totals as rebuild

    monkeypatch.setenv("PC2_DATABASE_URL", uri)

    def forbidden(*a, **kw):
        raise AssertionError("invalid URL reached database setup")

    monkeypatch.setattr(db, "init_app", forbidden)
    with pytest.raises(SystemExit) as exc:
        rebuild.main(["--dry-run"])
    assert exc.value.code == 2


def test_undo_continues_after_changed_player_and_reports_idempotent_partial_result(app, tmp_path):
    from scripts import rebuild_reported_match_totals as rebuild

    ids, _user, _list = seed_personas()
    undo, cursor = tmp_path / "undo.jsonl", tmp_path / "cursor.json"
    result = rebuild.run(db.session, dry_run=False, limit=100, after=-(2**31), delay=0, undo=undo, checkpoint=cursor)
    assert result["players_changed"] == 5
    pid = ids["Reuben Castellane"]  # changed player in the middle of the journal
    total = PlayerSeasonTotal.query.filter_by(player_api_id=pid).one()
    total.goals = 987
    db.session.commit()
    for _ in range(2):
        assert rebuild.restore(db.session, undo) == {"players_restored": 4, "players_skipped": [pid]}
        assert PlayerSeasonTotal.query.filter_by(player_api_id=pid).one().goals == 987
    # All unaffected records restored even after the skipped player's position.
    kofi = PlayerSeasonTotal.query.filter_by(player_api_id=ids["Kofi Asante-Reid"]).one()
    assert kofi.minutes == 164


def test_dry_run_cannot_be_combined_with_mutating_rollback(monkeypatch):
    from scripts import rebuild_reported_match_totals as rebuild

    monkeypatch.setenv("PC2_DATABASE_URL", "postgresql+psycopg:///aw_pc2")
    with pytest.raises(SystemExit) as exc:
        rebuild.main(["--dry-run", "--rollback", "unused.jsonl"])
    assert exc.value.code == 2


@pytest.mark.parametrize("variable", ["PGHOST", "PGHOSTADDR", "PGSERVICE", "PGSERVICEFILE"])
@pytest.mark.parametrize(
    "uri", ["postgresql+psycopg:///aw_pc2", "postgresql+psycopg://allowed.pooler.supabase.com/aw_pc2"]
)
def test_rebuild_rejects_implicit_libpq_target_before_connect(monkeypatch, variable, uri):
    from scripts import rebuild_reported_match_totals as rebuild

    monkeypatch.setenv("PC2_DATABASE_URL", uri)
    monkeypatch.setenv(variable, "remote.invalid")
    monkeypatch.setattr(db, "init_app", lambda *a, **kw: pytest.fail("implicit target reached database setup"))
    with pytest.raises(SystemExit) as exc:
        rebuild.main(["--dry-run"])
    assert exc.value.code == 2


@pytest.mark.parametrize(
    "uri", ["postgresql+psycopg:///aw_pc2?service=name", "postgresql+psycopg://localhost/aw_pc2?service=name"]
)
def test_rebuild_rejects_libpq_query_service_before_connect(monkeypatch, uri):
    from scripts import rebuild_reported_match_totals as rebuild

    monkeypatch.setenv("PC2_DATABASE_URL", uri)
    monkeypatch.setattr(db, "init_app", lambda *a, **kw: pytest.fail("service reached database setup"))
    with pytest.raises(SystemExit) as exc:
        rebuild.main(["--dry-run"])
    assert exc.value.code == 2
