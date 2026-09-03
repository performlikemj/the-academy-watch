"""Add moderated club program profiles and updates.

Revision ID: s3c1
Revises: s3b1
Create Date: 2026-09-03

All DDL is guarded because production may contain partially pre-applied schema.
The updates table is RLS enabled without policies so direct clients remain
default-deny.
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
down_revision = "s3b1"
branch_labels = None
depends_on = None

REVISION_TABLE = "club_program_profile_revisions"
UPDATES_TABLE = "club_program_updates"
UPDATES_INDEX = "ix_club_program_updates_program_status_published"


def upgrade():
    if table_exists(REVISION_TABLE):
        add_column_safe(
            REVISION_TABLE,
            sa.Column("external_support_provider", sa.String(length=30), nullable=True),
        )
        add_column_safe(
            REVISION_TABLE,
            sa.Column("external_support_url", sa.String(length=500), nullable=True),
        )

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
            sa.Column("title", sa.String(length=140), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("impact", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("reviewed_by", sa.String(length=200), nullable=True),
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
    if table_exists(UPDATES_TABLE):
        create_index_safe(
            UPDATES_INDEX,
            UPDATES_TABLE,
            ["program_id", "status", "published_at"],
        )
        if op.get_bind().dialect.name != "sqlite":
            op.execute(sa.text(f'ALTER TABLE "{UPDATES_TABLE}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    if table_exists(UPDATES_TABLE):
        if index_exists(UPDATES_INDEX):
            op.drop_index(UPDATES_INDEX, table_name=UPDATES_TABLE)
        op.drop_table(UPDATES_TABLE)

    if table_exists(REVISION_TABLE):
        for column_name in ("external_support_url", "external_support_provider"):
            if column_exists(REVISION_TABLE, column_name):
                op.drop_column(REVISION_TABLE, column_name)
