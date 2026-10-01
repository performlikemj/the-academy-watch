"""Adult opportunity recruiting; guarded DDL, RLS and append-only event history."""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, table_exists

revision = "p2b2"
down_revision = "p2b1"
branch_labels = None
depends_on = None

EVENT_GUARD = """
CREATE OR REPLACE FUNCTION public.p2b2_application_event_guard() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF current_setting('academy_watch.application_privacy', true) = 'on' THEN
        IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
        IF TG_OP = 'UPDATE' AND OLD.actor_user_id IS NOT NULL AND NEW.actor_user_id IS NULL
          AND (to_jsonb(NEW) - 'actor_user_id') = (to_jsonb(OLD) - 'actor_user_id') THEN RETURN NEW; END IF;
    END IF;
    RAISE EXCEPTION 'application_events is append-only (retention/erasure only)';
END;
$$;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'p2b2_application_events_append_only'
                   AND tgrelid = 'public.application_events'::regclass) THEN
        CREATE TRIGGER p2b2_application_events_append_only BEFORE UPDATE OR DELETE ON public.application_events
        FOR EACH ROW EXECUTE FUNCTION public.p2b2_application_event_guard();
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'p2b2_application_events_no_truncate'
                   AND tgrelid = 'public.application_events'::regclass) THEN
        CREATE TRIGGER p2b2_application_events_no_truncate BEFORE TRUNCATE ON public.application_events
        FOR EACH STATEMENT EXECUTE FUNCTION public.p2b2_application_event_guard();
    END IF;
END $$;
"""


def upgrade():
    if not table_exists("club_opportunities"):
        op.create_table(
            "club_opportunities",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("program_id", sa.Integer(), sa.ForeignKey("club_programs.id"), nullable=False),
            sa.Column("squad_id", sa.Integer(), sa.ForeignKey("club_squads.id", ondelete="SET NULL"), nullable=True),
            sa.Column(
                "creator_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True
            ),
            sa.Column("type", sa.String(length=20), nullable=False),
            sa.Column("title", sa.String(length=180), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column("instructions", sa.Text(), nullable=False),
            sa.Column("position_requirements", sa.String(length=200), nullable=False),
            sa.Column("birth_year_min", sa.Integer(), nullable=True),
            sa.Column("birth_year_max", sa.Integer(), nullable=True),
            sa.Column("gender_program", sa.String(length=20), nullable=False),
            sa.Column("starts_at", sa.DateTime(), nullable=True),
            sa.Column("ends_at", sa.DateTime(), nullable=True),
            sa.Column("timezone", sa.String(length=80), nullable=False),
            sa.Column("venue", sa.String(length=200), nullable=False),
            sa.Column("address", sa.String(length=300), nullable=False),
            sa.Column("capacity", sa.Integer(), nullable=True),
            sa.Column("closes_at", sa.DateTime(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("published_at", sa.DateTime(), nullable=True),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.CheckConstraint("capacity IS NULL OR capacity > 0", name="ck_opportunity_capacity"),
            sa.CheckConstraint("status IN ('draft','published','closed','cancelled')", name="ck_opportunity_status"),
            sa.CheckConstraint("type IN ('trial','open_session','position')", name="ck_opportunity_type"),
            sa.CheckConstraint("version > 0", name="ck_opportunity_version"),
        )
    create_index_safe("ix_opportunity_program", "club_opportunities", ["program_id", "created_at"], unique=False)
    create_index_safe("ix_opportunity_public", "club_opportunities", ["status", "closes_at", "id"], unique=False)
    op.execute("ALTER TABLE public.club_opportunities ENABLE ROW LEVEL SECURITY")
    if not table_exists("opportunity_applications"):
        op.create_table(
            "opportunity_applications",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column("opportunity_id", sa.String(length=36), sa.ForeignKey("club_opportunities.id"), nullable=False),
            sa.Column("program_id", sa.Integer(), sa.ForeignKey("club_programs.id"), nullable=False),
            sa.Column("applicant_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("applicant_kind", sa.String(length=20), nullable=False),
            sa.Column("claim_id", sa.Integer(), sa.ForeignKey("player_profile_claims.id"), nullable=False),
            sa.Column("signed_player_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("position", sa.String(length=80), nullable=False),
            sa.Column("current_club", sa.String(length=180), nullable=False),
            sa.Column("contact_consent_at", sa.DateTime(), nullable=False),
            sa.Column("submitted_at", sa.DateTime(), nullable=False),
            sa.Column("withdrawn_at", sa.DateTime(), nullable=True),
            sa.Column("retention_expires_at", sa.DateTime(), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("client_request_id", sa.String(length=36), nullable=False),
            sa.Column("request_hash", sa.String(length=64), nullable=False),
            sa.Column("trial_at", sa.DateTime(), nullable=True),
            sa.Column("trial_venue", sa.String(length=200), nullable=True),
            sa.Column("trial_instructions", sa.Text(), nullable=True),
            sa.Column("reservation_state", sa.String(length=20), nullable=False),
            sa.CheckConstraint("applicant_kind = 'adult_player'", name="ck_application_adult"),
            sa.CheckConstraint(
                "reservation_state IN ('none','pending','confirmed','declined','released')",
                name="ck_application_reservation",
            ),
            sa.CheckConstraint(
                "status IN ('new','shortlisted','invited','attended','offer','signed','rejected','withdrawn')",
                name="ck_application_status",
            ),
            sa.CheckConstraint("signed_player_id <> 0", name="ck_application_subject"),
            sa.CheckConstraint("version > 0", name="ck_application_version"),
            sa.UniqueConstraint("applicant_user_id", "client_request_id", name="uq_application_request"),
        )
    create_index_safe(
        "ix_application_applicant", "opportunity_applications", ["applicant_user_id", "submitted_at"], unique=False
    )
    create_index_safe("ix_application_retention", "opportunity_applications", ["retention_expires_at"], unique=False)
    create_index_safe(
        "uq_application_subject", "opportunity_applications", ["opportunity_id", "signed_player_id"], unique=True
    )
    op.execute("ALTER TABLE public.opportunity_applications ENABLE ROW LEVEL SECURITY")
    if not table_exists("application_events"):
        op.create_table(
            "application_events",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column(
                "application_id",
                sa.String(length=36),
                sa.ForeignKey("opportunity_applications.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "actor_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True
            ),
            sa.Column("from_state", sa.String(length=20), nullable=True),
            sa.Column("to_state", sa.String(length=20), nullable=False),
            sa.Column("reason_code", sa.String(length=40), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("application_id", "version", name="uq_application_event_version"),
        )
    op.execute("ALTER TABLE public.application_events ENABLE ROW LEVEL SECURITY")
    if not table_exists("application_notes"):
        op.create_table(
            "application_notes",
            sa.Column("id", sa.String(length=36), primary_key=True, nullable=False),
            sa.Column(
                "application_id",
                sa.String(length=36),
                sa.ForeignKey("opportunity_applications.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "author_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id", ondelete="SET NULL"), nullable=True
            ),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
    create_index_safe("ix_application_notes_application_id", "application_notes", ["application_id"], unique=False)
    op.execute("ALTER TABLE public.application_notes ENABLE ROW LEVEL SECURITY")
    op.execute(EVENT_GUARD)


def downgrade():
    for table in ("application_notes", "application_events", "opportunity_applications", "club_opportunities"):
        if table_exists(table) and op.get_bind().execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table})")).scalar():
            raise RuntimeError(f"refusing to downgrade nonempty {table}; run retention/erasure first")
    for table in ("application_notes", "application_events", "opportunity_applications", "club_opportunities"):
        if table_exists(table):
            op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS public.p2b2_application_event_guard()")
