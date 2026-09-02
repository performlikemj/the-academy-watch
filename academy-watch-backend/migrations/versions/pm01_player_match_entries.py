"""Add the player match-entry grain and showcase moderation audit events.

Revision ID: pm01
Revises: lp01
Create Date: 2026-09-02

All DDL is guarded because production is pre-applied through the pooler and may
be partially present when Alembic advances. The two new public tables are RLS
enabled without permissive policies, so direct/public clients remain denied.
Downgrade refuses to discard append-only moderation history.
"""

import logging

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import column_exists, create_index_safe, index_exists, table_exists

revision = "pm01"
down_revision = "lp01"
branch_labels = None
depends_on = None

logger = logging.getLogger(__name__)

NEW_TABLES = ("player_match_entries", "showcase_moderation_events")
LOCAL_PLAYER_API_INDEX = "ux_local_players_api_player_id"


def _local_player_api_id_duplicates_exist() -> bool:
    return (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM local_players "
                "WHERE api_player_id IS NOT NULL "
                "GROUP BY api_player_id HAVING COUNT(*) > 1 LIMIT 1"
            )
        )
        .first()
        is not None
    )


def _moderation_history_exists() -> bool:
    return bool(op.get_bind().execute(sa.text('SELECT EXISTS (SELECT 1 FROM "showcase_moderation_events")')).scalar())


def upgrade():
    if not table_exists("player_match_entries"):
        op.create_table(
            "player_match_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("season", sa.Integer(), nullable=False),
            sa.Column("source", sa.String(length=16), nullable=False),
            sa.Column("status", sa.String(length=16), nullable=False),
            sa.Column(
                "reported_by_user_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id"),
                nullable=False,
            ),
            sa.Column(
                "club_program_id",
                sa.Integer(),
                sa.ForeignKey("club_programs.id"),
                nullable=True,
            ),
            sa.Column("match_date", sa.Date(), nullable=False),
            sa.Column("competition", sa.String(length=120), nullable=True),
            sa.Column("opponent", sa.String(length=120), nullable=False),
            sa.Column("home_away", sa.String(length=8), nullable=False),
            sa.Column("result_for", sa.Integer(), nullable=True),
            sa.Column("result_against", sa.Integer(), nullable=True),
            sa.Column("minutes", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("goals", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("assists", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("yellows", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("reds", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("saves", sa.Integer(), nullable=True),
            sa.Column("goals_conceded", sa.Integer(), nullable=True),
            sa.Column("note", sa.String(length=500), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint("source IN ('self','club')", name="ck_player_match_entries_source"),
            sa.CheckConstraint(
                "status IN ('self_reported','club_confirmed','disputed')",
                name="ck_player_match_entries_status",
            ),
            sa.CheckConstraint(
                "home_away IN ('home','away','neutral')",
                name="ck_player_match_entries_home_away",
            ),
            sa.CheckConstraint("minutes BETWEEN 0 AND 130", name="ck_player_match_entries_minutes"),
            sa.CheckConstraint(
                "goals BETWEEN 0 AND 20 AND assists BETWEEN 0 AND 20 "
                "AND yellows BETWEEN 0 AND 20 AND reds BETWEEN 0 AND 20",
                name="ck_player_match_entries_counts",
            ),
            sa.CheckConstraint(
                "(result_for IS NULL OR result_for BETWEEN 0 AND 20) "
                "AND (result_against IS NULL OR result_against BETWEEN 0 AND 20) "
                "AND (saves IS NULL OR saves BETWEEN 0 AND 20) "
                "AND (goals_conceded IS NULL OR goals_conceded BETWEEN 0 AND 20)",
                name="ck_player_match_entries_optional_counts",
            ),
            sa.UniqueConstraint(
                "player_api_id",
                "match_date",
                "opponent",
                "source",
                "reported_by_user_id",
                name="uq_player_match_entries_identity",
            ),
        )
    create_index_safe(
        "ix_player_match_entries_player_season",
        "player_match_entries",
        ["player_api_id", "season"],
    )
    create_index_safe(
        "ix_player_match_entries_club_program",
        "player_match_entries",
        ["club_program_id"],
    )

    if not table_exists("showcase_moderation_events"):
        op.create_table(
            "showcase_moderation_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "user_account_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id"),
                nullable=True,
            ),
            sa.Column("target_kind", sa.String(length=32), nullable=False),
            sa.Column("target_id", sa.Integer(), nullable=False),
            sa.Column("action", sa.String(length=32), nullable=False),
            sa.Column("actor_email", sa.String(length=255), nullable=True),
            sa.Column("metadata", sa.JSON(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.CheckConstraint(
                "action IN ('approved','rejected','revoked','suppressed')",
                name="ck_showcase_moderation_events_action",
            ),
        )
    create_index_safe(
        "ix_showcase_moderation_events_user_created",
        "showcase_moderation_events",
        ["user_account_id", "created_at"],
    )

    if (
        table_exists("local_players")
        and column_exists("local_players", "api_player_id")
        and not index_exists(LOCAL_PLAYER_API_INDEX)
    ):
        if _local_player_api_id_duplicates_exist():
            logger.warning(
                "Skipping %s: local_players contains duplicate non-null api_player_id values",
                LOCAL_PLAYER_API_INDEX,
            )
        else:
            predicate = sa.text("api_player_id IS NOT NULL")
            op.create_index(
                LOCAL_PLAYER_API_INDEX,
                "local_players",
                ["api_player_id"],
                unique=True,
                postgresql_where=predicate,
                sqlite_where=predicate,
            )

    for table_name in NEW_TABLES:
        op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    if table_exists("showcase_moderation_events") and _moderation_history_exists():
        raise RuntimeError("pm01 downgrade refused: showcase moderation history exists")

    if index_exists(LOCAL_PLAYER_API_INDEX):
        op.drop_index(LOCAL_PLAYER_API_INDEX, table_name="local_players")

    for table_name in reversed(NEW_TABLES):
        if table_exists(table_name):
            op.drop_table(table_name)
