import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from sqlalchemy.exc import IntegrityError

from src.auth import require_api_key, _safe_error_payload
from src.models.league import db
from src.models.formation import TeamFormation

logger = logging.getLogger(__name__)

formation_bp = Blueprint('formation', __name__)


@formation_bp.route('/admin/teams/<int:team_id>/formations', methods=['GET'])
@require_api_key
def list_formations(team_id):
    formations = TeamFormation.query.filter_by(team_id=team_id).order_by(TeamFormation.updated_at.desc()).all()
    return jsonify([f.to_dict() for f in formations])


@formation_bp.route('/admin/teams/<int:team_id>/formations', methods=['POST'])
@require_api_key
def create_formation(team_id):
    data = request.get_json(silent=True) or {}
    name = (data.get('name') or '').strip()
    formation_type = (data.get('formation_type') or '').strip()

    if not name or not formation_type:
        return jsonify({'error': 'name and formation_type are required'}), 400

    formation = TeamFormation(
        team_id=team_id,
        name=name,
        formation_type=formation_type,
        positions=data.get('positions', []),
        notes=data.get('notes'),
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    try:
        db.session.add(formation)
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': f'A formation named "{name}" already exists for this team'}), 409

    return jsonify(formation.to_dict()), 201


@formation_bp.route('/admin/teams/<int:team_id>/formations/<int:formation_id>', methods=['GET'])
@require_api_key
def get_formation(team_id, formation_id):
    formation = TeamFormation.query.filter_by(id=formation_id, team_id=team_id).first()
    if not formation:
        return jsonify({'error': 'Formation not found'}), 404
    return jsonify(formation.to_dict())


@formation_bp.route('/admin/teams/<int:team_id>/formations/<int:formation_id>', methods=['PUT'])
@require_api_key
def update_formation(team_id, formation_id):
    formation = TeamFormation.query.filter_by(id=formation_id, team_id=team_id).first()
    if not formation:
        return jsonify({'error': 'Formation not found'}), 404

    data = request.get_json(silent=True) or {}

    if 'name' in data:
        formation.name = (data['name'] or '').strip()
    if 'formation_type' in data:
        formation.formation_type = (data['formation_type'] or '').strip()
    if 'positions' in data:
        formation.positions = data['positions']
    if 'notes' in data:
        formation.notes = data['notes']

    formation.updated_at = datetime.now(timezone.utc)

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({'error': f'A formation with that name already exists for this team'}), 409

    return jsonify(formation.to_dict())


@formation_bp.route('/admin/teams/<int:team_id>/formations/<int:formation_id>', methods=['DELETE'])
@require_api_key
def delete_formation(team_id, formation_id):
    formation = TeamFormation.query.filter_by(id=formation_id, team_id=team_id).first()
    if not formation:
        return jsonify({'error': 'Formation not found'}), 404

    db.session.delete(formation)
    db.session.commit()
    return '', 204
