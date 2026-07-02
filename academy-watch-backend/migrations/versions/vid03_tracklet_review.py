"""Add human-review audit columns to video_tracklets

Revision ID: vid03
Revises: aw20
Create Date: 2026-06-18

The Film Room tag-review gains a per-row video + correction workflow. A human
decision (confirm / reassign / not-a-player) must be distinguishable from a raw
auto-tag — both for the report (a 'confirmed' identity must survive a pipeline
requeue) and for the feedback export that turns corrections into training labels.

Originally authored as the aw18+vid02 merge; re-parented onto aw20 after aw19
merged those heads upstream (aw18 → cs01 → aw19(cs01,vid02) → aw20).

All DDL is guarded — production has had columns added out-of-band.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import add_column_safe, column_exists

revision = "vid03"
down_revision = "aw20"
branch_labels = None
depends_on = None


def upgrade():
    # when the human last reviewed this tracklet (NULL = never human-touched)
    add_column_safe("video_tracklets", sa.Column("reviewed_at", sa.DateTime(), nullable=True))
    # confirmed | reassigned | dismissed — distinguishes "human agreed with auto"
    # from "human corrected it" (training weight + audit + survives re-runs)
    add_column_safe("video_tracklets", sa.Column("review_action", sa.String(20), nullable=True))
    add_column_safe("video_tracklets", sa.Column("reviewer_email", sa.String(200), nullable=True))


def downgrade():
    for col in ("reviewed_at", "review_action", "reviewer_email"):
        if column_exists("video_tracklets", col):
            op.drop_column("video_tracklets", col)
