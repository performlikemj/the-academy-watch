"""Curator API endpoints for The Academy Watch.

Handles:
- Tweet curation: CRUD for CommunityTakes with source_type='twitter'
- Newsletter generation scoped to curator's approved teams
- Tweet-to-newsletter attachment
"""

import logging
import re
from datetime import UTC, datetime, timedelta

from flask import Blueprint, g, jsonify, request
from src.auth import require_curator_auth
from src.models.league import (
    CommunityTake,
    JournalistTeamAssignment,
    Newsletter,
    Team,
    db,
)
from src.models.tracked_player import TrackedPlayer
from src.utils.sanitize import sanitize_comment_body, sanitize_plain_text

curator_bp = Blueprint("curator", __name__)
logger = logging.getLogger(__name__)


def _get_curator_team_ids() -> list[int]:
    """Get team IDs the current curator is assigned to."""
    assignments = JournalistTeamAssignment.query.filter_by(user_id=g.user.id).all()
    return [a.team_id for a in assignments]


def _curator_can_access_team(team_id: int) -> bool:
    """Check if the current curator is assigned to the given team."""
    return JournalistTeamAssignment.query.filter_by(user_id=g.user.id, team_id=team_id).first() is not None


# =============================================================================
# Team Endpoints
# =============================================================================


@curator_bp.route("/curator/teams", methods=["GET"])
@require_curator_auth
def curator_teams():
    """List teams the curator is assigned to."""
    team_ids = _get_curator_team_ids()
    teams = Team.query.filter(Team.id.in_(team_ids)).all() if team_ids else []
    return jsonify(
        {
            "teams": [{"id": t.id, "name": t.name, "team_id": t.team_id, "logo": t.logo} for t in teams],
        }
    )


# =============================================================================
# Newsletter Endpoints
# =============================================================================


@curator_bp.route("/curator/newsletters", methods=["GET"])
@require_curator_auth
def curator_newsletters():
    """List newsletters for the curator's approved teams.

    Query params:
    - team_id: Filter by specific team (must be an approved team)
    - limit: Max results (default 20, max 100)
    - offset: Pagination offset
    """
    team_ids = _get_curator_team_ids()
    if not team_ids:
        return jsonify({"newsletters": [], "total": 0})

    filter_team = request.args.get("team_id", type=int)
    if filter_team and filter_team not in team_ids:
        return jsonify({"error": "Not authorized for this team"}), 403

    target_ids = [filter_team] if filter_team else team_ids
    limit = min(request.args.get("limit", 20, type=int), 100)
    offset = request.args.get("offset", 0, type=int)

    query = Newsletter.query.filter(Newsletter.team_id.in_(target_ids))
    query = query.order_by(Newsletter.created_at.desc())
    total = query.count()
    newsletters = query.offset(offset).limit(limit).all()

    return jsonify(
        {
            "newsletters": [n.to_dict() for n in newsletters],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )


@curator_bp.route("/curator/newsletters/generate", methods=["POST"])
@require_curator_auth
def curator_generate_newsletter():
    """Generate a newsletter for an approved team.

    Body:
    - team_id: Required. Must be an approved team.
    - target_date: Optional. YYYY-MM-DD format. Defaults to today.
    - force_refresh: Optional. Boolean. Default false.
    """
    data = request.get_json() or {}
    team_id = data.get("team_id")
    target_date_str = data.get("target_date")
    force_refresh = data.get("force_refresh", False)

    if not team_id:
        return jsonify({"error": "team_id is required"}), 400

    if not _curator_can_access_team(team_id):
        return jsonify({"error": "Not authorized for this team"}), 403

    team = db.session.get(Team, team_id)
    if not team:
        return jsonify({"error": "Team not found"}), 404

    # Parse target date
    if target_date_str:
        try:
            target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400
    else:
        target_date = datetime.now(UTC).date()

    # Compute week window
    week_start = target_date - timedelta(days=target_date.weekday())
    week_end = week_start + timedelta(days=6)

    # Check for existing newsletter
    existing = Newsletter.query.filter_by(
        team_id=team_id,
        newsletter_type="weekly",
        week_start_date=week_start,
        week_end_date=week_end,
    ).first()

    if existing and not force_refresh:
        return jsonify(
            {
                "message": "Newsletter already exists for this week",
                "newsletter": existing.to_dict(),
            }
        )

    try:
        import json

        from src.agents.weekly_newsletter_agent import (
            compose_team_weekly_newsletter,
            persist_newsletter,
        )

        composed = compose_team_weekly_newsletter(team_id, target_date, force_refresh=force_refresh)

        if existing and force_refresh:
            content_json_str = composed.get("content_json") or "{}"
            payload_obj = None
            try:
                payload_obj = json.loads(content_json_str) if isinstance(content_json_str, str) else content_json_str
            except Exception:
                payload_obj = None

            if isinstance(payload_obj, dict):
                try:
                    from src.agents.weekly_newsletter_agent import _render_variants

                    variants = _render_variants(payload_obj, team.name)
                    payload_obj["rendered"] = variants
                    content_json_str = json.dumps(payload_obj, ensure_ascii=False)
                except Exception:
                    pass

            now = datetime.now(UTC)
            if isinstance(payload_obj, dict):
                title = payload_obj.get("title")
                if isinstance(title, str) and title.strip():
                    existing.title = title.strip()
            existing.content = content_json_str
            existing.structured_content = content_json_str
            existing.issue_date = target_date
            existing.week_start_date = composed.get("week_start") or week_start
            existing.week_end_date = composed.get("week_end") or week_end
            existing.generated_date = now
            existing.updated_at = now
            db.session.commit()
            row = existing
        else:
            row = persist_newsletter(
                team_db_id=team_id,
                content_json_str=composed["content_json"],
                week_start=composed["week_start"],
                week_end=composed["week_end"],
                issue_date=target_date,
                newsletter_type="weekly",
            )

        logger.info("Curator %s generated newsletter %d for team %d", g.user_email, row.id, team_id)
        return jsonify(
            {
                "message": "Newsletter generated successfully",
                "newsletter": row.to_dict(),
            }
        )
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.exception("Newsletter generation failed for curator %s, team %d", g.user_email, team_id)
        return jsonify({"error": str(e)}), 500


# =============================================================================
# Tweet CRUD Endpoints
# =============================================================================


def _extract_twitter_handle(url: str) -> str | None:
    """Extract Twitter handle from a tweet URL."""
    match = re.match(r"https?://(?:twitter\.com|x\.com)/([^/]+)/status", url or "")
    return f"@{match.group(1)}" if match else None


@curator_bp.route("/curator/tweets", methods=["GET"])
@require_curator_auth
def curator_list_tweets():
    """List tweets (CommunityTakes with source_type='twitter') for curator's teams.

    Query params:
    - team_id: Filter by team
    - newsletter_id: Filter by newsletter
    - status: Filter by status (default: all)
    - limit: Max results (default 50, max 200)
    - offset: Pagination offset
    """
    team_ids = _get_curator_team_ids()
    if not team_ids:
        return jsonify({"tweets": [], "total": 0})

    filter_team = request.args.get("team_id", type=int)
    if filter_team and filter_team not in team_ids:
        return jsonify({"error": "Not authorized for this team"}), 403

    target_ids = [filter_team] if filter_team else team_ids
    limit = min(request.args.get("limit", 50, type=int), 200)
    offset = request.args.get("offset", 0, type=int)
    status = request.args.get("status")
    newsletter_id = request.args.get("newsletter_id", type=int)

    query = CommunityTake.query.filter(
        CommunityTake.source_type == "twitter",
        CommunityTake.team_id.in_(target_ids),
    )
    if status:
        query = query.filter_by(status=status)
    if newsletter_id:
        query = query.filter_by(newsletter_id=newsletter_id)

    query = query.order_by(CommunityTake.created_at.desc())
    total = query.count()
    tweets = query.offset(offset).limit(limit).all()

    return jsonify(
        {
            "tweets": [t.to_dict() for t in tweets],
            "total": total,
            "limit": limit,
            "offset": offset,
        }
    )


@curator_bp.route("/curator/tweets", methods=["POST"])
@require_curator_auth
def curator_create_tweet():
    """Create a tweet take with attribution.

    Body:
    - content: Required. Tweet text.
    - source_author: Required. Twitter handle (e.g., @username).
    - source_url: Optional. URL to the original tweet.
    - team_id: Required. Must be an approved team.
    - player_id: Optional. API-Football player ID.
    - player_name: Optional. Player name for display.
    - newsletter_id: Optional. Attach to a specific newsletter.
    """
    data = request.get_json() or {}

    content = (data.get("content") or "").strip()
    source_author = (data.get("source_author") or "").strip()
    team_id = data.get("team_id")
    source_url = (data.get("source_url") or "").strip() or None

    if not content:
        return jsonify({"error": "content is required"}), 400
    if not source_author:
        return jsonify({"error": "source_author (Twitter handle) is required"}), 400
    if not team_id:
        return jsonify({"error": "team_id is required"}), 400

    if not _curator_can_access_team(team_id):
        return jsonify({"error": "Not authorized for this team"}), 403

    # Sanitize
    content = sanitize_comment_body(content)
    source_author = sanitize_plain_text(source_author)

    if not content:
        return jsonify({"error": "content contains invalid characters"}), 400

    # Auto-extract handle from URL if not provided as @handle
    if source_url and not source_author.startswith("@"):
        extracted = _extract_twitter_handle(source_url)
        if extracted:
            source_author = extracted

    # Optional fields
    player_id = data.get("player_id")
    player_name = (data.get("player_name") or "").strip() or None
    newsletter_id = data.get("newsletter_id")

    if player_name:
        player_name = sanitize_plain_text(player_name)

    # Validate newsletter belongs to an approved team
    if newsletter_id:
        newsletter = db.session.get(Newsletter, newsletter_id)
        if not newsletter:
            return jsonify({"error": "Newsletter not found"}), 404
        if not _curator_can_access_team(newsletter.team_id):
            return jsonify({"error": "Not authorized for this newsletter's team"}), 403

    take = CommunityTake(
        source_type="twitter",
        source_author=source_author,
        source_url=source_url,
        source_platform="Twitter/X",
        content=content,
        player_id=player_id,
        player_name=player_name,
        team_id=team_id,
        newsletter_id=newsletter_id,
        status="approved",
        curated_by=g.user.id,
        curated_at=datetime.now(UTC),
    )

    db.session.add(take)
    db.session.commit()

    logger.info("Curator %s created tweet take #%d for team %d", g.user_email, take.id, team_id)

    return jsonify(
        {
            "message": "Tweet added successfully",
            "tweet": take.to_dict(),
        }
    ), 201


@curator_bp.route("/curator/tweets/<int:tweet_id>", methods=["PUT"])
@require_curator_auth
def curator_update_tweet(tweet_id):
    """Update a tweet take.

    Body (all optional):
    - content: Tweet text
    - source_author: Twitter handle
    - source_url: Tweet URL
    - player_id: Player association
    - player_name: Player name
    """
    take = db.session.get(CommunityTake, tweet_id)
    if not take:
        return jsonify({"error": "Tweet not found"}), 404
    if take.source_type != "twitter":
        return jsonify({"error": "Not a twitter take"}), 400
    if not take.team_id or not _curator_can_access_team(take.team_id):
        return jsonify({"error": "Not authorized for this team"}), 403

    data = request.get_json() or {}

    if "content" in data:
        content = sanitize_comment_body((data["content"] or "").strip())
        if not content:
            return jsonify({"error": "content cannot be empty"}), 400
        take.content = content

    if "source_author" in data:
        author = sanitize_plain_text((data["source_author"] or "").strip())
        if not author:
            return jsonify({"error": "source_author cannot be empty"}), 400
        take.source_author = author

    if "source_url" in data:
        take.source_url = (data["source_url"] or "").strip() or None

    if "player_id" in data:
        take.player_id = data["player_id"]

    if "player_name" in data:
        name = (data["player_name"] or "").strip()
        take.player_name = sanitize_plain_text(name) if name else None

    take.updated_at = datetime.now(UTC)
    db.session.commit()

    logger.info("Curator %s updated tweet take #%d", g.user_email, tweet_id)

    return jsonify(
        {
            "message": "Tweet updated",
            "tweet": take.to_dict(),
        }
    )


@curator_bp.route("/curator/tweets/<int:tweet_id>", methods=["DELETE"])
@require_curator_auth
def curator_delete_tweet(tweet_id):
    """Delete a tweet take."""
    take = db.session.get(CommunityTake, tweet_id)
    if not take:
        return jsonify({"error": "Tweet not found"}), 404
    if take.source_type != "twitter":
        return jsonify({"error": "Not a twitter take"}), 400
    if not take.team_id or not _curator_can_access_team(take.team_id):
        return jsonify({"error": "Not authorized for this team"}), 403

    db.session.delete(take)
    db.session.commit()

    logger.info("Curator %s deleted tweet take #%d", g.user_email, tweet_id)

    return jsonify({"message": "Tweet deleted"})


# =============================================================================
# Tweet-Newsletter Attachment
# =============================================================================


@curator_bp.route("/curator/tweets/<int:tweet_id>/attach", methods=["POST"])
@require_curator_auth
def curator_attach_tweet(tweet_id):
    """Attach a tweet to a newsletter.

    Body:
    - newsletter_id: Required.
    """
    take = db.session.get(CommunityTake, tweet_id)
    if not take:
        return jsonify({"error": "Tweet not found"}), 404
    if take.source_type != "twitter":
        return jsonify({"error": "Not a twitter take"}), 400
    if not take.team_id or not _curator_can_access_team(take.team_id):
        return jsonify({"error": "Not authorized for this team"}), 403

    data = request.get_json() or {}
    newsletter_id = data.get("newsletter_id")
    if not newsletter_id:
        return jsonify({"error": "newsletter_id is required"}), 400

    newsletter = db.session.get(Newsletter, newsletter_id)
    if not newsletter:
        return jsonify({"error": "Newsletter not found"}), 404
    if not _curator_can_access_team(newsletter.team_id):
        return jsonify({"error": "Not authorized for this newsletter's team"}), 403

    take.newsletter_id = newsletter_id
    take.updated_at = datetime.now(UTC)
    db.session.commit()

    logger.info("Curator %s attached tweet #%d to newsletter #%d", g.user_email, tweet_id, newsletter_id)

    return jsonify(
        {
            "message": "Tweet attached to newsletter",
            "tweet": take.to_dict(),
        }
    )


@curator_bp.route("/curator/tweets/<int:tweet_id>/detach", methods=["POST"])
@require_curator_auth
def curator_detach_tweet(tweet_id):
    """Remove a tweet from its newsletter."""
    take = db.session.get(CommunityTake, tweet_id)
    if not take:
        return jsonify({"error": "Tweet not found"}), 404
    if take.source_type != "twitter":
        return jsonify({"error": "Not a twitter take"}), 400
    if not take.team_id or not _curator_can_access_team(take.team_id):
        return jsonify({"error": "Not authorized for this team"}), 403

    take.newsletter_id = None
    take.updated_at = datetime.now(UTC)
    db.session.commit()

    logger.info("Curator %s detached tweet #%d from newsletter", g.user_email, tweet_id)

    return jsonify(
        {
            "message": "Tweet detached from newsletter",
            "tweet": take.to_dict(),
        }
    )


# =============================================================================
# Players for Curator's Teams
# =============================================================================


@curator_bp.route("/curator/players", methods=["GET"])
@require_curator_auth
def curator_players():
    """List active loaned players for curator's approved teams.

    Query params:
    - team_id: Filter by specific team
    """
    team_ids = _get_curator_team_ids()
    if not team_ids:
        return jsonify({"players": []})

    filter_team = request.args.get("team_id", type=int)
    if filter_team:
        if filter_team not in team_ids:
            return jsonify({"error": "Not authorized for this team"}), 403
        target_ids = [filter_team]
    else:
        target_ids = team_ids

    players = TrackedPlayer.query.filter(
        TrackedPlayer.team_id.in_(target_ids),
        TrackedPlayer.is_active,
    ).all()

    return jsonify(
        {
            "players": [
                {
                    "id": p.id,
                    "player_id": p.player_id,
                    "name": p.name,
                    "team_id": p.team_id,
                    "loan_team": p.loan_team,
                }
                for p in players
            ],
        }
    )
