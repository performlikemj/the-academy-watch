"""Drop foreign keys pointing to loaned_players table

Revision ID: aw12
Revises: aw11
Create Date: 2026-03-31

Removes loaned_player_id FK columns from tracked_players,
weekly_loan_appearances, and academy_appearances in preparation
for dropping the loaned_players table.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import column_exists

# revision identifiers, used by Alembic.
revision = "aw12"
down_revision = "aw11"
branch_labels = None
depends_on = None


def _get_fk_constraints(table, column):
    """Look up actual FK constraint names from pg_catalog."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text("""
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_attribute att ON att.attrelid = con.conrelid
            AND att.attnum = ANY(con.conkey)
        WHERE rel.relname = :table
            AND att.attname = :column
            AND con.contype = 'f'
    """),
        {"table": table, "column": column},
    )
    return [row[0] for row in result]


def _get_unique_constraints(table, column):
    """Look up unique constraint names that include this column."""
    conn = op.get_bind()
    result = conn.execute(
        sa.text("""
        SELECT con.conname
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        JOIN pg_attribute att ON att.attrelid = con.conrelid
            AND att.attnum = ANY(con.conkey)
        WHERE rel.relname = :table
            AND att.attname = :column
            AND con.contype = 'u'
    """),
        {"table": table, "column": column},
    )
    return [row[0] for row in result]


def _drop_column_with_constraints(table, column):
    """Drop a column and all its FK/unique constraints."""
    if not column_exists(table, column):
        return

    # Drop FK constraints
    for fk_name in _get_fk_constraints(table, column):
        op.drop_constraint(fk_name, table, type_="foreignkey")

    # Drop unique constraints that include this column
    for uq_name in _get_unique_constraints(table, column):
        op.drop_constraint(uq_name, table, type_="unique")

    op.drop_column(table, column)


def upgrade():
    _drop_column_with_constraints("tracked_players", "loaned_player_id")
    _drop_column_with_constraints("weekly_loan_appearances", "loaned_player_id")
    _drop_column_with_constraints("academy_appearances", "loaned_player_id")


def downgrade():
    op.add_column("academy_appearances", sa.Column("loaned_player_id", sa.Integer(), nullable=True))
    op.add_column("weekly_loan_appearances", sa.Column("loaned_player_id", sa.Integer(), nullable=True))
    op.add_column("tracked_players", sa.Column("loaned_player_id", sa.Integer(), nullable=True))
