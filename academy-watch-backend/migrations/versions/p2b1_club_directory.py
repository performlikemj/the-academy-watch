"""Club directory: moderated location and offering fields on program profile revisions.

Revision ID: p2b1
Revises: p2a2
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import add_column_safe, column_exists

revision = "p2b1"
down_revision = "p2a2"
branch_labels = None
depends_on = None

TABLE = "club_program_profile_revisions"
COLUMNS = (
    ("venue_name", sa.String(120)),
    ("postcode", sa.String(12)),
    ("latitude", sa.Float()),
    ("longitude", sa.Float()),
    ("geocode_source", sa.String(20)),
    ("club_level", sa.String(20)),
    ("gender_programs", sa.JSON()),
)
CHECKS = (
    (
        "ck_club_program_revisions_club_level",
        "club_level IS NULL OR club_level IN ('grassroots','amateur','semi_pro','professional')",
    ),
    (
        "ck_club_program_revisions_coordinates",
        "(latitude IS NULL AND longitude IS NULL) OR (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180)",
    ),
)


def _check_exists(name):
    return any(check.get("name") == name for check in sa.inspect(op.get_bind()).get_check_constraints(TABLE))


def upgrade():
    for name, column_type in COLUMNS:
        add_column_safe(TABLE, sa.Column(name, column_type, nullable=True))
    for name, condition in CHECKS:
        if not _check_exists(name):
            op.create_check_constraint(name, TABLE, condition)


def downgrade():
    for name, _condition in CHECKS:
        if _check_exists(name):
            op.drop_constraint(name, TABLE, type_="check")
    for name, _column_type in reversed(COLUMNS):
        if column_exists(TABLE, name):
            op.drop_column(TABLE, name)
