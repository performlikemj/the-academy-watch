"""Private player pages/photos and admin safeguarding inventory."""

import logging
from datetime import UTC, datetime
from io import BytesIO

from flask import current_app, g, jsonify, request, send_file
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import or_
from src.auth import require_api_key
from src.models.funding import ClubProgram, ClubRosterMember
from src.models.league import db
from src.models.showcase import LocalPlayer, local_player_is_minor
from src.routes.club_home import HomeError, payload, resource, transaction
from src.services import showcase_media_storage as storage
from src.services.club_player_profile import profile_payload
from src.services.club_registry import require_club_manager
from src.services.photo_processing import process_photo
from src.services.player_suppression import is_local_player_suppressed

logger = logging.getLogger(__name__)


def _serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="club-player-photo")


def _delete_previous(path, prefix):
    if path and path.startswith(prefix):
        try:
            storage.delete_club_photo(path)
        except Exception:
            logger.exception("Could not remove previous private club photo")


def register(club_bp):
    def route(path, methods):
        def decorate(view):
            return club_bp.route(f"/club/<int:program_id>/roster/<int:member_id>/{path}", methods=methods)(
                require_club_manager()(transaction(view))
            )

        return decorate

    def member_resource(program_id, member_id):
        from src.routes.club import _member_subject

        member = resource(ClubRosterMember, program_id, member_id)
        if _member_subject(member)[0] is None:
            raise HomeError("Not found", 404)
        return member

    @route("profile", ["GET"])
    def club_player_profile(program_id, member_id):
        response = jsonify(profile_payload(member_resource(program_id, member_id)))
        response.headers["Cache-Control"] = "private, no-store"
        return response

    @route("photo", ["GET", "POST", "DELETE"])
    def club_player_photo(program_id, member_id):
        member = member_resource(program_id, member_id)
        prefix = f"club-player-photos/{program_id}/{member_id}/"
        if not storage.is_configured():
            raise HomeError("Media storage is unavailable", 503)
        if request.method == "POST":
            content_type = payload().get("content_type")
            if content_type not in ("image/jpeg", "image/png", "image/webp"):
                raise HomeError("Photo must be JPEG, PNG or WebP")
            upload = storage.mint_upload(
                program_id, member_id, content_type, path_prefix=f"club-player-photos/{program_id}"
            )
            token = _serializer().dumps(
                {"program": program_id, "member": member_id, "user": g.user_id, "path": upload["blob_path"]}
            )
            return jsonify(upload=upload, upload_token=token), 201
        if request.method == "DELETE":
            previous = member.photo_path
            member.photo_path = member.photo_updated_at = None
            db.session.commit()
            _delete_previous(previous, prefix)
            return jsonify(deleted=True)
        if not member.photo_path or not member.photo_path.startswith(prefix):
            raise HomeError("Not found", 404)
        try:
            raw = storage.read_club_photo(member.photo_path)
        except (OSError, storage.StoredMediaError):
            raise HomeError("Not found", 404) from None
        response = send_file(BytesIO(raw), mimetype="image/jpeg", conditional=False, etag=False)
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @route("photo/complete", ["POST"])
    def club_player_photo_complete(program_id, member_id):
        member = member_resource(program_id, member_id)
        prefix = f"club-player-photos/{program_id}/{member_id}/"
        try:
            grant = _serializer().loads(payload().get("upload_token", ""), max_age=3600)
        except (BadSignature, TypeError):
            raise HomeError("Not found", 404) from None
        if any(
            grant.get(k) != v for k, v in {"program": program_id, "member": member_id, "user": g.user_id}.items()
        ) or not grant.get("path", "").startswith(prefix):
            raise HomeError("Not found", 404)
        if not storage.is_configured():
            raise HomeError("Media storage is unavailable", 503)
        try:
            processed, _ = process_photo(storage.read_pending_bytes(grant["path"]))
        except (ValueError, storage.StoredMediaError) as exc:
            raise HomeError(str(exc)) from exc
        previous = member.photo_path
        path = storage.store_club_photo(grant["path"], processed)
        try:
            member.photo_path = path
            member.photo_updated_at = datetime.now(UTC)
            db.session.commit()
        except Exception:
            db.session.rollback()
            _delete_previous(path, prefix)
            raise
        try:
            storage.delete_pending(grant["path"])
        except Exception:
            logger.exception("Could not remove completed club photo upload")
        if previous != path:
            _delete_previous(previous, prefix)
        return jsonify(
            photo={
                "source": "club",
                "url": f"/api/club/{program_id}/roster/{member_id}/photo",
                "updated_at": member.photo_updated_at.isoformat(),
            }
        )

    @club_bp.get("/admin/club-identities")
    @require_api_key
    def admin_club_identities():
        query = LocalPlayer.query.filter_by(provenance="club")
        raw = request.args.get("program_id")
        if raw:
            try:
                program_id = int(raw)
                if program_id <= 0:
                    raise ValueError
            except ValueError:
                return jsonify(error="Invalid program_id"), 400
            memberships = db.session.query(ClubRosterMember.local_player_id).filter_by(program_id=program_id)
            query = query.filter(or_(LocalPlayer.origin_program_id == program_id, LocalPlayer.id.in_(memberships)))
        limit = min(max(request.args.get("limit", 100, type=int), 1), 200)
        offset = max(request.args.get("offset", 0, type=int), 0)
        total = query.count()
        players = []
        for player in query.order_by(LocalPlayer.id.desc()).offset(offset).limit(limit):
            origin = db.session.get(ClubProgram, player.origin_program_id) if player.origin_program_id else None
            memberships = ClubRosterMember.query.filter_by(local_player_id=player.id).all()
            players.append(
                {
                    "id": player.id,
                    "display_name": player.display_name,
                    "origin_program_id": player.origin_program_id,
                    "program_name": origin.name if origin else None,
                    "created_by": player.created_by_user_id,
                    "created_at": player.created_at.isoformat() if player.created_at else None,
                    "is_minor": bool(local_player_is_minor(player)),
                    "suppressed": is_local_player_suppressed(player.id),
                    "memberships": [
                        {
                            "member_id": m.id,
                            "program_id": m.program_id,
                            "program_name": m.program.name,
                            "squad_id": m.squad_id,
                        }
                        for m in memberships
                    ],
                    "takedown_request_url": f"/api/local-players/{player.id}/takedown-request",
                }
            )
        response = jsonify(players=players, total=total, limit=limit, offset=offset)
        response.headers["Cache-Control"] = "private, no-store"
        return response
