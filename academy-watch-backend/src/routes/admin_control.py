"""Four independently dark, dual-authenticated control-room views."""

import os
from datetime import datetime, timedelta
from functools import wraps
from urllib.parse import quote

import sqlalchemy as sa
from flask import Blueprint, abort, current_app, g, jsonify, request
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

            @wraps(view)
            def authorized(*args, **kwargs):
                from src.services.admin_control_safety import lazy_reconcile

                if any(isinstance(v, int) and not 0 < v <= 2147483647 for v in kwargs.values()):
                    return jsonify(error="ID is out of range"), 400
                if request.method == "GET" and which in {"safety", "business"}:
                    lazy_reconcile(current_app, which)
                return view(*args, **kwargs)

            return require_api_key(authorized)(*args, **kwargs)

        wrapped.control_page = which
        return wrapped

    return decorate


@admin_control_bp.before_app_request
def hide_dark_control_routes():
    # Try the actual method first: GET can match the SPA shell for a POST-only path.
    from flask.globals import request_ctx
    from werkzeug.exceptions import MethodNotAllowed, NotFound
    from werkzeug.routing import Map, RequestRedirect

    adapter = current_app.url_map.bind_to_environ(request.environ)
    try:
        rule, _ = adapter.match(method=request.method, return_rule=True)
    except MethodNotAllowed as error:
        # Do not rely on set ordering: GET/OPTIONS might select the SPA fallback.
        for method in error.valid_methods:
            rule, _ = adapter.match(method=method, return_rule=True)
            if rule.endpoint.startswith("admin_control."):
                break
        else:
            return
    except (NotFound, RequestRedirect):
        return
    if not rule.endpoint.startswith("admin_control."):
        return
    view = current_app.view_functions[rule.endpoint]
    if not flag_enabled(FLAGS[view.control_page]):
        # Route as though every dark B3 rule were absent. This preserves the real
        # app's SPA fallback, 405 body and OPTIONS Allow header, and sibling tools.
        rules = tuple(current_app.url_map.iter_rules())
        disabled = tuple(which for which, flag in FLAGS.items() if not flag_enabled(flag))
        key = (rules, disabled)
        cached = current_app.extensions.get("admin_control_dark_map")
        if cached is None or cached[0] != key:
            original = current_app.url_map
            visible_rules = []
            for candidate in rules:
                if (
                    candidate.endpoint.startswith("admin_control.")
                    and current_app.view_functions[candidate.endpoint].control_page in disabled
                ):
                    continue
                copied = candidate.empty()
                # C4 integration: preserve Werkzeug method iteration for exact dark Allow parity.
                copied.methods = candidate.methods
                # Flask adds this attribute after Werkzeug constructs the rule.
                copied.provide_automatic_options = getattr(candidate, "provide_automatic_options", False)
                visible_rules.append(copied)
            visible = Map(
                visible_rules,
                converters=original.converters,
                strict_slashes=original.strict_slashes,
                merge_slashes=original.merge_slashes,
                redirect_defaults=original.redirect_defaults,
                host_matching=original.host_matching,
                default_subdomain=original.default_subdomain,
            )
            current_app.extensions["admin_control_dark_map"] = (key, visible)
        else:
            visible = cached[1]
        request_ctx.url_adapter = visible.bind_to_environ(request.environ)
        request.routing_exception = None
        request.url_rule = None
        request.view_args = None
        request_ctx.match_request()


@admin_control_bp.after_request
def private_response(response):
    # Dark routes use the application's normal unrouted response, headers included.
    if request.endpoint and flag_enabled(FLAGS[current_app.view_functions[request.endpoint].control_page]):
        response.headers["Cache-Control"] = "no-store"
    return response


def pagination():
    try:
        offset = int(request.args.get("offset", "0"))
    except ValueError:
        abort(400, description="Invalid offset")
    if not 0 <= offset <= 2147483647:
        abort(400, description="Offset is out of range")
    return max(1, min(100, request.args.get("limit", 30, type=int) or 30)), offset


def iso(value):
    return value.isoformat() + "Z" if value else None


def search_pattern():
    search = request.args.get("q", "").strip()
    if len(search) > 120:
        abort(400, description="Search must be at most 120 characters")
    return "%" + search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%" if search else None


def program_counts(ids):
    result = {pid: {} for pid in ids}
    for label, model, column, predicate in (
        ("players", ClubRosterMember, ClubRosterMember.program_id, sa.true()),
        ("managers", ClubProgramManager, ClubProgramManager.program_id, ClubProgramManager.status == "active"),
        ("matches", VideoMatch, VideoMatch.club_program_id, sa.true()),
        ("claims_pending", ClubProgramClaim, ClubProgramClaim.program_id, ClubProgramClaim.status == "pending"),
    ):
        for pid, count in db.session.query(column, sa.func.count()).filter(column.in_(ids), predicate).group_by(column):
            result[pid][label] = count
    return result


def program_dict(program, counts=None):
    counts = counts if counts is not None else program_counts([program.id])[program.id]
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
        "players": counts.get("players", 0),
        "managers": counts.get("managers", 0),
        "matches": counts.get("matches", 0),
        "claims_pending": counts.get("claims_pending", 0),
    }


@admin_control_bp.get("/admin/programs")
@page("programs")
def programs():
    limit, offset = pagination()
    query = ClubProgram.query
    search = search_pattern()
    if search:
        query = query.filter(
            sa.or_(
                ClubProgram.name.ilike(search, escape="\\"),
                ClubProgram.city.ilike(search, escape="\\"),
                ClubProgram.region.ilike(search, escape="\\"),
            )
        )
    rows = query.order_by(ClubProgram.name, ClubProgram.id).offset(offset).limit(limit).all()
    counts = program_counts([row.id for row in rows])
    return jsonify(
        total=query.count(), rows=[program_dict(row, counts[row.id]) for row in rows], limit=limit, offset=offset
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


def people_context(ids):
    context = {uid: {"claims": [], "managers": [], "grants": [], "verification": None} for uid in ids}
    for row in PlayerProfileClaim.query.filter(
        PlayerProfileClaim.user_account_id.in_(ids), PlayerProfileClaim.status == "approved"
    ):
        context[row.user_account_id]["claims"].append(row)
    managers = (
        db.session.query(ClubProgramManager, ClubProgram)
        .join(ClubProgram)
        .join(
            ClubProgramClaim,
            sa.and_(ClubProgramClaim.id == ClubProgramManager.source_claim_id, ClubProgramClaim.status == "approved"),
        )
        .filter(ClubProgramManager.user_account_id.in_(ids), ClubProgramManager.status == "active")
    )
    for manager, program in managers:
        context[manager.user_account_id]["managers"].append((manager, program))
    if flag_enabled("CLUB_STAFF_ACCESS_ENABLED"):
        for grant in ClubAccessGrant.query.join(ClubProgram, ClubProgram.id == ClubAccessGrant.program_id).filter(
            ClubAccessGrant.user_account_id.in_(ids),
            ClubAccessGrant.status == "active",
            ClubProgram.platform_status == "approved",
            ClubProgram.emergency_hidden.is_(False),
        ):
            context[grant.user_account_id]["grants"].append(grant)
    for row in ScoutVerification.query.filter(ScoutVerification.user_account_id.in_(ids)).order_by(
        ScoutVerification.submitted_at.desc(), ScoutVerification.id.desc()
    ):
        if context[row.user_account_id]["verification"] is None:
            context[row.user_account_id]["verification"] = row
    return context


def person_dict(user, context=None):
    roles = []
    if (user.email or "").lower() in {email.lower() for email in _admin_email_list()}:
        roles.append("admin")
    for name, attribute in (("writer", "is_journalist"), ("editor", "is_editor"), ("curator", "is_curator")):
        if getattr(user, attribute):
            roles.append(name)
    context = context if context is not None else people_context([user.id])[user.id]
    claims, managers, grants = context["claims"], context["managers"], context["grants"]
    roles.extend(sorted({claim.relationship_type for claim in claims}))
    if managers:
        roles.append("club_manager")
    if user.account_status == "active":
        roles.extend(
            f"club_{grant.role}"
            for grant in grants
            if grant.role != "owner" or any(program.id == grant.program_id for _, program in managers)
        )
    verification = context["verification"]
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
    search = search_pattern()
    if search:
        query = query.filter(
            sa.or_(UserAccount.email.ilike(search, escape="\\"), UserAccount.display_name.ilike(search, escape="\\"))
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
                sa.select(ClubProgramManager.user_account_id)
                .join(ClubProgramClaim, ClubProgramClaim.id == ClubProgramManager.source_claim_id)
                .where(ClubProgramManager.status == "active", ClubProgramClaim.status == "approved")
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
    rows = query.order_by(UserAccount.id).offset(offset).limit(limit).all()
    context = people_context([row.id for row in rows])
    return jsonify(
        total=query.count(),
        rows=[person_dict(user, context[user.id]) for user in rows],
        limit=limit,
        offset=offset,
    )


@admin_control_bp.get("/admin/people/<int:user_id>")
@page("people")
def person_detail(user_id):
    user = db.session.get(UserAccount, user_id)
    if user is None or user.is_tombstone:
        return jsonify(error="Not found"), 404
    return jsonify(person=person_dict(user), last_owner_programs=last_owner_programs(user.id))


def last_owner_programs(uid):
    # Before staff rollout, the verified manager set is the club's ownership fallback.
    qualified = (
        db.session.query(ClubProgramManager.program_id, UserAccount.id)
        .join(UserAccount, UserAccount.id == ClubProgramManager.user_account_id)
        .join(ClubProgramClaim, ClubProgramClaim.id == ClubProgramManager.source_claim_id)
        .filter(
            ClubProgramManager.status == "active",
            ClubProgramClaim.status == "approved",
            UserAccount.account_status == "active",
            UserAccount.is_tombstone.is_(False),
        )
    )
    if flag_enabled("CLUB_STAFF_ACCESS_ENABLED"):
        qualified = qualified.join(
            ClubAccessGrant,
            sa.and_(
                ClubAccessGrant.program_id == ClubProgramManager.program_id,
                ClubAccessGrant.user_account_id == UserAccount.id,
                ClubAccessGrant.role == "owner",
                ClubAccessGrant.status == "active",
            ),
        )
    managers = qualified.subquery()
    only = (
        sa.select(managers.c.program_id)
        .group_by(managers.c.program_id)
        .having(sa.func.count(sa.distinct(managers.c.id)) == 1, sa.func.min(managers.c.id) == uid)
    )
    return [
        name for (name,) in db.session.query(ClubProgram.name).filter(ClubProgram.id.in_(only)).order_by(ClubProgram.id)
    ]


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
        "owns_hold": bool(case.held_program_id or case.owned_suppression_id),
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
