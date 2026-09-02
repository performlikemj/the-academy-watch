"""Verified club-manager roster and match-video console.

Roster membership is a private authorization boundary for video and reports;
it is deliberately not a player claim, public affiliation, or contact-consent
signal. GPU processing, tracklet review, tag review, and finalization remain on
the existing admin-only concierge routes.
"""

from __future__ import annotations

import json
import math
import os
import uuid
from datetime import UTC, datetime, timedelta

from flask import Blueprint, g, jsonify, request
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from src.auth import mint_media_token
from src.models.funding import ClubProgram, ClubRosterMember
from src.models.league import Team, db
from src.models.showcase import LocalPlayer, local_player_is_minor
from src.models.tracked_player import TrackedPlayer
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry, VideoTracklet
from src.services import video_retention, video_storage
from src.services.club_registry import require_club_manager
from src.services.player_identity import retained_shadow_identity_exists
from src.services.player_suppression import is_local_player_suppressed, is_player_suppressed
from src.utils.sanitize import sanitize_plain_text

club_bp = Blueprint("club", __name__)

RAW_RETENTION_DAYS = 90
DEFAULT_MATCH_QUOTA = 3
MAX_MATCH_QUOTA = 100
QUOTA_LOCK_NAMESPACE = 4_343_202
MAX_CAPTURE_META_BYTES = 8 * 1024
MAX_CAPTURE_META_DEPTH = 4
MAX_CAPTURE_META_KEYS = 50
MAX_TIMELINE_SECONDS = 6 * 60 * 60
CLUB_EDITABLE_MATCH_STATUSES = {"created", "uploaded"}
TEXT_LIMITS = {
    "opponent_name": 200,
    "competition": 200,
    "our_kit_color": 50,
    "opponent_kit_color": 50,
}


def _bad_request(message: str):
    return jsonify({"error": message}), 400


def _payload() -> dict:
    data = request.get_json(silent=True)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise ValueError("JSON body must be an object")
    return data


def _clean_optional(value, field: str, limit: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string or null")
    cleaned = sanitize_plain_text(value).strip()
    if len(cleaned) > limit:
        raise ValueError(f"{field} must be at most {limit} characters")
    return cleaned or None


def _positive_int(value, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")
    return value


def _timeline_value(value, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(f"{field} must be a number or null")
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be a number or null") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise ValueError(f"{field} must be a finite non-negative number")
    if parsed > MAX_TIMELINE_SECONDS:
        raise ValueError(f"{field} must be at most {MAX_TIMELINE_SECONDS} seconds")
    return parsed


def _match_date(value):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError("match_date must be YYYY-MM-DD or null")
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("match_date must be YYYY-MM-DD or null") from exc


def _capture_meta(value):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("capture_meta must be an object or null")

    key_count = 0

    def inspect_shape(node, depth: int) -> None:
        nonlocal key_count
        if isinstance(node, dict):
            if depth > MAX_CAPTURE_META_DEPTH:
                raise ValueError(f"capture_meta nesting depth must be at most {MAX_CAPTURE_META_DEPTH}")
            key_count += len(node)
            if key_count > MAX_CAPTURE_META_KEYS:
                raise ValueError(f"capture_meta must contain at most {MAX_CAPTURE_META_KEYS} keys")
            for child in node.values():
                inspect_shape(child, depth + 1)
        elif isinstance(node, list):
            if depth > MAX_CAPTURE_META_DEPTH:
                raise ValueError(f"capture_meta nesting depth must be at most {MAX_CAPTURE_META_DEPTH}")
            for child in node:
                inspect_shape(child, depth + 1)

    inspect_shape(value, 1)
    try:
        encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError) as exc:
        raise ValueError("capture_meta must contain valid JSON values") from exc
    if len(encoded) > MAX_CAPTURE_META_BYTES:
        raise ValueError(f"capture_meta must be at most {MAX_CAPTURE_META_BYTES} serialized bytes")
    return value


def _club_match(program_id: int, match_id: int) -> VideoMatch | None:
    return VideoMatch.query.filter_by(id=match_id, club_program_id=program_id).first()


def _tracked_player(player_api_id: int) -> TrackedPlayer | None:
    return (
        TrackedPlayer.query.filter_by(player_api_id=player_api_id)
        .order_by(TrackedPlayer.is_active.desc(), TrackedPlayer.id.asc())
        .first()
    )


def _local_player_available(player: LocalPlayer | None) -> bool:
    return bool(
        player
        and player.status not in {"rejected", "merged"}
        and player.merged_into_local_player_id is None
        and not is_local_player_suppressed(player.id)
        and not (player.api_player_id and is_player_suppressed(player.api_player_id))
    )


def _member_subject(member: ClubRosterMember) -> tuple[dict | None, object | None]:
    if member.player_api_id is not None:
        if is_player_suppressed(member.player_api_id):
            return None, None
        tracked = _tracked_player(member.player_api_id)
        if tracked is None:
            return None, None
        return (
            {
                "subject_type": "tracked",
                "player_api_id": member.player_api_id,
                "local_player_id": None,
                "display_name": tracked.player_name,
                "position": tracked.position,
                "is_minor": False,
            },
            tracked,
        )
    local = db.session.get(LocalPlayer, member.local_player_id)
    if not _local_player_available(local):
        return None, None
    return (
        {
            "subject_type": "local",
            "player_api_id": None,
            "local_player_id": local.id,
            "display_name": local.display_name,
            "position": local.position,
            "is_minor": local_player_is_minor(local),
        },
        local,
    )


def _member_dict(member: ClubRosterMember) -> dict:
    subject, _ = _member_subject(member)
    out = {
        "id": member.id,
        "program_id": member.program_id,
        "role": member.role,
        "note": member.note,
        "created_at": member.created_at.isoformat() if member.created_at else None,
        "available": subject is not None,
    }
    if subject is not None:
        out.update(subject)
    return out


def _quota() -> int:
    try:
        configured = int(os.getenv("CLUB_MATCH_QUOTA_DEFAULT", str(DEFAULT_MATCH_QUOTA)))
    except ValueError:
        configured = DEFAULT_MATCH_QUOTA
    return min(MAX_MATCH_QUOTA, max(1, configured))


def _lock_program_quota(program_id: int) -> None:
    """Serialize count+insert on Postgres; SQLite tests are single-process."""
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :program_id)"),
            {"namespace": QUOTA_LOCK_NAMESPACE, "program_id": program_id},
        )


def _resolve_team_id(program: ClubProgram) -> int | None:
    if program.team_api_id is None:
        return None
    row = Team.query.filter_by(team_id=program.team_api_id).order_by(Team.season.desc(), Team.id.desc()).first()
    return row.id if row else None


@club_bp.route("/club/<int:program_id>/roster", methods=["GET"])
@require_club_manager()
def list_club_roster(program_id: int):
    rows = (
        ClubRosterMember.query.filter_by(program_id=program_id)
        .order_by(ClubRosterMember.created_at.asc(), ClubRosterMember.id.asc())
        .all()
    )
    return jsonify({"members": [_member_dict(row) for row in rows], "count": len(rows)})


@club_bp.route("/club/<int:program_id>/roster", methods=["POST"])
@require_club_manager()
def add_club_roster_member(program_id: int):
    try:
        data = _payload()
        has_api = data.get("player_api_id") is not None
        has_local = data.get("local_player_id") is not None
        if has_api == has_local:
            raise ValueError("exactly one of player_api_id or local_player_id is required")

        player_api_id = None
        local_player_id = None
        if has_api:
            # This roster link grants private video/report scope only. It does
            # not confer a public affiliation or public footage attribution.
            player_api_id = _positive_int(data.get("player_api_id"), "player_api_id")
            if is_player_suppressed(player_api_id) or _tracked_player(player_api_id) is None:
                return jsonify({"error": "Player not found"}), 404
        else:
            local_player_id = _positive_int(data.get("local_player_id"), "local_player_id")
            local = db.session.get(LocalPlayer, local_player_id)
            # A manager can attach only a local identity they personally created.
            # The response is neutral for foreign, merged, rejected, or suppressed rows.
            if (
                local is None
                or local.created_by_user_id != g.user_id
                or local.status in {"rejected", "merged"}
                or local.merged_into_local_player_id is not None
            ):
                return jsonify({"error": "Player not found"}), 404
            if retained_shadow_identity_exists(
                display_name=local.display_name,
                birth_year=local.birth_year,
                api_player_id=local.api_player_id,
            ):
                return jsonify({"error": "An existing player identity needs review"}), 409
            if not _local_player_available(local):
                return jsonify({"error": "Player not found"}), 404

        member = ClubRosterMember(
            program_id=program_id,
            player_api_id=player_api_id,
            local_player_id=local_player_id,
            added_by_user_id=g.user_id,
            role=_clean_optional(data.get("role"), "role", 80),
            note=_clean_optional(data.get("note"), "note", 500),
        )
        db.session.add(member)
        db.session.commit()
        return jsonify({"member": _member_dict(member)}), 201
    except ValueError as exc:
        db.session.rollback()
        return _bad_request(str(exc))
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Player is already on this club roster"}), 409


@club_bp.route("/club/<int:program_id>/roster/<int:member_id>", methods=["DELETE"])
@require_club_manager()
def delete_club_roster_member(program_id: int, member_id: int):
    member = ClubRosterMember.query.filter_by(id=member_id, program_id=program_id).first()
    if member is None:
        return jsonify({"error": "Roster member not found"}), 404
    # A player who leaves before finalization must not acquire report access.
    VideoRosterEntry.query.filter_by(club_roster_member_id=member.id).update(
        {VideoRosterEntry.club_roster_member_id: None}, synchronize_session=False
    )
    db.session.delete(member)
    db.session.commit()
    return "", 204


@club_bp.route("/club/<int:program_id>/matches", methods=["POST"])
@require_club_manager()
def create_club_match(program_id: int):
    try:
        data = _payload()
        capture_meta = _capture_meta(data.get("capture_meta"))
        program = db.session.get(ClubProgram, program_id)
        if program is None:
            return jsonify({"error": "Club manager access denied"}), 403

        _lock_program_quota(program_id)
        used = db.session.query(func.count(VideoMatch.id)).filter(VideoMatch.club_program_id == program_id).scalar()
        quota = _quota()
        if used >= quota:
            db.session.rollback()
            return (
                jsonify({"error": f"Club match quota reached ({quota})", "quota": quota}),
                429,
            )

        values = {field: _clean_optional(data.get(field), field, limit) for field, limit in TEXT_LIMITS.items()}
        match = VideoMatch(
            team_id=_resolve_team_id(program),
            club_program_id=program_id,
            match_date=_match_date(data.get("match_date")),
            capture_meta=capture_meta,
            status="created",
            **values,
        )
        db.session.add(match)
        db.session.flush()
        match.blob_path = f"matches/{match.id}/{uuid.uuid4().hex}.mp4"
        db.session.commit()
        out = match.to_dict()
        if video_storage.is_configured():
            out["upload"] = video_storage.mint_upload_sas(match.blob_path)
        else:
            out["upload"] = None
            out["upload_unavailable"] = "blob storage not configured"
        return jsonify(out), 201
    except ValueError as exc:
        db.session.rollback()
        return _bad_request(str(exc))


@club_bp.route("/club/<int:program_id>/matches", methods=["GET"])
@require_club_manager()
def list_club_matches(program_id: int):
    """List one program's matches, newest first. Quota caps a program at MAX_MATCH_QUOTA rows, so no paging."""
    rows = (
        VideoMatch.query.filter_by(club_program_id=program_id)
        .order_by(VideoMatch.created_at.desc(), VideoMatch.id.desc())
        .all()
    )
    matches = []
    for match in rows:
        out = match.to_dict(include_job=True)
        out["processing_request_status"] = "requested" if match.processing_requested_at else None
        matches.append(out)
    return jsonify({"matches": matches, "total": len(matches)})


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>/sas", methods=["POST"])
@require_club_manager()
def club_match_sas(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    if match.status not in {"created", "uploaded"}:
        return _bad_request(f"cannot re-mint SAS in status '{match.status}'")
    if not video_retention.can_issue_upload_grant(match):
        return jsonify({"error": "retention deadline too close to issue an upload grant; create a new match"}), 409
    if not video_storage.is_configured():
        return jsonify({"error": "blob storage not configured"}), 503
    return jsonify(video_storage.mint_upload_sas(match.blob_path))


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>/upload-complete", methods=["POST"])
@require_club_manager()
def club_match_upload_complete(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    # Serialize with the retention sweeper: it re-checks this row under the same lock before deleting footage.
    db.session.refresh(match, with_for_update=True)
    if match.status not in {"created", "uploaded"}:
        return _bad_request(f"cannot complete upload in status '{match.status}'")
    if video_retention.retention_window_closed(match):
        return jsonify({"error": "retention window closed; the footage is due for deletion"}), 409
    if not video_storage.is_configured():
        return jsonify({"error": "blob storage not configured"}), 503
    is_reattestation = match.status == "uploaded"
    check = video_storage.verify_uploaded_blob(match.blob_path)
    if not check["ok"]:
        return jsonify({"error": check["error"]}), 422
    # TODO(C2 follow-up): validate media signatures/container with ffprobe during admin processing.
    try:
        data = _payload()
        for field in ("kickoff_s", "halftime_s", "second_half_kickoff_s", "duration_s"):
            if field in data:
                setattr(match, field, _timeline_value(data[field], field))
    except ValueError as exc:
        return _bad_request(str(exc))
    now = datetime.now(UTC)
    match.blob_etag = check["etag"]
    match.status = "uploaded"
    match.uploaded_at = now
    if match.expires_at is None:  # first completion stamps the deadline; a reattestation keeps the original one
        match.expires_at = now + timedelta(days=RAW_RETENTION_DAYS)
    if is_reattestation:
        match.processing_requested_at = None
        match.processing_requested_by_user_id = None
    db.session.commit()
    return jsonify(match.to_dict() | {"size_bytes": check["size_bytes"]})


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>", methods=["PATCH"])
@require_club_manager()
def update_club_match(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    if match.status not in CLUB_EDITABLE_MATCH_STATUSES:
        return _bad_request(f"cannot edit match in status '{match.status}'")
    try:
        data = _payload()
        for field, limit in TEXT_LIMITS.items():
            if field in data:
                setattr(match, field, _clean_optional(data[field], field, limit))
        if "match_date" in data:
            match.match_date = _match_date(data["match_date"])
        for field in ("kickoff_s", "halftime_s", "second_half_kickoff_s", "duration_s"):
            if field in data:
                setattr(match, field, _timeline_value(data[field], field))
        if "capture_meta" in data:
            match.capture_meta = _capture_meta(data["capture_meta"])
    except ValueError as exc:
        return _bad_request(str(exc))
    db.session.commit()
    return jsonify(match.to_dict())


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>", methods=["GET"])
@require_club_manager()
def get_club_match(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    out = match.to_dict(include_job=True)
    out["roster"] = [entry.to_dict() for entry in match.roster_entries]
    out["processing_request_status"] = "requested" if match.processing_requested_at else None
    return jsonify(out)


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>/media-token", methods=["GET"])
@require_club_manager()
def get_club_match_media_token(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    return jsonify(
        mint_media_token(
            match.id,
            email=getattr(g, "user_email", None),
            club_program_id=program_id,
        )
    )


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>/reel", methods=["GET"])
@require_club_manager()
def get_club_match_reel(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404

    # A club sees only identities still available through its own roster
    # boundary. This mirrors the report's suppression/detachment posture while
    # retaining private minor rows for their own verified manager.
    visible_roster_entries = []
    for entry in match.roster_entries:
        member = (
            ClubRosterMember.query.filter_by(
                id=entry.club_roster_member_id,
                program_id=program_id,
            ).first()
            if entry.club_roster_member_id is not None
            else None
        )
        if member is not None and _member_subject(member)[0] is not None:
            visible_roster_entries.append(entry)

    # Imported lazily to keep the club blueprint independent of registration
    # order while sharing the exact admin reel loader and aggregation service.
    from src.routes.video import _reel_payload

    return jsonify(_reel_payload(match, visible_roster_entries))


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>/roster", methods=["PUT"])
@require_club_manager()
def set_club_match_roster(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    if match.status not in CLUB_EDITABLE_MATCH_STATUSES:
        return _bad_request(f"cannot edit roster in status '{match.status}'")
    try:
        entries = _payload().get("entries")
        if not isinstance(entries, list) or not entries:
            raise ValueError("entries must be a non-empty list")
        member_ids: list[int] = []
        seen_numbers: set[int] = set()
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("each entry must be an object")
            member_id = _positive_int(entry.get("club_roster_member_id"), "club_roster_member_id")
            number = entry.get("jersey_number")
            if isinstance(number, bool) or not isinstance(number, int) or not 1 <= number <= 99:
                raise ValueError("each entry needs jersey_number 1-99")
            if member_id in member_ids:
                raise ValueError(f"duplicate club_roster_member_id {member_id}")
            if number in seen_numbers:
                raise ValueError(f"duplicate jersey_number {number}")
            member_ids.append(member_id)
            seen_numbers.add(number)

        members = {
            row.id: row
            for row in ClubRosterMember.query.filter(
                ClubRosterMember.program_id == program_id,
                ClubRosterMember.id.in_(member_ids),
            )
        }
        if len(members) != len(member_ids):
            return _bad_request("every match player must be on this club roster")

        resolved = {}
        for member_id, member in members.items():
            subject, model = _member_subject(member)
            if subject is None:
                return _bad_request("every match player must be an available club roster member")
            resolved[member_id] = (subject, model)

        existing = {row.jersey_number: row for row in match.roster_entries}
        kept_numbers: set[int] = set()
        for payload_entry in entries:
            number = payload_entry["jersey_number"]
            member_id = payload_entry["club_roster_member_id"]
            subject, model = resolved[member_id]
            row = existing.get(number)
            if row is None:
                row = VideoRosterEntry(video_match_id=match.id, jersey_number=number)
                db.session.add(row)
            row.player_name = subject["display_name"]
            row.position = subject["position"]
            row.club_roster_member_id = member_id
            row.tracked_player_id = model.id if isinstance(model, TrackedPlayer) else None
            kept_numbers.add(number)

        removed = 0
        for number, row in existing.items():
            if number not in kept_numbers:
                VideoTracklet.query.filter_by(roster_entry_id=row.id).update(
                    {VideoTracklet.roster_entry_id: None, VideoTracklet.tag_source: None},
                    synchronize_session=False,
                )
                VideoPlayerReport.query.filter_by(roster_entry_id=row.id).delete(synchronize_session=False)
                db.session.delete(row)
                removed += 1
        db.session.commit()
        return jsonify({"roster": [row.to_dict() for row in match.roster_entries], "removed": removed})
    except ValueError as exc:
        db.session.rollback()
        return _bad_request(str(exc))


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>/process", methods=["POST"])
@require_club_manager()
def request_club_match_processing(program_id: int, match_id: int):
    """Record a request only; no GPU job, tag access, or state transition."""
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    if match.status != "uploaded":
        return _bad_request(f"cannot request processing in status '{match.status}' (upload first)")
    if match.kickoff_s is None:
        return _bad_request("kickoff_s must be marked before requesting processing")
    integrity = video_storage.verify_expected_blob(match.blob_path, match.blob_etag)
    if not integrity["ok"]:
        return jsonify({"error": integrity["error"]}), 422
    if match.processing_requested_at is None:
        match.processing_requested_at = datetime.now(UTC)
        match.processing_requested_by_user_id = g.user_id
        db.session.commit()
    return jsonify({"processing_request_status": "requested", "match": match.to_dict()}), 202


@club_bp.route("/club/<int:program_id>/matches/<int:match_id>/report", methods=["GET"])
@require_club_manager()
def get_club_match_report(program_id: int, match_id: int):
    match = _club_match(program_id, match_id)
    if match is None:
        return jsonify({"error": "Match not found"}), 404
    if match.status != "finalized":
        return jsonify({"error": "Report is not finalized"}), 409

    reports = VideoPlayerReport.query.filter_by(
        video_match_id=match.id,
        club_program_id_at_finalize=program_id,
    ).all()
    roster_by_id = {row.id: row for row in match.roster_entries}
    visible = []
    for report in reports:
        subject = None
        if report.club_player_api_id_at_finalize is not None:
            if is_player_suppressed(report.club_player_api_id_at_finalize):
                continue
            subject = {
                "subject_type": "tracked",
                "player_api_id": report.club_player_api_id_at_finalize,
                "local_player_id": None,
                "is_minor": False,
            }
        elif report.club_local_player_id_at_finalize is not None:
            local = db.session.get(LocalPlayer, report.club_local_player_id_at_finalize)
            if not _local_player_available(local):
                continue
            subject = {
                "subject_type": "local",
                "player_api_id": None,
                "local_player_id": local.id,
                "is_minor": local_player_is_minor(local),
            }
        if subject is None:
            continue
        row = report.to_dict()
        entry = roster_by_id.get(report.roster_entry_id)
        row["player_name"] = entry.player_name if entry else None
        row["jersey_number"] = entry.jersey_number if entry else None
        row["subject"] = subject
        visible.append(row)
    visible.sort(key=lambda row: -(row["minutes_visible"] or 0))
    return jsonify({"match": match.to_dict(), "reports": visible})
