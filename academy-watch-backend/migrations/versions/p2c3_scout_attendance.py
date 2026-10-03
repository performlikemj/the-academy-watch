"""Scout attendance separate from applicants. Guarded DDL and RLS.

Revision ID: p2c3
Revises: p2c2
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, table_exists

revision = "p2c3"
down_revision = "p2c2"
branch_labels = None
depends_on = None

TABLE_SQL = """CREATE TABLE public.scout_attendance_requests (
 id VARCHAR(36) PRIMARY KEY,
 opportunity_id VARCHAR(36) NOT NULL REFERENCES club_opportunities(id) ON DELETE CASCADE,
 program_id INTEGER NOT NULL REFERENCES club_programs(id),
 scout_user_id INTEGER NOT NULL REFERENCES user_accounts(id) ON DELETE CASCADE,
 note VARCHAR(500) NOT NULL DEFAULT '', status VARCHAR(20) NOT NULL DEFAULT 'pending',
 version INTEGER NOT NULL DEFAULT 1,
 decision_user_id INTEGER REFERENCES user_accounts(id) ON DELETE SET NULL,
 arrival_instructions VARCHAR(500) NOT NULL DEFAULT '',
 created_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
 updated_at TIMESTAMP NOT NULL DEFAULT (now() AT TIME ZONE 'utc'), retention_expires_at TIMESTAMP NOT NULL,
 CONSTRAINT uq_scout_attendance_subject UNIQUE(opportunity_id, scout_user_id),
 CONSTRAINT ck_scout_attendance_status CHECK(status IN ('pending','accepted','declined','withdrawn')),
 CONSTRAINT ck_scout_attendance_version CHECK(version > 0)
)"""


def upgrade():
    if not table_exists("scout_attendance_requests"):
        op.execute(TABLE_SQL)
    op.execute(
        "ALTER TABLE public.scout_attendance_requests ADD COLUMN IF NOT EXISTS request_count INTEGER NOT NULL DEFAULT 1;\nALTER TABLE public.scout_attendance_requests DROP CONSTRAINT IF EXISTS ck_scout_attendance_status;\nALTER TABLE public.scout_attendance_requests ADD CONSTRAINT ck_scout_attendance_status CHECK(status IN ('pending','accepted','declined','withdrawn','expired','revoked','cancelled'));\nDO $retry$ BEGIN\nIF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.scout_attendance_requests'::regclass AND conname='ck_scout_attendance_request_count') THEN\nALTER TABLE public.scout_attendance_requests ADD CONSTRAINT ck_scout_attendance_request_count CHECK(request_count IN (1,2));\nEND IF;\nEND $retry$;\n"
    )
    op.execute("ALTER TABLE public.scout_attendance_requests ENABLE ROW LEVEL SECURITY")
    create_index_safe("ix_scout_attendance_inbox", "scout_attendance_requests", ["program_id", "status", "created_at"])
    create_index_safe("ix_scout_attendance_scout", "scout_attendance_requests", ["scout_user_id", "id"])
    create_index_safe("ix_scout_attendance_retention", "scout_attendance_requests", ["retention_expires_at"])


def downgrade():
    if table_exists("scout_attendance_requests"):
        if op.get_bind().execute(sa.text("SELECT 1 FROM scout_attendance_requests LIMIT 1")).first():
            raise RuntimeError("Refusing to drop retained scout attendance requests")
        op.drop_table("scout_attendance_requests")
