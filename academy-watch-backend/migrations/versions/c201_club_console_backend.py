"""Club console roster, club-owned match video, and local takedowns.

Revision ID: c201
Revises: ob01
Create Date: 2026-08-09

All DDL is guarded because production has drifted out-of-band. The new public
``club_roster_members`` table enables RLS in this migration. Downgrade refuses
to discard club-console rows or local-player takedown history.
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

revision = "c201"
down_revision = "ob01"
branch_labels = None
depends_on = None

ROSTER_TABLE = "club_roster_members"


def _constraint_exists(table_name: str, constraint_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    groups = (
        inspector.get_check_constraints(table_name),
        inspector.get_unique_constraints(table_name),
        inspector.get_foreign_keys(table_name),
    )
    return any(row.get("name") == constraint_name for rows in groups for row in rows)


def _ensure_roster_columns() -> None:
    columns = (
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "program_id",
            sa.Integer(),
            sa.ForeignKey("club_programs.id", ondelete="CASCADE", name="fk_club_roster_program"),
            nullable=False,
        ),
        sa.Column("player_api_id", sa.Integer(), nullable=True),
        sa.Column(
            "local_player_id",
            sa.Integer(),
            sa.ForeignKey("local_players.id", name="fk_club_roster_local_player"),
            nullable=True,
        ),
        sa.Column(
            "added_by_user_id",
            sa.Integer(),
            sa.ForeignKey("user_accounts.id", name="fk_club_roster_added_by"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=80), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    for column in columns:
        add_column_safe(ROSTER_TABLE, column)


def _ensure_roster_constraints() -> None:
    constraints = (
        (
            "ck_club_roster_member_subject_xor",
            lambda: op.create_check_constraint(
                "ck_club_roster_member_subject_xor",
                ROSTER_TABLE,
                "(player_api_id IS NOT NULL AND local_player_id IS NULL) OR "
                "(player_api_id IS NULL AND local_player_id IS NOT NULL)",
            ),
        ),
        (
            "uq_club_roster_program_player",
            lambda: op.create_unique_constraint(
                "uq_club_roster_program_player",
                ROSTER_TABLE,
                ["program_id", "player_api_id"],
            ),
        ),
        (
            "uq_club_roster_program_local_player",
            lambda: op.create_unique_constraint(
                "uq_club_roster_program_local_player",
                ROSTER_TABLE,
                ["program_id", "local_player_id"],
            ),
        ),
    )
    for name, create in constraints:
        if not _constraint_exists(ROSTER_TABLE, name):
            create()


def _upgrade_roster() -> None:
    if not table_exists(ROSTER_TABLE):
        op.create_table(
            ROSTER_TABLE,
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "program_id",
                sa.Integer(),
                sa.ForeignKey("club_programs.id", ondelete="CASCADE", name="fk_club_roster_program"),
                nullable=False,
            ),
            sa.Column("player_api_id", sa.Integer(), nullable=True),
            sa.Column(
                "local_player_id",
                sa.Integer(),
                sa.ForeignKey("local_players.id", name="fk_club_roster_local_player"),
                nullable=True,
            ),
            sa.Column(
                "added_by_user_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id", name="fk_club_roster_added_by"),
                nullable=False,
            ),
            sa.Column("role", sa.String(length=80), nullable=True),
            sa.Column("note", sa.String(length=500), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint(
                "(player_api_id IS NOT NULL AND local_player_id IS NULL) OR "
                "(player_api_id IS NULL AND local_player_id IS NOT NULL)",
                name="ck_club_roster_member_subject_xor",
            ),
            sa.UniqueConstraint("program_id", "player_api_id", name="uq_club_roster_program_player"),
            sa.UniqueConstraint(
                "program_id",
                "local_player_id",
                name="uq_club_roster_program_local_player",
            ),
        )
    else:
        _ensure_roster_columns()
        _ensure_roster_constraints()
    create_index_safe(
        "ix_club_roster_members_program",
        ROSTER_TABLE,
        ["program_id", "created_at"],
    )
    op.execute(sa.text(f'ALTER TABLE "{ROSTER_TABLE}" ENABLE ROW LEVEL SECURITY'))


def _upgrade_video_scope() -> None:
    if table_exists("video_matches"):
        add_column_safe(
            "video_matches",
            sa.Column(
                "club_program_id",
                sa.Integer(),
                sa.ForeignKey("club_programs.id", name="fk_video_matches_club_program"),
                nullable=True,
            ),
        )
        add_column_safe("video_matches", sa.Column("processing_requested_at", sa.DateTime(), nullable=True))
        add_column_safe(
            "video_matches",
            sa.Column(
                "processing_requested_by_user_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id", name="fk_video_matches_processing_requester"),
                nullable=True,
            ),
        )
        if column_exists("video_matches", "team_id"):
            op.alter_column("video_matches", "team_id", existing_type=sa.Integer(), nullable=True)
        create_index_safe("ix_video_matches_club_program_id", "video_matches", ["club_program_id"])

    if table_exists("video_roster_entries"):
        add_column_safe(
            "video_roster_entries",
            sa.Column(
                "club_roster_member_id",
                sa.Integer(),
                sa.ForeignKey(
                    "club_roster_members.id",
                    ondelete="SET NULL",
                    name="fk_video_roster_club_member",
                ),
                nullable=True,
            ),
        )
        create_index_safe(
            "ix_video_roster_entries_club_roster_member_id",
            "video_roster_entries",
            ["club_roster_member_id"],
        )

    if table_exists("video_player_reports"):
        for column in (
            sa.Column("club_program_id_at_finalize", sa.Integer(), nullable=True),
            sa.Column("club_roster_member_id_at_finalize", sa.Integer(), nullable=True),
            sa.Column("club_player_api_id_at_finalize", sa.Integer(), nullable=True),
            sa.Column("club_local_player_id_at_finalize", sa.Integer(), nullable=True),
        ):
            add_column_safe("video_player_reports", column)
        create_index_safe(
            "ix_video_player_reports_club_program_finalize",
            "video_player_reports",
            ["club_program_id_at_finalize"],
        )


def _upgrade_local_suppressions() -> None:
    if not table_exists("player_suppressions"):
        return
    add_column_safe("player_suppressions", sa.Column("local_player_id", sa.Integer(), nullable=True))
    if column_exists("player_suppressions", "player_api_id"):
        op.alter_column("player_suppressions", "player_api_id", existing_type=sa.Integer(), nullable=True)
    if index_exists("uq_player_suppressions_open_player"):
        op.drop_index("uq_player_suppressions_open_player", table_name="player_suppressions")
    create_index_safe(
        "uq_player_suppressions_open_player",
        "player_suppressions",
        ["player_api_id"],
        unique=True,
        postgresql_where=sa.text("player_api_id IS NOT NULL AND status IN ('requested', 'active')"),
    )
    create_index_safe(
        "uq_player_suppressions_open_local_player",
        "player_suppressions",
        ["local_player_id"],
        unique=True,
        postgresql_where=sa.text("local_player_id IS NOT NULL AND status IN ('requested', 'active')"),
    )
    if not _constraint_exists("player_suppressions", "ck_player_suppressions_subject_xor"):
        op.create_check_constraint(
            "ck_player_suppressions_subject_xor",
            "player_suppressions",
            "(player_api_id IS NOT NULL AND local_player_id IS NULL) OR "
            "(player_api_id IS NULL AND local_player_id IS NOT NULL)",
        )


def upgrade():
    _upgrade_roster()
    _upgrade_video_scope()
    _upgrade_local_suppressions()


def _has_rows(sql: str) -> bool:
    return op.get_bind().execute(sa.text(sql)).scalar() is not None


def downgrade():
    # Refuse every known C2 data-loss path before changing any schema. Alembic
    # uses transactional DDL on Postgres, but an explicit preflight keeps this
    # safe and auditable on every supported invocation path.
    if table_exists(ROSTER_TABLE) and _has_rows(f"SELECT 1 FROM {ROSTER_TABLE} LIMIT 1"):
        raise RuntimeError("c201 downgrade refused: club roster membership exists")
    if table_exists("player_suppressions") and column_exists("player_suppressions", "local_player_id"):
        if _has_rows("SELECT 1 FROM player_suppressions WHERE local_player_id IS NOT NULL LIMIT 1"):
            raise RuntimeError("c201 downgrade refused: local-player suppression history exists")
    if table_exists("video_matches") and column_exists("video_matches", "club_program_id"):
        if _has_rows("SELECT 1 FROM video_matches WHERE club_program_id IS NOT NULL LIMIT 1"):
            raise RuntimeError("c201 downgrade refused: club-owned video matches exist")

    if table_exists("player_suppressions") and column_exists("player_suppressions", "local_player_id"):
        if index_exists("uq_player_suppressions_open_local_player"):
            op.drop_index("uq_player_suppressions_open_local_player", table_name="player_suppressions")
        if index_exists("uq_player_suppressions_open_player"):
            op.drop_index("uq_player_suppressions_open_player", table_name="player_suppressions")
        if _constraint_exists("player_suppressions", "ck_player_suppressions_subject_xor"):
            op.drop_constraint(
                "ck_player_suppressions_subject_xor",
                "player_suppressions",
                type_="check",
            )
        op.drop_column("player_suppressions", "local_player_id")
        op.alter_column("player_suppressions", "player_api_id", existing_type=sa.Integer(), nullable=False)
        create_index_safe(
            "uq_player_suppressions_open_player",
            "player_suppressions",
            ["player_api_id"],
            unique=True,
            postgresql_where=sa.text("status IN ('requested', 'active')"),
        )

    if table_exists("video_player_reports"):
        if index_exists("ix_video_player_reports_club_program_finalize"):
            op.drop_index("ix_video_player_reports_club_program_finalize", table_name="video_player_reports")
        for column in (
            "club_local_player_id_at_finalize",
            "club_player_api_id_at_finalize",
            "club_roster_member_id_at_finalize",
            "club_program_id_at_finalize",
        ):
            if column_exists("video_player_reports", column):
                op.drop_column("video_player_reports", column)

    if table_exists("video_roster_entries"):
        if index_exists("ix_video_roster_entries_club_roster_member_id"):
            op.drop_index(
                "ix_video_roster_entries_club_roster_member_id",
                table_name="video_roster_entries",
            )
        if column_exists("video_roster_entries", "club_roster_member_id"):
            op.drop_column("video_roster_entries", "club_roster_member_id")

    if table_exists("video_matches"):
        if index_exists("ix_video_matches_club_program_id"):
            op.drop_index("ix_video_matches_club_program_id", table_name="video_matches")
        for column in (
            "processing_requested_by_user_id",
            "processing_requested_at",
            "club_program_id",
        ):
            if column_exists("video_matches", column):
                op.drop_column("video_matches", column)
        if column_exists("video_matches", "team_id"):
            op.alter_column("video_matches", "team_id", existing_type=sa.Integer(), nullable=False)

    if table_exists(ROSTER_TABLE):
        if index_exists("ix_club_roster_members_program"):
            op.drop_index("ix_club_roster_members_program", table_name=ROSTER_TABLE)
        op.drop_table(ROSTER_TABLE)
