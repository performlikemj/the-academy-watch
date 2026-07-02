"""Product analytics events table.

Creates ``product_events`` — first-party telemetry rows (pageview, follow_added,
...). No cookies / IP / user-agent columns by design.

Idempotent (guards + helpers) — production has had objects added out-of-band,
so every DDL op is safe to re-run in both directions.

Revision ID: aw21
Revises: vid03
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import (
    create_index_safe,
    index_exists,
    table_exists,
)
from sqlalchemy.dialects.postgresql import JSONB

revision = "aw21"
down_revision = "vid03"
branch_labels = None
depends_on = None


def upgrade():
    if not table_exists("product_events"):
        op.create_table(
            "product_events",
            sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
            sa.Column("event_name", sa.String(length=64), nullable=False),
            sa.Column("user_email", sa.String(length=320), nullable=True),
            sa.Column("session_id", sa.String(length=64), nullable=True),
            sa.Column("path", sa.String(length=512), nullable=True),
            sa.Column("referrer", sa.String(length=512), nullable=True),
            sa.Column("props", JSONB(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        )
    create_index_safe("ix_product_events_name_created", "product_events", ["event_name", "created_at"])
    create_index_safe("ix_product_events_created", "product_events", ["created_at"])


def downgrade():
    if index_exists("ix_product_events_created"):
        op.drop_index("ix_product_events_created", table_name="product_events")
    if index_exists("ix_product_events_name_created"):
        op.drop_index("ix_product_events_name_created", table_name="product_events")
    if table_exists("product_events"):
        op.drop_table("product_events")
