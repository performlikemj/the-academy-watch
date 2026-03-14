"""add public slug to newsletters

Revision ID: n0o1p2q3r4s5
Revises: 32b05e0d9e91
Create Date: 2025-11-03 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

import re
import unicodedata


# revision identifiers, used by Alembic.
revision = 'n0o1p2q3r4s5'
down_revision = '32b05e0d9e91'
branch_labels = None
depends_on = None


def _slugify(value: str | None) -> str:
    if not value:
        return ''
    normalized = unicodedata.normalize('NFKD', value)
    ascii_value = normalized.encode('ascii', 'ignore').decode('ascii')
    cleaned = re.sub(r'[^a-zA-Z0-9]+', '-', ascii_value)
    return cleaned.strip('-').lower()


def upgrade():
    op.add_column('newsletters', sa.Column('public_slug', sa.String(length=200), nullable=True))
    op.create_index('ix_newsletters_public_slug', 'newsletters', ['public_slug'], unique=True)

    bind = op.get_bind()
    rows = bind.execute(sa.text(
        """
        SELECT n.id, n.team_id, t.name AS team_name, n.newsletter_type,
               n.issue_date, n.week_start_date, n.week_end_date
        FROM newsletters AS n
        LEFT JOIN teams AS t ON t.id = n.team_id
        ORDER BY n.id
        """
    )).fetchall()

    used: set[str] = set()

    for row in rows:
        team_slug = _slugify(row.team_name) if hasattr(row, 'team_name') else ''
        type_slug = _slugify(row.newsletter_type)

        date_value = row.week_end_date or row.issue_date or row.week_start_date
        date_segment = date_value.isoformat() if date_value else ''

        segments = [seg for seg in (team_slug, type_slug, date_segment) if seg]
        base = '-'.join(segments) if segments else 'newsletter'
        slug_base = f"{base}-{row.id}" if not base.endswith(str(row.id)) else base
        slug_candidate = slug_base[:200]

        candidate = slug_candidate
        counter = 2
        while candidate in used:
            suffix = f"-{counter}"
            candidate = f"{slug_candidate[:200 - len(suffix)]}{suffix}"
            counter += 1

        used.add(candidate)
        bind.execute(
            sa.text("UPDATE newsletters SET public_slug = :slug WHERE id = :id"),
            {"slug": candidate, "id": row.id},
        )

    op.alter_column('newsletters', 'public_slug', existing_type=sa.String(length=200), nullable=False)


def downgrade():
    op.alter_column('newsletters', 'public_slug', existing_type=sa.String(length=200), nullable=True)
    op.drop_index('ix_newsletters_public_slug', table_name='newsletters')
    op.drop_column('newsletters', 'public_slug')
