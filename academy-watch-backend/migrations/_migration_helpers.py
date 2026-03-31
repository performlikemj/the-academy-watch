"""Shared helpers for idempotent migrations.

Columns and tables were added out-of-band to production, so migrations
must guard against duplicates.
"""
import sqlalchemy as sa
from alembic import op


def column_exists(table, column):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = :table AND column_name = :column"
    ), {'table': table, 'column': column})
    return result.scalar() is not None


def table_exists(table):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM information_schema.tables "
        "WHERE table_name = :table AND table_schema = 'public'"
    ), {'table': table})
    return result.scalar() is not None


def index_exists(index_name):
    conn = op.get_bind()
    result = conn.execute(sa.text(
        "SELECT 1 FROM pg_indexes WHERE indexname = :name"
    ), {'name': index_name})
    return result.scalar() is not None


def add_column_safe(table, column):
    """Add a column only if it doesn't already exist."""
    if not column_exists(table, column.name):
        op.add_column(table, column)


def create_index_safe(index_name, table, columns, **kwargs):
    """Create an index only if it doesn't already exist."""
    if not index_exists(index_name):
        op.create_index(index_name, table, columns, **kwargs)
