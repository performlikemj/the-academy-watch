"""S3-P2a club program profile editing and moderated updates.

Revision ID: s3c1
Revises: cb01
Create Date: 2026-09-03

NOTE: the S3 orchestrator re-chains this migration onto ``s3b1`` before merge.

All DDL is guarded because production has drifted out-of-band. The new public
table is RLS enabled without permissive policies so direct/public clients
remain denied.
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

revision = "s3c1"
down_revision = "cb01"
branch_labels = None
depends_on = None

REVISION_TABLE = "club_program_profile_revisions"
UPDATES_TABLE = "club_program_updates"
UPDATES_INDEX = "ix_club_program_updates_program_status_published"

REVISION_COLUMNS = (
    sa.Column("external_support_provider", sa.String(30), nullable=True),
    sa.Column("external_support_url", sa.String(500), nullable=True),
)


def upgrade():
    if table_exists(REVISION_TABLE):
        for column in REVISION_COLUMNS:
            add_column_safe(REVISION_TABLE, column)

    if not table_exists(UPDATES_TABLE):
        op.create_table(
            UPDATES_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "program_id",
                sa.Integer(),
                sa.ForeignKey("club_programs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "author_user_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("title", sa.String(140), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("impact", sa.Text(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("reviewed_by", sa.String(200), nullable=True),
            sa.Column("review_reason", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "status IN ('pending','approved','rejected','withdrawn')",
                name="ck_club_program_updates_status",
            ),
        )
    create_index_safe(
        UPDATES_INDEX,
        UPDATES_TABLE,
        ["program_id", "status", "published_at"],
    )

    if table_exists(UPDATES_TABLE) and op.get_bind().dialect.name != "sqlite":
        op.execute(sa.text(f'ALTER TABLE "{UPDATES_TABLE}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    if table_exists(UPDATES_TABLE):
        if index_exists(UPDATES_INDEX):
            op.drop_index(UPDATES_INDEX, table_name=UPDATES_TABLE)
        op.drop_table(UPDATES_TABLE)

    if table_exists(REVISION_TABLE):
        for column in reversed(REVISION_COLUMNS):
            if column_exists(REVISION_TABLE, column.name):
                op.drop_column(REVISION_TABLE, column.name)
