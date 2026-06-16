"""Add structured confidence-per-field columns to video_player_reports

Revision ID: vid02
Revises: vid01
Create Date: 2026-06-16

Per-player video reports become a structured, confidence-per-data-point object:
identity is the gate (a stat is only as trustworthy as the identity it hangs on),
coverage tells the coach how much of the player we actually saw, and every metric
carries its own confidence + a `kind` (point / lower_bound / partial_observed /
beta / suppressed) so a biased partial is never shown as a full-match total.

All DDL is guarded — production has had columns added out-of-band.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import add_column_safe, column_exists

revision = "vid02"
down_revision = "vid01"
branch_labels = None
depends_on = None


def upgrade():
    # identity gate
    add_column_safe("video_player_reports", sa.Column("identity_confidence", sa.String(20), nullable=True))
    add_column_safe("video_player_reports", sa.Column("identity_evidence", sa.JSON(), nullable=True))
    # how much of the player we confidently observed
    add_column_safe("video_player_reports", sa.Column("coverage", sa.JSON(), nullable=True))
    # per-metric list: [{key, value, unit, confidence, kind, note, suppressed}]
    add_column_safe("video_player_reports", sa.Column("metrics", sa.JSON(), nullable=True))
    # confidence-flagged partial outputs (confirmed sprints, shots, sequences)
    add_column_safe("video_player_reports", sa.Column("events", sa.JSON(), nullable=True))


def downgrade():
    # Guard each drop on existence rather than swallowing errors — a real failure
    # (lock, permission) should surface, not be masked by a bare except.
    for col in ("identity_confidence", "identity_evidence", "coverage", "metrics", "events"):
        if column_exists("video_player_reports", col):
            op.drop_column("video_player_reports", col)
