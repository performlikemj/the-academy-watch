"""Personal-data export and atomic account-erasure orchestration."""

from __future__ import annotations

from datetime import UTC, date, datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import func, or_
from src.models.account import AccountDeletionEvent
from src.models.billing import BillingCheckoutSession, BillingCustomer, BillingSubscription, GolCheckoutTerms
from src.models.contact import ContactAuditEvent, ContactMessage, ContactOutcome, ContactRequest
from src.models.follow import Follow, FollowList, FollowPlayerSnapshot
from src.models.gol_credits import GolChatExecution, GolCreditLedger, GolPaymentSettlement
from src.models.league import (
    CommentaryApplause,
    CommunityTake,
    EmailToken,
    JournalistLoanTeamAssignment,
    JournalistSubscription,
    JournalistTeamAssignment,
    ManualPlayerSubmission,
    NewsletterComment,
    NewsletterCommentary,
    NewsletterDigestQueue,
    PlayerComment,
    PlayerFlag,
    PlayerLink,
    QuickTakeSubmission,
    StripeConnectedAccount,
    StripeSubscription,
    StripeSubscriptionPlan,
    TeamTrackingRequest,
    UserAccount,
    UserSubscription,
    WriterCoverageRequest,
    db,
)
from src.models.player_fan import PlayerFan
from src.models.player_match_entry import PlayerMatchEntry
from src.models.product_event import ProductEvent
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.showcase import PlayerProfileClaim, PlayerShowcaseProfile
from src.models.trust import ContentReport, ScoutVerification
from src.services import season_rollup_service
from src.services.club_registry import active_manager_program_ids, program_is_operational
from src.services.gol_credits import forfeit_for_deletion
from src.services.player_suppression import active_suppressed_player_ids
from src.services.stripe_billing import (
    cancel_subscriptions_for_account_deletion,
    subscription_payload,
    subscriptions_for_user,
)
from src.services.user_blocks import delete_user_block_rows_for_account

DELETED_DISPLAY_NAME = "Account deleted"
DELETED_EMAIL_PLACEHOLDER = "account-deleted@invalid"

# Rows in these tables must survive for another person's content, moderation,
# or audit integrity. Every owned/private table is deleted explicitly before
# this allowlist is applied; an unclassified future FK fails closed instead of
# silently retaining personal data.
ANONYMIZED_USER_FOREIGN_KEYS = {
    "account_deletion_events.tombstone_user_id",
    "club_program_profile_revisions.submitted_by_user_id",
    "community_takes.curated_by",
    "contact_audit_events.actor_user_id",
    "contact_messages.sender_user_id",
    "contact_outcomes.reported_by_user_id",
    "contact_requests.club_consent_by_user_id",
    "contact_requests.scout_user_id",
    "content_reports.reporter_user_id",
    "contributor_profiles.created_by_id",
    "funding_leagues.proposed_by_user_id",
    "journalist_loan_team_assignments.assigned_by",
    "journalist_team_assignments.assigned_by",
    "manual_player_submissions.reviewed_by",
    "newsletter_commentary.author_id",
    "newsletter_comments.user_id",
    "player_comments.user_id",
    "player_match_entries.reported_by_user_id",
    "player_shadows.requested_by_user_id",
    "quick_take_submissions.reviewed_by",
    "showcase_moderation_events.user_account_id",
    "user_accounts.managed_by_user_id",
    "writer_coverage_requests.reviewed_by",
}


class AccountDeletionUnavailable(RuntimeError):
    """The account disappeared or is already an anonymous tombstone."""


def _iso(value):
    return value.isoformat() if value else None


def _follow_dict(follow: Follow, suppressed_player_ids: set[int] | None = None) -> dict:
    payload = {
        "id": follow.id,
        "kind": follow.kind,
        "selector": follow.selector,
        "label": follow.label,
        "note": follow.note,
        "created_at": _iso(follow.created_at),
    }
    player_api_id = (follow.selector or {}).get("player_api_id") if follow.kind == "player" else None
    if player_api_id in (suppressed_player_ids or set()):
        payload["label"] = "Unavailable"
        payload["unavailable"] = True
    return payload


def _follow_list_dict(follow_list: FollowList, suppressed_player_ids: set[int] | None = None) -> dict:
    follows = follow_list.follows.order_by(Follow.created_at.asc(), Follow.id.asc()).all()
    return {
        "id": follow_list.id,
        "name": follow_list.name,
        "cadence": follow_list.cadence,
        "is_active": bool(follow_list.is_active),
        "is_default": bool(follow_list.is_default),
        "player_cap": follow_list.player_cap,
        "created_at": _iso(follow_list.created_at),
        "updated_at": _iso(follow_list.updated_at),
        "follows": [_follow_dict(follow, suppressed_player_ids) for follow in follows],
    }


def _showcase_profile_dict(profile: PlayerShowcaseProfile, own_claim_ids: set[int]) -> dict:
    payload = profile.owner_dict()
    pending_contract = profile.pending_contract_dict()
    if pending_contract is not None and pending_contract.get("claim_id") not in own_claim_ids:
        pending_contract = None
    payload["pending_contract"] = pending_contract
    return payload


def _submitted_link_dict(link: PlayerLink) -> dict:
    payload = link.to_dict()
    payload["sort_order"] = link.sort_order or 0
    return payload


def _contact_request_dict(contact_request: ContactRequest) -> dict:
    payload = contact_request.to_dict()
    payload["messages"] = [
        message.to_dict()
        for message in contact_request.messages.order_by(None)
        .order_by(ContactMessage.created_at.asc(), ContactMessage.id.asc())
        .all()
    ]
    payload["outcomes"] = [
        outcome.to_dict()
        for outcome in contact_request.outcomes.order_by(None)
        .order_by(ContactOutcome.occurred_at.asc(), ContactOutcome.created_at.asc(), ContactOutcome.id.asc())
        .all()
    ]
    return payload


def _subscription_dict(subscription: UserSubscription) -> dict:
    """Subscription state without the bearer-like unsubscribe capability."""
    return {
        "id": subscription.id,
        "team_id": subscription.team_id,
        "team_name": subscription.team.name if subscription.team else None,
        "preferred_frequency": subscription.preferred_frequency,
        "active": bool(subscription.active),
        "last_email_sent": _iso(subscription.last_email_sent),
        "bounce_count": subscription.bounce_count or 0,
        "email_bounced": bool(subscription.email_bounced),
        "created_at": _iso(subscription.created_at),
        "updated_at": _iso(subscription.updated_at),
    }


def _match_entry_dict(entry: PlayerMatchEntry, schema=None) -> dict:
    """Serialize every current persisted field, explicitly and portably."""
    payload = {
        "id": entry.id,
        "player_api_id": entry.player_api_id,
        "season": entry.season,
        "source": entry.source,
        "status": entry.status,
        "reported_by_user_id": entry.reported_by_user_id,
        "club_program_id": entry.club_program_id,
        "match_date": _iso(entry.match_date),
        "competition": entry.competition,
        "opponent": entry.opponent,
        "home_away": entry.home_away,
        "result_for": entry.result_for,
        "result_against": entry.result_against,
        "minutes": entry.minutes,
        "goals": entry.goals,
        "assists": entry.assists,
        "yellows": entry.yellows,
        "reds": entry.reds,
        "saves": entry.saves,
        "goals_conceded": entry.goals_conceded,
        "note": entry.note,
        "created_at": _iso(entry.created_at),
        "updated_at": _iso(entry.updated_at),
    }

    if schema and schema.has_columns("player_match_entries", "club_result_id"):
        payload["club_result_id"] = db.session.execute(
            sa.text("SELECT club_result_id FROM player_match_entries WHERE id = :id"), {"id": entry.id}
        ).scalar()
    return payload


def _pilot_export(user, schema):
    from src.models.club_invitation import ClubInvitation, strict_manager
    from src.models.player_feedback import PlayerFeedback, feedback_dict, player_can_read

    result = {"club_invitations": [], "player_feedback": {"received": [], "authored": []}, "club_results": []}
    if schema.has_columns("club_invitations", "recipient_user_id", "created_by_user_id"):
        for row in (
            ClubInvitation.query.filter(
                or_(ClubInvitation.recipient_user_id == user.id, ClubInvitation.created_by_user_id == user.id)
            )
            .order_by(ClubInvitation.created_at, ClubInvitation.id)
            .all()
        ):
            result["club_invitations"].append(
                {
                    "id": row.id,
                    "program_id": row.program_id,
                    "player_api_id": row.player_api_id,
                    "status": row.status,
                    "created_at": _iso(row.created_at) + "Z",
                    "expires_at": _iso(row.expires_at) + "Z",
                    "responded_at": _iso(row.responded_at) + "Z" if row.responded_at else None,
                    "role": "recipient" if row.recipient_user_id == user.id else "creator",
                }
            )
    if schema.has_table("player_feedback"):
        for row in (
            PlayerFeedback.query.filter(
                or_(PlayerFeedback.recipient_user_id == user.id, PlayerFeedback.author_user_id == user.id)
            )
            .order_by(PlayerFeedback.published_at, PlayerFeedback.id)
            .all()
        ):
            if player_can_read(db.session, row, user.id):
                result["player_feedback"]["received"].append(feedback_dict(db.session, row))
            if row.author_user_id == user.id:
                # Historical authorship cannot disclose another person's data.
                payload = {"id": row.id, "revision": row.revision, "published_at": _iso(row.published_at) + "Z"}
                if (
                    strict_manager(db.session, row.program_id, user.id)
                    and not row.withdrawn_at
                    and not row.audit_expires_at
                ):
                    from src.models.player_feedback import relationship_matches

                    if relationship_matches(db.session, row):
                        payload = feedback_dict(db.session, row, manager=True)
                result["player_feedback"]["authored"].append(payload)
    # P4 may arrive before its ORM is loaded, or may not exist at all.
    actor_columns = [c for c in ("created_by_user_id", "updated_by_user_id") if schema.has_columns("club_results", c)]
    if actor_columns:
        header_names = (
            "id",
            "program_id",
            "client_request_id",
            "create_request_hash",
            "version",
            "match_date",
            "season",
            "opponent",
            "opponent_key",
            "competition",
            "home_away",
            "result_for",
            "result_against",
            "video_match_id",
            "created_by_user_id",
            "updated_by_user_id",
            "created_at",
            "updated_at",
            "deleted_at",
        )
        headers = [c for c in header_names if c in schema.columns("club_results")]
        if headers:
            table = sa.Table("club_results", sa.MetaData(), autoload_with=schema.bind)
            query = sa.select(*(table.c[c] for c in headers)).where(
                sa.or_(*(table.c[c] == user.id for c in actor_columns))
            )
            result["club_results"] = [
                {
                    k: (v.isoformat() + ("Z" if isinstance(v, datetime) else "") if isinstance(v, date) else v)
                    for k, v in row.items()
                }
                for row in db.session.execute(query).mappings()
            ]
    return result


def _erase_pilot_rows(schema, user_id, claim_ids, tombstone_id):
    from src.models.club_invitation import ClubInvitation, strict_manager
    from src.models.funding import ClubProgramClaim, ClubProgramManager, ClubRosterMember
    from src.models.player_feedback import PlayerFeedback, locked_invitation, observe_closure
    from src.models.video import VideoRosterEntry

    counts = {}
    if schema.has_table("club_invitations"):
        owned_sources = sa.select(ClubProgramClaim.id).where(ClubProgramClaim.user_account_id == user_id)
        predicate = or_(
            ClubInvitation.recipient_user_id == user_id,
            ClubInvitation.created_by_user_id == user_id,
            ClubInvitation.source_manager_claim_id.in_(owned_sources),
        )
        if claim_ids:
            predicate = or_(predicate, ClubInvitation.claim_id.in_(claim_ids))
        invitations = (
            ClubInvitation.query.filter(predicate)
            .order_by(ClubInvitation.program_id, ClubInvitation.claim_id, ClubInvitation.id)
            .all()
        )
        for invitation in invitations:
            invitation = locked_invitation(db.session, invitation, user_id)
            if invitation is None:
                continue
            recipient_deleted = invitation.recipient_user_id == user_id or invitation.claim_id in claim_ids
            delete_invitation = recipient_deleted or invitation.status == "pending"
            if recipient_deleted and schema.has_table("player_feedback"):
                counts["received_feedback"] = counts.get("received_feedback", 0) + PlayerFeedback.query.filter_by(
                    invitation_id=invitation.id
                ).delete(synchronize_session=False)
            other_manager = any(
                strict_manager(db.session, invitation.program_id, grant.user_account_id)
                for grant in ClubProgramManager.query.filter(
                    ClubProgramManager.program_id == invitation.program_id,
                    ClubProgramManager.user_account_id != user_id,
                    ClubProgramManager.status == "active",
                ).all()
            )
            if delete_invitation or not other_manager:
                members = ClubRosterMember.query.filter_by(accepted_invitation_id=invitation.id).all()
                for member in members:
                    VideoRosterEntry.query.filter_by(club_roster_member_id=member.id).update(
                        {VideoRosterEntry.club_roster_member_id: None}, synchronize_session=False
                    )
                    db.session.delete(member)
                db.session.flush()
            if delete_invitation:
                db.session.delete(invitation)
            else:
                invitation.created_by_user_id = None
                invitation.source_manager_claim_id = None
                if not other_manager:
                    invitation.status = "revoked"
                    from src.models.club_invitation import utcnow

                    invitation.revoked_at = invitation.revoked_at or utcnow()
                    if schema.has_table("player_feedback"):
                        for feedback in PlayerFeedback.query.filter_by(invitation_id=invitation.id).all():
                            observe_closure(db.session, feedback)
        db.session.flush()
    # Exact, local policies; the exhaustive global FK allowlist stays closed.
    for table, actor in (
        ("player_feedback", "author_user_id"),
        ("club_roster_members", "brief_updated_by_user_id"),
        ("club_programs", "system_brief_updated_by_user_id"),
        ("video_matches", "processing_requested_by_user_id"),
        ("local_players", "created_by_user_id"),
        ("club_results", "created_by_user_id"),
        ("club_results", "updated_by_user_id"),
    ):
        if not schema.has_columns(table, actor):
            continue
        assignments = f"{schema.quote(actor)} = NULL"
        if table == "club_roster_members":
            assignments += ", coach_brief_body = NULL, brief_updated_at = NULL"
        if table == "club_programs":
            assignments += ", system_brief_body = NULL, system_brief_updated_at = NULL"
        counts[f"{table}.{actor}"] = _update_where(
            schema, table, assignments, f"{schema.quote(actor)} = :user_id", {"user_id": user_id}
        )
    if schema.has_columns("club_roster_members", "added_by_user_id"):
        counts["roster_actors"] = _update_where(
            schema,
            "club_roster_members",
            "added_by_user_id = :tombstone_id, note = NULL",
            "added_by_user_id = :user_id",
            {"user_id": user_id, "tombstone_id": tombstone_id},
        )
    return counts


def build_account_export(user: UserAccount) -> dict:
    """Build the authenticated caller's narrow, portable JSON document."""
    from flask import after_this_request, has_request_context

    if has_request_context():

        @after_this_request
        def private_export(response):
            response.headers["Cache-Control"] = "private, no-store"
            return response

    claims = (
        PlayerProfileClaim.query.filter_by(user_account_id=user.id)
        .order_by(PlayerProfileClaim.created_at.asc(), PlayerProfileClaim.id.asc())
        .all()
    )
    approved_player_ids = {claim.player_api_id for claim in claims if claim.status == "approved"}
    own_claim_ids = {claim.id for claim in claims}

    profile_filter = PlayerShowcaseProfile.updated_by_user_id == user.id
    if approved_player_ids:
        profile_filter = or_(
            profile_filter,
            PlayerShowcaseProfile.player_api_id.in_(approved_player_ids),
        )
    profiles = (
        PlayerShowcaseProfile.query.filter(profile_filter)
        .order_by(PlayerShowcaseProfile.player_api_id.asc(), PlayerShowcaseProfile.id.asc())
        .all()
    )

    sent_requests = (
        ContactRequest.query.filter_by(scout_user_id=user.id)
        .order_by(ContactRequest.created_at.asc(), ContactRequest.id.asc())
        .all()
    )
    sent_request_ids = {row.id for row in sent_requests}
    # Match the live product's inbox authorization: historical actor references
    # alone must never reveal a counterpart's thread after access is revoked.
    received_claim_ids = [
        claim.id for claim in claims if claim.relationship_type == "player" and claim.status == "approved"
    ]
    received_requests = []
    if received_claim_ids:
        received_requests = (
            ContactRequest.query.filter(
                ContactRequest.claim_id.in_(received_claim_ids),
                ContactRequest.id.notin_(sent_request_ids),
            )
            .order_by(ContactRequest.created_at.asc(), ContactRequest.id.asc())
            .all()
        )
    received_request_ids = {row.id for row in received_requests}

    managed_program_ids = [
        program_id
        for program_id in sorted(active_manager_program_ids(user.id))
        if program_is_operational(program_id, for_update=True)
    ]
    club_requests = []
    if managed_program_ids:
        already_exported_request_ids = sent_request_ids | received_request_ids
        club_query = ContactRequest.query.filter(
            sa.and_(
                ContactRequest.routing_mode == "club_included",
                ContactRequest.club_program_id.in_(managed_program_ids),
            )
        )
        if already_exported_request_ids:
            club_query = club_query.filter(ContactRequest.id.notin_(already_exported_request_ids))
        club_requests = club_query.order_by(
            ContactRequest.created_at.asc(),
            ContactRequest.id.asc(),
        ).all()

    account = user.to_dict()
    # The manager id identifies another account and is not needed for portability.
    account.pop("managed_by_user_id", None)
    account["scout_tier"] = user.scout_tier or "free"
    account["scout_digest_opt_in"] = bool(user.scout_digest_opt_in)
    account["profile_activity_email_opt_in"] = bool(user.profile_activity_email_opt_in)

    schema = _SchemaView()
    pilot_export = _pilot_export(user, schema)
    normalized_email = (user.email or "").strip().lower()
    subscriptions = []
    if normalized_email:
        subscriptions = (
            UserSubscription.query.filter(func.lower(UserSubscription.email) == normalized_email)
            .order_by(UserSubscription.created_at.asc(), UserSubscription.id.asc())
            .all()
        )

    watchlist_entries = (
        ScoutWatchlistEntry.query.filter_by(user_account_id=user.id)
        .order_by(ScoutWatchlistEntry.created_at.asc(), ScoutWatchlistEntry.id.asc())
        .all()
    )
    follow_lists = (
        FollowList.query.filter_by(user_account_id=user.id)
        .order_by(FollowList.created_at.asc(), FollowList.id.asc())
        .all()
    )
    list_ids = [row.id for row in follow_lists]
    direct_follow_ids = []
    if list_ids:
        direct_follow_ids = [
            (row.selector or {}).get("player_api_id")
            for row in Follow.query.filter(Follow.list_id.in_(list_ids), Follow.kind == "player").all()
        ]
    suppressed_player_ids = active_suppressed_player_ids(
        [row.player_api_id for row in watchlist_entries] + direct_follow_ids
    )

    watchlist_payloads = []
    for row in watchlist_entries:
        payload = row.to_dict()
        if row.player_api_id in suppressed_player_ids:
            payload["unavailable"] = True
        watchlist_payloads.append(payload)

    return {
        **pilot_export,
        "exported_at": datetime.now(UTC).isoformat(),
        "account": account,
        "billing": {
            "has_billing_account": BillingCustomer.query.filter_by(user_account_id=user.id).first() is not None,
            "subscriptions": [subscription_payload(row) for row in subscriptions_for_user(user)],
        },
        "gol_chat_executions": [
            row.to_dict()
            for row in GolChatExecution.query.filter_by(user_account_id=user.id).order_by(GolChatExecution.id).all()
        ],
        "gol_credit_ledger": [
            row.to_dict()
            for row in GolCreditLedger.query.filter_by(user_account_id=user.id)
            .order_by(GolCreditLedger.created_at.asc(), GolCreditLedger.id.asc())
            .all()
        ],
        "scout_verifications": [
            row.to_dict()
            for row in ScoutVerification.query.filter_by(user_account_id=user.id)
            .order_by(ScoutVerification.submitted_at.asc(), ScoutVerification.id.asc())
            .all()
        ],
        "watchlist_entries": watchlist_payloads,
        "fan_follows": [
            row.to_dict()
            for row in PlayerFan.query.filter_by(user_account_id=user.id)
            .order_by(PlayerFan.created_at.asc(), PlayerFan.id.asc())
            .all()
        ],
        "follow_lists": [_follow_list_dict(row, suppressed_player_ids) for row in follow_lists],
        "match_entries": [
            _match_entry_dict(row, schema)
            for row in PlayerMatchEntry.query.filter_by(reported_by_user_id=user.id)
            .order_by(PlayerMatchEntry.created_at.asc(), PlayerMatchEntry.id.asc())
            .all()
        ],
        "showcase_claims": [claim.to_dict() for claim in claims],
        "showcase_profiles": [_showcase_profile_dict(profile, own_claim_ids) for profile in profiles],
        "submitted_links": [
            _submitted_link_dict(row)
            for row in PlayerLink.query.filter_by(user_id=user.id)
            .order_by(PlayerLink.created_at.asc(), PlayerLink.id.asc())
            .all()
        ],
        "contact_requests": {
            "sent": [_contact_request_dict(row) for row in sent_requests],
            "received": [_contact_request_dict(row) for row in received_requests],
            "club": [_contact_request_dict(row) for row in club_requests],
        },
        "content_reports": [
            row.to_dict()
            for row in ContentReport.query.filter_by(reporter_user_id=user.id)
            .order_by(ContentReport.created_at.asc(), ContentReport.id.asc())
            .all()
        ],
        "email_subscriptions": {
            "delivery_preference": user.email_delivery_preference or "individual",
            "scout_digest_opt_in": bool(user.scout_digest_opt_in),
            "team_subscriptions": [_subscription_dict(row) for row in subscriptions],
        },
    }


class _SchemaView:
    """Small Core-introspection bridge for optional and future FK tables."""

    def __init__(self):
        # Introspect through the session's transactional connection. Besides
        # keeping every deletion step on one connection, this prevents an
        # inspector-owned wrapper from rolling back SQLite's shared in-memory
        # connection when it closes.
        self.bind = db.session.connection()
        self.inspector = sa.inspect(self.bind)
        self.tables = set(self.inspector.get_table_names())
        self._columns: dict[str, set[str]] = {}
        self.preparer = self.bind.dialect.identifier_preparer

    def has_table(self, table: str) -> bool:
        return table in self.tables

    def columns(self, table: str) -> set[str]:
        if table not in self._columns:
            self._columns[table] = (
                {column["name"] for column in self.inspector.get_columns(table)} if self.has_table(table) else set()
            )
        return self._columns[table]

    def has_columns(self, table: str, *columns: str) -> bool:
        return self.has_table(table) and set(columns).issubset(self.columns(table))

    def quote(self, identifier: str) -> str:
        return self.preparer.quote(identifier)


def _count_where(schema: _SchemaView, table: str, where: str, params: dict) -> int:
    quoted_table = schema.quote(table)
    return int(db.session.execute(sa.text(f"SELECT count(*) FROM {quoted_table} WHERE {where}"), params).scalar() or 0)


def _delete_where(schema: _SchemaView, table: str, where: str, params: dict) -> int:
    count = _count_where(schema, table, where, params)
    if count:
        quoted_table = schema.quote(table)
        db.session.execute(sa.text(f"DELETE FROM {quoted_table} WHERE {where}"), params)
    return count


def _update_where(schema: _SchemaView, table: str, assignments: str, where: str, params: dict) -> int:
    count = _count_where(schema, table, where, params)
    if count:
        quoted_table = schema.quote(table)
        db.session.execute(sa.text(f"UPDATE {quoted_table} SET {assignments} WHERE {where}"), params)
    return count


def _delete_optional_funding_rows(schema: _SchemaView, user_id: int) -> dict[str, int]:
    counts = {"funding_claims": 0, "funding_claim_evidence": 0, "funding_managers": 0}
    claims_exist = schema.has_columns("club_program_claims", "id", "user_account_id")

    if schema.has_columns("club_program_managers", "user_account_id"):
        manager_table = schema.quote("club_program_managers")
        user_column = schema.quote("user_account_id")
        where = f"{user_column} = :user_id"
        if claims_exist and "source_claim_id" in schema.columns("club_program_managers"):
            claim_table = schema.quote("club_program_claims")
            source_column = schema.quote("source_claim_id")
            claim_id = schema.quote("id")
            claim_user = schema.quote("user_account_id")
            where += f" OR {source_column} IN (SELECT {claim_id} FROM {claim_table} WHERE {claim_user} = :user_id)"
        counts["funding_managers"] = _delete_where(schema, "club_program_managers", where, {"user_id": user_id})

    if claims_exist and schema.has_columns("club_claim_evidence", "claim_id"):
        claim_table = schema.quote("club_program_claims")
        claim_id = schema.quote("id")
        claim_user = schema.quote("user_account_id")
        evidence_claim = schema.quote("claim_id")
        where = f"{evidence_claim} IN (SELECT {claim_id} FROM {claim_table} WHERE {claim_user} = :user_id)"
        counts["funding_claim_evidence"] = _delete_where(
            schema,
            "club_claim_evidence",
            where,
            {"user_id": user_id},
        )

    if claims_exist:
        user_column = schema.quote("user_account_id")
        counts["funding_claims"] = _delete_where(
            schema,
            "club_program_claims",
            f"{user_column} = :user_id",
            {"user_id": user_id},
        )
    return counts


def _redact_string_identity_columns(schema: _SchemaView, email: str) -> tuple[int, int]:
    """Scrub denormalized admin identities, including independently ordered gf01."""
    cached_rows: set[tuple[str, object]] = set()
    unkeyed_count = 0
    funding_event_count = 0
    targets = (
        ("scout_verifications", "reviewed_by"),
        ("player_profile_claims", "reviewed_by"),
        ("player_showcase_profiles", "reviewed_by"),
        ("video_tracklets", "reviewer_email"),
        ("funding_leagues", "reviewed_by"),
        ("club_programs", "reviewed_by"),
        ("club_program_claims", "reviewed_by"),
        ("club_program_profile_revisions", "reviewed_by"),
        ("club_program_updates", "reviewed_by"),
        ("club_program_managers", "granted_by"),
        ("club_program_managers", "revoked_by"),
        ("player_suppressions", "decided_by"),
        ("showcase_moderation_events", "actor_email"),
    )
    for table, column in targets:
        if not schema.has_columns(table, column):
            continue
        quoted_column = schema.quote(column)
        if schema.has_columns(table, "id"):
            quoted_table = schema.quote(table)
            quoted_id = schema.quote("id")
            matched_ids = db.session.execute(
                sa.text(f"SELECT {quoted_id} FROM {quoted_table} WHERE lower({quoted_column}) = :email"),
                {"email": email},
            ).scalars()
            cached_rows.update((table, row_id) for row_id in matched_ids)
        updated_count = _update_where(
            schema,
            table,
            f"{quoted_column} = :placeholder",
            f"lower({quoted_column}) = :email",
            {"email": email, "placeholder": DELETED_DISPLAY_NAME},
        )
        if not schema.has_columns(table, "id"):
            unkeyed_count += updated_count

    if schema.has_columns("funding_admin_events", "actor_email"):
        actor_email = schema.quote("actor_email")
        funding_event_count = _update_where(
            schema,
            "funding_admin_events",
            f"{actor_email} = :placeholder",
            f"lower({actor_email}) = :email",
            {"email": email, "placeholder": DELETED_DISPLAY_NAME},
        )
    return len(cached_rows) + unkeyed_count, funding_event_count


def _redact_cached_content_identities(user_id: int) -> int:
    count = 0
    count += NewsletterComment.query.filter_by(user_id=user_id).update(
        {
            NewsletterComment.author_email: DELETED_EMAIL_PLACEHOLDER,
            NewsletterComment.author_name: DELETED_DISPLAY_NAME,
            NewsletterComment.author_name_legacy: DELETED_DISPLAY_NAME,
        },
        synchronize_session=False,
    )
    count += NewsletterCommentary.query.filter_by(author_id=user_id).update(
        {NewsletterCommentary.author_name: DELETED_DISPLAY_NAME},
        synchronize_session=False,
    )
    count += PlayerComment.query.filter_by(user_id=user_id).update(
        {
            PlayerComment.author_email: DELETED_EMAIL_PLACEHOLDER,
            PlayerComment.author_name: DELETED_DISPLAY_NAME,
        },
        synchronize_session=False,
    )
    return count


def _redact_email_keyed_rows(email: str) -> tuple[int, int]:
    """Anonymize retained moderation rows and delete first-party telemetry."""
    anonymized = 0
    anonymized += PlayerFlag.query.filter(func.lower(PlayerFlag.email) == email).update(
        {
            PlayerFlag.email: None,
            PlayerFlag.ip_address: None,
            PlayerFlag.user_agent: None,
        },
        synchronize_session=False,
    )
    anonymized += TeamTrackingRequest.query.filter(func.lower(TeamTrackingRequest.email) == email).update(
        {
            TeamTrackingRequest.email: None,
            TeamTrackingRequest.ip_address: None,
            TeamTrackingRequest.user_agent: None,
        },
        synchronize_session=False,
    )

    quick_takes = QuickTakeSubmission.query.filter(func.lower(QuickTakeSubmission.submitter_email) == email).all()
    community_take_ids = [row.community_take_id for row in quick_takes if row.community_take_id is not None]
    if community_take_ids:
        anonymized += CommunityTake.query.filter(CommunityTake.id.in_(community_take_ids)).update(
            {CommunityTake.source_author: DELETED_DISPLAY_NAME},
            synchronize_session=False,
        )
    if quick_takes:
        quick_take_ids = [row.id for row in quick_takes]
        anonymized += QuickTakeSubmission.query.filter(QuickTakeSubmission.id.in_(quick_take_ids)).update(
            {
                QuickTakeSubmission.submitter_name: DELETED_DISPLAY_NAME,
                QuickTakeSubmission.submitter_email: None,
                QuickTakeSubmission.ip_hash: None,
                QuickTakeSubmission.user_agent: None,
            },
            synchronize_session=False,
        )

    deleted_product_events = ProductEvent.query.filter(func.lower(ProductEvent.user_email) == email).delete(
        synchronize_session=False
    )
    return anonymized, deleted_product_events


def _repoint_anonymized_user_foreign_keys(schema: _SchemaView, user_id: int, tombstone_id: int) -> dict[str, int]:
    """Repoint classified integrity rows and reject unclassified retention.

    Explicit deletion and identity-scrubbing rules run first. This exhaustive
    schema pass then applies the documented anonymization allowlist. A future
    table that still references the source account aborts the transaction until
    its delete-versus-retain policy is consciously defined.
    """
    counts: dict[str, int] = {}
    for table in sorted(schema.tables):
        for foreign_key in schema.inspector.get_foreign_keys(table):
            if foreign_key.get("referred_table") != "user_accounts":
                continue
            constrained = foreign_key.get("constrained_columns") or []
            referred = foreign_key.get("referred_columns") or []
            if len(constrained) != 1 or referred != ["id"]:
                continue
            column = constrained[0]
            if table == "user_accounts" and column == "id":
                continue
            quoted_column = schema.quote(column)
            key = f"{table}.{column}"
            reference_count = _count_where(
                schema,
                table,
                f"{quoted_column} = :user_id",
                {"user_id": user_id},
            )
            if not reference_count:
                continue
            if key not in ANONYMIZED_USER_FOREIGN_KEYS:
                raise RuntimeError(f"account deletion policy missing for {key}")
            count = _update_where(
                schema,
                table,
                f"{quoted_column} = :tombstone_id",
                f"{quoted_column} = :user_id",
                {"user_id": user_id, "tombstone_id": tombstone_id},
            )
            if count:
                counts[key] = count
    return counts


def delete_account(user: UserAccount) -> AccountDeletionEvent:
    """Erase one account in the request's existing transaction.

    This function flushes but never commits. The route performs one final
    commit, so the tombstone, anonymization, owned-row deletion, original-user
    deletion, and append-only event either all persist or all roll back.
    """
    # Match webhook order (settlement -> user -> terms). Ensure legacy grants
    # also have a settlement, so deletion cannot race a newly created refund row.
    from src.services.stripe_billing import _lock_gol_settlement

    user_pk = user.id

    def purchase_intents():
        return {
            intent
            for (intent,) in db.session.query(GolCreditLedger.stripe_payment_intent_id)
            .filter(
                GolCreditLedger.user_account_id == user_pk,
                GolCreditLedger.kind == "grant",
                GolCreditLedger.stripe_payment_intent_id.isnot(None),
            )
            .distinct()
            .all()
        }

    for _attempt in range(5):
        savepoint = db.session.begin_nested()
        intents = purchase_intents()
        for intent_id in sorted(intents):
            _lock_gol_settlement(intent_id)
        locked_user = db.session.execute(
            sa.select(UserAccount)
            .where(UserAccount.id == user_pk)
            .with_for_update()
            .execution_options(populate_existing=True)
        ).scalar_one_or_none()
        if purchase_intents() <= intents:
            savepoint.commit()
            break
        # A grant committed while we waited for the user. Release these locks
        # before acquiring its settlement, preserving settlement -> user order.
        savepoint.rollback()
    else:
        raise AccountDeletionUnavailable("purchases changed during deletion; retry")
    if locked_user is None or locked_user.is_tombstone:
        raise AccountDeletionUnavailable("account is already deleted")
    cancel_subscriptions_for_account_deletion(locked_user)

    requested_at = datetime.now(UTC)
    user_id = locked_user.id
    email = (locked_user.email or "").strip().lower()
    anonymous_key = uuid4().hex
    tombstone = UserAccount(
        email=None,
        display_name=DELETED_DISPLAY_NAME,
        display_name_lower=f"account-deleted-{anonymous_key}",
        display_name_confirmed=True,
        can_author_commentary=False,
        is_journalist=False,
        is_editor=False,
        is_curator=False,
        scout_digest_opt_in=False,
        scout_tier="free",
        is_tombstone=True,
        created_at=requested_at,
        updated_at=requested_at,
    )
    db.session.add(tombstone)
    db.session.flush()

    claims = PlayerProfileClaim.query.filter_by(user_account_id=user_id).all()
    claim_ids = [claim.id for claim in claims]
    approved_player_ids = {claim.player_api_id for claim in claims if claim.status == "approved"}

    contact_filters = [
        ContactRequest.scout_user_id == user_id,
        ContactRequest.club_consent_by_user_id == user_id,
        ContactRequest.messages.any(ContactMessage.sender_user_id == user_id),
        ContactRequest.outcomes.any(ContactOutcome.reported_by_user_id == user_id),
        ContactRequest.audit_events.any(ContactAuditEvent.actor_user_id == user_id),
    ]
    if claim_ids:
        contact_filters.append(ContactRequest.claim_id.in_(claim_ids))

    counts = {
        "deleted": {
            "watchlist_entries": 0,
            "fan_follows": 0,
            "follow_lists": 0,
            "follows": 0,
            "follow_player_snapshots": 0,
            "scout_verifications": 0,
            "user_blocks": 0,
            "email_subscriptions": 0,
            "email_tokens": 0,
            "self_match_entries": 0,
            "showcase_claims": len(claim_ids),
            "showcase_profiles": 0,
            "submitted_links": 0,
            "journalist_subscriptions": 0,
            "digest_queue_entries": 0,
            "commentary_applause": 0,
            "journalist_team_assignments": 0,
            "journalist_loan_team_assignments": 0,
            "writer_coverage_requests": 0,
            "manual_player_submissions": 0,
            "product_events": 0,
            "billing_customers": 0,
            "billing_subscriptions": 0,
            "billing_checkout_sessions": 0,
            "gol_credit_ledger": 0,
            "stripe_connected_accounts": 0,
            "stripe_subscription_plans": 0,
            "stripe_subscriptions": 0,
            "funding_claims": 0,
            "funding_claim_evidence": 0,
            "funding_managers": 0,
        },
        "anonymized": {
            "contact_requests": ContactRequest.query.filter(or_(*contact_filters)).distinct().count(),
            "contact_messages": ContactMessage.query.filter_by(sender_user_id=user_id).count(),
            "contact_outcomes": ContactOutcome.query.filter_by(reported_by_user_id=user_id).count(),
            "contact_audit_events": ContactAuditEvent.query.filter_by(actor_user_id=user_id).count(),
            "content_reports": ContentReport.query.filter_by(reporter_user_id=user_id).count(),
            "funding_admin_events": 0,
            "cached_identity_rows": 0,
            "email_keyed_rows": 0,
            "user_fk_references": {},
        },
        "reset": {"showcase_pending_claims": 0, "reel_items": 0},
        "forfeited_credits": 0,
    }

    counts["pilot"] = _erase_pilot_rows(_SchemaView(), user_id, claim_ids, tombstone.id)

    # Break the sole indirect FK that cannot point at a UserAccount tombstone.
    if claim_ids:
        ContactRequest.query.filter(ContactRequest.claim_id.in_(claim_ids)).update(
            {ContactRequest.claim_id: None},
            synchronize_session=False,
        )
        counts["reset"]["showcase_pending_claims"] = PlayerShowcaseProfile.query.filter(
            PlayerShowcaseProfile.pending_contract_claim_id.in_(claim_ids)
        ).update(
            {
                PlayerShowcaseProfile.pending_contract_claim_id: None,
                PlayerShowcaseProfile.pending_contract_status: None,
                PlayerShowcaseProfile.pending_current_club_name: None,
                PlayerShowcaseProfile.pending_club_program_id: None,
                PlayerShowcaseProfile.pending_status_contradiction: False,
            },
            synchronize_session=False,
        )

    remaining_claimed_player_ids = set()
    if approved_player_ids:
        remaining_claimed_player_ids = {
            player_id
            for (player_id,) in db.session.query(PlayerProfileClaim.player_api_id)
            .filter(
                PlayerProfileClaim.player_api_id.in_(approved_player_ids),
                PlayerProfileClaim.status == "approved",
                PlayerProfileClaim.user_account_id != user_id,
            )
            .distinct()
            .all()
        }
    newly_unclaimed_player_ids = approved_player_ids - remaining_claimed_player_ids
    profile_filter = PlayerShowcaseProfile.updated_by_user_id == user_id
    if newly_unclaimed_player_ids:
        profile_filter = or_(
            profile_filter,
            PlayerShowcaseProfile.player_api_id.in_(newly_unclaimed_player_ids),
        )
    counts["deleted"]["showcase_profiles"] = PlayerShowcaseProfile.query.filter(profile_filter).delete(
        synchronize_session=False
    )
    counts["deleted"]["submitted_links"] = PlayerLink.query.filter_by(user_id=user_id).delete(synchronize_session=False)
    if newly_unclaimed_player_ids:
        counts["reset"]["reel_items"] = PlayerLink.query.filter(
            PlayerLink.player_id.in_(newly_unclaimed_player_ids),
            PlayerLink.link_type == "highlight",
            PlayerLink.sort_order != 0,
        ).update({PlayerLink.sort_order: 0}, synchronize_session=False)

    counts["deleted"]["watchlist_entries"] = ScoutWatchlistEntry.query.filter_by(user_account_id=user_id).delete(
        synchronize_session=False
    )
    counts["deleted"]["fan_follows"] = PlayerFan.query.filter_by(user_account_id=user_id).delete(
        synchronize_session=False
    )
    list_ids = [row[0] for row in db.session.query(FollowList.id).filter_by(user_account_id=user_id).all()]
    if list_ids:
        counts["deleted"]["follows"] = Follow.query.filter(Follow.list_id.in_(list_ids)).delete(
            synchronize_session=False
        )
        counts["deleted"]["follow_lists"] = FollowList.query.filter(FollowList.id.in_(list_ids)).delete(
            synchronize_session=False
        )
    counts["deleted"]["follow_player_snapshots"] = FollowPlayerSnapshot.query.filter_by(user_account_id=user_id).delete(
        synchronize_session=False
    )
    counts["deleted"]["scout_verifications"] = ScoutVerification.query.filter_by(user_account_id=user_id).delete(
        synchronize_session=False
    )
    counts["deleted"]["user_blocks"] = delete_user_block_rows_for_account(user_id=user_id)

    # Self reports are the user's own data and leave with the account. Club
    # reports belong to the club, so the exhaustive FK pass below retains them
    # and repoints their reporter to this deletion's anonymous tombstone.
    self_match_refresh_pairs = (
        db.session.query(PlayerMatchEntry.player_api_id, PlayerMatchEntry.season)
        .filter(
            PlayerMatchEntry.reported_by_user_id == user_id,
            PlayerMatchEntry.source == "self",
        )
        .distinct()
        .order_by(PlayerMatchEntry.player_api_id.asc(), PlayerMatchEntry.season.asc())
        .all()
    )
    counts["deleted"]["self_match_entries"] = PlayerMatchEntry.query.filter_by(
        reported_by_user_id=user_id,
        source="self",
    ).delete(synchronize_session=False)
    db.session.flush()
    for player_api_id, season in self_match_refresh_pairs:
        season_rollup_service.refresh_player(
            player_api_id,
            season,
            session=db.session,
        )

    # Keep only nonpersonal purchase receipts, so already fulfilled purchases
    # cannot turn into manual-refund incidents after deletion erases the ledger.
    ProductEvent.query.filter(
        ProductEvent.event_name == "gol_credits_purchased", ProductEvent.user_email == email
    ).update({ProductEvent.user_email: None}, synchronize_session=False)
    if email:
        subscriptions = UserSubscription.query.filter(func.lower(UserSubscription.email) == email)
        subscriptions.update({UserSubscription.active: False}, synchronize_session=False)
        counts["deleted"]["email_subscriptions"] = subscriptions.delete(synchronize_session=False)
        counts["deleted"]["email_tokens"] = EmailToken.query.filter(func.lower(EmailToken.email) == email).delete(
            synchronize_session=False
        )
        email_rows, product_events = _redact_email_keyed_rows(email)
        counts["anonymized"]["email_keyed_rows"] = email_rows
        counts["deleted"]["product_events"] = product_events

    counts["deleted"]["gol_chat_executions"] = GolChatExecution.query.filter_by(user_account_id=user_id).delete(
        synchronize_session=False
    )
    checkout_ids = sa.select(BillingCheckoutSession.id).where(BillingCheckoutSession.purchaser_user_id == user_id)
    # Remove the owned link explicitly, retaining immutable, unowned purchase
    # terms as proof for late-payment refunds. No account or question data remains.
    counts["anonymized"]["gol_checkout_terms"] = GolCheckoutTerms.query.filter(
        GolCheckoutTerms.checkout_row_id.in_(checkout_ids)
    ).update({GolCheckoutTerms.checkout_row_id: None}, synchronize_session=False)
    grant_ids = sa.select(GolCreditLedger.id).where(GolCreditLedger.user_account_id == user_id)
    GolPaymentSettlement.query.filter(GolPaymentSettlement.grant_ledger_id.in_(grant_ids)).update(
        {GolPaymentSettlement.grant_ledger_id: None}, synchronize_session=False
    )
    forfeiture = forfeit_for_deletion(locked_user)
    counts["deleted"]["gol_credit_ledger"] = forfeiture["ledger_rows"]
    counts["forfeited_credits"] = forfeiture["forfeited_credits"]
    db.session.add(
        ProductEvent(
            event_name="gol_credits_forfeited",
            user_email=None,
            props={"credits": forfeiture["forfeited_credits"]},
        )
    )

    counts["deleted"]["journalist_subscriptions"] = JournalistSubscription.query.filter(
        or_(
            JournalistSubscription.subscriber_user_id == user_id,
            JournalistSubscription.journalist_user_id == user_id,
        )
    ).delete(synchronize_session=False)

    billing_checkout_query = BillingCheckoutSession.query.filter_by(purchaser_user_id=user_id)
    counts["deleted"]["billing_checkout_sessions"] = billing_checkout_query.delete(synchronize_session=False)
    billing_subscription_query = BillingSubscription.query.filter(
        or_(
            BillingSubscription.purchaser_user_id == user_id,
            (BillingSubscription.scope_type == "user") & (BillingSubscription.scope_id == user_id),
        )
    )
    counts["deleted"]["billing_subscriptions"] = billing_subscription_query.delete(synchronize_session=False)
    counts["deleted"]["billing_customers"] = BillingCustomer.query.filter_by(user_account_id=user_id).delete(
        synchronize_session=False
    )
    # The Stripe rail is deprecated and has no live product/legal-integrity
    # consumer. Remove its sensitive external identifiers instead of retaining
    # them behind a tombstone; a subscription row involving the caller is
    # deleted even when the counterpart account survives.
    counts["deleted"]["stripe_subscriptions"] = StripeSubscription.query.filter(
        or_(
            StripeSubscription.subscriber_user_id == user_id,
            StripeSubscription.journalist_user_id == user_id,
        )
    ).delete(synchronize_session=False)
    counts["deleted"]["stripe_subscription_plans"] = StripeSubscriptionPlan.query.filter_by(
        journalist_user_id=user_id
    ).delete(synchronize_session=False)
    counts["deleted"]["stripe_connected_accounts"] = StripeConnectedAccount.query.filter_by(
        journalist_user_id=user_id
    ).delete(synchronize_session=False)
    counts["deleted"]["digest_queue_entries"] = NewsletterDigestQueue.query.filter_by(user_id=user_id).delete(
        synchronize_session=False
    )
    counts["deleted"]["commentary_applause"] = CommentaryApplause.query.filter_by(user_id=user_id).delete(
        synchronize_session=False
    )
    counts["deleted"]["journalist_team_assignments"] = JournalistTeamAssignment.query.filter_by(user_id=user_id).delete(
        synchronize_session=False
    )
    counts["deleted"]["journalist_loan_team_assignments"] = JournalistLoanTeamAssignment.query.filter_by(
        user_id=user_id
    ).delete(synchronize_session=False)
    counts["deleted"]["writer_coverage_requests"] = WriterCoverageRequest.query.filter_by(user_id=user_id).delete(
        synchronize_session=False
    )
    counts["deleted"]["manual_player_submissions"] = ManualPlayerSubmission.query.filter_by(user_id=user_id).delete(
        synchronize_session=False
    )
    counts["anonymized"]["cached_identity_rows"] = _redact_cached_content_identities(user_id)

    schema = _SchemaView()
    funding_deleted = _delete_optional_funding_rows(schema, user_id)
    counts["deleted"].update(funding_deleted)
    if email:
        string_identities, funding_events = _redact_string_identity_columns(schema, email)
        counts["anonymized"]["cached_identity_rows"] += string_identities
        counts["anonymized"]["funding_admin_events"] = funding_events

    if schema.has_columns("club_program_updates", "author_user_id"):
        author_column = schema.quote("author_user_id")
        _update_where(
            schema,
            "club_program_updates",
            f"{author_column} = NULL",
            f"{author_column} = :user_id",
            {"user_id": user_id},
        )

    if claim_ids:
        PlayerProfileClaim.query.filter(PlayerProfileClaim.id.in_(claim_ids)).delete(synchronize_session=False)

    db.session.flush()
    counts["anonymized"]["user_fk_references"] = _repoint_anonymized_user_foreign_keys(
        schema,
        user_id,
        tombstone.id,
    )
    db.session.flush()

    # Core delete avoids ORM relationship cascades after every FK has been
    # deliberately deleted or repointed above. Detach the still-loaded source
    # account so the session identity map cannot return a stale account after
    # the Core deletion.
    db.session.expunge(locked_user)
    if db.session.execute(sa.select(UserAccount.id).where(UserAccount.id == tombstone.id)).scalar_one_or_none() is None:
        raise RuntimeError("account tombstone disappeared before source account delete")
    deleted_user_count = db.session.execute(
        sa.delete(UserAccount).where(UserAccount.id == user_id).execution_options(synchronize_session=False)
    ).rowcount
    if deleted_user_count != 1:
        raise AccountDeletionUnavailable("account could not be deleted")
    if db.session.execute(sa.select(UserAccount.id).where(UserAccount.id == tombstone.id)).scalar_one_or_none() is None:
        raise RuntimeError("account tombstone disappeared during source account delete")

    event = AccountDeletionEvent(
        tombstone_user_id=tombstone.id,
        requested_at=requested_at,
        completed_at=datetime.now(UTC),
        counts=counts,
    )
    db.session.add(event)
    db.session.flush()
    return event


__all__ = [
    "AccountDeletionUnavailable",
    "build_account_export",
    "delete_account",
]
