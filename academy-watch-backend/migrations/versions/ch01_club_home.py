"""Private Club Home squads, staff and branding.

Revision ID: ch01
Revises: s4d1
"""

import sqlalchemy as sa
from alembic import op

revision = "ch01"
down_revision = "s4d1"
branch_labels = None
depends_on = None


def upgrade():
    # PostgreSQL guards cover partially applied schemas as well as fresh upgrades.
    op.execute("""CREATE TABLE IF NOT EXISTS club_squads (
        id SERIAL PRIMARY KEY, program_id INTEGER NOT NULL REFERENCES club_programs(id) ON DELETE CASCADE,
        name VARCHAR(80) NOT NULL, kind VARCHAR(20) NOT NULL,
        age_limit SMALLINT, sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        CONSTRAINT ck_club_squad_kind CHECK (kind IN ('first_team','reserves','age_group','other'))
    )""")
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_club_squad_name ON club_squads (program_id, lower(name))")
    op.execute("""CREATE TABLE IF NOT EXISTS club_staff (
        id SERIAL PRIMARY KEY, program_id INTEGER NOT NULL REFERENCES club_programs(id) ON DELETE CASCADE,
        display_name VARCHAR(120) NOT NULL, title VARCHAR(80) NOT NULL,
        reports_to_staff_id INTEGER REFERENCES club_staff(id) ON DELETE SET NULL,
        leads_squad_id INTEGER REFERENCES club_squads(id) ON DELETE SET NULL,
        user_account_id INTEGER REFERENCES user_accounts(id), sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )""")
    for table in ("club_squads", "club_staff"):
        op.execute(sa.text(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY"))
    op.execute(
        "ALTER TABLE club_roster_members ADD COLUMN IF NOT EXISTS squad_id INTEGER REFERENCES club_squads(id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE club_roster_members ADD COLUMN IF NOT EXISTS shirt_number SMALLINT")
    constraints = {
        row[0]
        for row in op.get_bind().execute(
            sa.text("SELECT conname FROM pg_constraint WHERE conrelid='club_roster_members'::regclass")
        )
    }
    if "ck_club_roster_shirt" not in constraints:
        op.create_check_constraint(
            "ck_club_roster_shirt", "club_roster_members", "shirt_number IS NULL OR shirt_number BETWEEN 1 AND 99"
        )
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_club_squad_shirt ON club_roster_members (squad_id, shirt_number)")
    for name, kind in (
        ("brand_primary_color", "VARCHAR(7)"),
        ("brand_accent_color", "VARCHAR(7)"),
        ("banner_url", "TEXT"),
        ("banner_updated_at", "TIMESTAMPTZ"),
    ):
        op.execute(sa.text(f"ALTER TABLE club_programs ADD COLUMN IF NOT EXISTS {name} {kind}"))


def downgrade():
    for name in ("banner_updated_at", "banner_url", "brand_accent_color", "brand_primary_color"):
        op.execute(sa.text(f"ALTER TABLE IF EXISTS club_programs DROP COLUMN IF EXISTS {name}"))
    op.execute("DROP INDEX IF EXISTS uq_club_squad_shirt")
    op.execute("ALTER TABLE IF EXISTS club_roster_members DROP CONSTRAINT IF EXISTS ck_club_roster_shirt")
    op.execute("ALTER TABLE IF EXISTS club_roster_members DROP COLUMN IF EXISTS shirt_number")
    op.execute("ALTER TABLE IF EXISTS club_roster_members DROP COLUMN IF EXISTS squad_id")
    op.execute("DROP TABLE IF EXISTS club_staff")
    op.execute("DROP TABLE IF EXISTS club_squads")
