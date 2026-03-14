"""add user_accounts table and link comments to users

Revision ID: e4f5d6c7b8a9
Revises: c1d2e3f4a5b6
Create Date: 2025-09-17 12:45:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone
import re


# revision identifiers, used by Alembic.
revision = 'e4f5d6c7b8a9'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def _sanitize_display_name(value: str) -> str:
    cleaned = re.sub(r'\s+', ' ', value or '').strip()
    cleaned = re.sub(r'[^A-Za-z0-9 ._\-]', '', cleaned)
    return cleaned[:40] or 'Loaner'


def upgrade():
    op.create_table(
        'user_accounts',
        sa.Column('id', sa.Integer(), primary_key=True, nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('display_name', sa.String(length=80), nullable=False),
        sa.Column('display_name_lower', sa.String(length=80), nullable=False),
        sa.Column('display_name_confirmed', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('last_login_at', sa.DateTime(), nullable=True),
    )
    op.create_index('ix_user_accounts_email', 'user_accounts', ['email'], unique=True)
    op.create_index('ix_user_accounts_display_name_lower', 'user_accounts', ['display_name_lower'], unique=True)

    op.add_column('newsletter_comments', sa.Column('user_id', sa.Integer(), nullable=True))
    op.create_index('ix_newsletter_comments_user_id', 'newsletter_comments', ['user_id'])
    op.create_foreign_key(
        'fk_newsletter_comments_user_id',
        'newsletter_comments',
        'user_accounts',
        ['user_id'],
        ['id'],
        ondelete='SET NULL',
    )

    connection = op.get_bind()
    now = datetime.now(timezone.utc)
    existing_display_names = set()
    existing_emails = set()

    result = connection.execute(sa.text(
        "SELECT DISTINCT LOWER(author_email) AS email, COALESCE(author_name, '') AS author_name "
        "FROM newsletter_comments WHERE author_email IS NOT NULL AND author_email <> ''"
    ))

    for row in result:
        email = (row.email or '').strip()
        if not email:
            continue
        base_name = _sanitize_display_name(row.author_name) if row.author_name else _sanitize_display_name(email.split('@')[0])
        candidate = base_name
        suffix = 1
        while candidate.lower() in existing_display_names:
            suffix += 1
            trimmed = base_name[: max(1, 30 - len(str(suffix)))]
            candidate = f"{trimmed}{suffix}"
        existing_display_names.add(candidate.lower())
        if email not in existing_emails:
            connection.execute(
                sa.text(
                    "INSERT INTO user_accounts (email, display_name, display_name_lower, display_name_confirmed, created_at, updated_at, last_login_at) "
                    "VALUES (:email, :display_name, :display_name_lower, :confirmed, :created_at, :updated_at, :last_login_at)"
                ),
                {
                    'email': email,
                    'display_name': candidate,
                    'display_name_lower': candidate.lower(),
                    'confirmed': bool(row.author_name.strip()) if row.author_name else False,
                    'created_at': now,
                    'updated_at': now,
                    'last_login_at': None,
                }
            )
            existing_emails.add(email)

    connection.execute(sa.text(
        "UPDATE newsletter_comments AS nc "
        "SET user_id = ua.id, author_name = CASE WHEN nc.author_name IS NULL OR nc.author_name = '' THEN ua.display_name ELSE nc.author_name END "
        "FROM user_accounts AS ua "
        "WHERE LOWER(ua.email) = LOWER(nc.author_email)"
    ))


def downgrade():
    op.drop_constraint('fk_newsletter_comments_user_id', 'newsletter_comments', type_='foreignkey')
    op.drop_index('ix_newsletter_comments_user_id', table_name='newsletter_comments')
    op.drop_column('newsletter_comments', 'user_id')
    op.drop_index('ix_user_accounts_display_name_lower', table_name='user_accounts')
    op.drop_index('ix_user_accounts_email', table_name='user_accounts')
    op.drop_table('user_accounts')
