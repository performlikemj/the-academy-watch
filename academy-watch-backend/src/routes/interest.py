"""Public, idempotent interest intake and authenticated admin reporting."""

import csv
import io
import re

from flask import Blueprint, Response, jsonify, request, stream_with_context
from sqlalchemy.exc import IntegrityError
from src.auth import require_api_key
from src.extensions import limiter
from src.models.interest import INTEREST_FEATURES, INTEREST_ROLES, InterestSignup
from src.models.league import db

interest_bp = Blueprint("interest", __name__)
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


@interest_bp.post("/interest")
@limiter.limit("10 per minute;30 per hour")
def create_interest():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify(error="Send a JSON object."), 400
    if data.get("website"):
        return jsonify(status="ok"), 201
    raw_email = data.get("email")
    email = raw_email.strip().lower() if isinstance(raw_email, str) else ""
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        return jsonify(error="Enter a valid email address."), 400
    feature = data.get("feature")
    role = data.get("role")
    if role == "":
        role = None
    if feature not in INTEREST_FEATURES:
        return jsonify(error="Choose a valid feature."), 400
    if role is not None and role not in INTEREST_ROLES:
        return jsonify(error="Choose a valid role."), 400
    source_path = data.get("source_path")
    if source_path == "":
        source_path = None
    if source_path is not None and (
        not isinstance(source_path, str) or len(source_path) > 500 or not source_path.startswith("/")
    ):
        return jsonify(error="Source path must be a local path of at most 500 characters."), 400
    if InterestSignup.query.filter_by(email=email, feature=feature).first():
        return jsonify(status="already"), 200
    db.session.add(InterestSignup(email=email, feature=feature, role=role, source_path=source_path))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        # The unique constraint also handles simultaneous duplicate requests.
        if InterestSignup.query.filter_by(email=email, feature=feature).first():
            return jsonify(status="already"), 200
        raise
    return jsonify(status="ok"), 201


def _csv_cell(value):
    """Keep user-provided cells inert when an export is opened in a spreadsheet."""
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


@interest_bp.get("/admin/interest")
@require_api_key
def admin_interest():
    query = InterestSignup.query.order_by(InterestSignup.created_at.desc(), InterestSignup.id.desc())
    if request.args.get("format") == "csv":

        @stream_with_context
        def generate():
            buffer = io.StringIO()
            writer = csv.writer(buffer)
            columns = ("id", "email", "feature", "role", "source_path", "created_at")
            writer.writerow(columns)
            yield buffer.getvalue()
            for row in query.yield_per(500):
                buffer.seek(0)
                buffer.truncate(0)
                writer.writerow([_csv_cell(row.to_dict()[column]) for column in columns])
                yield buffer.getvalue()

        return Response(
            generate(),
            mimetype="text/csv",
            headers={"Content-Disposition": 'attachment; filename="interest-signups.csv"', "Cache-Control": "no-store"},
        )
    limit = max(1, min(request.args.get("limit", 100, type=int), 500))
    by_feature = dict.fromkeys(INTEREST_FEATURES, 0)
    by_role = dict.fromkeys((*INTEREST_ROLES, "unspecified"), 0)
    grouped = (
        db.session.query(InterestSignup.feature, InterestSignup.role, db.func.count(InterestSignup.id))
        .group_by(InterestSignup.feature, InterestSignup.role)
        .all()
    )
    for feature, role, count in grouped:
        by_feature[feature] = by_feature.get(feature, 0) + count
        by_role[role or "unspecified"] = by_role.get(role or "unspecified", 0) + count
    response = jsonify(
        total=sum(by_feature.values()),
        counts={"feature": by_feature, "role": by_role},
        rows=[row.to_dict() for row in query.limit(limit)],
    )
    response.headers["Cache-Control"] = "no-store"
    return response
