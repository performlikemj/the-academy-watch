"""Club-created adult identities require independent public consent.

Revision ID: p2c1
Revises: p2b3
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import add_column_safe, table_exists

revision = "p2c1"
down_revision = "p2b3"
branch_labels = None
depends_on = None

DDL = """CREATE TABLE public.club_player_publications (
 id SERIAL PRIMARY KEY,
 program_id INTEGER NOT NULL REFERENCES public.club_programs(id),
 local_player_id INTEGER NOT NULL REFERENCES public.local_players(id),
 recipient_email VARCHAR(254),
 recipient_user_id INTEGER REFERENCES public.user_accounts(id),
 claim_id INTEGER REFERENCES public.player_profile_claims(id),
 invite_token_hash VARCHAR(64) UNIQUE, invite_expires_at TIMESTAMP,
 adult_invited_at TIMESTAMP NOT NULL, claimed_at TIMESTAMP,
 association_confirmed_at TIMESTAMP,
 association_confirmed_by INTEGER REFERENCES public.user_accounts(id),
 consent_version VARCHAR(40), consented_at TIMESTAMP,
 moderation_status VARCHAR(20) NOT NULL DEFAULT 'pending',
 reviewed_by VARCHAR(254), reviewed_at TIMESTAMP,
 withdrawn_at TIMESTAMP, club_revoked_at TIMESTAMP,
 creator_user_id INTEGER REFERENCES public.user_accounts(id),
 version INTEGER NOT NULL DEFAULT 1,
 created_at TIMESTAMP NOT NULL DEFAULT now(), updated_at TIMESTAMP NOT NULL DEFAULT now(),
 CONSTRAINT uq_club_player_publication UNIQUE(program_id,local_player_id),
 CONSTRAINT ck_publication_moderation CHECK(moderation_status IN ('pending','approved','rejected')),
 CONSTRAINT ck_publication_version CHECK(version > 0)
)"""


def upgrade():
    add_column_safe(
        "contact_requests", sa.Column("club_first", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    if not table_exists("club_player_publications"):
        op.execute(DDL)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_publication_recipient ON public.club_player_publications(recipient_user_id)"
    )
    op.execute("ALTER TABLE public.club_player_publications ALTER COLUMN recipient_email DROP NOT NULL")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_publication_local_player ON public.club_player_publications(local_player_id)"
    )
    op.execute("ALTER TABLE public.club_player_publications ENABLE ROW LEVEL SECURITY")


def downgrade():
    if table_exists("club_player_publications"):
        connection = op.get_bind()
        if connection.exec_driver_sql("SELECT 1 FROM public.club_player_publications LIMIT 1").first():
            raise RuntimeError("Cannot discard retained publication consent; withdraw and retain evidence")
        op.drop_table("club_player_publications")
