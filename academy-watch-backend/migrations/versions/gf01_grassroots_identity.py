"""Grassroots league registry, club claims, and verification identity.

Revision ID: gf01
Revises: sea01

IMPORTANT: ``sea01`` was the sole head on refreshed ``origin/main`` when this
migration was authored. If another head lands first, update ``down_revision``
before merge. Never allow a migration fork.

All DDL is guarded because production has drifted out-of-band. Every new public
schema table has RLS enabled in this same migration. No permissive policies are
created: evidence, grants, Connect telemetry, and audit data are default-deny to
direct/public clients and are exposed only through narrow server serializers.
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

revision = "gf01"
down_revision = "tf02"
branch_labels = None
depends_on = None


NEW_TABLES = (
    "funding_leagues",
    "club_programs",
    "club_program_claims",
    "club_claim_evidence",
    "club_program_managers",
    "club_program_profile_revisions",
    "club_connect_accounts",
    "funding_admin_events",
)


def upgrade():
    if not table_exists("funding_leagues"):
        op.create_table(
            "funding_leagues",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(length=160), nullable=False),
            sa.Column("country", sa.String(length=80), nullable=False),
            sa.Column("region", sa.String(length=120), nullable=False),
            sa.Column("level", sa.String(length=30), nullable=False),
            sa.Column("age_bands", sa.JSON(), nullable=False),
            sa.Column("gender_program", sa.String(length=10), nullable=False),
            sa.Column("season_calendar", sa.String(length=20), nullable=False),
            sa.Column("data_tier", sa.String(length=20), nullable=False),
            sa.Column("league_api_id", sa.Integer(), nullable=True),
            sa.Column("existing_league_id", sa.Integer(), sa.ForeignKey("leagues.id"), nullable=True),
            sa.Column("registry_status", sa.String(length=20), nullable=False, server_default="approved"),
            sa.Column("admission_state", sa.String(length=20), nullable=False, server_default="waitlisted"),
            sa.Column("proposed_by_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=True),
            sa.Column("reviewed_by", sa.String(length=200), nullable=True),
            sa.Column("review_reason", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.CheckConstraint(
                "level IN ('pro_academy','youth_national','youth_regional','recreational')",
                name="ck_funding_leagues_level",
            ),
            sa.CheckConstraint("gender_program IN ('boys','girls','both')", name="ck_funding_leagues_gender"),
            sa.CheckConstraint(
                "season_calendar IN ('aug_may','calendar_year','fall_spring')",
                name="ck_funding_leagues_calendar",
            ),
            sa.CheckConstraint(
                "data_tier IN ('api_football','film_room','self_reported')",
                name="ck_funding_leagues_data_tier",
            ),
            sa.CheckConstraint(
                "registry_status IN ('proposed','approved','rejected')",
                name="ck_funding_leagues_registry_status",
            ),
            sa.CheckConstraint(
                "admission_state IN ('open','waitlisted','closed')",
                name="ck_funding_leagues_admission_state",
            ),
            sa.UniqueConstraint("name", "country", "region", name="uq_funding_league_identity"),
            sa.UniqueConstraint("league_api_id", name="uq_funding_league_api_id"),
            sa.UniqueConstraint("existing_league_id", name="uq_funding_league_bridge"),
        )
    create_index_safe(
        "ix_funding_leagues_admission",
        "funding_leagues",
        ["registry_status", "admission_state"],
    )
    create_index_safe("ix_funding_leagues_location", "funding_leagues", ["country", "region"])

    if not table_exists("club_programs"):
        op.create_table(
            "club_programs",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("funding_league_id", sa.Integer(), sa.ForeignKey("funding_leagues.id"), nullable=False),
            sa.Column("team_api_id", sa.Integer(), sa.ForeignKey("team_profiles.team_id"), nullable=True),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("legal_name", sa.String(length=220), nullable=False),
            sa.Column("slug", sa.String(length=200), nullable=False),
            sa.Column("crest_url", sa.String(length=500), nullable=True),
            sa.Column("country", sa.String(length=80), nullable=False),
            sa.Column("region", sa.String(length=120), nullable=False),
            sa.Column("city", sa.String(length=120), nullable=True),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="USD"),
            sa.Column("provenance_tier", sa.String(length=30), nullable=False, server_default="self_reported"),
            sa.Column("platform_status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("donations_enabled", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("emergency_hidden", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("approved_profile_revision_id", sa.Integer(), nullable=True),
            sa.Column("reviewed_by", sa.String(length=200), nullable=True),
            sa.Column("review_reason", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("verified_at", sa.DateTime(), nullable=True),
            sa.Column("next_review_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.CheckConstraint(
                "provenance_tier IN ('provider_covered','film_room_verified','self_reported')",
                name="ck_club_programs_provenance",
            ),
            sa.CheckConstraint(
                "platform_status IN ('pending','approved','rejected','suspended')",
                name="ck_club_programs_status",
            ),
            sa.UniqueConstraint("slug", name="uq_club_programs_slug"),
            sa.UniqueConstraint("team_api_id", name="uq_club_programs_team_api_id"),
        )
    create_index_safe("ix_club_programs_league", "club_programs", ["funding_league_id"])
    create_index_safe("ix_club_programs_location", "club_programs", ["country", "region"])
    create_index_safe("ix_club_programs_status", "club_programs", ["platform_status"])

    if not table_exists("club_program_claims"):
        op.create_table(
            "club_program_claims",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "program_id",
                sa.Integer(),
                sa.ForeignKey("club_programs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("user_account_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("relationship_type", sa.String(length=30), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("applicant_message", sa.Text(), nullable=True),
            sa.Column("reviewed_by", sa.String(length=200), nullable=True),
            sa.Column("review_reason", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.CheckConstraint(
                "status IN ('pending','approved','rejected','revoked')",
                name="ck_club_program_claims_status",
            ),
            sa.UniqueConstraint("program_id", "user_account_id", name="uq_club_claim_program_user"),
        )
    create_index_safe("ix_club_claims_status", "club_program_claims", ["status", "created_at"])
    create_index_safe("ix_club_claims_user", "club_program_claims", ["user_account_id"])

    if not table_exists("club_claim_evidence"):
        op.create_table(
            "club_claim_evidence",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "claim_id",
                sa.Integer(),
                sa.ForeignKey("club_program_claims.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("adult_authority_attested", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("official_email", sa.Text(), nullable=True),
            sa.Column("authorization_method", sa.String(length=40), nullable=False),
            sa.Column("authorization_reference", sa.Text(), nullable=True),
            sa.Column("organization_form", sa.String(length=40), nullable=False),
            sa.Column("registration_reference", sa.Text(), nullable=False),
            sa.Column("official_contact_name", sa.Text(), nullable=False),
            sa.Column("official_contact_reference", sa.Text(), nullable=False),
            sa.Column("safeguarding_contact_email", sa.Text(), nullable=False),
            sa.Column("safeguarding_policy_url", sa.Text(), nullable=True),
            sa.Column("safeguarding_policy_attested", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("eligible_organization_attested", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("payout_control_attested", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("evidence_notes", sa.Text(), nullable=True),
            sa.Column("retention_expires_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("claim_id", name="uq_club_claim_evidence_claim"),
        )
    create_index_safe("ix_club_claim_evidence_retention", "club_claim_evidence", ["retention_expires_at"])

    if not table_exists("club_program_managers"):
        op.create_table(
            "club_program_managers",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "program_id",
                sa.Integer(),
                sa.ForeignKey("club_programs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("user_account_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("source_claim_id", sa.Integer(), sa.ForeignKey("club_program_claims.id"), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("granted_by", sa.String(length=200), nullable=False),
            sa.Column("granted_at", sa.DateTime(), nullable=True),
            sa.Column("revoked_by", sa.String(length=200), nullable=True),
            sa.Column("revoked_reason", sa.Text(), nullable=True),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.CheckConstraint("status IN ('active','revoked')", name="ck_club_program_managers_status"),
            sa.UniqueConstraint("program_id", "user_account_id", name="uq_club_manager_program_user"),
        )
    create_index_safe(
        "ix_club_managers_user_status",
        "club_program_managers",
        ["user_account_id", "status"],
    )

    if not table_exists("club_program_profile_revisions"):
        op.create_table(
            "club_program_profile_revisions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "program_id",
                sa.Integer(),
                sa.ForeignKey("club_programs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("submitted_by_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
            sa.Column("summary", sa.Text(), nullable=True),
            sa.Column("age_groups", sa.JSON(), nullable=False),
            sa.Column("activities", sa.JSON(), nullable=False),
            sa.Column("funding_purpose", sa.Text(), nullable=True),
            sa.Column("official_url", sa.String(length=500), nullable=True),
            sa.Column("safeguarding_url", sa.String(length=500), nullable=True),
            sa.Column("media_urls", sa.JSON(), nullable=False),
            sa.Column("reviewed_by", sa.String(length=200), nullable=True),
            sa.Column("review_reason", sa.Text(), nullable=True),
            sa.Column("reviewed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.CheckConstraint(
                "status IN ('pending','approved','rejected','withdrawn')",
                name="ck_club_program_revisions_status",
            ),
        )
    create_index_safe(
        "ix_club_program_revisions_program",
        "club_program_profile_revisions",
        ["program_id", "created_at"],
    )
    op.execute(
        sa.text(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'fk_club_programs_approved_revision'
                ) THEN
                    ALTER TABLE club_programs
                    ADD CONSTRAINT fk_club_programs_approved_revision
                    FOREIGN KEY (approved_profile_revision_id)
                    REFERENCES club_program_profile_revisions(id);
                END IF;
            END
            $$;
            """
        )
    )

    if not table_exists("club_connect_accounts"):
        op.create_table(
            "club_connect_accounts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "program_id",
                sa.Integer(),
                sa.ForeignKey("club_programs.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("stripe_account_id", sa.String(length=255), nullable=True),
            sa.Column("account_type", sa.String(length=20), nullable=False, server_default="express"),
            sa.Column("country", sa.String(length=2), nullable=False, server_default="US"),
            sa.Column("business_type", sa.String(length=30), nullable=False, server_default="company"),
            sa.Column("livemode", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("transfers_active", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("details_submitted", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("payouts_enabled", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("charges_enabled", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("requirements_due", sa.JSON(), nullable=False),
            sa.Column("disabled_reason", sa.String(length=255), nullable=True),
            sa.Column("onboarding_url", sa.String(length=1000), nullable=True),
            sa.Column("onboarding_expires_at", sa.DateTime(), nullable=True),
            sa.Column("deauthorized_at", sa.DateTime(), nullable=True),
            sa.Column("last_synced_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("program_id", name="uq_club_connect_program"),
            sa.UniqueConstraint("stripe_account_id", name="uq_club_connect_stripe_account"),
        )
    create_index_safe(
        "ix_club_connect_readiness",
        "club_connect_accounts",
        ["transfers_active", "payouts_enabled"],
    )

    if not table_exists("funding_admin_events"):
        op.create_table(
            "funding_admin_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("actor_email", sa.String(length=254), nullable=False),
            sa.Column("action", sa.String(length=80), nullable=False),
            sa.Column("target_type", sa.String(length=40), nullable=False),
            sa.Column("target_id", sa.Integer(), nullable=False),
            sa.Column("reason", sa.Text(), nullable=False),
            sa.Column("event_metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    create_index_safe(
        "ix_funding_admin_events_target",
        "funding_admin_events",
        ["target_type", "target_id"],
    )
    create_index_safe("ix_funding_admin_events_created", "funding_admin_events", ["created_at"])

    add_column_safe(
        "follows",
        sa.Column("notify_when_fundable", sa.Boolean(), nullable=False, server_default="false"),
    )

    for table_name in NEW_TABLES:
        # Idempotent and intentionally policy-free: direct/public roles see no
        # rows. Flask publishes only explicitly serialized fields.
        op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))


def downgrade():
    if column_exists("follows", "notify_when_fundable"):
        op.drop_column("follows", "notify_when_fundable")

    if table_exists("club_programs"):
        op.execute(sa.text("ALTER TABLE club_programs DROP CONSTRAINT IF EXISTS fk_club_programs_approved_revision"))

    indexes = (
        ("ix_funding_admin_events_created", "funding_admin_events"),
        ("ix_funding_admin_events_target", "funding_admin_events"),
        ("ix_club_connect_readiness", "club_connect_accounts"),
        ("ix_club_program_revisions_program", "club_program_profile_revisions"),
        ("ix_club_managers_user_status", "club_program_managers"),
        ("ix_club_claim_evidence_retention", "club_claim_evidence"),
        ("ix_club_claims_user", "club_program_claims"),
        ("ix_club_claims_status", "club_program_claims"),
        ("ix_club_programs_status", "club_programs"),
        ("ix_club_programs_location", "club_programs"),
        ("ix_club_programs_league", "club_programs"),
        ("ix_funding_leagues_location", "funding_leagues"),
        ("ix_funding_leagues_admission", "funding_leagues"),
    )
    for index_name, table_name in indexes:
        if index_exists(index_name):
            op.drop_index(index_name, table_name=table_name)

    for table_name in reversed(NEW_TABLES):
        if table_exists(table_name):
            op.drop_table(table_name)
