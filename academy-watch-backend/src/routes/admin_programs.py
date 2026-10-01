"""Reversible emergency publication hold, separate from player takedowns."""

from flask import Blueprint, g, jsonify, request
from src.auth import require_api_key
from src.models.funding import ClubProgram
from src.models.league import db
from src.services.admin_audit import record_admin_event
from src.services.p2_foundation import foundation_enabled

admin_programs_bp = Blueprint("admin_programs", __name__)


def _emergency_action(program_id, hidden):
    if not foundation_enabled():
        return jsonify({"error": "Not found"}), 404
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"error": "JSON body must be an object"}), 400
    try:
        from src.services.admin_control_safety import lock_target

        lock_target("club_program", str(program_id))
        program = ClubProgram.query.filter_by(id=program_id).populate_existing().with_for_update().first()
        if program is None:
            return jsonify({"error": "Not found"}), 404
        before = bool(program.emergency_hidden)
        record_admin_event(
            g.user_email,
            "emergency_hide" if hidden else "emergency_lift",
            "club_program",
            program.id,
            payload.get("reason"),
            {"before_hidden": before, "after_hidden": hidden},
        )
        program.emergency_hidden = hidden
        if not hidden:
            from src.services.admin_control_safety import release_club_case_intents

            release_club_case_intents(program.id, g.user_email, payload.get("reason"))
        db.session.commit()
        return jsonify({"program_id": program.id, "emergency_hidden": hidden})
    except ValueError as exc:
        db.session.rollback()
        return jsonify({"error": str(exc)}), 400
    except Exception:
        db.session.rollback()
        raise


@admin_programs_bp.post("/admin/programs/<int:program_id>/emergency-hide")
@require_api_key
def emergency_hide(program_id):
    return _emergency_action(program_id, True)


@admin_programs_bp.post("/admin/programs/<int:program_id>/emergency-lift")
@require_api_key
def emergency_lift(program_id):
    return _emergency_action(program_id, False)
