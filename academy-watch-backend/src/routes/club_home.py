"""Private Club Home resources, registered on the existing manager blueprint."""

import logging
import re
from datetime import UTC, datetime
from functools import wraps

from flask import current_app, g, jsonify, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from src.models.funding import ClubProgram, ClubProgramManager, ClubRosterMember, ClubSquad, ClubStaff
from src.models.league import db
from src.services import showcase_media_storage as storage
from src.services.club_registry import require_club_manager
from src.services.photo_processing import process_photo

logger = logging.getLogger(__name__)


class HomeError(ValueError):
    def __init__(self, message, status=422):
        super().__init__(message)
        self.status = status


def transaction(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            # Serialize graph and assignment mutations per program, including template creation.
            if request.method != "GET":
                db.session.query(ClubProgram).filter_by(id=kwargs["program_id"]).with_for_update().one()
            return view(*args, **kwargs)
        except HomeError as exc:
            db.session.rollback()
            return jsonify(error=str(exc)), exc.status
        except IntegrityError:
            db.session.rollback()
            return jsonify(error="conflict"), 409

    return wrapped


def payload():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise HomeError("Expected a JSON object")
    return data


def resource(model, program_id, row_id):
    if isinstance(row_id, bool) or not isinstance(row_id, int):
        raise HomeError("Not found", 404)
    row = model.query.filter_by(id=row_id, program_id=program_id).first()
    if row is None:
        raise HomeError("Not found", 404)
    return row


def integer(value, field, low=0, high=32767, nullable=False):
    if value is None and nullable:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise HomeError(f"{field} must be an integer from {low} to {high}")
    return value


def required_text(value, field, limit):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit:
        raise HomeError(f"{field} must contain 1–{limit} characters")
    return value.strip()


MAX_CLUB_ROSTER_MEMBERS = 500


def check_roster_capacity(program_id):
    if ClubRosterMember.query.filter_by(program_id=program_id).count() >= MAX_CLUB_ROSTER_MEMBERS:
        raise HomeError(f"Club roster limit reached ({MAX_CLUB_ROSTER_MEMBERS} players)", 429)


def assign_roster(member, data):
    squad_id = data.get("squad_id", member.squad_id)
    if squad_id is not None:
        resource(ClubSquad, member.program_id, squad_id)
    shirt = integer(data.get("shirt_number", member.shirt_number), "shirt_number", 1, 99, nullable=True)
    if squad_id is not None and shirt is not None:
        query = ClubRosterMember.query.filter_by(squad_id=squad_id, shirt_number=shirt)
        if member.id is not None:
            query = query.filter(ClubRosterMember.id != member.id)
        if query.first():
            raise HomeError("shirt_number_taken", 409)
    from src.services.club_player_profile import change_squad

    change_squad(member, squad_id)
    member.shirt_number = shirt


def luminance(color):
    channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722), strict=True))


def contrast(a, b):
    light, dark = sorted((luminance(a), luminance(b)), reverse=True)
    return (light + 0.05) / (dark + 0.05)


def serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="club-banner-upload")


def register(club_bp):
    def route(path, methods):
        def decorate(view):
            return club_bp.route(f"/club/<int:program_id>/{path}", methods=methods)(
                require_club_manager()(transaction(view))
            )

        return decorate

    @route("squads", ["GET", "POST"])
    def home_squads(program_id):
        if request.method == "GET":
            return jsonify(
                squads=[
                    s.to_dict()
                    for s in ClubSquad.query.filter_by(program_id=program_id).order_by(
                        ClubSquad.sort_order, ClubSquad.id
                    )
                ]
            )
        squad = ClubSquad(program_id=program_id, sort_order=ClubSquad.query.filter_by(program_id=program_id).count())
        update_squad(squad, payload(), creating=True)
        db.session.add(squad)
        db.session.commit()
        return jsonify(squad=squad.to_dict()), 201

    def update_squad(squad, data, creating=False):
        if creating or "name" in data:
            squad.name = required_text(data.get("name"), "name", 80)
        if creating or "kind" in data:
            kind = data.get("kind", "other")
            if kind not in ("first_team", "reserves", "age_group", "other"):
                raise HomeError("Invalid squad kind")
            squad.kind = kind
        if "age_limit" in data:
            squad.age_limit = integer(data["age_limit"], "age_limit", 1, 99, nullable=True)
        if "sort_order" in data:
            squad.sort_order = integer(data["sort_order"], "sort_order")

    @route("squads/<int:row_id>", ["PATCH", "DELETE"])
    def home_squad(program_id, row_id):
        squad = resource(ClubSquad, program_id, row_id)
        if request.method == "DELETE":
            for member in ClubRosterMember.query.filter_by(program_id=program_id, squad_id=row_id).all():
                assign_roster(member, {"squad_id": None})
            # Mirror SET NULL for SQLite fixtures without foreign-key enforcement.
            from src.models.funding import ClubRosterSquadHistory

            ClubRosterSquadHistory.query.filter_by(squad_id=row_id).update({"squad_id": None})
            ClubStaff.query.filter_by(leads_squad_id=row_id).update({"leads_squad_id": None})
            db.session.delete(squad)
            db.session.commit()
            return jsonify(deleted=True)
        update_squad(squad, payload())
        db.session.commit()
        return jsonify(squad=squad.to_dict())

    @route("squads/reorder", ["POST"])
    def home_reorder(program_id):
        ids = payload().get("ids")
        squads = ClubSquad.query.filter_by(program_id=program_id).all()
        if not isinstance(ids, list) or any(type(i) is not int for i in ids) or len(ids) != len(set(ids)):
            raise HomeError("ids must list every squad once")
        if set(ids) != {s.id for s in squads}:
            raise HomeError("Not found", 404)
        for squad in squads:
            squad.sort_order = ids.index(squad.id)
        db.session.commit()
        return jsonify(squads=[s.to_dict() for s in sorted(squads, key=lambda s: s.sort_order)])

    @route("squads/template", ["POST"])
    def home_template(program_id):
        if ClubSquad.query.filter_by(program_id=program_id).first():
            raise HomeError("The standard template requires a club with no squads", 409)
        squads = []
        for index, (name, kind, age) in enumerate(
            (
                ("First team", "first_team", None),
                ("Reserves", "reserves", None),
                ("Under-21s", "age_group", 21),
                ("Under-18s", "age_group", 18),
                ("Under-16s", "age_group", 16),
            )
        ):
            squad = ClubSquad(program_id=program_id, name=name, kind=kind, age_limit=age, sort_order=index)
            db.session.add(squad)
            squads.append(squad)
        db.session.commit()
        return jsonify(squads=[s.to_dict() for s in squads]), 201

    def update_staff(staff, data, creating=False):
        for field, limit in (("display_name", 120), ("title", 80)):
            if creating or field in data:
                setattr(staff, field, required_text(data.get(field), field, limit))
        for field, model in (("reports_to_staff_id", ClubStaff), ("leads_squad_id", ClubSquad)):
            if field in data:
                value = data[field]
                if value is not None:
                    resource(model, staff.program_id, value)
                setattr(staff, field, value)
        if "user_account_id" in data:
            value = data["user_account_id"]
            if value is not None and (
                type(value) is not int
                or not ClubProgramManager.query.filter_by(
                    program_id=staff.program_id, user_account_id=value, status="active"
                ).first()
            ):
                raise HomeError("Not found", 404)
            staff.user_account_id = value
        if "sort_order" in data:
            staff.sort_order = integer(data["sort_order"], "sort_order")
        visited = {staff.id} if staff.id else set()
        parent = staff.reports_to_staff_id
        while parent is not None:
            if parent in visited:
                raise HomeError("Reporting lines cannot form a cycle")
            visited.add(parent)
            parent = resource(ClubStaff, staff.program_id, parent).reports_to_staff_id
        if staff.leads_squad_id is not None:
            other = ClubStaff.query.filter_by(program_id=staff.program_id, leads_squad_id=staff.leads_squad_id)
            if staff.id:
                other = other.filter(ClubStaff.id != staff.id)
            if other.first():
                raise HomeError("This squad already has a lead coach", 409)

    @route("staff", ["GET", "POST"])
    def home_staff(program_id):
        if request.method == "GET":
            return jsonify(
                staff=[
                    s.to_dict()
                    for s in ClubStaff.query.filter_by(program_id=program_id).order_by(
                        ClubStaff.sort_order, ClubStaff.id
                    )
                ]
            )
        staff = ClubStaff(program_id=program_id)
        update_staff(staff, payload(), creating=True)
        db.session.add(staff)
        db.session.commit()
        return jsonify(staff=staff.to_dict()), 201

    @route("staff/<int:row_id>", ["PATCH", "DELETE"])
    def home_staff_member(program_id, row_id):
        staff = resource(ClubStaff, program_id, row_id)
        if request.method == "DELETE":
            ClubStaff.query.filter_by(reports_to_staff_id=row_id).update({"reports_to_staff_id": None})
            db.session.delete(staff)
            db.session.commit()
            return jsonify(deleted=True)
        with db.session.no_autoflush:
            update_staff(staff, payload())
        db.session.commit()
        return jsonify(staff=staff.to_dict())

    @route("roster/<int:member_id>", ["PATCH"])
    def home_roster(program_id, member_id):
        from src.routes.club import _clean_optional, _member_dict

        member = resource(ClubRosterMember, program_id, member_id)
        data = payload()
        assign_roster(member, data)
        try:
            for field, limit in (("role", 80), ("note", 500)):
                if field in data:
                    setattr(member, field, _clean_optional(data[field], field, limit))
        except ValueError as exc:
            raise HomeError(str(exc)) from exc
        db.session.commit()
        return jsonify(member=_member_dict(member))

    @route("available-local-players", ["GET"])
    def home_available_local_players(program_id):
        from src.models.showcase import LocalPlayer
        from src.routes.club import _local_player_available

        assigned = (
            db.session.query(ClubRosterMember.local_player_id)
            .filter_by(program_id=program_id)
            .filter(ClubRosterMember.local_player_id.is_not(None))
        )
        players = (
            LocalPlayer.query.filter(
                or_(
                    and_(LocalPlayer.provenance == "club", LocalPlayer.origin_program_id == program_id),
                    and_(LocalPlayer.provenance != "club", LocalPlayer.created_by_user_id == g.user_id),
                ),
                ~LocalPlayer.id.in_(assigned),
            )
            .order_by(LocalPlayer.display_name, LocalPlayer.id)
            .all()
        )
        return jsonify(
            players=[
                {"id": p.id, "display_name": p.display_name, "position": p.position}
                for p in players
                if _local_player_available(p)
            ]
        )

    @route("map", ["GET"])
    def home_map(program_id):
        staff = ClubStaff.query.filter_by(program_id=program_id).order_by(ClubStaff.sort_order, ClubStaff.id).all()
        counts = dict(
            db.session.query(ClubRosterMember.squad_id, func.count(ClubRosterMember.id))
            .filter_by(program_id=program_id)
            .group_by(ClubRosterMember.squad_id)
            .all()
        )
        leads = {s.leads_squad_id: s.id for s in staff if s.leads_squad_id}
        return jsonify(
            program=db.session.get(ClubProgram, program_id).manager_dict(),
            staff=[s.to_dict() for s in staff],
            squads=[
                s.to_dict() | {"member_count": counts.get(s.id, 0), "lead_staff_id": leads.get(s.id)}
                for s in ClubSquad.query.filter_by(program_id=program_id).order_by(ClubSquad.sort_order, ClubSquad.id)
            ],
            unassigned_count=counts.get(None, 0),
        )

    @route("branding", ["PATCH"])
    def home_branding(program_id):
        data = payload()
        program = db.session.get(ClubProgram, program_id)
        for field, foreground in (("primary_color", "#FFFFFF"), ("accent_color", "#16201B")):
            if field not in data:
                continue
            color = data[field]
            if not isinstance(color, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
                raise HomeError(f"{field} must be a #RRGGBB hex colour")
            if contrast(color, foreground) < 4.5:
                raise HomeError(f"{field}: text contrast must be at least 4.5:1 against {foreground}")
            setattr(program, f"brand_{field}", color.upper())
        db.session.commit()
        logger.info("Club branding changed program=%s user=%s", program_id, g.user_id)
        return jsonify(brand=program.brand_dict())

    @route("branding/banner", ["POST"])
    def home_banner(program_id):
        content_type = payload().get("content_type")
        if content_type not in ("image/jpeg", "image/png", "image/webp"):
            raise HomeError("Banner must be JPEG, PNG or WebP")
        if not storage.is_configured():
            raise HomeError("Media storage is unavailable", 503)
        upload = storage.mint_upload(program_id, g.user_id, content_type, path_prefix=f"club-banners/{program_id}")
        token = serializer().dumps({"program": program_id, "user": g.user_id, "path": upload["blob_path"]})
        return jsonify(upload=upload, upload_token=token), 201

    @route("branding/banner/complete", ["POST"])
    def home_banner_complete(program_id):
        try:
            grant = serializer().loads(payload().get("upload_token", ""), max_age=3600)
        except (BadSignature, TypeError):
            raise HomeError("Upload not found", 404) from None
        if grant.get("program") != program_id or grant.get("user") != g.user_id:
            raise HomeError("Upload not found", 404)
        if not storage.is_configured():
            raise HomeError("Media storage is unavailable", 503)
        try:
            processed, content_type = process_photo(storage.read_pending_bytes(grant["path"]))
        except (ValueError, storage.StoredMediaError) as exc:
            raise HomeError(str(exc)) from exc
        program = db.session.get(ClubProgram, program_id)
        previous_url = program.banner_url
        program.banner_url = storage.publish(grant["path"], processed, content_type)
        program.banner_updated_at = datetime.now(UTC)
        db.session.commit()
        storage.delete_pending(grant["path"])
        if previous_url and previous_url != program.banner_url:
            try:
                previous_path = storage.public_blob_path_from_reference(previous_url)
            except storage.InvalidBlobPathError:
                previous_path = ""  # Legacy/external URLs are never deletion targets.
            if previous_path.startswith(f"club-banners/{program_id}/"):
                storage.delete_published(previous_url)
        logger.info("Club banner published program=%s user=%s", program_id, g.user_id)
        return jsonify(brand=program.brand_dict())
