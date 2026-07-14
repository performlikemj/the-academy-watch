"""Talent Showcase blueprint — player-owned profiles, highlight reels, and
club-verified footage evidence.

Product slice:
- Public: a player's showcase (curated YouTube reel + self-reported card +
  club-verified appearance evidence from Film Room).
- Users claim a player's profile; an admin approves; approved owners curate the
  reel and profile. All owner-submitted content is pre-moderated (many players
  are minors) — an edit reverts to ``pending`` and is hidden until re-approved.

Reuse decisions (see the build contract):
- Reel storage is the existing ``PlayerLink`` (``link_type='highlight'``); the
  public reel merges newsletter YouTube links as synthetic read-only entries.
- Link moderation reuses the existing ``/admin/player-links`` pipeline — no new
  link-moderation endpoints here.
- Auth mirrors ``routes/scout.py``: ``require_user_auth`` may leave ``g.user``
  unset, so the account is resolved lazily; per-user rate limits key off the
  authenticated email (the ingress proxy collapses per-IP buckets).
"""

import logging
import re
import secrets
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, urlparse

from flask import Blueprint, g, jsonify, request, send_file
from sqlalchemy import func, text
from sqlalchemy.exc import IntegrityError
from src.auth import (
    _ensure_user_account,
    _safe_error_payload,
    _user_serializer,
    require_api_key,
    require_user_auth,
)
from src.extensions import limiter
from src.models.league import NewsletterPlayerYoutubeLink, PlayerLink, Team, UserAccount, db
from src.models.showcase import (
    LocalClub,
    PlayerClubAffiliation,
    PlayerProfileClaim,
    PlayerShowcaseMedia,
    PlayerShowcaseProfile,
)
from src.models.tracked_player import TrackedPlayer
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry
from src.services import showcase_media_storage, social_proof
from src.services.photo_processing import process_photo
from src.utils.sanitize import is_safe_https_url, sanitize_plain_text

logger = logging.getLogger(__name__)

showcase_bp = Blueprint("showcase", __name__)

RELATIONSHIP_TYPES = {"player", "agent", "guardian", "club_official"}
CLAIM_STATUSES = {"pending", "approved", "rejected", "revoked"}
PROFILE_STATUSES = {"pending", "approved"}
MEDIA_STATUSES = {"pending_upload", "pending", "approved", "rejected"}
PREFERRED_FEET = {"left", "right", "both"}
CONTRACT_STATUSES = {"under_contract", "expiring", "free_agent"}
AVAILABILITY_STATUSES = {"open_to_moves", "not_looking", "trial_available"}
PHOTO_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

MAX_BIO_LENGTH = 2000
MAX_POSITIONS_LENGTH = 100
MAX_TITLE_LENGTH = 200
MAX_MESSAGE_LENGTH = 1000
MAX_URL_LENGTH = 500
MAX_REEL_ITEMS = 20
MAX_PHOTOS = 8
MAX_AGENT_NAME_LENGTH = 200
MAX_AGENT_EMAIL_LENGTH = 320
MAX_NATIONALITY_LENGTH = 100
MAX_LANGUAGES_LENGTH = 300
MAX_REVIEW_NOTE_LENGTH = 2000
MIN_HEIGHT_CM = 100
MAX_HEIGHT_CM = 260
VERIFIED_FOOTAGE_CAP = 10
PLAYER_SEARCH_CAP = 20
VERIFICATION_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
VERIFICATION_NOTE_MAX_LENGTH = 500
LOCAL_CLUB_LEVELS = {"grassroots", "academy", "youth", "semi_pro", "professional", "other"}
LOCAL_CLUB_STATUSES = {"pending", "verified", "merged", "rejected"}
AFFILIATION_STATUSES = {"pending", "self_reported", "club_confirmed", "rejected"}
PUBLIC_AFFILIATION_STATUSES = {"self_reported", "club_confirmed"}
MAX_LOCAL_CLUB_NAME_LENGTH = 200
MAX_LOCAL_CLUB_COUNTRY_LENGTH = 100
MAX_LOCAL_CLUB_CITY_LENGTH = 120
MAX_AFFILIATION_SEASON_LENGTH = 20
MAX_AFFILIATIONS = 5

# The only identity gate strong enough for public display (see models/video.py).
VERIFIED_IDENTITY = "human_confirmed"


# ---------------------------------------------------------------------------
# Auth / account helpers (mirrors routes/scout.py)
# ---------------------------------------------------------------------------


def _user_rate_limit_key() -> str:
    # remote_addr is the ingress proxy in production, so per-IP buckets collapse
    # into one shared global bucket — key by the authenticated email.
    return getattr(g, "user_email", None) or (request.remote_addr or "anon")


def _current_user_account():
    """UserAccount for the authenticated request, created on first use."""
    user = getattr(g, "user", None)
    if user is not None:
        return user
    email = getattr(g, "user_email", None)
    if not email:
        return None
    user = UserAccount.query.filter_by(email=email).first()
    if user is None:
        user = _ensure_user_account(email)
        db.session.commit()
    return user


def _has_approved_claim(player_api_id: int, user_id: int) -> bool:
    return (
        PlayerProfileClaim.query.filter_by(
            player_api_id=player_api_id, user_account_id=user_id, status="approved"
        ).first()
        is not None
    )


def _optional_authenticated_context():
    """Best-effort optional Bearer auth for public showcase responses.

    A missing, expired, or malformed token degrades to an anonymous response.
    The account lookup is intentionally read-only: a public GET never creates a
    UserAccount merely because a valid token was supplied.
    """
    try:
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        if not token:
            return None
        data = _user_serializer().loads(token, max_age=60 * 60 * 24 * 30)
        email = (data or {}).get("email")
        if not email:
            return None
        return {
            "email": email,
            "role": (data or {}).get("role"),
            "user": UserAccount.query.filter_by(email=email).first(),
        }
    except Exception:
        return None


def _optional_owner_user(player_api_id: int):
    """The authenticated approved owner of this player, or None (optional auth).

    Parses the Bearer manually — mirroring ``require_user_auth`` internals — so a
    missing / expired / malformed token DEGRADES to the public view instead of
    401. Returns the UserAccount only when the token is valid AND that user holds
    an approved claim on the player. Any error → None (never raise).
    """
    try:
        context = _optional_authenticated_context()
        user = context["user"] if context else None
        if user is None or not _has_approved_claim(player_api_id, user.id):
            return None
        return user
    except Exception:
        # Bad/expired/malformed token, or any lookup error → public view.
        return None


def _approved_claim_or_403(player_api_id: int):
    """Resolve the caller and require an approved claim for the player.

    Returns ``(user, None)`` when the caller owns an approved claim, otherwise
    ``(None, (response, status))`` for the route to return directly.
    """
    user = _current_user_account()
    if user is None:
        return None, (jsonify({"error": "auth context missing email"}), 401)
    if not _has_approved_claim(player_api_id, user.id):
        return None, (jsonify({"error": "You do not have an approved claim for this player"}), 403)
    return user, None


# ---------------------------------------------------------------------------
# Text / URL validation
# ---------------------------------------------------------------------------


def _clean_optional_text(value, max_len: int):
    """Bleach-clean a free-text field; empty/whitespace/non-str → None."""
    if value is None or not isinstance(value, str):
        return None
    cleaned = _sanitize_text(value).strip()
    return cleaned[:max_len] if cleaned else None


def _sanitize_text(value: str) -> str:
    """Sanitize plain text and defensively remove any residual markup.

    ``sanitize_plain_text`` is authoritative in production. The residual-tag
    pass is defense in depth for alternate/test sanitizer implementations.
    """
    return re.sub(r"<[^>]*>", "", sanitize_plain_text(value))


def _normalize_club_name(value: str) -> str:
    """Canonical key for local-club duplicate detection."""
    return LocalClub.normalize_name(value)


def _mint_verification_code() -> str:
    """Mint a short code without visually ambiguous 0/O/1/I characters."""
    return "AW-" + "".join(secrets.choice(VERIFICATION_ALPHABET) for _ in range(8))


def _proof_url_error():
    allowed = ", ".join(social_proof.ALLOWED_SOCIAL_HOSTS)
    return jsonify(
        {
            "error": (
                "proof_url must be an HTTPS public profile URL on one of: "
                f"{allowed}; IP addresses, userinfo, and explicit ports are not allowed"
            )
        }
    ), 400


def _run_claim_proof_check(claim: PlayerProfileClaim, proof_url: str) -> None:
    """Apply one advisory social-profile check result to a claim row."""
    result = social_proof.check_proof(proof_url, claim.verification_code)
    found = bool(result.get("found"))
    note = str(result.get("note") or "The public profile could not be checked.")
    claim.verification_proof_url = proof_url
    claim.verification_checked_at = datetime.now(UTC)
    claim.verification_status = "code_found" if found else "code_not_found"
    claim.verification_note = note[:VERIFICATION_NOTE_MAX_LENGTH]


def _json_object_or_400():
    """Return ``(object, None)`` or a consistent 400 for non-object JSON."""
    payload = request.get_json(silent=True)
    if payload is None:
        if request.is_json and request.get_data(cache=True).strip():
            return None, (jsonify({"error": "JSON body must be an object"}), 400)
        return {}, None
    if not isinstance(payload, dict):
        return None, (jsonify({"error": "JSON body must be an object"}), 400)
    return payload, None


def _youtube_video_id(url: str) -> str | None:
    """Extract the YouTube video id from a safe https URL, else None.

    Server-side port of the frontend ``extractYouTubeId`` — recognises
    watch?v=, youtu.be/<id>, /embed/<id>, /shorts/<id>.
    """
    if not is_safe_https_url(url):
        return None
    try:
        parsed = urlparse(url.strip())
    except (ValueError, TypeError):
        return None
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if host == "youtu.be":
        first = parsed.path.strip("/").split("/")[0]
        return first or None
    if host in ("youtube.com", "m.youtube.com"):
        vid = parse_qs(parsed.query).get("v", [""])[0]
        if vid:
            return vid
        match = re.match(r"^/(?:embed|shorts)/([^/?]+)", parsed.path)
        return match.group(1) if match else None
    return None


def _is_youtube_url(url: str) -> bool:
    """Server-side port of the frontend ``isYouTubeUrl`` (safe https + video id)."""
    return _youtube_video_id(url) is not None


# ---------------------------------------------------------------------------
# Reel composition (shared public + owner)
# ---------------------------------------------------------------------------


def _link_dict(link: PlayerLink) -> dict:
    """Compose a reel item dict — PlayerLink.to_dict lacks sort_order."""
    return {
        "id": link.id,
        "player_id": link.player_id,
        "url": link.url,
        "title": link.title,
        "link_type": link.link_type,
        "status": link.status,
        "upvotes": link.upvotes or 0,
        "sort_order": link.sort_order if link.sort_order is not None else 0,
        "source": "user",
        "created_at": link.created_at.isoformat() if link.created_at else None,
    }


def _media_dict(media: PlayerShowcaseMedia, *, include_preview: bool = False) -> dict:
    """Stable media JSON contract shared by public, owner, and admin routes."""
    payload = {
        "id": media.id,
        "player_api_id": media.player_api_id,
        "kind": media.kind,
        "status": media.status,
        "public_url": media.public_url,
        "content_type": media.content_type,
        "size_bytes": media.size_bytes,
        "is_primary": bool(media.is_primary),
        "sort_order": media.sort_order if media.sort_order is not None else 0,
        "created_at": media.created_at.isoformat() if media.created_at else None,
        "review_note": media.review_note,
    }
    if include_preview and media.status != "approved":
        if media.status == "rejected":
            payload["pending_preview_url"] = None
        else:
            try:
                payload["pending_preview_url"] = showcase_media_storage.pending_preview_url(media.blob_path)
            except Exception as exc:
                logger.warning("Unable to mint pending preview for media %s: %s", media.id, exc)
                payload["pending_preview_url"] = None
    return payload


def _local_club_dict(club: LocalClub) -> dict:
    """Full local-club contract for creators and administrators."""
    return {
        "id": club.id,
        "name": club.name,
        "normalized_name": club.normalized_name,
        "country": club.country,
        "city": club.city,
        "level": club.level,
        "status": club.status,
        "api_team_id": club.api_team_id,
        "merged_into_local_club_id": club.merged_into_local_club_id,
        "provenance": club.provenance,
        "created_by_user_id": club.created_by_user_id,
        "reviewed_by": club.reviewed_by,
        "reviewed_at": club.reviewed_at.isoformat() if club.reviewed_at else None,
        "review_note": club.review_note,
        "created_at": club.created_at.isoformat() if club.created_at else None,
        "updated_at": club.updated_at.isoformat() if club.updated_at else None,
    }


def _local_club_search_dict(club: LocalClub) -> dict:
    """Public search result shape; moderation/audit metadata stays private."""
    return {
        "id": club.id,
        "name": club.name,
        "country": club.country,
        "city": club.city,
        "level": club.level,
        "status": club.status,
    }


def _affiliation_club_name(affiliation: PlayerClubAffiliation) -> str | None:
    """Resolve the display club, following one local-club merge hop."""
    if affiliation.team_api_id is not None:
        team = (
            Team.query.filter_by(team_id=affiliation.team_api_id).order_by(Team.season.desc(), Team.id.desc()).first()
        )
        return team.name if team else None

    club = db.session.get(LocalClub, affiliation.local_club_id) if affiliation.local_club_id else None
    if club and club.status == "merged" and club.merged_into_local_club_id:
        club = db.session.get(LocalClub, club.merged_into_local_club_id) or club
    return club.name if club else None


def _affiliation_dict(affiliation: PlayerClubAffiliation, *, include_review_note: bool = False) -> dict:
    """Stable affiliation contract shared by showcase and admin responses."""
    payload = {
        "id": affiliation.id,
        "player_api_id": affiliation.player_api_id,
        "team_api_id": affiliation.team_api_id,
        "local_club_id": affiliation.local_club_id,
        "club_name": _affiliation_club_name(affiliation),
        "season": affiliation.season,
        "status": affiliation.status,
        "created_at": affiliation.created_at.isoformat() if affiliation.created_at else None,
    }
    if include_review_note:
        payload["review_note"] = affiliation.review_note
    return payload


def _player_affiliations(player_api_id: int, *, include_private: bool) -> list[dict]:
    query = PlayerClubAffiliation.query.filter_by(player_api_id=player_api_id)
    if not include_private:
        query = query.filter(PlayerClubAffiliation.status.in_(PUBLIC_AFFILIATION_STATUSES))
    rows = query.order_by(PlayerClubAffiliation.created_at.asc(), PlayerClubAffiliation.id.asc()).all()
    return [_affiliation_dict(row, include_review_note=include_private) for row in rows]


def _lock_photo_cap(player_api_id: int) -> None:
    """Serialize photo-row creation per player on PostgreSQL.

    The eight-row cap is a conditional count and cannot be expressed as a
    portable table constraint. A transaction-scoped advisory lock closes the
    count-then-insert race in production; SQLite tests remain a no-op.
    """
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :player_api_id)"),
            {"namespace": 5_455_001, "player_api_id": player_api_id},
        )


def _lock_affiliation_cap(player_api_id: int) -> None:
    """Serialize affiliation cap/duplicate checks per player on PostgreSQL."""
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :player_api_id)"),
            {"namespace": 5_455_002, "player_api_id": player_api_id},
        )


def _cleanup_failed_publication(public_url: str | None, media_id: int) -> None:
    """Compensate a published blob when moderation cannot commit approval."""
    if not public_url:
        return
    try:
        showcase_media_storage.delete_published(public_url)
    except Exception as exc:
        logger.error("Failed to compensate public blob for media %s: %s", media_id, exc)


def _player_photos(player_api_id: int, *, include_unapproved: bool) -> list[dict]:
    query = PlayerShowcaseMedia.query.filter_by(player_api_id=player_api_id, kind="photo")
    if not include_unapproved:
        query = query.filter(PlayerShowcaseMedia.status == "approved")
    rows = query.order_by(
        PlayerShowcaseMedia.is_primary.desc(),
        PlayerShowcaseMedia.sort_order.asc(),
        PlayerShowcaseMedia.created_at.asc(),
        PlayerShowcaseMedia.id.asc(),
    ).all()
    return [_media_dict(row, include_preview=include_unapproved) for row in rows]


def _highlight_reel(player_api_id: int, *, include_pending: bool) -> list[dict]:
    """The player's highlight reel: approved (and, for owners, pending) highlight
    ``PlayerLink`` rows ordered by sort_order, then newsletter YouTube links
    appended as synthetic read-only entries (dedup by URL; not reorderable)."""
    statuses = ("approved", "pending") if include_pending else ("approved",)
    order_col = func.coalesce(PlayerLink.sort_order, 0)
    links = (
        PlayerLink.query.filter(
            PlayerLink.player_id == player_api_id,
            PlayerLink.link_type == "highlight",
            PlayerLink.status.in_(statuses),
        )
        .order_by(order_col.asc(), PlayerLink.upvotes.desc(), PlayerLink.created_at.desc())
        .all()
    )
    results = [_link_dict(link) for link in links]

    # Dedup by canonical YouTube video id (same video, different URL forms),
    # falling back to the raw URL for non-YouTube approved highlights.
    def _dedup_key(url: str) -> str:
        return _youtube_video_id(url) or url

    seen_urls = {_dedup_key(r["url"]) for r in results}
    yt_rows = (
        NewsletterPlayerYoutubeLink.query.filter_by(player_id=player_api_id)
        .order_by(NewsletterPlayerYoutubeLink.created_at.desc())
        .all()
    )
    for yt in yt_rows:
        # Newsletter links are admin-entered with no write-side URL validation —
        # only merge ones that are verifiably YouTube (defense in depth: a stored
        # non-https URL must never reach the public <a href> sink).
        if not _is_youtube_url(yt.youtube_link):
            continue
        if _dedup_key(yt.youtube_link) in seen_urls:
            continue
        seen_urls.add(_dedup_key(yt.youtube_link))
        results.append(
            {
                "id": f"yt-{yt.id}",
                "player_id": yt.player_id,
                "url": yt.youtube_link,
                "title": (yt.player_name + " Highlights") if yt.player_name else "Match Highlights",
                "link_type": "highlight",
                "status": "approved",
                "upvotes": 0,
                "sort_order": None,
                "source": "newsletter",
                "created_at": yt.created_at.isoformat() if yt.created_at else None,
            }
        )
    return results


def _resolve_player_name(player_api_id: int):
    """Best-effort display name from the tracking universe (may be None)."""
    tracked = TrackedPlayer.query.filter_by(player_api_id=player_api_id).order_by(TrackedPlayer.id).first()
    return tracked.player_name if tracked and tracked.player_name else None


# ---------------------------------------------------------------------------
# Flywheel X — Film Room → verified footage evidence
# ---------------------------------------------------------------------------


def _verified_footage(player_api_id: int) -> list[dict]:
    """Club-verified appearance evidence for a player.

    Joins through the authoritative roster entry (not the denormalized report
    column): a player's TrackedPlayer ids → roster entries linked to them →
    their reports on finalized matches with ``human_confirmed`` identity. Any
    exception degrades to ``[]`` — this must never break the showcase payload.
    """
    try:
        tp_ids = [
            row[0]
            for row in db.session.query(TrackedPlayer.id).filter(TrackedPlayer.player_api_id == player_api_id).all()
        ]
        if not tp_ids:
            return []

        rows = (
            db.session.query(VideoPlayerReport, VideoMatch)
            .join(VideoRosterEntry, VideoRosterEntry.id == VideoPlayerReport.roster_entry_id)
            .join(VideoMatch, VideoMatch.id == VideoPlayerReport.video_match_id)
            .filter(VideoRosterEntry.tracked_player_id.in_(tp_ids))
            .filter(VideoMatch.status == "finalized")
            .filter(VideoPlayerReport.identity_confidence == VERIFIED_IDENTITY)
            .order_by(VideoMatch.match_date.desc().nullslast(), VideoMatch.id.desc())
            .limit(VERIFIED_FOOTAGE_CAP)
            .all()
        )

        out = []
        for report, match in rows:
            coverage = report.coverage if isinstance(report.coverage, dict) else {}
            evidence = report.identity_evidence if isinstance(report.identity_evidence, dict) else {}
            out.append(
                {
                    "match_id": match.id,
                    "match_date": match.match_date.isoformat() if match.match_date else None,
                    "opponent_name": match.opponent_name,
                    "team_name": match.team.name if match.team else None,
                    "minutes_on_camera": report.minutes_visible,
                    "pct_of_match": coverage.get("pct_of_match"),
                    "identity_source": evidence.get("source") or VERIFIED_IDENTITY,
                    "verified": True,
                }
            )
        return out
    except Exception as exc:
        logger.warning("verified_footage failed for player %s: %s", player_api_id, exc)
        return []


# ---------------------------------------------------------------------------
# Authenticated local-club discovery + creation
# ---------------------------------------------------------------------------


@showcase_bp.route("/clubs/search", methods=["GET"])
@require_user_auth
def search_clubs():
    """Search API-synced teams and the isolated self-reported club layer."""
    try:
        raw_q = request.args.get("q")
        q = _sanitize_text(raw_q).strip() if isinstance(raw_q, str) else ""
        q = re.sub(r"\s+", " ", q)
        if len(q) < 2:
            return jsonify({"error": "q must be at least 2 characters"}), 400

        ranked_teams = (
            db.session.query(
                Team.team_id.label("team_api_id"),
                Team.name.label("name"),
                Team.country.label("country"),
                func.row_number()
                .over(
                    partition_by=Team.team_id,
                    order_by=(Team.season.desc(), Team.id.desc()),
                )
                .label("row_number"),
            )
            .filter(Team.name.ilike(f"%{q}%"))
            .subquery()
        )
        teams = (
            db.session.query(
                ranked_teams.c.team_api_id,
                ranked_teams.c.name,
                ranked_teams.c.country,
            )
            .filter(ranked_teams.c.row_number == 1)
            .order_by(ranked_teams.c.name.asc(), ranked_teams.c.team_api_id.asc())
            .limit(10)
            .all()
        )
        local_clubs = (
            LocalClub.query.filter(
                LocalClub.name.ilike(f"%{q}%"),
                LocalClub.status.in_(("pending", "verified")),
            )
            .order_by(LocalClub.name.asc(), LocalClub.id.asc())
            .limit(10)
            .all()
        )
        return jsonify(
            {
                "api_teams": [
                    {"team_api_id": team.team_api_id, "name": team.name, "country": team.country} for team in teams
                ],
                "local_clubs": [_local_club_search_dict(club) for club in local_clubs],
            }
        )
    except Exception as e:
        logger.error("Error in search_clubs: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to search clubs")), 500


@showcase_bp.route("/local-clubs", methods=["POST"])
@require_user_auth
@limiter.limit("10 per hour", key_func=_user_rate_limit_key)
def create_local_club():
    """Create a pending community club without touching API-synced teams."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401

        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error

        raw_name = payload.get("name")
        if not isinstance(raw_name, str):
            return jsonify({"error": "name is required and must be a string"}), 400
        name = _sanitize_text(raw_name).strip()
        if not 2 <= len(name) <= MAX_LOCAL_CLUB_NAME_LENGTH:
            return jsonify({"error": "name must be between 2 and 200 characters"}), 400

        country = _clean_optional_text(payload.get("country"), MAX_LOCAL_CLUB_COUNTRY_LENGTH)
        city = _clean_optional_text(payload.get("city"), MAX_LOCAL_CLUB_CITY_LENGTH)
        raw_level = payload.get("level")
        if raw_level is None or (isinstance(raw_level, str) and not raw_level.strip()):
            level = None
        elif isinstance(raw_level, str):
            level = _sanitize_text(raw_level).strip().lower()
            if level not in LOCAL_CLUB_LEVELS:
                return jsonify({"error": f"level must be one of {sorted(LOCAL_CLUB_LEVELS)}"}), 400
        else:
            return jsonify({"error": f"level must be one of {sorted(LOCAL_CLUB_LEVELS)}"}), 400

        normalized_name = _normalize_club_name(name)
        existing = (
            LocalClub.query.filter(
                LocalClub.normalized_name == normalized_name,
                func.lower(func.coalesce(LocalClub.country, "")) == (country or "").lower(),
                LocalClub.status != "rejected",
            )
            .order_by(LocalClub.id.asc())
            .first()
        )
        if existing is not None:
            return (
                jsonify(
                    {
                        "error": "A local club with this name and country already exists",
                        "existing": _local_club_search_dict(existing),
                    }
                ),
                409,
            )

        club = LocalClub(
            name=name,
            country=country,
            city=city,
            level=level,
            status="pending",
            provenance="user",
            created_by_user_id=user.id,
        )
        db.session.add(club)
        db.session.commit()
        return jsonify({"club": _local_club_dict(club)}), 201
    except Exception as e:
        db.session.rollback()
        logger.error("Error in create_local_club: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to create local club")), 500


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


@showcase_bp.route("/players/<int:player_api_id>/showcase", methods=["GET"])
def get_player_showcase(player_api_id: int):
    """Showcase payload: approved profile + reel + verified footage + claim status.

    Optionally authenticated: an approved owner (valid Bearer) additionally sees
    their own pending highlight items and a pending profile draft (each carrying
    a ``status`` for the frontend's "pending review" badge). Anonymous, non-owner,
    or bad-token callers get the approved-only public view — never a 401.
    """
    try:
        auth_context = _optional_authenticated_context()
        authenticated = auth_context is not None
        auth_user = auth_context["user"] if auth_context else None
        is_owner = bool(auth_user and _has_approved_claim(player_api_id, auth_user.id))
        profile_row = PlayerShowcaseProfile.query.filter_by(player_api_id=player_api_id).first()
        if profile_row and profile_row.status == "approved":
            profile = profile_row.public_dict(include_agent_contact=authenticated)
        elif profile_row and is_owner and profile_row.status == "pending":
            # Owner sees their unpublished draft with its status; public does not.
            profile = profile_row.owner_dict()
        else:
            profile = None

        reel = _highlight_reel(player_api_id, include_pending=is_owner)
        photos = _player_photos(player_api_id, include_unapproved=is_owner)

        claimed = PlayerProfileClaim.query.filter_by(player_api_id=player_api_id, status="approved").first() is not None

        return jsonify(
            {
                "player_api_id": player_api_id,
                "profile": profile,
                "reel": reel,
                "photos": photos,
                "affiliations": _player_affiliations(
                    player_api_id,
                    include_private=is_owner,
                ),
                "verified_footage": _verified_footage(player_api_id),
                "claim_status": "claimed" if claimed else "unclaimed",
            }
        )
    except Exception as e:
        logger.error("Error in get_player_showcase: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load showcase")), 500


# ---------------------------------------------------------------------------
# Local development media transport (never active with Azure or in prod/stage)
# ---------------------------------------------------------------------------


@showcase_bp.route("/dev/showcase-media/<path:blob_path>", methods=["PUT"])
def dev_put_showcase_media(blob_path: str):
    """Local-dev stand-in for the browser's direct Azure BlockBlob PUT."""
    if not showcase_media_storage.is_local_dev_enabled():
        return jsonify({"error": "not found"}), 404
    if blob_path.startswith("published/"):
        return jsonify({"error": "invalid blob path"}), 400
    if request.mimetype not in PHOTO_CONTENT_TYPES:
        return jsonify({"error": f"Content-Type must be one of {sorted(PHOTO_CONTENT_TYPES)}"}), 400

    max_bytes = showcase_media_storage.max_photo_bytes()
    if request.content_length is not None and request.content_length > max_bytes:
        return jsonify({"error": "photo exceeds the upload size limit"}), 413
    raw = request.stream.read(max_bytes + 1)
    if not raw:
        return jsonify({"error": "photo upload is empty"}), 400
    if len(raw) > max_bytes:
        return jsonify({"error": "photo exceeds the upload size limit"}), 413
    try:
        path = showcase_media_storage.local_pending_path(blob_path, create_parent=True)
        with path.open("xb") as pending_file:
            pending_file.write(raw)
    except FileExistsError:
        return jsonify({"error": "pending upload already exists"}), 409
    except (showcase_media_storage.InvalidBlobPathError, showcase_media_storage.StorageNotConfiguredError):
        return jsonify({"error": "invalid blob path"}), 400
    return "", 201


@showcase_bp.route("/dev/showcase-media/<path:blob_path>", methods=["GET"])
def dev_get_showcase_media(blob_path: str):
    """Serve a private preview or approved local artifact during development."""
    if not showcase_media_storage.is_local_dev_enabled():
        return jsonify({"error": "not found"}), 404
    try:
        path = showcase_media_storage.local_serving_path(blob_path)
    except (showcase_media_storage.InvalidBlobPathError, showcase_media_storage.StorageNotConfiguredError):
        return jsonify({"error": "not found"}), 404
    if not path.is_file():
        return jsonify({"error": "not found"}), 404
    response = send_file(path, conditional=True)
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


# ---------------------------------------------------------------------------
# User-authed — claims
# ---------------------------------------------------------------------------


@showcase_bp.route("/players/<int:player_api_id>/claim", methods=["POST"])
@require_user_auth
@limiter.limit("3 per hour", key_func=_user_rate_limit_key)
def submit_profile_claim(player_api_id: int):
    """Submit a pending claim to own a player's profile."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401

        payload = request.get_json(silent=True) or {}
        relationship_type = (payload.get("relationship_type") or "").strip().lower()
        if relationship_type not in RELATIONSHIP_TYPES:
            return jsonify({"error": f"relationship_type must be one of {sorted(RELATIONSHIP_TYPES)}"}), 400
        message = _clean_optional_text(payload.get("message"), MAX_MESSAGE_LENGTH)

        existing = PlayerProfileClaim.query.filter_by(player_api_id=player_api_id, user_account_id=user.id).first()
        if existing:
            if existing.status in ("rejected", "revoked"):
                # Recovery path: a rejected/revoked claim may be resubmitted —
                # reset it to pending for a fresh admin review.
                existing.relationship_type = relationship_type
                existing.message = message
                existing.status = "pending"
                existing.reviewed_by = None
                existing.reviewed_at = None
                existing.created_at = datetime.now(UTC)
                existing.verification_code = _mint_verification_code()
                existing.verification_proof_url = None
                existing.verification_status = "unverified"
                existing.verification_checked_at = None
                existing.verification_note = None
                existing.verification_method = None
                db.session.commit()
                return jsonify({"claim": existing.to_dict()}), 201
            return jsonify(
                {"error": "You have already submitted a claim for this player", "claim": existing.to_dict()}
            ), 409

        claim = PlayerProfileClaim(
            player_api_id=player_api_id,
            user_account_id=user.id,
            relationship_type=relationship_type,
            message=message,
            status="pending",
            verification_code=_mint_verification_code(),
            verification_status="unverified",
        )
        db.session.add(claim)
        try:
            db.session.commit()
        except IntegrityError:
            # Lost the unique-constraint race (double submit) — honour idempotency with 409.
            db.session.rollback()
            existing = PlayerProfileClaim.query.filter_by(player_api_id=player_api_id, user_account_id=user.id).first()
            if existing is not None:
                return jsonify(
                    {"error": "You have already submitted a claim for this player", "claim": existing.to_dict()}
                ), 409
            raise
        return jsonify({"claim": claim.to_dict()}), 201
    except Exception as e:
        db.session.rollback()
        logger.error("Error in submit_profile_claim: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to submit claim")), 500


@showcase_bp.route("/me/claims", methods=["GET"])
@require_user_auth
@limiter.limit("60 per minute", key_func=_user_rate_limit_key)
def my_claims():
    """The authenticated user's claims with statuses and best-effort player names."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        claims = (
            PlayerProfileClaim.query.filter_by(user_account_id=user.id)
            .order_by(PlayerProfileClaim.created_at.desc(), PlayerProfileClaim.id.desc())
            .all()
        )
        if any(claim.verification_code is None for claim in claims):
            for claim in claims:
                if claim.verification_code is None:
                    claim.verification_code = _mint_verification_code()
            db.session.commit()
        out = []
        for claim in claims:
            payload = claim.to_dict()
            payload["player_name"] = _resolve_player_name(claim.player_api_id)
            out.append(payload)
        return jsonify({"claims": out})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in my_claims: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load claims")), 500


@showcase_bp.route("/me/claims/<int:claim_id>/verify", methods=["POST"])
@require_user_auth
@limiter.limit("6 per hour", key_func=_user_rate_limit_key)
def verify_my_claim(claim_id: int):
    """Run an advisory social-profile proof check for the caller's pending claim."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        claim = PlayerProfileClaim.query.filter_by(id=claim_id, user_account_id=user.id).first()
        if claim is None:
            return jsonify({"error": "claim not found"}), 404
        if claim.status != "pending":
            return jsonify({"error": f"cannot verify a {claim.status} claim"}), 409

        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        raw_proof_url = payload.get("proof_url")
        proof_url = raw_proof_url.strip() if isinstance(raw_proof_url, str) else ""
        valid, _ = social_proof.validate_proof_url(proof_url)
        if not valid or len(proof_url) > MAX_URL_LENGTH:
            return _proof_url_error()

        if claim.verification_code is None:
            claim.verification_code = _mint_verification_code()
        _run_claim_proof_check(claim, proof_url)
        db.session.commit()
        return jsonify({"claim": claim.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in verify_my_claim: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to verify claim proof")), 500


# ---------------------------------------------------------------------------
# Owner-gated — affiliations, profile + reel curation
# ---------------------------------------------------------------------------


@showcase_bp.route("/players/<int:player_api_id>/showcase/affiliations", methods=["POST"])
@require_user_auth
@limiter.limit("10 per hour", key_func=_user_rate_limit_key)
def create_player_affiliation(player_api_id: int):
    """Submit one pre-moderated self-reported club affiliation."""
    try:
        user, error = _approved_claim_or_403(player_api_id)
        if error:
            return error

        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error

        local_club_id = payload.get("local_club_id")
        team_api_id = payload.get("team_api_id")
        has_local_club = local_club_id is not None
        has_api_team = team_api_id is not None
        if has_local_club == has_api_team:
            return jsonify({"error": "exactly one of local_club_id or team_api_id is required"}), 400

        if has_local_club:
            if isinstance(local_club_id, bool) or not isinstance(local_club_id, int) or local_club_id <= 0:
                return jsonify({"error": "local_club_id must reference an active local club"}), 400
            local_club = db.session.get(LocalClub, local_club_id)
            if local_club is None or local_club.status in ("merged", "rejected"):
                return jsonify({"error": "local_club_id must reference an active local club"}), 400
        elif isinstance(team_api_id, bool) or not isinstance(team_api_id, int) or team_api_id <= 0:
            return jsonify({"error": "team_api_id must be a positive integer"}), 400

        raw_season = payload.get("season")
        if raw_season is None:
            season = None
        elif not isinstance(raw_season, str):
            return jsonify({"error": "season must be a string of at most 20 characters"}), 400
        else:
            season = _sanitize_text(raw_season).strip() or None
            if season is not None and len(season) > MAX_AFFILIATION_SEASON_LENGTH:
                return jsonify({"error": "season must be a string of at most 20 characters"}), 400

        _lock_affiliation_cap(player_api_id)
        duplicate_query = PlayerClubAffiliation.query.filter(
            PlayerClubAffiliation.player_api_id == player_api_id,
            PlayerClubAffiliation.status != "rejected",
        )
        if has_local_club:
            duplicate_query = duplicate_query.filter(PlayerClubAffiliation.local_club_id == local_club_id)
        else:
            duplicate_query = duplicate_query.filter(PlayerClubAffiliation.team_api_id == team_api_id)
        if duplicate_query.first() is not None:
            return jsonify({"error": "This club affiliation has already been submitted"}), 409

        active_count = PlayerClubAffiliation.query.filter(
            PlayerClubAffiliation.player_api_id == player_api_id,
            PlayerClubAffiliation.status != "rejected",
        ).count()
        if active_count >= MAX_AFFILIATIONS:
            return jsonify({"error": f"affiliation limit reached ({MAX_AFFILIATIONS})"}), 409

        affiliation = PlayerClubAffiliation(
            player_api_id=player_api_id,
            local_club_id=local_club_id if has_local_club else None,
            team_api_id=team_api_id if has_api_team else None,
            season=season,
            status="pending",
            created_by_user_id=user.id,
        )
        db.session.add(affiliation)
        db.session.commit()
        return jsonify({"affiliation": _affiliation_dict(affiliation, include_review_note=True)}), 201
    except Exception as e:
        db.session.rollback()
        logger.error("Error in create_player_affiliation: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to create affiliation")), 500


@showcase_bp.route(
    "/players/<int:player_api_id>/showcase/affiliations/<int:aff_id>",
    methods=["DELETE"],
)
@require_user_auth
def delete_player_affiliation(player_api_id: int, aff_id: int):
    """Delete an affiliation belonging to a player whose profile the caller owns."""
    try:
        _, error = _approved_claim_or_403(player_api_id)
        if error:
            return error
        affiliation = PlayerClubAffiliation.query.filter_by(id=aff_id, player_api_id=player_api_id).first()
        if affiliation is None:
            return jsonify({"error": "affiliation not found"}), 404
        db.session.delete(affiliation)
        db.session.commit()
        return jsonify({"deleted": True})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in delete_player_affiliation: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to delete affiliation")), 500


@showcase_bp.route("/players/<int:player_api_id>/showcase/profile", methods=["PUT"])
@require_user_auth
@limiter.limit("20 per hour", key_func=_user_rate_limit_key)
def upsert_showcase_profile(player_api_id: int):
    """Upsert the self-reported profile card. Any edit reverts to pending
    (hidden from public until an admin re-approves)."""
    try:
        user, error = _approved_claim_or_403(player_api_id)
        if error:
            return error

        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        bio = _clean_optional_text(payload.get("bio"), MAX_BIO_LENGTH)
        positions = _clean_optional_text(payload.get("positions"), MAX_POSITIONS_LENGTH)

        preferred_foot = payload.get("preferred_foot")
        if preferred_foot is not None:
            preferred_foot = str(preferred_foot).strip().lower() or None
            if preferred_foot and preferred_foot not in PREFERRED_FEET:
                return jsonify({"error": f"preferred_foot must be one of {sorted(PREFERRED_FEET)}"}), 400

        height_cm = payload.get("height_cm")
        if height_cm is not None:
            if isinstance(height_cm, bool) or not isinstance(height_cm, int):
                return jsonify({"error": "height_cm must be an integer"}), 400
            if height_cm < MIN_HEIGHT_CM or height_cm > MAX_HEIGHT_CM:
                return jsonify({"error": f"height_cm must be between {MIN_HEIGHT_CM} and {MAX_HEIGHT_CM}"}), 400

        contract_status = payload.get("contract_status")
        if contract_status is not None:
            contract_status = str(contract_status).strip().lower() or None
            if contract_status and contract_status not in CONTRACT_STATUSES:
                return jsonify({"error": f"contract_status must be one of {sorted(CONTRACT_STATUSES)}"}), 400

        availability = payload.get("availability")
        if availability is not None:
            availability = str(availability).strip().lower() or None
            if availability and availability not in AVAILABILITY_STATUSES:
                return jsonify({"error": f"availability must be one of {sorted(AVAILABILITY_STATUSES)}"}), 400

        contract_until = None
        raw_contract_until = payload.get("contract_until")
        if raw_contract_until not in (None, ""):
            if not isinstance(raw_contract_until, str):
                return jsonify({"error": "contract_until must be an ISO date (YYYY-MM-DD)"}), 400
            try:
                contract_until = date.fromisoformat(raw_contract_until.strip())
            except ValueError:
                return jsonify({"error": "contract_until must be an ISO date (YYYY-MM-DD)"}), 400

        raw_agent_email = payload.get("agent_contact_email")
        agent_contact_email = None
        if raw_agent_email is not None:
            if not isinstance(raw_agent_email, str):
                return jsonify({"error": "agent_contact_email must be a valid email address"}), 400
            agent_contact_email = sanitize_plain_text(raw_agent_email).strip() or None
            if agent_contact_email and (
                len(agent_contact_email) > MAX_AGENT_EMAIL_LENGTH or not EMAIL_PATTERN.fullmatch(agent_contact_email)
            ):
                return jsonify({"error": "agent_contact_email must be a valid email address"}), 400

        agent_name = _clean_optional_text(payload.get("agent_name"), MAX_AGENT_NAME_LENGTH)
        nationality_secondary = _clean_optional_text(payload.get("nationality_secondary"), MAX_NATIONALITY_LENGTH)
        languages = _clean_optional_text(payload.get("languages"), MAX_LANGUAGES_LENGTH)

        profile = PlayerShowcaseProfile.query.filter_by(player_api_id=player_api_id).first()
        if profile is None:
            profile = PlayerShowcaseProfile(player_api_id=player_api_id)
            db.session.add(profile)
        profile.bio = bio
        profile.positions = positions
        profile.preferred_foot = preferred_foot
        profile.height_cm = height_cm
        profile.contract_status = contract_status
        profile.contract_until = contract_until
        profile.availability = availability
        profile.agent_name = agent_name
        profile.agent_contact_email = agent_contact_email
        profile.nationality_secondary = nationality_secondary
        profile.languages = languages
        profile.status = "pending"  # owner edit → pending; hidden until re-approved
        profile.updated_by_user_id = user.id
        db.session.commit()
        return jsonify({"profile": profile.owner_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in upsert_showcase_profile: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to save profile")), 500


@showcase_bp.route("/players/<int:player_api_id>/showcase/photos", methods=["POST"])
@require_user_auth
@limiter.limit("20 per hour", key_func=_user_rate_limit_key)
def create_showcase_photo(player_api_id: int):
    """Create a private pending-upload row and mint a direct browser PUT URL."""
    try:
        user, error = _approved_claim_or_403(player_api_id)
        if error:
            return error
        if not showcase_media_storage.is_configured():
            return jsonify({"error": "Showcase media storage is not configured"}), 503

        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        content_type = payload.get("content_type")
        if not isinstance(content_type, str) or content_type.strip().lower() not in PHOTO_CONTENT_TYPES:
            return jsonify({"error": f"content_type must be one of {sorted(PHOTO_CONTENT_TYPES)}"}), 400
        content_type = content_type.strip().lower()

        size_bytes = payload.get("size_bytes")
        max_bytes = showcase_media_storage.max_photo_bytes()
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int) or size_bytes <= 0:
            return jsonify({"error": "size_bytes must be a positive integer"}), 400
        if size_bytes > max_bytes:
            return jsonify({"error": f"photo exceeds the {max_bytes // (1024**2)}MB limit"}), 400

        _lock_photo_cap(player_api_id)
        active_count = PlayerShowcaseMedia.query.filter(
            PlayerShowcaseMedia.player_api_id == player_api_id,
            PlayerShowcaseMedia.kind == "photo",
            PlayerShowcaseMedia.status != "rejected",
        ).count()
        if active_count >= MAX_PHOTOS:
            return jsonify({"error": f"photo limit reached ({MAX_PHOTOS})"}), 409

        media = PlayerShowcaseMedia(
            player_api_id=player_api_id,
            kind="photo",
            blob_path="pending",
            content_type=content_type,
            size_bytes=size_bytes,
            status="pending_upload",
            uploaded_by_user_id=user.id,
            sort_order=active_count,
        )
        db.session.add(media)
        db.session.flush()
        upload = showcase_media_storage.mint_upload(player_api_id, media.id, content_type)
        media.blob_path = upload["blob_path"]
        db.session.commit()
        return (
            jsonify(
                {
                    "media": _media_dict(media, include_preview=True),
                    "upload": {
                        "url": upload["url"],
                        "method": "PUT",
                        "headers": upload["headers"],
                    },
                }
            ),
            201,
        )
    except showcase_media_storage.StorageNotConfiguredError:
        db.session.rollback()
        return jsonify({"error": "Showcase media storage is not configured"}), 503
    except Exception as e:
        db.session.rollback()
        logger.error("Error in create_showcase_photo: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to create photo upload")), 500


@showcase_bp.route(
    "/players/<int:player_api_id>/showcase/photos/<int:media_id>/complete",
    methods=["POST"],
)
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def complete_showcase_photo(player_api_id: int, media_id: int):
    """Verify a direct upload and move it into the private moderation queue."""
    try:
        _, error = _approved_claim_or_403(player_api_id)
        if error:
            return error
        media = (
            PlayerShowcaseMedia.query.filter_by(id=media_id, player_api_id=player_api_id, kind="photo")
            .with_for_update()
            .first()
        )
        if media is None:
            return jsonify({"error": "photo not found"}), 404
        if media.status != "pending_upload":
            return jsonify({"error": f"cannot complete a {media.status} photo"}), 409
        if not showcase_media_storage.is_configured():
            return jsonify({"error": "Showcase media storage is not configured"}), 503

        verification = showcase_media_storage.verify_pending(media.blob_path)
        if not verification.get("ok"):
            return jsonify({"error": verification.get("error") or "pending upload could not be verified"}), 400
        actual_size = verification.get("size_bytes")
        if not isinstance(actual_size, int) or actual_size <= 0:
            return jsonify({"error": "pending upload is empty or unreadable"}), 400
        if actual_size > showcase_media_storage.max_photo_bytes():
            return jsonify({"error": "pending upload exceeds the photo size limit"}), 400

        media.size_bytes = actual_size
        media.status = "pending"
        media.updated_at = datetime.now(UTC)
        db.session.commit()
        return jsonify({"media": _media_dict(media, include_preview=True)})
    except showcase_media_storage.StorageNotConfiguredError:
        db.session.rollback()
        return jsonify({"error": "Showcase media storage is not configured"}), 503
    except Exception as e:
        db.session.rollback()
        logger.error("Error in complete_showcase_photo: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to complete photo upload")), 500


@showcase_bp.route("/players/<int:player_api_id>/showcase/photos/order", methods=["PATCH"])
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def reorder_showcase_photos(player_api_id: int):
    """Reorder approved photos; pending/rejected/foreign ids are ignored."""
    try:
        _, error = _approved_claim_or_403(player_api_id)
        if error:
            return error
        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        ordered_ids = payload.get("ordered_ids")
        if not isinstance(ordered_ids, list):
            return jsonify({"error": "ordered_ids must be a list"}), 400

        approved = (
            PlayerShowcaseMedia.query.filter_by(player_api_id=player_api_id, kind="photo", status="approved")
            .order_by(PlayerShowcaseMedia.sort_order.asc(), PlayerShowcaseMedia.id.asc())
            .all()
        )
        by_id = {media.id: media for media in approved}
        reordered = []
        seen = set()
        for media_id in ordered_ids:
            if isinstance(media_id, bool) or not isinstance(media_id, int) or media_id in seen:
                continue
            media = by_id.get(media_id)
            if media is not None:
                reordered.append(media)
                seen.add(media_id)
        reordered.extend(media for media in approved if media.id not in seen)
        for position, media in enumerate(reordered):
            media.sort_order = position
        db.session.commit()
        return jsonify({"photos": [_media_dict(media) for media in reordered]})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in reorder_showcase_photos: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to reorder photos")), 500


@showcase_bp.route("/players/<int:player_api_id>/showcase/photos/<int:media_id>", methods=["PATCH"])
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def set_primary_showcase_photo(player_api_id: int, media_id: int):
    """Set one approved photo as primary, clearing every prior primary."""
    try:
        _, error = _approved_claim_or_403(player_api_id)
        if error:
            return error
        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        if payload.get("is_primary") is not True:
            return jsonify({"error": "is_primary must be true"}), 400
        media = (
            PlayerShowcaseMedia.query.filter_by(id=media_id, player_api_id=player_api_id, kind="photo")
            .with_for_update()
            .first()
        )
        if media is None:
            return jsonify({"error": "photo not found"}), 404
        if media.status != "approved":
            return jsonify({"error": "only approved photos can be primary"}), 409

        PlayerShowcaseMedia.query.filter_by(player_api_id=player_api_id, kind="photo").update(
            {PlayerShowcaseMedia.is_primary: False}, synchronize_session=False
        )
        media.is_primary = True
        db.session.commit()
        return jsonify({"media": _media_dict(media)})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in set_primary_showcase_photo: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to set primary photo")), 500


@showcase_bp.route("/players/<int:player_api_id>/showcase/photos/<int:media_id>", methods=["DELETE"])
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def delete_showcase_photo(player_api_id: int, media_id: int):
    """Delete a photo row and both its private and published blob representations."""
    try:
        _, error = _approved_claim_or_403(player_api_id)
        if error:
            return error
        media = (
            PlayerShowcaseMedia.query.filter_by(id=media_id, player_api_id=player_api_id, kind="photo")
            .with_for_update()
            .first()
        )
        if media is None:
            return jsonify({"error": "photo not found"}), 404
        if not showcase_media_storage.is_configured():
            return jsonify({"error": "Showcase media storage is not configured"}), 503

        showcase_media_storage.delete_pending(media.blob_path)
        if media.public_url:
            showcase_media_storage.delete_published(media.public_url)
        db.session.delete(media)
        db.session.commit()
        return jsonify({"deleted": True})
    except showcase_media_storage.StorageNotConfiguredError:
        db.session.rollback()
        return jsonify({"error": "Showcase media storage is not configured"}), 503
    except Exception as e:
        db.session.rollback()
        logger.error("Error in delete_showcase_photo: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to delete photo")), 500


@showcase_bp.route("/players/<int:player_api_id>/showcase/reel", methods=["POST"])
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def add_reel_item(player_api_id: int):
    """Add a pending YouTube highlight to the player's reel (goes to moderation)."""
    try:
        user, error = _approved_claim_or_403(player_api_id)
        if error:
            return error

        payload = request.get_json(silent=True) or {}
        raw_url = (payload.get("url") or "").strip()
        if not raw_url:
            return jsonify({"error": "url is required"}), 400
        if len(raw_url) > MAX_URL_LENGTH:
            return jsonify({"error": "url is too long"}), 400
        if not _is_youtube_url(raw_url):
            return jsonify({"error": "url must be a valid https YouTube link"}), 400
        title = _clean_optional_text(payload.get("title"), MAX_TITLE_LENGTH)

        # Cap the whole player's reel (any status) so pending submissions can't grow unbounded.
        count = PlayerLink.query.filter_by(player_id=player_api_id, link_type="highlight").count()
        if count >= MAX_REEL_ITEMS:
            return jsonify({"error": f"reel limit reached ({MAX_REEL_ITEMS})"}), 400

        link = PlayerLink(
            player_id=player_api_id,
            user_id=user.id,
            url=raw_url,
            title=title,
            link_type="highlight",
            status="pending",
            sort_order=count,
        )
        db.session.add(link)
        db.session.commit()
        return jsonify({"link": _link_dict(link)}), 201
    except Exception as e:
        db.session.rollback()
        logger.error("Error in add_reel_item: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to add reel item")), 500


@showcase_bp.route("/players/<int:player_api_id>/showcase/reel/order", methods=["PATCH"])
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def reorder_reel(player_api_id: int):
    """Set sort_order from an ordered id list. Only integer PlayerLink ids that
    belong to this player and are highlights apply; foreign and synthetic
    ``yt-*`` ids are ignored."""
    try:
        user, error = _approved_claim_or_403(player_api_id)
        if error:
            return error

        payload = request.get_json(silent=True) or {}
        ordered_ids = payload.get("ordered_ids")
        if not isinstance(ordered_ids, list):
            return jsonify({"error": "ordered_ids must be a list"}), 400

        own_links = {
            link.id: link for link in PlayerLink.query.filter_by(player_id=player_api_id, link_type="highlight").all()
        }
        position = 0
        for link_id in ordered_ids:
            if isinstance(link_id, bool) or not isinstance(link_id, int):
                continue  # synthetic "yt-*" (string) / malformed ids are not reorderable
            link = own_links.get(link_id)
            if link is None:
                continue  # foreign id — ignore
            link.sort_order = position
            position += 1
        db.session.commit()
        return jsonify({"reel": _highlight_reel(player_api_id, include_pending=True)})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in reorder_reel: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to reorder reel")), 500


@showcase_bp.route("/players/<int:player_api_id>/showcase/reel/<int:link_id>", methods=["DELETE"])
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def delete_reel_item(player_api_id: int, link_id: int):
    """Delete a reel item — only the submitter or an approved owner of the player.
    Synthetic ``yt-*`` ids never match this integer route (not deletable)."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        link = PlayerLink.query.filter_by(id=link_id, player_id=player_api_id, link_type="highlight").first()
        if link is None:
            return jsonify({"error": "reel item not found"}), 404
        if link.user_id != user.id and not _has_approved_claim(player_api_id, user.id):
            return jsonify({"error": "You are not permitted to delete this reel item"}), 403
        db.session.delete(link)
        db.session.commit()
        return jsonify({"deleted": True})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in delete_reel_item: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to delete reel item")), 500


# ---------------------------------------------------------------------------
# Admin — local clubs + affiliation review
# ---------------------------------------------------------------------------


@showcase_bp.route("/admin/local-clubs", methods=["GET"])
@require_api_key
def admin_list_local_clubs():
    """List local clubs, optionally filtered by moderation status."""
    try:
        status = (request.args.get("status") or "").strip().lower()
        query = LocalClub.query
        if status:
            if status not in LOCAL_CLUB_STATUSES:
                return jsonify({"error": f"invalid status; one of {sorted(LOCAL_CLUB_STATUSES)}"}), 400
            query = query.filter(LocalClub.status == status)
        clubs = query.order_by(LocalClub.created_at.desc(), LocalClub.id.desc()).all()
        return jsonify({"clubs": [_local_club_dict(club) for club in clubs]})
    except Exception as e:
        logger.error("Error in admin_list_local_clubs: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load local clubs")), 500


@showcase_bp.route("/admin/local-clubs/<int:club_id>/review", methods=["POST"])
@require_api_key
def admin_review_local_club(club_id: int):
    """Verify or reject a pending local club."""
    try:
        club = LocalClub.query.filter_by(id=club_id).with_for_update().first()
        if club is None:
            return jsonify({"error": "local club not found"}), 404

        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        raw_action = payload.get("action")
        action = raw_action.strip().lower() if isinstance(raw_action, str) else ""
        if action not in ("verify", "reject"):
            return jsonify({"error": "action must be verify or reject"}), 400
        if club.status != "pending":
            return jsonify({"error": f"cannot {action} a {club.status} local club"}), 409

        now = datetime.now(UTC)
        club.status = "verified" if action == "verify" else "rejected"
        club.review_note = _clean_optional_text(payload.get("note"), MAX_REVIEW_NOTE_LENGTH)
        club.reviewed_by = getattr(g, "user_email", None)
        club.reviewed_at = now
        club.updated_at = now
        db.session.commit()
        return jsonify({"club": _local_club_dict(club)})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in admin_review_local_club: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to review local club")), 500


@showcase_bp.route("/admin/local-clubs/<int:club_id>/merge", methods=["POST"])
@require_api_key
def admin_merge_local_club(club_id: int):
    """Merge one local club into another and repoint every affiliation."""
    try:
        source = LocalClub.query.filter_by(id=club_id).with_for_update().first()
        if source is None:
            return jsonify({"error": "local club not found"}), 404

        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        target_id = payload.get("into_local_club_id")
        if isinstance(target_id, bool) or not isinstance(target_id, int) or target_id <= 0:
            return jsonify({"error": "into_local_club_id must be a positive integer"}), 400
        if target_id == source.id:
            return jsonify({"error": "A local club cannot be merged into itself"}), 400
        if source.status in ("merged", "rejected"):
            return jsonify({"error": f"cannot merge a {source.status} local club"}), 409

        target = LocalClub.query.filter_by(id=target_id).with_for_update().first()
        if target is None or target.status in ("merged", "rejected"):
            return jsonify({"error": "merge target must be an active local club"}), 400

        now = datetime.now(UTC)
        moved_affiliations = PlayerClubAffiliation.query.filter_by(local_club_id=source.id).update(
            {
                PlayerClubAffiliation.local_club_id: target.id,
                PlayerClubAffiliation.updated_at: now,
            },
            synchronize_session=False,
        )
        source.status = "merged"
        source.merged_into_local_club_id = target.id
        source.reviewed_by = getattr(g, "user_email", None)
        source.reviewed_at = now
        source.updated_at = now
        db.session.commit()
        return jsonify(
            {
                "club": _local_club_dict(source),
                "moved_affiliations": moved_affiliations,
            }
        )
    except Exception as e:
        db.session.rollback()
        logger.error("Error in admin_merge_local_club: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to merge local club")), 500


@showcase_bp.route("/admin/local-clubs/<int:club_id>/link-api", methods=["POST"])
@require_api_key
def admin_link_local_club_api(club_id: int):
    """Store an API-Football bridge id on the local row only."""
    try:
        club = db.session.get(LocalClub, club_id)
        if club is None:
            return jsonify({"error": "local club not found"}), 404

        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        team_api_id = payload.get("team_api_id")
        if isinstance(team_api_id, bool) or not isinstance(team_api_id, int) or team_api_id <= 0:
            return jsonify({"error": "team_api_id must be a positive integer"}), 400

        club.api_team_id = team_api_id
        club.updated_at = datetime.now(UTC)
        db.session.commit()
        return jsonify({"club": _local_club_dict(club)})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in admin_link_local_club_api: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to link local club")), 500


@showcase_bp.route("/admin/showcase/affiliations", methods=["GET"])
@require_api_key
def admin_list_affiliations():
    """List player affiliations with resolved club names."""
    try:
        status = (request.args.get("status") or "").strip().lower()
        query = PlayerClubAffiliation.query
        if status:
            if status not in AFFILIATION_STATUSES:
                return jsonify({"error": f"invalid status; one of {sorted(AFFILIATION_STATUSES)}"}), 400
            query = query.filter(PlayerClubAffiliation.status == status)
        affiliations = query.order_by(
            PlayerClubAffiliation.created_at.desc(),
            PlayerClubAffiliation.id.desc(),
        ).all()
        return jsonify(
            {"affiliations": [_affiliation_dict(affiliation, include_review_note=True) for affiliation in affiliations]}
        )
    except Exception as e:
        logger.error("Error in admin_list_affiliations: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load affiliations")), 500


@showcase_bp.route("/admin/showcase/affiliations/<int:aff_id>/review", methods=["POST"])
@require_api_key
def admin_review_affiliation(aff_id: int):
    """Approve a pending self-report or reject it with an optional note."""
    try:
        affiliation = PlayerClubAffiliation.query.filter_by(id=aff_id).with_for_update().first()
        if affiliation is None:
            return jsonify({"error": "affiliation not found"}), 404

        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        raw_action = payload.get("action")
        action = raw_action.strip().lower() if isinstance(raw_action, str) else ""
        if action not in ("approve", "reject"):
            return jsonify({"error": "action must be approve or reject"}), 400
        if affiliation.status != "pending":
            return jsonify({"error": f"cannot {action} a {affiliation.status} affiliation"}), 409

        now = datetime.now(UTC)
        affiliation.status = "self_reported" if action == "approve" else "rejected"
        affiliation.review_note = _clean_optional_text(payload.get("note"), MAX_REVIEW_NOTE_LENGTH)
        affiliation.reviewed_by = getattr(g, "user_email", None)
        affiliation.reviewed_at = now
        affiliation.updated_at = now
        db.session.commit()
        return jsonify({"affiliation": _affiliation_dict(affiliation, include_review_note=True)})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in admin_review_affiliation: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to review affiliation")), 500


# ---------------------------------------------------------------------------
# Admin — media, claim + profile review
# ---------------------------------------------------------------------------


@showcase_bp.route("/admin/showcase/media", methods=["GET"])
@require_api_key
def admin_list_showcase_media():
    """List showcase media, optionally filtered by lifecycle status."""
    try:
        status = (request.args.get("status") or "").strip().lower()
        query = PlayerShowcaseMedia.query.filter_by(kind="photo")
        if status:
            if status not in MEDIA_STATUSES:
                return jsonify({"error": f"invalid status; one of {sorted(MEDIA_STATUSES)}"}), 400
            query = query.filter(PlayerShowcaseMedia.status == status)
        rows = query.order_by(PlayerShowcaseMedia.created_at.desc(), PlayerShowcaseMedia.id.desc()).all()
        return jsonify({"media": [_media_dict(row, include_preview=True) for row in rows]})
    except Exception as e:
        logger.error("Error in admin_list_showcase_media: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load showcase media")), 500


@showcase_bp.route("/admin/showcase/media/<int:media_id>/review", methods=["POST"])
@require_api_key
def admin_review_showcase_media(media_id: int):
    """Approve a processed photo for publication or reject its pending blob."""
    published_url = None
    try:
        media = PlayerShowcaseMedia.query.filter_by(id=media_id).with_for_update().first()
        if media is None or media.kind != "photo":
            return jsonify({"error": "photo not found"}), 404

        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        raw_action = payload.get("action")
        action = raw_action.strip().lower() if isinstance(raw_action, str) else ""
        if action not in ("approve", "reject"):
            return jsonify({"error": "action must be approve or reject"}), 400
        if media.status != "pending":
            return jsonify({"error": f"cannot {action} a {media.status} photo"}), 409
        note = _clean_optional_text(payload.get("note"), MAX_REVIEW_NOTE_LENGTH)
        if not showcase_media_storage.is_configured():
            return jsonify({"error": "Showcase media storage is not configured"}), 503

        if action == "approve":
            try:
                raw = showcase_media_storage.read_pending_bytes(media.blob_path)
                processed, content_type = process_photo(raw)
                published_url = showcase_media_storage.publish(media.blob_path, processed, content_type)
                # Approval is not durable until the original (which can carry
                # minors' EXIF/GPS) is gone. A failure compensates the public
                # write and leaves the row pending for a safe retry.
                showcase_media_storage.delete_pending(media.blob_path)
            except showcase_media_storage.StorageNotConfiguredError:
                db.session.rollback()
                _cleanup_failed_publication(published_url, media.id)
                return jsonify({"error": "Showcase media storage is not configured"}), 503
            except Exception as exc:
                db.session.rollback()
                _cleanup_failed_publication(published_url, media.id)
                logger.warning("Photo processing/publish failed for media %s: %s", media.id, exc)
                return jsonify({"error": "Photo could not be processed or published"}), 422

            media.public_url = published_url
            media.content_type = content_type
            media.size_bytes = len(processed)
            media.status = "approved"
        else:
            try:
                showcase_media_storage.delete_pending(media.blob_path)
            except showcase_media_storage.StorageNotConfiguredError:
                db.session.rollback()
                return jsonify({"error": "Showcase media storage is not configured"}), 503
            except Exception as exc:
                db.session.rollback()
                logger.warning("Pending photo delete failed for rejected media %s: %s", media.id, exc)
                return jsonify({"error": "Photo could not be rejected because its upload could not be deleted"}), 422
            media.status = "rejected"
            media.public_url = None
            media.is_primary = False

        media.review_note = note
        media.reviewed_by = getattr(g, "user_email", None)
        media.reviewed_at = datetime.now(UTC)
        media.updated_at = datetime.now(UTC)
        db.session.commit()
        published_url = None
        return jsonify({"media": _media_dict(media, include_preview=action == "reject")})
    except Exception as e:
        db.session.rollback()
        _cleanup_failed_publication(published_url, media_id)
        logger.error("Error in admin_review_showcase_media: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to review showcase media")), 500


@showcase_bp.route("/admin/showcase/claims", methods=["GET"])
@require_api_key
def admin_list_claims():
    """List profile claims, optionally filtered by status."""
    try:
        status = (request.args.get("status") or "").strip().lower()
        query = PlayerProfileClaim.query
        if status:
            if status not in CLAIM_STATUSES:
                return jsonify({"error": f"invalid status; one of {sorted(CLAIM_STATUSES)}"}), 400
            query = query.filter(PlayerProfileClaim.status == status)
        claims = query.order_by(PlayerProfileClaim.created_at.desc(), PlayerProfileClaim.id.desc()).all()
        out = []
        for claim in claims:
            payload = claim.to_dict()
            payload["player_name"] = _resolve_player_name(claim.player_api_id)
            payload["user_email"] = claim.user.email if claim.user else None
            out.append(payload)
        return jsonify({"claims": out})
    except Exception as e:
        logger.error("Error in admin_list_claims: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load claims")), 500


@showcase_bp.route("/admin/showcase/claims/<int:claim_id>/recheck", methods=["POST"])
@require_api_key
def admin_recheck_claim(claim_id: int):
    """Re-run the advisory check against a claim's stored social proof URL."""
    try:
        claim = db.session.get(PlayerProfileClaim, claim_id)
        if claim is None:
            return jsonify({"error": "claim not found"}), 404
        proof_url = (claim.verification_proof_url or "").strip()
        if not proof_url:
            return jsonify({"error": "claim has no stored proof_url"}), 400
        valid, _ = social_proof.validate_proof_url(proof_url)
        if not valid or len(proof_url) > MAX_URL_LENGTH:
            return _proof_url_error()
        if claim.verification_code is None:
            claim.verification_code = _mint_verification_code()

        _run_claim_proof_check(claim, proof_url)
        db.session.commit()
        return jsonify({"claim": claim.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in admin_recheck_claim: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to re-check claim proof")), 500


@showcase_bp.route("/admin/showcase/claims/<int:claim_id>/review", methods=["POST"])
@require_api_key
def admin_review_claim(claim_id: int):
    """Transition a claim: pending → approved|rejected, approved → revoked.
    Approving does NOT auto-revoke other approved claims (player + agent may co-own)."""
    try:
        claim = db.session.get(PlayerProfileClaim, claim_id)
        if claim is None:
            return jsonify({"error": "claim not found"}), 404

        payload = request.get_json(silent=True) or {}
        action = (payload.get("action") or "").strip().lower()
        # approve doubles as the recovery path for mistaken rejections/revocations.
        transitions = {
            "approve": ({"pending", "rejected", "revoked"}, "approved"),
            "reject": ({"pending"}, "rejected"),
            "revoke": ({"approved"}, "revoked"),
        }
        if action not in transitions:
            return jsonify({"error": "action must be approve, reject, or revoke"}), 400
        allowed_from, target = transitions[action]
        if claim.status not in allowed_from:
            return jsonify({"error": f"cannot {action} a {claim.status} claim"}), 409

        claim.status = target
        claim.reviewed_by = getattr(g, "user_email", None)
        claim.reviewed_at = datetime.now(UTC)
        db.session.commit()
        return jsonify({"claim": claim.to_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in admin_review_claim: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to review claim")), 500


@showcase_bp.route("/admin/showcase/profiles", methods=["GET"])
@require_api_key
def admin_list_profiles():
    """List showcase profiles (default: pending edits awaiting review)."""
    try:
        status = (request.args.get("status") or "pending").strip().lower()
        query = PlayerShowcaseProfile.query
        if status and status != "all":
            if status not in PROFILE_STATUSES:
                return jsonify({"error": f"invalid status; one of {sorted(PROFILE_STATUSES)}"}), 400
            query = query.filter(PlayerShowcaseProfile.status == status)
        profiles = query.order_by(PlayerShowcaseProfile.updated_at.desc().nullslast()).all()
        out = []
        for profile in profiles:
            payload = profile.owner_dict()
            payload["player_name"] = _resolve_player_name(profile.player_api_id)
            out.append(payload)
        return jsonify({"profiles": out})
    except Exception as e:
        logger.error("Error in admin_list_profiles: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load profiles")), 500


@showcase_bp.route("/admin/showcase/profiles/<int:player_api_id>/review", methods=["POST"])
@require_api_key
def admin_review_profile(player_api_id: int):
    """Approve (publish) or reject (keep hidden/pending) a showcase profile edit."""
    try:
        profile = PlayerShowcaseProfile.query.filter_by(player_api_id=player_api_id).first()
        if profile is None:
            return jsonify({"error": "profile not found"}), 404
        payload = request.get_json(silent=True) or {}
        action = (payload.get("action") or "").strip().lower()
        if action not in ("approve", "reject"):
            return jsonify({"error": "action must be approve or reject"}), 400
        profile.status = "approved" if action == "approve" else "pending"
        profile.reviewed_by = getattr(g, "user_email", None)
        profile.reviewed_at = datetime.now(UTC)
        db.session.commit()
        return jsonify({"profile": profile.owner_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in admin_review_profile: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to review profile")), 500


# ---------------------------------------------------------------------------
# Admin — Flywheel X (Film Room roster linking)
# ---------------------------------------------------------------------------


@showcase_bp.route("/admin/showcase/video-rosters", methods=["GET"])
@require_api_key
def admin_list_video_rosters():
    """Finalized matches' roster entries with current tracked_player links and
    each report's identity summary. Filter by match_id or player_api_id."""
    try:
        match_id = request.args.get("match_id", type=int)
        player_api_id = request.args.get("player_api_id", type=int)

        query = (
            db.session.query(VideoRosterEntry, VideoMatch)
            .join(VideoMatch, VideoMatch.id == VideoRosterEntry.video_match_id)
            .filter(VideoMatch.status == "finalized")
        )
        if match_id:
            query = query.filter(VideoMatch.id == match_id)
        if player_api_id:
            tp_ids = [
                row[0]
                for row in db.session.query(TrackedPlayer.id).filter(TrackedPlayer.player_api_id == player_api_id).all()
            ]
            if not tp_ids:
                return jsonify({"rosters": []})
            query = query.filter(VideoRosterEntry.tracked_player_id.in_(tp_ids))

        rows = query.order_by(VideoMatch.match_date.desc().nullslast(), VideoRosterEntry.jersey_number).all()
        out = []
        for roster, match in rows:
            report = VideoPlayerReport.query.filter_by(video_match_id=match.id, roster_entry_id=roster.id).first()
            linked = db.session.get(TrackedPlayer, roster.tracked_player_id) if roster.tracked_player_id else None
            out.append(
                {
                    "roster_id": roster.id,
                    "match_id": match.id,
                    "match_date": match.match_date.isoformat() if match.match_date else None,
                    "opponent_name": match.opponent_name,
                    "team_id": match.team_id,
                    "team_name": match.team.name if match.team else None,
                    "player_name": roster.player_name,
                    "jersey_number": roster.jersey_number,
                    "tracked_player_id": roster.tracked_player_id,
                    "linked_player_api_id": linked.player_api_id if linked else None,
                    "linked_player_name": linked.player_name if linked else None,
                    "identity_confidence": report.identity_confidence if report else None,
                    "has_report": report is not None,
                }
            )
        return jsonify({"rosters": out})
    except Exception as e:
        logger.error("Error in admin_list_video_rosters: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load video rosters")), 500


@showcase_bp.route("/admin/showcase/video-rosters/<int:roster_id>/link", methods=["PUT"])
@require_api_key
def admin_link_video_roster(roster_id: int):
    """Link (or clear) a roster entry to a tracked player. Resolves player_api_id
    to a TrackedPlayer (prefer the match's team, else an active row) and updates
    BOTH the roster and the denormalized column on its existing reports."""
    try:
        roster = db.session.get(VideoRosterEntry, roster_id)
        if roster is None:
            return jsonify({"error": "roster entry not found"}), 404

        payload = request.get_json(silent=True) or {}
        player_api_id = payload.get("player_api_id")

        if player_api_id is None:
            roster.tracked_player_id = None
            for report in VideoPlayerReport.query.filter_by(roster_entry_id=roster.id).all():
                report.tracked_player_id = None
            db.session.commit()
            return jsonify({"roster": roster.to_dict()})

        if isinstance(player_api_id, bool) or not isinstance(player_api_id, int):
            return jsonify({"error": "player_api_id must be an integer or null"}), 400

        candidates = TrackedPlayer.query.filter_by(player_api_id=player_api_id).all()
        if not candidates:
            return jsonify({"error": "no tracked player with that id"}), 404

        match = db.session.get(VideoMatch, roster.video_match_id)
        tracked = None
        if match is not None:
            tracked = next(
                (c for c in candidates if match.team_id in (c.current_club_db_id, c.team_id)),
                None,
            )
        if tracked is None:
            tracked = next((c for c in candidates if c.is_active), None) or candidates[0]

        roster.tracked_player_id = tracked.id
        for report in VideoPlayerReport.query.filter_by(roster_entry_id=roster.id).all():
            report.tracked_player_id = tracked.id
        db.session.commit()
        return jsonify({"roster": roster.to_dict(), "tracked_player_id": tracked.id})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in admin_link_video_roster: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to link roster entry")), 500


@showcase_bp.route("/admin/showcase/player-search", methods=["GET"])
@require_api_key
def admin_player_search():
    """Search active tracked players by name for the roster-linking UI (cap 20)."""
    try:
        q = (request.args.get("q") or "").strip()
        if not q:
            return jsonify({"players": []})
        rows = (
            TrackedPlayer.query.filter(
                TrackedPlayer.player_name.ilike(f"%{q}%"),
                TrackedPlayer.is_active.is_(True),
            )
            .order_by(TrackedPlayer.player_name)
            .limit(PLAYER_SEARCH_CAP * 3)
            .all()
        )
        seen = set()
        out = []
        for tracked in rows:
            if tracked.player_api_id in seen:
                continue
            seen.add(tracked.player_api_id)
            out.append(
                {
                    "player_api_id": tracked.player_api_id,
                    "player_name": tracked.player_name,
                    "team_name": tracked.team.name if tracked.team else None,
                    "status": tracked.status,
                }
            )
            if len(out) >= PLAYER_SEARCH_CAP:
                break
        return jsonify({"players": out})
    except Exception as e:
        logger.error("Error in admin_player_search: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to search players")), 500
