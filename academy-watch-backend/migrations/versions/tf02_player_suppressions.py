"""Player takedown requests and reversible publication suppressions.

Revision ID: tf02
Revises: tf01

This trust-floor migration deliberately chains ``tf02 -> tf01``. PR #636's
``gf01`` funding registry remains independently ordered. If ``gf01`` lands
first, re-point ``fc01`` onto ``gf01``, retain
``tf02 -> tf01 -> fc03 -> fc02 -> fc01``, upgrade ``gf01`` first, and downgrade
this entire stack before ``gf01``. If this stack lands first, re-point ``gf01``
onto ``tf02`` and downgrade ``gf01`` before ``tf02``. Never merge an
arrangement with two heads.

All DDL is guarded because production has drifted out-of-band. The public
table enables Row Level Security in this same migration with no permissive
direct-client policies. Downgrade refuses to discard any takedown history.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, index_exists, table_exists

revision = "tf02"
down_revision = "tf01"
branch_labels = None
depends_on = None

TABLE = "player_suppressions"
OPEN_INDEX = "uq_player_suppressions_open_player"
QUEUE_INDEX = "ix_player_suppressions_status_created"


def _table_has_rows() -> bool:
    return bool(op.get_bind().execute(sa.text(f'SELECT EXISTS (SELECT 1 FROM "{TABLE}")')).scalar())


def upgrade():
    if not table_exists(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("reason_code", sa.String(length=30), nullable=False),
            sa.Column("requester_role", sa.String(length=20), nullable=False),
            # Fernet ciphertext is intentionally Text; plaintext is bounded at intake.
            sa.Column("requester_contact", sa.Text(), nullable=False),
            sa.Column("request_statement", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="requested"),
            sa.Column("notes", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("decided_at", sa.DateTime(), nullable=True),
            sa.Column("decided_by", sa.String(length=200), nullable=True),
            sa.CheckConstraint(
                "reason_code IN ('guardian_request','player_request','legal','admin_other')",
                name="ck_player_suppressions_reason",
            ),
            sa.CheckConstraint(
                "requester_role IN ('player','guardian','club','other')",
                name="ck_player_suppressions_requester_role",
            ),
            sa.CheckConstraint(
                "status IN ('requested','active','lifted','rejected')",
                name="ck_player_suppressions_status",
            ),
        )

    if table_exists(TABLE):
        create_index_safe(
            OPEN_INDEX,
            TABLE,
            ["player_api_id"],
            unique=True,
            postgresql_where=sa.text("status IN ('requested', 'active')"),
            sqlite_where=sa.text("status IN ('requested', 'active')"),
        )
        create_index_safe(QUEUE_INDEX, TABLE, ["status", "created_at"])
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    if table_exists(TABLE) and _table_has_rows():
        raise RuntimeError("tf02 downgrade refused: player suppression history exists")
    if table_exists(TABLE):
        if index_exists(QUEUE_INDEX):
            op.drop_index(QUEUE_INDEX, table_name=TABLE)
        if index_exists(OPEN_INDEX):
            op.drop_index(OPEN_INDEX, table_name=TABLE)
        op.drop_table(TABLE)
