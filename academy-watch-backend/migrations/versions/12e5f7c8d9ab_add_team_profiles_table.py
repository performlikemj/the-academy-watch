"""add team profiles table

Revision ID: 12e5f7c8d9ab
Revises: 11d3f5b7c9da
Create Date: 2025-09-22 12:10:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone


# revision identifiers, used by Alembic.
revision = '12e5f7c8d9ab'
down_revision = '11d3f5b7c9da'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'team_profiles',
        sa.Column('team_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('code', sa.String(length=20), nullable=True),
        sa.Column('country', sa.String(length=80), nullable=True),
        sa.Column('founded', sa.Integer(), nullable=True),
        sa.Column('is_national', sa.Boolean(), nullable=True),
        sa.Column('logo_url', sa.String(length=255), nullable=True),
        sa.Column('venue_id', sa.Integer(), nullable=True),
        sa.Column('venue_name', sa.String(length=160), nullable=True),
        sa.Column('venue_address', sa.String(length=255), nullable=True),
        sa.Column('venue_city', sa.String(length=120), nullable=True),
        sa.Column('venue_capacity', sa.Integer(), nullable=True),
        sa.Column('venue_surface', sa.String(length=80), nullable=True),
        sa.Column('venue_image', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('team_id')
    )
    op.create_index('ix_team_profiles_name', 'team_profiles', ['name'])

    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    rows = connection.execute(sa.text(
        """
        SELECT team_id, name, code, country, founded, national, logo,
               venue_name, venue_address, venue_city, venue_capacity
        FROM teams
        WHERE team_id IS NOT NULL
        """
    )).fetchall()

    insert_stmt = sa.text(
        """
        INSERT INTO team_profiles (
            team_id,
            name,
            code,
            country,
            founded,
            is_national,
            logo_url,
            venue_name,
            venue_address,
            venue_city,
            venue_capacity,
            created_at,
            updated_at
        )
        VALUES (
            :team_id,
            :name,
            :code,
            :country,
            :founded,
            :is_national,
            :logo_url,
            :venue_name,
            :venue_address,
            :venue_city,
            :venue_capacity,
            :created_at,
            :updated_at
        )
        ON CONFLICT (team_id) DO NOTHING
        """
    )

    for row in rows:
        connection.execute(
            insert_stmt,
            {
                'team_id': row.team_id,
                'name': row.name,
                'code': row.code,
                'country': row.country,
                'founded': row.founded,
                'is_national': row.national,
                'logo_url': row.logo,
                'venue_name': row.venue_name,
                'venue_address': row.venue_address,
                'venue_city': row.venue_city,
                'venue_capacity': row.venue_capacity,
                'created_at': now,
                'updated_at': now,
            }
        )


def downgrade():
    op.drop_index('ix_team_profiles_name', table_name='team_profiles')
    op.drop_table('team_profiles')
