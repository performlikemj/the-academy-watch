"""Merge the scout-workspace chain (aw14..aw16) with video Phase A (vid01)

Revision ID: aw17
Revises: aw16, vid01
Create Date: 2026-06-12

Pure merge point — no schema changes. The two lines diverged from aw13 in
parallel branches; converging them here keeps a single head whichever
branch a database applied first.
"""

revision = "aw17"
down_revision = ("aw16", "vid01")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
