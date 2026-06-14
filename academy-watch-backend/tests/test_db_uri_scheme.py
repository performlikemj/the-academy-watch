"""Coercion of the SQLALCHEMY_DATABASE_URI scheme to psycopg v3."""

import pytest
from src.main import _coerce_psycopg_driver


@pytest.mark.parametrize(
    "raw, expect_driver",
    [
        ("postgresql://u:p@h:5432/db", "postgresql+psycopg"),
        ("postgres://u:p@h:5432/db", "postgresql+psycopg"),
        ("postgresql+psycopg://u:p@h:5432/db", "postgresql+psycopg"),
        ("postgresql+psycopg2://u:p@h:5432/db", "postgresql+psycopg2"),
    ],
)
def test_driver_coerced_to_psycopg(raw, expect_driver):
    from sqlalchemy.engine.url import make_url

    out = _coerce_psycopg_driver(raw)
    assert make_url(out).drivername == expect_driver


def test_supabase_pooler_string_preserves_everything():
    raw = "postgresql://postgres.abcd:s3cr3t@aws-0-x.pooler.supabase.com:6543/postgres?sslmode=require"
    out = _coerce_psycopg_driver(raw)
    from sqlalchemy.engine.url import make_url

    u = make_url(out)
    assert u.drivername == "postgresql+psycopg"
    assert u.username == "postgres.abcd"
    assert u.password == "s3cr3t"
    assert u.host == "aws-0-x.pooler.supabase.com"
    assert u.port == 6543
    assert u.database == "postgres"
    assert u.query.get("sslmode") == "require"


def test_invalid_uri_raises():
    with pytest.raises(Exception):
        _coerce_psycopg_driver("not a uri at all ::::")
