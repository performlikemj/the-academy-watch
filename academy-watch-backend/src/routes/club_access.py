"""Club staff access HTTP routes (dark behind CLUB_STAFF_ACCESS_ENABLED; 404 while off)."""

from __future__ import annotations

import logging
from functools import wraps

from flask import Blueprint, g, jsonify, request
from src.auth import require_api_key, require_user_auth
from src.extensions import limiter
from src.models.club_access import ClubAccessGrant, ClubStaffInvite
from src.models.league import UserAccount, db
from src.services import club_access as access_service
from src.services.club_access import (
    BOARD_MATRIX,
    AccessError,
    current_access,
    require_club_permission,
    staff_access_enabled,
)

logger = logging.getLogger(__name__)
club_access_bp = Blueprint("club_access", __name__)


def _user_key():
    return f"user:{getattr(g, 'user_id', None) or request.remote_addr or 'anon'}"


def flagged(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not staff_access_enabled():
            return jsonify({"error": "Not found"}), 404
        try:
            return view(*args, **kwargs)
        except AccessError as exc:
            db.session.rollback()
            return jsonify({"error": exc.code}), exc.status

    return wrapped


def _payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise AccessError("invalid_payload")
    return data


def _matrix():
    # Row labels only. Each person carries their own marks (``permissions``), built from the access the
    # resolver gives them, so an invited (unverified) manager never shows a verified-only right.
    return {"rows": [label for label, _ in BOARD_MATRIX]}


def _permissions(program_id, user_id):
    return access_service.board_permissions(access_service.resolve_club_access(user_id, program_id))


def _person(user, **extra):
    return {
        "user_account_id": user.id if user else None,
        "display_name": (user.display_name if user and user.display_name else None),
        "email": user.email if user else None,
        **extra,
    }


def _people(program_id):
    from src.models.funding import ClubProgramManager

    owner_ids = {
        g_.user_account_id
        for g_ in ClubAccessGrant.query.filter_by(program_id=program_id, role="owner", status="active").all()
    }
    people = []
    seen = set()
    for manager in (
        ClubProgramManager.query.filter_by(program_id=program_id, status="active").order_by(ClubProgramManager.id).all()
    ):
        if not access_service.is_manager_of_approved_program(manager.user_account_id, program_id):
            continue
        seen.add(manager.user_account_id)
        user = db.session.get(UserAccount, manager.user_account_id)
        people.append(
            _person(
                user,
                grant_id=None,
                role="owner" if manager.user_account_id in owner_ids else "manager",
                verified=True,
                all_squads=True,
                squad_ids=[],
                editable=False,
                permissions=_permissions(program_id, manager.user_account_id),
            )
        )
    for grant in (
        ClubAccessGrant.query.filter_by(program_id=program_id, status="active").order_by(ClubAccessGrant.id).all()
    ):
        if grant.user_account_id in seen or grant.role == "owner":
            continue
        user = db.session.get(UserAccount, grant.user_account_id)
        people.append(
            _person(
                user,
                grant_id=grant.id,
                role=grant.role,
                verified=False,
                all_squads=bool(grant.all_squads) or grant.role == "manager",
                squad_ids=grant.squad_ids,
                version=grant.version,
                editable=True,
                permissions=_permissions(program_id, grant.user_account_id),
            )
        )
    return people


# ---------------------------------------------------------------------------
# Club side
# ---------------------------------------------------------------------------


def access_read_enabled(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        from src.services.opportunities import enabled

        if not staff_access_enabled() and not enabled("OPPORTUNITIES_ENABLED"):
            return jsonify({"error": "Not found"}), 404
        return view(*args, **kwargs)

    return wrapped


@club_access_bp.route("/club/<int:program_id>/access/me", methods=["GET"])
@access_read_enabled
@require_club_permission("players.view")
def my_club_access(program_id):
    return jsonify(access=current_access().to_dict())


@club_access_bp.route("/club/<int:program_id>/access", methods=["GET"])
@flagged
@require_club_permission("access.view")
def list_club_access(program_id):
    invites = (
        ClubStaffInvite.query.filter_by(program_id=program_id, status="pending")
        .order_by(ClubStaffInvite.created_at.desc())
        .all()
    )
    return jsonify(
        me=current_access().to_dict(),
        people=_people(program_id),
        invites=[i.to_dict() for i in invites],
        activity=access_service.recent_activity(program_id),
        matrix=_matrix(),
    )


@club_access_bp.route("/club/<int:program_id>/staff-invites", methods=["POST"])
@flagged
@require_club_permission("access.manage")
@limiter.limit("30 per hour", key_func=_user_key)
def create_staff_invite(program_id):
    from src.models.funding import ClubProgram

    invite, token = access_service.create_invite(program_id, g.user_id, _payload())
    program_name = db.session.get(ClubProgram, program_id).name
    db.session.commit()
    delivered = access_service.send_invite_email(invite, token, program_name)
    return jsonify(invite=invite.to_dict(), email_sent=delivered), 201


@club_access_bp.route("/club/<int:program_id>/staff-invites/<invite_id>/revoke", methods=["POST"])
@flagged
@require_club_permission("access.manage")
def revoke_staff_invite(program_id, invite_id):
    invite = access_service.revoke_invite(program_id, invite_id, g.user_id)
    db.session.commit()
    return jsonify(invite=invite.to_dict())


@club_access_bp.route("/club/<int:program_id>/access/<int:grant_id>", methods=["PATCH"])
@flagged
@require_club_permission("access.manage")
def update_club_access(program_id, grant_id):
    grant = access_service.update_grant(program_id, grant_id, g.user_id, _payload())
    db.session.commit()
    return jsonify(grant=grant.to_dict())


@club_access_bp.route("/club/<int:program_id>/access/<int:grant_id>", methods=["DELETE"])
@flagged
@require_club_permission("access.manage")
def revoke_club_access(program_id, grant_id):
    grant = access_service.revoke_grant(program_id, grant_id, g.user_id)
    db.session.commit()
    return jsonify(grant=grant.to_dict())


# ---------------------------------------------------------------------------
# Recipient side (existing OTP login; bound to the signed-in email)
# ---------------------------------------------------------------------------


@club_access_bp.route("/me/club-access", methods=["GET"])
@flagged
@require_user_auth
def my_grant_programs():
    from src.models.funding import ClubProgram

    programs = []
    for grant in ClubAccessGrant.query.filter_by(user_account_id=g.user_id, status="active").all():
        access = access_service.resolve_club_access(g.user_id, grant.program_id)
        program = db.session.get(ClubProgram, grant.program_id)
        if access is None or program is None or access.verified:
            continue
        programs.append({"program": program.public_dict(), "access": access.to_dict()})
    return jsonify(programs=programs)


@club_access_bp.route("/me/staff-invites/preview", methods=["POST"])
@flagged
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_key)
def preview_staff_invite():
    return jsonify(access_service.preview_invite(g.user, _payload().get("token")))


@club_access_bp.route("/me/staff-invites/accept", methods=["POST"])
@flagged
@require_user_auth
@limiter.limit("10 per hour", key_func=_user_key)
def accept_staff_invite():
    grant = access_service.accept_invite(g.user, _payload().get("token"))
    db.session.commit()
    access = access_service.resolve_club_access(g.user_id, grant.program_id)
    return jsonify(program_id=grant.program_id, access=access.to_dict() if access else None)


# ---------------------------------------------------------------------------
# Admin: owner bootstrap (explicit, audited) and read-only access view
# ---------------------------------------------------------------------------


def _admin_reason(data):
    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip() or len(reason) > 2000:
        raise AccessError("reason_required")
    return reason.strip()


@club_access_bp.route("/admin/programs/<int:program_id>/owner", methods=["POST"])
@flagged
@require_api_key
def admin_assign_owner(program_id):
    data = _payload()
    user_id = data.get("user_account_id")
    if isinstance(user_id, bool) or not isinstance(user_id, int):
        raise AccessError("user_account_id_required")
    grant = access_service.assign_owner(program_id, user_id, _admin_reason(data))
    db.session.commit()
    return jsonify(grant=grant.to_dict())


@club_access_bp.route("/admin/programs/<int:program_id>/owner", methods=["DELETE"])
@flagged
@require_api_key
def admin_remove_owner(program_id):
    grant = access_service.remove_owner(program_id, _admin_reason(_payload()))
    db.session.commit()
    return jsonify(grant=grant.to_dict())


@club_access_bp.route("/admin/programs/<int:program_id>/access", methods=["GET"])
@flagged
@require_api_key
def admin_program_access(program_id):
    invites = ClubStaffInvite.query.filter_by(program_id=program_id).order_by(ClubStaffInvite.created_at.desc()).all()
    return jsonify(
        people=_people(program_id),
        invites=[i.to_dict() for i in invites[:50]],
        activity=access_service.recent_activity(program_id, limit=50),
    )
