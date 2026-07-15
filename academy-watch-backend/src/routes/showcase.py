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
from dataclasses import dataclass
from datetime import UTC, date, datetime
from urllib.parse import parse_qs, unquote, urlparse

from flask import Blueprint, g, jsonify, request, send_file
from sqlalchemy import func, or_, text
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
    ClubOfficialClaim,
    LocalClub,
    LocalPlayer,
    PlayerClubAffiliation,
    PlayerProfileClaim,
    PlayerShowcaseMedia,
    PlayerShowcaseProfile,
)
from src.models.tracked_player import TrackedPlayer
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry
from src.services import showcase_media_storage, social_proof
from src.services.photo_processing import process_photo, validate_photo
from src.utils.sanitize import is_safe_https_url, sanitize_plain_text

logger = logging.getLogger(__name__)

showcase_bp = Blueprint("showcase", __name__)

RELATIONSHIP_TYPES = {"player", "agent", "guardian", "club_official"}
CLAIM_STATUSES = {"pending", "approved", "rejected", "revoked"}
CLUB_OFFICIAL_CLAIM_STATUSES = {"pending", "approved", "rejected", "revoked"}
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
MAX_CLUB_ROLE_TITLE_LENGTH = 100
LOCAL_PLAYER_STATUSES = {"pending", "approved", "rejected", "merged"}
LOCAL_PLAYER_RELATIONSHIP_TYPES = {"player", "agent", "guardian"}
MAX_LOCAL_PLAYER_NAME_LENGTH = 200
MAX_LOCAL_PLAYER_POSITION_LENGTH = 50
MAX_LOCAL_PLAYER_COUNTRY_LENGTH = 100
MAX_LOCAL_PLAYER_CITY_LENGTH = 120
MIN_LOCAL_PLAYER_BIRTH_YEAR = 1950
MAX_LOCAL_PLAYER_BIRTH_YEAR = 2020
MAX_PENDING_LOCAL_PLAYERS_PER_USER = 10
MAX_PENDING_LOCAL_CLUBS_PER_USER = 10
MAX_PENDING_CLUB_CLAIMS_PER_USER = 5

# The only identity gate strong enough for public display (see models/video.py).
VERIFIED_IDENTITY = "human_confirmed"


@dataclass(frozen=True)
class ShowcaseSubject:
    """One explicit showcase identity key (API-Football XOR local)."""

    player_api_id: int | None = None
    local_player_id: int | None = None

    def __post_init__(self):
        if (self.player_api_id is None) == (self.local_player_id is None):
            raise ValueError("exactly one showcase subject id is required")
        subject_id = self.player_api_id if self.player_api_id is not None else self.local_player_id
        if isinstance(subject_id, bool) or not isinstance(subject_id, int) or subject_id <= 0:
            raise ValueError("showcase subject ids must be positive integers")

    @property
    def is_local(self) -> bool:
        return self.local_player_id is not None

    @property
    def subject_id(self) -> int:
        return self.local_player_id if self.local_player_id is not None else self.player_api_id


def _api_subject(player_api_id: int) -> ShowcaseSubject:
    return ShowcaseSubject(player_api_id=player_api_id)


def _local_subject(local_player_id: int) -> ShowcaseSubject:
    return ShowcaseSubject(local_player_id=local_player_id)


def _subject_filters(model, subject: ShowcaseSubject, *, api_field: str = "player_api_id") -> tuple:
    """SQL predicates that enforce both sides of the subject XOR."""
    api_column = getattr(model, api_field)
    local_column = model.local_player_id
    if subject.is_local:
        return api_column.is_(None), local_column == subject.local_player_id
    return api_column == subject.player_api_id, local_column.is_(None)


def _subject_values(subject: ShowcaseSubject, *, api_field: str = "player_api_id") -> dict:
    return {
        api_field: subject.player_api_id,
        "local_player_id": subject.local_player_id,
    }


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


def _has_approved_subject_claim(subject: ShowcaseSubject, user_id: int) -> bool:
    return (
        PlayerProfileClaim.query.filter(
            *_subject_filters(PlayerProfileClaim, subject),
            PlayerProfileClaim.user_account_id == user_id,
            PlayerProfileClaim.status == "approved",
        ).first()
        is not None
    )


def _has_approved_claim(player_api_id: int, user_id: int) -> bool:
    """Compatibility wrapper for the existing API-player routes."""
    return _has_approved_subject_claim(_api_subject(player_api_id), user_id)


def _has_visible_local_claim(local_player_id: int, user_id: int) -> bool:
    return (
        PlayerProfileClaim.query.filter(
            *_subject_filters(PlayerProfileClaim, _local_subject(local_player_id)),
            PlayerProfileClaim.user_account_id == user_id,
            PlayerProfileClaim.status.in_(("pending", "approved")),
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


def _approved_subject_claim_or_403(subject: ShowcaseSubject):
    """Resolve the caller and require an approved claim for one subject.

    Returns ``(user, None)`` when the caller owns an approved claim, otherwise
    ``(None, (response, status))`` for the route to return directly.
    """
    user = _current_user_account()
    if user is None:
        return None, (jsonify({"error": "auth context missing email"}), 401)
    if subject.is_local:
        player = db.session.get(LocalPlayer, subject.local_player_id)
        if player is None or player.status in ("merged", "rejected"):
            return None, (jsonify({"error": "local player not found"}), 404)
    if not _has_approved_subject_claim(subject, user.id):
        return None, (jsonify({"error": "You do not have an approved claim for this player"}), 403)
    return user, None


def _approved_claim_or_403(player_api_id: int):
    """Compatibility wrapper for the existing API-player owner gate."""
    return _approved_subject_claim_or_403(_api_subject(player_api_id))


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


def _normalize_local_player_name(value: str) -> str:
    """Canonical key for local-player duplicate detection."""
    return LocalPlayer.normalize_name(value)


def _escape_like_literal(value: str) -> str:
    """Escape SQL LIKE metacharacters so a search term stays literal."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


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


def _proof_url_contains_verification_code(proof_url: str, verification_code: str | None) -> bool:
    """Reject search/result URLs that can merely reflect the claimant's code."""
    if not isinstance(proof_url, str) or not isinstance(verification_code, str):
        return False
    code = verification_code.strip().casefold()
    if not code:
        return False

    decoded = proof_url
    # Decode a small, fixed number of layers so percent-encoding cannot hide a
    # reflected code without allowing attacker input to drive unbounded work.
    for _ in range(3):
        next_decoded = unquote(decoded)
        if next_decoded == decoded:
            break
        decoded = next_decoded
    return code in decoded.casefold()


def _run_claim_proof_check(claim: PlayerProfileClaim | ClubOfficialClaim, proof_url: str) -> None:
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
    payload = {
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
    if link.local_player_id is not None:
        payload["local_player_id"] = link.local_player_id
    return payload


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
    if media.local_player_id is not None:
        payload["local_player_id"] = media.local_player_id
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


def _profile_claim_dict(claim: PlayerProfileClaim, *, include_null_local_id: bool = False) -> dict:
    """Serialize a profile claim without changing legacy API-player responses."""
    payload = claim.to_dict()
    if include_null_local_id or claim.local_player_id is not None:
        payload["local_player_id"] = claim.local_player_id
    return payload


def _local_player_public_dict(player: LocalPlayer) -> dict:
    return {
        "id": player.id,
        "display_name": player.display_name,
        "birth_year": player.birth_year,
        "position": player.position,
        "country": player.country,
        "status": player.status,
        "api_player_id": player.api_player_id,
    }


def _local_player_owner_dict(player: LocalPlayer) -> dict:
    """Identity fields visible to the claimant, including precise locality."""
    payload = _local_player_public_dict(player)
    payload["city"] = player.city
    return payload


def _local_player_admin_dict(player: LocalPlayer) -> dict:
    payload = _local_player_owner_dict(player)
    payload.update(
        {
            "normalized_name": player.normalized_name,
            "merged_into_local_player_id": player.merged_into_local_player_id,
            "provenance": player.provenance,
            "created_by_user_id": player.created_by_user_id,
            "reviewed_by": player.reviewed_by,
            "reviewed_at": player.reviewed_at.isoformat() if player.reviewed_at else None,
            "review_note": player.review_note,
            "created_at": player.created_at.isoformat() if player.created_at else None,
            "updated_at": player.updated_at.isoformat() if player.updated_at else None,
        }
    )
    return payload


def _local_player_mini_dict(player: LocalPlayer) -> dict:
    return {
        "id": player.id,
        "display_name": player.display_name,
        "status": player.status,
    }


def _resolved_local_player(local_player_id: int) -> tuple[LocalPlayer | None, int | None]:
    """Resolve one merge hop, returning ``(target-or-row, target_id)``."""
    player = db.session.get(LocalPlayer, local_player_id)
    if player and player.status == "merged" and player.merged_into_local_player_id:
        target = db.session.get(LocalPlayer, player.merged_into_local_player_id)
        if target is not None:
            return target, target.id
    return player, None


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


def _latest_team_name(team_api_id: int | None) -> str | None:
    """Resolve an API-Football team's latest-season display name."""
    if team_api_id is None:
        return None
    team = Team.query.filter_by(team_id=team_api_id).order_by(Team.season.desc(), Team.id.desc()).first()
    return team.name if team else None


def _resolved_local_club(local_club_id: int | None) -> LocalClub | None:
    """Resolve one local-club merge hop for display and matching."""
    club = db.session.get(LocalClub, local_club_id) if local_club_id else None
    if club and club.status == "merged" and club.merged_into_local_club_id:
        return db.session.get(LocalClub, club.merged_into_local_club_id) or club
    return club


def _club_reference_name(*, team_api_id: int | None, local_club_id: int | None) -> str | None:
    if team_api_id is not None:
        return _latest_team_name(team_api_id)
    club = _resolved_local_club(local_club_id)
    return club.name if club else None


def _club_claim_dict(claim: ClubOfficialClaim, *, include_verification_code: bool = True) -> dict:
    """Serialize an official claim while making code exposure explicit."""
    payload = claim.to_dict()
    if not include_verification_code:
        payload.pop("verification_code", None)
    payload["club_name"] = _club_reference_name(
        team_api_id=claim.team_api_id,
        local_club_id=claim.local_club_id,
    )
    return payload


def _player_claim_for_official_dict(claim: PlayerProfileClaim) -> dict:
    """Cross-user claim shape: verification result is visible, secret code is not."""
    payload = _profile_claim_dict(claim)
    payload.pop("verification_code", None)
    payload["player_name"] = _resolve_claim_player_name(claim)
    return payload


def _local_club_match_ids(local_club_id: int | None) -> set[int]:
    """Ids equivalent to a local club under the single-hop merge rule."""
    if local_club_id is None:
        return set()
    original = db.session.get(LocalClub, local_club_id)
    canonical_id = local_club_id
    if original and original.status == "merged" and original.merged_into_local_club_id:
        canonical_id = original.merged_into_local_club_id

    ids = {local_club_id, canonical_id}
    merged_sources = (
        db.session.query(LocalClub.id)
        .filter(
            LocalClub.status == "merged",
            LocalClub.merged_into_local_club_id == canonical_id,
        )
        .all()
    )
    ids.update(row[0] for row in merged_sources)
    return ids


def _club_claim_matches_affiliation(claim: ClubOfficialClaim, affiliation: PlayerClubAffiliation) -> bool:
    """Whether an approved official claim covers an affiliation's club."""
    if claim.team_api_id is not None:
        return affiliation.team_api_id == claim.team_api_id
    if claim.local_club_id is None or affiliation.local_club_id is None:
        return False
    claimed_club = _resolved_local_club(claim.local_club_id)
    affiliated_club = _resolved_local_club(affiliation.local_club_id)
    if (
        claimed_club is None
        or claimed_club.status != "verified"
        or affiliated_club is None
        or affiliated_club.status != "verified"
    ):
        return False
    return affiliation.local_club_id in _local_club_match_ids(claim.local_club_id)


def _approved_official_claims(user_id: int) -> list[ClubOfficialClaim]:
    return (
        ClubOfficialClaim.query.filter_by(user_account_id=user_id, status="approved")
        .order_by(ClubOfficialClaim.created_at.asc(), ClubOfficialClaim.id.asc())
        .all()
    )


def _matching_approved_official_claim(
    user_id: int,
    affiliation: PlayerClubAffiliation,
) -> ClubOfficialClaim | None:
    for claim in _approved_official_claims(user_id):
        if _club_claim_matches_affiliation(claim, affiliation):
            return claim
    return None


def _affiliations_for_club_claim(
    claim: ClubOfficialClaim,
    *,
    statuses: set[str] | None = None,
    exclude_rejected: bool = False,
) -> list[PlayerClubAffiliation]:
    query = PlayerClubAffiliation.query
    if claim.team_api_id is not None:
        query = query.filter(PlayerClubAffiliation.team_api_id == claim.team_api_id)
    elif claim.local_club_id is not None:
        match_ids = sorted(_local_club_match_ids(claim.local_club_id))
        query = query.filter(PlayerClubAffiliation.local_club_id.in_(match_ids))
    else:
        return []
    if statuses is not None:
        query = query.filter(PlayerClubAffiliation.status.in_(statuses))
    elif exclude_rejected:
        query = query.filter(PlayerClubAffiliation.status != "rejected")
    return query.order_by(PlayerClubAffiliation.created_at.asc(), PlayerClubAffiliation.id.asc()).all()


def _affiliation_club_name(
    affiliation: PlayerClubAffiliation,
    *,
    include_unverified_local_name: bool = False,
) -> str | None:
    """Resolve the display club, following one local-club merge hop."""
    if affiliation.team_api_id is not None:
        return _latest_team_name(affiliation.team_api_id)
    club = _resolved_local_club(affiliation.local_club_id)
    if club is None or (not include_unverified_local_name and club.status != "verified"):
        return None
    return club.name


def _affiliation_dict(
    affiliation: PlayerClubAffiliation,
    *,
    include_review_note: bool = False,
    include_unverified_local_name: bool = False,
) -> dict:
    """Stable affiliation contract shared by showcase and admin responses."""
    payload = {
        "id": affiliation.id,
        "player_api_id": affiliation.player_api_id,
        "team_api_id": affiliation.team_api_id,
        "local_club_id": affiliation.local_club_id,
        "club_name": _affiliation_club_name(
            affiliation,
            include_unverified_local_name=include_unverified_local_name,
        ),
        "season": affiliation.season,
        "status": affiliation.status,
        "created_at": affiliation.created_at.isoformat() if affiliation.created_at else None,
    }
    if affiliation.local_player_id is not None:
        payload["local_player_id"] = affiliation.local_player_id
    if include_review_note:
        payload["review_note"] = affiliation.review_note
    return payload


def _subject_affiliations(subject: ShowcaseSubject, *, include_private: bool) -> list[dict]:
    query = PlayerClubAffiliation.query.filter(*_subject_filters(PlayerClubAffiliation, subject))
    if not include_private:
        query = query.filter(PlayerClubAffiliation.status.in_(PUBLIC_AFFILIATION_STATUSES))
    rows = query.order_by(PlayerClubAffiliation.created_at.asc(), PlayerClubAffiliation.id.asc()).all()
    return [
        _affiliation_dict(
            row,
            include_review_note=include_private,
            include_unverified_local_name=include_private,
        )
        for row in rows
    ]


def _player_affiliations(player_api_id: int, *, include_private: bool) -> list[dict]:
    """Compatibility wrapper for API-player showcase responses."""
    return _subject_affiliations(_api_subject(player_api_id), include_private=include_private)


def _lock_subject_cap(subject: ShowcaseSubject, *, api_namespace: int, local_namespace: int) -> None:
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :subject_id)"),
            {
                "namespace": local_namespace if subject.is_local else api_namespace,
                "subject_id": subject.subject_id,
            },
        )


def _lock_photo_cap_subject(subject: ShowcaseSubject) -> None:
    """Serialize photo-row creation per player on PostgreSQL.

    The eight-row cap is a conditional count and cannot be expressed as a
    portable table constraint. A transaction-scoped advisory lock closes the
    count-then-insert race in production; SQLite tests remain a no-op.
    """
    _lock_subject_cap(subject, api_namespace=5_455_001, local_namespace=5_455_011)


def _lock_affiliation_cap_subject(subject: ShowcaseSubject) -> None:
    """Serialize affiliation cap/duplicate checks per player on PostgreSQL."""
    _lock_subject_cap(subject, api_namespace=5_455_002, local_namespace=5_455_012)


def _lock_photo_cap(player_api_id: int) -> None:
    """Compatibility wrapper for the existing API-player cap lock."""
    _lock_photo_cap_subject(_api_subject(player_api_id))


def _lock_affiliation_cap(player_api_id: int) -> None:
    """Compatibility wrapper for the existing API-player cap lock."""
    _lock_affiliation_cap_subject(_api_subject(player_api_id))


def _lock_club_claims(user_id: int) -> None:
    """Serialize active-club duplicate checks per claimant on PostgreSQL."""
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :user_id)"),
            {"namespace": 5_455_003, "user_id": user_id},
        )


def _lock_pending_quota(user_id: int, *, namespace: int) -> None:
    """Serialize each per-account pending count in production."""
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(
            text("SELECT pg_advisory_xact_lock(:namespace, :user_id)"),
            {"namespace": namespace, "user_id": user_id},
        )


def _cleanup_failed_publication(public_url: str | None, media_id: int) -> None:
    """Compensate a published blob when moderation cannot commit approval."""
    if not public_url:
        return
    try:
        showcase_media_storage.delete_published(public_url)
    except Exception as exc:
        logger.error("Failed to compensate public blob for media %s: %s", media_id, exc)


def _cleanup_failed_pending_upload(blob_path: str, media_id: int) -> None:
    """Best-effort terminal cleanup for an upload that failed completion."""
    try:
        showcase_media_storage.delete_pending(blob_path)
    except Exception as exc:
        logger.warning("Failed to delete invalid pending blob for media %s: %s", media_id, exc)


def _subject_photos(subject: ShowcaseSubject, *, include_unapproved: bool) -> list[dict]:
    query = PlayerShowcaseMedia.query.filter(
        *_subject_filters(PlayerShowcaseMedia, subject),
        PlayerShowcaseMedia.kind == "photo",
    )
    if not include_unapproved:
        query = query.filter(PlayerShowcaseMedia.status == "approved")
    rows = query.order_by(
        PlayerShowcaseMedia.is_primary.desc(),
        PlayerShowcaseMedia.sort_order.asc(),
        PlayerShowcaseMedia.created_at.asc(),
        PlayerShowcaseMedia.id.asc(),
    ).all()
    return [_media_dict(row, include_preview=include_unapproved) for row in rows]


def _player_photos(player_api_id: int, *, include_unapproved: bool) -> list[dict]:
    """Compatibility wrapper for API-player photo queries."""
    return _subject_photos(_api_subject(player_api_id), include_unapproved=include_unapproved)


def _subject_highlight_reel(subject: ShowcaseSubject, *, include_pending: bool) -> list[dict]:
    """The player's highlight reel: approved (and, for owners, pending) highlight
    ``PlayerLink`` rows ordered by sort_order, then newsletter YouTube links
    appended as synthetic read-only entries (dedup by URL; not reorderable)."""
    statuses = ("approved", "pending") if include_pending else ("approved",)
    order_col = func.coalesce(PlayerLink.sort_order, 0)
    links = (
        PlayerLink.query.filter(
            *_subject_filters(PlayerLink, subject, api_field="player_id"),
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
    yt_rows = []
    if not subject.is_local:
        yt_rows = (
            NewsletterPlayerYoutubeLink.query.filter_by(player_id=subject.player_api_id)
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


def _highlight_reel(player_api_id: int, *, include_pending: bool) -> list[dict]:
    """Compatibility wrapper for the existing API-player reel."""
    return _subject_highlight_reel(_api_subject(player_api_id), include_pending=include_pending)


def _resolve_player_name(player_api_id: int):
    """Best-effort display name from the tracking universe (may be None)."""
    tracked = TrackedPlayer.query.filter_by(player_api_id=player_api_id).order_by(TrackedPlayer.id).first()
    return tracked.player_name if tracked and tracked.player_name else None


def _resolve_claim_player_name(claim: PlayerProfileClaim) -> str | None:
    if claim.local_player_id is not None:
        local_player = db.session.get(LocalPlayer, claim.local_player_id)
        return local_player.display_name if local_player else None
    return _resolve_player_name(claim.player_api_id)


def _claim_subject(claim: PlayerProfileClaim) -> ShowcaseSubject:
    return ShowcaseSubject(
        player_api_id=claim.player_api_id,
        local_player_id=claim.local_player_id,
    )


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
@limiter.limit("30 per minute", key_func=_user_rate_limit_key)
def search_clubs():
    """Search API-synced teams and the isolated self-reported club layer."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        raw_q = request.args.get("q")
        q = _sanitize_text(raw_q).strip() if isinstance(raw_q, str) else ""
        q = re.sub(r"\s+", " ", q)
        if len(q) < 2:
            return jsonify({"error": "q must be at least 2 characters"}), 400
        like_pattern = f"%{_escape_like_literal(q)}%"

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
            .filter(Team.name.ilike(like_pattern, escape="\\"))
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
                LocalClub.name.ilike(like_pattern, escape="\\"),
                or_(
                    LocalClub.status == "verified",
                    (LocalClub.status == "pending") & (LocalClub.created_by_user_id == user.id),
                ),
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
        _lock_pending_quota(user.id, namespace=5_455_004)
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
            body = {"error": "A local club with this name and country already exists"}
            if existing.status == "verified" or existing.created_by_user_id == user.id:
                body["existing"] = {
                    "id": existing.id,
                    "name": existing.name,
                    "country": existing.country,
                    "status": existing.status,
                }
            return jsonify(body), 409

        pending_count = LocalClub.query.filter_by(
            created_by_user_id=user.id,
            status="pending",
        ).count()
        if pending_count >= MAX_PENDING_LOCAL_CLUBS_PER_USER:
            return (
                jsonify({"error": (f"pending local club limit reached ({MAX_PENDING_LOCAL_CLUBS_PER_USER})")}),
                429,
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


@showcase_bp.route("/local-players", methods=["POST"])
@require_user_auth
@limiter.limit("5 per hour", key_func=_user_rate_limit_key)
def create_local_player():
    """Create a pending showcase-only identity and auto-claim it for its creator."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401

        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error

        raw_name = payload.get("display_name")
        if not isinstance(raw_name, str):
            return jsonify({"error": "display_name is required and must be a string"}), 400
        display_name = _sanitize_text(raw_name).strip()
        if not 2 <= len(display_name) <= MAX_LOCAL_PLAYER_NAME_LENGTH:
            return jsonify({"error": "display_name must be between 2 and 200 characters"}), 400

        birth_year = payload.get("birth_year")
        if birth_year is not None:
            if isinstance(birth_year, bool) or not isinstance(birth_year, int):
                return jsonify({"error": "birth_year must be an integer between 1950 and 2020"}), 400
            if not MIN_LOCAL_PLAYER_BIRTH_YEAR <= birth_year <= MAX_LOCAL_PLAYER_BIRTH_YEAR:
                return jsonify({"error": "birth_year must be between 1950 and 2020"}), 400

        position = _clean_optional_text(payload.get("position"), MAX_LOCAL_PLAYER_POSITION_LENGTH)
        country = _clean_optional_text(payload.get("country"), MAX_LOCAL_PLAYER_COUNTRY_LENGTH)
        city = _clean_optional_text(payload.get("city"), MAX_LOCAL_PLAYER_CITY_LENGTH)

        raw_relationship = payload.get("relationship_type", "player")
        relationship_type = raw_relationship.strip().lower() if isinstance(raw_relationship, str) else ""
        if relationship_type not in LOCAL_PLAYER_RELATIONSHIP_TYPES:
            return (
                jsonify({"error": f"relationship_type must be one of {sorted(LOCAL_PLAYER_RELATIONSHIP_TYPES)}"}),
                400,
            )

        _lock_pending_quota(user.id, namespace=5_455_005)
        duplicate_query = LocalPlayer.query.filter(
            LocalPlayer.normalized_name == _normalize_local_player_name(display_name),
            LocalPlayer.status.notin_(("rejected", "merged")),
        )
        if birth_year is None:
            duplicate_query = duplicate_query.filter(LocalPlayer.birth_year.is_(None))
        else:
            duplicate_query = duplicate_query.filter(LocalPlayer.birth_year == birth_year)
        existing = duplicate_query.order_by(LocalPlayer.id.asc()).first()
        if existing is not None:
            body = {"error": "A local player with this name and birth year already exists"}
            if existing.status == "approved" or existing.created_by_user_id == user.id:
                body["existing"] = {
                    "id": existing.id,
                    "display_name": existing.display_name,
                    "status": existing.status,
                }
            return jsonify(body), 409

        pending_count = LocalPlayer.query.filter_by(
            created_by_user_id=user.id,
            status="pending",
        ).count()
        if pending_count >= MAX_PENDING_LOCAL_PLAYERS_PER_USER:
            return (
                jsonify({"error": (f"pending local player limit reached ({MAX_PENDING_LOCAL_PLAYERS_PER_USER})")}),
                429,
            )

        player = LocalPlayer(
            display_name=display_name,
            birth_year=birth_year,
            position=position,
            country=country,
            city=city,
            status="pending",
            provenance="user",
            created_by_user_id=user.id,
        )
        db.session.add(player)
        db.session.flush()
        claim = PlayerProfileClaim(
            player_api_id=None,
            local_player_id=player.id,
            user_account_id=user.id,
            relationship_type=relationship_type,
            status="pending",
            verification_code=_mint_verification_code(),
            verification_status="unverified",
        )
        db.session.add(claim)
        db.session.commit()
        return jsonify({"player": _local_player_owner_dict(player), "claim": _profile_claim_dict(claim)}), 201
    except Exception as e:
        db.session.rollback()
        logger.error("Error in create_local_player: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to create local player")), 500


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------


def _subject_showcase_payload(subject: ShowcaseSubject, *, auth_context=None) -> dict:
    """Compose the shared showcase contract for an explicit subject."""
    if auth_context is None:
        auth_context = _optional_authenticated_context()
    authenticated = auth_context is not None
    auth_user = auth_context["user"] if auth_context else None
    is_owner = bool(auth_user and _has_approved_subject_claim(subject, auth_user.id))
    profile_row = PlayerShowcaseProfile.query.filter(*_subject_filters(PlayerShowcaseProfile, subject)).first()
    if profile_row and profile_row.status == "approved":
        profile = profile_row.public_dict(include_agent_contact=authenticated)
    elif profile_row and is_owner and profile_row.status == "pending":
        profile = profile_row.owner_dict()
    else:
        profile = None

    claimed = (
        PlayerProfileClaim.query.filter(
            *_subject_filters(PlayerProfileClaim, subject),
            PlayerProfileClaim.status == "approved",
        ).first()
        is not None
    )
    payload = {
        "profile": profile,
        "reel": _subject_highlight_reel(subject, include_pending=is_owner),
        "photos": _subject_photos(subject, include_unapproved=is_owner),
        "affiliations": _subject_affiliations(subject, include_private=is_owner),
        "verified_footage": [] if subject.is_local else _verified_footage(subject.player_api_id),
        "claim_status": "claimed" if claimed else "unclaimed",
    }
    if subject.is_local:
        return {"local_player_id": subject.local_player_id, **payload}
    return {"player_api_id": subject.player_api_id, **payload}


def _local_player_visible_to_context(player: LocalPlayer, auth_context) -> bool:
    if player.status == "approved":
        return True
    user = auth_context["user"] if auth_context else None
    return bool(user and _has_visible_local_claim(player.id, user.id))


@showcase_bp.route("/local-players/<int:lp_id>", methods=["GET"])
def get_local_player(lp_id: int):
    """Public local-player identity, with claimant-only pending visibility."""
    try:
        player, merged_into = _resolved_local_player(lp_id)
        if player is None:
            return jsonify({"error": "local player not found"}), 404
        auth_context = _optional_authenticated_context()
        if not _local_player_visible_to_context(player, auth_context):
            return jsonify({"error": "local player not found"}), 404
        auth_user = auth_context["user"] if auth_context else None
        is_owner = bool(auth_user and _has_visible_local_claim(player.id, auth_user.id))
        player_payload = _local_player_owner_dict(player) if is_owner else _local_player_public_dict(player)
        payload = {"player": player_payload}
        if merged_into is not None:
            payload["merged_into"] = merged_into
        return jsonify(payload)
    except Exception as e:
        logger.error("Error in get_local_player: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load local player")), 500


@showcase_bp.route("/local-players/<int:lp_id>/showcase", methods=["GET"])
def get_local_player_showcase(lp_id: int):
    """Showcase-only local profile; local subjects never have Film Room evidence."""
    try:
        player, _ = _resolved_local_player(lp_id)
        if player is None:
            return jsonify({"error": "local player not found"}), 404
        auth_context = _optional_authenticated_context()
        if not _local_player_visible_to_context(player, auth_context):
            return jsonify({"error": "local player not found"}), 404
        return jsonify(_subject_showcase_payload(_local_subject(player.id), auth_context=auth_context))
    except Exception as e:
        logger.error("Error in get_local_player_showcase: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load showcase")), 500


@showcase_bp.route("/players/<int:player_api_id>/showcase", methods=["GET"])
def get_player_showcase(player_api_id: int):
    """Showcase payload: approved profile + reel + verified footage + claim status.

    Optionally authenticated: an approved owner (valid Bearer) additionally sees
    their own pending highlight items and a pending profile draft (each carrying
    a ``status`` for the frontend's "pending review" badge). Anonymous, non-owner,
    or bad-token callers get the approved-only public view — never a 401.
    """
    try:
        return jsonify(_subject_showcase_payload(_api_subject(player_api_id)))
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
            payload = _profile_claim_dict(claim, include_null_local_id=True)
            payload["player_name"] = _resolve_claim_player_name(claim)
            if claim.local_player_id is not None:
                local_player = db.session.get(LocalPlayer, claim.local_player_id)
                payload["local_player"] = _local_player_mini_dict(local_player) if local_player else None
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
        if _proof_url_contains_verification_code(proof_url, claim.verification_code):
            return _proof_url_error()
        _run_claim_proof_check(claim, proof_url)
        db.session.commit()
        return jsonify({"claim": _profile_claim_dict(claim)})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in verify_my_claim: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to verify claim proof")), 500


# ---------------------------------------------------------------------------
# User-authed — club-official claims and My Club trust actions
# ---------------------------------------------------------------------------


@showcase_bp.route("/clubs/claim", methods=["POST"])
@require_user_auth
@limiter.limit("5 per hour", key_func=_user_rate_limit_key)
def submit_club_official_claim():
    """Submit a pending claim to represent one API team or local club."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401

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

        raw_role_title = payload.get("role_title")
        if not isinstance(raw_role_title, str):
            return jsonify({"error": "role_title is required and must be a string"}), 400
        role_title = _sanitize_text(raw_role_title).strip()
        if not 2 <= len(role_title) <= MAX_CLUB_ROLE_TITLE_LENGTH:
            return jsonify({"error": "role_title must be between 2 and 100 characters"}), 400

        raw_message = payload.get("message")
        if raw_message is not None and not isinstance(raw_message, str):
            return jsonify({"error": "message must be a string of at most 1000 characters"}), 400
        message = _sanitize_text(raw_message).strip() if isinstance(raw_message, str) else None
        message = message or None
        if message is not None and len(message) > MAX_MESSAGE_LENGTH:
            return jsonify({"error": "message must be a string of at most 1000 characters"}), 400

        _lock_club_claims(user.id)
        duplicate_query = ClubOfficialClaim.query.filter(
            ClubOfficialClaim.user_account_id == user.id,
            ClubOfficialClaim.status.in_(("pending", "approved")),
        )
        if has_local_club:
            duplicate_query = duplicate_query.filter(
                ClubOfficialClaim.local_club_id.in_(sorted(_local_club_match_ids(local_club_id)))
            )
        else:
            duplicate_query = duplicate_query.filter(ClubOfficialClaim.team_api_id == team_api_id)
        if duplicate_query.first() is not None:
            return jsonify({"error": "You already have an active claim for this club"}), 409

        pending_count = ClubOfficialClaim.query.filter_by(
            user_account_id=user.id,
            status="pending",
        ).count()
        if pending_count >= MAX_PENDING_CLUB_CLAIMS_PER_USER:
            return (
                jsonify({"error": (f"pending club-official claim limit reached ({MAX_PENDING_CLUB_CLAIMS_PER_USER})")}),
                429,
            )

        claim = ClubOfficialClaim(
            user_account_id=user.id,
            team_api_id=team_api_id if has_api_team else None,
            local_club_id=local_club_id if has_local_club else None,
            role_title=role_title,
            message=message,
            status="pending",
            verification_code=_mint_verification_code(),
            verification_status="unverified",
        )
        db.session.add(claim)
        db.session.commit()
        return jsonify({"claim": _club_claim_dict(claim)}), 201
    except Exception as e:
        db.session.rollback()
        logger.error("Error in submit_club_official_claim: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to submit club-official claim")), 500


@showcase_bp.route("/me/club-claims", methods=["GET"])
@require_user_auth
def my_club_claims():
    """The caller's club-official claims, including their own verification codes."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        claims = (
            ClubOfficialClaim.query.filter_by(user_account_id=user.id)
            .order_by(ClubOfficialClaim.created_at.desc(), ClubOfficialClaim.id.desc())
            .all()
        )
        if any(claim.verification_code is None for claim in claims):
            for claim in claims:
                if claim.verification_code is None:
                    claim.verification_code = _mint_verification_code()
                    claim.updated_at = datetime.now(UTC)
            db.session.commit()
        return jsonify({"claims": [_club_claim_dict(claim) for claim in claims]})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in my_club_claims: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load club-official claims")), 500


@showcase_bp.route("/me/club-claims/<int:claim_id>/verify", methods=["POST"])
@require_user_auth
@limiter.limit("6 per hour", key_func=_user_rate_limit_key)
def verify_my_club_claim(claim_id: int):
    """Run an advisory social-profile proof check for the caller's club claim."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        claim = ClubOfficialClaim.query.filter_by(id=claim_id, user_account_id=user.id).first()
        if claim is None:
            return jsonify({"error": "club-official claim not found"}), 404
        if claim.status != "pending":
            return jsonify({"error": f"cannot verify a {claim.status} club-official claim"}), 409

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
        if _proof_url_contains_verification_code(proof_url, claim.verification_code):
            return _proof_url_error()
        _run_claim_proof_check(claim, proof_url)
        claim.updated_at = datetime.now(UTC)
        db.session.commit()
        return jsonify({"claim": _club_claim_dict(claim, include_verification_code=False)})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in verify_my_club_claim: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to verify club-official claim proof")), 500


@showcase_bp.route("/me/club", methods=["GET"])
@require_user_auth
def my_club():
    """Approved club workspaces with affiliation review and vouch candidates."""
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401

        clubs = []
        for official_claim in _approved_official_claims(user.id):
            pending_affiliations = _affiliations_for_club_claim(
                official_claim,
                statuses={"pending", "self_reported"},
            )
            eligible_affiliations = _affiliations_for_club_claim(
                official_claim,
                exclude_rejected=True,
            )
            player_ids = {
                affiliation.player_api_id for affiliation in eligible_affiliations if affiliation.player_api_id
            }
            local_player_ids = {
                affiliation.local_player_id for affiliation in eligible_affiliations if affiliation.local_player_id
            }
            subject_predicates = []
            if player_ids:
                subject_predicates.append(
                    (PlayerProfileClaim.player_api_id.in_(sorted(player_ids)))
                    & PlayerProfileClaim.local_player_id.is_(None)
                )
            if local_player_ids:
                subject_predicates.append(
                    (PlayerProfileClaim.local_player_id.in_(sorted(local_player_ids)))
                    & PlayerProfileClaim.player_api_id.is_(None)
                )
            if subject_predicates:
                player_claims = (
                    PlayerProfileClaim.query.filter(
                        PlayerProfileClaim.status == "pending",
                        or_(*subject_predicates),
                    )
                    .order_by(PlayerProfileClaim.created_at.asc(), PlayerProfileClaim.id.asc())
                    .all()
                )
            else:
                player_claims = []

            club_name = _club_reference_name(
                team_api_id=official_claim.team_api_id,
                local_club_id=official_claim.local_club_id,
            )
            clubs.append(
                {
                    # This workspace is caller-owned but not one of the explicit
                    # claim-code surfaces; keep exposure narrowly allowlisted.
                    "claim": _club_claim_dict(official_claim, include_verification_code=False),
                    "club_name": club_name,
                    "pending_affiliations": [
                        _affiliation_dict(
                            affiliation,
                            include_review_note=True,
                            include_unverified_local_name=True,
                        )
                        for affiliation in pending_affiliations
                    ],
                    "vouchable_player_claims": [_player_claim_for_official_dict(claim) for claim in player_claims],
                }
            )
        return jsonify({"clubs": clubs})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in my_club: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load club workspace")), 500


def _official_affiliation_action(
    aff_id: int,
    *,
    target_status: str,
    parse_rejection_note: bool = False,
):
    """Apply a club-confirm/reject transition after the shared official gate."""
    user = _current_user_account()
    if user is None:
        return jsonify({"error": "auth context missing email"}), 401
    affiliation = PlayerClubAffiliation.query.filter_by(id=aff_id).with_for_update().first()
    if affiliation is None:
        return jsonify({"error": "affiliation not found"}), 404
    if _matching_approved_official_claim(user.id, affiliation) is None:
        return jsonify({"error": "affiliation not found"}), 404
    if affiliation.status not in ("pending", "self_reported"):
        action = "confirm" if target_status == "club_confirmed" else "reject"
        return jsonify({"error": f"cannot {action} a {affiliation.status} affiliation"}), 409

    note = None
    if parse_rejection_note:
        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        note = _clean_optional_text(payload.get("note"), MAX_REVIEW_NOTE_LENGTH)

    now = datetime.now(UTC)
    affiliation.status = target_status
    if target_status == "rejected":
        affiliation.review_note = note
    affiliation.reviewed_by = getattr(g, "user_email", None)
    affiliation.reviewed_at = now
    affiliation.updated_at = now
    db.session.commit()
    return jsonify(
        {
            "affiliation": _affiliation_dict(
                affiliation,
                include_review_note=True,
                include_unverified_local_name=True,
            )
        }
    )


@showcase_bp.route("/me/club/affiliations/<int:aff_id>/confirm", methods=["POST"])
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def confirm_club_affiliation(aff_id: int):
    """Confirm a pending/self-reported affiliation for the caller's club."""
    try:
        return _official_affiliation_action(aff_id, target_status="club_confirmed")
    except Exception as e:
        db.session.rollback()
        logger.error("Error in confirm_club_affiliation: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to confirm affiliation")), 500


@showcase_bp.route("/me/club/affiliations/<int:aff_id>/reject", methods=["POST"])
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def reject_club_affiliation(aff_id: int):
    """Reject a pending/self-reported affiliation for the caller's club."""
    try:
        return _official_affiliation_action(
            aff_id,
            target_status="rejected",
            parse_rejection_note=True,
        )
    except Exception as e:
        db.session.rollback()
        logger.error("Error in reject_club_affiliation: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to reject affiliation")), 500


@showcase_bp.route("/me/club/player-claims/<int:claim_id>/vouch", methods=["POST"])
@require_user_auth
@limiter.limit("10 per hour", key_func=_user_rate_limit_key)
def vouch_for_player_claim(claim_id: int):
    """Approve a player's IDENTITY via a verified club official.

    Vouching never approves profile content: every owner-authored bio, reel item,
    photo, and other showcase content remains pre-moderated.
    """
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        player_claim = PlayerProfileClaim.query.filter_by(id=claim_id).with_for_update().first()
        if player_claim is None:
            return jsonify({"error": "player claim not found"}), 404

        official_claims = _approved_official_claims(user.id)
        subject = _claim_subject(player_claim)
        affiliations = (
            PlayerClubAffiliation.query.filter(
                *_subject_filters(PlayerClubAffiliation, subject),
                PlayerClubAffiliation.status != "rejected",
            )
            .order_by(PlayerClubAffiliation.created_at.asc(), PlayerClubAffiliation.id.asc())
            .all()
        )
        matching_official = next(
            (
                official
                for official in official_claims
                if any(_club_claim_matches_affiliation(official, affiliation) for affiliation in affiliations)
            ),
            None,
        )
        if matching_official is None:
            return jsonify({"error": "player claim not found"}), 404
        if player_claim.status != "pending":
            return jsonify({"error": f"cannot vouch for a {player_claim.status} player claim"}), 409

        club_name = _club_reference_name(
            team_api_id=matching_official.team_api_id,
            local_club_id=matching_official.local_club_id,
        )
        descriptor = f"{club_name} " if club_name else ""
        now = datetime.now(UTC)
        player_claim.status = "approved"
        player_claim.verification_method = "vouch"
        player_claim.verification_note = f"Vouched by a verified {descriptor}official"[:VERIFICATION_NOTE_MAX_LENGTH]
        player_claim.reviewed_by = getattr(g, "user_email", None)
        player_claim.reviewed_at = now
        db.session.commit()
        return jsonify({"claim": _player_claim_for_official_dict(player_claim)})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in vouch_for_player_claim: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to vouch for player claim")), 500


# ---------------------------------------------------------------------------
# Owner-gated — affiliations, profile + reel curation
# ---------------------------------------------------------------------------


@showcase_bp.route("/players/<int:player_api_id>/showcase/affiliations", methods=["POST"])
@require_user_auth
@limiter.limit("10 per hour", key_func=_user_rate_limit_key)
def create_player_affiliation(player_api_id: int):
    """Submit one pre-moderated self-reported club affiliation."""
    return _create_subject_affiliation(_api_subject(player_api_id))


@showcase_bp.route("/local-players/<int:lp_id>/showcase/affiliations", methods=["POST"])
@require_user_auth
@limiter.limit("10 per hour", key_func=_user_rate_limit_key)
def create_local_player_affiliation(lp_id: int):
    return _create_subject_affiliation(_local_subject(lp_id))


def _create_subject_affiliation(subject: ShowcaseSubject):
    try:
        user, error = _approved_subject_claim_or_403(subject)
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

        _lock_affiliation_cap_subject(subject)
        duplicate_query = PlayerClubAffiliation.query.filter(
            *_subject_filters(PlayerClubAffiliation, subject),
            PlayerClubAffiliation.status != "rejected",
        )
        if has_local_club:
            duplicate_query = duplicate_query.filter(PlayerClubAffiliation.local_club_id == local_club_id)
        else:
            duplicate_query = duplicate_query.filter(PlayerClubAffiliation.team_api_id == team_api_id)
        if duplicate_query.first() is not None:
            return jsonify({"error": "This club affiliation has already been submitted"}), 409

        active_count = PlayerClubAffiliation.query.filter(
            *_subject_filters(PlayerClubAffiliation, subject),
            PlayerClubAffiliation.status != "rejected",
        ).count()
        if active_count >= MAX_AFFILIATIONS:
            return jsonify({"error": f"affiliation limit reached ({MAX_AFFILIATIONS})"}), 409

        affiliation = PlayerClubAffiliation(
            **_subject_values(subject),
            local_club_id=local_club_id if has_local_club else None,
            team_api_id=team_api_id if has_api_team else None,
            season=season,
            status="pending",
            created_by_user_id=user.id,
        )
        db.session.add(affiliation)
        db.session.commit()
        return (
            jsonify(
                {
                    "affiliation": _affiliation_dict(
                        affiliation,
                        include_review_note=True,
                        include_unverified_local_name=True,
                    )
                }
            ),
            201,
        )
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
    return _delete_subject_affiliation(_api_subject(player_api_id), aff_id)


@showcase_bp.route(
    "/local-players/<int:lp_id>/showcase/affiliations/<int:aff_id>",
    methods=["DELETE"],
)
@require_user_auth
def delete_local_player_affiliation(lp_id: int, aff_id: int):
    return _delete_subject_affiliation(_local_subject(lp_id), aff_id)


def _delete_subject_affiliation(subject: ShowcaseSubject, aff_id: int):
    try:
        _, error = _approved_subject_claim_or_403(subject)
        if error:
            return error
        affiliation = PlayerClubAffiliation.query.filter(
            PlayerClubAffiliation.id == aff_id,
            *_subject_filters(PlayerClubAffiliation, subject),
        ).first()
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
    return _upsert_subject_showcase_profile(_api_subject(player_api_id))


@showcase_bp.route("/local-players/<int:lp_id>/showcase/profile", methods=["PUT"])
@require_user_auth
@limiter.limit("20 per hour", key_func=_user_rate_limit_key)
def upsert_local_showcase_profile(lp_id: int):
    return _upsert_subject_showcase_profile(_local_subject(lp_id))


def _upsert_subject_showcase_profile(subject: ShowcaseSubject):
    try:
        user, error = _approved_subject_claim_or_403(subject)
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

        profile = PlayerShowcaseProfile.query.filter(*_subject_filters(PlayerShowcaseProfile, subject)).first()
        if profile is None:
            profile = PlayerShowcaseProfile(**_subject_values(subject))
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
    return _create_subject_showcase_photo(_api_subject(player_api_id))


@showcase_bp.route("/local-players/<int:lp_id>/showcase/photos", methods=["POST"])
@require_user_auth
@limiter.limit("20 per hour", key_func=_user_rate_limit_key)
def create_local_showcase_photo(lp_id: int):
    return _create_subject_showcase_photo(_local_subject(lp_id))


def _create_subject_showcase_photo(subject: ShowcaseSubject):
    try:
        user, error = _approved_subject_claim_or_403(subject)
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

        _lock_photo_cap_subject(subject)
        active_count = PlayerShowcaseMedia.query.filter(
            *_subject_filters(PlayerShowcaseMedia, subject),
            PlayerShowcaseMedia.kind == "photo",
            PlayerShowcaseMedia.status != "rejected",
        ).count()
        if active_count >= MAX_PHOTOS:
            return jsonify({"error": f"photo limit reached ({MAX_PHOTOS})"}), 409

        media = PlayerShowcaseMedia(
            **_subject_values(subject),
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
        path_prefix = f"local-players/{subject.local_player_id}" if subject.is_local else None
        upload = showcase_media_storage.mint_upload(
            subject.subject_id,
            media.id,
            content_type,
            path_prefix=path_prefix,
        )
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
    return _complete_subject_showcase_photo(_api_subject(player_api_id), media_id)


@showcase_bp.route(
    "/local-players/<int:lp_id>/showcase/photos/<int:media_id>/complete",
    methods=["POST"],
)
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def complete_local_showcase_photo(lp_id: int, media_id: int):
    return _complete_subject_showcase_photo(_local_subject(lp_id), media_id)


def _complete_subject_showcase_photo(subject: ShowcaseSubject, media_id: int):
    try:
        _, error = _approved_subject_claim_or_403(subject)
        if error:
            return error
        media = (
            PlayerShowcaseMedia.query.filter(
                PlayerShowcaseMedia.id == media_id,
                *_subject_filters(PlayerShowcaseMedia, subject),
                PlayerShowcaseMedia.kind == "photo",
            )
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
            _cleanup_failed_pending_upload(media.blob_path, media.id)
            return jsonify({"error": verification.get("error") or "pending upload could not be verified"}), 400
        actual_size = verification.get("size_bytes")
        if not isinstance(actual_size, int) or actual_size <= 0:
            _cleanup_failed_pending_upload(media.blob_path, media.id)
            return jsonify({"error": "pending upload is empty or unreadable"}), 400
        if actual_size > showcase_media_storage.max_photo_bytes():
            _cleanup_failed_pending_upload(media.blob_path, media.id)
            return jsonify({"error": "pending upload exceeds the photo size limit"}), 400

        try:
            raw = showcase_media_storage.read_pending_bytes(media.blob_path)
            validate_photo(raw)
        except Exception as exc:
            _cleanup_failed_pending_upload(media.blob_path, media.id)
            logger.warning("Photo validation failed during completion for media %s: %s", media.id, exc)
            return jsonify({"error": "Photo could not be validated"}), 422

        media.size_bytes = len(raw)
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
    return _reorder_subject_showcase_photos(_api_subject(player_api_id))


@showcase_bp.route("/local-players/<int:lp_id>/showcase/photos/order", methods=["PATCH"])
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def reorder_local_showcase_photos(lp_id: int):
    return _reorder_subject_showcase_photos(_local_subject(lp_id))


def _reorder_subject_showcase_photos(subject: ShowcaseSubject):
    try:
        _, error = _approved_subject_claim_or_403(subject)
        if error:
            return error
        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        ordered_ids = payload.get("ordered_ids")
        if not isinstance(ordered_ids, list):
            return jsonify({"error": "ordered_ids must be a list"}), 400

        approved = (
            PlayerShowcaseMedia.query.filter(
                *_subject_filters(PlayerShowcaseMedia, subject),
                PlayerShowcaseMedia.kind == "photo",
                PlayerShowcaseMedia.status == "approved",
            )
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
    return _set_primary_subject_showcase_photo(_api_subject(player_api_id), media_id)


@showcase_bp.route("/local-players/<int:lp_id>/showcase/photos/<int:media_id>", methods=["PATCH"])
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def set_primary_local_showcase_photo(lp_id: int, media_id: int):
    return _set_primary_subject_showcase_photo(_local_subject(lp_id), media_id)


def _set_primary_subject_showcase_photo(subject: ShowcaseSubject, media_id: int):
    try:
        _, error = _approved_subject_claim_or_403(subject)
        if error:
            return error
        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        if payload.get("is_primary") is not True:
            return jsonify({"error": "is_primary must be true"}), 400
        media = (
            PlayerShowcaseMedia.query.filter(
                PlayerShowcaseMedia.id == media_id,
                *_subject_filters(PlayerShowcaseMedia, subject),
                PlayerShowcaseMedia.kind == "photo",
            )
            .with_for_update()
            .first()
        )
        if media is None:
            return jsonify({"error": "photo not found"}), 404
        if media.status != "approved":
            return jsonify({"error": "only approved photos can be primary"}), 409

        PlayerShowcaseMedia.query.filter(
            *_subject_filters(PlayerShowcaseMedia, subject),
            PlayerShowcaseMedia.kind == "photo",
        ).update({PlayerShowcaseMedia.is_primary: False}, synchronize_session=False)
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
    return _delete_subject_showcase_photo(_api_subject(player_api_id), media_id)


@showcase_bp.route("/local-players/<int:lp_id>/showcase/photos/<int:media_id>", methods=["DELETE"])
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def delete_local_showcase_photo(lp_id: int, media_id: int):
    return _delete_subject_showcase_photo(_local_subject(lp_id), media_id)


def _delete_subject_showcase_photo(subject: ShowcaseSubject, media_id: int):
    try:
        _, error = _approved_subject_claim_or_403(subject)
        if error:
            return error
        media = (
            PlayerShowcaseMedia.query.filter(
                PlayerShowcaseMedia.id == media_id,
                *_subject_filters(PlayerShowcaseMedia, subject),
                PlayerShowcaseMedia.kind == "photo",
            )
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
    return _add_subject_reel_item(_api_subject(player_api_id))


@showcase_bp.route("/local-players/<int:lp_id>/showcase/reel", methods=["POST"])
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def add_local_reel_item(lp_id: int):
    return _add_subject_reel_item(_local_subject(lp_id))


def _add_subject_reel_item(subject: ShowcaseSubject):
    try:
        user, error = _approved_subject_claim_or_403(subject)
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
        count = PlayerLink.query.filter(
            *_subject_filters(PlayerLink, subject, api_field="player_id"),
            PlayerLink.link_type == "highlight",
        ).count()
        if count >= MAX_REEL_ITEMS:
            return jsonify({"error": f"reel limit reached ({MAX_REEL_ITEMS})"}), 400

        link = PlayerLink(
            **_subject_values(subject, api_field="player_id"),
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
    return _reorder_subject_reel(_api_subject(player_api_id))


@showcase_bp.route("/local-players/<int:lp_id>/showcase/reel/order", methods=["PATCH"])
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def reorder_local_reel(lp_id: int):
    return _reorder_subject_reel(_local_subject(lp_id))


def _reorder_subject_reel(subject: ShowcaseSubject):
    try:
        _, error = _approved_subject_claim_or_403(subject)
        if error:
            return error

        payload = request.get_json(silent=True) or {}
        ordered_ids = payload.get("ordered_ids")
        if not isinstance(ordered_ids, list):
            return jsonify({"error": "ordered_ids must be a list"}), 400

        own_links = {
            link.id: link
            for link in PlayerLink.query.filter(
                *_subject_filters(PlayerLink, subject, api_field="player_id"),
                PlayerLink.link_type == "highlight",
            ).all()
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
        return jsonify({"reel": _subject_highlight_reel(subject, include_pending=True)})
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
    return _delete_subject_reel_item(_api_subject(player_api_id), link_id)


@showcase_bp.route("/local-players/<int:lp_id>/showcase/reel/<int:link_id>", methods=["DELETE"])
@require_user_auth
@limiter.limit("30 per hour", key_func=_user_rate_limit_key)
def delete_local_reel_item(lp_id: int, link_id: int):
    return _delete_subject_reel_item(_local_subject(lp_id), link_id)


def _delete_subject_reel_item(subject: ShowcaseSubject, link_id: int):
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        link = PlayerLink.query.filter(
            PlayerLink.id == link_id,
            *_subject_filters(PlayerLink, subject, api_field="player_id"),
            PlayerLink.link_type == "highlight",
        ).first()
        if link is None:
            return jsonify({"error": "reel item not found"}), 404
        if link.user_id != user.id and not _has_approved_subject_claim(subject, user.id):
            return jsonify({"error": "You are not permitted to delete this reel item"}), 403
        db.session.delete(link)
        db.session.commit()
        return jsonify({"deleted": True})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in delete_reel_item: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to delete reel item")), 500


# ---------------------------------------------------------------------------
# Admin — club-official claims, local clubs + affiliation review
# ---------------------------------------------------------------------------


@showcase_bp.route("/admin/club-claims", methods=["GET"])
@require_api_key
def admin_list_club_claims():
    """List club-official claims, optionally filtered by lifecycle status."""
    try:
        status = (request.args.get("status") or "").strip().lower()
        query = ClubOfficialClaim.query
        if status:
            if status not in CLUB_OFFICIAL_CLAIM_STATUSES:
                return jsonify({"error": f"invalid status; one of {sorted(CLUB_OFFICIAL_CLAIM_STATUSES)}"}), 400
            query = query.filter(ClubOfficialClaim.status == status)
        claims = query.order_by(ClubOfficialClaim.created_at.desc(), ClubOfficialClaim.id.desc()).all()
        out = []
        for claim in claims:
            payload = _club_claim_dict(claim)
            payload["user_email"] = claim.user.email if claim.user else None
            out.append(payload)
        return jsonify({"claims": out})
    except Exception as e:
        logger.error("Error in admin_list_club_claims: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load club-official claims")), 500


@showcase_bp.route("/admin/club-claims/<int:claim_id>/review", methods=["POST"])
@require_api_key
def admin_review_club_claim(claim_id: int):
    """Approve/reject a pending official claim, or revoke an approved one."""
    try:
        claim = ClubOfficialClaim.query.filter_by(id=claim_id).with_for_update().first()
        if claim is None:
            return jsonify({"error": "club-official claim not found"}), 404

        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        raw_action = payload.get("action")
        action = raw_action.strip().lower() if isinstance(raw_action, str) else ""
        transitions = {
            "approve": ({"pending"}, "approved"),
            "reject": ({"pending"}, "rejected"),
            "revoke": ({"approved"}, "revoked"),
        }
        if action not in transitions:
            return jsonify({"error": "action must be approve, reject, or revoke"}), 400
        allowed_from, target = transitions[action]
        if claim.status not in allowed_from:
            return jsonify({"error": f"cannot {action} a {claim.status} club-official claim"}), 409

        now = datetime.now(UTC)
        claim.status = target
        claim.review_note = _clean_optional_text(payload.get("note"), MAX_REVIEW_NOTE_LENGTH)
        claim.reviewed_by = getattr(g, "user_email", None)
        claim.reviewed_at = now
        claim.updated_at = now
        db.session.commit()
        return jsonify({"claim": _club_claim_dict(claim, include_verification_code=False)})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in admin_review_club_claim: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to review club-official claim")), 500


@showcase_bp.route("/admin/club-claims/<int:claim_id>/recheck", methods=["POST"])
@require_api_key
def admin_recheck_club_claim(claim_id: int):
    """Re-run social proof against a club claim's stored proof URL."""
    try:
        claim = db.session.get(ClubOfficialClaim, claim_id)
        if claim is None:
            return jsonify({"error": "club-official claim not found"}), 404
        proof_url = (claim.verification_proof_url or "").strip()
        if not proof_url:
            return jsonify({"error": "club-official claim has no stored proof_url"}), 400
        valid, _ = social_proof.validate_proof_url(proof_url)
        if not valid or len(proof_url) > MAX_URL_LENGTH:
            return _proof_url_error()
        if claim.verification_code is None:
            claim.verification_code = _mint_verification_code()
        if _proof_url_contains_verification_code(proof_url, claim.verification_code):
            return _proof_url_error()

        _run_claim_proof_check(claim, proof_url)
        claim.updated_at = datetime.now(UTC)
        db.session.commit()
        return jsonify({"claim": _club_claim_dict(claim, include_verification_code=False)})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in admin_recheck_club_claim: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to re-check club-official claim proof")), 500


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


@showcase_bp.route("/admin/local-players", methods=["GET"])
@require_api_key
def admin_list_local_players():
    """List local identities with creator email and full moderation metadata."""
    try:
        status = (request.args.get("status") or "").strip().lower()
        query = LocalPlayer.query
        if status:
            if status not in LOCAL_PLAYER_STATUSES:
                return jsonify({"error": f"invalid status; one of {sorted(LOCAL_PLAYER_STATUSES)}"}), 400
            query = query.filter(LocalPlayer.status == status)
        players = query.order_by(LocalPlayer.created_at.desc(), LocalPlayer.id.desc()).all()
        out = []
        for player in players:
            payload = _local_player_admin_dict(player)
            creator = db.session.get(UserAccount, player.created_by_user_id) if player.created_by_user_id else None
            payload["created_by_email"] = creator.email if creator else None
            out.append(payload)
        return jsonify({"players": out})
    except Exception as e:
        logger.error("Error in admin_list_local_players: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load local players")), 500


@showcase_bp.route("/admin/local-players/<int:lp_id>/review", methods=["POST"])
@require_api_key
def admin_review_local_player(lp_id: int):
    """Approve or reject a pending local identity."""
    try:
        player = LocalPlayer.query.filter_by(id=lp_id).with_for_update().first()
        if player is None:
            return jsonify({"error": "local player not found"}), 404
        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        raw_action = payload.get("action")
        action = raw_action.strip().lower() if isinstance(raw_action, str) else ""
        if action not in ("approve", "reject"):
            return jsonify({"error": "action must be approve or reject"}), 400
        if player.status != "pending":
            return jsonify({"error": f"cannot {action} a {player.status} local player"}), 409

        now = datetime.now(UTC)
        player.status = "approved" if action == "approve" else "rejected"
        player.review_note = _clean_optional_text(payload.get("note"), MAX_REVIEW_NOTE_LENGTH)
        player.reviewed_by = getattr(g, "user_email", None)
        player.reviewed_at = now
        player.updated_at = now
        db.session.commit()
        return jsonify({"player": _local_player_admin_dict(player)})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in admin_review_local_player: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to review local player")), 500


_PROFILE_MERGE_FIELDS = (
    "bio",
    "positions",
    "preferred_foot",
    "height_cm",
    "contract_status",
    "contract_until",
    "availability",
    "agent_name",
    "agent_contact_email",
    "nationality_secondary",
    "languages",
)
_CLAIM_MERGE_STATUS_RANK = {
    "pending": 0,
    "approved": 1,
    "rejected": 2,
    "revoked": 3,
}
_CLAIM_EVIDENCE_STATUS_RANK = {
    "unverified": 0,
    "code_not_found": 1,
    "code_found": 2,
}


def _merge_local_player_claims(source_id: int, target_id: int) -> int:
    """Move claims while retaining one canonical row per claimant.

    A user may have claimed both duplicate identities before an admin discovers
    the duplicate. The target row survives. Explicit denial is precedence-safe
    (revoked/rejected cannot be resurrected), while the strongest independent
    social-proof evidence and club-vouch provenance are retained.
    """
    source_subject = _local_subject(source_id)
    target_subject = _local_subject(target_id)
    source_claims = (
        PlayerProfileClaim.query.filter(*_subject_filters(PlayerProfileClaim, source_subject)).with_for_update().all()
    )
    if not source_claims:
        return 0

    target_claims = (
        PlayerProfileClaim.query.filter(*_subject_filters(PlayerProfileClaim, target_subject)).with_for_update().all()
    )
    target_by_user = {claim.user_account_id: claim for claim in target_claims}
    for source_claim in source_claims:
        target_claim = target_by_user.get(source_claim.user_account_id)
        if target_claim is None:
            continue

        source_rank = _CLAIM_MERGE_STATUS_RANK.get(source_claim.status, -1)
        target_rank = _CLAIM_MERGE_STATUS_RANK.get(target_claim.status, -1)
        source_status_wins = source_rank > target_rank
        if source_rank == target_rank and source_claim.reviewed_at is not None:
            source_status_wins = target_claim.reviewed_at is None or source_claim.reviewed_at > target_claim.reviewed_at
        if source_status_wins:
            for field in (
                "relationship_type",
                "status",
                "message",
                "reviewed_by",
                "reviewed_at",
            ):
                setattr(target_claim, field, getattr(source_claim, field))
        elif target_claim.message is None and source_claim.message is not None:
            target_claim.message = source_claim.message

        source_evidence_rank = _CLAIM_EVIDENCE_STATUS_RANK.get(source_claim.verification_status, -1)
        target_evidence_rank = _CLAIM_EVIDENCE_STATUS_RANK.get(target_claim.verification_status, -1)
        source_evidence_wins = source_evidence_rank > target_evidence_rank
        if source_evidence_rank == target_evidence_rank:
            if source_claim.verification_proof_url and not target_claim.verification_proof_url:
                source_evidence_wins = True
            elif source_claim.verification_checked_at is not None:
                source_evidence_wins = (
                    target_claim.verification_checked_at is None
                    or source_claim.verification_checked_at > target_claim.verification_checked_at
                )
        if source_evidence_wins:
            for field in (
                "verification_code",
                "verification_proof_url",
                "verification_status",
                "verification_checked_at",
            ):
                setattr(target_claim, field, getattr(source_claim, field))

        if source_claim.verification_method == "vouch" or target_claim.verification_method == "vouch":
            target_claim.verification_method = "vouch"
        elif target_claim.verification_method is None:
            target_claim.verification_method = source_claim.verification_method

        target_note = target_claim.verification_note
        source_note = source_claim.verification_note
        if target_note and source_note and target_note != source_note:
            delimiter = " | "
            note_budget = VERIFICATION_NOTE_MAX_LENGTH - len(delimiter)
            target_budget = note_budget // 2
            target_claim.verification_note = (
                f"{target_note[:target_budget]}{delimiter}{source_note[: note_budget - target_budget]}"
            )
        else:
            target_claim.verification_note = (target_note or source_note or "")[:VERIFICATION_NOTE_MAX_LENGTH] or None

        if source_claim.created_at and (
            target_claim.created_at is None or source_claim.created_at < target_claim.created_at
        ):
            target_claim.created_at = source_claim.created_at
        db.session.delete(source_claim)

    # Flush duplicate removals before the bulk move meets the local claimant
    # uniqueness constraint.
    db.session.flush()
    PlayerProfileClaim.query.filter(*_subject_filters(PlayerProfileClaim, source_subject)).update(
        {PlayerProfileClaim.local_player_id: target_id},
        synchronize_session=False,
    )
    return len(source_claims)


def _merge_local_player_profiles(source_id: int, target_id: int, now: datetime) -> int:
    """Move the source profile, consolidating a target collision safely."""
    source_subject = _local_subject(source_id)
    target_subject = _local_subject(target_id)
    source_profile = (
        PlayerShowcaseProfile.query.filter(*_subject_filters(PlayerShowcaseProfile, source_subject))
        .with_for_update()
        .first()
    )
    if source_profile is None:
        return 0

    target_profile = (
        PlayerShowcaseProfile.query.filter(*_subject_filters(PlayerShowcaseProfile, target_subject))
        .with_for_update()
        .first()
    )
    if target_profile is None:
        return PlayerShowcaseProfile.query.filter(PlayerShowcaseProfile.id == source_profile.id).update(
            {
                PlayerShowcaseProfile.local_player_id: target_id,
                PlayerShowcaseProfile.updated_at: now,
            },
            synchronize_session=False,
        )

    changed = False
    for field in _PROFILE_MERGE_FIELDS:
        if getattr(target_profile, field) is None and getattr(source_profile, field) is not None:
            setattr(target_profile, field, getattr(source_profile, field))
            changed = True
    if changed:
        # Any source-authored material entering the canonical card must pass
        # through pre-moderation again before becoming public.
        target_profile.status = "pending"
        target_profile.reviewed_by = None
        target_profile.reviewed_at = None
        target_profile.updated_by_user_id = source_profile.updated_by_user_id
        target_profile.updated_at = now
    db.session.delete(source_profile)
    db.session.flush()
    return 1


@showcase_bp.route("/admin/local-players/<int:lp_id>/merge", methods=["POST"])
@require_api_key
def admin_merge_local_player(lp_id: int):
    """Merge a duplicate and repoint every explicit local showcase key."""
    try:
        source = LocalPlayer.query.filter_by(id=lp_id).with_for_update().first()
        if source is None:
            return jsonify({"error": "local player not found"}), 404
        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        target_id = payload.get("into_local_player_id")
        if isinstance(target_id, bool) or not isinstance(target_id, int) or target_id <= 0:
            return jsonify({"error": "into_local_player_id must be a positive integer"}), 400
        if target_id == source.id:
            return jsonify({"error": "A local player cannot be merged into itself"}), 400
        if source.status in ("merged", "rejected"):
            return jsonify({"error": f"cannot merge a {source.status} local player"}), 409

        target = LocalPlayer.query.filter_by(id=target_id).with_for_update().first()
        if target is None or target.status in ("merged", "rejected"):
            return jsonify({"error": "merge target must be an active local player"}), 400

        now = datetime.now(UTC)
        claims = _merge_local_player_claims(source.id, target.id)
        profiles = _merge_local_player_profiles(source.id, target.id, now)
        media = PlayerShowcaseMedia.query.filter(
            *_subject_filters(PlayerShowcaseMedia, _local_subject(source.id))
        ).update(
            {
                PlayerShowcaseMedia.local_player_id: target.id,
                PlayerShowcaseMedia.updated_at: now,
            },
            synchronize_session=False,
        )
        affiliations = PlayerClubAffiliation.query.filter(
            *_subject_filters(PlayerClubAffiliation, _local_subject(source.id))
        ).update(
            {
                PlayerClubAffiliation.local_player_id: target.id,
                PlayerClubAffiliation.updated_at: now,
            },
            synchronize_session=False,
        )
        links = PlayerLink.query.filter(
            *_subject_filters(PlayerLink, _local_subject(source.id), api_field="player_id")
        ).update({PlayerLink.local_player_id: target.id}, synchronize_session=False)

        source.status = "merged"
        source.merged_into_local_player_id = target.id
        source.reviewed_by = getattr(g, "user_email", None)
        source.reviewed_at = now
        source.updated_at = now
        db.session.commit()
        return jsonify(
            {
                "player": _local_player_admin_dict(source),
                "moved": {
                    "claims": claims,
                    "profiles": profiles,
                    "media": media,
                    "affiliations": affiliations,
                    "links": links,
                },
            }
        )
    except Exception as e:
        db.session.rollback()
        logger.error("Error in admin_merge_local_player: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to merge local player")), 500


@showcase_bp.route("/admin/local-players/<int:lp_id>/link-api", methods=["POST"])
@require_api_key
def admin_link_local_player_api(lp_id: int):
    """Store a future API-Football bridge without moving or syncing content."""
    try:
        player = db.session.get(LocalPlayer, lp_id)
        if player is None:
            return jsonify({"error": "local player not found"}), 404
        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        player_api_id = payload.get("player_api_id")
        if isinstance(player_api_id, bool) or not isinstance(player_api_id, int) or player_api_id <= 0:
            return jsonify({"error": "player_api_id must be a positive integer"}), 400
        player.api_player_id = player_api_id
        player.updated_at = datetime.now(UTC)
        db.session.commit()
        return jsonify({"player": _local_player_admin_dict(player)})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in admin_link_local_player_api: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to link local player")), 500


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
            {
                "affiliations": [
                    _affiliation_dict(
                        affiliation,
                        include_review_note=True,
                        include_unverified_local_name=True,
                    )
                    for affiliation in affiliations
                ]
            }
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
        return jsonify(
            {
                "affiliation": _affiliation_dict(
                    affiliation,
                    include_review_note=True,
                    include_unverified_local_name=True,
                )
            }
        )
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
            payload = _profile_claim_dict(claim)
            payload["player_name"] = _resolve_claim_player_name(claim)
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
        if _proof_url_contains_verification_code(proof_url, claim.verification_code):
            return _proof_url_error()

        _run_claim_proof_check(claim, proof_url)
        db.session.commit()
        return jsonify({"claim": _profile_claim_dict(claim)})
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
        return jsonify({"claim": _profile_claim_dict(claim)})
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
            if profile.local_player_id is not None:
                local_player = db.session.get(LocalPlayer, profile.local_player_id)
                payload["player_name"] = local_player.display_name if local_player else None
            else:
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
    return _admin_review_subject_profile(_api_subject(player_api_id))


@showcase_bp.route("/admin/showcase/local-profiles/<int:lp_id>/review", methods=["POST"])
@require_api_key
def admin_review_local_profile(lp_id: int):
    """Approve or hide a local-player profile edit."""
    return _admin_review_subject_profile(_local_subject(lp_id))


def _admin_review_subject_profile(subject: ShowcaseSubject):
    try:
        profile = PlayerShowcaseProfile.query.filter(*_subject_filters(PlayerShowcaseProfile, subject)).first()
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
