"""Claimant-accepted private club relationships, shipped disabled.

Revision ID: s4a1
Revises: s3e1
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import column_exists, create_index_safe, table_exists

revision = "s4a1"
down_revision = "s3e1"
branch_labels = None
depends_on = None

TABLE = "club_invitations"
ROSTER = "club_roster_members"


def _columns():
    return [
        sa.Column("id", sa.String(36), nullable=False),
        sa.Column("program_id", sa.Integer(), nullable=False),
        sa.Column("player_api_id", sa.Integer(), nullable=False),
        sa.Column("claim_id", sa.Integer(), nullable=False),
        sa.Column("recipient_user_id", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.Integer()),
        sa.Column("source_manager_claim_id", sa.Integer()),
        sa.Column("client_request_id", sa.String(36), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("responded_at", sa.DateTime()),
        sa.Column("revoked_at", sa.DateTime()),
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
        op.create_primary_key("pk_club_invitations", TABLE, ["id"])
    checks = {
        "ck_club_invitation_status": "status IN ('pending','accepted','declined','revoked','expired')",
        "ck_club_invitation_subject": "player_api_id <> 0",
        "ck_club_invitation_expiry": "expires_at > created_at",
    }
    for name, expression in checks.items():
        if name not in {row["name"] for row in _inspector().get_check_constraints(TABLE)}:
            op.create_check_constraint(name, TABLE, expression)
    if not any(
        row["column_names"] == ["program_id", "created_by_user_id", "client_request_id"]
        for row in _inspector().get_unique_constraints(TABLE)
    ):
        op.create_unique_constraint(
            "uq_club_invitation_request", TABLE, ["program_id", "created_by_user_id", "client_request_id"]
        )
    for column in (
        sa.Column("accepted_invitation_id", sa.String(36)),
        sa.Column("requires_player_acceptance", sa.Boolean(), nullable=False, server_default=sa.false()),
    ):
        if not column_exists(ROSTER, column.name):
            op.add_column(ROSTER, column)
    for table, column, target, ondelete in (
        (TABLE, "program_id", "club_programs", "CASCADE"),
        (TABLE, "claim_id", "player_profile_claims", None),
        (TABLE, "recipient_user_id", "user_accounts", None),
        (TABLE, "created_by_user_id", "user_accounts", None),
        (TABLE, "source_manager_claim_id", "club_program_claims", "SET NULL"),
        (ROSTER, "accepted_invitation_id", TABLE, "SET NULL"),
    ):
        if not any(
            fk["constrained_columns"] == [column] and fk["referred_table"] == target
            for fk in _inspector().get_foreign_keys(table)
        ):
            op.create_foreign_key(f"fk_{table}_{column}", table, target, [column], ["id"], ondelete=ondelete)
    create_index_safe(
        "uq_club_invitation_active",
        TABLE,
        ["program_id", "player_api_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending','accepted')"),
        sqlite_where=sa.text("status IN ('pending','accepted')"),
    )
    create_index_safe("ix_club_invitation_recipient", TABLE, ["recipient_user_id", "status", "created_at", "id"])
    create_index_safe("ix_club_invitation_program", TABLE, ["program_id", "status", "created_at", "id"])
    create_index_safe("ix_club_roster_members_accepted_invitation_id", ROSTER, ["accepted_invitation_id"])
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("ALTER TABLE club_invitations ENABLE ROW LEVEL SECURITY"))


def downgrade():
    # Remove governed roster access before removing its durable acceptance marker.
    if column_exists(ROSTER, "requires_player_acceptance"):
        if table_exists("video_roster_entries") and column_exists("video_roster_entries", "club_roster_member_id"):
            op.execute(
                sa.text(
                    "UPDATE video_roster_entries SET club_roster_member_id = NULL WHERE club_roster_member_id IN (SELECT id FROM club_roster_members WHERE requires_player_acceptance = true)"
                )
            )
        op.execute(sa.text("DELETE FROM club_roster_members WHERE requires_player_acceptance = true"))
    for column in ("accepted_invitation_id", "requires_player_acceptance"):
        if column_exists(ROSTER, column):
            op.drop_column(ROSTER, column)
    if table_exists(TABLE):
        op.drop_table(TABLE)
