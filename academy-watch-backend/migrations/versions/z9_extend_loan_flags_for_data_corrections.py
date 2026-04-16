"""extend loan_flags table for general data correction flagging

Revision ID: z9a1b2c3d4e5
Revises: z8_rename_loan_club_to_current_club
Create Date: 2026-04-01 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "z9a1b2c3d4e5"
down_revision = ("z8_rename", "aw13")
branch_labels = None
depends_on = None


def upgrade():
    # Add new columns for general data correction flagging
    op.add_column("loan_flags", sa.Column("category", sa.String(length=30), nullable=True))
    op.add_column("loan_flags", sa.Column("source", sa.String(length=20), nullable=True))
    op.add_column("loan_flags", sa.Column("player_name", sa.String(length=100), nullable=True))
    op.add_column("loan_flags", sa.Column("team_name", sa.String(length=100), nullable=True))
    op.add_column("loan_flags", sa.Column("newsletter_id", sa.Integer(), nullable=True))
    op.add_column("loan_flags", sa.Column("page_url", sa.String(length=500), nullable=True))
    op.add_column("loan_flags", sa.Column("forwarded_to_api_football", sa.Boolean(), nullable=True))
    op.add_column("loan_flags", sa.Column("forwarded_at", sa.DateTime(), nullable=True))

    # Make player_api_id and primary_team_api_id nullable (general flags may not be player-specific)
    op.alter_column("loan_flags", "player_api_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("loan_flags", "primary_team_api_id", existing_type=sa.Integer(), nullable=True)

    # Add foreign key for newsletter_id
    op.create_foreign_key("fk_loan_flags_newsletter_id", "loan_flags", "newsletters", ["newsletter_id"], ["id"])

    # Backfill existing rows with defaults
    op.execute("UPDATE loan_flags SET category = 'player_data' WHERE category IS NULL")
    op.execute("UPDATE loan_flags SET source = 'website' WHERE source IS NULL")
    op.execute("UPDATE loan_flags SET forwarded_to_api_football = false WHERE forwarded_to_api_football IS NULL")


def downgrade():
    op.drop_constraint("fk_loan_flags_newsletter_id", "loan_flags", type_="foreignkey")
    op.drop_column("loan_flags", "forwarded_at")
    op.drop_column("loan_flags", "forwarded_to_api_football")
    op.drop_column("loan_flags", "page_url")
    op.drop_column("loan_flags", "newsletter_id")
    op.drop_column("loan_flags", "team_name")
    op.drop_column("loan_flags", "player_name")
    op.drop_column("loan_flags", "source")
    op.drop_column("loan_flags", "category")
    op.alter_column("loan_flags", "player_api_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("loan_flags", "primary_team_api_id", existing_type=sa.Integer(), nullable=False)
