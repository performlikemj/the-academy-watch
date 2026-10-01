"""Club staff access: role grants, squad scope, staff invites, match squad, recording coverage.

Revision ID: p2a2
Revises: p2a1
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import add_column_safe, create_index_safe, table_exists

revision = "p2a2"
down_revision = "p2a1"
branch_labels = None
depends_on = None


def _fk_exists(table, name):
    return any(fk.get("name") == name for fk in sa.inspect(op.get_bind()).get_foreign_keys(table))


def upgrade():
    if not table_exists("club_staff_invites"):
        op.create_table(
            "club_staff_invites",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column(
                "program_id", sa.Integer(), sa.ForeignKey("club_programs.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column("email", sa.String(254), nullable=False),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("all_squads", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("squad_ids", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
            sa.Column("token_hash", sa.String(64), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("invited_by_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("accepted_at", sa.DateTime()),
            sa.Column("accepted_by_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id", ondelete="SET NULL")),
            sa.Column("revoked_at", sa.DateTime()),
            sa.Column("revoked_by_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id", ondelete="SET NULL")),
            sa.CheckConstraint("role IN ('manager','coach','analyst','viewer')", name="ck_club_staff_invites_role"),
            sa.CheckConstraint("status IN ('pending','accepted','revoked')", name="ck_club_staff_invites_status"),
            sa.UniqueConstraint("token_hash", name="uq_club_staff_invites_token_hash"),
        )
    create_index_safe("ix_club_staff_invites_program_status", "club_staff_invites", ["program_id", "status"])
    create_index_safe("ix_club_staff_invites_email", "club_staff_invites", ["email"])
    op.execute("ALTER TABLE public.club_staff_invites ENABLE ROW LEVEL SECURITY")

    if not table_exists("club_access_grants"):
        op.create_table(
            "club_access_grants",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "program_id", sa.Integer(), sa.ForeignKey("club_programs.id", ondelete="CASCADE"), nullable=False
            ),
            sa.Column(
                "user_account_id",
                sa.Integer(),
                sa.ForeignKey("user_accounts.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("role", sa.String(20), nullable=False),
            sa.Column("all_squads", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("source", sa.String(20), nullable=False, server_default="invite"),
            sa.Column("source_invite_id", sa.String(36), sa.ForeignKey("club_staff_invites.id", ondelete="SET NULL")),
            sa.Column("granted_by_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id", ondelete="SET NULL")),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("revoked_at", sa.DateTime()),
            sa.Column("revoked_by_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id", ondelete="SET NULL")),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.CheckConstraint(
                "role IN ('owner','manager','coach','analyst','viewer')", name="ck_club_access_grants_role"
            ),
            sa.CheckConstraint("status IN ('active','revoked')", name="ck_club_access_grants_status"),
            sa.UniqueConstraint("program_id", "user_account_id", name="uq_club_access_grants_program_user"),
        )
    create_index_safe("ix_club_access_grants_user_status", "club_access_grants", ["user_account_id", "status"])
    op.execute("ALTER TABLE public.club_access_grants ENABLE ROW LEVEL SECURITY")

    if not table_exists("club_access_grant_squads"):
        op.create_table(
            "club_access_grant_squads",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "grant_id",
                sa.Integer(),
                sa.ForeignKey("club_access_grants.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("squad_id", sa.Integer(), sa.ForeignKey("club_squads.id", ondelete="CASCADE"), nullable=False),
            sa.UniqueConstraint("grant_id", "squad_id", name="uq_club_access_grant_squads"),
        )
    create_index_safe("ix_club_access_grant_squads_squad_id", "club_access_grant_squads", ["squad_id"])
    op.execute("ALTER TABLE public.club_access_grant_squads ENABLE ROW LEVEL SECURITY")

    if not table_exists("video_match_coverage"):
        op.create_table(
            "video_match_coverage",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "video_match_id",
                sa.Integer(),
                sa.ForeignKey("video_matches.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("kind", sa.String(20), nullable=False),
            sa.Column("club_roster_member_id", sa.Integer(), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.CheckConstraint("kind IN ('origin','member','uncertain')", name="ck_video_match_coverage_kind"),
        )
    create_index_safe("ix_video_match_coverage_match", "video_match_coverage", ["video_match_id"])
    create_index_safe(
        "uq_video_match_coverage_entry",
        "video_match_coverage",
        ["video_match_id", "kind", "club_roster_member_id"],
        unique=True,
    )
    op.execute("ALTER TABLE public.video_match_coverage ENABLE ROW LEVEL SECURITY")

    add_column_safe("video_matches", sa.Column("scoped_ready_etag", sa.String(100), nullable=True))
    add_column_safe("video_matches", sa.Column("squad_id", sa.Integer(), nullable=True))
    if not _fk_exists("video_matches", "fk_video_matches_squad_id"):
        op.create_foreign_key(
            "fk_video_matches_squad_id", "video_matches", "club_squads", ["squad_id"], ["id"], ondelete="SET NULL"
        )
    create_index_safe("ix_video_matches_squad_id", "video_matches", ["squad_id"])


def downgrade():
    from migrations._migration_helpers import column_exists, index_exists

    if index_exists("ix_video_matches_squad_id"):
        op.drop_index("ix_video_matches_squad_id", table_name="video_matches")
    if _fk_exists("video_matches", "fk_video_matches_squad_id"):
        op.drop_constraint("fk_video_matches_squad_id", "video_matches", type_="foreignkey")
    if column_exists("video_matches", "squad_id"):
        op.drop_column("video_matches", "squad_id")
    if column_exists("video_matches", "scoped_ready_etag"):
        op.drop_column("video_matches", "scoped_ready_etag")
    for table in ("video_match_coverage", "club_access_grant_squads", "club_access_grants", "club_staff_invites"):
        if table_exists(table):
            op.drop_table(table)
