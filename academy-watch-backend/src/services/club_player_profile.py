"""Manager-only player aggregate. No public identity or publication side effects."""

from datetime import UTC, datetime

from src.models.funding import ClubRosterSquadHistory, ClubSquad
from src.models.league import db
from src.models.showcase import PlayerProfileClaim, PlayerShowcaseMedia
from src.services.feedback_development import member_development


def close_squad_history(member, now=None):
    now = now or datetime.now(UTC)
    for row in member.squad_history:
        if row.ended_at is None:
            row.ended_at = now


def change_squad(member, squad_id):
    if member.squad_id == squad_id:
        return
    now = datetime.now(UTC)
    close_squad_history(member, now)
    member.squad_history.append(ClubRosterSquadHistory(program_id=member.program_id, squad_id=squad_id, started_at=now))
    member.squad_id = squad_id


def player_claims(member):
    query = PlayerProfileClaim.query.filter_by(status="approved", relationship_type="player")
    return (
        query.filter_by(local_player_id=member.local_player_id)
        if member.local_player_id
        else query.filter_by(player_api_id=member.player_api_id, local_player_id=None)
    )


def member_photo(member, subject, player):
    if (
        not subject["is_minor"]
        and getattr(player, "provenance", None) != "club"
        and (not member.local_player_id or (player.status == "approved" and player.api_player_id == -player.id))
    ):
        owners = [row.user_account_id for row in player_claims(member)]
        photos = PlayerShowcaseMedia.query.filter_by(status="approved", is_primary=True, kind="photo")
        photos = (
            photos.filter_by(local_player_id=member.local_player_id)
            if member.local_player_id
            else photos.filter_by(player_api_id=member.player_api_id, local_player_id=None)
        )
        photo = (
            photos.filter(PlayerShowcaseMedia.uploaded_by_user_id.in_(owners)).order_by(PlayerShowcaseMedia.id).first()
        )
        if photo and photo.public_url:
            return {"source": "player", "url": photo.public_url}
    if member.photo_path:
        return {
            "source": "club",
            "url": f"/api/club/{member.program_id}/roster/{member.id}/photo",
            "updated_at": member.photo_updated_at.isoformat() if member.photo_updated_at else None,
        }
    photo_url = getattr(player, "photo_url", None)
    if subject["subject_type"] == "tracked" and photo_url:
        return {"source": "tracked", "url": photo_url}
    return None


def profile_payload(member):
    from src.models.player_match_entry import ClubResult, PlayerMatchEntry
    from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry
    from src.routes.club import _member_dict, club_report_payload
    from src.routes.video import _reel_payload
    from src.utils.academy_window import current_stats_season

    identity = _member_dict(member)
    if not identity["available"]:
        return None
    squad = db.session.get(ClubSquad, member.squad_id) if member.squad_id else None
    identity.update(
        squad=squad.to_dict() if squad else None,
        claim_status="claimed" if player_claims(member).first() else "unclaimed",
        has_club_photo=bool(member.photo_path),
        age_label=identity.get("age_label") or (str(identity["age"]) if identity.get("age") is not None else None),
    )
    result = {"identity": identity}
    if member.squad_history:
        result["pathway"] = [
            {
                "id": h.id,
                "squad_id": h.squad_id,
                "squad_name": h.squad.name if h.squad else "Unassigned / deleted squad",
                "started_at": h.started_at.isoformat(),
                "ended_at": h.ended_at.isoformat() if h.ended_at else None,
            }
            for h in sorted(member.squad_history, key=lambda h: (h.started_at, h.id))
        ]
    signed_id = member.player_api_id or -member.local_player_id
    entries = (
        PlayerMatchEntry.query.outerjoin(ClubResult, ClubResult.id == PlayerMatchEntry.club_result_id)
        .filter(
            PlayerMatchEntry.club_program_id == member.program_id,
            PlayerMatchEntry.player_api_id == signed_id,
            PlayerMatchEntry.source == "club",
            ClubResult.deleted_at.is_(None),
        )
        .order_by(PlayerMatchEntry.match_date.desc(), PlayerMatchEntry.id.desc())
        .all()
    )
    if entries:
        season = current_stats_season()
        current = [e for e in entries if e.season == season]
        result["results"] = {"entries": [e.to_dict() for e in entries]}
        if current:
            result["results"]["season"] = {
                "year": season,
                "apps": sum(e.minutes > 0 for e in current),
                **{key: sum(getattr(e, key) for e in current) for key in ("minutes", "goals", "assists")},
            }
    film = []
    for entry, match in (
        db.session.query(VideoRosterEntry, VideoMatch)
        .join(VideoMatch, VideoMatch.id == VideoRosterEntry.video_match_id)
        .filter(VideoRosterEntry.club_roster_member_id == member.id, VideoMatch.club_program_id == member.program_id)
        .order_by(VideoMatch.match_date.desc(), VideoMatch.id.desc())
        .all()
    ):
        reel = _reel_payload(match, [entry])
        player_reel = next((p for p in reel["players"] if p["roster_entry_id"] == entry.id), None)
        reports = club_report_payload(match)["reports"] if match.status == "finalized" else []
        snapshot_ids = {
            r.id
            for r in VideoPlayerReport.query.filter_by(
                video_match_id=match.id,
                roster_entry_id=entry.id,
                club_program_id_at_finalize=member.program_id,
                club_roster_member_id_at_finalize=member.id,
            )
        }
        reports = [r for r in reports if r["id"] in snapshot_ids]
        report = next(
            (
                r
                for r in reports
                if r["roster_entry_id"] == entry.id and r.get("identity_confidence") == "human_confirmed"
            ),
            None,
        )
        base = f"/api/club/{member.program_id}/matches/{match.id}"
        film.append(
            {
                "match": match.to_dict(),
                "roster_entry_id": entry.id,
                "minutes_visible": report["minutes_visible"] if report else None,
                "reel_available": bool(player_reel and player_reel["windows"]),
                "reel_url": f"{base}/reel" if player_reel and player_reel["windows"] else None,
                "report_url": f"{base}/report" if report else None,
            }
        )
    if film:
        result["film"] = film
    if member.coach_brief_body:
        result["coach_brief"] = identity["brief"]
    development = member_development(member, signed_id)
    if development:
        result["development"] = development
    if identity["is_minor"]:
        result["scout_interest"] = {"locked": True, "reason": "Scout contact is unavailable for minors."}
    else:
        from flask import g
        from src.models.contact import ContactRequest
        from src.routes.contact import _contact_request_payload, club_visible_requests
        from src.services.contact import contact_rail_enabled

        if contact_rail_enabled():
            contacts = (
                club_visible_requests(g.user_id, [member.program_id])
                .filter(ContactRequest.player_api_id == signed_id)
                .order_by(ContactRequest.created_at.desc())
                .all()
            )
            if contacts:
                result["scout_interest"] = {
                    "locked": False,
                    "requests": [_contact_request_payload(r) for r in contacts],
                }
    if member.note:
        result["note"] = member.note
    return result
