"""Add rebuild_configs and rebuild_config_logs tables

Revision ID: rc01
Revises: ts01
Create Date: 2026-02-12

Adds tables for named rebuild configuration presets with audit trail.
Seeds a default "Big 6 Standard" config from current hardcoded values.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import json
from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision = 'rc01'
down_revision = 'ts01'
branch_labels = None
depends_on = None


DEFAULT_CONFIG = {
    "team_ids": {
        "33": "Manchester United",
        "42": "Arsenal",
        "49": "Chelsea",
        "50": "Manchester City",
        "40": "Liverpool",
        "47": "Tottenham",
    },
    "seasons": [2020, 2021, 2022, 2023, 2024],
    "youth_leagues": [
        {"key": "pl2_div1", "name": "Premier League 2 Division One", "fallback_id": 702, "level": "U23"},
        {"key": "u18_north", "name": "U18 Premier League - North", "fallback_id": 695, "level": "U18"},
        {"key": "u18_south", "name": "U18 Premier League - South", "fallback_id": 696, "level": "U18"},
        {"key": "u18_championship", "name": "U18 Premier League - Championship", "fallback_id": 987, "level": "U18"},
        {"key": "fa_youth_cup", "name": "FA Youth Cup", "fallback_id": 1068, "level": "U18"},
        {"key": "uefa_youth_league", "name": "UEFA Youth League", "fallback_id": 14, "level": "U19"},
    ],
    "use_transfers_for_status": False,
    "inactivity_threshold_years": 2,
    "assume_full_minutes": False,
    "cohort_discover_timeout": 120,
    "player_sync_timeout": 90,
}


def upgrade():
    op.create_table(
        'rebuild_configs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), unique=True, nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('config_json', sa.Text(), nullable=False),
        sa.Column('notes', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
        sa.Column('updated_at', sa.DateTime()),
    )

    op.create_table(
        'rebuild_config_logs',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('config_id', sa.Integer(), sa.ForeignKey('rebuild_configs.id'), nullable=False),
        sa.Column('action', sa.String(20), nullable=False),
        sa.Column('diff_json', sa.Text()),
        sa.Column('snapshot_json', sa.Text()),
        sa.Column('created_at', sa.DateTime()),
    )

    # Seed default config
    config_str = json.dumps(DEFAULT_CONFIG)
    op.execute(
        text(
            "INSERT INTO rebuild_configs (name, is_active, config_json, notes, created_at, updated_at) "
            "VALUES (:name, true, :config, :notes, NOW(), NOW())"
        ).bindparams(
            name='Big 6 Standard',
            config=config_str,
            notes='Default configuration seeded from hardcoded values.',
        )
    )

    # Log the creation
    op.execute(
        text(
            "INSERT INTO rebuild_config_logs (config_id, action, snapshot_json, created_at) "
            "VALUES ((SELECT id FROM rebuild_configs WHERE name = :name), 'created', :snapshot, NOW())"
        ).bindparams(
            name='Big 6 Standard',
            snapshot=config_str,
        )
    )


def downgrade():
    op.drop_table('rebuild_config_logs')
    op.drop_table('rebuild_configs')
