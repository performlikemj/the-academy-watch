"""Add slug column to team_profiles for human-readable URLs

Revision ID: ts01
Revises: aw10
Create Date: 2026-02-09

Adds a unique slug column to team_profiles, backfills from existing names
with collision handling (append country, then team_id).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import re
import unicodedata
from migrations._migration_helpers import column_exists, index_exists


# revision identifiers, used by Alembic.
revision = 'ts01'
down_revision = 'aw10'
branch_labels = None
depends_on = None


def _slugify(value):
    if not value:
        return ""
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_value)
    return cleaned.strip("-").lower()


def upgrade():
    if not column_exists('team_profiles', 'slug'):
        # 1. Add nullable slug column
        op.add_column('team_profiles', sa.Column('slug', sa.String(200), nullable=True))

        # 2. Backfill slugs from existing names
        conn = op.get_bind()
        profiles = conn.execute(text(
            "SELECT team_id, name, country FROM team_profiles ORDER BY team_id"
        )).fetchall()

        used_slugs = set()
        for p in profiles:
            base = _slugify(p.name)
            if not base:
                base = f"team-{p.team_id}"

            slug = base
            if slug in used_slugs:
                if p.country:
                    slug = f"{base}-{_slugify(p.country)}"
                if slug in used_slugs:
                    slug = f"{base}-{p.team_id}"

            used_slugs.add(slug)
            conn.execute(
                text("UPDATE team_profiles SET slug = :slug WHERE team_id = :tid"),
                {'slug': slug, 'tid': p.team_id},
            )

        # 3. Set NOT NULL and add unique index
        op.alter_column('team_profiles', 'slug', nullable=False)

    if not index_exists('ix_team_profiles_slug'):
        op.create_index('ix_team_profiles_slug', 'team_profiles', ['slug'], unique=True)


def downgrade():
    op.drop_index('ix_team_profiles_slug', 'team_profiles')
    op.drop_column('team_profiles', 'slug')
