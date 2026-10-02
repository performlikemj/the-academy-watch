"""Private adult handoff and live public consent. Caller owns every transaction."""

import hashlib
import os
import secrets
from datetime import UTC, date, timedelta

import sqlalchemy as sa
from src.models.club_player_publication import ClubPlayerPublication as Publication
from src.models.club_player_publication import now
from src.models.funding import ClubProgram, ClubRosterMember, FundingLeague
from src.models.league import UserAccount, db
from src.models.showcase import LocalPlayer, PlayerProfileClaim, local_player_is_minor
from src.services.club_directory import directory_eligibility, is_listed
from src.services.contact_locks import database_conflict as contact_database_conflict
from src.services.contact_locks import lock_contact_scope

CONSENT_VERSION = "public-profile-v1"
CONSENT_TEXT = (
    "I am this adult player. I agree to make my approved profile public, including scout discovery, "
    "watchlists and sharing. Introductions go to my club first, then I choose. I can withdraw at any time."
)


def enabled():
    return os.getenv("CLUB_PLAYER_PUBLICATION_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


class PublicationError(ValueError):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


def database_conflict(exc):
    return contact_database_conflict(exc, family="publication")


def lock_publication(row):
    locked = lock_contact_scope(db.session, publication_id=row.id).publications.get(row.id)
    if locked is None:
        raise PublicationError("publication_unavailable", 404)
    return locked


def lock_introduction_publication(local_id, program_id):
    from src.services.club_registry import program_is_operational

    hint = Publication.query.filter_by(local_player_id=local_id).first()
    scope = lock_contact_scope(db.session, program_id=program_id, publication_id=hint.id if hint else None)
    row = scope.publications.get(hint.id) if hint else None
    if not program_is_operational(program_id):
        return None
    return row if row is not None and row.program_id == program_id and row.local_player_id == local_id else None


def adult_at_consent(local, timestamp):
    # A corrected child DOB cannot become public merely by reaching a birthday.
    # Current adulthood and adulthood at each explicit permission are separate keys.
    born_year = sa.extract("year", local.birth_date)
    at_year = sa.extract("year", timestamp)
    born_month = sa.extract("month", local.birth_date)
    at_month = sa.extract("month", timestamp)
    return sa.or_(
        sa.and_(
            local.birth_date.is_not(None),
            sa.or_(
                born_year < at_year - 18,
                sa.and_(
                    born_year == at_year - 18,
                    sa.or_(
                        born_month < at_month,
                        sa.and_(
                            born_month == at_month, sa.extract("day", local.birth_date) <= sa.extract("day", timestamp)
                        ),
                    ),
                ),
            ),
        ),
        sa.and_(local.birth_date.is_(None), local.birth_year < at_year - 18),
    )


def publication_local_ids():
    """One live SQL policy, shared by resolvers, discovery and cached reads."""
    from sqlalchemy.orm import aliased
    from src.models.follow import PlayerShadow

    shadow = aliased(PlayerShadow)
    today = now().date()
    try:
        adult_cutoff = date(today.year - 18, today.month, today.day)
    except ValueError:
        adult_cutoff = date(today.year - 18, today.month, 28)
    query = (
        sa.select(Publication.local_player_id)
        .join(LocalPlayer, LocalPlayer.id == Publication.local_player_id)
        .join(PlayerProfileClaim, PlayerProfileClaim.id == Publication.claim_id)
        .join(UserAccount, UserAccount.id == Publication.recipient_user_id)
        .join(ClubProgram, ClubProgram.id == Publication.program_id)
        .join(FundingLeague, FundingLeague.id == ClubProgram.funding_league_id)
        .where(
            LocalPlayer.provenance == "club",
            LocalPlayer.origin_program_id == Publication.program_id,
            LocalPlayer.status == "approved",
            LocalPlayer.api_player_id == -LocalPlayer.id,
            LocalPlayer.merged_into_local_player_id.is_(None),
            ~local_player_is_minor(LocalPlayer),
            ~sa.exists().where(
                shadow.player_api_id == -LocalPlayer.id, shadow.is_active.is_(True), shadow.birth_date > adult_cutoff
            ),
            Publication.adult_invited_at.is_not(None),
            Publication.claimed_at.is_not(None),
            Publication.association_confirmed_at.is_not(None),
            Publication.consented_at.is_not(None),
            adult_at_consent(LocalPlayer, Publication.adult_invited_at),
            adult_at_consent(LocalPlayer, Publication.consented_at),
            Publication.consent_version == CONSENT_VERSION,
            Publication.moderation_status == "approved",
            Publication.withdrawn_at.is_(None),
            Publication.club_revoked_at.is_(None),
            PlayerProfileClaim.local_player_id == LocalPlayer.id,
            PlayerProfileClaim.player_api_id.is_(None),
            PlayerProfileClaim.user_account_id == Publication.recipient_user_id,
            PlayerProfileClaim.relationship_type == "player",
            PlayerProfileClaim.status == "approved",
            PlayerProfileClaim.club_program_id == Publication.program_id,
            UserAccount.is_tombstone.is_(False),
            UserAccount.account_status == "active",
            directory_eligibility(),
            sa.exists().where(
                ClubRosterMember.local_player_id == LocalPlayer.id,
                ClubRosterMember.program_id == Publication.program_id,
            ),
        )
    )
    return query.correlate(None)


def local_publication_filter(local):
    """Flag off never adds a new table dependency to legacy reads."""
    if not enabled():
        return local.provenance != "club"
    return sa.or_(local.provenance != "club", local.id.in_(publication_local_ids()))


def club_subject_filter(signed_id):
    if not enabled():
        return sa.true()
    from sqlalchemy.orm import aliased

    local = aliased(LocalPlayer)
    # Provider surfaces retain their legacy policy. Resolver-backed surfaces
    # separately reject consent transfer through a positive provider bridge.
    return sa.or_(
        signed_id >= 0,
        ~sa.exists().where(local.id == -signed_id, local.provenance == "club", ~local_publication_filter(local)),
    )


def available_club_requests(contacts):
    """Response-owned eligibility with claim/program binding; never cache across reads."""
    contacts = [c for c in contacts if getattr(c, "club_first", False)]
    if not contacts or not enabled():
        return set()
    local_ids = {-c.player_api_id for c in contacts if c.player_api_id < 0}
    rows = Publication.query.filter(
        Publication.local_player_id.in_(local_ids), Publication.local_player_id.in_(publication_local_ids())
    ).all()
    by_local = {r.local_player_id: r for r in rows}
    from src.services.public_adult import public_adult_ids

    adults = public_adult_ids([-i for i in by_local])
    return {
        c.id
        for c in contacts
        if c.player_api_id in adults
        and (r := by_local.get(-c.player_api_id))
        and r.claim_id == c.claim_id
        and r.program_id == c.club_program_id
    }


def club_request_available(contact):
    return not getattr(contact, "club_first", False) or contact.id in available_club_requests([contact])


def public_request_profiles(contacts, available=None):
    """Titles describe a live pinned public profile, separately from its account."""
    available = available_club_requests(contacts) if available is None else available
    live = [
        c
        for c in contacts
        if c.id in available and c.status in {"pending", "accepted"} and c.club_consent_status in {"pending", "granted"}
    ]
    if not live:
        return {}
    names = dict(
        db.session.query(LocalPlayer.id, LocalPlayer.display_name)
        .filter(LocalPlayer.id.in_({-c.player_api_id for c in live}))
        .all()
    )
    return {
        c.id: {"player_api_id": c.player_api_id, "display_name": names[-c.player_api_id]}
        for c in live
        if -c.player_api_id in names
    }


def scout_counterpart_available(contact, available=None):
    if not contact.club_first:
        return True
    return bool(
        contact.club_consent_status == "granted"
        and contact.status in {"pending", "accepted"}
        and (contact.id in available if available is not None else club_request_available(contact))
    )


def can_reinvite(row):
    # Consent withdrawal alone is never an authorization to replace its owner.
    return not row.claimed_at or bool(row.club_revoked_at or (row.withdrawn_at and not row.consented_at))


def shadow_birth_conflict(shadow):
    """Existing DOB evidence is never corrected by publication moderation."""
    from src.utils.academy_window import age_from_birth_date

    if shadow is None or shadow.birth_date is None:
        return False
    age = age_from_birth_date(shadow.birth_date, today=now().date())
    return age is None or age < 18


def canonical_club_namespace(local, shadow):
    """Approval's nonpersonal audit survives erasure; unrelated signed identities do not qualify."""
    from src.models.p2_foundation import AdminActionEvent
    from src.models.tracked_player import TrackedPlayer

    if (
        local.provenance != "club"
        or local.status != "approved"
        or local.api_player_id != -local.id
        or local.merged_into_local_player_id is not None
        or shadow is None
        or shadow.player_api_id != -local.id
        or shadow.player_name != local.display_name
        or shadow.birth_date != local.birth_date
        or shadow.requested_by_user_id != local.created_by_user_id
        or TrackedPlayer.query.filter_by(player_api_id=-local.id).first() is not None
        or PlayerProfileClaim.query.filter_by(player_api_id=-local.id).first() is not None
    ):
        return False
    return (
        AdminActionEvent.query.filter(
            AdminActionEvent.action == "club_player_publication_review",
            AdminActionEvent.target_type == "club_player_publication",
            AdminActionEvent.event_metadata["local_player_id"].as_integer() == local.id,
            AdminActionEvent.event_metadata["approved"].as_boolean().is_(True),
        ).first()
        is not None
    )


def quarantine_showcase(row):
    """Hide former-person content; private evidence stays with its actual author."""
    from src.models.league import PlayerLink
    from src.models.player_match_entry import PlayerMatchEntry
    from src.models.showcase import PlayerClubAffiliation, PlayerShowcaseMedia, PlayerShowcaseProfile
    from src.services.retired_club_content import archive_content
    from src.services.season_rollup_service import refresh_player_scopes

    content = {}
    seasons = set()
    for model in (PlayerShowcaseProfile, PlayerShowcaseMedia, PlayerLink, PlayerClubAffiliation, PlayerMatchEntry):
        signed_column = model.player_id if model is PlayerLink else model.player_api_id
        subject_filter = signed_column == -row.local_player_id
        if model is not PlayerMatchEntry:
            subject_filter = sa.or_(model.local_player_id == row.local_player_id, subject_filter)
        else:
            subject_filter = sa.and_(subject_filter, model.source == "self")
        records = model.query.filter(subject_filter).with_for_update().all()
        content[model.__tablename__] = [
            {
                c.name: value.isoformat() if hasattr(value, "isoformat") else value
                for c in model.__table__.columns
                if (value := getattr(record, c.name)) is not None
            }
            for record in records
        ]
        for record in records:
            if model is PlayerMatchEntry:
                seasons.add(record.season)
            db.session.delete(record)
    archive_content(
        content, local_player_id=row.local_player_id, claim_id=row.claim_id, claimant_id=row.recipient_user_id
    )
    db.session.flush()
    refresh_player_scopes([(-row.local_player_id, season) for season in seasons], session=db.session)


def retire_claim(row, actor):
    from src.services.admin_audit import record_admin_event

    row = lock_publication(row)
    claim = db.session.get(PlayerProfileClaim, row.claim_id) if row.claim_id else None
    quarantine_showcase(row)
    if claim:
        claim.status = "revoked"
        claim.verification_status = "unverified"
        claim.verification_method = "club_vouch_retired"
    record_admin_event(
        db.session.get(UserAccount, actor),
        "club_publication_recovery",
        "club_player_publication",
        row.id,
        "Fresh invitation after permission withdrawal",
        meta={
            "claim_id": row.claim_id,
            "recipient_user_id": row.recipient_user_id,
            "version": row.version,
            "consented": bool(row.consented_at),
            "moderation_status": row.moderation_status,
            "consent_version": row.consent_version,
            **{
                key: int(value.replace(tzinfo=UTC).timestamp()) if value else None
                for key in (
                    "adult_invited_at",
                    "claimed_at",
                    "consented_at",
                    "association_confirmed_at",
                    "withdrawn_at",
                    "club_revoked_at",
                )
                if (value := getattr(row, key)) is not None
            },
        },
    )
    close_threads(row)
    row.recipient_user_id = row.claim_id = row.claimed_at = None
    row.consented_at = row.consent_version = row.withdrawn_at = None
    row.reviewed_at = row.reviewed_by = None
    row.moderation_status = "pending"
    db.session.flush()


def club_local_is_eligible(local):
    return bool(
        enabled()
        and local.provenance == "club"
        and db.session.query(Publication.id)
        .filter(Publication.local_player_id == local.id, Publication.local_player_id.in_(publication_local_ids()))
        .first()
    )


def live_publication(local_id):
    if not enabled():
        return None
    return Publication.query.filter(
        Publication.local_player_id == local_id,
        Publication.local_player_id.in_(publication_local_ids()),
    ).first()


def private_local(program_id, local_id):
    local = LocalPlayer.query.filter_by(id=local_id, provenance="club", origin_program_id=program_id).first()
    if (
        local is None
        or local.merged_into_local_player_id is not None
        or local.api_player_id not in (None, -local.id)
        or local_player_is_minor(local)
        or not ClubRosterMember.query.filter_by(program_id=program_id, local_player_id=local_id).first()
    ):
        raise PublicationError("adult_player_unavailable", 404)
    from src.services.player_suppression import is_local_player_suppressed, is_player_suppressed

    if is_local_player_suppressed(local.id) or is_player_suppressed(-local.id):
        raise PublicationError("adult_player_unavailable", 404)
    return local


def bump(row):
    row.version += 1
    row.updated_at = now()


def expect_version(row, payload):
    value = payload.get("expected_version")
    if isinstance(value, bool) or not isinstance(value, int) or value != row.version:
        raise PublicationError("version_conflict")


def invite(program_id, local_id, actor, payload):
    hint = Publication.query.filter_by(program_id=program_id, local_player_id=local_id).first()
    scope = lock_contact_scope(db.session, program_id=program_id, publication_id=hint.id if hint else None)
    program = scope.programs.get(program_id)
    if not program or not is_listed(program):
        raise PublicationError("club_unavailable", 404)
    local = private_local(program_id, local_id)
    from src.services.club_access import EMAIL_RE

    email = payload.get("recipient_email")
    if not isinstance(email, str) or len(email) > 254 or not EMAIL_RE.fullmatch(email.strip()):
        raise PublicationError("invalid_recipient", 400)
    email = email.strip().lower()
    row = (
        scope.publications.get(hint.id)
        if hint
        else Publication.query.filter_by(program_id=program_id, local_player_id=local_id).first()
    )
    if row:
        row = lock_publication(row)
        expect_version(row, payload)
        if not can_reinvite(row):
            raise PublicationError("already_claimed")
        if row.claimed_at:
            retire_claim(row, actor)
        row.withdrawn_at = None
        row.adult_invited_at = now()
        row.recipient_email = email
        bump(row)
    else:
        row = Publication(
            program_id=program_id,
            local_player_id=local.id,
            recipient_email=email,
            adult_invited_at=now(),
            creator_user_id=actor,
            version=1,
        )
        db.session.add(row)
    token = secrets.token_urlsafe(32)
    row.invite_token_hash = hashlib.sha256(token.encode()).hexdigest()
    row.invite_expires_at = now() + timedelta(days=7)
    row.association_confirmed_at = now()
    row.association_confirmed_by = actor
    row.club_revoked_at = None
    db.session.flush()
    return row, token


def redeem(user, payload, *, preview=False):
    token = payload.get("token")
    if not isinstance(token, str) or not 30 <= len(token) <= 100:
        raise PublicationError("invite_unavailable", 404)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    hint = Publication.query.filter_by(invite_token_hash=token_hash).first()
    row = lock_publication(hint) if hint else None
    if (
        row is None
        or row.invite_token_hash != token_hash
        or row.invite_expires_at is None
        or row.invite_expires_at <= now()
        or row.club_revoked_at
        or row.claimed_at
        or row.recipient_email != user.email.strip().lower()
    ):
        raise PublicationError("invite_unavailable", 404)
    local = private_local(row.program_id, row.local_player_id)
    if not is_listed(db.session.get(ClubProgram, row.program_id)):
        raise PublicationError("invite_unavailable", 404)
    if preview:
        return row
    if payload.get("self_claim") is not True:
        raise PublicationError("self_claim_required", 400)
    if PlayerProfileClaim.query.filter(
        PlayerProfileClaim.local_player_id == local.id,
        sa.or_(
            PlayerProfileClaim.verification_method.is_(None),
            PlayerProfileClaim.verification_method != "club_vouch_retired",
        ),
    ).first():
        raise PublicationError("identity_review_required")
    claim = PlayerProfileClaim(
        local_player_id=local.id,
        user_account_id=user.id,
        relationship_type="player",
        status="pending",
        club_program_id=row.program_id,
        contract_status="unknown",
        current_club_name=local.club_name,
        verification_method="club_vouch",
        verification_status="unverified",
    )
    db.session.add(claim)
    db.session.flush()
    row.recipient_user_id = user.id
    row.claim_id = claim.id
    row.claimed_at = now()
    row.invite_token_hash = None
    row.invite_expires_at = None
    bump(row)
    return row


def consent(row, user_id, payload):
    row = lock_publication(row)
    if row.recipient_user_id != user_id or not row.claimed_at:
        raise PublicationError("publication_unavailable", 404)
    expect_version(row, payload)
    private_local(row.program_id, row.local_player_id)
    if row.club_revoked_at:
        raise PublicationError("association_revoked")
    if payload.get("public_profile_consent") is not True or payload.get("consent_version") != CONSENT_VERSION:
        raise PublicationError("explicit_consent_required", 400)
    row.consented_at = now()
    row.consent_version = CONSENT_VERSION
    row.withdrawn_at = None
    row.moderation_status = "pending"
    bump(row)


def review(row, actor, payload):
    row = lock_publication(row)
    expect_version(row, payload)
    action = payload.get("action")
    if action not in {"approve", "reject"}:
        raise PublicationError("invalid_action", 400)
    if action == "reject":
        row.moderation_status = "rejected"
        row.reviewed_by, row.reviewed_at = actor, now()
        close_threads(row)
        clear_club_follow_labels([row.local_player_id])
        bump(row)
        review_audit(row, actor, payload, False)
        return
    if row.moderation_status != "pending":
        raise PublicationError("publication_not_pending")
    local = private_local(row.program_id, row.local_player_id)
    from src.models.follow import PlayerShadow

    shadow = PlayerShadow.query.filter_by(player_api_id=-local.id).with_for_update().first()
    if shadow_birth_conflict(shadow):
        raise PublicationError("birth_evidence_conflict")
    claim = db.session.get(PlayerProfileClaim, row.claim_id) if row.claim_id else None
    recipient = db.session.get(UserAccount, row.recipient_user_id)
    if self_invitation(row, recipient):
        raise PublicationError("self_invitation_review_required")
    if (
        not row.consented_at
        or row.consent_version != CONSENT_VERSION
        or row.withdrawn_at
        or row.club_revoked_at
        or not row.claimed_at
        or not row.association_confirmed_at
        or local_player_is_minor(local, today=row.adult_invited_at.date())
        or local_player_is_minor(local, today=row.consented_at.date())
        or recipient is None
        or recipient.is_tombstone
        or recipient.account_status != "active"
        or claim is None
        or claim.user_account_id != row.recipient_user_id
        or claim.relationship_type != "player"
        or claim.local_player_id != local.id
        or claim.club_program_id != row.program_id
        or claim.status not in {"pending", "approved"}
        or not is_listed(db.session.get(ClubProgram, row.program_id))
    ):
        raise PublicationError("publication_not_ready")
    # Do not silently combine duplicate identities or override another claim.
    duplicate = LocalPlayer.query.filter(
        LocalPlayer.id != local.id,
        LocalPlayer.normalized_name == local.normalized_name,
        sa.or_(LocalPlayer.birth_date == local.birth_date, LocalPlayer.birth_year == local.birth_year),
        LocalPlayer.merged_into_local_player_id.is_(None),
    ).first()
    if action == "approve" and duplicate:
        raise PublicationError("duplicate_identity_review_required")
    if action == "approve" and not (local.status == "approved" and claim.status == "approved"):
        from src.routes.showcase import _legacy_negative_identity_conflict

        if not canonical_club_namespace(local, shadow) and _legacy_negative_identity_conflict(-local.id) is not None:
            raise PublicationError("identity_review_required")
    row.moderation_status = "approved" if action == "approve" else "rejected"
    row.reviewed_by, row.reviewed_at = actor, now()
    if action == "approve":
        local.status, local.api_player_id = "approved", -local.id
        local.reviewed_by, local.reviewed_at = actor, now()
        claim.status, claim.reviewed_by, claim.reviewed_at = "approved", actor, now()
        claim.verification_status = "verified"
        db.session.flush()
        from src.services.player_shadow_service import mint_shadow

        mint_shadow(-local.id)
    bump(row)
    review_audit(row, actor, payload, action == "approve")


def review_audit(row, actor, payload, approved):
    from src.services.admin_audit import record_admin_event

    record_admin_event(
        actor,
        "club_player_publication_review",
        "club_player_publication",
        row.id,
        payload.get("reason"),
        meta={"local_player_id": row.local_player_id, "approved": approved},
    )


def revoke(row, *, club=False):
    row = lock_publication(row)
    if club:
        quarantine_showcase(row)
        row.club_revoked_at = now()
        row.association_confirmed_at = None
    else:
        row.withdrawn_at = now()
    row.invite_token_hash = None
    row.invite_expires_at = None
    row.recipient_email = None
    bump(row)
    close_threads(row)
    clear_club_follow_labels([row.local_player_id])


def clear_club_follow_labels(local_ids=None, *, limit=None):
    """Dark-capable repair of old generated labels; caller commits."""
    from src.models.follow import Follow

    local_query = sa.select(LocalPlayer.id).where(LocalPlayer.provenance == "club")
    if local_ids is not None:
        local_query = local_query.where(LocalPlayer.id.in_(local_ids))
    query = Follow.query.filter(
        Follow.kind == "player",
        Follow.label.is_not(None),
        (-Follow.selector["player_api_id"].as_integer()).in_(local_query),
    )
    if limit is not None:
        ids = [id_ for (id_,) in query.with_entities(Follow.id).order_by(Follow.id).limit(limit).all()]
        query = Follow.query.filter(Follow.id.in_(ids))
    return query.update({Follow.label: None}, synchronize_session="fetch")


def close_threads(row):
    # Either key closes every old conversation; fresh consent cannot revive it.
    from src.models.contact import ContactRequest
    from src.services.contact import add_audit_event

    row = lock_publication(row)
    candidates = (
        ContactRequest.query.filter(
            ContactRequest.player_api_id == -row.local_player_id,
            ContactRequest.status.in_(("pending", "accepted")),
        )
        .order_by(ContactRequest.id)
        .all()
    )
    scope = lock_contact_scope(db.session, request_id=[r.id for r in candidates])
    for contact in scope.requests.values():
        if contact.status not in ("pending", "accepted") or contact.player_api_id != -row.local_player_id:
            continue
        contact.status = "withdrawn"
        add_audit_event(contact, "withdrawn", actor_user_id=None, metadata={"publication_id": row.id})


def masked_email(email):
    if not email or "@" not in email:
        return None
    name, domain = email.split("@", 1)
    return f"{name[:1]}***@{domain}"


def self_invitation(row, recipient=None):
    if recipient is None and row.recipient_user_id:
        recipient = db.session.get(UserAccount, row.recipient_user_id)
    inviter_id = row.association_confirmed_by or row.creator_user_id
    inviter = db.session.get(UserAccount, inviter_id) if inviter_id else None
    return bool(
        recipient
        and (
            inviter_id == recipient.id or (inviter and inviter.email.strip().lower() == recipient.email.strip().lower())
        )
    )


def dto_context(rows, *, admin=False):
    """One response owns all identity, eligibility and moderation evidence loads."""
    from src.models.funding import ClubSquad
    from src.models.p2_foundation import AdminActionEvent
    from src.services.public_adult import public_adult_ids

    local_ids = {r.local_player_id for r in rows}
    locals_ = {p.id: p for p in LocalPlayer.query.filter(LocalPlayer.id.in_(local_ids)).all()} if rows else {}
    context = {"locals": locals_, "adults": public_adult_ids([-i for i in local_ids]) if enabled() else set()}
    if not admin:
        return context
    program_ids = {r.program_id for r in rows}
    user_ids = {
        i for row in rows for i in (row.recipient_user_id, row.association_confirmed_by or row.creator_user_id) if i
    }
    from src.models.follow import PlayerShadow

    context["birth_conflicts"] = {
        -s.player_api_id
        for s in PlayerShadow.query.filter(PlayerShadow.player_api_id.in_([-i for i in local_ids])).all()
        if shadow_birth_conflict(s)
    }
    context["programs"] = {p.id: p for p in ClubProgram.query.filter(ClubProgram.id.in_(program_ids)).all()}
    context["users"] = {u.id: u for u in UserAccount.query.filter(UserAccount.id.in_(user_ids)).all()}
    context["squads"] = {}
    for pid, lid, name in (
        db.session.query(ClubRosterMember.program_id, ClubRosterMember.local_player_id, ClubSquad.name)
        .join(ClubSquad, ClubSquad.id == ClubRosterMember.squad_id)
        .filter(ClubRosterMember.program_id.in_(program_ids), ClubRosterMember.local_player_id.in_(local_ids))
        .distinct()
    ):
        context["squads"].setdefault((pid, lid), []).append(name)
    context["history"] = {}
    for event in AdminActionEvent.query.filter(
        AdminActionEvent.target_type == "club_player_publication",
        AdminActionEvent.target_id.in_([str(r.id) for r in rows]),
        AdminActionEvent.action.in_(["club_player_publication_review", "club_publication_recovery"]),
    ).order_by(AdminActionEvent.id):
        decision = (
            "recovery"
            if event.action == "club_publication_recovery"
            else "approved"
            if event.event_metadata.get("approved")
            else "rejected"
        )
        context["history"].setdefault(event.target_id, []).append(
            {"decision": decision, "reason": event.reason, "reviewed_at": event.created_at.isoformat()}
        )
    return context


def dto_list(rows, *, admin=False):
    context = dto_context(rows, admin=admin)
    return [dto(row, admin=admin, context=context) for row in rows]


def moderation_evidence(row, local, context):
    program = context["programs"].get(row.program_id)
    recipient = context["users"].get(row.recipient_user_id)
    inviter_id = row.association_confirmed_by or row.creator_user_id
    inviter = context["users"].get(inviter_id)
    squads = context["squads"].get((row.program_id, row.local_player_id), [])
    same_account = bool(recipient and inviter_id == recipient.id)
    same_email = bool(recipient and inviter and recipient.email.strip().lower() == inviter.email.strip().lower())
    return {
        "club_name": program.name if program else None,
        "squads": sorted(squads),
        "adult": bool(local and not local_player_is_minor(local) and local.id not in context["birth_conflicts"]),
        "birth_evidence_conflict": bool(local and local.id in context["birth_conflicts"]),
        "adult_evidence_source": "club_birth_date"
        if local and local.birth_date
        else "club_birth_year"
        if local and local.birth_year
        else "missing",
        "invited_email_masked": masked_email(row.recipient_email),
        "claimant_email_masked": masked_email(recipient.email if recipient else None),
        "inviter_email_masked": masked_email(inviter.email if inviter else None),
        "same_account": bool(recipient and inviter_id == recipient.id),
        "same_email": bool(recipient and inviter and recipient.email.strip().lower() == inviter.email.strip().lower()),
        "self_invitation": same_account or same_email,
        "review_history": context["history"].get(str(row.id), []),
        "invited_at": row.adult_invited_at.isoformat() if row.adult_invited_at else None,
        "claimed_at": row.claimed_at.isoformat() if row.claimed_at else None,
        "consented_at": row.consented_at.isoformat() if row.consented_at else None,
    }


def dto(row, *, names=True, admin=False, context=None):
    context = context if context is not None else dto_context([row], admin=admin)
    local = context["locals"].get(row.local_player_id)

    result = {
        "id": row.id,
        "program_id": row.program_id,
        "local_player_id": row.local_player_id,
        "player_name": local.display_name if local and names else None,
        "claimed": row.claimed_at is not None,
        "consented": row.consented_at is not None and row.withdrawn_at is None,
        "association_confirmed": row.association_confirmed_at is not None and row.club_revoked_at is None,
        "moderation_status": row.moderation_status,
        "withdrawn": row.withdrawn_at is not None,
        "club_revoked": row.club_revoked_at is not None,
        "version": row.version,
        "consent_version": CONSENT_VERSION,
        "consent_text": CONSENT_TEXT,
        "public": -row.local_player_id in context["adults"],
        "can_reinvite": can_reinvite(row),
    }
    if admin:
        result["moderation_evidence"] = moderation_evidence(row, local, context)
    return result


def hidden_club_subject_ids(signed_ids, *, include_dark=False):
    if not enabled() and not include_dark:
        return set()
    ids = {i for i in signed_ids if isinstance(i, int) and not isinstance(i, bool) and i < 0}
    if not ids:
        return set()
    club_ids = set()
    ordered = sorted(ids)
    for offset in range(0, len(ordered), 100):
        rows = (
            db.session.query(LocalPlayer.id)
            .filter(LocalPlayer.provenance == "club", LocalPlayer.id.in_([-i for i in ordered[offset : offset + 100]]))
            .all()
        )
        club_ids.update(-id_ for (id_,) in rows)
    from src.services.public_adult import public_adult_ids

    return club_ids - public_adult_ids(club_ids) if enabled() else club_ids


def audit(row, action, actor_id):
    from src.services.admin_audit import record_admin_event

    actor = db.session.get(UserAccount, actor_id)
    record_admin_event(
        actor,
        f"club_publication_{action}",
        "club_player_publication",
        row.id,
        f"Adult publication {action}",
        meta={"publication_id": row.id, "version": row.version},
    )
