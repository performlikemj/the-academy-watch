"""Routes for newsletter deadline management"""
from flask import Blueprint, request, jsonify, g
import logging
from src.models.league import Newsletter
from src.routes.api import require_api_key, require_user_auth, _safe_error_payload
from src.services.newsletter_deadline_service import (
    process_newsletter_deadline,
    get_upcoming_deadline_info,
    check_writer_submission_status,
    get_monday_deadline_utc
)

newsletter_deadline_bp = Blueprint('newsletter_deadline', __name__)
logger = logging.getLogger(__name__)


@newsletter_deadline_bp.route('/newsletters/deadline/process', methods=['POST'])
@require_api_key
def process_deadline():
    """Process the newsletter deadline - publish and charge writers who submitted
    
    This should be called automatically at Monday 23:59 GMT via cron job or scheduler.
    Can also be manually triggered by admin for testing.
    """
    try:
        data = request.get_json() or {}
        week_start_date = data.get('week_start_date')  # Optional, for testing specific weeks
        
        result = process_newsletter_deadline(week_start_date)
        
        return jsonify({
            'message': 'Deadline processed',
            'result': result
        })
        
    except Exception as e:
        logger.exception("Error in process_deadline")
        return jsonify(_safe_error_payload(e, 'Failed to process deadline')), 500


@newsletter_deadline_bp.route('/newsletters/deadline/info', methods=['GET'])
def get_deadline_info():
    """Get information about the next newsletter deadline
    
    Returns:
        - Next deadline datetime
        - Time remaining
        - Which week the deadline is for
    """
    try:
        info = get_upcoming_deadline_info()
        return jsonify(info)
        
    except Exception as e:
        logger.exception("Error in get_deadline_info")
        return jsonify(_safe_error_payload(e, 'Failed to get deadline info')), 500


@newsletter_deadline_bp.route('/writers/submission-status', methods=['GET'])
@require_user_auth
def get_my_submission_status():
    """Get submission status for the authenticated writer
    
    Shows:
    - Which newsletters they're assigned to this week
    - Whether they've submitted content for each
    - Time remaining until deadline
    """
    try:
        user = g.user
        
        if not user.is_journalist:
            return jsonify({'error': 'Only journalists can check submission status'}), 403
        
        status = check_writer_submission_status(user.id)
        
        return jsonify(status)
        
    except Exception as e:
        logger.exception("Error in get_my_submission_status")
        return jsonify(_safe_error_payload(e, 'Failed to get submission status')), 500


@newsletter_deadline_bp.route('/writers/<int:journalist_id>/submission-status', methods=['GET'])
@require_api_key
def get_writer_submission_status(journalist_id):
    """Admin endpoint to check any writer's submission status"""
    try:
        week_start_date = request.args.get('week_start_date')
        
        status = check_writer_submission_status(journalist_id, week_start_date)
        
        return jsonify(status)
        
    except Exception as e:
        logger.exception("Error in get_writer_submission_status")
        return jsonify(_safe_error_payload(e, 'Failed to get submission status')), 500


@newsletter_deadline_bp.route('/newsletters/deadline/test', methods=['POST'])
@require_api_key
def test_deadline_processing():
    """Test endpoint to manually trigger deadline processing
    
    Use this for testing the deadline system without waiting for Monday.
    """
    try:
        data = request.get_json() or {}
        
        # Allow specifying a specific week to test
        week_start_date = data.get('week_start_date')
        
        logger.info(f"Testing deadline processing for week: {week_start_date or 'current'}")
        
        result = process_newsletter_deadline(week_start_date)
        
        return jsonify({
            'message': 'Test deadline processing complete',
            'result': result,
            'note': 'This was a test run. In production, this runs automatically at Monday 23:59 GMT'
        })
        
    except Exception as e:
        logger.exception("Error in test_deadline_processing")
        return jsonify(_safe_error_payload(e, 'Failed to test deadline')), 500

