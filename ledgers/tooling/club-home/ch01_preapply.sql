-- ch01 pre-apply: the exact DDL of migrations/versions/ch01_club_home.py (feat/club-home-a @978e466), idempotent, one transaction.
BEGIN;
CREATE TABLE IF NOT EXISTS club_squads (
    id SERIAL PRIMARY KEY, program_id INTEGER NOT NULL REFERENCES club_programs(id) ON DELETE CASCADE,
    name VARCHAR(80) NOT NULL, kind VARCHAR(20) NOT NULL,
    age_limit SMALLINT, sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_club_squad_kind CHECK (kind IN ('first_team','reserves','age_group','other'))
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_club_squad_name ON club_squads (program_id, lower(name));
CREATE TABLE IF NOT EXISTS club_staff (
    id SERIAL PRIMARY KEY, program_id INTEGER NOT NULL REFERENCES club_programs(id) ON DELETE CASCADE,
    display_name VARCHAR(120) NOT NULL, title VARCHAR(80) NOT NULL,
    reports_to_staff_id INTEGER REFERENCES club_staff(id) ON DELETE SET NULL,
    leads_squad_id INTEGER REFERENCES club_squads(id) ON DELETE SET NULL,
    user_account_id INTEGER REFERENCES user_accounts(id), sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE club_squads ENABLE ROW LEVEL SECURITY;
ALTER TABLE club_staff ENABLE ROW LEVEL SECURITY;
ALTER TABLE club_roster_members ADD COLUMN IF NOT EXISTS squad_id INTEGER REFERENCES club_squads(id) ON DELETE SET NULL;
ALTER TABLE club_roster_members ADD COLUMN IF NOT EXISTS shirt_number SMALLINT;
DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'ck_club_roster_shirt' AND conrelid = 'club_roster_members'::regclass) THEN
    ALTER TABLE club_roster_members ADD CONSTRAINT ck_club_roster_shirt CHECK (shirt_number IS NULL OR shirt_number BETWEEN 1 AND 99);
  END IF;
END $$;
CREATE UNIQUE INDEX IF NOT EXISTS uq_club_squad_shirt ON club_roster_members (squad_id, shirt_number);
ALTER TABLE club_programs ADD COLUMN IF NOT EXISTS brand_primary_color VARCHAR(7);
ALTER TABLE club_programs ADD COLUMN IF NOT EXISTS brand_accent_color VARCHAR(7);
ALTER TABLE club_programs ADD COLUMN IF NOT EXISTS banner_url TEXT;
ALTER TABLE club_programs ADD COLUMN IF NOT EXISTS banner_updated_at TIMESTAMPTZ;
COMMIT;
