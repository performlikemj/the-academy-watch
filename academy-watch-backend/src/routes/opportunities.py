"""Dark launch APIs. Club resources are always addressed through their program."""

from functools import wraps

from flask import Blueprint, g, jsonify, request
from sqlalchemy.exc import IntegrityError, OperationalError
from src.auth import require_user_auth
from src.extensions import limiter
from src.models.league import db
from src.models.opportunities import ClubOpportunity, OpportunityApplication, now
from src.services import opportunities as service
from src.services.club_access import require_club_permission
from src.services.contact_locks import database_conflict

opportunities_bp = Blueprint("opportunities", __name__)


@opportunities_bp.record_once
def hide_dark_features(state):
    path = (state.url_prefix or "") + "/opportunities/features"

    @state.app.before_request
    def dark_features_not_found():
        # Includes Flask's automatic OPTIONS and otherwise-405 methods: exact dark parity.
        if request.path == path and not service.enabled("OPPORTUNITIES_ENABLED"):
            return jsonify(error="Not found"), 404


def key():
    return f"b2:{getattr(g, 'user_id', None) or request.remote_addr}"


def flagged(*, applications=False):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not service.enabled("OPPORTUNITIES_ENABLED") or (applications and not service.applications_enabled()):
                return jsonify(error="Not found"), 404
            try:
                result = view(*args, **kwargs)
                return result
            except service.OpportunityError as exc:
                if exc.reconciled:
                    db.session.commit()
                else:
                    db.session.rollback()
                return jsonify(error=exc.code), exc.status
            except OperationalError as exc:
                db.session.rollback()
                conflict = database_conflict(exc)
                if conflict:
                    code, status = conflict
                    return jsonify(error=code, code=code, retryable=True), status
                raise
            except IntegrityError:
                db.session.rollback()
                return jsonify(error="request_conflict"), 409

        return wrapped

    return decorator


def payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise service.OpportunityError("invalid_payload", 400)
    return data


def page_number():
    try:
        page = int(request.args.get("page", "1"))
    except ValueError:
        raise service.OpportunityError("invalid_page", 400) from None
    if not 1 <= page <= 10000:
        raise service.OpportunityError("invalid_page", 400)
    return page


@opportunities_bp.get("/opportunities/features")
@flagged()
@limiter.limit("60/minute")
def features():
    # Unrouted parity while dark; clients treat 404 as both flags off.
    return jsonify(opportunities=service.enabled("OPPORTUNITIES_ENABLED"), applications=service.applications_enabled())


@opportunities_bp.get("/opportunities")
@flagged()
@limiter.limit("60/minute")
def listing():
    program_id = request.args.get("program_id", type=int)
    if "program_id" in request.args and (program_id is None or not 1 <= program_id <= 2147483647):
        raise service.OpportunityError("invalid_program_id", 400)
    query = service.public_query(program_id)
    kind = request.args.get("type")
    if kind:
        if kind not in {"trial", "open_session", "position"}:
            raise service.OpportunityError("invalid_type")
        query = query.filter(ClubOpportunity.type == kind)
    page = page_number()
    rows = query.order_by(ClubOpportunity.closes_at, ClubOpportunity.id).offset((page - 1) * 30).limit(31).all()
    return jsonify(opportunities=[service.opportunity_dict(r) for r in rows[:30]], page=page, has_more=len(rows) > 30)


@opportunities_bp.get("/opportunities/<uuid:opportunity_id>")
@flagged()
@limiter.limit("60/minute")
def detail(opportunity_id):
    return jsonify(opportunity=service.opportunity_dict(service.opportunity(str(opportunity_id), public=True)))


@opportunities_bp.route("/club/<int:program_id>/opportunities", methods=["GET", "POST"])
@flagged()
@require_club_permission("recruiting")
@limiter.limit("60/minute", key_func=key)
def club_opportunities(program_id):
    program = service.operational(program_id, lock=True)
    if request.method == "POST":
        row = service.save_opportunity(program_id, g.user_id, payload())
        result = service.opportunity_dict(row, private=True)
        db.session.commit()
        return jsonify(opportunity=result), 201
    page = page_number()
    rows = (
        ClubOpportunity.query.filter_by(program_id=program_id)
        .order_by(ClubOpportunity.created_at.desc())
        .offset((page - 1) * 30)
        .limit(31)
        .with_for_update()
        .all()
    )
    result = service.opportunity_page(rows[:30], program)
    db.session.commit()
    return jsonify(opportunities=result, page=page, has_more=len(rows) > 30)


@opportunities_bp.patch("/club/<int:program_id>/opportunities/<uuid:opportunity_id>")
@flagged()
@require_club_permission("recruiting")
@limiter.limit("60/hour", key_func=key)
def edit(program_id, opportunity_id):
    row = service.save_opportunity(program_id, g.user_id, payload(), str(opportunity_id))
    result = service.opportunity_dict(row, private=True)
    db.session.commit()
    return jsonify(opportunity=result)


@opportunities_bp.post("/club/<int:program_id>/opportunities/<uuid:opportunity_id>/close")
@flagged()
@require_club_permission("recruiting")
@limiter.limit("60/hour", key_func=key)
def close(program_id, opportunity_id):
    row = service.close_opportunity(program_id, g.user_id, str(opportunity_id), payload())
    result = service.opportunity_dict(row, private=True)
    db.session.commit()
    return jsonify(opportunity=result)


@opportunities_bp.get("/me/application-claims")
@flagged(applications=True)
@require_user_auth
@limiter.limit("60/minute", key_func=key)
def claims():
    return jsonify(claims=service.eligible_claims(g.user_id))


@opportunities_bp.post("/opportunities/<uuid:opportunity_id>/applications")
@flagged(applications=True)
@require_user_auth
@limiter.limit("20/hour", key_func=key)
def apply(opportunity_id):
    row, created = service.submit(str(opportunity_id), g.user_id, payload())
    db.session.commit()
    return jsonify(application=service.application_dict(row)), 201 if created else 200


@opportunities_bp.get("/me/applications")
@flagged(applications=True)
@require_user_auth
@limiter.limit("60/minute", key_func=key)
def mine():
    page = page_number()
    rows = (
        OpportunityApplication.query.filter(
            OpportunityApplication.applicant_user_id == g.user_id, OpportunityApplication.retention_expires_at > now()
        )
        .order_by(OpportunityApplication.submitted_at.desc())
        .offset((page - 1) * 30)
        .limit(31)
        .all()
    )
    service.reconcile_applications(rows[:30])
    opportunities = {
        r.id: r
        for r in ClubOpportunity.query.filter(ClubOpportunity.id.in_([a.opportunity_id for a in rows[:30]])).all()
    }
    from src.models.funding import ClubProgram

    programs = {r.id: r for r in ClubProgram.query.filter(ClubProgram.id.in_([a.program_id for a in rows[:30]])).all()}
    result = [
        service.application_dict(a, row=opportunities[a.opportunity_id], program=programs[a.program_id])
        for a in rows[:30]
    ]
    db.session.commit()
    return jsonify(applications=result, page=page, has_more=len(rows) > 30)


@opportunities_bp.get("/me/applications/<uuid:application_id>")
@flagged(applications=True)
@require_user_auth
@limiter.limit("60/minute", key_func=key)
def my_detail(application_id):
    row = service.application(str(application_id), user_id=g.user_id)
    service.reconcile_applications([row])
    result = service.application_dict(row)
    db.session.commit()
    return jsonify(application=result)


@opportunities_bp.post("/me/applications/<uuid:application_id>/withdraw")
@flagged(applications=True)
@require_user_auth
@limiter.limit("30/hour", key_func=key)
def withdraw(application_id):
    row = service.applicant_action(str(application_id), g.user_id, payload(), "withdraw")
    db.session.commit()
    return jsonify(application=service.application_dict(row))


@opportunities_bp.post("/me/applications/<uuid:application_id>/trial-response")
@flagged(applications=True)
@require_user_auth
@limiter.limit("30/hour", key_func=key)
def trial_response(application_id):
    row = service.applicant_action(str(application_id), g.user_id, payload(), "trial-response")
    db.session.commit()
    return jsonify(application=service.application_dict(row))


@opportunities_bp.get("/club/<int:program_id>/opportunities/<uuid:opportunity_id>/applications")
@flagged(applications=True)
@require_club_permission("recruiting")
@limiter.limit("60/minute", key_func=key)
def pipeline(program_id, opportunity_id):
    program = service.operational(program_id, lock=True)
    opportunity = service.opportunity(str(opportunity_id), program_id, lock=True)
    page = page_number()
    rows = (
        OpportunityApplication.query.filter(
            OpportunityApplication.program_id == program_id,
            OpportunityApplication.opportunity_id == str(opportunity_id),
            OpportunityApplication.retention_expires_at > now(),
        )
        .order_by(OpportunityApplication.submitted_at, OpportunityApplication.id)
        .offset((page - 1) * 30)
        .limit(31)
        .with_for_update()
        .all()
    )
    result = service.application_page(rows[:30], row=opportunity, program=program)
    db.session.commit()
    return jsonify(applications=result, page=page, has_more=len(rows) > 30)


@opportunities_bp.get("/club/<int:program_id>/applications/<uuid:application_id>")
@flagged(applications=True)
@require_club_permission("recruiting")
@limiter.limit("60/minute", key_func=key)
def club_application(program_id, application_id):
    service.operational(program_id, lock=True)
    initial = service.application(str(application_id), program_id=program_id)
    service.opportunity(initial.opportunity_id, program_id, lock=True)
    row = service.application(str(application_id), program_id=program_id, lock=True)
    available = service.reconcile_applications([row])
    if row.id not in available:
        db.session.commit()
        raise service.OpportunityError("Not found", 404)
    result = service.application_dict(row, private=True)
    db.session.commit()
    return jsonify(application=result)


@opportunities_bp.post("/club/<int:program_id>/applications/<uuid:application_id>/transition")
@flagged(applications=True)
@require_club_permission("recruiting")
@limiter.limit("120/hour", key_func=key)
def transition(program_id, application_id):
    row = service.transition(program_id, g.user_id, str(application_id), payload())
    db.session.commit()
    return jsonify(application=service.application_dict(row, private=True))


@opportunities_bp.post("/club/<int:program_id>/applications/<uuid:application_id>/notes")
@flagged(applications=True)
@require_club_permission("recruiting")
@limiter.limit("120/hour", key_func=key)
def notes(program_id, application_id):
    note = service.add_note(program_id, g.user_id, str(application_id), payload())
    db.session.commit()
    return jsonify(note={"id": note.id, "body": note.body, "created_at": service.iso(note.created_at)}), 201
