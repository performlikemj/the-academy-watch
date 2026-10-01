"""Four independently dark, dual-authenticated control-room views."""

import os
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import quote

import sqlalchemy as sa
from flask import Blueprint, g, jsonify, request
from src.auth import _admin_email_list, require_api_key
from src.models.admin_control import (
    BusinessDeploymentState,
    SafeguardingCase,
    SafeguardingCaseEvent,
    now,
)
from src.models.billing import BillingSubscription
from src.models.club_access import ClubAccessGrant
from src.models.funding import ClubProgram, ClubProgramClaim, ClubProgramManager, ClubRosterMember
from src.models.league import EmailToken, UserAccount, db
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import PlayerProfileClaim
from src.models.trust import ContentReport, ScoutVerification
from src.models.video import VideoMatch
from src.services.admin_audit import record_admin_event
from src.services.admin_control_business import money_query
from src.services.admin_control_safety import act, case_hidden
from src.utils.data_mode import api_football_frozen, newsletters_frozen

admin_control_bp = Blueprint("admin_control", __name__)
FLAGS = {
    "programs": "ADMIN_PROGRAMS_ENABLED",
    "people": "ADMIN_PEOPLE_ENABLED",
    "safety": "ADMIN_SAFETY_ENABLED",
    "business": "ADMIN_BUSINESS_ENABLED",
}


def flag_enabled(flag):
    return os.getenv(flag, "").strip().lower() in {"1", "true", "yes", "on"}


def page(which):
    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not flag_enabled(FLAGS[which]):
                return jsonify({"error": "Not found"}), 404
            return require_api_key(view)(*args, **kwargs)

        return wrapped

    return decorate


@admin_control_bp.after_request
def private_response(response):
    response.headers["Cache-Control"] = "no-store"
    return response


def pagination():
    return max(1, min(100, request.args.get("limit", 30, type=int) or 30)), max(
        0, request.args.get("offset", 0, type=int) or 0
    )


def iso(value):
    return value.isoformat() + "Z" if value else None


def program_dict(program):
    return {
        "id": program.id,
        "name": program.name,
        "slug": program.slug,
        "city": program.city,
        "region": program.region,
        "country": program.country,
        "origin": "api" if program.team_api_id else "local",
        "team_api_id": program.team_api_id,
        "platform_status": program.platform_status,
        "emergency_hidden": bool(program.emergency_hidden),
        "verified_at": iso(program.verified_at),
        "players": ClubRosterMember.query.filter_by(program_id=program.id).count(),
        "managers": ClubProgramManager.query.filter_by(program_id=program.id, status="active").count(),
        "matches": VideoMatch.query.filter_by(club_program_id=program.id).count(),
        "claims_pending": ClubProgramClaim.query.filter_by(program_id=program.id, status="pending").count(),
    }


@admin_control_bp.get("/admin/programs")
@page("programs")
def programs():
    limit, offset = pagination()
    query = ClubProgram.query
    search = request.args.get("q", "").strip()[:120]
    if search:
        query = query.filter(
            sa.or_(
                ClubProgram.name.ilike(f"%{search}%"),
                ClubProgram.city.ilike(f"%{search}%"),
                ClubProgram.region.ilike(f"%{search}%"),
            )
        )
    return jsonify(
        total=query.count(),
        rows=[
            program_dict(row) for row in query.order_by(ClubProgram.name, ClubProgram.id).offset(offset).limit(limit)
        ],
        limit=limit,
        offset=offset,
    )


@admin_control_bp.get("/admin/programs/<int:program_id>")
@page("programs")
def program_detail(program_id):
    program = db.session.get(ClubProgram, program_id)
    if program is None:
        return jsonify(error="Not found"), 404
    managers = (
        db.session.query(ClubProgramManager, UserAccount)
        .join(UserAccount, UserAccount.id == ClubProgramManager.user_account_id)
        .filter(ClubProgramManager.program_id == program_id)
        .all()
    )
    owners = {
        row.user_account_id
        for row in ClubAccessGrant.query.filter_by(program_id=program_id, status="active", role="owner")
    }
    return jsonify(
        program=program_dict(program),
        managers=[
            {
                "user_account_id": user.id,
                "display_name": user.display_name,
                "email": user.email,
                "standing": user.account_status,
                "status": manager.status,
                "owner": user.id in owners,
            }
            for manager, user in managers
        ],
        actions={
            "emergency": flag_enabled("P2_FOUNDATION_ENABLED"),
            "owner": flag_enabled("CLUB_STAFF_ACCESS_ENABLED"),
        },
    )


def person_dict(user):
    roles = []
    if (user.email or "").lower() in {email.lower() for email in _admin_email_list()}:
        roles.append("admin")
    for name, attribute in (("writer", "is_journalist"), ("editor", "is_editor"), ("curator", "is_curator")):
        if getattr(user, attribute):
            roles.append(name)
    claims = PlayerProfileClaim.query.filter_by(user_account_id=user.id, status="approved").all()
    roles.extend(sorted({claim.relationship_type for claim in claims}))
    managers = (
        db.session.query(ClubProgramManager, ClubProgram)
        .join(ClubProgram)
        .join(
            ClubProgramClaim,
            sa.and_(
                ClubProgramClaim.program_id == ClubProgramManager.program_id,
                ClubProgramClaim.user_account_id == user.id,
                ClubProgramClaim.status == "approved",
            ),
        )
        .filter(ClubProgramManager.user_account_id == user.id, ClubProgramManager.status == "active")
        .all()
    )
    grants = (
        ClubAccessGrant.query.filter_by(user_account_id=user.id, status="active").all()
        if flag_enabled("CLUB_STAFF_ACCESS_ENABLED")
        else []
    )
    if managers:
        roles.append("club_manager")
    # Derived staff roles require live access; suspended roles remain provenance, not authorization.
    from src.services.club_access import resolve_club_access

    if user.account_status == "active":
        roles.extend(f"club_{grant.role}" for grant in grants if resolve_club_access(user.id, grant.program_id))
    verification = (
        ScoutVerification.query.filter_by(user_account_id=user.id)
        .order_by(ScoutVerification.submitted_at.desc(), ScoutVerification.id.desc())
        .first()
    )
    if verification:
        roles.append("verified_scout" if verification.status == "approved" else f"scout_{verification.status}")
    return {
        "id": user.id,
        "display_name": user.display_name,
        "email": user.email,
        "account_status": user.account_status,
        "created_at": iso(user.created_at),
        "last_login_at": iso(user.last_login_at),
        "roles": sorted(set(roles)),
        "programs": [
            {"id": program.id, "name": program.name, "status": program.platform_status} for _, program in managers
        ],
        "approved_claims": len(claims),
        "scout_verification": {"id": verification.id, "status": verification.status} if verification else None,
    }


@admin_control_bp.get("/admin/people")
@page("people")
def people():
    limit, offset = pagination()
    query = UserAccount.query.filter(UserAccount.is_tombstone.is_(False))
    search = request.args.get("q", "").strip()[:120]
    if search:
        query = query.filter(
            sa.or_(UserAccount.email.ilike(f"%{search}%"), UserAccount.display_name.ilike(f"%{search}%"))
        )
    role = request.args.get("role", "all")
    if role == "players":
        query = query.filter(
            UserAccount.id.in_(
                sa.select(PlayerProfileClaim.user_account_id).where(
                    PlayerProfileClaim.status == "approved", PlayerProfileClaim.relationship_type == "player"
                )
            )
        )
    elif role == "clubs":
        query = query.filter(
            UserAccount.id.in_(
                sa.select(ClubProgramManager.user_account_id).where(ClubProgramManager.status == "active")
            )
        )
    elif role == "scouts":
        query = query.filter(
            UserAccount.id.in_(
                sa.select(ScoutVerification.user_account_id).where(
                    ScoutVerification.status.in_(("pending", "approved"))
                )
            )
        )
    elif role == "admins":
        query = query.filter(sa.func.lower(UserAccount.email).in_([email.lower() for email in _admin_email_list()]))
    elif role != "all":
        return jsonify(error="Unknown people filter"), 400
    return jsonify(
        total=query.count(),
        rows=[person_dict(user) for user in query.order_by(UserAccount.id).offset(offset).limit(limit)],
        limit=limit,
        offset=offset,
    )


@admin_control_bp.get("/admin/people/<int:user_id>")
@page("people")
def person_detail(user_id):
    user = db.session.get(UserAccount, user_id)
    if user is None or user.is_tombstone:
        return jsonify(error="Not found"), 404
    return jsonify(person=person_dict(user))


@admin_control_bp.post("/admin/users/<int:user_id>/<action>")
@page("people")
def account_action(user_id, action):
    if action not in {"suspend", "restore"}:
        return jsonify(error="Not found"), 404
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="JSON object required"), 400
    try:
        user = UserAccount.query.filter_by(id=user_id).populate_existing().with_for_update().first()
        if user is None or user.is_tombstone:
            return jsonify(error="Not found"), 404
        if action == "suspend" and (user.email or "").lower() == g.user_email.lower():
            return jsonify(error="Cannot suspend your own administrative session"), 409
        target = "suspended" if action == "suspend" else "active"
        if user.account_status == target:
            return jsonify(person=person_dict(user), unchanged=True)
        record_admin_event(
            g.user_email,
            f"account_{action}",
            "user_account",
            user.id,
            payload.get("reason"),
            {"before_status": user.account_status, "after_status": target},
        )
        user.account_status = target
        user.auth_epoch = (user.auth_epoch or 0) + 1
        if action == "suspend":
            user.suspended_at, user.suspended_by, user.suspension_reason = now(), g.user_email, payload["reason"][:2000]
        else:
            user.suspended_at = user.suspended_by = user.suspension_reason = None
        EmailToken.query.filter_by(email=user.email, purpose="login").delete(synchronize_session=False)
        db.session.commit()
        return jsonify(person=person_dict(user))
    except ValueError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 400
    except Exception:
        db.session.rollback()
        raise


def case_dict(case):
    return {
        "id": case.id,
        "report_id": case.report_id,
        "suppression_id": case.suppression_id,
        "target_type": case.target_type,
        "target_id": case.target_id,
        "status": case.status,
        "received_at": iso(case.received_at),
        "first_action_due_at": iso(case.first_action_due_at),
        "first_action_at": iso(case.first_action_at),
        "overdue": case.first_action_at is None and case.status != "closed" and case.first_action_due_at < now(),
        "closed_at": iso(case.closed_at),
        "hidden": case_hidden(case),
        "notification_state": case.notification_state,
        "version": case.version,
    }


@admin_control_bp.get("/admin/safety/cases")
@page("safety")
def cases():
    limit, offset = pagination()
    query = SafeguardingCase.query
    if request.args.get("status", "open") != "all":
        query = query.filter(SafeguardingCase.status != "closed")
    return jsonify(
        total=query.count(),
        rows=[
            case_dict(case)
            for case in query.order_by(SafeguardingCase.received_at, SafeguardingCase.id).offset(offset).limit(limit)
        ],
        limit=limit,
        offset=offset,
        open_count=SafeguardingCase.query.filter(SafeguardingCase.status != "closed").count(),
        overdue_count=SafeguardingCase.query.filter(
            SafeguardingCase.status != "closed",
            SafeguardingCase.first_action_at.is_(None),
            SafeguardingCase.first_action_due_at < now(),
        ).count(),
        active_suppressions=PlayerSuppression.query.filter_by(status="active").count(),
        hidden_programs=ClubProgram.query.filter_by(emergency_hidden=True).count(),
        minor_public_audit="not_available",
    )


@admin_control_bp.get("/admin/safety/cases/<int:case_id>")
@page("safety")
def case_detail(case_id):
    case = db.session.get(SafeguardingCase, case_id)
    if case is None:
        return jsonify(error="Not found"), 404
    # Only source report/suppression evidence; unrelated feedback/notes are never queried.
    report = db.session.get(ContentReport, case.report_id) if case.report_id else None
    suppression = db.session.get(PlayerSuppression, case.suppression_id) if case.suppression_id else None
    record_admin_event(
        g.user_email, "safeguarding_evidence_read", "safeguarding_case", case.id, "Scoped case evidence read"
    )
    db.session.commit()
    return jsonify(
        case=case_dict(case),
        evidence={
            "reason_code": report.reason_code if report else (suppression.reason_code if suppression else None),
            "statement": report.details if report else (suppression.request_statement if suppression else None),
        },
        events=[
            {"id": event.id, "action": event.action, "created_at": iso(event.created_at), "reason": event.reason}
            for event in SafeguardingCaseEvent.query.filter_by(case_id=case.id).order_by(SafeguardingCaseEvent.id)
        ],
    )


@admin_control_bp.post("/admin/safety/cases/<int:case_id>/actions")
@page("safety")
def case_action(case_id):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify(error="JSON object required"), 400
    try:
        case = SafeguardingCase.query.filter_by(id=case_id).populate_existing().with_for_update().first()
        if case is None:
            return jsonify(error="Not found"), 404
        if payload.get("version") != case.version:
            return jsonify(error="Case changed. Refresh before acting."), 409
        act(case, payload.get("action"), g.user_email, payload.get("reason"))
        db.session.commit()
        return jsonify(case=case_dict(case))
    except ValueError as exc:
        db.session.rollback()
        return jsonify(error=str(exc)), 400
    except Exception:
        db.session.rollback()
        raise


@admin_control_bp.get("/admin/safety/hidden")
@page("safety")
def hidden():
    limit, offset = pagination()
    return jsonify(
        suppressions=[
            {"id": row.id, "player_api_id": row.player_api_id, "local_player_id": row.local_player_id}
            for row in PlayerSuppression.query.filter_by(status="active")
            .order_by(PlayerSuppression.id)
            .offset(offset)
            .limit(limit)
        ],
        programs=[
            {"id": row.id, "name": row.name}
            for row in ClubProgram.query.filter_by(emergency_hidden=True)
            .order_by(ClubProgram.id)
            .offset(offset)
            .limit(limit)
        ],
        limit=limit,
        offset=offset,
    )


def date_range():
    today = now()
    start = datetime.strptime(request.args.get("from") or today.replace(day=1).strftime("%Y-%m-%d"), "%Y-%m-%d")
    end = datetime.strptime(request.args.get("to") or today.strftime("%Y-%m-%d"), "%Y-%m-%d") + timedelta(days=1)
    if end <= start or (end - start).days > 366:
        raise ValueError("Use an inclusive date range of at most 366 days")
    return start, end


@admin_control_bp.get("/admin/business/summary")
@page("business")
def business():
    try:
        start, end = date_range()
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    limit, offset = pagination()
    money = money_query(start, end)
    totals = {}
    for currency, kind, amount in db.session.execute(
        sa.select(money.c.currency, money.c.kind, sa.func.sum(money.c.amount_cents)).group_by(
            money.c.currency, money.c.kind
        )
    ):
        totals.setdefault(currency.upper(), {"money_in_cents": 0, "refunds_cents": 0})[
            "money_in_cents" if kind == "receipt" else "refunds_cents"
        ] += amount
    rows = []
    for row in db.session.execute(
        sa.select(money).order_by(money.c.occurred_at.desc(), money.c.source, money.c.id).offset(offset).limit(limit)
    ).mappings():
        row = dict(row)
        row["occurred_at"] = iso(row["occurred_at"])
        row["currency"] = row["currency"].upper()
        row["stripe_url"] = (
            "https://dashboard.stripe.com/payments/" + quote(row["payment_intent_id"], safe="")
            if row["payment_intent_id"]
            else None
        )
        rows.append(row)
    return jsonify(
        rows=rows,
        total=db.session.scalar(sa.select(sa.func.count()).select_from(money)),
        limit=limit,
        offset=offset,
        currencies=totals,
        paying_clubs=BillingSubscription.query.filter(
            BillingSubscription.scope_type == "club_program", BillingSubscription.status.in_(("active", "trialing"))
        )
        .with_entities(BillingSubscription.scope_id)
        .distinct()
        .count(),
        freeze={
            "api_football": api_football_frozen(),
            "newsletters_configured": flag_enabled("NEWSLETTERS_FROZEN"),
            "newsletters_effective": newsletters_frozen(),
        },
        changes=[
            {
                "deployment_id": row.deployment_id,
                "observed_at": iso(row.observed_at),
                "api_football_frozen": row.api_football_frozen,
                "newsletters_configured_frozen": row.newsletters_configured_frozen,
                "newsletters_effective_frozen": row.newsletters_effective_frozen,
            }
            for row in BusinessDeploymentState.query.order_by(BusinessDeploymentState.id.desc()).limit(50)
        ],
        coverage="GOL purchase history and cash events recorded since Business was enabled. Earlier invoice receipts and refund dates are unavailable. Subscription prices and credit reversals are not cash receipts.",
    )
