"""reconcile admin_settings table if missing

Revision ID: d3e4f5a6b7c8
Revises: c1d2e3f4a5b6
Create Date: 2025-09-13 23:59:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd3e4f5a6b7c8'
down_revision = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def _table_exists(conn, table_name: str) -> bool:
    dialect = conn.dialect.name
    if dialect == 'postgresql':
        res = conn.execute(sa.text("SELECT to_regclass(:t) IS NOT NULL"), {"t": table_name}).scalar()
        return bool(res)
    # Fallback: use information_schema
    res = conn.execute(sa.text(
        "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = :t"
    ), {"t": table_name}).scalar()
    return (res or 0) > 0


def upgrade():
    conn = op.get_bind()
    if not _table_exists(conn, 'admin_settings'):
        op.create_table(
            'admin_settings',
            sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
            sa.Column('key', sa.String(length=100), nullable=False, unique=True),
            sa.Column('value_json', sa.Text(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
        )


def downgrade():
    conn = op.get_bind()
    # Be conservative: do not drop if table might be used by older revisions
    if _table_exists(conn, 'admin_settings'):
        op.drop_table('admin_settings')

