import importlib
from contextlib import contextmanager

import sqlalchemy as sa
from alembic import op as alembic_op
from alembic.migration import MigrationContext
from alembic.operations import Operations


@contextmanager
def alembic_ops(engine):
    """Yield an Alembic Operations proxy bound to the given engine."""
    conn = engine.connect()
    trans = conn.begin()
    ctx = MigrationContext.configure(conn)
    operations = Operations(ctx)
    original_proxy = getattr(alembic_op, "_proxy", None)
    alembic_op._proxy = operations
    try:
        yield operations
        trans.commit()
    finally:
        alembic_op._proxy = original_proxy
        conn.close()


def _prepare_base_tables(metadata):
    # Minimal schemas reflecting current production tables (missing new fields)
    sa.Table(
        "user_accounts",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=80), nullable=False),
        sa.Column("display_name_lower", sa.String(length=80), nullable=False),
        sa.Column("display_name_confirmed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
        sa.Column("last_login_at", sa.DateTime()),
        sa.Column("last_display_name_change_at", sa.DateTime()),
        sa.Column("can_author_commentary", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    sa.Table(
        "newsletters",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
    )

    sa.Table(
        "newsletter_commentary",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("newsletter_id", sa.Integer, sa.ForeignKey("newsletters.id"), nullable=False),
        sa.Column("player_id", sa.Integer),
        sa.Column("commentary_type", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("author_id", sa.Integer, nullable=False),
        sa.Column("author_name", sa.String(length=120), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime()),
        sa.Column("updated_at", sa.DateTime()),
    )


def test_upgrade_adds_journalist_profile_fields(sqlite_memory_engine):
    """Migration should add journalist/profile columns without dropping data."""
    engine = sqlite_memory_engine
    metadata = sa.MetaData()
    _prepare_base_tables(metadata)
    metadata.create_all(engine)

    # New migration should add missing columns
    migration = importlib.import_module(
        "migrations.versions.z5a6b7c8d9e0_add_journalist_profile_fields"
    )

    with alembic_ops(engine):
        migration.upgrade()

    inspector = sa.inspect(engine)
    user_cols = {col["name"] for col in inspector.get_columns("user_accounts")}
    assert {"is_journalist", "bio", "profile_image_url"}.issubset(user_cols)

    commentary_cols = {col["name"] for col in inspector.get_columns("newsletter_commentary")}
    assert {"title", "is_premium"}.issubset(commentary_cols)
