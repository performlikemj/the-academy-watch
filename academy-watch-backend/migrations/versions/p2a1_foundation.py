"""Phase 2 foundation. Guarded DDL; private tables with RLS."""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, table_exists

revision = "p2a1"
down_revision = "fl01"
branch_labels = None
depends_on = None

AUDIT_TRIGGER_FUNCTION = """
CREATE OR REPLACE FUNCTION public.p2a1_guard_admin_action_events() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.actor_email = 'Account deleted'
       AND NEW.reason = '[redacted]' AND NEW.event_metadata::jsonb = '{}'::jsonb
       AND NEW.id = OLD.id AND NEW.action = OLD.action
       AND NEW.target_type = OLD.target_type AND NEW.target_id = OLD.target_id
       AND NEW.created_at = OLD.created_at THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'admin_action_events is append-only (identity erasure only)';
END;
$$;
"""
AUDIT_TRIGGER = """
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname = 'p2a1_admin_action_events_append_only'
                   AND tgrelid = 'public.admin_action_events'::regclass) THEN
        CREATE TRIGGER p2a1_admin_action_events_append_only BEFORE UPDATE OR DELETE
        ON public.admin_action_events FOR EACH ROW EXECUTE FUNCTION public.p2a1_guard_admin_action_events();
    END IF;
END $$;
"""


def upgrade():
    if not table_exists("notification_outbox"):
        op.create_table(
            "notification_outbox",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("dedupe_key", sa.String(200), nullable=False),
            sa.Column("recipient_user_id", sa.Integer(), sa.ForeignKey("user_accounts.id"), nullable=False),
            sa.Column("event_type", sa.String(80), nullable=False),
            sa.Column("entity_type", sa.String(80), nullable=False),
            sa.Column("entity_id", sa.String(80), nullable=False),
            sa.Column("template", sa.String(80), nullable=False),
            sa.Column("payload", sa.JSON(), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("provider", sa.String(40)),
            sa.Column("provider_message_id", sa.String(254)),
            sa.Column("last_error", sa.String(80)),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("sent_at", sa.DateTime(timezone=True)),
            sa.CheckConstraint("attempts >= 0", name="ck_notification_outbox_attempts"),
            sa.CheckConstraint(
                "status IN ('pending', 'retry', 'sent', 'cancelled', 'failed')", name="ck_notification_outbox_status"
            ),
        )
    create_index_safe("uq_notification_outbox_dedupe", "notification_outbox", ["dedupe_key"], unique=True)
    create_index_safe("ix_notification_outbox_due", "notification_outbox", ["status", "next_attempt_at", "id"])
    if not table_exists("admin_action_events"):
        op.create_table(
            "admin_action_events",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("actor_email", sa.String(254), nullable=False),
            sa.Column("action", sa.String(80), nullable=False),
            sa.Column("target_type", sa.String(80), nullable=False),
            sa.Column("target_id", sa.String(80), nullable=False),
            sa.Column("reason", sa.String(2000), nullable=False),
            sa.Column("event_metadata", sa.JSON(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
    create_index_safe(
        "ix_admin_action_events_target", "admin_action_events", ["target_type", "target_id", "created_at"]
    )
    op.execute("ALTER TABLE public.notification_outbox ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.admin_action_events ENABLE ROW LEVEL SECURITY")
    op.execute(AUDIT_TRIGGER_FUNCTION)
    op.execute(AUDIT_TRIGGER)


def downgrade():
    for table in ("admin_action_events", "notification_outbox"):
        if table_exists(table):
            op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS public.p2a1_guard_admin_action_events()")
