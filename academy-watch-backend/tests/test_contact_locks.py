# ruff: noqa: F811
"""Contact scope protocol guard and retry responses for every contact route."""

import ast
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.exc import OperationalError
from src.services.contact_locks import database_conflict
from test_contact import _verified_scout, client, contact_app  # noqa: F401

ROOT = Path(__file__).parents[1] / "src"
TABLE_MODELS = {"ClubProgram", "ClubPlayerPublication", "PlayerProfileClaim", "ContactRequest"}
TABLE_NAMES = {"club_programs", "club_player_publications", "player_profile_claims", "contact_requests"}


def direct_scope_locks(source, path):
    """Follow local query aliases so `query.with_for_update()` cannot bypass this guard."""
    tree = ast.parse(source)
    model_aliases = set(TABLE_MODELS)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            model_aliases.update(alias.asname or alias.name for alias in node.names if alias.name in TABLE_MODELS)
    for function in ast.walk(tree):
        if not isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        tainted = set(model_aliases)

        def touches(node):
            return any(
                isinstance(child, ast.Name)
                and child.id in tainted
                or isinstance(child, ast.Constant)
                and isinstance(child.value, str)
                and child.value in TABLE_NAMES
                for child in ast.walk(node)
            )

        # Query aliases can have several assignment stages. A fixed point catches
        # them without relying on names such as query / claims / statement.
        assignments = [n for n in ast.walk(function) if isinstance(n, (ast.Assign, ast.AnnAssign))]
        for _ in assignments:
            before = set(tainted)
            for assignment in assignments:
                if assignment.value and touches(assignment.value):
                    targets = assignment.targets if isinstance(assignment, ast.Assign) else [assignment.target]
                    for target in targets:
                        tainted.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
            for loop in (n for n in ast.walk(function) if isinstance(n, ast.For)):
                if touches(loop.iter):
                    tainted.update(n.id for n in ast.walk(loop.target) if isinstance(n, ast.Name))
            if before == tainted:
                break
        for node in ast.walk(function):
            if not isinstance(node, ast.Call):
                continue
            locking = (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "with_for_update"
                or any(
                    key.arg == "with_for_update" and isinstance(key.value, ast.Constant) and key.value.value is True
                    for key in node.keywords
                )
            )
            if locking and touches(node):
                expression = ast.unparse(node)
                key = f"{path}:{function.name}:{hashlib.sha256(expression.encode()).hexdigest()[:16]}"
                yield key, node.lineno, expression


def test_no_new_scope_row_locks_outside_helper():
    # Frozen exceptions are existing program-only prefixes and the publication-
    # only dark email-retention sweep. New four-table row locks belong in helper.
    allowed = set(json.loads(Path(__file__).with_name("contact_single_row_locks.json").read_text()))
    found = {}
    for path in ROOT.rglob("*.py"):
        relative = str(path.relative_to(ROOT))
        if relative == "services/contact_locks.py":
            continue
        for key, line, expression in direct_scope_locks(path.read_text(), relative):
            found[key] = (line, expression)
    assert set(found) <= allowed, {key: found[key] for key in set(found) - allowed}
    assert allowed <= set(found), "Remove obsolete lock exceptions rather than growing the allowlist"


def test_guard_follows_query_aliases_and_refresh_locks():
    for source in (
        "def new_route():\n query = PlayerProfileClaim.query.filter_by(id=1)\n candidate = query.populate_existing()\n return candidate.with_for_update().first()",
        "def new_route():\n return session.get(ContactRequest, id_, with_for_update=True)",
        "def new_route():\n statement = sa.select(programs).where(programs.c.id == 1)\n return statement.with_for_update()",
    ):
        # The raw SQL table declaration is tracked when it is in the function.
        source = source.replace(" statement =", " programs = sa.table('club_programs')\n statement =")
        assert list(direct_scope_locks(source, "routes/new.py"))


@pytest.mark.parametrize(
    "state,status,code",
    [("40P01", 409, "contact_conflict"), ("40001", 409, "contact_conflict"), ("55P03", 503, "contact_busy")],
)
def test_retry_classifier(state, status, code):
    assert database_conflict(OperationalError("synthetic", {}, SimpleNamespace(sqlstate=state))) == (code, status)
    assert database_conflict(OperationalError("synthetic", {}, SimpleNamespace(pgcode=state))) == (code, status)


def test_unrelated_database_error_is_not_masked():
    assert database_conflict(OperationalError("synthetic", {}, SimpleNamespace(sqlstate="42P01"))) is None


@pytest.mark.parametrize(
    "endpoint,method",
    [
        ("/api/contact/requests", "POST"),
        ("/api/contact/requests?box=sent", "GET"),
        *[
            (f"/api/contact/requests/synthetic/{path}", method)
            for path, method in (
                ("accept", "POST"),
                ("decline", "POST"),
                ("club-consent", "POST"),
                ("withdraw", "POST"),
                ("messages", "GET"),
                ("messages", "POST"),
                ("outcome", "POST"),
                ("revoke", "POST"),
            )
        ],
    ],
)
@pytest.mark.parametrize(
    "state,status,code",
    [("40P01", 409, "contact_conflict"), ("40001", 409, "contact_conflict"), ("55P03", 503, "contact_busy")],
)
def test_every_contact_route_rolls_back_contention(client, monkeypatch, endpoint, method, state, status, code):
    import src.routes.contact as routes
    from src.models.league import db

    _, headers = _verified_scout("c1f7-retry@example.test")
    rolled_back = []
    original = db.session.rollback

    def rollback():
        rolled_back.append(True)
        return original()

    def conflict():
        raise OperationalError("synthetic", {}, SimpleNamespace(sqlstate=state))

    monkeypatch.setattr(db.session, "rollback", rollback)
    monkeypatch.setattr(routes, "_current_user_account", conflict)
    response = client.open(endpoint, method=method, headers=headers, json={})
    assert response.status_code == status and response.json["error"] == code
    assert rolled_back
