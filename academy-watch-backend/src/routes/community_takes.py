"""Community Takes API endpoints for The Academy Watch.

Handles:
- Public take submissions
- Admin curation workflow (approve/reject)
- Listing approved takes for newsletters
"""
from flask import Blueprint, request, jsonify, g
from src.models.league import (
    db, CommunityTake, QuickTakeSubmission, Team, Newsletter, UserAccount, Player
)
from src.routes.api import require_api_key, require_user_auth
from src.extensions import limiter
from src.utils.sanitize import sanitize_plain_text, sanitize_comment_body
from datetime import datetime, timezone, timedelta
from sqlalchemy import or_
import hashlib
import logging
import re

community_takes_bp = Blueprint('community_takes', __name__)
logger = logging.getLogger(__name__)

# Maximum content length for submissions (characters)
MAX_TAKE_LENGTH = 280

# Rate limits for public submission endpoint
RATE_LIMIT_PER_MINUTE = "10 per minute"
RATE_LIMIT_PER_HOUR = "30 per hour"

# Email validation pattern (basic format check)
EMAIL_PATTERN = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')


def _hash_ip(ip: str) -> str:
    """Hash IP address for spam prevention without storing raw IPs."""
    if not ip:
        return None
    return hashlib.sha256(ip.encode()).hexdigest()


def _get_client_ip() -> str:
    """Get client IP from request, handling proxies."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr


# =============================================================================
# Public Endpoints
# =============================================================================

@community_takes_bp.route('/community-takes', methods=['GET'])
def list_approved_takes():
    """List approved community takes, optionally filtered by player/team/newsletter.

    Query params:
    - player_id: Filter by player API ID
    - team_id: Filter by team DB ID
    - newsletter_id: Filter by newsletter ID
    - limit: Max results (default 20, max 100)
    - offset: Pagination offset
    """
    player_id = request.args.get('player_id', type=int)
    team_id = request.args.get('team_id', type=int)
    newsletter_id = request.args.get('newsletter_id', type=int)
    limit = min(request.args.get('limit', 20, type=int), 100)
    offset = request.args.get('offset', 0, type=int)

    query = CommunityTake.query.filter_by(status='approved')

    if player_id:
        query = query.filter_by(player_id=player_id)
    if team_id:
        query = query.filter_by(team_id=team_id)
    if newsletter_id:
        query = query.filter_by(newsletter_id=newsletter_id)

    query = query.order_by(CommunityTake.created_at.desc())
    total = query.count()
    takes = query.offset(offset).limit(limit).all()

    return jsonify({
        'takes': [t.to_dict() for t in takes],
        'total': total,
        'limit': limit,
        'offset': offset,
    })


@community_takes_bp.route('/community-takes/submit', methods=['POST'])
@limiter.limit(RATE_LIMIT_PER_MINUTE)
@limiter.limit(RATE_LIMIT_PER_HOUR)
def submit_take():
    """Submit a quick take for moderation.

    Body:
    - player_name: Required. Player name
    - player_id: Optional. API-Football player ID
    - team_id: Optional. Team DB ID
    - content: Required. Take content (max 280 chars)
    - submitter_name: Optional. Display name
    - submitter_email: Optional. Email for notifications

    Security measures:
    - Flask-Limiter: 10/min, 30/hour per IP
    - DB rate limit: 5 submissions per IP per hour
    - Input sanitization via bleach
    - Email format validation
    - Duplicate content detection (24h window)
    """
    data = request.get_json() or {}

    # Validate required fields
    player_name = (data.get('player_name') or '').strip()
    content = (data.get('content') or '').strip()

    if not player_name:
        return jsonify({'error': 'player_name is required'}), 400
    if not content:
        return jsonify({'error': 'content is required'}), 400
    if len(content) > MAX_TAKE_LENGTH:
        return jsonify({'error': f'content must be {MAX_TAKE_LENGTH} characters or less'}), 400

    # Sanitize inputs to prevent XSS
    player_name = sanitize_plain_text(player_name)
    content = sanitize_comment_body(content)

    # Re-validate after sanitization (in case input was all HTML)
    if not player_name:
        return jsonify({'error': 'player_name contains invalid content'}), 400
    if not content:
        return jsonify({'error': 'content contains invalid content'}), 400

    # Optional fields with sanitization
    player_id = data.get('player_id')
    team_id = data.get('team_id')
    submitter_name = (data.get('submitter_name') or '').strip() or None
    submitter_email = (data.get('submitter_email') or '').strip() or None

    # Sanitize optional text fields
    if submitter_name:
        submitter_name = sanitize_plain_text(submitter_name)
        if not submitter_name:
            submitter_name = None

    # Validate email format if provided
    if submitter_email:
        if not EMAIL_PATTERN.match(submitter_email):
            return jsonify({'error': 'Invalid email format'}), 400
        # Limit email length
        if len(submitter_email) > 254:
            return jsonify({'error': 'Email address too long'}), 400

    # Validate team exists if provided
    if team_id:
        team = db.session.get(Team, team_id)
        if not team:
            return jsonify({'error': 'Invalid team_id'}), 400

    # Spam prevention: hash IP
    ip_hash = _hash_ip(_get_client_ip())
    user_agent = request.headers.get('User-Agent', '')[:512]

    # Database-level rate limiting: max 5 submissions per IP per hour
    if ip_hash:
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_count = QuickTakeSubmission.query.filter(
            QuickTakeSubmission.ip_hash == ip_hash,
            QuickTakeSubmission.created_at >= one_hour_ago
        ).count()
        if recent_count >= 5:
            logger.warning(f'Rate limit exceeded for IP hash {ip_hash[:16]}...')
            return jsonify({'error': 'Too many submissions. Please try again later.'}), 429

    # Duplicate content detection: prevent exact duplicate submissions within 24 hours
    twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    duplicate = QuickTakeSubmission.query.filter(
        QuickTakeSubmission.content == content,
        QuickTakeSubmission.created_at >= twenty_four_hours_ago
    ).first()
    if duplicate:
        logger.warning(f'Duplicate content detected, original submission #{duplicate.id}')
        return jsonify({'error': 'This take has already been submitted.'}), 400

    submission = QuickTakeSubmission(
        player_name=player_name,
        player_id=player_id,
        team_id=team_id,
        content=content,
        submitter_name=submitter_name,
        submitter_email=submitter_email,
        ip_hash=ip_hash,
        user_agent=user_agent,
        status='pending',
    )

    db.session.add(submission)
    db.session.commit()

    logger.info(f'Quick take submission #{submission.id} created for player: {player_name}')

    return jsonify({
        'message': 'Take submitted successfully. It will be reviewed before publication.',
        'submission_id': submission.id,
    }), 201


# =============================================================================
# Admin Endpoints
# =============================================================================

@community_takes_bp.route('/admin/community-takes', methods=['GET'])
@require_api_key
def admin_list_takes():
    """List community takes for curation (admin only).

    Query params:
    - status: Filter by status (pending, approved, rejected). Default: pending
    - source_type: Filter by source (reddit, twitter, submission, editor)
    - limit: Max results (default 50, max 200)
    - offset: Pagination offset
    """
    status = request.args.get('status', 'pending')
    source_type = request.args.get('source_type')
    limit = min(request.args.get('limit', 50, type=int), 200)
    offset = request.args.get('offset', 0, type=int)

    query = CommunityTake.query

    if status:
        query = query.filter_by(status=status)
    if source_type:
        query = query.filter_by(source_type=source_type)

    query = query.order_by(CommunityTake.created_at.desc())
    total = query.count()
    takes = query.offset(offset).limit(limit).all()

    return jsonify({
        'takes': [t.to_dict() for t in takes],
        'total': total,
        'limit': limit,
        'offset': offset,
    })


@community_takes_bp.route('/admin/community-takes/submissions', methods=['GET'])
@require_api_key
def admin_list_submissions():
    """List quick take submissions for moderation (admin only).

    Query params:
    - status: Filter by status (pending, approved, rejected). Default: pending
    - limit: Max results (default 50, max 200)
    - offset: Pagination offset
    """
    status = request.args.get('status', 'pending')
    limit = min(request.args.get('limit', 50, type=int), 200)
    offset = request.args.get('offset', 0, type=int)

    query = QuickTakeSubmission.query

    if status:
        query = query.filter_by(status=status)

    query = query.order_by(QuickTakeSubmission.created_at.desc())
    total = query.count()
    submissions = query.offset(offset).limit(limit).all()

    return jsonify({
        'submissions': [s.to_dict() for s in submissions],
        'total': total,
        'limit': limit,
        'offset': offset,
    })


@community_takes_bp.route('/admin/community-takes/<int:take_id>/approve', methods=['POST'])
@require_api_key
def admin_approve_take(take_id):
    """Approve a community take (admin only).

    Optional body:
    - newsletter_id: Associate with a specific newsletter
    """
    take = db.session.get(CommunityTake, take_id)
    if not take:
        return jsonify({'error': 'Take not found'}), 404

    if take.status != 'pending':
        return jsonify({'error': f'Take is already {take.status}'}), 400

    data = request.get_json() or {}
    newsletter_id = data.get('newsletter_id')

    if newsletter_id:
        newsletter = db.session.get(Newsletter, newsletter_id)
        if not newsletter:
            return jsonify({'error': 'Invalid newsletter_id'}), 400
        take.newsletter_id = newsletter_id

    take.status = 'approved'
    take.curated_at = datetime.now(timezone.utc)
    # Note: curated_by would require user context from admin token

    db.session.commit()

    logger.info(f'Community take #{take_id} approved')

    return jsonify({
        'message': 'Take approved',
        'take': take.to_dict(),
    })


@community_takes_bp.route('/admin/community-takes/<int:take_id>/reject', methods=['POST'])
@require_api_key
def admin_reject_take(take_id):
    """Reject a community take (admin only).

    Optional body:
    - reason: Rejection reason
    """
    take = db.session.get(CommunityTake, take_id)
    if not take:
        return jsonify({'error': 'Take not found'}), 404

    if take.status != 'pending':
        return jsonify({'error': f'Take is already {take.status}'}), 400

    data = request.get_json() or {}
    reason = (data.get('reason') or '').strip() or None

    take.status = 'rejected'
    take.rejection_reason = reason
    take.curated_at = datetime.now(timezone.utc)

    db.session.commit()

    logger.info(f'Community take #{take_id} rejected')

    return jsonify({
        'message': 'Take rejected',
        'take': take.to_dict(),
    })


@community_takes_bp.route('/admin/community-takes/submissions/<int:submission_id>/approve', methods=['POST'])
@require_api_key
def admin_approve_submission(submission_id):
    """Approve a quick take submission and create a CommunityTake (admin only).

    This creates a new CommunityTake from the submission content.
    """
    submission = db.session.get(QuickTakeSubmission, submission_id)
    if not submission:
        return jsonify({'error': 'Submission not found'}), 404

    if submission.status != 'pending':
        return jsonify({'error': f'Submission is already {submission.status}'}), 400

    # Create CommunityTake from submission
    take = CommunityTake(
        source_type='submission',
        source_author=submission.submitter_name or 'Anonymous',
        content=submission.content,
        player_id=submission.player_id,
        player_name=submission.player_name,
        team_id=submission.team_id,
        status='approved',
        curated_at=datetime.now(timezone.utc),
    )
    db.session.add(take)
    db.session.flush()  # Get the take ID

    # Update submission
    submission.status = 'approved'
    submission.reviewed_at = datetime.now(timezone.utc)
    submission.community_take_id = take.id

    db.session.commit()

    logger.info(f'Submission #{submission_id} approved, created take #{take.id}')

    return jsonify({
        'message': 'Submission approved',
        'submission': submission.to_dict(),
        'take': take.to_dict(),
    })


@community_takes_bp.route('/admin/community-takes/submissions/<int:submission_id>/reject', methods=['POST'])
@require_api_key
def admin_reject_submission(submission_id):
    """Reject a quick take submission (admin only).

    Optional body:
    - reason: Rejection reason
    """
    submission = db.session.get(QuickTakeSubmission, submission_id)
    if not submission:
        return jsonify({'error': 'Submission not found'}), 404

    if submission.status != 'pending':
        return jsonify({'error': f'Submission is already {submission.status}'}), 400

    data = request.get_json() or {}
    reason = (data.get('reason') or '').strip() or None

    submission.status = 'rejected'
    submission.rejection_reason = reason
    submission.reviewed_at = datetime.now(timezone.utc)

    db.session.commit()

    logger.info(f'Submission #{submission_id} rejected')

    return jsonify({
        'message': 'Submission rejected',
        'submission': submission.to_dict(),
    })


@community_takes_bp.route('/admin/community-takes', methods=['POST'])
@require_api_key
def admin_create_take():
    """Create a community take directly (admin/editor only).

    Body:
    - source_type: 'editor' | 'reddit' | 'twitter'
    - source_author: Author name/handle
    - source_url: Optional. Original URL
    - source_platform: Optional. e.g., 'r/reddevils'
    - content: Required. Take content
    - player_id: Optional. API-Football player ID
    - player_name: Optional. Player name for display
    - team_id: Optional. Team DB ID
    - status: Optional. 'pending' or 'approved' (default: approved for editor creates)
    """
    data = request.get_json() or {}

    # Validate required fields
    source_type = (data.get('source_type') or '').strip()
    source_author = (data.get('source_author') or '').strip()
    content = (data.get('content') or '').strip()

    if source_type not in ('editor', 'reddit', 'twitter', 'submission'):
        return jsonify({'error': 'source_type must be editor, reddit, twitter, or submission'}), 400
    if not source_author:
        return jsonify({'error': 'source_author is required'}), 400
    if not content:
        return jsonify({'error': 'content is required'}), 400

    # Optional fields
    source_url = (data.get('source_url') or '').strip() or None
    source_platform = (data.get('source_platform') or '').strip() or None
    player_id = data.get('player_id')
    player_name = (data.get('player_name') or '').strip() or None
    team_id = data.get('team_id')
    status = data.get('status', 'approved')  # Default to approved for admin creates

    if status not in ('pending', 'approved'):
        return jsonify({'error': 'status must be pending or approved'}), 400

    # Validate team exists if provided
    if team_id:
        team = db.session.get(Team, team_id)
        if not team:
            return jsonify({'error': 'Invalid team_id'}), 400

    take = CommunityTake(
        source_type=source_type,
        source_author=source_author,
        source_url=source_url,
        source_platform=source_platform,
        content=content,
        player_id=player_id,
        player_name=player_name,
        team_id=team_id,
        status=status,
        curated_at=datetime.now(timezone.utc) if status == 'approved' else None,
    )

    db.session.add(take)
    db.session.commit()

    logger.info(f'Community take #{take.id} created by admin')

    return jsonify({
        'message': 'Take created',
        'take': take.to_dict(),
    }), 201


@community_takes_bp.route('/admin/community-takes/<int:take_id>', methods=['DELETE'])
@require_api_key
def admin_delete_take(take_id):
    """Delete a community take (admin only)."""
    take = db.session.get(CommunityTake, take_id)
    if not take:
        return jsonify({'error': 'Take not found'}), 404

    db.session.delete(take)
    db.session.commit()

    logger.info(f'Community take #{take_id} deleted')

    return jsonify({'message': 'Take deleted'})


@community_takes_bp.route('/admin/community-takes/stats', methods=['GET'])
@require_api_key
def admin_takes_stats():
    """Get statistics about community takes (admin only)."""
    pending_takes = CommunityTake.query.filter_by(status='pending').count()
    approved_takes = CommunityTake.query.filter_by(status='approved').count()
    rejected_takes = CommunityTake.query.filter_by(status='rejected').count()

    pending_submissions = QuickTakeSubmission.query.filter_by(status='pending').count()
    approved_submissions = QuickTakeSubmission.query.filter_by(status='approved').count()
    rejected_submissions = QuickTakeSubmission.query.filter_by(status='rejected').count()

    return jsonify({
        'takes': {
            'pending': pending_takes,
            'approved': approved_takes,
            'rejected': rejected_takes,
            'total': pending_takes + approved_takes + rejected_takes,
        },
        'submissions': {
            'pending': pending_submissions,
            'approved': approved_submissions,
            'rejected': rejected_submissions,
            'total': pending_submissions + approved_submissions + rejected_submissions,
        },
    })
