"""Contract-status-aware contact routing with club participation.

Revision ID: fc03
Revises: fc02

PR #636 (``gf01``, funding registry) remains independently ordered in both
directions. If ``gf01`` lands first, re-point ``fc01`` onto ``gf01`` while
retaining ``fc02 -> fc01`` and ``fc03 -> fc02``; upgrade ``gf01`` before this
stack and downgrade this stack before ``gf01``. If the FC stack lands first,
re-point ``gf01`` onto ``fc03``; its ``club_programs`` CREATE must include the
nullable ``contact_email`` column that this migration can only add when that
table already exists, and downgrades must remove ``gf01`` before ``fc03``.
Never merge an arrangement with two Alembic heads.

All DDL is guarded because production has drifted out-of-band. This revision
creates no table, so no new RLS grant is required; the reused gf01 registry
tables retain their existing default-deny RLS posture. Club-program references
are intentionally logical integers rather than hard foreign keys so either
migration ordering remains deployable.
"""

import sqlalchemy as sa
from alembic import op
from migrations._migration_helpers import (
    add_column_safe,
    column_exists,
    create_index_safe,
    index_exists,
    table_exists,
)

revision = "fc03"
down_revision = "fc02"
branch_labels = None
depends_on = None


AUDIT_EVENTS_FC03 = (
    "'created','accepted','declined','withdrawn','expired','message_sent','outcome_reported',"
    "'club_consent_granted','club_consent_declined','club_notice_sent','scout_permission_attested'"
)
AUDIT_EVENTS_FC02 = "'created','accepted','declined','withdrawn','expired','message_sent','outcome_reported'"
CONTACT_EMAIL_COMMENT = "added by fc03 contract-status routing"
CLUB_CONSENT_ACTOR_FK = "fk_contact_requests_club_consent_by_user"


def _replace_check(table_name: str, constraint_name: str, expression: str, *, not_valid: bool = False) -> None:
    if not table_exists(table_name):
        return
    validation = " NOT VALID" if not_valid else ""
    op.execute(sa.text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{constraint_name}"'))
    op.execute(
        sa.text(f'ALTER TABLE "{table_name}" ADD CONSTRAINT "{constraint_name}" CHECK ({expression}){validation}')
    )


def _drop_check(table_name: str, constraint_name: str) -> None:
    if table_exists(table_name):
        op.execute(sa.text(f'ALTER TABLE "{table_name}" DROP CONSTRAINT IF EXISTS "{constraint_name}"'))


def _constraint_exists(table_name: str, constraint_name: str) -> bool:
    return (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT 1 FROM pg_constraint "
                "WHERE conname = :constraint_name AND conrelid = to_regclass(:qualified_table)"
            ),
            {
                "constraint_name": constraint_name,
                "qualified_table": f"public.{table_name}",
            },
        )
        .scalar()
        is not None
    )


def upgrade():
    if table_exists("player_profile_claims"):
        add_column_safe(
            "player_profile_claims",
            sa.Column("contract_status", sa.String(length=20), nullable=False, server_default="unknown"),
        )
        add_column_safe(
            "player_profile_claims",
            sa.Column("current_club_name", sa.String(length=180), nullable=True),
        )
        add_column_safe("player_profile_claims", sa.Column("club_program_id", sa.Integer(), nullable=True))
        add_column_safe(
            "player_profile_claims",
            sa.Column("status_contradiction", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        _replace_check(
            "player_profile_claims",
            "ck_profile_claims_contract_status",
            "contract_status IN ('free_agent','contracted','unknown')",
        )
        create_index_safe(
            "ix_profile_claims_club_program",
            "player_profile_claims",
            ["club_program_id"],
        )

    if table_exists("player_showcase_profiles"):
        add_column_safe(
            "player_showcase_profiles",
            sa.Column("pending_contract_claim_id", sa.Integer(), nullable=True),
        )
        add_column_safe(
            "player_showcase_profiles",
            sa.Column("pending_contract_status", sa.String(length=20), nullable=True),
        )
        add_column_safe(
            "player_showcase_profiles",
            sa.Column("pending_current_club_name", sa.String(length=180), nullable=True),
        )
        add_column_safe(
            "player_showcase_profiles",
            sa.Column("pending_club_program_id", sa.Integer(), nullable=True),
        )
        add_column_safe(
            "player_showcase_profiles",
            sa.Column("pending_status_contradiction", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        _replace_check(
            "player_showcase_profiles",
            "ck_showcase_profiles_pending_contract_status",
            "pending_contract_status IS NULL OR pending_contract_status IN ('free_agent','contracted','unknown')",
        )

    if table_exists("contact_requests"):
        add_column_safe(
            "contact_requests",
            sa.Column("routing_mode", sa.String(length=20), nullable=False, server_default="direct"),
        )
        add_column_safe("contact_requests", sa.Column("club_program_id", sa.Integer(), nullable=True))
        add_column_safe(
            "contact_requests",
            sa.Column("club_consent_status", sa.String(length=20), nullable=True),
        )
        add_column_safe("contact_requests", sa.Column("club_consent_at", sa.DateTime(), nullable=True))
        add_column_safe(
            "contact_requests",
            sa.Column("club_consent_by_user_id", sa.Integer(), nullable=True),
        )
        if table_exists("user_accounts") and not _constraint_exists("contact_requests", CLUB_CONSENT_ACTOR_FK):
            op.create_foreign_key(
                CLUB_CONSENT_ACTOR_FK,
                "contact_requests",
                "user_accounts",
                ["club_consent_by_user_id"],
                ["id"],
            )
        add_column_safe(
            "contact_requests",
            sa.Column("club_consent_note", sa.String(length=1000), nullable=True),
        )
        add_column_safe(
            "contact_requests",
            sa.Column("permission_attestation", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
        add_column_safe(
            "contact_requests",
            sa.Column("permission_attested_at", sa.DateTime(), nullable=True),
        )
        _replace_check(
            "contact_requests",
            "ck_contact_requests_routing_mode",
            "routing_mode IN ('direct','club_included','club_notified')",
        )
        _replace_check(
            "contact_requests",
            "ck_contact_requests_club_consent",
            "club_consent_status IS NULL OR club_consent_status IN ('pending','granted','declined')",
        )

        create_index_safe(
            "ix_contact_requests_club_program_created",
            "contact_requests",
            ["club_program_id", "created_at"],
        )

        if table_exists("player_profile_claims") and column_exists("player_profile_claims", "contract_status"):
            # FC-B2 requests predate contract attestation. The new claim default
            # is unknown, which FC-B3 must treat as contracted, so those active
            # rows cannot be grandfathered into the new direct path.
            legacy_close = (
                "UPDATE contact_requests AS requests SET status = 'expired' "
                "FROM player_profile_claims AS claims "
                "WHERE requests.claim_id = claims.id "
                "AND requests.routing_mode = 'direct' "
                "AND requests.status IN ('pending','accepted') "
                "AND claims.contract_status IS DISTINCT FROM 'free_agent'"
            )
            if table_exists("contact_audit_events"):
                op.execute(
                    sa.text(
                        "WITH closed AS ("
                        f"{legacy_close} RETURNING requests.id"
                        ") INSERT INTO contact_audit_events "
                        '(contact_request_id, actor_user_id, event_type, "metadata", created_at) '
                        "SELECT id, NULL, 'expired', "
                        "json_build_object('reason', 'fc03_legacy_unknown_contract'), CURRENT_TIMESTAMP "
                        "FROM closed"
                    )
                )
            else:
                op.execute(sa.text(legacy_close))

    if table_exists("contact_messages"):
        add_column_safe(
            "contact_messages",
            sa.Column("sender_role", sa.String(length=20), nullable=True),
        )
        if column_exists("contact_messages", "sender_role"):
            if table_exists("contact_requests") and table_exists("player_profile_claims"):
                op.execute(
                    sa.text(
                        "UPDATE contact_messages AS messages SET sender_role = CASE "
                        "WHEN messages.sender_user_id = requests.scout_user_id THEN 'scout' "
                        "WHEN messages.sender_user_id = claims.user_account_id THEN 'player' "
                        "ELSE 'club' END "
                        "FROM contact_requests AS requests "
                        "JOIN player_profile_claims AS claims ON claims.id = requests.claim_id "
                        "WHERE messages.contact_request_id = requests.id AND messages.sender_role IS NULL"
                    )
                )
            op.execute(sa.text("UPDATE contact_messages SET sender_role = 'player' WHERE sender_role IS NULL"))
            op.alter_column(
                "contact_messages",
                "sender_role",
                existing_type=sa.String(length=20),
                nullable=False,
            )
            _replace_check(
                "contact_messages",
                "ck_contact_messages_sender_role",
                "sender_role IN ('scout','player','club')",
            )

    _replace_check(
        "contact_audit_events",
        "ck_contact_audit_events_type",
        f"event_type IN ({AUDIT_EVENTS_FC03})",
    )

    # PR #636's current gf01 has no row-level courtesy address. Add the narrow,
    # optional field only when its independently ordered table is already here.
    if table_exists("club_programs"):
        added_contact_email = not column_exists("club_programs", "contact_email")
        add_column_safe("club_programs", sa.Column("contact_email", sa.String(length=254), nullable=True))
        if added_contact_email:
            op.execute(sa.text(f"COMMENT ON COLUMN public.club_programs.contact_email IS '{CONTACT_EMAIL_COMMENT}'"))


def downgrade():
    # Preserve append-only FC-B3 audit history without deleting rows. NOT VALID
    # enforces the FC-B2 vocabulary for future writes but does not reject old
    # club events during the downgrade.
    _replace_check(
        "contact_audit_events",
        "ck_contact_audit_events_type",
        f"event_type IN ({AUDIT_EVENTS_FC02})",
        not_valid=True,
    )

    if table_exists("contact_messages"):
        _drop_check("contact_messages", "ck_contact_messages_sender_role")
        if column_exists("contact_messages", "sender_role"):
            op.drop_column("contact_messages", "sender_role")

    if table_exists("contact_requests"):
        if all(
            column_exists("contact_requests", column_name)
            for column_name in ("routing_mode", "club_consent_status", "status")
        ):
            # Fail closed before an FC-B2 application can see these rows without
            # the club-consent columns. Granted rows remain accepted/pending;
            # every other active club-included request becomes terminal.
            op.execute(
                sa.text(
                    "UPDATE contact_requests SET status = 'expired' "
                    "WHERE routing_mode = 'club_included' "
                    "AND status IN ('pending','accepted') "
                    "AND club_consent_status IS DISTINCT FROM 'granted'"
                )
            )
        if index_exists("ix_contact_requests_club_program_created"):
            op.drop_index("ix_contact_requests_club_program_created", table_name="contact_requests")
        if _constraint_exists("contact_requests", CLUB_CONSENT_ACTOR_FK):
            op.drop_constraint(CLUB_CONSENT_ACTOR_FK, "contact_requests", type_="foreignkey")
        _drop_check("contact_requests", "ck_contact_requests_club_consent")
        _drop_check("contact_requests", "ck_contact_requests_routing_mode")
        for column_name in (
            "permission_attested_at",
            "permission_attestation",
            "club_consent_note",
            "club_consent_by_user_id",
            "club_consent_at",
            "club_consent_status",
            "club_program_id",
            "routing_mode",
        ):
            if column_exists("contact_requests", column_name):
                op.drop_column("contact_requests", column_name)

    if table_exists("player_showcase_profiles"):
        _drop_check("player_showcase_profiles", "ck_showcase_profiles_pending_contract_status")
        for column_name in (
            "pending_status_contradiction",
            "pending_club_program_id",
            "pending_current_club_name",
            "pending_contract_status",
            "pending_contract_claim_id",
        ):
            if column_exists("player_showcase_profiles", column_name):
                op.drop_column("player_showcase_profiles", column_name)

    if table_exists("player_profile_claims"):
        if index_exists("ix_profile_claims_club_program"):
            op.drop_index("ix_profile_claims_club_program", table_name="player_profile_claims")
        _drop_check("player_profile_claims", "ck_profile_claims_contract_status")
        for column_name in (
            "status_contradiction",
            "club_program_id",
            "current_club_name",
            "contract_status",
        ):
            if column_exists("player_profile_claims", column_name):
                op.drop_column("player_profile_claims", column_name)

    if table_exists("club_programs") and column_exists("club_programs", "contact_email"):
        contact_email_comment = (
            op.get_bind()
            .execute(
                sa.text(
                    "SELECT col_description('public.club_programs'::regclass, ordinal_position) "
                    "FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'club_programs' "
                    "AND column_name = 'contact_email'"
                )
            )
            .scalar()
        )
        if contact_email_comment == CONTACT_EMAIL_COMMENT:
            op.drop_column("club_programs", "contact_email")
