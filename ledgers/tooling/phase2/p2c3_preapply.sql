-- C4 schema-only guarded preapply. Apply after p2c2; does not stamp Alembic.
BEGIN;
DO $c4$ BEGIN
IF to_regclass('public.scout_attendance_requests') IS NULL THEN
CREATE TABLE public.scout_attendance_requests (
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
);
END IF;
END $c4$;
ALTER TABLE public.scout_attendance_requests ADD COLUMN IF NOT EXISTS request_count INTEGER NOT NULL DEFAULT 1;
ALTER TABLE public.scout_attendance_requests DROP CONSTRAINT IF EXISTS ck_scout_attendance_status;
ALTER TABLE public.scout_attendance_requests ADD CONSTRAINT ck_scout_attendance_status CHECK(status IN ('pending','accepted','declined','withdrawn','expired','revoked','cancelled'));
DO $retry$ BEGIN
IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='public.scout_attendance_requests'::regclass AND conname='ck_scout_attendance_request_count') THEN
ALTER TABLE public.scout_attendance_requests ADD CONSTRAINT ck_scout_attendance_request_count CHECK(request_count IN (1,2));
END IF;
END $retry$;
ALTER TABLE public.scout_attendance_requests ENABLE ROW LEVEL SECURITY;
CREATE INDEX IF NOT EXISTS ix_scout_attendance_inbox ON scout_attendance_requests(program_id,status,created_at);
CREATE INDEX IF NOT EXISTS ix_scout_attendance_retention ON scout_attendance_requests(retention_expires_at);
CREATE INDEX IF NOT EXISTS ix_scout_attendance_scout ON scout_attendance_requests(scout_user_id,id);
COMMIT;
