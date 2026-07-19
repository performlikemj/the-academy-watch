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
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from flask import Blueprint, abort, g, jsonify, request
from sqlalchemy import case, func
from sqlalchemy.exc import IntegrityError
from src.auth import (
    _ensure_user_account,
    _safe_error_payload,
    _user_serializer,
    require_api_key,
    require_user_auth,
)
from src.extensions import limiter
from src.models.follow import Follow, FollowList, PlayerShadow
from src.models.journey import PlayerJourney
from src.models.league import NewsletterPlayerYoutubeLink, PlayerLink, UserAccount, db
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.showcase import PlayerProfileClaim, PlayerShowcaseProfile
from src.models.tracked_player import TrackedPlayer
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry
from src.services.contact import contact_rail_enabled, require_contact_rail, utcnow
from src.utils.academy_window import age_from_birth_date
from src.utils.sanitize import is_safe_https_url, sanitize_plain_text

logger = logging.getLogger(__name__)

showcase_bp = Blueprint("showcase", __name__)


@showcase_bp.before_app_request
def _hide_interest_signal_path_when_contact_rail_disabled():
    """Hide OPTIONS and wrong-method probes as well as supported methods."""
    if request.path.rstrip("/") == "/api/showcase/mine/interest-signals" and not contact_rail_enabled():
        abort(404)


RELATIONSHIP_TYPES = {"player", "agent", "guardian", "club_official"}
CLAIM_STATUSES = {"pending", "approved", "rejected", "revoked"}
PROFILE_STATUSES = {"pending", "approved"}
PREFERRED_FEET = {"left", "right", "both"}

MAX_BIO_LENGTH = 2000
MAX_POSITIONS_LENGTH = 100
MAX_TITLE_LENGTH = 200
MAX_MESSAGE_LENGTH = 1000
MAX_URL_LENGTH = 500
MAX_REEL_ITEMS = 20
MIN_HEIGHT_CM = 100
MAX_HEIGHT_CM = 260
VERIFIED_FOOTAGE_CAP = 10
PLAYER_SEARCH_CAP = 20

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


def _optional_owner_user(player_api_id: int):
    """The authenticated approved owner of this player, or None (optional auth).

    Parses the Bearer manually — mirroring ``require_user_auth`` internals — so a
    missing / expired / malformed token DEGRADES to the public view instead of
    401. Returns the UserAccount only when the token is valid AND that user holds
    an approved claim on the player. Any error → None (never raise).
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
        user = UserAccount.query.filter_by(email=email).first()
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
    cleaned = sanitize_plain_text(value).strip()
    return cleaned[:max_len] if cleaned else None


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
        is_owner = _optional_owner_user(player_api_id) is not None

        profile_row = PlayerShowcaseProfile.query.filter_by(player_api_id=player_api_id).first()
        if profile_row and profile_row.status == "approved":
            profile = profile_row.public_dict()
        elif profile_row and is_owner and profile_row.status == "pending":
            # Owner sees their unpublished draft with its status; public does not.
            profile = profile_row.owner_dict()
        else:
            profile = None

        reel = _highlight_reel(player_api_id, include_pending=is_owner)

        claimed = PlayerProfileClaim.query.filter_by(player_api_id=player_api_id, status="approved").first() is not None

        return jsonify(
            {
                "player_api_id": player_api_id,
                "profile": profile,
                "reel": reel,
                "verified_footage": _verified_footage(player_api_id),
                "claim_status": "claimed" if claimed else "unclaimed",
            }
        )
    except Exception as e:
        logger.error("Error in get_player_showcase: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load showcase")), 500


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
            if existing.status not in ("rejected", "revoked"):
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
            existing.status = "pending"
            existing.reviewed_by = None
            existing.reviewed_at = None
            existing.created_at = datetime.now(UTC)
            db.session.commit()
            return jsonify({"claim": existing.to_dict()}), 201

        claim = PlayerProfileClaim(
            player_api_id=player_api_id,
            user_account_id=user.id,
            relationship_type=relationship_type,
            message=message,
            status="pending",
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
        out = []
        for claim in claims:
            payload = claim.to_dict()
            payload["player_name"] = _resolve_player_name(claim.player_api_id)
            out.append(payload)
        return jsonify({"claims": out})
    except Exception as e:
        logger.error("Error in my_claims: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load claims")), 500


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

        player_ids = [
            row[0]
            for row in db.session.query(PlayerProfileClaim.player_api_id)
            .filter_by(
                user_account_id=user.id,
                relationship_type="player",
                status="approved",
            )
            .distinct()
            .order_by(PlayerProfileClaim.player_api_id.asc())
            .all()
        ]
        now = utcnow()
        week_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=now.weekday())
        if not player_ids:
            return jsonify(
                {
                    "week_start": week_start.replace(tzinfo=UTC).isoformat(),
                    "interest_signals": [],
                }
            )

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
            .filter(ScoutWatchlistEntry.player_api_id.in_(player_ids))
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
                    }
                    for player_id in player_ids
                ],
            }
        )
    except Exception as e:
        logger.error("Error in my_interest_signals: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to load interest signals")), 500


# ---------------------------------------------------------------------------
# Owner-gated — profile + reel curation
# ---------------------------------------------------------------------------


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

        payload = request.get_json(silent=True) or {}
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

        profile = PlayerShowcaseProfile.query.filter_by(player_api_id=player_api_id).first()
        if profile is None:
            profile = PlayerShowcaseProfile(player_api_id=player_api_id)
            db.session.add(profile)
        profile.bio = bio
        profile.positions = positions
        profile.preferred_foot = preferred_foot
        profile.height_cm = height_cm
        profile.status = "pending"  # owner edit → pending; hidden until re-approved
        profile.updated_by_user_id = user.id
        db.session.commit()
        return jsonify({"profile": profile.owner_dict()})
    except Exception as e:
        db.session.rollback()
        logger.error("Error in upsert_showcase_profile: %s", e)
        return jsonify(_safe_error_payload(e, "Failed to save profile")), 500


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
# Admin — claim + profile review
# ---------------------------------------------------------------------------


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

        if action == "approve" and claim.relationship_type == "player":
            policy_error = _adult_player_claim_error(claim.player_api_id)
            if policy_error is not None:
                return policy_error

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
