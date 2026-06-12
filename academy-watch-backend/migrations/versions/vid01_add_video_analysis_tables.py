"""Add video-analysis tables (Phase A concierge MVP)

Revision ID: vid01
Revises: aw13
Create Date: 2026-06-12

Tables: video_matches, video_analysis_jobs, video_roster_entries,
video_tracklets, video_player_reports, video_credit_ledger.
Spec: ledgers/CONTINUITY_video-analysis.md "Data model" section.
All DDL is guarded — the production DB has had objects created out-of-band.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import create_index_safe, table_exists

# revision identifiers, used by Alembic.
revision = "vid01"
down_revision = "aw13"
branch_labels = None
depends_on = None


def upgrade():
    if not table_exists("video_matches"):
        op.create_table(
            "video_matches",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("opponent_name", sa.String(200), nullable=True),
            sa.Column("match_date", sa.Date(), nullable=True),
            sa.Column("competition", sa.String(200), nullable=True),
            sa.Column("our_kit_color", sa.String(50), nullable=True),
            sa.Column("opponent_kit_color", sa.String(50), nullable=True),
            sa.Column("capture_meta", sa.JSON(), nullable=True),
            sa.Column("blob_path", sa.String(500), nullable=True),
            sa.Column("blob_etag", sa.String(100), nullable=True),
            sa.Column("duration_s", sa.Float(), nullable=True),
            sa.Column("kickoff_s", sa.Float(), nullable=True),
            sa.Column("halftime_s", sa.Float(), nullable=True),
            sa.Column("second_half_kickoff_s", sa.Float(), nullable=True),
            sa.Column("our_team_cluster", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="created"),
            sa.Column("quality_score", sa.Float(), nullable=True),
            sa.Column("quality_flags", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("uploaded_at", sa.DateTime(), nullable=True),
            sa.Column("finalized_at", sa.DateTime(), nullable=True),
            sa.Column("expires_at", sa.DateTime(), nullable=True),
        )
    create_index_safe("ix_video_matches_team_id", "video_matches", ["team_id"])
    create_index_safe("ix_video_matches_status", "video_matches", ["status"])

    if not table_exists("video_analysis_jobs"):
        op.create_table(
            "video_analysis_jobs",
            sa.Column("id", sa.String(36), primary_key=True),
            sa.Column("video_match_id", sa.Integer(), sa.ForeignKey("video_matches.id"), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
            sa.Column("stage", sa.String(30), nullable=True),
            sa.Column("progress", sa.Integer(), nullable=True, server_default="0"),
            sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("worker_id", sa.String(100), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("gpu_seconds", sa.Float(), nullable=True),
            sa.Column("pipeline_version", sa.String(40), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
    create_index_safe("ix_video_analysis_jobs_match", "video_analysis_jobs", ["video_match_id"])
    create_index_safe("ix_video_analysis_jobs_status", "video_analysis_jobs", ["status"])

    if not table_exists("video_roster_entries"):
        op.create_table(
            "video_roster_entries",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("video_match_id", sa.Integer(), sa.ForeignKey("video_matches.id"), nullable=False),
            sa.Column("player_name", sa.String(200), nullable=False),
            sa.Column("jersey_number", sa.Integer(), nullable=False),
            sa.Column("position", sa.String(50), nullable=True),
            sa.Column(
                "tracked_player_id",
                sa.Integer(),
                sa.ForeignKey("tracked_players.id"),
                nullable=True,
            ),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("video_match_id", "jersey_number", name="uq_video_roster_match_number"),
        )
    create_index_safe("ix_video_roster_entries_match", "video_roster_entries", ["video_match_id"])

    if not table_exists("video_tracklets"):
        op.create_table(
            "video_tracklets",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("video_match_id", sa.Integer(), sa.ForeignKey("video_matches.id"), nullable=False),
            sa.Column("kind", sa.String(10), nullable=False, server_default="fragment"),
            sa.Column("pipeline_key", sa.String(40), nullable=True),
            sa.Column("team_cluster", sa.Integer(), nullable=True),
            sa.Column("suggested_number", sa.Integer(), nullable=True),
            sa.Column("suggested_role", sa.String(20), nullable=True),
            sa.Column("confidence", sa.String(10), nullable=True),
            sa.Column("merge_confidence", sa.Float(), nullable=True),
            sa.Column("contaminated", sa.Boolean(), nullable=False, server_default="false"),
            sa.Column("first_s", sa.Float(), nullable=True),
            sa.Column("last_s", sa.Float(), nullable=True),
            sa.Column("visible_s", sa.Float(), nullable=True),
            sa.Column("thumbnail_paths", sa.JSON(), nullable=True),
            sa.Column("evidence", sa.JSON(), nullable=True),
            sa.Column(
                "roster_entry_id",
                sa.Integer(),
                sa.ForeignKey("video_roster_entries.id"),
                nullable=True,
            ),
            sa.Column("tag_source", sa.String(10), nullable=True),
            sa.Column("dismissed", sa.Boolean(), nullable=False, server_default="false"),
        )
    create_index_safe("ix_video_tracklets_match", "video_tracklets", ["video_match_id"])
    create_index_safe("ix_video_tracklets_roster", "video_tracklets", ["roster_entry_id"])

    if not table_exists("video_player_reports"):
        op.create_table(
            "video_player_reports",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("video_match_id", sa.Integer(), sa.ForeignKey("video_matches.id"), nullable=False),
            sa.Column(
                "roster_entry_id",
                sa.Integer(),
                sa.ForeignKey("video_roster_entries.id"),
                nullable=False,
            ),
            sa.Column(
                "tracked_player_id",
                sa.Integer(),
                sa.ForeignKey("tracked_players.id"),
                nullable=True,
            ),
            sa.Column("minutes_visible", sa.Float(), nullable=True),
            sa.Column("distance_m", sa.Float(), nullable=True),
            sa.Column("distance_confidence", sa.String(10), nullable=True),
            sa.Column("fastest_sustained_kmh", sa.Float(), nullable=True),
            sa.Column("sprint_count", sa.Integer(), nullable=True),
            sa.Column("speed_bands", sa.JSON(), nullable=True),
            sa.Column("heatmap_path", sa.String(500), nullable=True),
            sa.Column("touches", sa.Integer(), nullable=True),
            sa.Column("touches_is_beta", sa.Boolean(), nullable=False, server_default="true"),
            sa.Column("model_version", sa.String(40), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("video_match_id", "roster_entry_id", name="uq_video_report_match_roster"),
        )
    create_index_safe("ix_video_player_reports_match", "video_player_reports", ["video_match_id"])
    create_index_safe("ix_video_player_reports_tracked", "video_player_reports", ["tracked_player_id"])

    if not table_exists("video_credit_ledger"):
        op.create_table(
            "video_credit_ledger",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("team_id", sa.Integer(), sa.ForeignKey("teams.id"), nullable=False),
            sa.Column("delta", sa.Integer(), nullable=False),
            sa.Column("reason", sa.String(20), nullable=False),
            sa.Column("note", sa.String(500), nullable=True),
            sa.Column("video_match_id", sa.Integer(), sa.ForeignKey("video_matches.id"), nullable=True),
            sa.Column("stripe_session_id", sa.String(255), nullable=True, unique=True),
            sa.Column("created_by", sa.String(100), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
        )
    create_index_safe("ix_video_credit_ledger_team", "video_credit_ledger", ["team_id"])


def downgrade():
    for table in (
        "video_player_reports",
        "video_tracklets",
        "video_roster_entries",
        "video_credit_ledger",
        "video_analysis_jobs",
        "video_matches",
    ):
        if table_exists(table):
            op.drop_table(table)
