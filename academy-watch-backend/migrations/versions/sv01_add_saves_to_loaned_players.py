"""Add saves column to loaned_players

Revision ID: sv01_add_saves
Revises: w2x3y4z5a6b7
Create Date: 2025-11-30

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'sv01_add_saves'
down_revision = 'w2x3y4z5a6b7'
branch_labels = None
depends_on = None


def upgrade():
    # Add saves column to loaned_players for goalkeeper stats
    # Using IF NOT EXISTS to handle cases where column was added manually
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'loaned_players' AND column_name = 'saves'
            ) THEN
                ALTER TABLE loaned_players ADD COLUMN saves INTEGER DEFAULT 0;
            END IF;
        END $$;
    """)


def downgrade():
    op.drop_column('loaned_players', 'saves')

