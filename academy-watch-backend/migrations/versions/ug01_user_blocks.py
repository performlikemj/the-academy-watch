"""Persistent user-level blocks for UGC safety.

Revision ID: ug01
Revises: td01
Create Date: 2026-07-24

``td01`` was the sole Alembic head after this branch refreshed from
``origin/main``. If another migration lands first, re-point ``down_revision``
before merge. Never allow a migration fork.

All DDL is guarded because production has drifted out-of-band. The new public
table enables Row Level Security in this same migration with no permissive
direct-client policies. Downgrade checks every object before removing it so a
partially applied schema remains recoverable.

DEPLOY ORDERING (migrations do NOT auto-run): pre-apply ``ug01`` before
deploying block routes or enforcement queries. Those code paths require the
table to exist; re-running the guarded upgrade is a clean no-op.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, index_exists, table_exists

revision = "ug01"
down_revision = "td01"
branch_labels = None
depends_on = None

TABLE = "user_blocks"
BLOCKED_USER_INDEX = "ix_user_blocks_blocked_user"


def upgrade():
    if not table_exists(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "blocker_user_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id"),
                nullable=False,
            ),
            sa.Column(
                "blocked_user_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id"),
                nullable=False,
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.UniqueConstraint(
                "blocker_user_id",
                "blocked_user_id",
                name="uq_user_blocks_pair",
            ),
            sa.CheckConstraint(
                "blocker_user_id <> blocked_user_id",
                name="ck_user_blocks_no_self",
            ),
        )

    if table_exists(TABLE):
        create_index_safe(
            BLOCKED_USER_INDEX,
            TABLE,
            ["blocked_user_id", "blocker_user_id"],
        )
        op.execute(sa.text(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    if table_exists(TABLE):
        if index_exists(BLOCKED_USER_INDEX):
            op.drop_index(BLOCKED_USER_INDEX, table_name=TABLE)
        op.drop_table(TABLE)
