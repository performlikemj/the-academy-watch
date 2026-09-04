"""Add the append-only GOL credit ledger.

Revision ID: s3d1
Revises: s3c1
Create Date: 2026-09-04

Every DDL operation is guarded for the production schema's pre-apply drift.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, index_exists, table_exists

revision = "s3d1"
down_revision = "s3c1"
branch_labels = None
depends_on = None

TABLE = "gol_credit_ledger"
USER_BUCKET_INDEX = "ix_gol_credit_ledger_user_bucket"
PAYMENT_INTENT_INDEX = "ix_gol_credit_ledger_payment_intent"


def upgrade():
    if not table_exists(TABLE):
        op.create_table(
            TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_account_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("bucket", sa.String(length=20), nullable=False),
            sa.Column("kind", sa.String(length=20), nullable=False),
            sa.Column("delta", sa.Integer(), nullable=False),
            sa.Column("idempotency_key", sa.String(length=120), nullable=False),
            sa.Column("debit_id", sa.Integer(), sa.ForeignKey(f"{TABLE}.id"), nullable=True),
            sa.Column("client_msg_id", sa.String(length=64), nullable=True),
            sa.Column("attempt", sa.Integer(), nullable=True),
            sa.Column("stripe_event_id", sa.String(length=255), nullable=True),
            sa.Column("stripe_session_id", sa.String(length=255), nullable=True),
            sa.Column("stripe_payment_intent_id", sa.String(length=255), nullable=True),
            sa.Column("pack_id", sa.String(length=40), nullable=True),
            sa.Column("amount_paid_cents", sa.Integer(), nullable=True),
            sa.Column("currency", sa.String(length=3), nullable=True),
            sa.Column("refunded_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("note", sa.String(length=200), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "bucket IN ('free_allowance','prepaid')",
                name="ck_gol_credit_ledger_bucket",
            ),
            sa.CheckConstraint(
                "kind IN ('grant','debit','reversal','adjustment')",
                name="ck_gol_credit_ledger_kind",
            ),
            sa.CheckConstraint("delta <> 0", name="ck_gol_credit_ledger_delta_nonzero"),
            sa.UniqueConstraint("idempotency_key", name="uq_gol_credit_ledger_idempotency_key"),
            sa.UniqueConstraint("stripe_session_id", name="uq_gol_credit_ledger_stripe_session_id"),
        )
    if table_exists(TABLE):
        create_index_safe(USER_BUCKET_INDEX, TABLE, ["user_account_id", "bucket"])
        create_index_safe(PAYMENT_INTENT_INDEX, TABLE, ["stripe_payment_intent_id"])
        if op.get_bind().dialect.name != "sqlite":
            op.execute(sa.text(f'ALTER TABLE "{TABLE}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    if table_exists(TABLE):
        if index_exists(PAYMENT_INTENT_INDEX):
            op.drop_index(PAYMENT_INTENT_INDEX, table_name=TABLE)
        if index_exists(USER_BUCKET_INDEX):
            op.drop_index(USER_BUCKET_INDEX, table_name=TABLE)
        op.drop_table(TABLE)
