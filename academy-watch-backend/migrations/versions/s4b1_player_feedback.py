"""Immutable private player feedback revisions.

Revision ID: s4b1
Revises: s4a1
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import column_exists, create_index_safe, table_exists

revision = "s4b1"
down_revision = "s4a1"
branch_labels = None
depends_on = None
TABLE = "player_feedback"


def _columns():
    return [
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("thread_id", sa.String(36), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("invitation_id", sa.String(36), nullable=False),
        sa.Column("claim_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("player_api_id", sa.Integer(), nullable=False),
        sa.Column("author_user_id", sa.Integer()),
        sa.Column("video_match_id", sa.Integer()),
        sa.Column("title", sa.String(140), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("observation_refs", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("client_request_id", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("acknowledged_at", sa.DateTime()),
        sa.Column("withdrawn_at", sa.DateTime()),
        sa.Column("audit_expires_at", sa.DateTime()),
    ]


def _inspector():
    return sa.inspect(op.get_bind())


def upgrade():
    if not table_exists(TABLE):
        op.create_table(TABLE, *_columns())
    for column in _columns():
        if not column_exists(TABLE, column.name):
            op.add_column(TABLE, column)
    if not _inspector().get_pk_constraint(TABLE)["constrained_columns"]:
        op.create_primary_key("pk_player_feedback", TABLE, ["id"])
    for name, expression in {
        "ck_player_feedback_revision": "revision >= 1",
        "ck_player_feedback_subject": "player_api_id <> 0 AND player_api_id BETWEEN -2147483647 AND 2147483647",
    }.items():
        if name not in {c["name"] for c in _inspector().get_check_constraints(TABLE)}:
            op.create_check_constraint(name, TABLE, expression)
    for name, columns in (
        ("uq_player_feedback_revision", ["thread_id", "revision"]),
        ("uq_player_feedback_request", ["program_id", "client_request_id"]),
    ):
        if not any(c["column_names"] == columns for c in _inspector().get_unique_constraints(TABLE)):
            op.create_unique_constraint(name, TABLE, columns)
    for column, target, ondelete in (
        ("program_id", "club_programs", None),
        ("invitation_id", "club_invitations", None),
        ("claim_id", "player_profile_claims", None),
        ("recipient_user_id", "user_accounts", None),
        ("author_user_id", "user_accounts", "SET NULL"),
        ("video_match_id", "video_matches", "SET NULL"),
    ):
        if not any(
            c["constrained_columns"] == [column] and c["referred_table"] == target
            for c in _inspector().get_foreign_keys(TABLE)
        ):
            op.create_foreign_key(f"fk_player_feedback_{column}", TABLE, target, [column], ["id"], ondelete=ondelete)
    create_index_safe("ix_player_feedback_recipient", TABLE, ["recipient_user_id", "published_at", "id"])
    create_index_safe("ix_player_feedback_invitation", TABLE, ["invitation_id", "thread_id", "revision"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE player_feedback ENABLE ROW LEVEL SECURITY"))


def downgrade():
    if table_exists(TABLE):
        op.drop_table(TABLE)
