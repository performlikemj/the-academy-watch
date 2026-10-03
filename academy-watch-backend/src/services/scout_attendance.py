"""Atomic attendance state/audit/intents; fresh trust and listing checks on every read."""

import os
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.orm import Session
from src.models.club_access import ClubAccessGrant
from src.models.funding import ClubProgramManager
from src.models.league import UserAccount, db
from src.models.opportunities import ClubOpportunity, now
from src.models.scout_attendance import ScoutAttendance
from src.models.trust import ScoutVerification
from src.services import opportunities as opportunity_service
from src.services.account_standing import is_account_active
from src.services.admin_audit import record_admin_event
from src.services.club_access import club_can, staff_access_enabled
from src.services.club_publication_hold import club_publication_held
from src.services.notification_outbox import enqueue, register_template
from src.services.trust import is_verified_scout

Error = opportunity_service.OpportunityError
STATES = {"pending", "accepted", "declined", "withdrawn", "expired", "revoked", "cancelled"}
SYSTEM = "attendance-system@theacademywatch.com"


def enabled():
    return opportunity_service.enabled("SCOUT_ATTEND_ENABLED")


def verification(user_id):
    return ScoutVerification.query.filter_by(user_account_id=user_id, status="approved").first()


def verified(user_id, *, lock=False):
    if lock:
        db.session.query(UserAccount.id).filter_by(id=user_id).with_for_update().first()
    user = db.session.get(UserAccount, user_id)
    if not is_account_active(user_id) or not is_verified_scout(user):
        raise Error("verified_scout_required", 403)
    return user


def attendance_event(row):
    # P2R permits youth-session adverts; attendance never grants access to any applicant.
    return row.type in {"trial", "open_session"}


def session_future(row):
    return bool((row.starts_at or row.ends_at) and (row.starts_at or row.ends_at) > now())


def session_end_expression():
    # Dates are stored naive UTC; SQLite has no native timestamp + interval.
    fallback = (
        sa.func.datetime(ClubOpportunity.starts_at, "+1 day")
        if db.session.get_bind().dialect.name == "sqlite"
        else ClubOpportunity.starts_at + timedelta(days=1)
    )
    return sa.func.coalesce(ClubOpportunity.ends_at, fallback)


def visible_event(row, *, accepting=False, deciding=False, history=False, ignore_hold=False):
    if not row or not opportunity_service.enabled("OPPORTUNITIES_ENABLED"):
        return False
    listed = (
        opportunity_service.ClubProgram.query.filter_by(id=row.program_id)
        .filter(opportunity_service.public_club_eligibility(ignore_publication_holds=ignore_hold))
        .first()
    )
    if not listed or not attendance_event(row):
        return False
    if history:
        return row.status in {"published", "closed", "cancelled"}
    if accepting:
        return row.status == "published" and row.closes_at > now() and session_future(row)
    return row.status in {"published", "closed"} and (not deciding or session_future(row))


def event(oid, *, lock=False, accepting=True):
    initial = db.session.get(ClubOpportunity, oid)
    if initial is None:
        raise Error("Not found", 404)
    opportunity_service.operational(initial.program_id, lock=lock)
    row = ClubOpportunity.query.filter_by(id=oid).populate_existing()
    row = (row.with_for_update() if lock else row).first()
    if not visible_event(row, accepting=accepting):
        raise Error("Not found", 404)
    return row


def request_row(rid, *, program_id=None, user_id=None, lock=False):
    initial = db.session.get(ScoutAttendance, rid)
    if (
        not initial
        or (program_id is not None and initial.program_id != program_id)
        or (user_id is not None and initial.scout_user_id != user_id)
    ):
        raise Error("Not found", 404)
    event(initial.opportunity_id, lock=lock, accepting=False)
    if lock:
        # Admission and trust revocation share this mutex before request locks.
        with db.session.no_autoflush:
            db.session.query(UserAccount.id).filter_by(id=initial.scout_user_id).with_for_update().first()
    query = ScoutAttendance.query.filter_by(id=rid).populate_existing()
    row = (query.with_for_update() if lock else query).first()
    if not row or row.retention_expires_at <= now():
        raise Error("Not found", 404)
    if user_id is not None:
        verified(row.scout_user_id)
    return row


def serialize(row, *, club=False, opp=None, program=None, scout=None, trusted=None):
    opp = opp or db.session.get(ClubOpportunity, row.opportunity_id)
    program = program or db.session.get(opportunity_service.ClubProgram, row.program_id)
    data = {
        "id": row.id,
        "opportunity_id": row.opportunity_id,
        "program_id": row.program_id,
        "title": opp.title,
        "club_name": program.name,
        "status": row.status,
        "version": row.version,
        "note": row.note,
        "created_at": opportunity_service.iso(row.created_at),
        "updated_at": opportunity_service.iso(row.updated_at),
        "retention_expires_at": opportunity_service.iso(row.retention_expires_at),
    }
    data["can_request_again"] = row.status == "withdrawn" and row.request_count < 2
    if row.status == "accepted" and (
        trusted
        if trusted is not None
        else (
            is_account_active(row.scout_user_id) and is_verified_scout(db.session.get(UserAccount, row.scout_user_id))
        )
    ):
        data["arrival_instructions"] = row.arrival_instructions
    if club:
        scout = scout or verification(row.scout_user_id)
        data["scout"] = {
            "name": scout.full_name,
            "organization": scout.organization,
            "verified": True,
        }
    return data


def audit(row, actor_id, action):
    record_admin_event(
        db.session.get(UserAccount, actor_id) if actor_id else SYSTEM,
        "scout_attendance_" + action,
        "scout_attendance",
        row.id,
        "Scout attendance request",
        {"program_id": row.program_id, "version": row.version},
    )


def notify(row):
    recipients = {row.scout_user_id}
    candidates = {
        m.user_account_id for m in ClubProgramManager.query.filter_by(program_id=row.program_id, status="active")
    }
    if staff_access_enabled():
        candidates |= {
            g.user_account_id for g in ClubAccessGrant.query.filter_by(program_id=row.program_id, status="active")
        }
    recipients |= {uid for uid in candidates if notification_contact(uid, row.program_id, ignore_hold=True)}
    for uid in recipients:
        enqueue(
            dedupe_key=f"c4:{row.id}:{row.version}:{uid}",
            recipient_user_id=uid,
            event_type="scout_attendance_updated",
            entity_type="user_account",
            entity_id=row.scout_user_id,
            template="c4_attendance",
            payload={"attendance_id": row.id, "version": row.version, "state": row.status},
        )


def submit(oid, user_id, data):
    verified(user_id)
    if set(data) - {"note", "no_approach_confirmed"}:
        raise Error("invalid_payload", 400)
    if data.get("no_approach_confirmed") is not True:
        raise Error("no_approach_confirmation_required", 422)
    note = opportunity_service.text(data.get("note", ""), "note", 500, required=False)
    opp = event(oid, lock=True)
    verified(user_id, lock=True)
    old = (
        ScoutAttendance.query.filter_by(opportunity_id=oid, scout_user_id=user_id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if old and old.status == "withdrawn":
        if old.request_count >= 2:
            raise Error("request_retry_used", 409)
        old.request_count += 1
        old.status, old.version, old.updated_at = "pending", old.version + 1, now()
        old.note, old.decision_user_id, old.arrival_instructions = note, None, ""
        audit(old, user_id, "requested_again")
        notify(old)
        return old, False
    if old:
        if old.note != note:
            raise Error("request_exists", 409)
        return old, False
    row = ScoutAttendance(
        opportunity_id=oid,
        program_id=opp.program_id,
        scout_user_id=user_id,
        note=note,
        retention_expires_at=min(
            now() + timedelta(days=180), (opp.ends_at or opp.starts_at or opp.closes_at) + timedelta(days=90)
        ),
    )
    db.session.add(row)
    db.session.flush()
    audit(row, user_id, "requested")
    notify(row)
    return row, True


def decide(rid, program_id, actor_id, data):
    row = request_row(rid, program_id=program_id, lock=True)
    if not club_can(actor_id, program_id, "contact"):
        raise Error("Access denied", 403)
    if set(data) - {"decision", "expected_version", "arrival_instructions"}:
        raise Error("invalid_payload", 400)
    target = data.get("decision")
    if not isinstance(target, str) or target not in {"accepted", "declined"}:
        raise Error("invalid_decision", 422)
    if opportunity_service.integer(data.get("expected_version"), "expected_version") != row.version:
        raise Error("version_conflict", 409)
    if row.status != "pending" and not (row.status == "accepted" and target == "declined"):
        raise Error("already_decided", 409)
    if not visible_event(db.session.get(ClubOpportunity, row.opportunity_id), deciding=row.status == "pending"):
        raise Error("Not found", 404)
    if target == "accepted":
        verified(row.scout_user_id)
    instructions = opportunity_service.text(
        data.get("arrival_instructions", ""), "arrival_instructions", 500, required=target == "accepted"
    )
    row.status, row.version, row.decision_user_id = target, row.version + 1, actor_id
    row.arrival_instructions = instructions if target == "accepted" else ""
    row.updated_at = now()
    audit(row, actor_id, target)
    notify(row)
    return row


def withdraw(rid, user_id, data):
    verified(user_id)
    row = request_row(rid, user_id=user_id, lock=True)
    if set(data) != {"expected_version"}:
        raise Error("invalid_payload", 400)
    if opportunity_service.integer(data.get("expected_version"), "expected_version") != row.version:
        raise Error("version_conflict", 409)
    if row.status not in {"pending", "accepted"}:
        raise Error("already_decided", 409)
    row.status, row.version, row.updated_at = "withdrawn", row.version + 1, now()
    row.arrival_instructions = ""
    audit(row, user_id, "withdrawn")
    notify(row)
    return row


def current_intent(intent, user, *, ignore_hold=False):
    if not enabled() or not is_account_active(user.id):
        return False
    row = db.session.get(ScoutAttendance, intent.payload.get("attendance_id"), populate_existing=True)
    if (
        not row
        or row.version != intent.payload.get("version")
        or row.status != intent.payload.get("state")
        or row.retention_expires_at <= now()
    ):
        return False
    # Neutral terminal notices must reach the club even after the scout loses trust.
    if row.status in {"pending", "accepted"}:
        try:
            verified(row.scout_user_id)
        except Error:
            return False
    if not visible_event(db.session.get(ClubOpportunity, row.opportunity_id), history=True, ignore_hold=ignore_hold):
        return False
    if row.scout_user_id == user.id:
        return True
    return notification_contact(user.id, row.program_id, ignore_hold=ignore_hold)


def notification_contact(user_id, program_id, *, ignore_hold=False):
    if club_can(user_id, program_id, "contact"):
        return True
    if not ignore_hold or not club_publication_held(program_id) or not is_account_active(user_id):
        return False
    # Emergency holds veto club_can, but never turn a non-contact into a recipient.
    from src.models.funding import ClubProgramClaim

    owner = (
        ClubProgramManager.query.join(
            ClubProgramClaim,
            sa.and_(
                ClubProgramClaim.id == ClubProgramManager.source_claim_id,
                ClubProgramClaim.program_id == ClubProgramManager.program_id,
                ClubProgramClaim.user_account_id == ClubProgramManager.user_account_id,
            ),
        )
        .filter(
            ClubProgramManager.program_id == program_id,
            ClubProgramManager.user_account_id == user_id,
            ClubProgramManager.status == "active",
            ClubProgramClaim.status == "approved",
        )
        .first()
    )
    # Contact is VERIFIED_ONLY: an invited manager grant cannot replace the
    # authoritative approved manager claim, even during a publication hold.
    return bool(owner)


def eligible(intent, user):
    return current_intent(intent, user)


def deferred(intent, user):
    return current_intent(intent, user, ignore_hold=True) and club_publication_held(
        db.session.get(ScoutAttendance, intent.payload["attendance_id"]).program_id
    )


def render(intent, user):
    row = db.session.get(ScoutAttendance, intent.payload["attendance_id"])
    base = os.getenv("PUBLIC_BASE_URL", "https://theacademywatch.com").rstrip("/")
    link = base + (
        "/scout?desk=clubs" if user.id == row.scout_user_id else f"/my-club?program={row.program_id}&view=today"
    )
    message = {
        "expired": "The session has started. This attendance request has expired.",
        "revoked": "An attendance permission is no longer valid.",
        "cancelled": "The session has been cancelled. Attendance permission is no longer valid.",
        "declined": "Attendance permission has not been granted or has been withdrawn by the club.",
    }.get(row.status, "An attendance request has an update. Sign in to view it.")
    if row.status == "accepted" and db.session.get(ClubOpportunity, row.opportunity_id).status == "closed":
        message = (
            "Session intake has closed. Your accepted attendance permission remains valid. Sign in to view it."
            if user.id == row.scout_user_id
            else "Session intake has closed. Accepted scout attendance permissions remain valid. Sign in to view them."
        )
    return {
        "subject": "Scout attendance update",
        "html": f'<p>{message}</p><a href="{link}">View update</a>',
        "text": f"{message} {link}",
    }


def register_notifications():
    register_template(
        "c4_attendance", eligible=eligible, defer=deferred, render=render, payload_enums={"state": STATES}
    )


def lock_requests(query):
    """Serialize every lifecycle mutation in program -> opportunity -> request order."""
    with db.session.no_autoflush:
        keys = [(r.id, r.program_id, r.opportunity_id) for r in query.all()]
        if not keys:
            return []
        opportunity_service.ClubProgram.query.filter(
            opportunity_service.ClubProgram.id.in_({k[1] for k in keys})
        ).order_by(opportunity_service.ClubProgram.id).with_for_update().all()
        ClubOpportunity.query.filter(ClubOpportunity.id.in_({k[2] for k in keys})).order_by(
            ClubOpportunity.program_id, ClubOpportunity.id
        ).with_for_update().all()
        return (
            ScoutAttendance.query.filter(ScoutAttendance.id.in_([k[0] for k in keys]))
            .order_by(ScoutAttendance.id)
            .populate_existing()
            .with_for_update()
            .all()
        )


def finish(row, state, actor_id=None):
    row.status, row.version, row.updated_at = state, row.version + 1, now()
    row.arrival_instructions = ""
    row.decision_user_id = actor_id
    audit(row, actor_id, state)
    notify(row)


def revoke_user(user_id):
    # Runs independently of the rollout flag, including after rollback.
    if not sa.inspect(db.session.connection()).has_table("scout_attendance_requests"):
        return 0
    # Never acquire program/opportunity locks here: their holders can wait for
    # this scout mutex during admission. Requery AFTER the mutex so newly committed
    # requests cannot escape revocation or force a later program-lock discovery.
    with db.session.no_autoflush:
        db.session.query(UserAccount.id).filter_by(id=user_id).with_for_update().first()
        rows = (
            ScoutAttendance.query.filter_by(scout_user_id=user_id)
            .filter(ScoutAttendance.status.in_(("pending", "accepted")))
            .order_by(ScoutAttendance.id)
            .populate_existing()
            .with_for_update()
            .all()
        )
    for row in rows:
        if row.status in {"pending", "accepted"}:
            finish(row, "revoked")
    return len(rows)


def session_closed(opportunity, actor_id):
    if not sa.inspect(db.session.connection()).has_table("scout_attendance_requests"):
        return
    rows = lock_requests(
        ScoutAttendance.query.filter_by(opportunity_id=opportunity.id).filter(
            ScoutAttendance.status.in_(("pending", "accepted"))
        )
    )
    for row in rows:
        if row.status not in {"pending", "accepted"}:
            continue
        if opportunity.status == "cancelled":
            finish(row, "cancelled", actor_id)
        elif row.status == "accepted":
            # Closing intake does not cancel a future session or permission.
            row.version, row.updated_at = row.version + 1, now()
            audit(row, actor_id, "intake_closed")
            notify(row)


def expire_pending(*, program_id=None, user_id=None, limit=100):
    query = ScoutAttendance.query.join(ClubOpportunity, ClubOpportunity.id == ScoutAttendance.opportunity_id).filter(
        ScoutAttendance.status == "pending",
        sa.func.coalesce(ClubOpportunity.starts_at, ClubOpportunity.ends_at) <= now(),
    )
    if program_id is not None:
        query = query.filter(ScoutAttendance.program_id == program_id)
    if user_id is not None:
        query = query.filter(ScoutAttendance.scout_user_id == user_id)
    rows = lock_requests(query.order_by(ScoutAttendance.id).limit(limit))
    count = 0
    for row in rows:
        if row.status == "pending" and not session_future(db.session.get(ClubOpportunity, row.opportunity_id)):
            finish(row, "expired")
            count += 1
    return count


def changed_trust_ids(session):
    ids = {
        r.user_account_id
        for r in session.dirty
        if isinstance(r, ScoutVerification)
        and r.status != "approved"
        and sa.inspect(r).attrs.status.history.has_changes()
    }
    ids |= {
        r.id
        for r in session.dirty
        if isinstance(r, UserAccount)
        and (r.account_status != "active" or r.is_tombstone)
        and (
            sa.inspect(r).attrs.account_status.history.has_changes()
            or sa.inspect(r).attrs.is_tombstone.history.has_changes()
        )
    }
    return ids


def remember_trust_changes(session):
    ids = changed_trust_ids(session)
    if not ids or not sa.inspect(session.connection()).has_table("scout_attendance_requests"):
        return
    # Before the trust UPDATE, serialize with admission, including explicit/autoflush.
    # Select only the key so a dirty UserAccount's new standing is never overwritten.
    with session.no_autoflush:
        session.query(UserAccount.id).filter(UserAccount.id.in_(ids)).order_by(UserAccount.id).with_for_update().all()
    session.info.setdefault("c4_changed_trust", set()).update(ids)


@sa.event.listens_for(Session, "before_flush")
def remember_flushed_trust(session, flush_context, instances):
    remember_trust_changes(session)


@sa.event.listens_for(Session, "before_commit")
def revoke_changed_trust(session):
    """Reconcile direct ORM moderation and flushed maintenance in their transaction.

    Bulk SQL moderation must call revoke_user explicitly; ordinary transactions do
    no extra work. Revocation holds scout/request locks, never program locks.
    """
    if session.info.get("c4_reconciling"):
        return
    remember_trust_changes(session)
    ids = session.info.pop("c4_changed_trust", set())
    if not ids:
        return
    session.info["c4_reconciling"] = True
    try:
        session.flush()
        for user_id in sorted(ids):
            try:
                verified(user_id)
            except Error:
                revoke_user(user_id)
        session.info.pop("c4_changed_trust", None)
    finally:
        session.info.pop("c4_reconciling", None)


@sa.event.listens_for(Session, "after_soft_rollback")
def clear_rolled_back_trust(session, previous_transaction):
    # A savepoint rollback must not lose changes belonging to the outer transaction.
    if not previous_transaction.nested:
        session.info.pop("c4_changed_trust", None)


def revoke_ineligible(*, program_id=None, limit=100):
    """Bounded safety sweep for SQL/bulk moderation outside the ordinary ORM path."""
    approved = sa.exists(
        sa.select(ScoutVerification.id).where(
            ScoutVerification.user_account_id == ScoutAttendance.scout_user_id, ScoutVerification.status == "approved"
        )
    )
    query = ScoutAttendance.query.join(UserAccount, UserAccount.id == ScoutAttendance.scout_user_id).filter(
        ScoutAttendance.status.in_(("pending", "accepted")),
        sa.or_(~approved, UserAccount.account_status != "active", UserAccount.is_tombstone.is_(True)),
    )
    if program_id is not None:
        query = query.filter(ScoutAttendance.program_id == program_id)
    rows = lock_requests(query.order_by(ScoutAttendance.id).limit(limit))
    count = 0
    for row in rows:
        if row.status in {"pending", "accepted"}:
            try:
                verified(row.scout_user_id)
            except Error:
                finish(row, "revoked")
                count += 1
    return count


def lock_user_attendance(user_id):
    if not sa.inspect(db.session.connection()).has_table("scout_attendance_requests"):
        return
    with db.session.no_autoflush:
        db.session.query(UserAccount.id).filter_by(id=user_id).with_for_update().first()
