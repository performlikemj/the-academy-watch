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


def raw_total_reads(source):
    tree = ast.parse(source)
    aliases = {
        a.asname or a.name
        for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and n.module == "src.models.season_rollup"
        for a in n.names
        if a.name == "PlayerSeasonTotal"
    }
    violations = []

    def walk(node, owner=None):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = node.name
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id in aliases:
            if node.attr in {
                "query",
                "__table__",
                "appearances",
                "minutes",
                "goals",
                "assists",
                "yellows",
                "reds",
                "saves",
                "goals_conceded",
            }:
                violations.append((owner, node.lineno))
        if isinstance(node, ast.Call) and isinstance(node.func, (ast.Attribute, ast.Name)):
            name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id
            if name in {"query", "select"} and any(isinstance(a, ast.Name) and a.id in aliases for a in node.args):
                violations.append((owner, node.lineno))
        for child in ast.iter_child_nodes(node):
            walk(child, owner)

    walk(tree)
    return violations


def test_public_readers_cannot_query_raw_stored_report_figures():
    root = Path(__file__).resolve().parents[1] / "src"
    # Explicit private writer/evidence exceptions, never public headlines.
    allowed = {
        "routes/club.py": {"_stable_result_payloads"},  # authenticated own-club source evidence only
        "routes/showcase.py": {"_rekey_rollup_rows", "_refresh_graduated_rollup"},  # merge writes
        "services/season_rollup_service.py": {"refresh_player"},  # writer
    }
    for directory in ("routes", "services", "utils"):
        for path in (root / directory).rglob("*.py"):
            relative = path.relative_to(root).as_posix()
            if relative == "services/reported_match_totals.py":
                continue  # sole effective SQL projection, including rejected/absent cells
            assert not [v for v in raw_total_reads(path.read_text()) if v[0] not in allowed.get(relative, set())], (
                relative
            )
    # The guard catches the exact reviewed Compare bypass, including aliases.
    assert raw_total_reads(
        "from src.models.season_rollup import PlayerSeasonTotal as PST\ndef compare():\n return PST.query.all()"
    )
    assert raw_total_reads(
        "from src.models.season_rollup import PlayerSeasonTotal as PST\ndef read():\n return select(PST.minutes)"
    )


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
