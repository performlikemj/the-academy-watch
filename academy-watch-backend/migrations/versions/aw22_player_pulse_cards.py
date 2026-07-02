"""Player pulse + shared AI card cache tables.

Creates the two Phase-2 surfaces that split digest generation into a cheap
deterministic layer and a shared LLM layer:

- ``player_pulse``      — deterministic per-(player, window) newsworthiness score
- ``player_card_cache`` — the ONE cached LLM card per (player, window), reused
                          across every user's digest

Both are keyed on ``(player_api_id, window_end)`` (composite PK, no surrogate id)
matching ledgers/research/talent-platform/panel-grouping.md.

Idempotent (guards + helpers) — production has had objects added out-of-band,
so every DDL op is safe to re-run in both directions. Tables only; the PKs are
the sole indexes the design requires.

Revision ID: aw22
Revises: aw21
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import table_exists
from sqlalchemy.dialects.postgresql import JSONB

revision = "aw22"
down_revision = "aw21"
branch_labels = None
depends_on = None


def upgrade():
    if not table_exists("player_pulse"):
        op.create_table(
            "player_pulse",
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("window_end", sa.Date(), nullable=False),
            sa.Column("score", sa.Float(), nullable=False),
            sa.Column("delta_json", JSONB(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("player_api_id", "window_end", name="pk_player_pulse"),
        )

    if not table_exists("player_card_cache"):
        op.create_table(
            "player_card_cache",
            sa.Column("player_api_id", sa.Integer(), nullable=False),
            sa.Column("window_end", sa.Date(), nullable=False),
            sa.Column("card_html", sa.Text(), nullable=False),
            sa.Column("card_text", sa.Text(), nullable=False),
            sa.Column("model", sa.String(length=40), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.text("now()")),
            sa.PrimaryKeyConstraint("player_api_id", "window_end", name="pk_player_card_cache"),
        )


def downgrade():
    if table_exists("player_card_cache"):
        op.drop_table("player_card_cache")
    if table_exists("player_pulse"):
        op.drop_table("player_pulse")
