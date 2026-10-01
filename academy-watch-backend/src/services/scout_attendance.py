"""Atomic attendance state/audit/intents; fresh trust and listing checks on every read."""

import os
from datetime import timedelta

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
from src.services.club_directory import is_listed
from src.services.club_publication_hold import club_publication_held
from src.services.notification_outbox import enqueue, register_template
from src.services.trust import is_verified_scout

Error = opportunity_service.OpportunityError
STATES = {"pending", "accepted", "declined", "withdrawn"}


def enabled():
    return opportunity_service.enabled("SCOUT_ATTEND_ENABLED")


def verification(user_id):
    return ScoutVerification.query.filter_by(user_account_id=user_id, status="approved").first()


def verified(user_id):
    user = db.session.get(UserAccount, user_id)
    if not is_account_active(user_id) or not is_verified_scout(user):
        raise Error("verified_scout_required", 403)
    return user


def adult_event(row):
    # An explicit, unambiguously adult year band. Unknown / youth session bands stay off the scout surface.
    return (
        row.type in {"trial", "open_session"}
        and row.birth_year_max is not None
        and row.birth_year_max < now().year - 18
    )


def visible_event(row, *, accepting=False):
    if not row or not opportunity_service.enabled("OPPORTUNITIES_ENABLED"):
        return False
    program = opportunity_service.db.session.get(opportunity_service.ClubProgram, row.program_id)
    if not program or not is_listed(program) or club_publication_held(row.program_id) or not adult_event(row):
        return False
    return (
        row.status in ({"published"} if accepting else {"published", "closed"})
        and (not accepting or row.closes_at > now())
        and (not accepting or not row.starts_at or row.starts_at > now())
    )


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
    query = ScoutAttendance.query.filter_by(id=rid).populate_existing()
    row = (query.with_for_update() if lock else query).first()
    if not row or row.retention_expires_at <= now():
        raise Error("Not found", 404)
    verified(row.scout_user_id)
    return row


def serialize(row, *, club=False):
    opp = db.session.get(ClubOpportunity, row.opportunity_id)
    data = {
        "id": row.id,
        "opportunity_id": row.opportunity_id,
        "program_id": row.program_id,
        "title": opp.title,
        "club_name": db.session.get(opportunity_service.ClubProgram, row.program_id).name,
        "status": row.status,
        "version": row.version,
        "note": row.note,
        "created_at": opportunity_service.iso(row.created_at),
        "updated_at": opportunity_service.iso(row.updated_at),
        "retention_expires_at": opportunity_service.iso(row.retention_expires_at),
    }
    if row.status == "accepted":
        data["arrival_instructions"] = row.arrival_instructions
    if club:
        scout = verification(row.scout_user_id)
        data["scout"] = {
            "name": scout.full_name,
            "organization": scout.organization,
            "role_title": scout.role_title,
            "verified": True,
        }
    return data


def audit(row, actor_id, action):
    record_admin_event(
        db.session.get(UserAccount, actor_id),
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
    recipients |= {uid for uid in candidates if club_can(uid, row.program_id, "contact")}
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
    old = ScoutAttendance.query.filter_by(opportunity_id=oid, scout_user_id=user_id).first()
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
    if not visible_event(db.session.get(ClubOpportunity, row.opportunity_id), accepting=True):
        raise Error("Not found", 404)
    if not club_can(actor_id, program_id, "contact"):
        raise Error("Access denied", 403)
    if set(data) - {"decision", "expected_version", "arrival_instructions"}:
        raise Error("invalid_payload", 400)
    target = data.get("decision")
    if not isinstance(target, str) or target not in {"accepted", "declined"}:
        raise Error("invalid_decision", 422)
    if opportunity_service.integer(data.get("expected_version"), "expected_version") != row.version:
        raise Error("version_conflict", 409)
    if row.status != "pending":
        raise Error("already_decided", 409)
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


def eligible(intent, user):
    if not enabled():
        return False
    row = db.session.get(ScoutAttendance, intent.payload.get("attendance_id"), populate_existing=True)
    if (
        not row
        or row.version != intent.payload.get("version")
        or row.status != intent.payload.get("state")
        or row.retention_expires_at <= now()
    ):
        return False
    try:
        verified(row.scout_user_id)
    except Error:
        return False
    return visible_event(db.session.get(ClubOpportunity, row.opportunity_id), accepting=False) and (
        row.scout_user_id == user.id or club_can(user.id, row.program_id, "contact")
    )


def render(intent, user):
    row = db.session.get(ScoutAttendance, intent.payload["attendance_id"])
    base = os.getenv("PUBLIC_BASE_URL", "https://theacademywatch.com").rstrip("/")
    link = base + (
        "/scout?desk=clubs" if user.id == row.scout_user_id else f"/my-club?program={row.program_id}&view=today"
    )
    return {
        "subject": "Scout attendance update",
        "html": f'<p>An attendance request has an update. Sign in to view it.</p><a href="{link}">View update</a>',
        "text": f"An attendance request has an update. Sign in to view it. {link}",
    }


def register_notifications():
    register_template("c4_attendance", eligible=eligible, render=render, payload_enums={"state": STATES})
