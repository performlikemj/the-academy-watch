"""Service for managing newsletter deadlines and auto-publishing"""
import logging
import json
import os
import requests
from datetime import datetime, timezone, timedelta
from flask import render_template
from src.models.league import db, Newsletter, NewsletterCommentary, UserAccount, NewsletterDigestQueue, UserSubscription

logger = logging.getLogger(__name__)


def get_current_week_key() -> str:
    """Get the ISO week key for the current week (e.g., '2025-W48')"""
    now = datetime.now(timezone.utc)
    return f"{now.year}-W{now.isocalendar()[1]:02d}"


def queue_newsletter_for_digest(user_id: int, newsletter_id: int) -> bool:
    """Queue a newsletter to be included in a user's weekly digest
    
    Args:
        user_id: ID of the user
        newsletter_id: ID of the newsletter to queue
        
    Returns:
        bool: True if queued successfully, False if already queued
    """
    try:
        week_key = get_current_week_key()
        
        # Check if already queued
        existing = NewsletterDigestQueue.query.filter_by(
            user_id=user_id,
            newsletter_id=newsletter_id
        ).first()
        
        if existing:
            logger.debug(f"Newsletter {newsletter_id} already queued for user {user_id}")
            return False
        
        queue_entry = NewsletterDigestQueue(
            user_id=user_id,
            newsletter_id=newsletter_id,
            week_key=week_key,
            queued_at=datetime.now(timezone.utc),
            sent=False
        )
        db.session.add(queue_entry)
        db.session.commit()
        
        logger.info(f"Queued newsletter {newsletter_id} for user {user_id} digest (week {week_key})")
        return True
        
    except Exception as e:
        logger.exception(f"Error queueing newsletter {newsletter_id} for user {user_id}")
        db.session.rollback()
        return False


def send_digest_emails(week_key: str = None) -> dict:
    """Send weekly digest emails to all users who have digest preference
    
    Args:
        week_key: Optional week key to process (defaults to current week)
        
    Returns:
        dict: Results of the digest sending
    """
    try:
        if not week_key:
            week_key = get_current_week_key()
        
        logger.info(f"Processing digest emails for week {week_key}")
        
        # Get all unsent queued items for this week, grouped by user
        from sqlalchemy import func
        
        # Find users with pending digest items
        users_with_pending = db.session.query(
            NewsletterDigestQueue.user_id
        ).filter(
            NewsletterDigestQueue.week_key == week_key,
            NewsletterDigestQueue.sent == False
        ).distinct().all()
        
        user_ids = [u[0] for u in users_with_pending]
        
        if not user_ids:
            logger.info(f"No pending digest items for week {week_key}")
            return {
                'success': True,
                'digests_sent': 0,
                'message': 'No pending digests'
            }
        
        results = {
            'success': True,
            'digests_sent': 0,
            'newsletters_included': 0,
            'errors': []
        }
        
        for user_id in user_ids:
            try:
                result = _send_single_digest(user_id, week_key)
                if result.get('success'):
                    results['digests_sent'] += 1
                    results['newsletters_included'] += result.get('newsletter_count', 0)
                else:
                    results['errors'].append({
                        'user_id': user_id,
                        'error': result.get('error')
                    })
            except Exception as e:
                logger.exception(f"Error sending digest to user {user_id}")
                results['errors'].append({
                    'user_id': user_id,
                    'error': str(e)
                })
        
        logger.info(f"Digest processing complete: {results['digests_sent']} sent, {len(results['errors'])} errors")
        return results
        
    except Exception as e:
        logger.exception("Error in send_digest_emails")
        return {
            'success': False,
            'error': str(e)
        }


def _send_single_digest(user_id: int, week_key: str) -> dict:
    """Send a digest email to a single user
    
    Args:
        user_id: ID of the user
        week_key: Week key for the digest
        
    Returns:
        dict: Result of sending
    """
    try:
        user = UserAccount.query.get(user_id)
        if not user or not user.email:
            return {'success': False, 'error': 'User not found or no email'}
        
        # Get all pending newsletters for this user's digest
        queue_entries = NewsletterDigestQueue.query.filter_by(
            user_id=user_id,
            week_key=week_key,
            sent=False
        ).all()
        
        if not queue_entries:
            return {'success': False, 'error': 'No pending newsletters'}
        
        newsletter_ids = [q.newsletter_id for q in queue_entries]
        newsletters = Newsletter.query.filter(Newsletter.id.in_(newsletter_ids)).all()
        
        if not newsletters:
            return {'success': False, 'error': 'No newsletters found'}
        
        # Build newsletter data for template
        newsletter_data = []
        for n in newsletters:
            # Parse newsletter content
            content = {}
            try:
                from src.routes.api import _load_newsletter_json
                content = _load_newsletter_json(n) or {}
            except Exception:
                content = {}
            if not content and n.content:
                try:
                    content = json.loads(n.content) if isinstance(n.content, str) else (n.content or {})
                except Exception:
                    content = {}
            
            team_logo = content.get('team_logo')
            if not team_logo and n.team:
                team_logo = getattr(n.team, 'logo', None)
            
            # Get web URL
            from src.routes.api import _newsletter_issue_slug, _absolute_url
            slug = _newsletter_issue_slug(n)
            web_url = _absolute_url(f'/newsletters/{slug}')
            
            newsletter_data.append({
                'id': n.id,
                'title': content.get('title') or n.title,
                'summary': content.get('summary'),
                'highlights': content.get('highlights', []),
                'team_name': n.team.name if n.team else None,
                'team_logo': team_logo,
                'journalist_name': None,  # Could be enriched if needed
                'web_url': web_url,
            })
        
        # Calculate week range
        now = datetime.now(timezone.utc)
        week_start = now - timedelta(days=now.weekday())
        week_end = week_start + timedelta(days=6)
        week_range = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d, %Y')}"
        
        # Get manage URL and unsubscribe URLs
        public_base = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
        manage_url = f"{public_base}/subscriptions" if public_base else None
        
        # Get an unsubscribe token from one of the user's active subscriptions
        # For digest, we use the subscription management page as the primary unsubscribe mechanism
        unsubscribe_url = manage_url  # Default to manage page
        one_click_url = None
        email_headers = {}
        
        # Try to get a specific subscription token for one-click unsubscribe
        active_sub = UserSubscription.query.filter_by(
            email=user.email, active=True
        ).first()
        
        if active_sub and active_sub.unsubscribe_token and public_base:
            token = active_sub.unsubscribe_token
            unsubscribe_url = f"{public_base}/subscriptions/unsubscribe/{token}"
            one_click_url = f"{public_base}/api/subscriptions/one-click-unsubscribe/{token}"
            
            # Build RFC 8058 compliant headers
            email_headers = {
                'List-Unsubscribe': f'<{unsubscribe_url}>',
                'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
            }
        
        # Render the digest template
        html = render_template(
            'newsletter_digest_email.html',
            newsletters=newsletter_data,
            newsletter_count=len(newsletter_data),
            week_range=week_range,
            manage_url=manage_url,
            bmc_button_url='https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png',
        )
        
        # Build plain text version
        text_lines = [
            "Your Weekly The Academy Watch Digest",
            f"Week: {week_range}",
            "",
            f"This digest contains {len(newsletter_data)} newsletter(s):",
            "",
        ]
        for nd in newsletter_data:
            text_lines.append(f"- {nd['title']}")
            if nd.get('team_name'):
                text_lines.append(f"  Team: {nd['team_name']}")
            if nd.get('web_url'):
                text_lines.append(f"  Read more: {nd['web_url']}")
            text_lines.append("")
        
        if unsubscribe_url:
            text_lines.append(f"\nManage your subscriptions: {unsubscribe_url}")
        
        text = "\n".join(text_lines)
        
        # Send via webhook
        webhook_url = os.getenv('N8N_EMAIL_WEBHOOK_URL')
        if not webhook_url:
            logger.warning("N8N_EMAIL_WEBHOOK_URL not configured, cannot send digest")
            return {'success': False, 'error': 'Email webhook not configured'}
        
        request_headers = {'Content-Type': 'application/json'}
        bearer = os.getenv('N8N_EMAIL_AUTH_BEARER')
        if bearer:
            request_headers['Authorization'] = f'Bearer {bearer}'
        
        payload = {
            'email': user.email,
            'subject': f"Your Weekly Academy Watch Digest ({week_range})",
            'html': html,
            'text': text,
            'headers': email_headers,  # RFC 8058 List-Unsubscribe headers
            'meta': {
                'digest': True,
                'week_key': week_key,
                'newsletter_count': len(newsletter_data),
                'unsubscribe_url': unsubscribe_url,
                'one_click_unsubscribe_url': one_click_url,
            }
        }
        
        try:
            response = requests.post(
                webhook_url,
                headers=request_headers,
                json=payload,
                timeout=20
            )
            
            if response.ok:
                # Mark all queue entries as sent
                now = datetime.now(timezone.utc)
                for entry in queue_entries:
                    entry.sent = True
                    entry.sent_at = now
                db.session.commit()
                
                logger.info(f"Sent digest to {user.email} with {len(newsletter_data)} newsletters")
                return {
                    'success': True,
                    'newsletter_count': len(newsletter_data),
                    'email': user.email
                }
            else:
                logger.error(f"Digest webhook failed: {response.status_code} - {response.text[:500]}")
                return {
                    'success': False,
                    'error': f"Webhook returned {response.status_code}"
                }
                
        except requests.RequestException as e:
            logger.exception(f"Error sending digest webhook to {user.email}")
            return {'success': False, 'error': str(e)}
        
    except Exception as e:
        logger.exception(f"Error in _send_single_digest for user {user_id}")
        db.session.rollback()
        return {'success': False, 'error': str(e)}


def get_monday_deadline_utc():
    """Get the next Monday 23:59 GMT deadline
    
    Returns:
        datetime: Next Monday at 23:59:59 UTC/GMT
    """
    now = datetime.now(timezone.utc)
    
    # Find next Monday (weekday 0 = Monday)
    days_until_monday = (7 - now.weekday()) % 7
    if days_until_monday == 0 and now.hour >= 23:
        # Already past Monday deadline, go to next Monday
        days_until_monday = 7
    
    next_monday = now + timedelta(days=days_until_monday)
    
    # Set to 23:59:59 GMT
    deadline = next_monday.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    return deadline


def check_writer_has_publishable_content(newsletter_id: int, journalist_id: int) -> bool:
    """Check if a writer has submitted publishable content for a newsletter
    
    Args:
        newsletter_id: ID of the newsletter
        journalist_id: ID of the journalist
        
    Returns:
        bool: True if writer has publishable content, False otherwise
    """
    commentary = NewsletterCommentary.query.filter_by(
        newsletter_id=newsletter_id,
        author_id=journalist_id
    ).first()
    
    if not commentary:
        return False
    
    # Check content exists and is substantial (at least 50 characters)
    if not commentary.content or len(commentary.content.strip()) < 50:
        return False
    
    return True


def process_newsletter_deadline(week_start_date=None):
    """Process newsletter deadline - publish and charge for writers who submitted content
    
    This should be run at Monday 23:59 GMT to:
    1. Find newsletters for the current week
    2. Check which writers submitted content
    3. Publish the newsletter
    4. Record usage (charge) only for writers who submitted
    5. Send emails to subscribers
    
    Args:
        week_start_date: Optional date for the week start (for testing)
        
    Returns:
        dict: Summary of processing results
    """
    try:
        now = datetime.now(timezone.utc)
        
        # Determine which week we're processing
        if week_start_date:
            target_date = week_start_date
        else:
            # Use the Monday that just ended (current week)
            days_since_monday = now.weekday()
            target_date = (now - timedelta(days=days_since_monday)).date()
        
        logger.info(f"Processing newsletter deadline for week starting {target_date}")
        
        # Find all newsletters for this week that aren't published yet
        newsletters = Newsletter.query.filter(
            Newsletter.week_start_date == target_date,
            Newsletter.published == False
        ).all()
        
        if not newsletters:
            logger.info(f"No unpublished newsletters found for week {target_date}")
            return {
                'success': True,
                'message': 'No newsletters to process',
                'newsletters_processed': 0
            }
        
        results = {
            'newsletters_processed': 0,
            'writers_contributed': 0,
            'details': []
        }

        for newsletter in newsletters:
            newsletter_result = process_single_newsletter_deadline(newsletter)
            results['newsletters_processed'] += 1
            results['writers_contributed'] += newsletter_result.get('writers_contributed', 0)
            results['details'].append({
                'newsletter_id': newsletter.id,
                'team_id': newsletter.team_id,
                **newsletter_result
            })
        
        logger.info(f"Deadline processing complete: {results}")
        return results
        
    except Exception as e:
        logger.exception("Error processing newsletter deadline")
        return {
            'success': False,
            'error': str(e)
        }


def process_single_newsletter_deadline(newsletter: Newsletter) -> dict:
    """Process deadline for a single newsletter
    
    Args:
        newsletter: Newsletter object to process
        
    Returns:
        dict: Processing results
    """
    try:
        # Find all commentaries for this newsletter
        commentaries = NewsletterCommentary.query.filter_by(
            newsletter_id=newsletter.id
        ).all()
        
        writers_with_content = []
        writers_without_content = []
        
        # Check which writers have publishable content
        for commentary in commentaries:
            if commentary.author and commentary.author.is_journalist:
                has_content = check_writer_has_publishable_content(
                    newsletter.id,
                    commentary.author.id
                )
                
                if has_content:
                    writers_with_content.append(commentary.author)
                else:
                    writers_without_content.append(commentary.author)
        
        # Only publish if at least one writer has content
        if not writers_with_content:
            logger.info(
                f"Newsletter {newsletter.id} has no publishable content, skipping"
            )
            return {
                'published': False,
                'writers_charged': 0,
                'subscribers_notified': 0,
                'reason': 'No publishable content'
            }
        
        # Publish the newsletter
        newsletter.published = True
        newsletter.published_date = datetime.now(timezone.utc)
        db.session.commit()
        
        logger.info(
            f"Published newsletter {newsletter.id} with content from "
            f"{len(writers_with_content)} writers"
        )

        # Log contributing writers
        for writer in writers_with_content:
            logger.info(f"Writer {writer.display_name} contributed to newsletter {newsletter.id}")

        # Log writers who didn't submit
        for writer in writers_without_content:
            logger.info(
                f"Writer {writer.display_name} did not submit content for "
                f"newsletter {newsletter.id}"
            )
        
        # TODO: Send emails to subscribers
        # This would integrate with your existing email system

        return {
            'published': True,
            'writers_contributed': len(writers_with_content),
            'writers_without_content': len(writers_without_content),
            'writer_names': [w.display_name for w in writers_with_content]
        }
        
    except Exception as e:
        logger.exception(f"Error processing newsletter {newsletter.id}")
        return {
            'published': False,
            'error': str(e)
        }


def get_upcoming_deadline_info() -> dict:
    """Get information about the next deadline
    
    Returns:
        dict: Information about next deadline
    """
    next_deadline = get_monday_deadline_utc()
    now = datetime.now(timezone.utc)
    time_remaining = next_deadline - now
    
    # Calculate week this deadline is for
    days_until_monday = (7 - now.weekday()) % 7
    if days_until_monday == 0 and now.hour >= 23:
        week_start = now + timedelta(days=7)
    else:
        week_start = now + timedelta(days=days_until_monday)
    
    week_start_date = week_start.date()
    
    return {
        'next_deadline': next_deadline.isoformat(),
        'time_remaining_hours': time_remaining.total_seconds() / 3600,
        'time_remaining_formatted': format_time_remaining(time_remaining),
        'week_start_date': week_start_date.isoformat(),
        'current_time_utc': now.isoformat()
    }


def format_time_remaining(timedelta_obj) -> str:
    """Format time remaining in human-readable format
    
    Args:
        timedelta_obj: Time delta object
        
    Returns:
        str: Formatted string like "2 days, 5 hours"
    """
    total_seconds = int(timedelta_obj.total_seconds())
    
    if total_seconds < 0:
        return "Deadline passed"
    
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    
    parts = []
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    if hours > 0:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if not parts and minutes > 0:
        parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    
    return ", ".join(parts) if parts else "Less than 1 minute"


def check_writer_submission_status(journalist_id: int, week_start_date=None) -> dict:
    """Check if a writer has submitted content for the current/specified week
    
    Args:
        journalist_id: ID of the journalist
        week_start_date: Optional specific week to check (defaults to current week)
        
    Returns:
        dict: Submission status information
    """
    try:
        journalist = UserAccount.query.get(journalist_id)
        if not journalist or not journalist.is_journalist:
            return {'error': 'Invalid journalist'}
        
        # Determine which week to check
        if week_start_date:
            target_date = week_start_date
        else:
            now = datetime.now(timezone.utc)
            days_since_monday = now.weekday()
            target_date = (now - timedelta(days=days_since_monday)).date()
        
        # Find newsletters for this week
        # Assuming writer is assigned to specific teams
        from src.models.league import JournalistTeamAssignment
        
        assigned_teams = JournalistTeamAssignment.query.filter_by(
            user_id=journalist_id
        ).all()
        
        team_ids = [assignment.team_id for assignment in assigned_teams]
        
        newsletters = Newsletter.query.filter(
            Newsletter.team_id.in_(team_ids),
            Newsletter.week_start_date == target_date
        ).all()
        
        submission_status = []
        
        for newsletter in newsletters:
            has_content = check_writer_has_publishable_content(
                newsletter.id,
                journalist_id
            )
            
            submission_status.append({
                'newsletter_id': newsletter.id,
                'team_id': newsletter.team_id,
                'has_submitted': has_content,
                'published': newsletter.published
            })
        
        deadline_info = get_upcoming_deadline_info()
        
        return {
            'journalist_id': journalist_id,
            'journalist_name': journalist.display_name,
            'week_start_date': target_date.isoformat(),
            'newsletters': submission_status,
            'deadline': deadline_info,
            'all_submitted': all(n['has_submitted'] for n in submission_status)
        }
        
    except Exception as e:
        logger.exception(f"Error checking writer submission status")
        return {'error': str(e)}
