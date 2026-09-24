"""Private club player photos, origin ownership and squad pathway.

Revision ID: ch02
Revises: ch01
"""

from alembic import op

revision = "ch02"
down_revision = "ch01"
branch_labels = None
depends_on = None

UPGRADE_SQL = """
CREATE TABLE IF NOT EXISTS club_roster_squad_history (
    id SERIAL PRIMARY KEY,
    program_id INTEGER NOT NULL REFERENCES club_programs(id) ON DELETE CASCADE,
    roster_member_id INTEGER NOT NULL REFERENCES club_roster_members(id) ON DELETE CASCADE,
    squad_id INTEGER REFERENCES club_squads(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS ix_club_roster_squad_history_member_started
    ON club_roster_squad_history (roster_member_id, started_at);
ALTER TABLE club_roster_squad_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE club_roster_members ADD COLUMN IF NOT EXISTS photo_path TEXT;
ALTER TABLE club_roster_members ADD COLUMN IF NOT EXISTS photo_updated_at TIMESTAMPTZ;
ALTER TABLE local_players ADD COLUMN IF NOT EXISTS origin_program_id INTEGER;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'fk_local_players_origin_program'
        AND conrelid = 'local_players'::regclass) THEN
        ALTER TABLE local_players ADD CONSTRAINT fk_local_players_origin_program
            FOREIGN KEY (origin_program_id) REFERENCES club_programs(id) ON DELETE SET NULL;
    END IF;
END $$;
INSERT INTO club_roster_squad_history (program_id, roster_member_id, squad_id)
    SELECT m.program_id, m.id, m.squad_id FROM club_roster_members m
    WHERE m.squad_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM club_roster_squad_history h WHERE h.roster_member_id=m.id AND h.ended_at IS NULL
    );
UPDATE local_players p SET origin_program_id = (
    SELECT m.program_id FROM club_roster_members m WHERE m.local_player_id=p.id
    ORDER BY m.created_at, m.id LIMIT 1
) WHERE p.provenance='club' AND p.origin_program_id IS NULL;
"""


def upgrade():
    op.execute(UPGRADE_SQL)


def downgrade():
    op.execute("DROP TABLE IF EXISTS club_roster_squad_history")
    op.execute("ALTER TABLE IF EXISTS club_roster_members DROP COLUMN IF EXISTS photo_updated_at")
    op.execute("ALTER TABLE IF EXISTS club_roster_members DROP COLUMN IF EXISTS photo_path")
    op.execute("ALTER TABLE IF EXISTS local_players DROP COLUMN IF EXISTS origin_program_id")
