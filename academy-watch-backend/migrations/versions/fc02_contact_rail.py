"""Scout-to-player contact requests, threads, audit events, and outcomes.

Revision ID: fc02
Revises: fc01

This stacked migration intentionally chains from FC-B1's ``fc01``. PR #636
(``gf01``, funding registry) is still independently ordered: if it lands first,
re-point ``fc01`` onto ``gf01`` and retain ``fc02 -> fc01``; if this FC stack
lands first, ``gf01`` must instead be re-pointed onto ``fc02``. Never merge an
arrangement with two Alembic heads.

All DDL is guarded because production has drifted out-of-band. Every new public
table has RLS enabled in this same migration, with no permissive direct-client
policies. Flask exposes only authenticated participant projections.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, index_exists, table_exists

revision = "fc02"
down_revision = "fc01"
branch_labels = None
depends_on = None


NEW_TABLES = (
    "contact_requests",
    "contact_messages",
    "contact_audit_events",
    "contact_outcomes",
)


def upgrade():
    if not table_exists("contact_requests"):
        op.create_table(
            "contact_requests",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column("scout_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("claim_id", sa.Integer(), sa.ForeignKey("player_profile_claims.id"), nullable=False),
            sa.Column("message", sa.String(length=2000), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("responded_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint(
                "status IN ('pending','accepted','declined','withdrawn','expired')",
                name="ck_contact_requests_status",
            ),
        )
    create_index_safe(
        "uq_contact_requests_active_scout_player",
        "contact_requests",
        ["scout_user_id", "player_api_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('pending', 'accepted')"),
        sqlite_where=sa.text("status IN ('pending', 'accepted')"),
    )
    create_index_safe(
        "ix_contact_requests_scout_created",
        "contact_requests",
        ["scout_user_id", "created_at"],
    )
    create_index_safe(
        "ix_contact_requests_claim_created",
        "contact_requests",
        ["claim_id", "created_at"],
    )
    create_index_safe(
        "ix_contact_requests_player_created",
        "contact_requests",
        ["player_api_id", "created_at"],
    )
    create_index_safe(
        "ix_contact_requests_status_expires",
        "contact_requests",
        ["status", "expires_at"],
    )

    if not table_exists("contact_messages"):
        op.create_table(
            "contact_messages",
            sa.Column("id", sa.String(length=36), primary_key=True),
            sa.Column(
                "contact_request_id",
                sa.String(length=36),
                sa.ForeignKey("contact_requests.id"),
                nullable=False,
            ),
            sa.Column("sender_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("body", sa.String(length=2000), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    create_index_safe(
        "ix_contact_messages_request_created",
        "contact_messages",
        ["contact_request_id", "created_at"],
    )

    if not table_exists("contact_audit_events"):
        op.create_table(
            "contact_audit_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "contact_request_id",
                sa.String(length=36),
                sa.ForeignKey("contact_requests.id"),
                nullable=False,
            ),
            sa.Column("actor_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=True),
            sa.Column("event_type", sa.String(length=30), nullable=False),
            sa.Column("metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint(
                "event_type IN "
                "('created','accepted','declined','withdrawn','expired','message_sent','outcome_reported')",
                name="ck_contact_audit_events_type",
            ),
        )
    create_index_safe(
        "ix_contact_audit_events_request_created",
        "contact_audit_events",
        ["contact_request_id", "created_at"],
    )

    if not table_exists("contact_outcomes"):
        op.create_table(
            "contact_outcomes",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "contact_request_id",
                sa.String(length=36),
                sa.ForeignKey("contact_requests.id"),
                nullable=False,
            ),
            sa.Column("stage", sa.String(length=30), nullable=False),
            sa.Column("reported_by_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("notes", sa.String(length=2000), nullable=True),
            sa.Column("occurred_at", sa.DateTime(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint(
                "stage IN ('contacted','trial_scheduled','trial_completed','signed','no_fit')",
                name="ck_contact_outcomes_stage",
            ),
        )
    create_index_safe(
        "ix_contact_outcomes_request_created",
        "contact_outcomes",
        ["contact_request_id", "created_at"],
    )
    create_index_safe(
        "ix_contact_outcomes_request_occurred",
        "contact_outcomes",
        ["contact_request_id", "occurred_at"],
    )

    for table_name in NEW_TABLES:
        # Idempotent and intentionally policy-free: direct/public roles see no
        # rows. Participant access is enforced by the Flask contact blueprint.
        op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    indexes = (
        ("ix_contact_outcomes_request_occurred", "contact_outcomes"),
        ("ix_contact_outcomes_request_created", "contact_outcomes"),
        ("ix_contact_audit_events_request_created", "contact_audit_events"),
        ("ix_contact_messages_request_created", "contact_messages"),
        ("ix_contact_requests_status_expires", "contact_requests"),
        ("ix_contact_requests_player_created", "contact_requests"),
        ("ix_contact_requests_claim_created", "contact_requests"),
        ("ix_contact_requests_scout_created", "contact_requests"),
        ("uq_contact_requests_active_scout_player", "contact_requests"),
    )
    for index_name, table_name in indexes:
        if index_exists(index_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name in reversed(NEW_TABLES):
        if table_exists(table_name):
            op.drop_table(table_name)
