from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


def test_alembic_has_single_head():
    """Ensure Alembic history stays merged so upgrades run without ambiguity."""
    repo_root = Path(__file__).resolve().parent.parent
    alembic_ini = repo_root / "alembic.ini"

    cfg = Config(str(alembic_ini))
    cfg.set_main_option("script_location", str(repo_root / "migrations"))

    script = ScriptDirectory.from_config(cfg)
    heads = script.get_heads()

    assert len(heads) == 1, f"Expected 1 Alembic head, found {len(heads)}: {heads}"
