"""Caller-owned transactions: authority, state, event and delivery intent are atomic."""

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import sqlalchemy as sa
from src.models.funding import ClubProgram, ClubProgramManager, ClubSquad
from src.models.league import UserAccount, db
from src.models.opportunities import (
    STATES,
    TERMINAL,
    ApplicationEvent,
    ApplicationNote,
    ClubOpportunity,
    OpportunityApplication,
    now,
)
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.tracked_player import TrackedPlayer
from src.services.admin_audit import record_admin_event
from src.services.club_access import club_can
from src.services.club_publication_hold import club_publication_held
from src.services.notification_outbox import enqueue, register_template
from src.services.public_adult import is_public_adult

TRANSITIONS = {
    "new": {"shortlisted", "rejected"},
    "shortlisted": {"invited", "rejected"},
    "invited": {"attended", "rejected"},
    "attended": {"offer", "rejected"},
    "offer": {"signed", "rejected"},
}
LABELS = {
    "new": "Applied",
    "shortlisted": "With the club",
    "invited": "Invited to trial",
    "attended": "Trial attended",
    "offer": "Offer received",
    "signed": "Signed",
    "rejected": "Not selected",
    "withdrawn": "Withdrawn",
}
RESERVED = ("pending", "confirmed")


class OpportunityError(ValueError):
    def __init__(self, code, status=422):
        self.code, self.status = code, status
        super().__init__(code)


def enabled(flag):
    return os.getenv(flag, "false").strip().lower() in {"1", "true", "yes", "on"}


def applications_enabled():
    return enabled("OPPORTUNITIES_ENABLED") and enabled("APPLICATIONS_ENABLED")


def integer(value, key, *, minimum=1, maximum=2147483647, nullable=False):
    if nullable and value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise OpportunityError(f"invalid_{key}")
    return value


def text(value, key, limit, *, required=True):
    if not isinstance(value, str) or len(value.strip()) > limit or (required and not value.strip()):
        raise OpportunityError(f"invalid_{key}")
    return value.strip()


def timestamp(value, key, *, nullable=False):
    if nullable and value is None:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(UTC).replace(tzinfo=None)
    except (ValueError, TypeError, AttributeError):
        raise OpportunityError(f"invalid_{key}") from None


def iso(value):
    return value.replace(tzinfo=UTC).isoformat() if value else None


def operational(program_id, *, lock=False):
    query = ClubProgram.query.filter_by(id=program_id).populate_existing()
    program = (query.with_for_update() if lock else query).first()
    if not program or program.platform_status != "approved" or club_publication_held(program_id):
        raise OpportunityError("Not found", 404)
    return program


def recruit(program_id, actor_id):
    operational(program_id, lock=True)
    if not club_can(actor_id, program_id, "recruiting"):
        raise OpportunityError("Access denied", 403)


def opportunity(oid, program_id=None, *, lock=False, public=False):
    query = ClubOpportunity.query.filter_by(id=oid).populate_existing()
    if program_id is not None:
        query = query.filter_by(program_id=program_id)
    row = (query.with_for_update() if lock else query).first()
    if row is None:
        raise OpportunityError("Not found", 404)
    operational(row.program_id)
    if public and (row.status != "published" or row.closes_at <= now()):
        raise OpportunityError("Not found", 404)
    return row


def reservations(oid):
    return OpportunityApplication.query.filter(
        OpportunityApplication.opportunity_id == oid, OpportunityApplication.reservation_state.in_(RESERVED)
    ).count()


def opportunity_dict(row, *, private=False):
    program = db.session.get(ClubProgram, row.program_id)
    squad = db.session.get(ClubSquad, row.squad_id) if row.squad_id else None
    data = {
        key: getattr(row, key)
        for key in (
            "id",
            "program_id",
            "squad_id",
            "type",
            "title",
            "description",
            "instructions",
            "position_requirements",
            "birth_year_min",
            "birth_year_max",
            "gender_program",
            "timezone",
            "venue",
            "address",
            "status",
            "version",
        )
    }
    data.update(
        club_name=program.name,
        club_slug=program.slug,
        squad_name=squad.name if squad else None,
        coach="Club coaching team",
    )
    for key in ("starts_at", "ends_at", "closes_at", "published_at"):
        data[key] = iso(getattr(row, key))
    reserved = reservations(row.id) if applications_enabled() or private else 0
    if private or (reserved and row.capacity is not None):
        data.update(
            capacity=row.capacity, places_left=max(0, row.capacity - reserved) if row.capacity is not None else None
        )
    if private:
        data["application_count"] = OpportunityApplication.query.filter_by(opportunity_id=row.id).count()
    return data


def public_query(program_id=None):
    q = ClubOpportunity.query.join(ClubProgram, ClubProgram.id == ClubOpportunity.program_id).filter(
        ClubOpportunity.status == "published",
        ClubOpportunity.closes_at > now(),
        ClubProgram.platform_status == "approved",
        ClubProgram.emergency_hidden.is_(False),
    )
    return q.filter(ClubOpportunity.program_id == program_id) if program_id else q


def open_opportunity_counts(program_ids):
    """Directory contract; no dependency on B1's schema, no counts while dark."""
    if not enabled("OPPORTUNITIES_ENABLED"):
        return {}
    return dict(
        public_query()
        .filter(ClubOpportunity.program_id.in_(program_ids))
        .with_entities(ClubOpportunity.program_id, sa.func.count(ClubOpportunity.id))
        .group_by(ClubOpportunity.program_id)
        .all()
    )


def save_opportunity(program_id, actor_id, data, oid=None):
    recruit(program_id, actor_id)
    if oid:
        row = opportunity(oid, program_id, lock=True)
        if integer(data.get("expected_version"), "expected_version") != row.version:
            raise OpportunityError("version_conflict", 409)
        if row.status in {"closed", "cancelled"}:
            raise OpportunityError("opportunity_closed", 409)
    else:
        row = ClubOpportunity(
            program_id=program_id,
            creator_user_id=actor_id,
            type="trial",
            title="",
            description="",
            instructions="",
            position_requirements="All positions",
            gender_program="all",
            timezone="UTC",
            venue="",
            address="",
            status="draft",
            version=1,
            created_at=now(),
        )
    allowed = {
        "expected_version",
        "type",
        "title",
        "description",
        "instructions",
        "position_requirements",
        "birth_year_min",
        "birth_year_max",
        "gender_program",
        "starts_at",
        "ends_at",
        "timezone",
        "venue",
        "address",
        "capacity",
        "closes_at",
        "squad_id",
        "status",
    }
    if set(data) - allowed:
        raise OpportunityError("invalid_fields")
    if oid and OpportunityApplication.query.filter_by(opportunity_id=oid).first():
        locked = {
            "type",
            "squad_id",
            "birth_year_min",
            "birth_year_max",
            "gender_program",
            "position_requirements",
            "starts_at",
            "ends_at",
            "timezone",
            "venue",
            "address",
            "closes_at",
        }
        if set(data) & locked:
            raise OpportunityError("eligibility_and_schedule_locked", 409)
    for key, limit in {
        "title": 180,
        "description": 6000,
        "instructions": 3000,
        "position_requirements": 200,
        "venue": 200,
        "address": 300,
        "timezone": 80,
    }.items():
        if key in data:
            setattr(row, key, text(data[key], key, limit, required=key not in {"instructions", "address"}))
    for key in ("starts_at", "ends_at", "closes_at"):
        if key in data:
            setattr(row, key, timestamp(data[key], key, nullable=key != "closes_at"))
    for key in ("birth_year_min", "birth_year_max"):
        if key in data:
            setattr(row, key, integer(data[key], key, minimum=1900, maximum=now().year, nullable=True))
    if "capacity" in data:
        row.capacity = integer(data["capacity"], "capacity", maximum=10000, nullable=True)
        if oid and row.capacity is not None and row.capacity < reservations(oid):
            raise OpportunityError("capacity_reserved", 409)
    if "squad_id" in data:
        row.squad_id = integer(data["squad_id"], "squad_id", nullable=True)
        if row.squad_id and not ClubSquad.query.filter_by(id=row.squad_id, program_id=program_id).first():
            raise OpportunityError("invalid_squad_id")
    for key, values in {
        "type": {"trial", "open_session", "position"},
        "gender_program": {"all", "boys", "girls", "men", "women", "mixed"},
    }.items():
        if key in data:
            if not isinstance(data[key], str) or data[key] not in values:
                raise OpportunityError(f"invalid_{key}")
            setattr(row, key, data[key])
    try:
        ZoneInfo(row.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise OpportunityError("invalid_timezone") from None
    if not row.title or not row.description or not row.venue or row.closes_at is None or row.closes_at <= now():
        raise OpportunityError("required_opportunity_details")
    if row.closes_at > row.created_at + timedelta(days=365):
        raise OpportunityError("deadline_too_far")
    if row.type != "position" and row.starts_at is None:
        raise OpportunityError("event_date_required")
    if row.starts_at and (row.starts_at < row.closes_at or row.starts_at > row.created_at + timedelta(days=365)):
        raise OpportunityError("invalid_event_dates")
    if row.ends_at and (not row.starts_at or row.ends_at <= row.starts_at):
        raise OpportunityError("invalid_event_dates")
    if row.birth_year_min and row.birth_year_max and row.birth_year_min > row.birth_year_max:
        raise OpportunityError("invalid_age_band")
    target = data.get("status", row.status)
    if (
        not isinstance(target, str)
        or target not in {"draft", "published"}
        or (row.status == "published" and target == "draft")
    ):
        raise OpportunityError("invalid_status")
    if target == "published" and row.status == "draft":
        row.published_at = now()
    row.status, row.updated_at = target, now()
    if oid:
        row.version += 1
    db.session.add(row)
    db.session.flush()
    record_admin_event(
        db.session.get(UserAccount, actor_id),
        "opportunity_saved",
        "club_opportunity",
        row.id,
        "Club opportunity saved",
        {"program_id": program_id, "version": row.version},
    )
    return row


def close_opportunity(program_id, actor_id, oid, data):
    recruit(program_id, actor_id)
    row = opportunity(oid, program_id, lock=True)
    if integer(data.get("expected_version"), "expected_version") != row.version:
        raise OpportunityError("version_conflict", 409)
    target = data.get("status", "closed")
    if not isinstance(target, str) or target not in {"closed", "cancelled"} or row.status == "cancelled":
        raise OpportunityError("invalid_status")
    row.status, row.closed_at, row.updated_at = target, now(), now()
    row.version += 1
    for app in (
        OpportunityApplication.query.filter_by(opportunity_id=oid)
        .order_by(OpportunityApplication.id)
        .with_for_update()
        .all()
    ):
        app.retention_expires_at = min(app.retention_expires_at, now() + timedelta(days=90))
        if target == "cancelled" and app.status not in TERMINAL:
            mutate(app, actor_id, "rejected", "opportunity_cancelled")
    record_admin_event(
        db.session.get(UserAccount, actor_id),
        "opportunity_" + target,
        "club_opportunity",
        row.id,
        "Club opportunity lifecycle",
        {"program_id": program_id, "version": row.version},
    )
    return row


def adult_claim(claim_id, user_id):
    claim = (
        PlayerProfileClaim.query.filter_by(
            id=claim_id, user_account_id=user_id, relationship_type="player", status="approved"
        )
        .populate_existing()
        .first()
    )
    if claim is None:
        raise OpportunityError("approved_adult_self_claim_required", 403)
    pid = claim.player_api_id or (-claim.local_player_id if claim.local_player_id else None)
    if not is_public_adult(pid):
        raise OpportunityError("approved_adult_self_claim_required", 403)
    source = (
        db.session.get(LocalPlayer, claim.local_player_id)
        if claim.local_player_id
        else TrackedPlayer.query.filter_by(player_api_id=pid).first()
    )
    if source is None:
        from src.models.follow import PlayerShadow

        source = PlayerShadow.query.filter_by(player_api_id=pid, is_active=True).first()
    return claim, pid, source


def eligible_claims(user_id):
    items = []
    for claim in PlayerProfileClaim.query.filter_by(
        user_account_id=user_id, relationship_type="player", status="approved"
    ).all():
        try:
            _, pid, source = adult_claim(claim.id, user_id)
        except OpportunityError:
            continue
        items.append(
            {
                "claim_id": claim.id,
                "signed_player_id": pid,
                "name": getattr(source, "display_name", None) or getattr(source, "player_name", None) or "Your profile",
            }
        )
    return items


def submit(oid, user_id, data):
    # Lock the receiving program then opportunity for every mutation; never reverse the order.
    initial = opportunity(oid, public=True)
    operational(initial.program_id, lock=True)
    row = opportunity(oid, lock=True, public=True)
    if set(data) - {"claim_id", "position", "current_club", "contact_consent", "client_request_id"}:
        raise OpportunityError("invalid_fields")
    if data.get("contact_consent") is not True:
        raise OpportunityError("contact_consent_required")
    try:
        key = str(UUID(data.get("client_request_id")))
    except (ValueError, TypeError, AttributeError):
        raise OpportunityError("invalid_client_request_id") from None
    claim, pid, source = adult_claim(integer(data.get("claim_id"), "claim_id"), user_id)
    birth_date = getattr(source, "birth_date", None)
    birth_year = getattr(source, "birth_year", None) or (int(str(birth_date)[:4]) if birth_date else None)
    if (row.birth_year_min or row.birth_year_max) and (
        not birth_year
        or (row.birth_year_min and birth_year < row.birth_year_min)
        or (row.birth_year_max and birth_year > row.birth_year_max)
    ):
        raise OpportunityError("outside_age_band", 403)
    position = text(data.get("position"), "position", 80)
    club = text(data.get("current_club", ""), "current_club", 180, required=False)
    digest = hashlib.sha256(
        json.dumps(
            {
                "opportunity_id": oid,
                "claim_id": claim.id,
                "position": position,
                "current_club": club,
                "contact_consent": True,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    existing = OpportunityApplication.query.filter_by(applicant_user_id=user_id, client_request_id=key).first()
    if existing:
        if existing.request_hash != digest:
            raise OpportunityError("request_conflict", 409)
        return existing, False
    if OpportunityApplication.query.filter_by(opportunity_id=oid, signed_player_id=pid).first():
        raise OpportunityError("already_applied", 409)
    deadline = (row.ends_at or row.starts_at or row.closes_at) + timedelta(days=90)
    app = OpportunityApplication(
        opportunity_id=oid,
        program_id=row.program_id,
        applicant_user_id=user_id,
        claim_id=claim.id,
        signed_player_id=pid,
        position=position,
        current_club=club,
        contact_consent_at=now(),
        retention_expires_at=min(deadline, now() + timedelta(days=180)),
        client_request_id=key,
        request_hash=digest,
    )
    db.session.add(app)
    db.session.flush()
    event(app, user_id, None, "submitted")
    notify(app)
    return app, True


def application(aid, *, user_id=None, program_id=None, lock=False):
    query = OpportunityApplication.query.filter_by(id=aid).populate_existing()
    if user_id is not None:
        query = query.filter_by(applicant_user_id=user_id)
    if program_id is not None:
        query = query.filter_by(program_id=program_id)
    app = (query.with_for_update() if lock else query).first()
    if app is None or app.retention_expires_at <= now():
        raise OpportunityError("Not found", 404)
    return app


def event(app, actor_id, previous, reason):
    db.session.add(
        ApplicationEvent(
            application_id=app.id,
            actor_user_id=actor_id,
            from_state=previous,
            to_state=app.status,
            reason_code=reason,
            version=app.version,
        )
    )


def mutate(app, actor_id, target, reason):
    previous = app.status
    app.status, app.version = target, app.version + 1
    if target in TERMINAL:
        app.reservation_state = "released"
    if target == "withdrawn":
        app.withdrawn_at = now()
    event(app, actor_id, previous, reason)
    notify(app)


def transition(program_id, actor_id, aid, data):
    recruit(program_id, actor_id)
    initial = application(aid, program_id=program_id)
    row = opportunity(initial.opportunity_id, program_id, lock=True)
    app = application(aid, program_id=program_id, lock=True)
    if integer(data.get("expected_version"), "expected_version") != app.version:
        raise OpportunityError("version_conflict", 409)
    target = data.get("status")
    if not isinstance(target, str):
        raise OpportunityError("invalid_status")
    if target != "rejected":
        adult_claim(app.claim_id, app.applicant_user_id)
    if target == "invited" and app.status == "invited":
        reason = "rescheduled"
    elif target not in TRANSITIONS.get(app.status, set()):
        raise OpportunityError("invalid_transition", 409)
    else:
        reason = {"invited": "trial_invited", "signed": "signed_recorded", "rejected": "not_selected"}.get(
            target, "stage_changed"
        )
    if row.status == "cancelled":
        raise OpportunityError("opportunity_cancelled", 409)
    if target == "invited":
        if app.reservation_state not in RESERVED and row.capacity is not None and reservations(row.id) >= row.capacity:
            raise OpportunityError("trial_full", 409)
        app.trial_at = timestamp(data.get("trial_at"), "trial_at")
        if app.trial_at <= now() or app.trial_at > app.retention_expires_at:
            raise OpportunityError("invalid_trial_at")
        app.trial_venue = text(data.get("trial_venue"), "trial_venue", 200)
        app.trial_instructions = text(data.get("trial_instructions", ""), "trial_instructions", 3000, required=False)
        app.reservation_state = "pending"
    if target == "attended" and (app.reservation_state != "confirmed" or app.trial_at > now()):
        raise OpportunityError("confirmed_completed_trial_required", 409)
    if target == "signed" and data.get("enrollment_confirmed") is not True:
        raise OpportunityError("separate_enrollment_required")
    mutate(app, actor_id, target, reason)
    record_admin_event(
        db.session.get(UserAccount, actor_id),
        "application_transition",
        "opportunity_application",
        app.id,
        "Recruiting state changed",
        {"program_id": program_id, "version": app.version, "state": target},
    )
    return app


def applicant_action(aid, user_id, data, action):
    initial = application(aid, user_id=user_id)
    # Withdrawal remains available under a club hold or revoked self-claim.
    ClubProgram.query.filter_by(id=initial.program_id).with_for_update().first()
    row = ClubOpportunity.query.filter_by(id=initial.opportunity_id).with_for_update().first()
    app = application(aid, user_id=user_id, lock=True)
    if integer(data.get("expected_version"), "expected_version") != app.version:
        raise OpportunityError("version_conflict", 409)
    if action == "withdraw":
        if app.status in TERMINAL:
            raise OpportunityError("invalid_transition", 409)
        mutate(app, user_id, "withdrawn", "applicant_withdrew")
    else:
        operational(app.program_id)
        adult_claim(app.claim_id, user_id)
        if (
            app.status != "invited"
            or app.reservation_state != "pending"
            or row.status == "cancelled"
            or app.trial_at <= now()
        ):
            raise OpportunityError("invitation_unavailable", 409)
        response = data.get("response")
        if not isinstance(response, str) or response not in {"accept", "decline"}:
            raise OpportunityError("invalid_response")
        if response == "decline":
            mutate(app, user_id, "withdrawn", "trial_declined")
            app.reservation_state = "declined"
        else:
            app.reservation_state, app.version = "confirmed", app.version + 1
            event(app, user_id, app.status, "trial_confirmed")
            notify(app)
    return app


def add_note(program_id, actor_id, aid, data):
    recruit(program_id, actor_id)
    app = application(aid, program_id=program_id, lock=True)
    body = text(data.get("body"), "body", 3000)
    note = ApplicationNote(application_id=app.id, author_user_id=actor_id, body=body)
    db.session.add(note)
    db.session.flush()
    return note


def application_dict(app, *, private=False):
    row = db.session.get(ClubOpportunity, app.opportunity_id)
    data = {
        key: getattr(app, key)
        for key in (
            "id",
            "opportunity_id",
            "program_id",
            "claim_id",
            "signed_player_id",
            "status",
            "position",
            "current_club",
            "version",
            "reservation_state",
            "trial_venue",
            "trial_instructions",
        )
    }
    data.update(
        status_label=LABELS[app.status],
        opportunity_title=row.title,
        club_name=db.session.get(ClubProgram, app.program_id).name,
    )
    for key in ("submitted_at", "withdrawn_at", "trial_at", "retention_expires_at"):
        data[key] = iso(getattr(app, key))
    if private:
        try:
            _, _, source = adult_claim(app.claim_id, app.applicant_user_id)
            data["applicant_name"] = (
                getattr(source, "display_name", None) or getattr(source, "player_name", None) or "Adult applicant"
            )
            data["profile_available"] = True
        except OpportunityError:
            data["applicant_name"], data["profile_available"] = "Profile unavailable", False
        data["notes"] = [
            {"id": n.id, "body": n.body, "created_at": iso(n.created_at)}
            for n in ApplicationNote.query.filter_by(application_id=app.id).order_by(ApplicationNote.created_at).all()
        ]
        data["events"] = [
            {
                "from_state": e.from_state,
                "to_state": e.to_state,
                "reason_code": e.reason_code,
                "version": e.version,
                "created_at": iso(e.created_at),
            }
            for e in ApplicationEvent.query.filter_by(application_id=app.id).order_by(ApplicationEvent.version).all()
        ]
        data["transitions"] = sorted(TRANSITIONS.get(app.status, set()))
    return data


def notify(app):
    recipients = {app.applicant_user_id}
    from src.models.club_access import ClubAccessGrant

    candidates = {
        m.user_account_id for m in ClubProgramManager.query.filter_by(program_id=app.program_id, status="active").all()
    }
    if enabled("CLUB_STAFF_ACCESS_ENABLED"):
        candidates |= {
            g.user_account_id for g in ClubAccessGrant.query.filter_by(program_id=app.program_id, status="active").all()
        }
    recipients |= {uid for uid in candidates if club_can(uid, app.program_id, "recruiting")}
    for recipient in recipients:
        enqueue(
            dedupe_key=f"b2:{app.id}:{app.version}:{recipient}",
            recipient_user_id=recipient,
            event_type="application_updated",
            entity_type="user_account",
            entity_id=app.applicant_user_id,
            template="b2_application",
            payload={"application_id": app.id, "version": app.version, "state": app.status},
        )


def notification_eligible(intent, user):
    if not applications_enabled():
        return False
    app = db.session.get(OpportunityApplication, intent.payload.get("application_id"), populate_existing=True)
    if (
        not app
        or app.version != intent.payload.get("version")
        or app.status != intent.payload.get("state")
        or app.retention_expires_at <= now()
    ):
        return False
    try:
        operational(app.program_id)
        adult_claim(app.claim_id, app.applicant_user_id)
    except OpportunityError:
        return False
    return app.applicant_user_id == user.id or club_can(user.id, app.program_id, "recruiting")


def notification_render(intent, user):
    # Neutral authenticated destination, no names/notes, credentials or copied profile data.
    base = os.getenv("PUBLIC_BASE_URL", "https://theacademywatch.com").rstrip("/")
    link = base + "/onboarding/player"
    app = db.session.get(OpportunityApplication, intent.payload["application_id"])
    if user.id != app.applicant_user_id:
        link = base + "/my-club?view=recruiting"
    return {
        "subject": "Your application update",
        "html": f'<p>An application has an update. Sign in to view the next step.</p><p><a href="{link}">View update</a></p>',
        "text": f"An application has an update. Sign in to view the next step: {link}",
    }


def register_notifications():
    register_template(
        "b2_application",
        eligible=notification_eligible,
        render=notification_render,
        payload_enums={"state": set(STATES)},
    )
