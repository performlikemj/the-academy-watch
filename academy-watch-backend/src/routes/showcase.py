"""Talent Showcase blueprint — player-owned profiles, highlight reels, and
club-verified footage evidence.

Product slice:
- Public: a player's showcase (curated YouTube reel + self-reported card +
  club-verified appearance evidence from Film Room).
- Users claim a player's profile; an admin approves; approved owners curate the
  reel and profile. Owner-submitted content is pre-moderated (many players are
  minors); only configured, low-risk edits by trusted adult owners retain an
  existing approval.

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
from datetime import UTC, date, datetime, timedelta
from functools import wraps
from urllib.parse import parse_qs, unquote, urlparse

from flask import Blueprint, abort, g, jsonify, request, send_file
from sqlalchemy import case, func, literal, or_, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from src.auth import (
    _ensure_user_account,
    _safe_error_payload,
    _user_serializer,
    require_api_key,
    require_user_auth,
)
from src.extensions import limiter
from src.models.club_invitation import (
    ClubInvitation,
    InvitationError,
    claim_matches,
    local_attestation,
    relationships_enabled,
    resolve_invitation,
    subject_claim,
)
from src.models.contact import ContactRequest
from src.models.follow import Follow, FollowList, FollowPlayerSnapshot, PlayerShadow, PlayerShadowStats
from src.models.funding import ClubRosterMember
from src.models.journey import PlayerJourney
from src.models.league import (
    CommunityTake,
    NewsletterCommentary,
    NewsletterPlayerYoutubeLink,
    Player,
    PlayerComment,
    PlayerFlag,
    PlayerLink,
    QuickTakeSubmission,
    Team,
    UserAccount,
    db,
)
from src.models.player_fan import PlayerFan
from src.models.player_match_entry import PlayerMatchEntry
from src.models.player_suppression import PlayerSuppression
from src.models.pulse import PlayerCardCache, PlayerPulse
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.showcase import (
    ClubOfficialClaim,
    LocalClub,
    LocalPlayer,
    PlayerClubAffiliation,
    PlayerProfileClaim,
    PlayerShowcaseMedia,
    PlayerShowcaseProfile,
    local_player_is_minor,
    without_minor_local_bridge,
)
from src.models.showcase_moderation import ShowcaseModerationEvent, record_moderation_event
from src.models.tracked_player import TrackedPlayer
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry
from src.services import season_rollup_service, showcase_media_storage, social_proof
from src.services.club_console_bridge import (
    ClubConsoleBridgeConflict,
    grant_console_for_official_claim,
    revoke_console_for_official_claim,
)
from src.services.club_registry import get_club_program
from src.services.contact import (
    CONTRACT_STATUSES as CLAIM_CONTRACT_STATUSES,
)
from src.services.contact import (
    add_audit_event,
    clean_plain_text,
    contact_rail_enabled,
    has_status_contradiction,
    require_contact_rail,
    utcnow,
)
from src.services.photo_processing import process_photo, validate_photo
from src.services.player_identity import retained_shadow_identity_exists
from src.services.player_shadow_service import mint_shadow
from src.services.player_subject import resolve_player_subject
from src.services.player_suppression import (
    hide_suppressed_player,
    is_local_player_suppressed,
    is_player_suppressed,
    neutral_player_not_found,
)
from src.services.public_player_subject import owned_public_adult_subjects
from src.services.reach_metrics import fan_counts, profile_view_counts
from src.services.user_blocks import blocked_user_ids
from src.utils.academy_window import age_from_birth_date
from src.utils.feature_flags import showcase_trust_min_account_age_days
from src.utils.sanitize import is_safe_https_url, sanitize_plain_text

logger = logging.getLogger(__name__)

showcase_bp = Blueprint("showcase", __name__)

# A handful of production rows predate D1 and occupy its reserved negative-id
# namespace without being referenced anywhere. Keep the warning useful instead
# of emitting it on every re-approval attempt or worker request.
_logged_orphan_legacy_player_ids: set[int] = set()


@showcase_bp.before_app_request
def _hide_interest_signal_path_when_contact_rail_disabled():
    """Hide OPTIONS and wrong-method probes as well as supported methods."""
    if request.path.rstrip("/") == "/api/showcase/mine/interest-signals" and not contact_rail_enabled():
        abort(404)


RELATIONSHIP_TYPES = {"player", "agent", "guardian", "club_official"}
CLAIM_STATUSES = {"pending", "approved", "rejected", "revoked"}
CLUB_OFFICIAL_CLAIM_STATUSES = {"pending", "approved", "rejected", "revoked"}
PROFILE_STATUSES = {"pending", "approved"}
MEDIA_STATUSES = {"pending_upload", "pending", "approved", "rejected"}
PREFERRED_FEET = {"left", "right", "both"}
PROFILE_CONTRACT_STATUSES = {"under_contract", "expiring", "free_agent"}
AVAILABILITY_STATUSES = {"open_to_moves", "not_looking", "trial_available"}
PHOTO_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
EMAIL_PATTERN = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

MAX_BIO_LENGTH = 2000
MAX_POSITIONS_LENGTH = 100
MAX_TITLE_LENGTH = 200
MAX_MESSAGE_LENGTH = 1000
MAX_CURRENT_CLUB_NAME_LENGTH = 180
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
MAX_LOCAL_PLAYER_CLUB_NAME_LENGTH = 200
MIN_LOCAL_PLAYER_BIRTH_YEAR = 1950
MAX_LOCAL_PLAYER_BIRTH_YEAR = 2020
LOCAL_SELF_CLAIM_ADULT_ERROR = "The platform is 18+ for self-managed profiles"
MAX_PENDING_LOCAL_PLAYERS_PER_USER = 10
MAX_PENDING_LOCAL_CLUBS_PER_USER = 10
MAX_PENDING_CLUB_CLAIMS_PER_USER = 5

# The only identity gate strong enough for public display (see models/video.py).
VERIFIED_IDENTITY = "human_confirmed"

_AUTO_APPROVAL_PROFILE_FIELDS = frozenset(
    {
        "availability",
        "bio",
        "height_cm",
        "languages",
        "positions",
        "preferred_foot",
    }
)
_PROFILE_EDIT_FIELD_LABELS = {
    "agent_contact_email": "agent_contact_email",
    "agent_name": "agent_name",
    "availability": "availability",
    "bio": "bio",
    "contract_status": "contract_status",
    "contract_until": "contract_until",
    "height_cm": "height_cm",
    "languages": "languages",
    "nationality_secondary": "nationality_secondary",
    "pending_club_program_id": "club_program_id",
    "pending_contract_claim_id": "contract_claim_id",
    "pending_contract_status": "contract_status",
    "pending_current_club_name": "current_club_name",
    "pending_status_contradiction": "status_contradiction",
    "positions": "positions",
    "preferred_foot": "preferred_foot",
}
_TRUST_DISQUALIFYING_ACTIONS = frozenset({"rejected", "revoked", "suppressed"})


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


def _has_approved_subject_claim(
    subject: ShowcaseSubject,
    user_id: int,
    *,
    for_update: bool = False,
) -> bool:
    query = PlayerProfileClaim.query.filter(
        *_subject_filters(PlayerProfileClaim, subject),
        PlayerProfileClaim.user_account_id == user_id,
        PlayerProfileClaim.status == "approved",
    )
    if for_update:
        query = query.with_for_update()
    return query.first() is not None


def _profile_edit_values(profile: PlayerShowcaseProfile) -> dict[str, object]:
    return {field: getattr(profile, field) for field in _PROFILE_EDIT_FIELD_LABELS}


def _trusted_profile_edit_is_eligible(
    *,
    subject: ShowcaseSubject,
    user: UserAccount,
    was_approved: bool,
    changed_fields: set[str],
) -> bool:
    """Fail-closed trust gate for low-risk edits to an approved profile."""
    min_age_days = showcase_trust_min_account_age_days()
    if min_age_days is None or not was_approved:
        return False
    if not changed_fields.issubset(_AUTO_APPROVAL_PROFILE_FIELDS):
        return False
    # Serialize the final eligibility decision against admin claim review. The
    # earlier owner gate is intentionally repeated under a row lock here.
    if not _has_approved_subject_claim(subject, user.id, for_update=True):
        return False

    created_at = user.created_at
    if created_at is None:
        return False
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    else:
        created_at = created_at.astimezone(UTC)
    try:
        oldest_eligible = datetime.now(UTC) - timedelta(days=min_age_days)
    except OverflowError:
        return False
    if created_at > oldest_eligible:
        return False

    return (
        ShowcaseModerationEvent.query.filter(
            ShowcaseModerationEvent.user_account_id == user.id,
            ShowcaseModerationEvent.action.in_(_TRUST_DISQUALIFYING_ACTIONS),
        ).first()
        is None
    )


def _approved_player_claim(player_api_id: int, user_id: int) -> PlayerProfileClaim | None:
    return (
        PlayerProfileClaim.query.filter_by(
            player_api_id=player_api_id,
            user_account_id=user_id,
            relationship_type="player",
            status="approved",
        )
        .order_by(PlayerProfileClaim.reviewed_at.desc(), PlayerProfileClaim.id.desc())
        .first()
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
        if player is None or player.status in ("merged", "rejected") or _local_player_is_suppressed(player):
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


def _local_player_is_suppressed(player: LocalPlayer) -> bool:
    """Honor both a local takedown and a suppression on a linked API identity."""

    return is_local_player_suppressed(player.id) or bool(
        player.api_player_id is not None and is_player_suppressed(player.api_player_id)
    )


def _duplicates_tracked_identity(display_name: str, birth_year: int | None) -> bool:
    """Block a local alias for an existing tracked identity.

    The response remains identity-neutral, so this also closes the path where
    an active suppression would otherwise be bypassed with a local duplicate.
    A missing birth year is treated conservatively; a supplied year must match
    the tracked DOB (or a tracked row whose DOB is unavailable).
    """

    normalized = _normalize_local_player_name(display_name)
    first_token = normalized.split(" ", 1)[0]
    candidates = TrackedPlayer.query.filter(
        func.lower(TrackedPlayer.player_name).like(
            f"%{_escape_like_literal(first_token)}%",
            escape="\\",
        )
    ).all()
    for candidate in candidates:
        if _normalize_local_player_name(candidate.player_name) != normalized:
            continue
        if birth_year is None or not candidate.birth_date:
            return True
        try:
            if int(str(candidate.birth_date)[:4]) == birth_year:
                return True
        except (TypeError, ValueError):
            return True
    return False


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


def _parse_contract_attestation(
    payload: dict,
    player_api_id: int,
    *,
    existing_claim: PlayerProfileClaim | None = None,
) -> dict:
    """Validate one complete or partial player contract attestation."""
    if "contract_status" in payload:
        raw_status = payload.get("contract_status")
        if not isinstance(raw_status, str):
            raise ValueError("contract_status must be a string")
        contract_status = raw_status.strip().lower()
    elif existing_claim is not None:
        contract_status = existing_claim.contract_status
    else:
        raise ValueError("contract_status is required for player claims")
    if contract_status not in CLAIM_CONTRACT_STATUSES:
        raise ValueError(f"contract_status must be one of {sorted(CLAIM_CONTRACT_STATUSES)}")

    if "current_club_name" in payload:
        current_club_name = clean_plain_text(
            payload.get("current_club_name"),
            "current_club_name",
            max_len=MAX_CURRENT_CLUB_NAME_LENGTH,
            required=False,
        )
    else:
        current_club_name = existing_claim.current_club_name if existing_claim is not None else None

    if "club_program_id" in payload:
        club_program_id = payload.get("club_program_id")
        if club_program_id is not None and (
            isinstance(club_program_id, bool) or not isinstance(club_program_id, int) or club_program_id <= 0
        ):
            raise ValueError("club_program_id must be a positive integer or null")
    else:
        club_program_id = existing_claim.club_program_id if existing_claim is not None else None

    program = None
    if club_program_id is not None:
        program = get_club_program(club_program_id)
        if program is None:
            raise ValueError("club_program_id does not identify an on-platform club program")
    if program is not None:
        # A linked registry identity is authoritative. Never let a claimant
        # route a request to one program while displaying a different club.
        current_club_name = clean_plain_text(
            program.get("name"),
            "current_club_name",
            max_len=MAX_CURRENT_CLUB_NAME_LENGTH,
            required=True,
        )

    return {
        "contract_status": contract_status,
        "current_club_name": current_club_name,
        "club_program_id": club_program_id,
        "status_contradiction": has_status_contradiction(player_api_id, contract_status),
    }


def _contract_attestation_matches_claim(attestation: dict, claim: PlayerProfileClaim) -> bool:
    """Treat the frontend's complete contract payload as a no-op when unchanged."""
    return (
        attestation["contract_status"] == claim.contract_status
        and attestation["current_club_name"] == claim.current_club_name
        and attestation["club_program_id"] == claim.club_program_id
        and bool(attestation["status_contradiction"]) == bool(claim.status_contradiction)
    )


def _claim_contract_payload(claim: PlayerProfileClaim, profile: PlayerShowcaseProfile | None = None) -> dict:
    profile_fields = (
        {"profile_contract_status": profile.contract_status}
        if profile is not None and profile.local_player_id is not None
        else {}
    )
    pending = profile.pending_contract_dict() if profile is not None else None
    if pending and pending["claim_id"] == claim.id:
        return {
            **profile_fields,
            "contract_status": pending["contract_status"],
            "current_club_name": pending["current_club_name"],
            "club_program_id": pending["club_program_id"],
            "status_contradiction": pending["status_contradiction"],
            "contract_attestation_review_status": "pending",
        }
    return {
        **profile_fields,
        "contract_status": claim.contract_status,
        "current_club_name": claim.current_club_name,
        "club_program_id": claim.club_program_id,
        "status_contradiction": bool(claim.status_contradiction),
        "contract_attestation_review_status": "approved",
    }


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
        "club_name": player.club_name,
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
        "club_name": player.club_name,
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


def _resolve_player_age_from_dob(player_api_id: int) -> int | None:
    """Resolve a current age from persisted DOB sources only.

    ``TrackedPlayer.age`` is deliberately excluded: it is a stale snapshot and
    the adults-only self-claim policy requires a known birth date. Malformed
    values fall through so a valid journey or shadow profile can still prove
    eligibility.
    """
    candidates = [
        row[0]
        for row in db.session.query(TrackedPlayer.birth_date)
        .filter(
            TrackedPlayer.player_api_id == player_api_id,
            TrackedPlayer.birth_date.isnot(None),
        )
        .order_by(TrackedPlayer.id.asc())
        .all()
    ]
    journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()
    if journey is not None:
        candidates.append(journey.birth_date)
    shadow = PlayerShadow.query.filter_by(player_api_id=player_api_id, is_active=True).first()
    if shadow is not None:
        candidates.append(shadow.birth_date)

    for birth_date in candidates:
        age = age_from_birth_date(birth_date)
        if age is not None:
            return age
    return None


def _adult_player_claim_error(player_api_id: int):
    """Return the D1 policy error response for an ineligible self-claim."""
    age = _resolve_player_age_from_dob(player_api_id)
    if age is None:
        return jsonify(
            {
                "error": "A known birth date is required for a player to claim their own profile",
                "code": "dob_unknown",
            }
        ), 422
    if age < 18:
        return jsonify(
            {
                "error": "Players must be at least 18 to claim their own profile",
                "code": "minor_claim_blocked",
            }
        ), 422
    return None


def _parse_local_player_birth_date(payload: dict) -> date | None:
    if "birth_date" not in payload:
        return None
    raw_birth_date = payload.get("birth_date")
    if not isinstance(raw_birth_date, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw_birth_date) is None:
        raise ValueError("birth_date must be an ISO date in YYYY-MM-DD format")
    try:
        parsed_birth_date = date.fromisoformat(raw_birth_date)
    except ValueError:
        raise ValueError("birth_date must be an ISO date in YYYY-MM-DD format") from None
    if not MIN_LOCAL_PLAYER_BIRTH_YEAR <= parsed_birth_date.year <= MAX_LOCAL_PLAYER_BIRTH_YEAR:
        raise ValueError(
            f"birth_date year must be between {MIN_LOCAL_PLAYER_BIRTH_YEAR} and {MAX_LOCAL_PLAYER_BIRTH_YEAR}"
        )
    return parsed_birth_date


def _local_self_claim_birth_year(birth_date: date | None, birth_year: int | None) -> int:
    """Require adult evidence for a self-managed local profile.

    An exact birth date is authoritative when supplied. A year alone only
    proves adulthood once every person born in that year must be at least 18.
    """
    today = datetime.now(UTC).date()
    if birth_date is not None:
        age = age_from_birth_date(birth_date, today=today)
        if age is None or age < 18:
            raise ValueError(LOCAL_SELF_CLAIM_ADULT_ERROR)
        return birth_date.year

    if birth_year is None or today.year - birth_year < 19:
        raise ValueError(LOCAL_SELF_CLAIM_ADULT_ERROR)
    return birth_year


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
            # Self-serve club-console footage is private club/report data and
            # must never create public attribution on a player's showcase.
            .filter(VideoMatch.club_program_id.is_(None))
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

        try:
            birth_date = _parse_local_player_birth_date(payload)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400

        birth_year = payload.get("birth_year")
        if birth_date is not None:
            birth_year = birth_date.year
        elif birth_year is not None:
            if isinstance(birth_year, bool) or not isinstance(birth_year, int):
                return jsonify({"error": "birth_year must be an integer between 1950 and 2020"}), 400
            if not MIN_LOCAL_PLAYER_BIRTH_YEAR <= birth_year <= MAX_LOCAL_PLAYER_BIRTH_YEAR:
                return jsonify({"error": "birth_year must be between 1950 and 2020"}), 400

        position = _clean_optional_text(payload.get("position"), MAX_LOCAL_PLAYER_POSITION_LENGTH)
        country = _clean_optional_text(payload.get("country"), MAX_LOCAL_PLAYER_COUNTRY_LENGTH)
        city = _clean_optional_text(payload.get("city"), MAX_LOCAL_PLAYER_CITY_LENGTH)
        club_name = _clean_optional_text(payload.get("club_name"), MAX_LOCAL_PLAYER_CLUB_NAME_LENGTH)

        raw_relationship = payload.get("relationship_type", "player")
        relationship_type = raw_relationship.strip().lower() if isinstance(raw_relationship, str) else ""
        if relationship_type not in LOCAL_PLAYER_RELATIONSHIP_TYPES:
            return (
                jsonify({"error": f"relationship_type must be one of {sorted(LOCAL_PLAYER_RELATIONSHIP_TYPES)}"}),
                400,
            )
        if relationship_type == "player":
            try:
                birth_year = _local_self_claim_birth_year(birth_date, birth_year)
            except ValueError as exc:
                return jsonify({"error": str(exc)}), 400
        elif birth_date is not None:
            age = age_from_birth_date(birth_date, today=datetime.now(UTC).date())
            if age is None or age < 18:
                birth_date = None

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
                    "club_name": existing.club_name,
                    "status": existing.status,
                }
            return jsonify(body), 409

        if _duplicates_tracked_identity(display_name, birth_year) or retained_shadow_identity_exists(
            display_name=display_name,
            birth_year=birth_year,
        ):
            return jsonify({"error": "An existing player identity needs review"}), 409

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
            birth_date=birth_date,
            birth_year=birth_year,
            position=position,
            country=country,
            city=city,
            club_name=club_name,
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
    owner_player_claim = _subject_player_claim(subject, auth_user.id) if auth_user is not None else None
    profile_row = PlayerShowcaseProfile.query.filter(*_subject_filters(PlayerShowcaseProfile, subject)).first()
    if profile_row and profile_row.status == "approved":
        profile = profile_row.public_dict(include_agent_contact=authenticated)
    elif profile_row and is_owner and profile_row.status == "pending":
        profile = profile_row.owner_dict()
    else:
        profile = None
    if profile is not None and owner_player_claim is not None:
        profile.update(_claim_contract_payload(owner_player_claim, profile_row))

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
    if _local_player_is_suppressed(player):
        return False
    user = auth_context["user"] if auth_context else None
    # Minor academy records are club-private even after an identity moderator
    # approves the row. Their claimant may still manage it.
    if local_player_is_minor(player):
        return bool(user and _has_visible_local_claim(player.id, user.id))
    if player.status == "approved":
        return True
    return bool(user and _has_visible_local_claim(player.id, user.id))


@showcase_bp.route("/local-players/<int:lp_id>", methods=["GET"])
def get_local_player(lp_id: int):
    """Public local-player identity, with claimant-only pending visibility."""
    try:
        requested = db.session.get(LocalPlayer, lp_id)
        if requested is not None and _local_player_is_suppressed(requested):
            return jsonify({"error": "local player not found"}), 404
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
        requested = db.session.get(LocalPlayer, lp_id)
        if requested is not None and _local_player_is_suppressed(requested):
            return jsonify({"error": "local player not found"}), 404
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


@showcase_bp.route("/players/<int(signed=True):player_api_id>/showcase", methods=["GET"])
@hide_suppressed_player("player_api_id")
def get_player_showcase(player_api_id: int):
    """Showcase payload: approved profile + reel + verified footage + claim status.

    Optionally authenticated: an approved owner (valid Bearer) additionally sees
    their own pending highlight items and a pending profile draft (each carrying
    a ``status`` for the frontend's "pending review" badge). Anonymous, non-owner,
    or bad-token callers get the approved-only public view — never a 401.
    """
    try:
        resolved = resolve_player_subject(player_api_id)
        if resolved is None or not resolved.is_public:
            return neutral_player_not_found()
        if resolved.is_local:
            player = resolved.local_player
            if player is None or _local_player_is_suppressed(player):
                return neutral_player_not_found()
            subject = _local_subject(player.id)
        else:
            visible = db.session.query(literal(1)).filter(without_minor_local_bridge(player_api_id)).first()
            if visible is None:
                return neutral_player_not_found()
            subject = _api_subject(player_api_id)
        return jsonify(_subject_showcase_payload(subject))
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
@hide_suppressed_player("player_api_id")
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

        if relationship_type == "player":
            attestation = _parse_contract_attestation(payload, player_api_id)
        else:
            attestation = {
                "contract_status": "unknown",
                "current_club_name": None,
                "club_program_id": None,
                "status_contradiction": False,
            }

        existing = PlayerProfileClaim.query.filter_by(player_api_id=player_api_id, user_account_id=user.id).first()
        if existing and existing.status not in ("rejected", "revoked"):
            return jsonify(
                {"error": "You have already submitted a claim for this player", "claim": existing.to_dict()}
            ), 409

        if relationship_type == "player":
            policy_error = _adult_player_claim_error(player_api_id)
            if policy_error is not None:
                return policy_error

        if existing:
            # Recovery path: a rejected/revoked claim may be resubmitted —
            # reset it to pending for a fresh admin review.
            existing.relationship_type = relationship_type
            existing.message = message
            existing.contract_status = attestation["contract_status"]
            existing.current_club_name = attestation["current_club_name"]
            existing.club_program_id = attestation["club_program_id"]
            existing.status_contradiction = attestation["status_contradiction"]
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

        claim = PlayerProfileClaim(
            player_api_id=player_api_id,
            user_account_id=user.id,
            relationship_type=relationship_type,
            message=message,
            contract_status=attestation["contract_status"],
            current_club_name=attestation["current_club_name"],
            club_program_id=attestation["club_program_id"],
            status_contradiction=attestation["status_contradiction"],
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
    except ValueError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400
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


@showcase_bp.route("/showcase/mine/interest-signals", methods=["GET"])
@require_contact_rail
@require_user_auth
def my_interest_signals():
    """Aggregate, identity-free interest in the caller's claimed players.

    Default follow lists mirror the legacy watchlist, so only active,
    non-default direct player follows contribute to the separate follow count.
    Existing digest snapshots contain performance stats rather than membership
    history; ``added_this_week`` therefore counts accounts whose earliest
    surviving membership began since Monday and is not presented as a net
    change.
    """
    try:
        user = _current_user_account()
        if user is None:
            return jsonify({"error": "auth context missing email"}), 401
        player_ids = [subject.signed_id for subject in owned_public_adult_subjects(user.id)]
        now = utcnow()
        week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
        if not player_ids:
            return jsonify(
                {
                    "week_start": week_start.replace(tzinfo=UTC).isoformat(),
                    "interest_signals": [],
                }
            )

        hidden_user_ids = blocked_user_ids(blocker_user_id=user.id)
        watchlist_rows = (
            db.session.query(
                ScoutWatchlistEntry.player_api_id,
                func.count(func.distinct(ScoutWatchlistEntry.user_account_id)),
                func.count(
                    func.distinct(
                        case(
                            (ScoutWatchlistEntry.created_at >= week_start, ScoutWatchlistEntry.user_account_id),
                            else_=None,
                        )
                    )
                ),
            )
            .filter(
                ScoutWatchlistEntry.player_api_id.in_(player_ids),
                ScoutWatchlistEntry.user_account_id.not_in(hidden_user_ids),
            )
            .group_by(ScoutWatchlistEntry.player_api_id)
            .all()
        )
        watchlists = {player_id: (total, added) for player_id, total, added in watchlist_rows}

        followed_player_id = Follow.selector["player_api_id"].as_integer()
        direct_followers = (
            db.session.query(
                followed_player_id.label("player_api_id"),
                FollowList.user_account_id.label("user_account_id"),
                func.min(Follow.created_at).label("first_followed_at"),
            )
            .join(FollowList, FollowList.id == Follow.list_id)
            .filter(
                Follow.kind == "player",
                FollowList.is_active.is_(True),
                FollowList.is_default.is_(False),
                followed_player_id.in_(player_ids),
                FollowList.user_account_id.not_in(hidden_user_ids),
            )
            .group_by(followed_player_id, FollowList.user_account_id)
            .subquery()
        )
        follow_rows = (
            db.session.query(
                direct_followers.c.player_api_id,
                func.count(direct_followers.c.user_account_id),
                func.count(
                    case(
                        (direct_followers.c.first_followed_at >= week_start, direct_followers.c.user_account_id),
                        else_=None,
                    )
                ),
            )
            .group_by(direct_followers.c.player_api_id)
            .all()
        )
        follows = {player_id: (total, added) for player_id, total, added in follow_rows}
        fans = fan_counts(player_ids, since=week_start, exclude_user_ids=hidden_user_ids)
        profile_views = profile_view_counts(player_ids, now=now)

        return jsonify(
            {
                "week_start": week_start.replace(tzinfo=UTC).isoformat(),
                "interest_signals": [
                    {
                        "player_api_id": player_id,
                        "watchlists": {
                            "total": watchlists.get(player_id, (0, 0))[0],
                            "added_this_week": watchlists.get(player_id, (0, 0))[1],
                        },
                        "follows": {
                            "total": follows.get(player_id, (0, 0))[0],
                            "added_this_week": follows.get(player_id, (0, 0))[1],
                        },
                        "fans": {
                            "total": fans[player_id][0],
                            "added_this_week": fans[player_id][1],
                        },
                        "profile_views": profile_views[player_id],
                    }
                    for player_id in player_ids
                ],
            }
        )
    except Exception as e:
        logger.error("Error in my_interest_signals: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load interest signals")), 500


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
@hide_suppressed_player("player_api_id")
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
@hide_suppressed_player("player_api_id")
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
@hide_suppressed_player("player_api_id")
@require_user_auth
@limiter.limit("20 per hour", key_func=_user_rate_limit_key)
def upsert_showcase_profile(player_api_id: int):
    """Upsert a card; only configured trusted low-risk edits retain approval."""
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
            return (jsonify({"error": "invalid_request"}), 400) if subject.is_local else payload_error

        raw_contract_status = payload.get("contract_status")
        if raw_contract_status is not None and not isinstance(raw_contract_status, str):
            if subject.is_local:
                raise InvitationError("invalid_request", 400)
            return jsonify({"error": "contract_status must be a string or null"}), 400
        contract_status = raw_contract_status.strip().lower() or None if isinstance(raw_contract_status, str) else None
        valid_contract_statuses = PROFILE_CONTRACT_STATUSES | CLAIM_CONTRACT_STATUSES
        if contract_status and contract_status not in valid_contract_statuses:
            if subject.is_local:
                raise InvitationError("invalid_request", 400)
            return jsonify({"error": f"contract_status must be one of {sorted(valid_contract_statuses)}"}), 400

        attestation_detail_requested = any(key in payload for key in ("current_club_name", "club_program_id"))
        profile_contract_context = any(
            key in payload
            for key in (
                "contract_until",
                "availability",
                "agent_name",
                "agent_contact_email",
                "nationality_secondary",
                "languages",
            )
        )
        local_contract_update = subject.is_local and (
            attestation_detail_requested
            or contract_status in {"contracted", "unknown"}
            or (contract_status == "free_agent" and not profile_contract_context)
        )
        if local_contract_update:
            if not relationships_enabled():
                return jsonify({"error": "not_found"}), 404
            if set(payload) - {"contract_status", "club_program_id", "current_club_name"}:
                raise InvitationError("invalid_request", 400)
        contract_update_requested = local_contract_update or (
            not subject.is_local and (attestation_detail_requested or contract_status in CLAIM_CONTRACT_STATUSES)
        )
        if "contract_status" not in payload:
            profile_contract_update_requested = not contract_update_requested
        else:
            profile_contract_update_requested = (
                contract_status is None
                or contract_status in {"under_contract", "expiring"}
                or (contract_status == "free_agent" and (subject.is_local or profile_contract_context))
            )

        contract_claim = None
        contract_attestation = None
        if contract_update_requested:
            contract_claim = _subject_player_claim(subject, user.id)
            if contract_claim is None:
                return jsonify({"error": "Only an approved player claimant can update contract status"}), 403
            contract_attestation = (
                local_attestation(db.session, contract_claim, -subject.local_player_id, payload)
                if subject.is_local
                else _parse_contract_attestation(payload, subject.player_api_id, existing_claim=contract_claim)
            )
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
        was_approved = profile is not None and profile.status == "approved"
        if profile is None:
            profile = PlayerShowcaseProfile(**_subject_values(subject))
            db.session.add(profile)
        before_values = _profile_edit_values(profile)
        if contract_attestation is not None and _contract_attestation_matches_claim(
            contract_attestation,
            contract_claim,
        ):
            staged_for_claim = (
                profile.pending_contract_status is not None and profile.pending_contract_claim_id == contract_claim.id
            )
            contract_attestation = None
            profile_contract_update_requested = False
            if staged_for_claim:
                # This is an explicit revert of a different staged
                # attestation, not the frontend repeating an approved value.
                # Clearing the staged fields makes the contract-field diff
                # visible to moderation and therefore keeps the edit pending.
                profile.pending_contract_claim_id = None
                profile.pending_contract_status = None
                profile.pending_current_club_name = None
                profile.pending_club_program_id = None
                profile.pending_status_contradiction = False
        if local_contract_update:
            bio, positions = profile.bio, profile.positions
            preferred_foot, height_cm = profile.preferred_foot, profile.height_cm
            contract_until, availability = profile.contract_until, profile.availability
            agent_name, agent_contact_email = profile.agent_name, profile.agent_contact_email
            nationality_secondary, languages = profile.nationality_secondary, profile.languages
            profile_contract_update_requested = False
        profile.bio = bio
        profile.positions = positions
        profile.preferred_foot = preferred_foot
        profile.height_cm = height_cm
        if profile_contract_update_requested:
            profile.contract_status = contract_status
        profile.contract_until = contract_until
        profile.availability = availability
        profile.agent_name = agent_name
        profile.agent_contact_email = agent_contact_email
        profile.nationality_secondary = nationality_secondary
        profile.languages = languages
        profile.updated_by_user_id = user.id
        if contract_attestation is not None:
            profile.pending_contract_claim_id = contract_claim.id
            profile.pending_contract_status = contract_attestation["contract_status"]
            profile.pending_current_club_name = contract_attestation["current_club_name"]
            profile.pending_club_program_id = contract_attestation["club_program_id"]
            profile.pending_status_contradiction = contract_attestation["status_contradiction"]
        after_values = _profile_edit_values(profile)
        changed_fields = {
            _PROFILE_EDIT_FIELD_LABELS[field]
            for field, before_value in before_values.items()
            if before_value != after_values[field]
        }
        auto_approved = _trusted_profile_edit_is_eligible(
            subject=subject,
            user=user,
            was_approved=was_approved,
            changed_fields=changed_fields,
        )
        profile.status = "approved" if auto_approved else "pending"
        if auto_approved:
            record_moderation_event(
                user_account_id=user.id,
                target_kind="profile",
                target_id=profile.id,
                action="approved",
                actor_email=user.email,
                metadata={"fields": sorted(changed_fields), "auto": True},
                session=db.session,
            )
        db.session.commit()
        response_profile = profile.owner_dict()
        owner_claim = contract_claim or _subject_player_claim(subject, user.id)
        if owner_claim is not None:
            response_profile.update(_claim_contract_payload(owner_claim, profile))
        return jsonify({"profile": response_profile})
    except InvitationError as e:
        db.session.rollback()
        return jsonify({"error": e.code}), e.status
    except ValueError as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400
    except SQLAlchemyError as e:
        return _invitation_database_error(e)
    except Exception as e:
        db.session.rollback()
        logger.error("Error in upsert_showcase_profile: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to save profile")), 500


@showcase_bp.route("/players/<int:player_api_id>/showcase/photos", methods=["POST"])
@hide_suppressed_player("player_api_id")
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
@hide_suppressed_player("player_api_id")
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
@hide_suppressed_player("player_api_id")
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
@hide_suppressed_player("player_api_id")
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
@hide_suppressed_player("player_api_id")
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
@hide_suppressed_player("player_api_id")
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
@hide_suppressed_player("player_api_id")
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
@hide_suppressed_player("player_api_id")
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
    """Approve/reject a pending claim or revoke an approved grant."""
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
        if action in {"reject", "revoke"}:
            record_moderation_event(
                user_account_id=claim.user_account_id,
                target_kind="club_claim",
                target_id=claim.id,
                action=target,
                actor_email=claim.reviewed_by,
                session=db.session,
            )
        if action == "approve":
            grant_console_for_official_claim(claim, actor=claim.reviewed_by, now=now)
        elif action == "revoke":
            revoke_console_for_official_claim(
                claim,
                actor=claim.reviewed_by,
                now=now,
                reason=claim.review_note,
            )
        db.session.commit()
        if action in {"approve", "reject"}:
            try:
                from src.services.trust_decision_email_service import send_club_claim_decision_email

                send_club_claim_decision_email(claim, action)
            except Exception:
                logger.exception("Failed to dispatch %s email for club claim %s", action, claim_id)
        return jsonify({"claim": _club_claim_dict(claim, include_verification_code=False)})
    except ClubConsoleBridgeConflict as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 409
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


def _legacy_negative_identity_conflict(player_api_id: int):
    """Lock and return a referenced legacy identity occupying D1's namespace.

    An unreferenced ``players`` row is inert legacy data and must not prevent a
    LocalPlayer from receiving its deterministic signed id. References in any
    player-universe table make the collision ambiguous, so those fail closed.
    """

    followed_player_id = Follow.selector["player_api_id"].as_integer()
    reference_queries = (
        TrackedPlayer.query.filter_by(player_api_id=player_api_id),
        PlayerShadow.query.filter_by(player_api_id=player_api_id),
        PlayerProfileClaim.query.filter_by(player_api_id=player_api_id),
        ScoutWatchlistEntry.query.filter_by(player_api_id=player_api_id),
        Follow.query.filter(Follow.kind == "player", followed_player_id == player_api_id),
        FollowPlayerSnapshot.query.filter_by(player_api_id=player_api_id),
    )
    for query in reference_queries:
        reference = query.with_for_update().first()
        if reference is not None:
            return reference

    legacy_player = Player.query.filter_by(player_id=player_api_id).with_for_update().first()
    if legacy_player is not None and player_api_id not in _logged_orphan_legacy_player_ids:
        logger.warning("Ignoring orphan legacy players row for reserved negative id %s", player_api_id)
        _logged_orphan_legacy_player_ids.add(player_api_id)
    return None


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
        repeated_approval = action == "approve" and player.status == "approved"
        if player.status != "pending" and not repeated_approval:
            return jsonify({"error": f"cannot {action} a {player.status} local player"}), 409
        if action == "approve" and _local_player_is_suppressed(player):
            return jsonify({"error": "local player not found"}), 404
        synthetic_player_api_id = player.api_player_id if player.api_player_id is not None else -player.id
        if (
            action == "approve"
            and not repeated_approval
            and synthetic_player_api_id < 0
            and _legacy_negative_identity_conflict(synthetic_player_api_id) is not None
        ):
            return jsonify({"error": "synthetic player id conflicts with a legacy manual player"}), 409

        now = datetime.now(UTC)
        if not repeated_approval:
            player.status = "approved" if action == "approve" else "rejected"
            player.review_note = _clean_optional_text(payload.get("note"), MAX_REVIEW_NOTE_LENGTH)
            player.reviewed_by = getattr(g, "user_email", None)
            player.reviewed_at = now
            player.updated_at = now
            if action == "reject":
                record_moderation_event(
                    user_account_id=player.created_by_user_id,
                    target_kind="local_player",
                    target_id=player.id,
                    action="rejected",
                    actor_email=player.reviewed_by,
                    session=db.session,
                )
        if action == "approve":
            if player.api_player_id is None:
                player.api_player_id = -player.id
                player.updated_at = now
            mint_shadow(
                player.api_player_id,
                seed={
                    "name": player.display_name,
                    "position": player.position,
                    "nationality": player.country,
                    "birth_date": player.birth_date,
                    "birth_year": player.birth_year,
                    "club_name": player.club_name,
                },
                requested_by=player.created_by_user_id,
            )
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
_PENDING_PROFILE_MERGE_FIELDS = (
    "pending_contract_claim_id",
    "pending_contract_status",
    "pending_current_club_name",
    "pending_club_program_id",
    "pending_status_contradiction",
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


def _merge_subject_claims(source_subject: ShowcaseSubject, target_subject: ShowcaseSubject) -> int:
    """Move claims while retaining one canonical row per claimant.

    A user may have claimed both duplicate identities before an admin discovers
    the duplicate. The target row survives. Explicit denial is precedence-safe
    (revoked/rejected cannot be resurrected), while the strongest independent
    social-proof evidence and club-vouch provenance are retained.
    """
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
        ContactRequest.query.filter_by(claim_id=source_claim.id).update(
            {ContactRequest.claim_id: target_claim.id},
            synchronize_session=False,
        )
        PlayerShowcaseProfile.query.filter_by(pending_contract_claim_id=source_claim.id).update(
            {PlayerShowcaseProfile.pending_contract_claim_id: target_claim.id},
            synchronize_session=False,
        )
        db.session.delete(source_claim)

    # Flush duplicate removals before the bulk move meets the local claimant
    # uniqueness constraint.
    db.session.flush()
    target_values = _subject_values(target_subject)
    PlayerProfileClaim.query.filter(*_subject_filters(PlayerProfileClaim, source_subject)).update(
        {
            PlayerProfileClaim.player_api_id: target_values["player_api_id"],
            PlayerProfileClaim.local_player_id: target_values["local_player_id"],
        },
        synchronize_session=False,
    )
    return len(source_claims)


def _merge_local_player_claims(source_id: int, target_id: int) -> int:
    return _merge_subject_claims(_local_subject(source_id), _local_subject(target_id))


def _merge_subject_profiles(source_subject: ShowcaseSubject, target_subject: ShowcaseSubject, now: datetime) -> int:
    """Move the source profile, consolidating a target collision safely."""
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
        target_values = _subject_values(target_subject)
        return PlayerShowcaseProfile.query.filter(PlayerShowcaseProfile.id == source_profile.id).update(
            {
                PlayerShowcaseProfile.player_api_id: target_values["player_api_id"],
                PlayerShowcaseProfile.local_player_id: target_values["local_player_id"],
                PlayerShowcaseProfile.updated_at: now,
            },
            synchronize_session=False,
        )

    changed = False
    for field in _PROFILE_MERGE_FIELDS:
        if getattr(target_profile, field) is None and getattr(source_profile, field) is not None:
            setattr(target_profile, field, getattr(source_profile, field))
            changed = True
    if target_profile.pending_contract_status is None and source_profile.pending_contract_status is not None:
        for field in _PENDING_PROFILE_MERGE_FIELDS:
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


def _merge_local_player_profiles(source_id: int, target_id: int, now: datetime) -> int:
    return _merge_subject_profiles(_local_subject(source_id), _local_subject(target_id), now)


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
        player_fans = _rekey_player_fans(
            -source.id,
            target.api_player_id if target.api_player_id is not None else -target.id,
        )

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
                    "player_fans": player_fans,
                },
            }
        )
    except Exception as e:
        db.session.rollback()
        logger.error("Error in admin_merge_local_player: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to merge local player")), 500


class _GraduationConflict(RuntimeError):
    """A collision that cannot be merged without changing user-owned history."""


def _naive_utc(value):
    if value is not None and value.tzinfo is not None:
        return value.replace(tzinfo=None)
    return value


def _earliest(left, right):
    if left is None:
        return right
    if right is None:
        return left
    return left if _naive_utc(left) <= _naive_utc(right) else right


def _latest(left, right):
    if left is None:
        return right
    if right is None:
        return left
    return left if _naive_utc(left) >= _naive_utc(right) else right


def _merge_snapshot_state(target, source) -> None:
    """Keep the newest digest baseline and avoid discarding a useful note."""
    if not target.note and source.note:
        target.note = source.note
    source_is_newer = source.last_digest_at is not None and (
        target.last_digest_at is None or _naive_utc(source.last_digest_at) > _naive_utc(target.last_digest_at)
    )
    if source.last_snapshot is not None and (target.last_snapshot is None or source_is_newer):
        target.last_snapshot = source.last_snapshot
    target.last_digest_at = _latest(target.last_digest_at, source.last_digest_at)
    target.created_at = _earliest(target.created_at, source.created_at)
    if hasattr(target, "updated_at"):
        target.updated_at = _latest(target.updated_at, source.updated_at)


def _merge_media_state(target, source) -> None:
    # Graduation must never make an explicitly denied duplicate public again.
    status_rank = {"pending_upload": 0, "pending": 1, "approved": 2, "rejected": 3}
    if status_rank.get(source.status, -1) > status_rank.get(target.status, -1):
        for field in ("status", "reviewed_by", "reviewed_at", "review_note"):
            setattr(target, field, getattr(source, field))
    for field in ("public_url", "content_type", "size_bytes", "uploaded_by_user_id"):
        if getattr(target, field) is None and getattr(source, field) is not None:
            setattr(target, field, getattr(source, field))
    target.is_primary = bool(target.is_primary or source.is_primary)
    target.created_at = _earliest(target.created_at, source.created_at)
    target.updated_at = _latest(target.updated_at, source.updated_at)


def _rekey_showcase_media(source: ShowcaseSubject, target: ShowcaseSubject, player_api_id: int, now: datetime) -> int:
    source_rows = (
        PlayerShowcaseMedia.query.filter(*_subject_filters(PlayerShowcaseMedia, source)).with_for_update().all()
    )
    target_rows = (
        PlayerShowcaseMedia.query.filter(*_subject_filters(PlayerShowcaseMedia, target)).with_for_update().all()
    )
    target_by_blob = {}
    for row in target_rows:
        existing = target_by_blob.get(row.blob_path)
        if existing is None or (row.status == "rejected" and existing.status != "rejected"):
            target_by_blob[row.blob_path] = row
    to_move = []
    for row in source_rows:
        duplicate = target_by_blob.get(row.blob_path)
        if duplicate is None:
            target_by_blob[row.blob_path] = row
            to_move.append(row)
            continue
        _merge_media_state(duplicate, row)
        db.session.delete(row)
    db.session.flush()
    for row in to_move:
        row.player_api_id = player_api_id
        row.local_player_id = None
        row.updated_at = now

    combined = [row for row in [*target_rows, *to_move] if row not in db.session.deleted and row.kind == "photo"]
    eligible_primaries = [row for row in combined if row.is_primary and row.status != "rejected"]
    if not eligible_primaries:
        eligible_primaries = [row for row in combined if row.is_primary]
    canonical_primary = min(eligible_primaries, key=lambda row: (row.sort_order or 0, row.id or 0), default=None)
    ordered = sorted(
        combined,
        key=lambda row: (
            0 if row is canonical_primary else 1,
            row.sort_order or 0,
            _naive_utc(row.created_at) or datetime.min,
            row.id or 0,
        ),
    )
    for sort_order, row in enumerate(ordered):
        row.is_primary = row is canonical_primary
        row.sort_order = sort_order
    return len(source_rows)


def _merge_affiliation_state(target, source, now: datetime) -> None:
    # Graduation is not a new moderation decision, so rejection wins.
    status_rank = {"pending": 0, "self_reported": 1, "club_confirmed": 2, "rejected": 3}
    if status_rank.get(source.status, -1) > status_rank.get(target.status, -1):
        for field in ("status", "reviewed_by", "reviewed_at", "review_note"):
            setattr(target, field, getattr(source, field))
    if target.season is None and source.season is not None:
        target.season = source.season
    if target.created_by_user_id is None and source.created_by_user_id is not None:
        target.created_by_user_id = source.created_by_user_id
    target.created_at = _earliest(target.created_at, source.created_at)
    target.updated_at = now


def _rekey_affiliations(source: ShowcaseSubject, player_api_id: int, now: datetime) -> int:
    source_rows = (
        PlayerClubAffiliation.query.filter(*_subject_filters(PlayerClubAffiliation, source)).with_for_update().all()
    )
    target_rows = PlayerClubAffiliation.query.filter_by(player_api_id=player_api_id).with_for_update().all()
    target_by_club = {}
    for row in target_rows:
        key = (row.local_club_id, row.team_api_id)
        existing = target_by_club.get(key)
        if existing is None or (row.status == "rejected" and existing.status != "rejected"):
            target_by_club[key] = row
    to_move = []
    for row in source_rows:
        key = (row.local_club_id, row.team_api_id)
        duplicate = target_by_club.get(key)
        if duplicate is None:
            target_by_club[key] = row
            to_move.append(row)
            continue
        _merge_affiliation_state(duplicate, row, now)
        db.session.delete(row)
    db.session.flush()
    for row in to_move:
        row.player_api_id = player_api_id
        row.local_player_id = None
        row.updated_at = now
    return len(source_rows)


def _link_dedup_key(row: PlayerLink) -> tuple[str | None, str]:
    url = (row.url or "").strip()
    return row.link_type, _youtube_video_id(url) or url


def _merge_link_state(target, source) -> None:
    status_rank = {"pending": 0, "approved": 1, "rejected": 2}
    if status_rank.get(source.status, -1) > status_rank.get(target.status, -1):
        target.status = source.status
    if not target.title and source.title:
        target.title = source.title
    if target.user_id is None and source.user_id is not None:
        target.user_id = source.user_id
    target.upvotes = max(target.upvotes or 0, source.upvotes or 0)
    target.sort_order = min(target.sort_order or 0, source.sort_order or 0)
    target.created_at = _earliest(target.created_at, source.created_at)


def _rekey_links(source: ShowcaseSubject, player_api_id: int) -> int:
    source_rows = (
        PlayerLink.query.filter(*_subject_filters(PlayerLink, source, api_field="player_id")).with_for_update().all()
    )
    target_rows = PlayerLink.query.filter_by(player_id=player_api_id).with_for_update().all()
    target_by_key = {}
    for row in target_rows:
        key = _link_dedup_key(row)
        existing = target_by_key.get(key)
        if existing is None or (row.status == "rejected" and existing.status != "rejected"):
            target_by_key[key] = row
    to_move = []
    for row in source_rows:
        key = _link_dedup_key(row)
        duplicate = target_by_key.get(key)
        if duplicate is None:
            target_by_key[key] = row
            to_move.append(row)
            continue
        _merge_link_state(duplicate, row)
        db.session.delete(row)
    db.session.flush()
    for row in to_move:
        row.player_id = player_api_id
        row.local_player_id = None
    highlights = sorted(
        [row for row in [*target_rows, *to_move] if row not in db.session.deleted and row.link_type == "highlight"],
        key=lambda row: (row.sort_order or 0, _naive_utc(row.created_at) or datetime.min, row.id or 0),
    )
    for sort_order, row in enumerate(highlights):
        row.sort_order = sort_order
    return len(source_rows)


def _rekey_showcase_rows(local_player_id: int, player_api_id: int, now: datetime) -> dict:
    source = _local_subject(local_player_id)
    target = _api_subject(player_api_id)
    counts = {
        "claims": _merge_subject_claims(source, target),
        "profiles": _merge_subject_profiles(source, target, now),
        "media": _rekey_showcase_media(source, target, player_api_id, now),
        "affiliations": _rekey_affiliations(source, player_api_id, now),
        "links": _rekey_links(source, player_api_id),
    }
    return counts


def _local_birth_date_for_shadow(player: LocalPlayer):
    return player.birth_date


def _rekey_shadow(
    old_player_api_id: int,
    player_api_id: int,
    local_player: LocalPlayer,
) -> tuple[int, bool]:
    source = PlayerShadow.query.filter_by(player_api_id=old_player_api_id).with_for_update().first()
    target = PlayerShadow.query.filter_by(player_api_id=player_api_id).with_for_update().first()
    if source is None:
        if target is not None:
            return 0, False
        db.session.add(
            PlayerShadow(
                player_api_id=player_api_id,
                player_name=local_player.display_name,
                position=local_player.position,
                nationality=local_player.country,
                birth_date=_local_birth_date_for_shadow(local_player),
                current_club_name=local_player.club_name,
                requested_by_user_id=local_player.created_by_user_id,
                is_active=True,
            )
        )
        db.session.flush()
        return 1, False
    if target is None:
        source.player_api_id = player_api_id
        return 1, False

    for field in (
        "photo_url",
        "position",
        "nationality",
        "birth_date",
        "current_club_name",
        "current_club_api_id",
        "requested_by_user_id",
    ):
        if getattr(target, field) is None and getattr(source, field) is not None:
            setattr(target, field, getattr(source, field))
    target.last_profile_sync_at = _latest(target.last_profile_sync_at, source.last_profile_sync_at)
    target.last_stats_sync_at = _latest(target.last_stats_sync_at, source.last_stats_sync_at)
    target.created_at = _earliest(target.created_at, source.created_at)
    target.is_active = bool(target.is_active or source.is_active)
    db.session.delete(source)
    return 1, True


def _rekey_shadow_stats(old_player_api_id: int, player_api_id: int) -> int:
    source_rows = PlayerShadowStats.query.filter_by(player_api_id=old_player_api_id).with_for_update().all()
    if not source_rows:
        return 0
    target_rows = PlayerShadowStats.query.filter_by(player_api_id=player_api_id).with_for_update().all()
    target_by_key = {(row.team_api_id, row.season): row for row in target_rows}
    to_move = []
    for source in source_rows:
        key = (source.team_api_id, source.season)
        target = target_by_key.get(key)
        if target is None:
            target_by_key[key] = source
            to_move.append(source)
            continue
        for field in ("team_name", "appearances", "goals", "assists", "minutes"):
            if getattr(target, field) is None and getattr(source, field) is not None:
                setattr(target, field, getattr(source, field))
        target.updated_at = _latest(target.updated_at, source.updated_at)
        db.session.delete(source)
    db.session.flush()
    for source in to_move:
        source.player_api_id = player_api_id
    return len(source_rows)


def _rekey_watchlists(old_player_api_id: int, player_api_id: int) -> int:
    source_rows = ScoutWatchlistEntry.query.filter_by(player_api_id=old_player_api_id).with_for_update().all()
    targets = {
        row.user_account_id: row
        for row in ScoutWatchlistEntry.query.filter_by(player_api_id=player_api_id).with_for_update().all()
    }
    to_move = []
    for source in source_rows:
        target = targets.get(source.user_account_id)
        if target is None:
            targets[source.user_account_id] = source
            to_move.append(source)
            continue
        _merge_snapshot_state(target, source)
        db.session.delete(source)
    db.session.flush()
    for source in to_move:
        source.player_api_id = player_api_id
    return len(source_rows)


def _rekey_player_fans(old_player_api_id: int, player_api_id: int) -> int:
    source_rows = PlayerFan.query.filter_by(player_api_id=old_player_api_id).with_for_update().all()
    targets = {
        row.user_account_id: row
        for row in PlayerFan.query.filter_by(player_api_id=player_api_id).with_for_update().all()
    }
    to_move = []
    for source in source_rows:
        target = targets.get(source.user_account_id)
        if target is not None:
            target.created_at = _earliest(
                _naive_utc(target.created_at),
                _naive_utc(source.created_at),
            )
            db.session.delete(source)
            continue
        targets[source.user_account_id] = source
        to_move.append(source)
    db.session.flush()
    for source in to_move:
        source.player_api_id = player_api_id
    return len(source_rows)


def _rekey_follow_snapshots(old_player_api_id: int, player_api_id: int) -> int:
    source_rows = FollowPlayerSnapshot.query.filter_by(player_api_id=old_player_api_id).with_for_update().all()
    targets = {
        row.user_account_id: row
        for row in FollowPlayerSnapshot.query.filter_by(player_api_id=player_api_id).with_for_update().all()
    }
    to_move = []
    for source in source_rows:
        target = targets.get(source.user_account_id)
        if target is None:
            targets[source.user_account_id] = source
            to_move.append(source)
            continue
        _merge_snapshot_state(target, source)
        db.session.delete(source)
    db.session.flush()
    for source in to_move:
        source.player_api_id = player_api_id
    return len(source_rows)


def _rekey_follow_selectors(old_player_api_id: int, player_api_id: int) -> int:
    followed_player_id = Follow.selector["player_api_id"].as_integer()
    player_follows = (
        Follow.query.filter(
            Follow.kind == "player",
            followed_player_id.in_((old_player_api_id, player_api_id)),
        )
        .with_for_update()
        .all()
    )
    source_rows = [row for row in player_follows if (row.selector or {}).get("player_api_id") == old_player_api_id]
    target_by_list = {
        row.list_id: row for row in player_follows if (row.selector or {}).get("player_api_id") == player_api_id
    }
    to_move = []
    for source in source_rows:
        target = target_by_list.get(source.list_id)
        if target is None:
            target_by_list[source.list_id] = source
            to_move.append(source)
            continue
        if not target.note and source.note:
            target.note = source.note
        target.notify_when_fundable = bool(target.notify_when_fundable or source.notify_when_fundable)
        target.created_at = _earliest(target.created_at, source.created_at)
        db.session.delete(source)
    db.session.flush()
    for source in to_move:
        source.selector = {**(source.selector or {}), "player_api_id": player_api_id}
    return len(source_rows)


def _rekey_roster(local_player_id: int, old_player_api_id: int, player_api_id: int) -> tuple[int, int]:
    source_rows = (
        ClubRosterMember.query.filter(
            or_(
                ClubRosterMember.local_player_id == local_player_id,
                ClubRosterMember.player_api_id == old_player_api_id,
            )
        )
        .with_for_update()
        .all()
    )
    targets = {
        row.program_id: row
        for row in ClubRosterMember.query.filter_by(player_api_id=player_api_id).with_for_update().all()
    }
    to_move = []
    video_rows = 0
    for source in source_rows:
        target = targets.get(source.program_id)
        if target is None:
            targets[source.program_id] = source
            to_move.append(source)
            continue
        if not target.role and source.role:
            target.role = source.role
        if not target.note and source.note:
            target.note = source.note
        target.created_at = _earliest(target.created_at, source.created_at)
        video_rows += VideoRosterEntry.query.filter_by(club_roster_member_id=source.id).update(
            {VideoRosterEntry.club_roster_member_id: target.id},
            synchronize_session=False,
        )
        db.session.delete(source)
    db.session.flush()
    for source in to_move:
        source.player_api_id = player_api_id
        source.local_player_id = None
    return len(source_rows), video_rows


def _rekey_video_report_subjects(local_player_id: int, player_api_id: int) -> int:
    return VideoPlayerReport.query.filter_by(club_local_player_id_at_finalize=local_player_id).update(
        {
            VideoPlayerReport.club_player_api_id_at_finalize: player_api_id,
            VideoPlayerReport.club_local_player_id_at_finalize: None,
        },
        synchronize_session=False,
    )


def _rekey_contacts(old_player_api_id: int, player_api_id: int) -> int:
    source_rows = ContactRequest.query.filter_by(player_api_id=old_player_api_id).with_for_update().all()
    active_statuses = {"pending", "accepted"}
    target_active_by_scout = {
        row.scout_user_id: row
        for row in ContactRequest.query.filter(
            ContactRequest.player_api_id == player_api_id,
            ContactRequest.status.in_(active_statuses),
        )
        .with_for_update()
        .all()
    }
    status_rank = {"pending": 0, "accepted": 1}
    now = utcnow()
    for source in source_rows:
        target = target_active_by_scout.get(source.scout_user_id)
        if source.status not in active_statuses or target is None:
            continue
        if status_rank[source.status] > status_rank[target.status]:
            winner, loser = source, target
            target_active_by_scout[source.scout_user_id] = source
        else:
            winner, loser = target, source
        loser.status = "withdrawn"
        loser.responded_at = loser.responded_at or now
        add_audit_event(
            loser,
            "withdrawn",
            actor_user_id=None,
            metadata={
                "reason": "identity_graduation_deduplication",
                "canonical_request_id": winner.id,
            },
            created_at=now,
        )
    db.session.flush()
    for row in source_rows:
        row.player_api_id = player_api_id
    return len(source_rows)


def _rekey_suppressions(local_player_id: int, old_player_api_id: int, player_api_id: int) -> int:
    source_rows = (
        PlayerSuppression.query.filter(
            or_(
                PlayerSuppression.local_player_id == local_player_id,
                PlayerSuppression.player_api_id == old_player_api_id,
            )
        )
        .with_for_update()
        .all()
    )
    target_rows = PlayerSuppression.query.filter_by(player_api_id=player_api_id).with_for_update().all()
    open_statuses = {"requested", "active"}
    open_rows = [row for row in [*source_rows, *target_rows] if row.status in open_statuses]
    if len(open_rows) > 1:
        target_ids = {row.id for row in target_rows}
        status_rank = {"requested": 0, "active": 1}
        winner = max(
            open_rows,
            key=lambda row: (status_rank[row.status], row.id in target_ids, row.id),
        )
        decided_at = datetime.now(UTC)
        note = "Consolidated into the canonical identity during local-to-API graduation."
        for row in open_rows:
            if row is winner:
                continue
            row.status = "lifted" if row.status == "active" else "rejected"
            row.decided_at = decided_at
            row.decided_by = "system:identity-graduation"
            row.notes = f"{row.notes}\n{note}"[-2000:] if row.notes else note
        db.session.flush()
    for row in source_rows:
        row.player_api_id = player_api_id
        row.local_player_id = None
    return len(source_rows)


def _rekey_windowed_player_rows(model, old_player_api_id: int, player_api_id: int) -> int:
    """Move pulse/card rows, retaining the newest payload on key collisions."""

    source_rows = model.query.filter_by(player_api_id=old_player_api_id).with_for_update().all()
    if not source_rows:
        return 0
    target_by_window = {
        row.window_end: row for row in model.query.filter_by(player_api_id=player_api_id).with_for_update().all()
    }
    to_move = []
    for source in source_rows:
        target = target_by_window.get(source.window_end)
        if target is None:
            target_by_window[source.window_end] = source
            to_move.append(source)
            continue
        source_created = _naive_utc(source.created_at)
        target_created = _naive_utc(target.created_at)
        if source_created is not None and (target_created is None or source_created > target_created):
            if isinstance(source, PlayerPulse):
                target.score = source.score
                target.delta_json = source.delta_json
            else:
                target.card_html = source.card_html
                target.card_text = source.card_text
                target.model = source.model
            target.created_at = source.created_at
        db.session.delete(source)
    db.session.flush()
    for source in to_move:
        source.player_api_id = player_api_id
    return len(source_rows)


def _rekey_newsletter_youtube_links(old_player_api_id: int, player_api_id: int) -> int:
    source_rows = NewsletterPlayerYoutubeLink.query.filter_by(player_id=old_player_api_id).with_for_update().all()
    target_by_newsletter = {
        row.newsletter_id: row
        for row in NewsletterPlayerYoutubeLink.query.filter_by(player_id=player_api_id).with_for_update().all()
    }
    to_move = []
    for source in source_rows:
        if source.newsletter_id in target_by_newsletter:
            db.session.delete(source)
        else:
            target_by_newsletter[source.newsletter_id] = source
            to_move.append(source)
    db.session.flush()
    for source in to_move:
        source.player_id = player_api_id
    return len(source_rows)


def _rekey_content_references(old_player_api_id: int, player_api_id: int) -> dict:
    """Move signed-id content that can be created for followed/local players."""

    return {
        "player_pulses": _rekey_windowed_player_rows(PlayerPulse, old_player_api_id, player_api_id),
        "player_card_cache": _rekey_windowed_player_rows(PlayerCardCache, old_player_api_id, player_api_id),
        "newsletter_youtube_links": _rekey_newsletter_youtube_links(old_player_api_id, player_api_id),
        "player_flags": PlayerFlag.query.filter_by(player_api_id=old_player_api_id).update(
            {PlayerFlag.player_api_id: player_api_id},
            synchronize_session=False,
        ),
        "quick_take_submissions": QuickTakeSubmission.query.filter_by(player_id=old_player_api_id).update(
            {QuickTakeSubmission.player_id: player_api_id},
            synchronize_session=False,
        ),
        "community_takes": CommunityTake.query.filter_by(player_id=old_player_api_id).update(
            {CommunityTake.player_id: player_api_id},
            synchronize_session=False,
        ),
        "newsletter_commentary": NewsletterCommentary.query.filter_by(player_id=old_player_api_id).update(
            {NewsletterCommentary.player_id: player_api_id},
            synchronize_session=False,
        ),
        "player_comments": PlayerComment.query.filter_by(player_id=old_player_api_id).update(
            {PlayerComment.player_id: player_api_id},
            synchronize_session=False,
        ),
    }


def _rekey_extra_tables(old_player_api_id: int, player_api_id: int, session) -> dict:
    """Re-key user-entered match rows before refreshing derived totals."""
    source_rows = session.query(PlayerMatchEntry).filter_by(player_api_id=old_player_api_id).with_for_update().all()
    target_rows = session.query(PlayerMatchEntry).filter_by(player_api_id=player_api_id).with_for_update().all()
    target_by_identity = {
        (row.match_date, row.opponent, row.source, row.reported_by_user_id): row for row in target_rows
    }
    to_move = []
    editable_fields = (
        "season",
        "status",
        "club_program_id",
        "competition",
        "home_away",
        "result_for",
        "result_against",
        "minutes",
        "goals",
        "assists",
        "yellows",
        "reds",
        "saves",
        "goals_conceded",
        "note",
    )
    for source in source_rows:
        identity = (source.match_date, source.opponent, source.source, source.reported_by_user_id)
        target = target_by_identity.get(identity)
        if target is None:
            target_by_identity[identity] = source
            to_move.append(source)
            continue

        source_is_newer = source.updated_at is not None and (
            target.updated_at is None or _naive_utc(source.updated_at) > _naive_utc(target.updated_at)
        )
        target_was_disputed = target.status == "disputed"
        if source_is_newer:
            for field in editable_fields:
                setattr(target, field, getattr(source, field))
        if target_was_disputed or source.status == "disputed":
            target.status = "disputed"
        target.created_at = _earliest(target.created_at, source.created_at)
        target.updated_at = _latest(target.updated_at, source.updated_at)
        session.delete(source)

    session.flush()
    for source in to_move:
        source.player_api_id = player_api_id
    session.flush()
    return {"player_match_entries": len(source_rows)} if source_rows else {}


def _rekey_rollup_rows(old_player_api_id: int, player_api_id: int) -> dict:
    """Re-key derived rows collision-safely before rebuilding them from source.

    Shadow plus user/club match-entry sources are re-keyed before refresh. Fail
    closed if API-derived rows somehow exist for a synthetic local identity.
    """
    source_cells = PlayerSeasonCell.query.filter_by(player_api_id=old_player_api_id).with_for_update().all()
    source_totals = PlayerSeasonTotal.query.filter_by(player_api_id=old_player_api_id).with_for_update().all()
    # API fixture/journey/APSS rows should never exist for a synthetic local id;
    # fail closed if malformed historical data says otherwise instead of
    # refreshing those totals into zeros.
    rebuildable_sources = {"club", "shadow", "user"}
    observed_sources = {row.source for row in source_cells} | {row.primary_source for row in source_totals}
    unsupported_sources = sorted(source for source in observed_sources if source not in rebuildable_sources)
    if unsupported_sources:
        raise _GraduationConflict(f"rollup sources require graduation integration: {', '.join(unsupported_sources)}")

    target_cells = PlayerSeasonCell.query.filter_by(player_api_id=player_api_id).with_for_update().all()
    target_cells_by_key = {(row.season, row.source, row.club_api_id, row.competition_tier): row for row in target_cells}
    cells_to_move = []
    for source in source_cells:
        key = (source.season, source.source, source.club_api_id, source.competition_tier)
        if key in target_cells_by_key:
            db.session.delete(source)
        else:
            target_cells_by_key[key] = source
            cells_to_move.append(source)

    target_totals_by_key = {
        (row.season, row.level_group): row
        for row in PlayerSeasonTotal.query.filter_by(player_api_id=player_api_id).with_for_update().all()
    }
    totals_to_move = []
    for source in source_totals:
        key = (source.season, source.level_group)
        if key in target_totals_by_key:
            db.session.delete(source)
        else:
            target_totals_by_key[key] = source
            totals_to_move.append(source)

    db.session.flush()
    for source in cells_to_move:
        source.player_api_id = player_api_id
    for source in totals_to_move:
        source.player_api_id = player_api_id
    db.session.flush()
    return {"season_cells": len(source_cells), "season_totals": len(source_totals)}


def _refresh_graduated_rollup(old_player_api_id: int, player_api_id: int) -> tuple[dict, dict]:
    extra_counts = _rekey_extra_tables(old_player_api_id, player_api_id, db.session)
    for locked_player_api_id in sorted((old_player_api_id, player_api_id)):
        season_rollup_service._lock_player_refresh(db.session, locked_player_api_id)

    visible_reported_sources = {
        row.source
        for row in PlayerSeasonCell.query.filter_by(player_api_id=old_player_api_id).with_for_update().all()
        if row.source in {"club", "user"}
    }
    visible_reported_sources.update(
        row.primary_source
        for row in PlayerSeasonTotal.query.filter_by(player_api_id=old_player_api_id).with_for_update().all()
        if row.primary_source in {"club", "user"}
    )
    rollup_counts = _rekey_rollup_rows(old_player_api_id, player_api_id)
    rollup = season_rollup_service.refresh_player(player_api_id, session=db.session)
    rebuilt_sources = {
        row.source
        for row in PlayerSeasonCell.query.filter(
            PlayerSeasonCell.player_api_id == player_api_id,
            PlayerSeasonCell.source.in_(visible_reported_sources),
        ).all()
    }
    missing_sources = sorted(visible_reported_sources - rebuilt_sources)
    if missing_sources:
        raise _GraduationConflict("graduated rollup withheld previously visible sources: " + ", ".join(missing_sources))
    return {**rollup_counts, **extra_counts}, rollup


@showcase_bp.route("/admin/local-players/<int:lp_id>/link-api", methods=["POST"])
@require_api_key
def admin_link_local_player_api(lp_id: int):
    """Atomically graduate a synthetic local identity to an API-Football id."""
    try:
        player = LocalPlayer.query.filter_by(id=lp_id).with_for_update().first()
        if player is None:
            return jsonify({"error": "local player not found"}), 404
        payload, payload_error = _json_object_or_400()
        if payload_error:
            return payload_error
        player_api_id = payload.get("player_api_id")
        if isinstance(player_api_id, bool) or not isinstance(player_api_id, int) or player_api_id <= 0:
            return jsonify({"error": "player_api_id must be a positive integer"}), 400
        if player.status != "approved":
            return jsonify({"error": "only an approved local player can be linked"}), 409
        conflict = (
            LocalPlayer.query.filter(
                LocalPlayer.id != player.id,
                LocalPlayer.api_player_id == player_api_id,
            )
            .with_for_update()
            .first()
        )
        if conflict is not None:
            return jsonify({"error": "player_api_id is already linked to another local player"}), 409

        old_player_api_id = -player.id
        if player.api_player_id is None and _legacy_negative_identity_conflict(old_player_api_id) is not None:
            return jsonify({"error": "synthetic player id conflicts with a legacy manual player"}), 409
        if player.api_player_id not in (None, old_player_api_id, player_api_id):
            return jsonify({"error": "local player is already linked to a different API player"}), 409

        now = datetime.now(UTC)
        rekeyed = _rekey_showcase_rows(player.id, player_api_id, now)
        shadow_count, shadow_merged = _rekey_shadow(old_player_api_id, player_api_id, player)
        rekeyed["player_shadows"] = shadow_count
        rekeyed["shadow_stats"] = _rekey_shadow_stats(old_player_api_id, player_api_id)
        rekeyed["watchlist_entries"] = _rekey_watchlists(old_player_api_id, player_api_id)
        rekeyed["player_fans"] = _rekey_player_fans(old_player_api_id, player_api_id)
        rekeyed["follow_selectors"] = _rekey_follow_selectors(old_player_api_id, player_api_id)
        rekeyed["follow_snapshots"] = _rekey_follow_snapshots(old_player_api_id, player_api_id)
        roster_rows, video_rows = _rekey_roster(player.id, old_player_api_id, player_api_id)
        rekeyed["roster_members"] = roster_rows
        rekeyed["video_roster_entries"] = video_rows
        rekeyed["video_player_reports"] = _rekey_video_report_subjects(player.id, player_api_id)
        rekeyed["contact_requests"] = _rekey_contacts(old_player_api_id, player_api_id)
        rekeyed["suppressions"] = _rekey_suppressions(player.id, old_player_api_id, player_api_id)
        rekeyed.update(_rekey_content_references(old_player_api_id, player_api_id))
        player.api_player_id = player_api_id
        player.updated_at = now
        db.session.flush()
        rollup_counts, rollup = _refresh_graduated_rollup(old_player_api_id, player_api_id)
        rekeyed.update(rollup_counts)

        db.session.commit()
        return jsonify(
            {
                "player": _local_player_admin_dict(player),
                "graduation": {
                    "from_player_api_id": old_player_api_id,
                    "to_player_api_id": player_api_id,
                    "rekeyed": rekeyed,
                    "shadow_merged": shadow_merged,
                    "rollup": rollup,
                },
            }
        )
    except _GraduationConflict as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 409
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
        if action == "approve":
            if media.player_api_id is not None:
                suppressed = is_player_suppressed(media.player_api_id)
            else:
                local_player = db.session.get(LocalPlayer, media.local_player_id)
                suppressed = local_player is None or _local_player_is_suppressed(local_player)
            if suppressed:
                # Neutral refusal: the pending row/blob remains private for
                # incident review and cannot be published after a takedown.
                return jsonify({"error": "photo not found"}), 404
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
        if action == "reject":
            record_moderation_event(
                user_account_id=media.uploaded_by_user_id,
                target_kind="media",
                target_id=media.id,
                action="rejected",
                actor_email=media.reviewed_by,
                session=db.session,
            )
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

        if action == "approve" and claim.player_api_id is not None and is_player_suppressed(claim.player_api_id):
            return neutral_player_not_found()

        if action == "approve" and claim.player_api_id is not None and claim.relationship_type == "player":
            policy_error = _adult_player_claim_error(claim.player_api_id)
            if policy_error is not None:
                return policy_error
            claim.status_contradiction = has_status_contradiction(claim.player_api_id, claim.contract_status)

        claim.status = target
        claim.reviewed_by = getattr(g, "user_email", None)
        claim.reviewed_at = datetime.now(UTC)
        if action in {"reject", "revoke"}:
            record_moderation_event(
                user_account_id=claim.user_account_id,
                target_kind="claim",
                target_id=claim.id,
                action=target,
                actor_email=claim.reviewed_by,
                session=db.session,
            )
        db.session.commit()
        if action in {"approve", "reject"}:
            try:
                from src.services.trust_decision_email_service import send_player_claim_decision_email

                send_player_claim_decision_email(claim, action, _resolve_claim_player_name(claim))
            except Exception:
                logger.exception("Failed to dispatch %s email for player claim %s", action, claim_id)
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
            contract_claim = (
                db.session.get(PlayerProfileClaim, profile.pending_contract_claim_id)
                if profile.pending_contract_claim_id is not None
                else None
            )
            if contract_claim is None and profile.updated_by_user_id is not None:
                contract_claim = _subject_player_claim(
                    _local_subject(profile.local_player_id)
                    if profile.local_player_id
                    else _api_subject(profile.player_api_id),
                    profile.updated_by_user_id,
                )
            if contract_claim is not None:
                payload.update(_claim_contract_payload(contract_claim, profile))
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
        if subject.is_local and profile.pending_contract_status is not None:
            body = request.get_json(silent=True)
            if not isinstance(body, dict) or set(body) != {"action"} or body["action"] not in ("approve", "reject"):
                raise InvitationError("invalid_request", 400)
        payload = request.get_json(silent=True) or {}
        action = (payload.get("action") or "").strip().lower()
        if action not in ("approve", "reject"):
            return jsonify({"error": "action must be approve or reject"}), 400
        contract_claim = None
        if action == "approve" and profile.pending_contract_status is not None:
            contract_claim = db.session.get(PlayerProfileClaim, profile.pending_contract_claim_id)
            if subject.is_local:
                if not relationships_enabled():
                    return jsonify({"error": "not_found"}), 404
                if contract_claim is None or contract_claim.user_account_id != profile.updated_by_user_id:
                    raise InvitationError("club_relationship_required")
                local_attestation(
                    db.session,
                    contract_claim,
                    -subject.local_player_id,
                    {
                        "contract_status": profile.pending_contract_status,
                        "club_program_id": profile.pending_club_program_id,
                        "current_club_name": profile.pending_current_club_name,
                    },
                )
                db.session.refresh(profile, with_for_update=True)
                # Revocation locks the claim first, so the staged selection is stable here.
                if profile.pending_contract_status is None:
                    raise InvitationError("club_relationship_required")
            elif (
                contract_claim is None
                or contract_claim.player_api_id != subject.player_api_id
                or contract_claim.relationship_type != "player"
                or contract_claim.status != "approved"
            ):
                return jsonify({"error": "contract attestation claim is no longer approved"}), 409
            contract_claim.contract_status = profile.pending_contract_status
            contract_claim.current_club_name = profile.pending_current_club_name
            contract_claim.club_program_id = profile.pending_club_program_id
            contract_claim.status_contradiction = (
                False
                if subject.is_local
                else has_status_contradiction(
                    subject.player_api_id,
                    profile.pending_contract_status,
                )
            )
            profile.pending_contract_claim_id = None
            profile.pending_contract_status = None
            profile.pending_current_club_name = None
            profile.pending_club_program_id = None
            profile.pending_status_contradiction = False
        profile.status = "approved" if action == "approve" else "pending"
        profile.reviewed_by = getattr(g, "user_email", None)
        profile.reviewed_at = datetime.now(UTC)
        if action == "reject":
            record_moderation_event(
                user_account_id=profile.updated_by_user_id,
                target_kind="profile",
                target_id=profile.id,
                action="rejected",
                actor_email=profile.reviewed_by,
                session=db.session,
            )
        db.session.commit()
        response_profile = profile.owner_dict()
        if contract_claim is None and profile.updated_by_user_id is not None:
            contract_claim = _subject_player_claim(subject, profile.updated_by_user_id)
        if contract_claim is not None:
            response_profile.update(_claim_contract_payload(contract_claim, profile))
        return jsonify({"profile": response_profile})
    except InvitationError as e:
        db.session.rollback()
        return jsonify({"error": e.code}), e.status
    except SQLAlchemyError as e:
        return _invitation_database_error(e)
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


# HTTP adapters live in blueprints; the relationship module owns transaction policy.
from src.routes.club import (
    _invitation_database_error,
    _invitation_limit_key,
    _invitation_list_response,
    _invitation_operation,
    _invitation_rate_rejected,
    _require_relationships,
)


def _subject_player_claim(subject, user_id):
    return subject_claim(db.session, -subject.local_player_id if subject.is_local else subject.player_api_id, user_id)


@showcase_bp.after_request
def _private_relationship_response(response):
    if "/club-invitations" in request.path or (
        request.headers.get("Authorization") and ("/showcase" in request.path or "/local-profiles" in request.path)
    ):
        response.headers["Cache-Control"] = "private, no-store"
    return response


def _require_pinned_invitation(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        from src.services.public_player_subject import resolve_public_adult_subject

        invitation = ClubInvitation.query.filter_by(
            id=str(kwargs["invitation_id"]), recipient_user_id=g.user_id
        ).first()
        if (
            invitation is None
            or not claim_matches(
                db.session, db.session.get(PlayerProfileClaim, invitation.claim_id), invitation.player_api_id, g.user_id
            )
            or not resolve_public_adult_subject(invitation.player_api_id)
        ):
            return jsonify({"error": "invitation_not_found"}), 404
        g.club_invitation = invitation
        return view(*args, **kwargs)

    return wrapped


@showcase_bp.route("/me/club-invitations", methods=["GET"])
@require_user_auth
@_require_relationships
@limiter.limit("60 per minute", key_func=_invitation_limit_key, on_breach=_invitation_rate_rejected)
def my_club_invitations():
    # Recipient scoping happens before cursor resolution and pagination.
    return _invitation_list_response(recipient_id=g.user_id)


@showcase_bp.route("/me/club-invitations/<uuid:invitation_id>/accept", methods=["POST"], defaults={"action": "accept"})
@showcase_bp.route(
    "/me/club-invitations/<uuid:invitation_id>/decline", methods=["POST"], defaults={"action": "decline"}
)
@showcase_bp.route("/me/club-invitations/<uuid:invitation_id>/revoke", methods=["POST"], defaults={"action": "revoke"})
@require_user_auth
@_require_pinned_invitation
@_require_relationships
@limiter.shared_limit(
    "20 per hour",
    key_func=_invitation_limit_key,
    on_breach=_invitation_rate_rejected,
    scope="club-invitation-decisions",
)
def decide_club_invitation(invitation_id, action):
    if request.get_json(silent=True) != {}:
        return jsonify({"error": "invalid_request"}), 400
    return _invitation_operation(lambda: (resolve_invitation(db.session, g.club_invitation, g.user_id, action), 200))
