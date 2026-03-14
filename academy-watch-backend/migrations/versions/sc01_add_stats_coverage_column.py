"""Add stats_coverage column to loaned_players

Revision ID: sc01_stats_coverage
Revises: a5632964f34c
Create Date: 2025-12-01
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'sc01_stats_coverage'
down_revision = 'a5632964f34c'
branch_labels = None
depends_on = None


def upgrade():
    # Add stats_coverage column with default 'full'
    # Using op.execute for IF NOT EXISTS since add_column doesn't support it
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'loaned_players' AND column_name = 'stats_coverage'
            ) THEN
                ALTER TABLE loaned_players ADD COLUMN stats_coverage VARCHAR(20) NOT NULL DEFAULT 'full';
            END IF;
        END $$;
    """)


def downgrade():
    op.drop_column('loaned_players', 'stats_coverage')













