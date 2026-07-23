"""Marketplace trust prerequisites for scout verification and content reports.

Revision ID: fc01
Revises: tre01

IMPORTANT: ``tre01`` was the sole head on this branch when this migration was
authored. PR #636 (``gf01``, funding registry) is open and may merge first. If
``gf01`` or another head lands first, re-point ``down_revision`` before merge.
Never allow a migration fork.

All DDL is guarded because production has drifted out-of-band. Both new public
tables have RLS enabled in this same migration. No permissive policies are
created: Flask exposes only authenticated, narrowly serialized views.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, index_exists, table_exists

revision = "fc01"
down_revision = "tre01"
branch_labels = None
depends_on = None


NEW_TABLES = (
    "scout_verifications",
    "content_reports",
)


def upgrade():
    if not table_exists("scout_verifications"):
        op.create_table(
            "scout_verifications",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("user_account_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("full_name", sa.String(length=200), nullable=False),
            sa.Column("organization", sa.String(length=200), nullable=False),
            sa.Column("role_title", sa.String(length=120), nullable=False),
            sa.Column("statement", sa.String(length=2000), nullable=False),
            sa.Column("evidence_urls", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("submitted_at", sa.DateTime(), nullable=False),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("reviewed_by", sa.String(length=200), nullable=True),
            sa.Column("review_notes", sa.String(length=2000), nullable=True),
            sa.Column("revocation_reason", sa.String(length=1000), nullable=True),
            sa.CheckConstraint(
                "status IN ('pending','approved','rejected','revoked')",
                name="ck_scout_verifications_status",
            ),
        )
    create_index_safe(
        "uq_scout_verifications_active_user",
        "scout_verifications",
        ["user_account_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'approved')"),
        sqlite_where=sa.text("status IN ('pending', 'approved')"),
    )
    create_index_safe(
        "ix_scout_verifications_user_submitted",
        "scout_verifications",
        ["user_account_id", "submitted_at"],
    )
    create_index_safe(
        "ix_scout_verifications_status_submitted",
        "scout_verifications",
        ["status", "submitted_at"],
    )

    if not table_exists("content_reports"):
        op.create_table(
            "content_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("reporter_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("subject_type", sa.String(length=40), nullable=False),
            sa.Column("subject_id", sa.String(length=200), nullable=False),
            sa.Column("reason_code", sa.String(length=80), nullable=False),
            sa.Column("details", sa.String(length=2000), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
            sa.Column("resolution_notes", sa.String(length=2000), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("resolved_at", sa.DateTime(), nullable=True),
            sa.CheckConstraint(
                "subject_type IN ('player_profile','showcase_content','club_program','contact_message','other')",
                name="ck_content_reports_subject_type",
            ),
            sa.CheckConstraint(
                "status IN ('open','reviewing','resolved','dismissed')",
                name="ck_content_reports_status",
            ),
        )
    create_index_safe(
        "ix_content_reports_reporter_created",
        "content_reports",
        ["reporter_user_id", "created_at"],
    )
    create_index_safe(
        "ix_content_reports_status_created",
        "content_reports",
        ["status", "created_at"],
    )
    create_index_safe(
        "ix_content_reports_subject",
        "content_reports",
        ["subject_type", "subject_id"],
    )

    for table_name in NEW_TABLES:
        # Idempotent and intentionally policy-free: direct/public roles see no
        # rows. Flask publishes only explicitly serialized fields.
        op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    indexes = (
        ("ix_content_reports_subject", "content_reports"),
        ("ix_content_reports_status_created", "content_reports"),
        ("ix_content_reports_reporter_created", "content_reports"),
        ("ix_scout_verifications_status_submitted", "scout_verifications"),
        ("ix_scout_verifications_user_submitted", "scout_verifications"),
        ("uq_scout_verifications_active_user", "scout_verifications"),
    )
    for index_name, table_name in indexes:
        if index_exists(index_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name in reversed(NEW_TABLES):
        if table_exists(table_name):
            op.drop_table(table_name)
