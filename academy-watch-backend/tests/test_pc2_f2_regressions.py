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


# Import access is intentionally narrow: additions require review of the actual
# use, even if an ORM alias or a new job hides how the model is queried.
ROLLUP_MODEL_FILES = {
    "models/season_rollup.py",  # definitions
    "main.py",
    "scripts/season_rollup_cold_build.py",  # schema registration only
    "services/reported_match_totals.py",  # sole effective public projection
    "services/season_rollup_service.py",  # writer
    "routes/club.py",  # authenticated own-club evidence
    "routes/showcase.py",  # merge writes
    "routes/players.py",  # projected DTO types + guarded source evidence
    "routes/season_rollup.py",
    "routes/seasons.py",
    "utils/academy_window.py",  # metadata
    "utils/team_season_stats.py",  # projected DTO type only
}
RAW_READ_FUNCTIONS = {
    "routes/club.py": {"_stable_result_payloads"},
    "routes/showcase.py": {"_rekey_rollup_rows", "_refresh_graduated_rollup"},
    "routes/season_rollup.py": {"_had_source_cell"},  # metadata-only source membership
    "routes/players.py": {"_rollup_source_breakdown"},  # eligibility guarded private source evidence
    "services/season_rollup_service.py": {"refresh_player"},
}
MODEL_NAMES = {"PlayerSeasonTotal", "PlayerSeasonCell"}
TABLE_NAMES = {"player_season_totals", "player_season_cells"}


def raw_total_reads(source):
    tree = ast.parse(source)
    aliases = set(MODEL_NAMES)
    for n in ast.walk(tree):
        if isinstance(n, ast.ImportFrom):
            aliases.update(a.asname or a.name for a in n.names if a.name in MODEL_NAMES)

    # Follow local and ORM aliases, including qualified module access.
    def model(node):
        return (
            (isinstance(node, ast.Name) and node.id in aliases)
            or (isinstance(node, ast.Attribute) and node.attr in MODEL_NAMES)
            or (isinstance(node, ast.Call) and any(model(a) for a in node.args))
        )

    for _ in range(3):
        for n in ast.walk(tree):
            if isinstance(n, ast.Assign) and model(n.value):
                aliases.update(t.id for t in n.targets if isinstance(t, ast.Name))
    violations = []
    metadata = {"player_api_id", "season", "level_group", "computed_at", "synced_at", "source", "id"}

    def walk(node, owner=None):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = node.name
        if isinstance(node, ast.Attribute) and model(node.value) and node.attr not in metadata:
            violations.append((owner, node.lineno))
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name)):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            if name in {"get", "query", "select", "aliased", "outerjoin", "join", "add_entity", "select_from"}:
                if any(model(a) for a in node.args):
                    violations.append((owner, node.lineno))
        for child in ast.iter_child_nodes(node):
            walk(child, owner)

    walk(tree)
    return violations


def rollup_boundary_violations(root):
    violations = []
    for path in root.rglob("*.py"):
        relative = path.relative_to(root).as_posix()
        source = path.read_text()
        tree = ast.parse(source)
        # Catch direct/qualified imports, model references and literal SQL,
        # across every src directory (including jobs, agents and workers).
        model_access = any(
            (isinstance(n, ast.Name) and n.id in MODEL_NAMES)
            or (isinstance(n, ast.Attribute) and n.attr in MODEL_NAMES)
            or (
                isinstance(n, ast.ImportFrom)
                and (
                    (
                        n.module == "src.models.season_rollup"
                        and any(a.name in MODEL_NAMES or a.name == "*" for a in n.names)
                    )
                    or (n.module == "src.models" and any(a.name == "season_rollup" for a in n.names))
                )
            )
            or (isinstance(n, ast.Import) and any("models.season_rollup" in a.name for a in n.names))
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
        if model_access and relative not in ROLLUP_MODEL_FILES:
            violations.append((relative, "model access outside reviewed files"))
        # The cold-build maintenance script explicitly addresses these tables.
        if raw_sql and relative not in {
            "models/season_rollup.py",
            "services/season_rollup_service.py",
            "scripts/season_rollup_cold_build.py",
        }:
            violations.append((relative, "raw stored table access"))
        if relative in ROLLUP_MODEL_FILES - {"models/season_rollup.py", "services/reported_match_totals.py"}:
            violations.extend(
                (relative, line)
                for owner, line in raw_total_reads(source)
                if owner not in RAW_READ_FUNCTIONS.get(relative, set())
            )
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
