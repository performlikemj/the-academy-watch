"""Durable GOL executions, payment settlements, and immutable purchase terms.

Revision ID: s3e1
Revises: s3d1
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, index_exists, table_exists

revision = "s3e1"
down_revision = "s3d1"
branch_labels = None
depends_on = None

INDEXES = (
    ("ix_gol_chat_executions_debit", "gol_chat_executions", ["debit_id"]),
    ("ix_gol_payment_settlements_grant_ledger_id", "gol_payment_settlements", ["grant_ledger_id"]),
    ("ix_gol_checkout_terms_checkout_row_id", "gol_checkout_terms", ["checkout_row_id"]),
)


def upgrade():
    if not table_exists("gol_chat_executions"):
        op.create_table(
            "gol_chat_executions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_account_id", sa.Integer(), sa.ForeignKey("user_accounts.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("client_msg_id", sa.String(64), nullable=False),
            sa.Column("attempt", sa.Integer(), nullable=False),
            sa.Column("debit_id", sa.Integer(), sa.ForeignKey("gol_credit_ledger.id")),
            sa.Column("status", sa.String(20), nullable=False),
            sa.Column("input_hash", sa.String(64), nullable=False),
            sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("lease_started_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("response_text", sa.Text()),
            sa.Column("response_events", sa.Text()),
            sa.Column("recover_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("completed_at", sa.DateTime()),
            sa.UniqueConstraint("user_account_id", "client_msg_id", "attempt", name="uq_gol_chat_execution_attempt"),
            sa.CheckConstraint("status IN ('running','completed','failed')", name="ck_gol_chat_execution_status"),
        )
    if not table_exists("gol_payment_settlements"):
        op.create_table(
            "gol_payment_settlements",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("stripe_payment_intent_id", sa.String(255), nullable=False),
            sa.Column("grant_ledger_id", sa.Integer(), sa.ForeignKey("gol_credit_ledger.id", ondelete="SET NULL")),
            sa.Column("refund_target_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("refund_applied_cents", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("last_refund_event_id", sa.String(255)),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("stripe_payment_intent_id", name="uq_gol_payment_settlements_intent"),
        )
    if not table_exists("gol_checkout_terms"):
        op.create_table(
            "gol_checkout_terms",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("purchase_key", sa.String(36), nullable=False),
            sa.Column(
                "checkout_row_id", sa.Integer(), sa.ForeignKey("billing_checkout_sessions.id", ondelete="SET NULL")
            ),
            sa.Column("stripe_session_id", sa.String(255)),
            sa.Column("price_code", sa.String(40), nullable=False),
            sa.Column("credits", sa.Integer(), nullable=False),
            sa.Column("unit_amount_cents", sa.Integer(), nullable=False),
            sa.Column("currency", sa.String(3), nullable=False),
            sa.Column("stripe_price_id", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("attached_at", sa.DateTime()),
            sa.UniqueConstraint("purchase_key", name="uq_gol_checkout_terms_purchase_key"),
            sa.UniqueConstraint("stripe_session_id", name="uq_gol_checkout_terms_session"),
        )
    for name, table, columns in INDEXES:
        if table_exists(table):
            create_index_safe(name, table, columns)
            if op.get_bind().dialect.name == "postgresql":
                op.execute(sa.text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    for name, table, _columns in reversed(INDEXES):
        if table_exists(table):
            if index_exists(name):
                op.drop_index(name, table_name=table)
            op.drop_table(table)
