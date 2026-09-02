"""Add the fan grain and profile-activity email preferences.

Revision ID: s2f1
Revises: pm01
Create Date: 2026-09-02

All DDL is guarded because production may be pre-applied through the pooler and
partially present when Alembic advances. The new public table is RLS enabled
without permissive policies so direct/public clients remain denied.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import (
    add_column_safe,
    column_exists,
    create_index_safe,
    index_exists,
    table_exists,
)

revision = "s2f1"
down_revision = "pm01"
branch_labels = None
depends_on = None

FAN_INDEX = "ix_player_fans_player_created"


def upgrade():
    if not table_exists("player_fans"):
        op.create_table(
            "player_fans",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_account_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint("player_api_id <> 0", name="ck_player_fans_nonzero"),
            sa.UniqueConstraint(
                "user_account_id",
                "player_api_id",
                name="uq_player_fans_user_player",
            ),
        )
    create_index_safe(
        FAN_INDEX,
        "player_fans",
        ["player_api_id", "created_at"],
    )

    if table_exists("user_accounts"):
        add_column_safe(
            "user_accounts",
            sa.Column(
                "profile_activity_email_opt_in",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        add_column_safe(
            "user_accounts",
            sa.Column(
                "profile_activity_email_last_sent_at",
                sa.DateTime(),
                nullable=True,
            ),
        )

    if table_exists("player_fans") and op.get_bind().dialect.name != "sqlite":
        op.execute(sa.text('ALTER TABLE "player_fans" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    if table_exists("user_accounts"):
        if column_exists("user_accounts", "profile_activity_email_last_sent_at"):
            op.drop_column("user_accounts", "profile_activity_email_last_sent_at")
        if column_exists("user_accounts", "profile_activity_email_opt_in"):
            op.drop_column("user_accounts", "profile_activity_email_opt_in")

    if table_exists("player_fans"):
        if index_exists(FAN_INDEX):
            op.drop_index(FAN_INDEX, table_name="player_fans")
        op.drop_table("player_fans")
