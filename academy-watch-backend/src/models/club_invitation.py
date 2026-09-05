"""Private claimant-accepted relationships. Policies never commit or depend on HTTP."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import sqlalchemy as sa
from src.models.league import UserAccount, db


def utcnow():
    return datetime.now(UTC).replace(tzinfo=None)


def relationships_enabled():
    return os.getenv("PILOT_CLUB_RELATIONSHIPS_ENABLED", "false").strip().lower() in {"true", "1", "yes", "on"}


class InvitationError(Exception):
    def __init__(self, code, status=409):
        self.code = code
        self.status = status
        super().__init__(code)


class ClubInvitation(db.Model):
    __tablename__ = "club_invitations"
    __table_args__ = (
        sa.UniqueConstraint("program_id", "created_by_user_id", "client_request_id", name="uq_club_invitation_request"),
        sa.CheckConstraint(
            "status IN ('pending','accepted','declined','revoked','expired')", name="ck_club_invitation_status"
        ),
        sa.CheckConstraint("player_api_id <> 0", name="ck_club_invitation_subject"),
        sa.CheckConstraint("expires_at > created_at", name="ck_club_invitation_expiry"),
        sa.Index(
            "uq_club_invitation_active",
            "program_id",
            "player_api_id",
            unique=True,
            sqlite_where=sa.text("status IN ('pending','accepted')"),
            postgresql_where=sa.text("status IN ('pending','accepted')"),
        ),
        sa.Index("ix_club_invitation_recipient", "recipient_user_id", "status", "created_at", "id"),
        sa.Index("ix_club_invitation_program", "program_id", "status", "created_at", "id"),
    )
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid4()))
    program_id = db.Column(db.Integer, db.ForeignKey("club_programs.id", ondelete="CASCADE"), nullable=False)
    player_api_id = db.Column(db.Integer, nullable=False)
    claim_id = db.Column(db.Integer, db.ForeignKey("player_profile_claims.id"), nullable=False)
    recipient_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"), nullable=False)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("user_accounts.id"))
    source_manager_claim_id = db.Column(db.Integer, db.ForeignKey("club_program_claims.id", ondelete="SET NULL"))
    client_request_id = db.Column(db.String(36), nullable=False)
    request_hash = db.Column(db.String(64), nullable=False)
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime(), nullable=False, default=utcnow)
    expires_at = db.Column(db.DateTime(), nullable=False)
    responded_at = db.Column(db.DateTime())
    revoked_at = db.Column(db.DateTime())


def canonical_uuid(value):
    if not isinstance(value, str) or len(value) != 36:
        raise InvitationError("invalid_request", 400)
    try:
        return str(UUID(value))
    except ValueError:
        raise InvitationError("invalid_request", 400) from None


def claim_matches(session, claim, signed_id, recipient_id=None):
    from src.models.showcase import LocalPlayer

    if claim is None or claim.status != "approved" or claim.relationship_type != "player":
        return False
    if recipient_id is not None and claim.user_account_id != recipient_id:
        return False
    if signed_id > 0:
        return claim.player_api_id == signed_id and claim.local_player_id is None
    local = session.get(LocalPlayer, -signed_id)
    return bool(
        local and local.api_player_id == signed_id and claim.local_player_id == local.id and claim.player_api_id is None
    )


def subject_claim(session, signed_id, user_id=None):
    from src.models.showcase import PlayerProfileClaim

    query = session.query(PlayerProfileClaim).filter_by(status="approved", relationship_type="player")
    query = query.filter_by(local_player_id=-signed_id) if signed_id < 0 else query.filter_by(player_api_id=signed_id)
    if user_id is not None:
        query = query.filter_by(user_account_id=user_id)
    return query.order_by(PlayerProfileClaim.reviewed_at.desc(), PlayerProfileClaim.id.desc()).first()


def strict_manager(session, program_id, user_id=None, source_id=None, lock=False):
    from src.models.funding import ClubProgram, ClubProgramClaim, ClubProgramManager

    program = session.get(ClubProgram, program_id)
    if not program or program.platform_status != "approved" or program.emergency_hidden:
        return None
    query = session.query(ClubProgramManager).filter_by(program_id=program_id, status="active")
    if user_id is not None:
        query = query.filter_by(user_account_id=user_id)
    if source_id is not None:
        query = query.filter_by(source_claim_id=source_id)
    if lock:
        query = query.populate_existing().with_for_update()
    for grant in query.order_by(ClubProgramManager.id).all():
        claims = session.query(ClubProgramClaim).filter_by(id=grant.source_claim_id)
        claim = (claims.populate_existing().with_for_update() if lock else claims).first()
        if (
            claim
            and claim.status == "approved"
            and claim.program_id == program_id
            and claim.user_account_id == grant.user_account_id
        ):
            return grant
    return None


def effective_relationship(session, invitation, *, claim_id=None):
    from src.models.showcase import PlayerProfileClaim
    from src.services.public_player_subject import resolve_public_adult_subject

    return bool(
        relationships_enabled()
        and invitation
        and invitation.status == "accepted"
        and (claim_id is None or invitation.claim_id == claim_id)
        and resolve_public_adult_subject(invitation.player_api_id)
        and claim_matches(
            session,
            session.get(PlayerProfileClaim, invitation.claim_id),
            invitation.player_api_id,
            invitation.recipient_user_id,
        )
        and strict_manager(session, invitation.program_id)
    )


def accepted_relationship(session, claim, program_id):
    if not relationships_enabled() or program_id is None:
        return None
    invitation = (
        session.query(ClubInvitation).filter_by(claim_id=claim.id, program_id=program_id, status="accepted").first()
    )
    return invitation if effective_relationship(session, invitation, claim_id=claim.id) else None


def governed_member_available(session, member):
    if not member.requires_player_acceptance:
        return True
    invitation = session.get(ClubInvitation, member.accepted_invitation_id) if member.accepted_invitation_id else None
    signed_id = member.player_api_id if member.player_api_id is not None else -member.local_player_id
    return bool(
        invitation
        and invitation.program_id == member.program_id
        and invitation.player_api_id == signed_id
        and effective_relationship(session, invitation)
    )


def lock_context(session, *, claim_id, program_id, account_ids):
    """Stable lock order shared by invitations and local attestation moderation."""
    from src.models.funding import ClubProgram
    from src.models.showcase import PlayerProfileClaim

    session.query(UserAccount).filter(UserAccount.id.in_(sorted({v for v in account_ids if v is not None}))).order_by(
        UserAccount.id
    ).populate_existing().with_for_update().all()
    claim = session.query(PlayerProfileClaim).filter_by(id=claim_id).populate_existing().with_for_update().first()
    program = (
        session.query(ClubProgram).filter_by(id=program_id).populate_existing().with_for_update().first()
        if program_id
        else None
    )
    return claim, program


def _roster_query(session, invitation):
    from src.models.funding import ClubRosterMember

    query = session.query(ClubRosterMember).filter_by(program_id=invitation.program_id)
    return (
        query.filter_by(player_api_id=invitation.player_api_id)
        if invitation.player_api_id > 0
        else query.filter_by(local_player_id=-invitation.player_api_id)
    )


def invitation_dict(session, invitation):
    from src.models.funding import ClubProgram

    program = session.get(ClubProgram, invitation.program_id)
    member = (
        _roster_query(session, invitation)
        .filter_by(accepted_invitation_id=invitation.id, requires_player_acceptance=True)
        .first()
    )

    def timestamp(value):
        return value.isoformat() + "Z" if value is not None else None

    return {
        "id": invitation.id,
        "program_id": invitation.program_id,
        "program_name": program.name if program else None,
        "player_api_id": invitation.player_api_id,
        "claim_id": invitation.claim_id,
        "status": "expired"
        if invitation.status == "pending" and utcnow() >= invitation.expires_at
        else invitation.status,
        "created_at": timestamp(invitation.created_at),
        "expires_at": timestamp(invitation.expires_at),
        "responded_at": timestamp(invitation.responded_at),
        "roster_member_id": member.id if member else None,
    }


def create_invitation(session, program_id, manager_id, payload):
    from src.services.public_player_subject import resolve_public_adult_subject

    if not isinstance(payload, dict) or set(payload) != {"player_api_id", "client_request_id"}:
        raise InvitationError("invalid_request", 400)
    signed_id = payload["player_api_id"]
    if isinstance(signed_id, bool) or not isinstance(signed_id, int) or not 0 < abs(signed_id) <= 2_147_483_647:
        raise InvitationError("invalid_request", 400)
    request_id = canonical_uuid(payload["client_request_id"])
    digest = hashlib.sha256(
        json.dumps({"player_api_id": signed_id}, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    # Replay identity precedes subject lookup, but locked validation still forbids private disclosure.
    replay = (
        session.query(ClubInvitation)
        .filter_by(program_id=program_id, created_by_user_id=manager_id, client_request_id=request_id)
        .first()
    )
    claim = subject_claim(session, signed_id)
    if replay:
        from src.models.showcase import PlayerProfileClaim

        claim = session.get(PlayerProfileClaim, replay.claim_id)
    if claim is None:
        raise InvitationError("player_not_invitable", 404)
    claim, _ = lock_context(
        session, claim_id=claim.id, program_id=program_id, account_ids=[manager_id, claim.user_account_id]
    )
    grant = strict_manager(session, program_id, manager_id, lock=True)
    if grant is None:
        raise InvitationError("invitation_unavailable")
    replay = (
        session.query(ClubInvitation)
        .filter_by(program_id=program_id, created_by_user_id=manager_id, client_request_id=request_id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if replay and replay.request_hash != digest:
        raise InvitationError("client_request_id_reused")
    if (
        not resolve_public_adult_subject(signed_id)
        or not claim_matches(session, claim, signed_id)
        or claim.user_account_id == manager_id
    ):
        raise InvitationError("player_not_invitable", 404)
    if replay:
        if replay.status == "pending" and utcnow() >= replay.expires_at:
            replay.status = "expired"
        return replay, 200
    if subject_claim(session, signed_id).id != claim.id:
        raise InvitationError("retry_conflict")
    now = utcnow()
    for existing in (
        session.query(ClubInvitation)
        .filter_by(program_id=program_id, player_api_id=signed_id)
        .filter(ClubInvitation.status.in_(["pending", "accepted"]))
        .populate_existing()
        .with_for_update()
        .all()
    ):
        if existing.status == "pending" and now >= existing.expires_at:
            existing.status = "expired"
        else:
            raise InvitationError("invitation_exists")
    session.flush()
    invitation = ClubInvitation(
        program_id=program_id,
        player_api_id=signed_id,
        claim_id=claim.id,
        recipient_user_id=claim.user_account_id,
        created_by_user_id=manager_id,
        source_manager_claim_id=grant.source_claim_id,
        client_request_id=request_id,
        request_hash=digest,
        status="pending",
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    session.add(invitation)
    session.flush()
    return invitation, 201


def resolve_invitation(session, invitation, actor_id, action, *, manager=False):
    from src.models.funding import ClubRosterMember
    from src.services.public_player_subject import resolve_public_adult_subject

    claim, _ = lock_context(
        session,
        claim_id=invitation.claim_id,
        program_id=invitation.program_id,
        account_ids=[actor_id, invitation.recipient_user_id, invitation.created_by_user_id],
    )
    actor_grant = strict_manager(session, invitation.program_id, actor_id, lock=True) if manager else None
    source_grant = (
        strict_manager(
            session, invitation.program_id, invitation.created_by_user_id, invitation.source_manager_claim_id, lock=True
        )
        if invitation.created_by_user_id and invitation.source_manager_claim_id
        else None
    )
    invitation = session.query(ClubInvitation).filter_by(id=invitation.id).populate_existing().with_for_update().one()
    if manager and actor_grant is None:
        raise InvitationError("invitation_unavailable")
    if not manager and invitation.recipient_user_id != actor_id:
        raise InvitationError("invitation_not_found", 404)
    if action == "revoke" and invitation.status == "revoked":
        return invitation
    # Withdrawal removes access even if age or publication eligibility has changed.
    if not claim_matches(session, claim, invitation.player_api_id, invitation.recipient_user_id) or (
        action != "revoke" and not resolve_public_adult_subject(invitation.player_api_id)
    ):
        raise InvitationError("invitation_unavailable")
    now = utcnow()
    if invitation.status == "pending" and now >= invitation.expires_at:
        invitation.status = "expired"
        # The route commits this terminal transition before returning the expiry error.
        return invitation
    if invitation.status == "expired":
        raise InvitationError("invitation_expired")
    if action == "revoke":
        if invitation.status not in {"pending", "accepted"}:
            raise InvitationError("invitation_already_resolved")
        revoke_relationship(session, invitation, claim, now)
    else:
        if invitation.status != "pending":
            raise InvitationError("invitation_already_resolved")
        if source_grant is None:
            raise InvitationError("invitation_unavailable")
        if action == "accept":
            member = _roster_query(session, invitation).populate_existing().with_for_update().first()
            if member is None:
                member = ClubRosterMember(
                    program_id=invitation.program_id,
                    added_by_user_id=actor_id,
                    player_api_id=invitation.player_api_id if invitation.player_api_id > 0 else None,
                    local_player_id=-invitation.player_api_id if invitation.player_api_id < 0 else None,
                )
                session.add(member)
            member.requires_player_acceptance = True
            member.accepted_invitation_id = invitation.id
            invitation.status = "accepted"
        else:
            invitation.status = "declined"
        invitation.responded_at = now
    session.flush()
    return invitation


def revoke_relationship(session, invitation, claim, now):
    from src.models.contact import ContactRequest
    from src.models.showcase import PlayerShowcaseProfile
    from src.models.video import VideoRosterEntry

    invitation.status = "revoked"
    invitation.revoked_at = now
    for member in (
        _roster_query(session, invitation)
        .filter_by(requires_player_acceptance=True, accepted_invitation_id=invitation.id)
        .populate_existing()
        .with_for_update()
        .all()
    ):
        session.query(VideoRosterEntry).filter_by(club_roster_member_id=member.id).update(
            {VideoRosterEntry.club_roster_member_id: None}, synchronize_session="fetch"
        )
        session.delete(member)
    if invitation.player_api_id < 0:
        if claim.club_program_id == invitation.program_id:
            claim.club_program_id = None
            claim.current_club_name = None
        for profile in (
            session.query(PlayerShowcaseProfile)
            .filter_by(pending_contract_claim_id=claim.id, pending_club_program_id=invitation.program_id)
            .with_for_update()
            .all()
        ):
            profile.pending_club_program_id = None
            profile.pending_current_club_name = None
            # Retain the pending claim/status so review must revalidate the withdrawn selection.
    contacts = (
        session.query(ContactRequest)
        .filter_by(claim_id=claim.id, club_program_id=invitation.program_id, routing_mode="club_included")
        .filter(ContactRequest.status.in_(["pending", "accepted"]))
        .order_by(ContactRequest.id)
        .populate_existing()
        .with_for_update()
        .all()
    )
    for contact in contacts:
        contact.status = "declined"
        contact.club_consent_status = "declined"
        contact.club_consent_at = now
        contact.responded_at = now


def local_attestation(session, claim, signed_id, payload, *, lock=True):
    from src.services.public_player_subject import resolve_public_adult_subject

    status = payload.get("contract_status", claim.contract_status)
    program_id = payload.get("club_program_id", claim.club_program_id)
    if not isinstance(status, str) or status not in {"contracted", "unknown", "free_agent"}:
        raise InvitationError("invalid_request", 400)
    if program_id is not None and (
        isinstance(program_id, bool) or not isinstance(program_id, int) or not 0 < program_id <= 2_147_483_647
    ):
        raise InvitationError("invalid_request", 400)
    name = payload.get("current_club_name")
    if name is not None and (not isinstance(name, str) or len(name) > 180):
        raise InvitationError("invalid_request", 400)
    if lock:
        claim, program = lock_context(
            session, claim_id=claim.id, program_id=program_id, account_ids=[claim.user_account_id]
        )
        if program_id:
            strict_manager(session, program_id, lock=True)
    else:
        from src.models.funding import ClubProgram

        program = session.get(ClubProgram, program_id) if program_id else None
    if not claim_matches(session, claim, signed_id) or not resolve_public_adult_subject(signed_id):
        raise InvitationError("club_relationship_required")
    if status == "free_agent":
        program_id, name = None, None
    elif program_id is not None:
        if not accepted_relationship(session, claim, program_id):
            raise InvitationError("club_relationship_required")
        if name is not None and name != program.name:
            raise InvitationError("invalid_request", 400)
        name = program.name
    elif status == "contracted":
        raise InvitationError("club_relationship_required")
    else:
        name = None
    return {
        "contract_status": status,
        "club_program_id": program_id,
        "current_club_name": name,
        "status_contradiction": False,
    }


def list_invitations(session, *, recipient_id=None, program_id=None, player_api_id=None, limit=20, before=None):
    from src.models.showcase import PlayerProfileClaim
    from src.services.public_player_subject import resolve_public_adult_subject

    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 50:
        raise InvitationError("invalid_request", 400)
    query = session.query(ClubInvitation)
    if recipient_id is not None:
        query = query.filter_by(recipient_user_id=recipient_id)
    if program_id is not None:
        query = query.filter_by(program_id=program_id)
    if player_api_id is not None:
        if not 0 < abs(player_api_id) <= 2_147_483_647:
            raise InvitationError("invalid_request", 400)
        query = query.filter_by(player_api_id=player_api_id)
    if before is not None:
        cursor = query.filter_by(id=canonical_uuid(before)).first()
        if cursor is None:
            raise InvitationError("invitation_not_found", 404)
        query = query.filter(
            sa.or_(
                ClubInvitation.created_at < cursor.created_at,
                sa.and_(ClubInvitation.created_at == cursor.created_at, ClubInvitation.id < cursor.id),
            )
        )
    rows = []
    for row in query.order_by(ClubInvitation.created_at.desc(), ClubInvitation.id.desc()).yield_per(50):
        if not resolve_public_adult_subject(row.player_api_id) or not claim_matches(
            session, session.get(PlayerProfileClaim, row.claim_id), row.player_api_id, row.recipient_user_id
        ):
            continue
        rows.append(row)
        if len(rows) > limit:
            break
    return {
        "invitations": [invitation_dict(session, row) for row in rows[:limit]],
        "next_before": rows[limit - 1].id if len(rows) > limit else None,
    }
