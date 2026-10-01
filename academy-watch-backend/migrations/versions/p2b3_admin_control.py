"""Dark admin control room, standing, cases and cash/deployment projections.

Revision ID: p2b3
Revises: p2b2
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import add_column_safe, table_exists

revision = "p2b3"
down_revision = "p2b2"
branch_labels = None
depends_on = None

TABLES = {
    "safeguarding_cases": """CREATE TABLE public.safeguarding_cases (
        id SERIAL PRIMARY KEY,
        report_id INTEGER UNIQUE REFERENCES content_reports(id) ON DELETE SET NULL,
        suppression_id INTEGER UNIQUE REFERENCES player_suppressions(id) ON DELETE SET NULL,
        target_type VARCHAR(40) NOT NULL, target_id VARCHAR(200) NOT NULL,
        status VARCHAR(20) NOT NULL DEFAULT 'open', received_at TIMESTAMP NOT NULL DEFAULT now(),
        first_action_due_at TIMESTAMP NOT NULL, first_action_at TIMESTAMP, closed_at TIMESTAMP,
        resolver_email VARCHAR(254), version INTEGER NOT NULL DEFAULT 1,
        held_program_id INTEGER REFERENCES club_programs(id) ON DELETE SET NULL,
        owned_suppression_id INTEGER REFERENCES player_suppressions(id) ON DELETE SET NULL,
        notification_state VARCHAR(30) NOT NULL DEFAULT 'none',
        CONSTRAINT ck_safeguarding_case_status CHECK(status IN ('open','investigating','closed'))
    )""",
    "safeguarding_case_events": """CREATE TABLE public.safeguarding_case_events (
        id SERIAL PRIMARY KEY, case_id INTEGER NOT NULL REFERENCES safeguarding_cases(id) ON DELETE CASCADE,
        action VARCHAR(40) NOT NULL, actor_email VARCHAR(254) NOT NULL, reason VARCHAR(2000) NOT NULL,
        created_at TIMESTAMP NOT NULL DEFAULT now()
    )""",
    "billing_cash_events": """CREATE TABLE public.billing_cash_events (
        id SERIAL PRIMARY KEY, source_key VARCHAR(255) NOT NULL UNIQUE, stripe_event_id VARCHAR(255) NOT NULL,
        kind VARCHAR(20) NOT NULL, amount_cents INTEGER NOT NULL, currency VARCHAR(3) NOT NULL,
        occurred_at TIMESTAMP NOT NULL, product_code VARCHAR(40) NOT NULL,
        scope_type VARCHAR(20), scope_id INTEGER,
        purchaser_user_id INTEGER REFERENCES user_accounts(id) ON DELETE SET NULL,
        payment_intent_id VARCHAR(255), invoice_id VARCHAR(255),
        CONSTRAINT ck_billing_cash_events_kind CHECK(kind IN ('receipt','refund')),
        CONSTRAINT ck_billing_cash_events_amount CHECK(amount_cents >= 0)
    )""",
    "business_deployment_states": """CREATE TABLE public.business_deployment_states (
        id SERIAL PRIMARY KEY, deployment_id VARCHAR(200) NOT NULL UNIQUE,
        api_football_frozen BOOLEAN NOT NULL, newsletters_configured_frozen BOOLEAN NOT NULL,
        newsletters_effective_frozen BOOLEAN NOT NULL, observed_at TIMESTAMP NOT NULL DEFAULT now()
    )""",
}

EVENT_GUARD = """
CREATE OR REPLACE FUNCTION public.p2b3_guard_case_events() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF TG_OP='UPDATE' AND OLD.actor_email <> 'Account deleted'
 AND NEW.actor_email='Account deleted' AND NEW.reason='[redacted]'
 AND (to_jsonb(NEW)-'actor_email'-'reason')=(to_jsonb(OLD)-'actor_email'-'reason') THEN RETURN NEW; END IF;
 RAISE EXCEPTION 'safeguarding_case_events is append-only';
END $$;
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='p2b3_case_events_guard'
 AND tgrelid='public.safeguarding_case_events'::regclass) THEN
 CREATE TRIGGER p2b3_case_events_guard BEFORE UPDATE OR DELETE ON public.safeguarding_case_events
 FOR EACH ROW EXECUTE FUNCTION public.p2b3_guard_case_events(); END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_trigger WHERE tgname='p2b3_case_events_truncate_guard'
 AND tgrelid='public.safeguarding_case_events'::regclass) THEN
 CREATE TRIGGER p2b3_case_events_truncate_guard BEFORE TRUNCATE ON public.safeguarding_case_events
 FOR EACH STATEMENT EXECUTE FUNCTION public.p2b3_guard_case_events(); END IF;
END $$;
"""


def upgrade():
    for column in (
        sa.Column("account_status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("auth_epoch", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("suspended_at", sa.DateTime()),
        sa.Column("suspended_by", sa.String(254)),
        sa.Column("suspension_reason", sa.String(2000)),
    ):
        add_column_safe("user_accounts", column)
    for table, ddl in TABLES.items():
        if not table_exists(table):
            op.execute(ddl)
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    for sql in (
        "CREATE INDEX IF NOT EXISTS ix_safeguarding_cases_due ON safeguarding_cases(status, first_action_due_at,id)",
        "CREATE INDEX IF NOT EXISTS ix_safeguarding_case_events_case_id ON safeguarding_case_events(case_id)",
        "CREATE INDEX IF NOT EXISTS ix_billing_cash_events_occurred_at ON billing_cash_events(occurred_at)",
        "CREATE INDEX IF NOT EXISTS ix_billing_cash_events_payment_intent_id ON billing_cash_events(payment_intent_id)",
    ):
        op.execute(sql)
    # Reapplication-safe import; never fabricate a first-action timestamp for old reports.
    op.execute("""INSERT INTO safeguarding_cases(report_id,target_type,target_id,status,received_at,first_action_due_at,closed_at)
        SELECT id,subject_type,subject_id,CASE WHEN status IN ('resolved','dismissed') THEN 'closed' ELSE 'open' END,
        created_at,created_at + interval '24 hours',resolved_at FROM content_reports
        ON CONFLICT(report_id) DO NOTHING""")
    op.execute("""INSERT INTO safeguarding_cases(suppression_id,target_type,target_id,status,received_at,first_action_due_at,first_action_at,closed_at)
        SELECT id,'player_profile',COALESCE(player_api_id,-local_player_id)::text,
        CASE WHEN status IN ('lifted','rejected') THEN 'closed' WHEN status='active' THEN 'investigating' ELSE 'open' END,
        created_at,created_at + interval '24 hours',decided_at,
        CASE WHEN status IN ('lifted','rejected') THEN decided_at END FROM player_suppressions
        ON CONFLICT(suppression_id) DO NOTHING""")
    op.execute(EVENT_GUARD)


def downgrade():
    if (
        op.get_bind()
        .execute(
            sa.text("SELECT EXISTS(SELECT 1 FROM user_accounts WHERE account_status <> 'active' OR auth_epoch <> 0)")
        )
        .scalar()
    ):
        raise RuntimeError("Preserve account standing; refusing downgrade")
    for table in TABLES:
        if table_exists(table) and op.get_bind().execute(sa.text(f"SELECT EXISTS(SELECT 1 FROM {table})")).scalar():
            raise RuntimeError(f"Preserve retained {table}; refusing downgrade")
    for table in reversed(TABLES):
        if table_exists(table):
            op.drop_table(table)
    op.execute("DROP FUNCTION IF EXISTS public.p2b3_guard_case_events()")
    from migrations._migration_helpers import column_exists

    for column in ("suspension_reason", "suspended_by", "suspended_at", "auth_epoch", "account_status"):
        if column_exists("user_accounts", column):
            op.drop_column("user_accounts", column)
