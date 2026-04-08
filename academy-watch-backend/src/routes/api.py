from flask import Blueprint, request, jsonify, make_response, render_template, Response, current_app, g, send_file
from src.models.league import db, League, Team, Newsletter, UserSubscription, EmailToken, PlayerFlag, FLAG_CATEGORIES, FLAG_STATUSES, AdminSetting, NewsletterComment, UserAccount, NewsletterPlayerYoutubeLink, NewsletterCommentary, Player, JournalistTeamAssignment, CommentaryApplause, TeamTrackingRequest, StripeSubscription, NewsletterDigestQueue, JournalistSubscription, BackgroundJob, TeamSubreddit, RedditPost, TeamAlias, ManualPlayerSubmission, CommunityTake, AcademyAppearance, PlayerComment, PlayerLink, _as_utc
from src.models.tracked_player import TrackedPlayer
from src.models.sponsor import Sponsor
from src.api_football_client import APIFootballClient
from src.admin.sandbox_tasks import (
    SandboxContext,
    TaskExecutionError,
    TaskNotFoundError,
    TaskValidationError,
    list_tasks as sandbox_list_tasks,
    run_task as sandbox_run_task,
)
from datetime import datetime, date, timedelta, timezone
import uuid
import json
import logging
import csv
import io
import math
import re
import os
import shutil
from io import BytesIO
from functools import wraps
from uuid import uuid4
from sqlalchemy import or_, func
import time
from datetime import timedelta
from typing import Any
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import secrets
import base64
import string
import requests
from src.extensions import limiter
from src.utils.sanitize import sanitize_comment_body, sanitize_plain_text, sanitize_commentary_html
from src.agents.errors import NoActiveLoaneesError
from src.models.tracked_player import TrackedPlayer
from src.utils.slug import resolve_team_by_identifier, generate_unique_team_slug
from src.utils.academy_classifier import classify_tracked_player, flatten_transfers, is_same_club, _get_latest_season
from src.utils.newsletter_slug import compose_newsletter_public_slug
from src.services.email_service import email_service
import threading

# Import auth utilities from the extracted auth module
from src.auth import (
    require_api_key,
    require_user_auth,
    issue_user_token,
    _user_serializer,
    _get_authorized_email,
    _admin_email_list,
    _ensure_user_account,
    _generate_default_display_name,
    _normalize_display_name,
    _make_display_name_unique,
    get_client_ip,
    ALLOWED_ADMIN_IPS,
    _safe_error_payload,
    _is_production,
)
from src.utils.background_jobs import (
    create_background_job as _create_background_job,
    update_job as _update_job,
    get_job as _get_job,
    STALE_JOB_TIMEOUT,
)

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

# Background job functions (_create_background_job, _update_job, _get_job) are imported from src.utils.background_jobs


class LazyAPIFootballClient:
    """Instantiate APIFootballClient only when first touched to avoid early network calls."""

    def __init__(self, factory):
        self._factory = factory
        self._instance = None

    def _resolve(self):
        if self._instance is None:
            self._instance = self._factory()
        return self._instance

    def __getattr__(self, item: str):
        return getattr(self._resolve(), item)

    def __repr__(self) -> str:
        state = "initialized" if self._instance is not None else "uninitialized"
        return f"<LazyAPIFootballClient {state}>"


# Initialize API-Football client lazily to keep migrations/test tools offline-friendly
api_client = LazyAPIFootballClient(APIFootballClient)

SUBSCRIPTIONS_REQUIRE_VERIFY = os.getenv('SUBSCRIPTIONS_REQUIRE_VERIFY', '1').lower() in ('1', 'true', 'yes', 'on')
try:
    SUBSCRIPTIONS_VERIFY_TTL_MINUTES = int(os.getenv('SUBSCRIPTIONS_VERIFY_TTL_MINUTES') or 60 * 24)
except Exception:
    SUBSCRIPTIONS_VERIFY_TTL_MINUTES = 60 * 24


# require_api_key, require_user_auth, and other auth utilities are imported from src.auth

# CORS support - only add headers not already set by Flask-CORS
# Do NOT override Access-Control-Allow-Origin (Flask-CORS in main.py handles this based on CORS_ALLOW_ORIGINS)
@api_bp.after_request
def after_request(response):
    if 'Access-Control-Allow-Headers' not in response.headers:
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization,X-API-Key,X-Admin-Key')
    if 'Access-Control-Allow-Methods' not in response.headers:
        response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response


@api_bp.route('/admin/auth-check', methods=['GET'])
@require_api_key
def admin_auth_check():
    """Lightweight endpoint to verify admin credentials from the client UI."""
    return jsonify({
        'status': 'ok',
        'user': getattr(g, 'user_email', None),
    })


@api_bp.route('/admin/sandbox', methods=['GET'])
@require_api_key
def admin_sandbox_home():
    """Render the admin sandbox interface with available diagnostic tasks."""
    teams = Team.query.order_by(Team.name.asc()).all()
    logger.info("[admin-sandbox] fetched %d teams (pre-dedupe) for dropdown", len(teams))
    # Deduplicate by lowercase name, keep the latest id
    dedup: dict[str, Team] = {}
    for t in teams:
        key = (t.name or '').strip().lower()
        if key:
            dedup[key] = t
    teams = sorted(dedup.values(), key=lambda t: (t.name or '').lower())
    logger.info("[admin-sandbox] teams after dedupe: %d", len(teams))
    if not teams:
        logger.warning("[admin-sandbox] no teams found in database")
    else:
        sample = ", ".join(f"{team.name}#{team.team_id}" for team in teams[:5])
        logger.debug("[admin-sandbox] sample teams: %s", sample)

    team_options = [
        {
            'label': f"{team.name} (API #{team.team_id})",
            'value': team.name,
            'team_id': team.team_id,
            'team_db_id': team.id,
        }
        for team in teams
    ]

    tasks = [
        {
            'task_id': task.task_id,
            'label': task.label,
            'description': task.description,
            'parameters': [
                {
                    **param,
                    'options': team_options if param.get('name') == 'team_name' else param.get('options'),
                }
                for param in task.parameters
            ],
        }
        for task in sandbox_list_tasks()
    ]
    accept_json = request.accept_mimetypes['application/json']
    accept_html = request.accept_mimetypes['text/html']
    wants_json = (
        request.args.get('format') == 'json'
        or (accept_json > accept_html and accept_json > 0)
    )
    if wants_json:
        return jsonify({'tasks': tasks})
    return render_template('admin_sandbox.html', tasks=tasks)


@api_bp.route('/admin/sandbox/run/<task_id>', methods=['POST'])
@require_api_key
def admin_sandbox_run(task_id: str):
    """Execute a sandbox diagnostic task and return the structured result."""

    payload = request.get_json(silent=True) or {}
    context = SandboxContext(db_session=db.session, api_client=api_client)

    try:
        result = sandbox_run_task(task_id, payload, context)
    except TaskNotFoundError as exc:
        return (
            jsonify({'status': 'error', 'summary': str(exc), 'payload': {}, 'task_id': task_id}),
            404,
        )
    except TaskValidationError as exc:
        return (
            jsonify({'status': 'error', 'summary': str(exc), 'payload': {}, 'task_id': task_id}),
            400,
        )
    except TaskExecutionError as exc:
        return (
            jsonify({'status': 'error', 'summary': str(exc), 'payload': {}, 'task_id': task_id}),
            500,
        )

    return jsonify(result)


@api_bp.route('/admin/users', methods=['GET'])
@require_api_key
def admin_get_users():
    """Get all users with their subscriptions and assignments."""
    try:
        users = UserAccount.query.order_by(UserAccount.created_at.desc()).all()
        result = []
        for user in users:
            # Get subscriptions (teams they follow)
            # Note: UserSubscription links by email, not user_id
            subscriptions = UserSubscription.query.filter_by(email=user.email, active=True).all()
            following = []
            for sub in subscriptions:
                if sub.team:
                    following.append({
                        'team_id': sub.team.team_id,
                        'name': sub.team.name
                    })
            
            # Get assignments (teams they report on)
            assignments = JournalistTeamAssignment.query.filter_by(user_id=user.id).all()
            reporting = []
            for assign in assignments:
                if assign.team:
                    reporting.append({
                        'team_id': assign.team.team_id,
                        'name': assign.team.name
                    })
            
            user_data = user.to_dict()
            user_data['following'] = following
            user_data['reporting'] = reporting
            result.append(user_data)
            
        return jsonify(result)
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'Failed to fetch users')), 500


@api_bp.route('/admin/users/<int:user_id>/role', methods=['POST'])
@require_api_key
def admin_toggle_user_role(user_id):
    """Toggle user role (specifically journalist status)."""
    try:
        data = request.get_json() or {}
        is_journalist = data.get('is_journalist')
        
        if is_journalist is None:
            return jsonify({'error': 'is_journalist boolean is required'}), 400
            
        user = UserAccount.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
            
        user.is_journalist = bool(is_journalist)
        # If becoming a journalist, ensure they can author commentary
        if user.is_journalist:
            user.can_author_commentary = True
            
        db.session.commit()
        
        return jsonify({
            'message': f"User role updated. Journalist: {user.is_journalist}",
            'user': user.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to update user role')), 500


@api_bp.route('/admin/users/<int:user_id>/editor-role', methods=['POST'])
@require_api_key
def admin_toggle_editor_role(user_id):
    """Toggle user's editor status (can manage external writers)."""
    try:
        data = request.get_json() or {}
        is_editor = data.get('is_editor')

        if is_editor is None:
            return jsonify({'error': 'is_editor boolean is required'}), 400

        user = UserAccount.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        user.is_editor = bool(is_editor)
        user.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        return jsonify({
            'message': f"Editor status {'granted' if is_editor else 'revoked'}",
            'user': user.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to update editor role')), 500


@api_bp.route('/admin/users/<int:user_id>/curator-role', methods=['POST'])
@require_api_key
def admin_toggle_curator_role(user_id):
    """Toggle user's curator status (can add tweets/attributions to newsletters)."""
    try:
        data = request.get_json() or {}
        is_curator = data.get('is_curator')

        if is_curator is None:
            return jsonify({'error': 'is_curator boolean is required'}), 400

        user = UserAccount.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404

        user.is_curator = bool(is_curator)
        user.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        return jsonify({
            'message': f"Curator status {'granted' if is_curator else 'revoked'}",
            'user': user.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to update curator role')), 500


@api_bp.route('/admin/curator-token', methods=['POST'])
@require_api_key
def admin_issue_curator_token():
    """Issue a Bearer token for a curator user (admin convenience endpoint).

    Creates/looks up the user account and ensures is_curator=True,
    then returns a signed 30-day token the curator can use with the API.

    Body:
    - email: Required. Curator's email address.
    """
    data = request.get_json() or {}
    email = (data.get('email') or '').strip().lower()
    if not email:
        return jsonify({'error': 'email is required'}), 400

    try:
        user = _ensure_user_account(email)
        user.is_curator = True
        db.session.commit()

        token_data = issue_user_token(email, role='user')
        logger.info("Admin issued curator token for %s (user_id=%d)", email, user.id)
        return jsonify({
            'token': token_data['token'],
            'expires_in': token_data['expires_in'],
            'email': email,
            'user_id': user.id,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to issue curator token')), 500


# Auth utilities (_user_serializer, _ensure_user_account, issue_user_token, require_user_auth,
# _get_authorized_email, _is_production, _safe_error_payload, display name helpers) are imported from src.auth
# _send_login_code is now in auth_routes.py


def _send_email_via_webhook(
    *,
    email: str,
    subject: str,
    text: str,
    html: str | None = None,
    meta: dict | None = None,
    http_method_override: str | None = None,
) -> dict:
    """Send email via email service (Mailgun/SMTP).
    
    This function maintains backward compatibility with the old n8n webhook interface.
    The meta and http_method_override parameters are ignored but kept for compatibility.
    """
    if not email_service.is_configured():
        raise RuntimeError('Email service is not configured (set MAILGUN_* or SMTP_* env vars)')

    # Extract tags from meta if present
    tags = None
    if meta and 'kind' in meta:
        tags = [meta['kind']]

    try:
        result = email_service.send_email(
            to=email,
            subject=subject,
            html=html or text,
            text=text,
            tags=tags,
        )
        return {
            'status': 'ok' if result.success else 'error',
            'http_status': result.http_status or (200 if result.success else 500),
            'response_text': result.message_id or result.error or '',
            'provider': result.provider,
        }
    except Exception as exc:
        logger.exception('Failed to send email to %s', email)
        raise RuntimeError(f'Email delivery failed: {exc}') from exc


def _send_subscription_verification_email(email: str, team_names: list[str], token: str) -> dict:
    public_base = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    confirm_path = f"/verify?token={token}"
    confirm_url = f"{public_base}{confirm_path}" if public_base else confirm_path

    subject = f"Confirm your newsletter subscription"

    team_lines_html = ''.join(f'<li>{name}</li>' for name in team_names)
    team_lines_text = '\n'.join(f" • {name}" for name in team_names)

    html = f"""
    <p>Thanks for subscribing to The Academy Watch newsletters.</p>
    <p>Please confirm your email address to start receiving weekly updates.</p>
    <p><a href="{confirm_url}">Confirm subscription</a></p>
    <p>You requested updates for:</p>
    <ul>{team_lines_html}</ul>
    <p>If you did not make this request, you can ignore this message.</p>
    """
    text = (
        "Thanks for subscribing to The Academy Watch newsletters.\n\n"
        "Confirm your email address to start receiving updates:\n"
        f"{confirm_url}\n\n"
        "You requested updates for:\n"
        f"{team_lines_text}\n\n"
        "If you did not make this request, you can ignore this message."
    )

    meta = {
        'kind': 'subscription_verification',
        'team_count': len(team_names),
    }
    return _send_email_via_webhook(email=email, subject=subject, text=text, html=html, meta=meta)


def _send_waitlist_welcome_email(email: str, team_names: list[str]) -> dict:
    """Send a welcome email for teams that don't have active newsletters yet."""
    subject = "Thanks for your interest in The Academy Watch newsletters"
    
    team_lines_html = ''.join(f'<li>{name}</li>' for name in team_names)
    team_lines_text = '\n'.join(f" • {name}" for name in team_names)
    
    html = f"""
    <p>Thanks for subscribing to The Academy Watch newsletters!</p>
    <p>You've subscribed to the following team(s):</p>
    <ul>{team_lines_html}</ul>
    <p><strong>Important:</strong> We're not currently generating newsletters for {'this team' if len(team_names) == 1 else 'these teams'} yet. 
    Newsletter generation is resource-intensive, and we only activate it once a team has sufficient subscriber interest.</p>
    <p>We'll notify you via email once we start creating newsletters for your selected team(s). 
    In the meantime, thank you for your patience and support!</p>
    <p>If you have any questions, feel free to reach out.</p>
    """
    
    text = (
        "Thanks for subscribing to The Academy Watch newsletters!\n\n"
        "You've subscribed to:\n"
        f"{team_lines_text}\n\n"
        f"Important: We're not currently generating newsletters for {'this team' if len(team_names) == 1 else 'these teams'} yet. "
        "Newsletter generation is resource-intensive, and we only activate it once a team has sufficient subscriber interest.\n\n"
        "We'll notify you via email once we start creating newsletters for your selected team(s). "
        "In the meantime, thank you for your patience and support!"
    )
    
    meta = {
        'kind': 'waitlist_welcome',
        'team_count': len(team_names),
    }
    return _send_email_via_webhook(email=email, subject=subject, text=text, html=html, meta=meta)


@api_bp.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint."""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'api_version': '1.3.0',
        'features': {
            'transfer_windows': True,
            'window_key_support': True,
            'backward_compatibility': True,
            'team_name_resolution': True,
            'enhanced_loan_detection': True,
            'outbound_loan_sweep': True,
            'csv_table_split': True
        }
    })

@api_bp.route('/sync-status', methods=['GET'])
def public_sync_status():
    """Public endpoint: returns whether a major background sync is running."""
    STALE_THRESHOLD = STALE_JOB_TIMEOUT
    MAJOR_JOB_TYPES = ('full_rebuild', 'seed_big6')
    now = datetime.now(timezone.utc)

    running = BackgroundJob.query.filter(
        BackgroundJob.status == 'running',
        BackgroundJob.job_type.in_(MAJOR_JOB_TYPES),
    ).all()

    syncing = False
    for job in running:
        last_active = job.updated_at or job.started_at or job.created_at
        if last_active:
            elapsed = now - last_active.replace(tzinfo=timezone.utc)
            if elapsed > STALE_THRESHOLD:
                job.status = 'failed'
                job.error = f'Stale job auto-failed (no update in {elapsed}).'
                job.completed_at = now
                db.session.commit()
                continue
        syncing = True

    payload = {'syncing': syncing}
    if syncing:
        payload['message'] = "We're currently updating player data. Some information may be temporarily unavailable."
        # Find the most recently updated active job for progress info
        active = [j for j in running if j.status == 'running']
        if active:
            job = max(active, key=lambda j: j.updated_at or j.created_at)
            payload['stage'] = job.current_player
            payload['progress'] = job.progress
            payload['total'] = job.total
        # Include tracked team logos for the public banner animation
        tracked = Team.query.filter_by(is_tracked=True).all()
        payload['teams'] = [
            {'name': t.name, 'logo': t.logo, 'team_id': t.team_id}
            for t in tracked if t.logo
        ]
    return jsonify(payload)


@api_bp.route('/options', methods=['OPTIONS'])
def handle_options():
    return '', 200

# Auth endpoints (/auth/request-code, /auth/me, /auth/verify-code, /auth/display-name, /auth/status)
# are now in src/routes/auth_routes.py

@api_bp.route('/user/email-preferences', methods=['GET', 'PATCH'])
@require_user_auth
def user_email_preferences():
    """Get or update user's email delivery preference."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'auth context missing email'}), 401
        
        user = UserAccount.query.filter_by(email=email).first()
        if not user:
            user = _ensure_user_account(email)
        
        if request.method == 'PATCH':
            payload = request.get_json() or {}
            pref = (payload.get('email_delivery_preference') or '').strip().lower()
            if pref not in ('individual', 'digest'):
                return jsonify({'error': 'email_delivery_preference must be "individual" or "digest"'}), 400
            user.email_delivery_preference = pref
            user.updated_at = datetime.now(timezone.utc)
            db.session.commit()
        
        return jsonify({
            'email_delivery_preference': user.email_delivery_preference or 'individual',
            'user_id': user.id,
        })
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@api_bp.route('/user/all-subscriptions', methods=['GET'])
@require_user_auth
def user_all_subscriptions():
    """Get all user's subscriptions (both free team subs and paid journalist subs)."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'auth context missing email'}), 401
        
        user = UserAccount.query.filter_by(email=email).first()
        
        # Get free team subscriptions (by email)
        team_subs = UserSubscription.query.filter_by(email=email, active=True).all()
        free_subscriptions = []
        for sub in team_subs:
            team = sub.team
            free_subscriptions.append({
                'id': sub.id,
                'type': 'free',
                'team_id': sub.team_id,
                'team_name': team.name if team else None,
                'team_logo': team.logo if team else None,
                'created_at': sub.created_at.isoformat() if sub.created_at else None,
                'last_email_sent': sub.last_email_sent.isoformat() if sub.last_email_sent else None,
            })
        
        # Get PAID journalist subscriptions (Stripe only)
        paid_subscriptions = []
        
        if user:
            stripe_subs = StripeSubscription.query.filter_by(
                subscriber_user_id=user.id
            ).filter(StripeSubscription.status.in_(['active', 'trialing', 'past_due', 'canceled'])).all()
            
            for sub in stripe_subs:
                # Skip canceled subscriptions that have already ended
                if sub.status == 'canceled' and sub.current_period_end:
                    if sub.current_period_end < datetime.now(timezone.utc):
                        continue
                        
                journalist = sub.journalist
                
                # Get journalist's assigned teams for context
                assigned_teams = []
                if journalist:
                    for assignment in journalist.assigned_teams:
                        if assignment.team:
                            assigned_teams.append({
                                'id': assignment.team.id,
                                'name': assignment.team.name,
                                'logo': assignment.team.logo,
                            })
                
                paid_subscriptions.append({
                    'id': sub.id,
                    'type': 'paid',
                    'journalist_id': sub.journalist_user_id,
                    'journalist_name': journalist.display_name if journalist else None,
                    'journalist_email': journalist.email if journalist else None,
                    'journalist_profile_image': journalist.profile_image_url if journalist else None,
                    'assigned_teams': assigned_teams,
                    'status': sub.status,
                    'current_period_end': sub.current_period_end.isoformat() if sub.current_period_end else None,
                    'cancel_at_period_end': sub.cancel_at_period_end,
                    'created_at': sub.created_at.isoformat() if sub.created_at else None,
                })
        
        # Get FREE journalist follows (JournalistSubscription)
        journalist_follows = []
        if user:
            follows = JournalistSubscription.query.filter_by(
                subscriber_user_id=user.id,
                is_active=True
            ).all()
            
            for follow in follows:
                journalist = UserAccount.query.get(follow.journalist_user_id)
                
                # Get journalist's assigned teams for context
                assigned_teams = []
                if journalist:
                    for assignment in getattr(journalist, 'assigned_teams', []) or []:
                        if assignment.team:
                            assigned_teams.append({
                                'id': assignment.team.id,
                                'name': assignment.team.name,
                                'logo': assignment.team.logo,
                            })
                
                journalist_follows.append({
                    'id': follow.id,
                    'journalist_id': follow.journalist_user_id,
                    'journalist_name': journalist.display_name if journalist else None,
                    'journalist_email': journalist.email if journalist else None,
                    'journalist_profile_image': journalist.profile_image_url if journalist else None,
                    'assigned_teams': assigned_teams,
                    'created_at': follow.created_at.isoformat() if follow.created_at else None,
                })
        
        # Calculate estimated emails per week
        # Assume each team/journalist sends ~1 newsletter per week
        individual_count = len(free_subscriptions) + len(journalist_follows)
        
        return jsonify({
            'free_subscriptions': free_subscriptions,
            'paid_subscriptions': paid_subscriptions,
            'journalist_follows': journalist_follows,
            'total_count': individual_count,
            'estimated_emails_per_week': {
                'individual': individual_count,
                'digest': 1 if individual_count > 0 else 0,
            },
            'email_delivery_preference': (user.email_delivery_preference if user else 'individual') or 'individual',
        })
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


def _user_rate_limit_key() -> str | None:
    return getattr(g, 'user_email', None) or (request.remote_addr or 'anon')

# Auth endpoints moved to src/routes/auth_routes.py:
# - /auth/display-name, /auth/verify-code, /auth/status

# In api.py
@api_bp.route('/newsletters/generate-weekly-all', methods=['POST'])
@require_api_key
def generate_weekly_all():
    try:
        data = request.get_json() or {}
        target_date_str = data.get('target_date')  # YYYY-MM-DD
        from datetime import datetime
        if target_date_str:
            target_dt = datetime.strptime(target_date_str, "%Y-%m-%d").date()
        else:
            target_dt = datetime.now(timezone.utc).date()
        from src.jobs.run_weekly_newsletters import run_for_date
        result = run_for_date(target_dt)
        # Append to run history for admin UI visibility
        try:
            ok = len([r for r in (result or []) if r.get("newsletter_id")])
            errs = len([r for r in (result or []) if r.get("error")])
            _append_run_history({
                "kind": "newsletter-run",
                "ran_for": target_dt.isoformat(),
                "ok": ok,
                "errors": errs,
                "message": f"Weekly newsletters run for {target_dt.isoformat()} ({ok} ok, {errs} errors)"
            })
        except Exception:
            pass
        return jsonify({"ran_for": target_dt.isoformat(), "results": result})
    except Exception as e:
        logger.exception("generate-weekly-all failed")
        return jsonify({"error": str(e)}), 500

@api_bp.route('/newsletters/generate-weekly-all-mcp', methods=['POST'])
@require_api_key
def generate_weekly_all_mcp():
    try:
        payload = request.get_json() or {}
        target_date = payload.get('target_date')
        from datetime import datetime, date as d
        tdate = datetime.strptime(target_date, "%Y-%m-%d").date() if target_date else d.today()

        from src.jobs.run_weekly_newsletters_mcp import run_for_date
        result = run_for_date(tdate)
        # Append to run history
        try:
            ok = len([r for r in (result or []) if r.get("status") == "ok"])  # mcp variant shape
            errs = len([r for r in (result or []) if r.get("status") == "error"]) 
            _append_run_history({
                "kind": "newsletter-run-mcp",
                "ran_for": tdate.isoformat(),
                "ok": ok,
                "errors": errs,
                "message": f"Weekly newsletters (MCP) for {tdate.isoformat()} ({ok} ok, {errs} errors)"
            })
        except Exception:
            pass
        return jsonify({"ran_for": tdate.isoformat(), "results": result})
    except Exception as e:
        logger.exception("generate-weekly-all-mcp failed")
        return jsonify({"error": str(e)}), 500
    
def _sync_season(window_key: str | None = None, season: int | None = None):
    """Set api_client season and prime cache. Returns the start-year int."""
    if window_key:
        season_start = int(window_key.split("::")[0].split("-")[0])
        api_client.set_season_from_window_key(window_key)
    elif season is not None:
        season_start = season
        api_client.set_season_year(season_start)
    else:
        raise ValueError("Either window_key or season required")
    api_client._prime_team_cache(season_start)
    return season_start

# ALLOWED_ADMIN_IPS and get_client_ip are imported from src.auth
# Teams, leagues, and gameweek endpoints have been moved to src/routes/teams.py

# Team utility functions (used by other parts of api.py)
def resolve_team_ids(id_or_api_id: int, season: int = None) -> tuple[int | None, int | None, str | None]:
    """
    Return (db_id, api_id, name) for a team, accepting either a DB PK or an
    API-Football team_id.  We prefer an API-id match first, then DB PK.
    If season is provided, it will be used to filter the team lookup.
    """
    # 1 – exact API-id match (with season if provided)
    if season:
        row = Team.query.filter_by(team_id=id_or_api_id, season=season).first()
    else:
        row = Team.query.filter_by(team_id=id_or_api_id).first()
    if row:
        return row.id, row.team_id, row.name

    # 2 – fallback: treat as DB primary-key
    row = Team.query.get(id_or_api_id)
    if row:
        return row.id, row.team_id, row.name

    # 3 – not found
    return None, None, None


# Team name resolution — single source of truth in utils/team_resolver.py
from src.utils.team_resolver import resolve_team_name_and_logo  # noqa: F811


# Newsletter endpoints
@api_bp.route('/newsletters', methods=['GET'])
def get_newsletters():
    """Get newsletters with filters."""
    try:
        query = Newsletter.query
        
        # Filter by team
        team_id = request.args.get('team', type=int)
        if team_id:
            query = query.filter_by(team_id=team_id)

        # Filter by multiple teams (comma-separated list)
        raw_team_ids = request.args.get('team_ids')
        if raw_team_ids:
            try:
                ids = [int(x.strip()) for x in str(raw_team_ids).split(',') if str(x).strip().isdigit()]
                if ids:
                    query = query.filter(Newsletter.team_id.in_(ids))
            except Exception:
                pass
        
        # Filter by newsletter type
        newsletter_type = request.args.get('type')
        if newsletter_type:
            query = query.filter_by(newsletter_type=newsletter_type)

        # Filter by league (by leagues PK)
        league_id = request.args.get('league_id', type=int)
        if league_id:
            query = query.join(Team).filter(Team.league_id == league_id)
        
        # Filter by published status
        published_only = request.args.get('published_only', 'false').lower() == 'true'
        if published_only:
            query = query.filter_by(published=True)
        
        # Filter by date range
        days = request.args.get('days')
        if days:
            try:
                cutoff_date = datetime.now(timezone.utc) - timedelta(days=int(days))
                query = query.filter(Newsletter.generated_date >= cutoff_date)
            except ValueError:
                pass

        # Filter by a specific week range (inclusive)
        # Expect week_start and week_end as YYYY-MM-DD
        week_start_str = request.args.get('week_start')
        week_end_str = request.args.get('week_end')
        if week_start_str and week_end_str:
            try:
                week_start = datetime.strptime(week_start_str, '%Y-%m-%d').date()
                week_end = datetime.strptime(week_end_str, '%Y-%m-%d').date()
                # Match newsletters whose stored week range overlaps the requested week
                query = query.filter(
                    db.and_(
                        Newsletter.week_start_date <= week_end,
                        Newsletter.week_end_date >= week_start,
                    )
                )
            except ValueError:
                pass

        # Handle search filter (for global search)
        search = request.args.get('search', '').strip()
        if search:
            # Search in newsletter title or team name
            # Need to join with Team if not already joined
            query = query.outerjoin(Team, Newsletter.team_id == Team.id).filter(
                db.or_(
                    Newsletter.title.ilike(f'%{search}%'),
                    Team.name.ilike(f'%{search}%')
                )
            )

        # Exclude current week (server-side)
        exclude_current_week = request.args.get('exclude_current_week', 'false').lower() in ('true', '1', 'yes', 'y')
        if exclude_current_week:
            today = datetime.now(timezone.utc).date()
            # Compute Monday..Sunday of current week
            days_since_monday = today.weekday()
            current_week_start = today - timedelta(days=days_since_monday)
            current_week_end = current_week_start + timedelta(days=6)
            # Exclude if generated/published in current week OR stored week overlaps current week
            query = query.filter(
                db.and_(
                    db.or_(
                        Newsletter.published_date == None,
                        db.not_(db.and_(
                            db.func.date(Newsletter.published_date) >= current_week_start,
                            db.func.date(Newsletter.published_date) <= current_week_end,
                        )),
                    ),
                    db.or_(
                        Newsletter.week_start_date == None,
                        Newsletter.week_end_date == None,
                        db.not_(db.and_(
                            Newsletter.week_start_date <= current_week_end,
                            Newsletter.week_end_date >= current_week_start,
                        )),
                    ),
                )
            )
        
        newsletters = query.order_by(Newsletter.generated_date.desc()).all()
        payload: list[dict] = []
        for newsletter in newsletters:
            row = newsletter.to_dict()
            try:
                enriched = _load_newsletter_json(newsletter)
                # The LIST endpoint must NOT return the full enriched_content —
                # each newsletter carries ~6 base64-encoded chart PNGs per
                # player which add ~2 MB / newsletter. With 10+ newsletters
                # this turns into a 25-30 MB payload that takes 30-40 seconds
                # to download even on fast connections, which made the
                # newsletter list page (and the focused-view URL that gates
                # on it) effectively unusable. Strip the chart URLs and any
                # embedded HTML before serialising. Detail consumers should
                # call GET /newsletters/<id> for the full content.
                row['enriched_content'] = _strip_heavy_fields_for_list(enriched)
            except Exception:
                row['enriched_content'] = None
            # Skip `row['rendered']` entirely — the rendered web/email HTML
            # blobs also embed the chart images and add several MB. The
            # focused-view detail endpoint still returns them.
            payload.append(row)
        return jsonify(payload)
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/subscriptions/me', methods=['GET'])
@require_user_auth
def my_subscriptions():
    """Return active subscriptions for the authenticated user's email."""
    try:
        email = getattr(g, 'user_email', None)
        email_norm = (email or '').strip().lower()
        if not email_norm:
            return jsonify({'error': 'Unauthorized'}), 401
        subs = UserSubscription.query.filter_by(email=email_norm, active=True).all()
        return jsonify([s.to_dict() for s in subs])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@api_bp.route('/subscriptions/me', methods=['POST'])
@require_user_auth
def update_my_subscriptions():
    """Create, reactivate, or deactivate team subscriptions for the signed-in user."""
    try:
        email = getattr(g, 'user_email', None)
        if not email:
            return jsonify({'error': 'Unauthorized'}), 401

        payload = request.get_json() or {}
        team_ids_raw = payload.get('team_ids') or []
        preferred_frequency = (payload.get('preferred_frequency') or 'weekly').strip() or 'weekly'

        parsed_ids: list[int] = []
        rejected_inputs: list[Any] = []
        for raw in team_ids_raw:
            try:
                tid = int(raw)
            except (TypeError, ValueError):
                rejected_inputs.append(raw)
                continue
            parsed_ids.append(tid)

        # Preserve order but drop duplicates
        unique_ids: list[int] = []
        seen: set[int] = set()
        for tid in parsed_ids:
            if tid not in seen:
                seen.add(tid)
                unique_ids.append(tid)

        team_rows = Team.query.filter(Team.id.in_(unique_ids)).all() if unique_ids else []
        valid_ids = {row.id for row in team_rows}
        missing_team_ids = [tid for tid in unique_ids if tid not in valid_ids]

        desired_team_ids = set(valid_ids)
        email_norm = (email or '').strip().lower()
        now = datetime.now(timezone.utc)

        existing_rows = UserSubscription.query.filter_by(email=email_norm).all()
        existing_map = {row.team_id: row for row in existing_rows}

        created_count = 0
        reactivated_count = 0
        updated_pref_count = 0

        for team in team_rows:
            sub = existing_map.get(team.id)
            if sub:
                changed = False
                if not sub.active:
                    sub.active = True
                    changed = True
                    reactivated_count += 1
                if sub.preferred_frequency != preferred_frequency:
                    sub.preferred_frequency = preferred_frequency
                    changed = True
                    updated_pref_count += 1
                if not sub.unsubscribe_token:
                    sub.unsubscribe_token = str(uuid.uuid4())
                    changed = True
                if changed:
                    sub.updated_at = now
            else:
                subscription = UserSubscription(
                    email=email_norm,
                    team_id=team.id,
                    preferred_frequency=preferred_frequency,
                    active=True,
                    unsubscribe_token=str(uuid.uuid4()),
                    created_at=now,
                    updated_at=now,
                )
                db.session.add(subscription)
                created_count += 1

        deactivated_count = 0
        for sub in existing_rows:
            if sub.team_id not in desired_team_ids and sub.active:
                sub.active = False
                sub.updated_at = now
                deactivated_count += 1

        db.session.commit()

        if created_count or reactivated_count or deactivated_count:
            from src.services.admin_notify_service import notify_subscription_change
            changed_names = [r.name or f'Team #{r.id}' for r in team_rows]
            notify_subscription_change(
                email_norm, changed_names,
                created=created_count, reactivated=reactivated_count,
                deactivated=deactivated_count,
            )

        active_subs = UserSubscription.query.filter_by(email=email_norm, active=True).all()
        response = {
            'message': 'Subscriptions updated',
            'created_count': created_count,
            'reactivated_count': reactivated_count,
            'updated_frequency_count': updated_pref_count,
            'deactivated_count': deactivated_count,
            'ignored_team_ids': missing_team_ids + rejected_inputs,
            'subscriptions': [s.to_dict() for s in active_subs],
        }
        return jsonify(response)
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

        return jsonify(payload)
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/newsletters/<int:newsletter_id>', methods=['GET'])
def get_newsletter(newsletter_id):
    """Get specific newsletter."""
    try:
        newsletter = Newsletter.query.get_or_404(newsletter_id)
        payload = newsletter.to_dict()
        
        # Collect all commentaries
        all_commentaries = [c.to_dict() for c in _collect_commentaries_for_newsletter(newsletter)]
        
        # Check for journalist filter
        journalist_id_param = request.args.get('journalist_id')
        if journalist_id_param:
            try:
                journalist_id = int(journalist_id_param)
                # Filter commentaries
                filtered_commentaries = [c for c in all_commentaries if c.get('author_id') == journalist_id]
                
                # Check subscription status
                is_subscribed = False
                email = _get_authorized_email()
                if email:
                    user = UserAccount.query.filter_by(email=email).first()
                    if user:
                        sub = JournalistSubscription.query.filter_by(
                            subscriber_user_id=user.id,
                            journalist_user_id=journalist_id,
                            is_active=True
                        ).first()
                        if sub:
                            is_subscribed = True
                
                # Apply masking
                for c in filtered_commentaries:
                    if c.get('is_premium') and not is_subscribed:
                        # Mask content
                        raw_content = c.get('content') or ''
                        # Simple strip tags for preview
                        clean_text = re.sub('<[^<]+?>', '', raw_content)
                        preview = clean_text[:200] + '...' if len(clean_text) > 200 else clean_text
                        c['content'] = preview
                        c['is_locked'] = True
                    else:
                        c['is_locked'] = False
                
                payload['commentaries'] = filtered_commentaries
                
            except ValueError:
                # Invalid journalist_id, ignore filter
                payload['commentaries'] = all_commentaries
        else:
            payload['commentaries'] = all_commentaries

        logger.info(f"📰 [get_newsletter] Serving newsletter ID: {newsletter_id}")
        
        # Extract embedded rendered variants if present
        try:
            obj = json.loads(payload.get('structured_content') or payload.get('content') or '{}')
            rendered = obj.get('rendered') if isinstance(obj, dict) else None
            if isinstance(rendered, dict):
                payload['rendered'] = {
                    k: (v if isinstance(v, str) else '') for k, v in rendered.items()
                }
                logger.info(f"✅ [get_newsletter] Found rendered variants - web_html: {len(payload['rendered'].get('web_html', ''))} chars")
                
                # Check if web_html has expanded stats
                web_html = payload['rendered'].get('web_html', '')
                if 'Shots' in web_html or 'Saves' in web_html or 'Key Passes' in web_html:
                    logger.info(f"✅ [get_newsletter] Rendered HTML contains expanded stats!")
                else:
                    logger.warning(f"⚠️  [get_newsletter] Rendered HTML might not contain expanded stats")
            else:
                logger.warning(f"⚠️  [get_newsletter] No rendered variants found in newsletter content")
                
            # Log sample stats from the JSON
            sections = obj.get('sections', [])
            if sections:
                first_section = sections[0]
                items = first_section.get('items', [])
                if items:
                    first_item = items[0]
                    stats = first_item.get('stats', {})
                    logger.info(f"📊 [get_newsletter] Sample item stats from JSON:")
                    logger.info(f"   Player: {first_item.get('player_name')}")
                    logger.info(f"   Stats keys: {list(stats.keys())}")
                    logger.info(f"   Position: {stats.get('position')}")
                    logger.info(f"   Rating: {stats.get('rating')}")
                    logger.info(f"   Shots: {stats.get('shots_total')}")
                    logger.info(f"   Passes: {stats.get('passes_total')}")
        except Exception as e:
            logger.error(f"❌ [get_newsletter] Error extracting rendered variants: {e}")
            pass

        try:
            comments = (
                NewsletterComment.query
                .filter_by(newsletter_id=newsletter_id, is_deleted=False)
                .order_by(NewsletterComment.created_at.asc())
                .all()
            )
            payload['comments'] = [comment.to_dict() for comment in comments]
        except Exception:
            payload['comments'] = []

        try:
            payload['enriched_content'] = _load_newsletter_json(newsletter)
        except Exception:
            payload['enriched_content'] = None

        # Community takes (incl. tweets). Surfaced on the JSON response so the
        # React newsletter view can render an inline tweet block per player and
        # a team-level "Around the Squad — Twitter" section, matching what the
        # Flask templates already get via _newsletter_render_context.
        try:
            community_takes = _fetch_community_takes_for_newsletter(newsletter)
            payload['community_takes'] = community_takes
            payload['twitter_takes'] = [
                t for t in community_takes if t.get('source_type') == 'twitter'
            ]
            payload['twitter_takes_by_player'] = _build_twitter_takes_by_player(community_takes)
        except Exception:
            payload['community_takes'] = []
            payload['twitter_takes'] = []
            payload['twitter_takes_by_player'] = {}

        return jsonify(payload)
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/newsletters/<int:newsletter_id>/refresh-fixtures', methods=['POST'])
def refresh_newsletter_fixtures(newsletter_id: int):
    """
    Check upcoming fixtures in a newsletter and update with results if games have been played.
    This makes newsletters 'living documents' that show actual match outcomes.
    """
    try:
        newsletter = Newsletter.query.get_or_404(newsletter_id)
        
        # Parse structured content
        raw_content = newsletter.structured_content or newsletter.content or '{}'
        try:
            content = json.loads(raw_content)
        except json.JSONDecodeError:
            return jsonify({'error': 'Invalid newsletter content'}), 400
        
        sections = content.get('sections', [])
        if not sections:
            return jsonify({'updated': False, 'message': 'No sections found'})
        
        # Initialize API client for fixture lookups
        from src.api_football_client import APIFootballClient
        api_client = APIFootballClient()
        
        now = datetime.now(timezone.utc)
        fixtures_updated = 0
        fixtures_checked = 0
        
        # Iterate through all player sections and their upcoming fixtures
        for section in sections:
            items = section.get('items', [])
            for item in items:
                # Get loan team info from the player item (for fallback lookups)
                item_loan_team_id = item.get('loan_team_id') or item.get('loan_team_api_id')
                
                upcoming_fixtures = item.get('upcoming_fixtures', [])
                for fixture in upcoming_fixtures:
                    # Skip if already has result
                    if fixture.get('result'):
                        continue
                    
                    # Check if fixture date is in the past
                    fixture_date_str = fixture.get('date')
                    if not fixture_date_str:
                        continue
                    
                    try:
                        fixture_date = datetime.fromisoformat(fixture_date_str.replace('Z', '+00:00'))
                    except (ValueError, TypeError):
                        continue
                    
                    # Only check fixtures that should have been played (add 3 hour buffer for match duration)
                    if fixture_date + timedelta(hours=3) > now:
                        continue
                    
                    fixtures_checked += 1
                    
                    # Get fixture_id - either from fixture data or look it up
                    fixture_id = fixture.get('fixture_id')
                    loan_team_id = fixture.get('loan_team_id') or item_loan_team_id
                    
                    result_data = None
                    
                    if fixture_id:
                        # Direct lookup by fixture ID
                        result_data = api_client.get_fixture_result(fixture_id)
                    elif loan_team_id:
                        # Fallback: Look up by team + date (for older newsletters without fixture_id)
                        try:
                            fixture_date_only = fixture_date.date()
                            date_str = fixture_date_only.strftime('%Y-%m-%d')
                            season = api_client.current_season_start_year
                            
                            # Fetch fixtures for this team on this date
                            team_fixtures = api_client.get_fixtures_for_team(
                                loan_team_id, season, date_str, date_str
                            )
                            
                            # Find matching fixture by opponent
                            opponent_id = fixture.get('opponent_id')
                            opponent_name = fixture.get('opponent', '').lower()
                            
                            for fx in team_fixtures:
                                fx_info = fx.get('fixture', {})
                                teams = fx.get('teams', {})
                                home = teams.get('home', {}) or {}
                                away = teams.get('away', {}) or {}
                                
                                # Check if this fixture matches by opponent
                                is_home = loan_team_id == home.get('id')
                                opp_team = away if is_home else home
                                
                                match_by_id = opponent_id and opp_team.get('id') == opponent_id
                                match_by_name = opponent_name and opponent_name in (opp_team.get('name', '')).lower()
                                
                                if match_by_id or match_by_name:
                                    # Found it - extract result data
                                    goals = fx.get('goals', {})
                                    result_data = {
                                        'fixture_id': fx_info.get('id'),
                                        'status': fx_info.get('status', {}).get('short', ''),
                                        'home_team_id': home.get('id'),
                                        'away_team_id': away.get('id'),
                                        'home_score': goals.get('home'),
                                        'away_score': goals.get('away'),
                                    }
                                    # Store fixture_id for future lookups
                                    fixture['fixture_id'] = fx_info.get('id')
                                    fixture['loan_team_id'] = loan_team_id
                                    break
                        except Exception as e:
                            logger.warning(f"Fallback fixture lookup failed: {e}")
                            continue
                    
                    if not result_data:
                        continue
                    
                    status = result_data.get('status', '')
                    # Only update if match is finished (FT, AET, PEN)
                    if status not in ('FT', 'AET', 'PEN'):
                        continue
                    
                    home_score = result_data.get('home_score')
                    away_score = result_data.get('away_score')
                    
                    if home_score is None or away_score is None:
                        continue
                    
                    # Determine W/L/D based on loan team
                    home_team_id = result_data.get('home_team_id')
                    is_home = loan_team_id == home_team_id
                    
                    if is_home:
                        team_score = home_score
                        opponent_score = away_score
                    else:
                        team_score = away_score
                        opponent_score = home_score
                    
                    if team_score > opponent_score:
                        match_result = 'W'
                    elif team_score < opponent_score:
                        match_result = 'L'
                    else:
                        match_result = 'D'
                    
                    # Update the fixture with result data
                    fixture['status'] = 'completed'
                    fixture['home_score'] = home_score
                    fixture['away_score'] = away_score
                    fixture['result'] = match_result
                    fixture['team_score'] = team_score
                    fixture['opponent_score'] = opponent_score
                    
                    fixtures_updated += 1
        
        # Save updated content if any fixtures were updated
        if fixtures_updated > 0:
            content_json = json.dumps(content, ensure_ascii=False)
            newsletter.structured_content = content_json
            newsletter.content = content_json
            db.session.commit()
            logger.info(f"Updated {fixtures_updated} fixture results for newsletter {newsletter_id}")
        
        # Return updated newsletter content
        return jsonify({
            'updated': fixtures_updated > 0,
            'fixtures_checked': fixtures_checked,
            'fixtures_updated': fixtures_updated,
            'enriched_content': content
        })
        
    except Exception as e:
        logger.error(f"Error refreshing fixtures for newsletter {newsletter_id}: {e}")
        import traceback
        traceback.print_exc()
        return jsonify(_safe_error_payload(e, 'Failed to refresh fixture results')), 500


# Player endpoints (stats, profile, season-stats, commentaries) moved to routes/players.py


def _extract_lineup_info(api_client, fixture_id_api: int, player_api_id: int, team_api_id: int):
    """Extract formation and grid for a player from cached lineup data.

    Returns (formation, grid, formation_position).
    All values may be None if lineup data is unavailable or player not found.
    """
    from src.utils.formation_roles import grid_to_role
    try:
        lineups = api_client.get_fixture_lineups(fixture_id_api).get("response", [])
    except Exception:
        return None, None, None

    for lu in lineups:
        team = lu.get('team') or {}
        if team.get('id') != team_api_id:
            continue
        formation = lu.get('formation')
        for entry in lu.get('startXI') or []:
            pb = (entry or {}).get('player') or {}
            if pb.get('id') == player_api_id:
                grid = pb.get('grid')
                return formation, grid, grid_to_role(formation, grid)
        # Player is a substitute — formation known but no grid
        for entry in lu.get('substitutes') or []:
            pb = (entry or {}).get('player') or {}
            if pb.get('id') == player_api_id:
                return formation, None, None
    return None, None, None


def _sync_player_club_fixtures(player_id: int, loan_team_api_id: int, season: int, player_name: str = None) -> int:
    """
    Sync all fixtures for a player at their loan club from API-Football.
    Returns number of fixtures synced.
    
    Now includes automatic ID verification - if player_id yields no results but
    a matching player name is found with a different ID, updates the TrackedPlayer
    record and syncs with the correct ID.
    """
    from src.api_football_client import APIFootballClient
    from src.models.weekly import Fixture, FixturePlayerStats
    
    api_client = APIFootballClient()
    
    # Fetch all fixtures for the loan team this season
    season_start = f"{season}-08-01"
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    
    fixtures = api_client.get_fixtures_for_team_cached(
        loan_team_api_id,
        season,
        season_start,
        today
    )
    
    logger.info(f"Found {len(fixtures)} fixtures for team {loan_team_api_id} in season {season}")
    
    # 🔄 If we have a player name, verify ID via fixtures BEFORE syncing
    # This catches ID mismatches early (e.g., seeded before player played)
    corrected_id = None
    if player_name and len(fixtures) > 0:
        verified_id, method = api_client.verify_player_id_via_fixtures(
            candidate_player_id=player_id,
            player_name=player_name,
            loan_team_id=loan_team_api_id,
            season=season,
            max_fixtures=3
        )
        if verified_id != player_id:
            logger.warning(
                f"🔄 ID mismatch detected during stats sync for '{player_name}': "
                f"stored={player_id}, correct={verified_id}. Auto-correcting..."
            )
            # Also delete any ghost stats with the old ID
            ghost_deleted = FixturePlayerStats.query.filter(
                FixturePlayerStats.player_api_id == player_id,
                FixturePlayerStats.team_api_id == loan_team_api_id,
                FixturePlayerStats.minutes == 0
            ).delete()
            if ghost_deleted:
                db.session.commit()
                logger.info(f"🗑️ Deleted {ghost_deleted} ghost stat records with old ID {player_id}")
            
            corrected_id = verified_id
            player_id = verified_id  # Use corrected ID for syncing
    
    synced = 0
    for fx in fixtures:
        fixture_info = fx.get('fixture', {})
        fixture_id_api = fixture_info.get('id')
        fixture_status = fixture_info.get('status', {}).get('short', '')
        
        # Only process finished games
        if fixture_status not in ('FT', 'AET', 'PEN'):
            continue
        
        # Get or create fixture record
        existing_fixture = Fixture.query.filter_by(fixture_id_api=fixture_id_api).first()
        
        if not existing_fixture:
            teams = fx.get('teams', {})
            goals = fx.get('goals', {})
            league = fx.get('league', {})
            
            existing_fixture = Fixture(
                fixture_id_api=fixture_id_api,
                date_utc=datetime.fromisoformat(fixture_info.get('date', '').replace('Z', '+00:00')) if fixture_info.get('date') else None,
                season=season,
                competition_name=league.get('name'),
                home_team_api_id=teams.get('home', {}).get('id'),
                away_team_api_id=teams.get('away', {}).get('id'),
                home_goals=goals.get('home'),
                away_goals=goals.get('away'),
            )
            db.session.add(existing_fixture)
            db.session.flush()
        
        # Check if we already have player stats for this fixture
        existing_stats = FixturePlayerStats.query.filter_by(
            fixture_id=existing_fixture.id,
            player_api_id=player_id
        ).first()
        
        if existing_stats:
            continue
        
        # Fetch player stats for this fixture from API
        try:
            player_stats = api_client.get_player_stats_for_fixture(player_id, season, fixture_id_api)
            
            if player_stats and player_stats.get('statistics'):
                # statistics is a LIST, get first element
                stat_list = player_stats['statistics']
                if not stat_list:
                    continue
                st = stat_list[0] if isinstance(stat_list, list) else stat_list
                
                # Extract stats from the nested structure
                games = st.get('games', {}) or {}
                goals_obj = st.get('goals', {}) or {}
                cards = st.get('cards', {}) or {}
                shots = st.get('shots', {}) or {}
                passes = st.get('passes', {}) or {}
                tackles = st.get('tackles', {}) or {}
                duels = st.get('duels', {}) or {}
                dribbles = st.get('dribbles', {}) or {}
                
                minutes = games.get('minutes', 0) or 0

                # Record if player played (minutes > 0) or was listed as substitute
                # API-Football returns null minutes for some leagues, so we also
                # check the substitute flag to avoid dropping valid appearances
                if minutes > 0 or games.get('substitute') is not None:
                    # Fouls and penalties for more complete stats
                    fouls = st.get('fouls', {}) or {}
                    penalty = st.get('penalty', {}) or {}
                    
                    formation, grid, formation_pos = _extract_lineup_info(
                        api_client, fixture_id_api, player_id, loan_team_api_id)

                    fps = FixturePlayerStats(
                        fixture_id=existing_fixture.id,
                        player_api_id=player_id,
                        team_api_id=loan_team_api_id,
                        minutes=minutes,
                        substitute=bool(games.get('substitute')),
                        position=games.get('position'),
                        rating=games.get('rating'),
                        goals=goals_obj.get('total', 0) or 0,
                        assists=goals_obj.get('assists', 0) or 0,
                        yellows=cards.get('yellow', 0) or 0,
                        reds=cards.get('red', 0) or 0,
                        shots_total=shots.get('total'),
                        shots_on=shots.get('on'),
                        passes_total=passes.get('total'),
                        passes_key=passes.get('key'),
                        tackles_total=tackles.get('total'),
                        duels_won=duels.get('won'),
                        duels_total=duels.get('total'),
                        dribbles_success=dribbles.get('success'),
                        # Goalkeeper stats - saves and conceded are in goals block
                        saves=goals_obj.get('saves'),
                        goals_conceded=goals_obj.get('conceded'),
                        # Additional stats
                        fouls_drawn=fouls.get('drawn'),
                        fouls_committed=fouls.get('committed'),
                        penalty_saved=penalty.get('saved'),
                        # Formation & tactical position
                        formation=formation,
                        grid=grid,
                        formation_position=formation_pos,
                    )
                    db.session.add(fps)
                    synced += 1
                    logger.debug(f"Added stats for fixture {fixture_id_api}: {minutes}' played")
        except Exception as e:
            logger.warning(f"Failed to get player stats for fixture {fixture_id_api}: {e}")
            continue
    
    if synced > 0:
        db.session.commit()
        logger.info(f"Synced {synced} fixtures for player {player_id} at team {loan_team_api_id}")
    
    return synced

@api_bp.route('/players/search', methods=['GET'])
def public_player_search():
    """Public search for tracked players by name."""
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    try:
        rows = TrackedPlayer.query\
            .filter(TrackedPlayer.player_name.ilike(f'%{q}%'), TrackedPlayer.is_active == True)\
            .order_by(TrackedPlayer.player_name)\
            .limit(20)\
            .all()
        # Deduplicate by player_api_id (a player may be tracked by multiple academies)
        seen = set()
        results = []
        for row in rows:
            if row.player_api_id in seen:
                continue
            seen.add(row.player_api_id)
            results.append({
                'player_api_id': row.player_api_id,
                'player_name': row.player_name,
                'photo_url': row.photo_url,
                'position': row.position,
                'team_name': row.team.name if row.team else None,
                'current_club_name': row.current_club_name,
            })
            if len(results) >= 8:
                break
        return jsonify(results)
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'Player search failed')), 500



@api_bp.route('/newsletters/<int:newsletter_id>/comments', methods=['GET'])
def list_newsletter_comments(newsletter_id: int):
    try:
        # Ensure newsletter exists
        Newsletter.query.get_or_404(newsletter_id)
        rows = NewsletterComment.query\
            .filter_by(newsletter_id=newsletter_id, is_deleted=False)\
            .order_by(NewsletterComment.created_at.asc())\
            .all()
        return jsonify([r.to_dict() for r in rows])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/newsletters/<int:newsletter_id>/comments', methods=['POST'])
@require_user_auth
@limiter.limit("8 per minute", key_func=_user_rate_limit_key)
def create_newsletter_comment(newsletter_id: int):
    try:
        nl = Newsletter.query.get_or_404(newsletter_id)
        payload = request.get_json() or {}
        raw_body = (payload.get('body') or '').strip()
        if not raw_body:
            return jsonify({'error': 'body is required'}), 400
        body = sanitize_comment_body(raw_body)
        user_email = getattr(g, 'user_email', None)
        if not user_email:
            return jsonify({'error': 'auth context missing email'}), 401
        user = UserAccount.query.filter_by(email=user_email).first()
        if not user:
            user = _ensure_user_account(user_email)
        if not body:
            return jsonify({'error': 'body is required'}), 400
        c = NewsletterComment(
            newsletter_id=nl.id,
            user_id=user.id if user else None,
            author_email=user_email,
            author_name=user.display_name if user else None,
            author_name_legacy=user.display_name if user else None,
            user=user,
            body=body,
        )
        if not c.author_email:
            return jsonify({'error': 'auth context missing email'}), 401
        db.session.add(c)
        db.session.commit()
        return jsonify({'message': 'Comment created', 'comment': c.to_dict()}), 201
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


# ===== Player Comments =====

@api_bp.route('/players/<int:player_id>/comments', methods=['GET'])
def list_player_comments(player_id: int):
    try:
        rows = PlayerComment.query\
            .filter_by(player_id=player_id, is_deleted=False)\
            .order_by(PlayerComment.created_at.asc())\
            .all()
        return jsonify([r.to_dict() for r in rows])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/players/<int:player_id>/comments', methods=['POST'])
@require_user_auth
@limiter.limit("8 per minute", key_func=_user_rate_limit_key)
def create_player_comment(player_id: int):
    try:
        payload = request.get_json() or {}
        raw_body = (payload.get('body') or '').strip()
        if not raw_body:
            return jsonify({'error': 'body is required'}), 400
        body = sanitize_comment_body(raw_body)
        if not body:
            return jsonify({'error': 'body is required'}), 400
        user_email = getattr(g, 'user_email', None)
        if not user_email:
            return jsonify({'error': 'auth context missing email'}), 401
        user = UserAccount.query.filter_by(email=user_email).first()
        if not user:
            user = _ensure_user_account(user_email)
        c = PlayerComment(
            player_id=player_id,
            user_id=user.id if user else None,
            author_email=user_email,
            author_name=user.display_name if user else None,
            body=body,
        )
        db.session.add(c)
        db.session.commit()
        return jsonify({'message': 'Comment created', 'comment': c.to_dict()}), 201
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


# ===== Player Links =====

@api_bp.route('/players/<int:player_id>/links', methods=['GET'])
def list_player_links(player_id: int):
    try:
        rows = PlayerLink.query\
            .filter_by(player_id=player_id, status='approved')\
            .order_by(PlayerLink.upvotes.desc(), PlayerLink.created_at.desc())\
            .all()
        results = [r.to_dict() for r in rows]

        # Merge YouTube links from newsletters for this player
        yt_rows = NewsletterPlayerYoutubeLink.query\
            .filter_by(player_id=player_id)\
            .order_by(NewsletterPlayerYoutubeLink.created_at.desc())\
            .all()
        seen_urls = {r['url'] for r in results}
        for yt in yt_rows:
            if yt.youtube_link in seen_urls:
                continue
            seen_urls.add(yt.youtube_link)
            results.append({
                'id': f'yt-{yt.id}',
                'player_id': yt.player_id,
                'url': yt.youtube_link,
                'title': yt.player_name + ' Highlights' if yt.player_name else 'Match Highlights',
                'link_type': 'highlight',
                'status': 'approved',
                'upvotes': 0,
                'source': 'newsletter',
                'created_at': yt.created_at.isoformat() if yt.created_at else None,
            })

        return jsonify(results)
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'Failed to fetch player links')), 500

@api_bp.route('/players/<int:player_id>/links', methods=['POST'])
@require_user_auth
@limiter.limit("5 per minute", key_func=_user_rate_limit_key)
def submit_player_link(player_id: int):
    try:
        payload = request.get_json() or {}
        raw_url = (payload.get('url') or '').strip()
        if not raw_url:
            return jsonify({'error': 'url is required'}), 400
        if len(raw_url) > 500:
            return jsonify({'error': 'url is too long'}), 400
        raw_title = (payload.get('title') or '').strip()
        title = sanitize_plain_text(raw_title)[:200] if raw_title else None
        link_type = (payload.get('link_type') or 'article').strip()
        if link_type not in ('article', 'highlight', 'social', 'stats', 'other'):
            link_type = 'other'
        user_email = getattr(g, 'user_email', None)
        if not user_email:
            return jsonify({'error': 'auth context missing email'}), 401
        user = UserAccount.query.filter_by(email=user_email).first()
        if not user:
            user = _ensure_user_account(user_email)
        link = PlayerLink(
            player_id=player_id,
            user_id=user.id if user else None,
            url=raw_url,
            title=title,
            link_type=link_type,
            status='pending',
        )
        db.session.add(link)
        db.session.commit()
        return jsonify({'message': 'Link submitted for review', 'link': link.to_dict()}), 201
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'Failed to submit link')), 500

@api_bp.route('/admin/player-links/pending', methods=['GET'])
@require_api_key
def admin_list_pending_player_links():
    try:
        rows = PlayerLink.query\
            .filter_by(status='pending')\
            .order_by(PlayerLink.created_at.asc())\
            .all()
        return jsonify([r.to_dict() for r in rows])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'Failed to fetch pending links')), 500

@api_bp.route('/admin/player-links/<int:link_id>', methods=['PUT'])
@require_api_key
def admin_update_player_link(link_id: int):
    try:
        link = PlayerLink.query.get_or_404(link_id)
        payload = request.get_json() or {}
        new_status = payload.get('status')
        if new_status not in ('approved', 'rejected'):
            return jsonify({'error': 'status must be approved or rejected'}), 400
        link.status = new_status
        db.session.commit()
        return jsonify({'message': f'Link {new_status}', 'link': link.to_dict()})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'Failed to update link')), 500


@api_bp.route('/newsletters/generate', methods=['POST'])
def generate_newsletter():
    """Generate a newsletter for a specific team and date."""
    try:
        logger.info("=" * 80)
        logger.info("📰 NEWSLETTER GENERATION REQUEST STARTED")
        
        data = request.get_json()
        team_id = data.get('team_id')
        target_date = data.get('target_date')  # Format: YYYY-MM-DD
        newsletter_type = data.get('type', 'weekly')
        force_refresh = data.get('force_refresh', False)
        
        logger.info(f"📝 Request data: team_id={team_id}, target_date={target_date}, type={newsletter_type}, force_refresh={force_refresh}")
        
        if not team_id:
            logger.warning("❌ Missing team_id in request")
            return jsonify({'error': 'team_id is required'}), 400
        
        logger.info(f"🔍 Fetching team with ID: {team_id}")
        team = Team.query.get_or_404(team_id)
        logger.info(f"✅ Found team: {team.name} (ID: {team.id})")
        
        # Parse target date
        if target_date:
            try:
                target_date = datetime.strptime(target_date, '%Y-%m-%d').date()
                logger.info(f"📅 Parsed target date: {target_date}")
            except ValueError as ve:
                logger.error(f"❌ Invalid date format: {target_date}, error: {ve}")
                return jsonify({'error': 'Invalid date format. Use YYYY-MM-DD'}), 400
        else:
            target_date = datetime.now(timezone.utc).date()
            logger.info(f"📅 Using today's date: {target_date}")
        
        # Compute week window for weekly newsletters
        week_start = None
        week_end = None
        if newsletter_type == 'weekly' and target_date:
            week_start = target_date - timedelta(days=target_date.weekday())
            week_end = week_start + timedelta(days=6)
            logger.info(f"📆 Computed week range: {week_start} to {week_end}")

        # Check if newsletter already exists for this team and week/date
        logger.info(f"🔍 Checking for existing newsletter: team_id={team_id}, type={newsletter_type}, date={target_date}")
        if week_start and week_end:
            existing = Newsletter.query.filter_by(
                team_id=team_id,
                newsletter_type=newsletter_type,
                week_start_date=week_start,
                week_end_date=week_end
            ).first()
        else:
            existing = Newsletter.query.filter_by(
                team_id=team_id,
                newsletter_type=newsletter_type,
                issue_date=target_date
            ).first()

        if existing and not force_refresh:
            logger.info(f"ℹ️  Newsletter already exists with ID: {existing.id}")
            return jsonify({
                'message': 'Newsletter already exists for this date',
                'newsletter': existing.to_dict()
            })
        
        # For weekly newsletters, use the OpenAI-powered generator which
        # compiles full player + loan team weekly context before writing,
        # then persist the newsletter with the same semantics as before.
        if newsletter_type == 'weekly':
            logger.info("🤖 Starting weekly newsletter composition...")
            try:
                from src.agents.weekly_newsletter_agent import (
                    compose_team_weekly_newsletter,
                    persist_newsletter,
                )
                logger.info("✅ Successfully imported newsletter agent functions")
            except ImportError as ie:
                logger.error(f"❌ IMPORT ERROR: Failed to import newsletter agent: {ie}")
                logger.exception("Full import traceback:")
                raise

            try:
                logger.info(f"🚀 Calling compose_team_weekly_newsletter(team_id={team_id}, target_date={target_date}, force_refresh={force_refresh})")
                composed = compose_team_weekly_newsletter(team_id, target_date, force_refresh=force_refresh)
                logger.info("✅ Newsletter composed successfully")
                logger.info(f"📊 Composed data keys: {list(composed.keys())}")
            except Exception as compose_error:
                logger.error(f"❌ COMPOSITION ERROR: {type(compose_error).__name__}: {compose_error}")
                logger.exception("Full composition traceback:")
                raise
            
            try:
                logger.info("💾 Persisting newsletter to database...")
                if existing and force_refresh:
                    logger.info(f"♻️  Force refresh requested; updating existing newsletter ID: {existing.id}")
                    payload_obj = None
                    content_json_str = composed.get('content_json') or '{}'
                    try:
                        payload_obj = json.loads(content_json_str) if isinstance(content_json_str, str) else content_json_str
                    except Exception:
                        payload_obj = None

                    if isinstance(payload_obj, dict):
                        # Render variants for preview/email
                        try:
                            from src.agents.weekly_newsletter_agent import _render_variants
                            team_name = team.name if team else None
                            variants = _render_variants(payload_obj, team_name)
                            payload_obj['rendered'] = variants
                            content_json_str = json.dumps(payload_obj, ensure_ascii=False)
                        except Exception:
                            pass

                    now = datetime.now(timezone.utc)
                    if isinstance(payload_obj, dict):
                        title = payload_obj.get('title')
                        if isinstance(title, str) and title.strip():
                            existing.title = title.strip()
                    existing.content = content_json_str
                    existing.structured_content = content_json_str
                    existing.issue_date = target_date
                    existing.week_start_date = composed.get('week_start') or week_start
                    existing.week_end_date = composed.get('week_end') or week_end
                    existing.generated_date = now
                    existing.updated_at = now
                    db.session.commit()
                    logger.info(f"✅ Newsletter refreshed for ID: {existing.id}")
                    row = existing
                else:
                    # Persist using shared helper (sets generated_date/published_date)
                    row = persist_newsletter(
                        team_db_id=team_id,
                        content_json_str=composed['content_json'],
                        week_start=composed['week_start'],
                        week_end=composed['week_end'],
                        issue_date=target_date,
                        newsletter_type='weekly',
                    )
                    logger.info(f"✅ Newsletter persisted with ID: {row.id}")
            except Exception as persist_error:
                logger.error(f"❌ PERSISTENCE ERROR: {type(persist_error).__name__}: {persist_error}")
                logger.exception("Full persistence traceback:")
                raise
            
            logger.info("🎉 Newsletter generation completed successfully!")
            logger.info("=" * 80)
            return jsonify({
                'message': 'Newsletter generated successfully',
                'newsletter': row.to_dict()
            })
        
        # Fallback for other types (currently unsupported):
        logger.warning(f"❌ Unsupported newsletter type: {newsletter_type}")
        return jsonify({'error': f'Unsupported newsletter type: {newsletter_type}'}), 400
        
    except Exception as e:
        # Ensure DB session is not left in a failed state for subsequent requests
        try:
            db.session.rollback()
        except Exception:
            pass
        logger.error("=" * 80)
        logger.error(f"💥 FATAL ERROR in generate_newsletter: {type(e).__name__}: {e}")
        logger.exception("Full error traceback:")
        logger.error("=" * 80)
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

def generate_newsletter_content(*args, **kwargs):  # pragma: no cover - legacy shim
    """Deprecated: shim retained for backward compatibility.
    The /newsletters/generate endpoint now uses the OpenAI-backed
    generator for 'weekly' type. This function is unused and will
    be removed in a future cleanup.
    """
    raise NotImplementedError("Legacy mock generator removed; use generate_team_weekly_newsletter")

# Subscription endpoints
@api_bp.route('/subscriptions', methods=['GET'])
@require_api_key
def get_subscriptions():
    """Admin: list subscriptions with optional active filter."""
    try:
        active_only = request.args.get('active_only', 'false').lower() in ('true', '1', 'yes', 'y')
        query = UserSubscription.query
        if active_only:
            query = query.filter(UserSubscription.active == True)
        subscriptions = query.all()
        return jsonify([sub.to_dict() for sub in subscriptions])
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


def _activate_subscriptions(email: str, team_ids: list[int], preferred_frequency: str = 'weekly') -> dict[str, Any]:
    created_ids: list[int] = []
    updated_ids: list[int] = []
    skipped: list[dict[str, Any]] = []
    teams_without_newsletters: list[dict[str, Any]] = []

    unique_ids: list[int] = []
    seen_ids: set[int] = set()
    for tid in team_ids:
        if tid in seen_ids:
            continue
        seen_ids.add(tid)
        unique_ids.append(tid)

    team_rows = Team.query.filter(Team.id.in_(unique_ids)).all() if unique_ids else []
    team_map = {row.id: row for row in team_rows}

    for tid in unique_ids:
        team = team_map.get(tid)
        if not team:
            skipped.append({'team_id': tid, 'reason': 'team not found'})
            continue

        # Track teams without active newsletters
        if not team.newsletters_active:
            teams_without_newsletters.append({
                'team_id': team.id,
                'team_name': team.name
            })

        existing = UserSubscription.query.filter_by(email=email, team_id=team.id).first()
        if existing:
            changed = False
            if not existing.active:
                existing.active = True
                changed = True
            if existing.preferred_frequency != preferred_frequency:
                existing.preferred_frequency = preferred_frequency
                changed = True
            if not existing.unsubscribe_token:
                existing.unsubscribe_token = str(uuid.uuid4())
                changed = True
            if changed:
                updated_ids.append(existing.id)
            else:
                skipped.append({'team_id': team.id, 'reason': 'already active'})
            continue

        subscription = UserSubscription(
            email=email,
            team_id=team.id,
            preferred_frequency=preferred_frequency,
            active=True,
            unsubscribe_token=str(uuid.uuid4()),
        )
        db.session.add(subscription)
        db.session.flush()
        created_ids.append(subscription.id)

    result_ids = created_ids + updated_ids
    subs = UserSubscription.query.filter(UserSubscription.id.in_(result_ids)).all() if result_ids else []

    # Send waitlist email if there are teams without newsletters
    if teams_without_newsletters:
        try:
            team_names = [t['team_name'] for t in teams_without_newsletters]
            _send_waitlist_welcome_email(email, team_names)
        except Exception as e:
            logger.warning('Failed to send waitlist email to %s: %s', email, e)

    return {
        'message': 'Subscriptions updated',
        'created_count': len(created_ids),
        'updated_count': len(updated_ids),
        'skipped': skipped,
        'created_ids': created_ids,
        'updated_ids': updated_ids,
        'subscriptions': [s.to_dict() for s in subs],
        'teams_without_newsletters': teams_without_newsletters,
    }


def _process_subscriptions(email: str, team_ids_raw: list[Any], preferred_frequency: str) -> tuple[dict[str, Any], int]:
    if not email:
        return {'error': 'email is required'}, 400
    if not team_ids_raw:
        return {'error': 'team_ids are required'}, 400

    parsed_ids: list[int] = []
    skipped: list[dict[str, Any]] = []
    for raw_id in team_ids_raw:
        try:
            tid = int(raw_id)
        except (TypeError, ValueError):
            skipped.append({'team_id': raw_id, 'reason': 'invalid team id'})
            continue
        parsed_ids.append(tid)

    if not parsed_ids:
        return {'error': 'No valid team ids provided', 'skipped': skipped}, 400

    team_rows = Team.query.filter(Team.id.in_(parsed_ids)).all()
    team_map = {row.id: row for row in team_rows}

    valid_ids: list[int] = []
    team_names: list[str] = []
    teams_without_newsletters: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for tid in parsed_ids:
        if tid in seen_ids:
            continue
        seen_ids.add(tid)
        team = team_map.get(tid)
        if not team:
            skipped.append({'team_id': tid, 'reason': 'team not found'})
            continue
        valid_ids.append(tid)
        team_names.append(team.name or f'Team #{tid}')
        
        # Track teams without active newsletters
        if not team.newsletters_active:
            teams_without_newsletters.append({
                'team_id': team.id,
                'team_name': team.name
            })

    if not valid_ids:
        return {'error': 'No valid team ids provided', 'skipped': skipped}, 400

    if SUBSCRIPTIONS_REQUIRE_VERIFY:
        try:
            token_row = _create_email_token(
                email=email,
                purpose='subscribe_confirm',
                metadata={'team_ids': valid_ids, 'preferred_frequency': preferred_frequency},
                ttl_minutes=SUBSCRIPTIONS_VERIFY_TTL_MINUTES,
            )
            db.session.flush()
            _send_subscription_verification_email(email, team_names, token_row.token)
            db.session.commit()
            from src.services.admin_notify_service import notify_subscription_change
            notify_subscription_change(
                email, team_names,
                created=len(valid_ids), pending_verification=True,
            )
            return ({
                'message': 'Verification email sent. Please check your inbox to confirm.',
                'verification_required': True,
                'team_count': len(valid_ids),
                'expires_at': token_row.expires_at.isoformat() if token_row.expires_at else None,
                'skipped': skipped,
                'teams_without_newsletters': teams_without_newsletters,
            }, 202)
        except Exception as exc:
            try:
                db.session.rollback()
            except Exception:
                pass
            logger.exception('Failed to queue subscription verification for %s', email)
            return _safe_error_payload(exc, 'Failed to send verification email'), 500

    result = _activate_subscriptions(email, valid_ids, preferred_frequency)
    result['skipped'].extend(skipped)
    db.session.commit()

    if result['created_count'] or result['updated_count']:
        from src.services.admin_notify_service import notify_subscription_change
        notify_subscription_change(
            email, team_names,
            created=result['created_count'], reactivated=result['updated_count'],
        )

    status = 201 if result['created_count'] else 200
    return result, status

@api_bp.route('/subscriptions', methods=['POST'])
def create_subscription():
    """Create a new subscription for a single team."""
    try:
        data = request.get_json() or {}

        email = data.get('email')
        team_id = data.get('team_id')
        preferred_frequency = data.get('preferred_frequency', 'weekly')

        if not email or team_id is None:
            return jsonify({'error': 'email and team_id are required'}), 400

        payload, status = _process_subscriptions(email, [team_id], preferred_frequency)
        return jsonify(payload), status
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/subscriptions/bulk_create', methods=['POST'])
def bulk_create_subscriptions():
    """Create or update subscriptions for multiple teams in one request."""
    try:
        data = request.get_json() or {}
        email = data.get('email')
        team_ids = data.get('team_ids') or []
        preferred_frequency = data.get('preferred_frequency', 'weekly')

        if not email or not team_ids:
            return jsonify({'error': 'email and team_ids are required'}), 400

        payload, status = _process_subscriptions(email, team_ids, preferred_frequency)
        return jsonify(payload), status
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

def _create_email_token(email: str, purpose: str, metadata: dict | None = None, ttl_minutes: int = 60) -> EmailToken:
    token = str(uuid.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=ttl_minutes)
    row = EmailToken(
        token=token,
        email=email,
        purpose=purpose,
        expires_at=expires_at,
        metadata_json=json.dumps(metadata or {})
    )
    db.session.add(row)
    db.session.flush()
    logger.info(
        "Created email token id=%s purpose=%s email=%s expires_at=%s",
        row.id,
        purpose,
        email,
        expires_at.isoformat(),
    )
    return row

@api_bp.route('/subscriptions/request-manage-link', methods=['POST'])
def request_manage_link():
    """Issue a one-time manage token emailed to the user (email delivery handled elsewhere)."""
    try:
        data = request.get_json() or {}
        email = data.get('email')
        if not email:
            return jsonify({'error': 'email is required'}), 400
        # 30 days TTL so links in newsletters remain useful across sends
        tok = _create_email_token(email=email, purpose='manage', ttl_minutes=60 * 24 * 30)
        db.session.commit()
        return jsonify({'message': 'Manage link created', 'token': tok.token, 'expires_at': tok.expires_at.isoformat()})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/subscriptions/manage/<token>', methods=['GET'])
def get_manage_state(token: str):
    """Validate token and return current subscriptions for that email."""
    try:
        row = EmailToken.query.filter_by(token=token, purpose='manage').first()
        if not row or not row.is_valid():
            return jsonify({'error': 'invalid or expired token'}), 400
        subs = UserSubscription.query.filter_by(email=row.email, active=True).all()
        return jsonify({'email': row.email, 'subscriptions': [s.to_dict() for s in subs], 'expires_at': row.expires_at.isoformat()})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/subscriptions/manage/<token>', methods=['POST'])
def update_manage_state(token: str):
    """Upsert subscriptions for the token's email using team_ids and preferred_frequency."""
    try:
        row = EmailToken.query.filter_by(token=token, purpose='manage').first()
        if not row or not row.is_valid():
            return jsonify({'error': 'invalid or expired token'}), 400

        payload = request.get_json() or {}
        team_ids = payload.get('team_ids') or []
        preferred_frequency = payload.get('preferred_frequency', 'weekly')

        # Deactivate all current subscriptions for this email first
        UserSubscription.query.filter_by(email=row.email, active=True).update({UserSubscription.active: False})

        # Activate/create for provided list
        for raw_id in team_ids:
            team = Team.query.get(int(raw_id))
            if not team:
                continue
            existing = UserSubscription.query.filter_by(email=row.email, team_id=team.id).first()
            if existing:
                existing.active = True
                existing.preferred_frequency = preferred_frequency
                if not existing.unsubscribe_token:
                    existing.unsubscribe_token = str(uuid.uuid4())
            else:
                db.session.add(UserSubscription(
                    email=row.email,
                    team_id=team.id,
                    preferred_frequency=preferred_frequency,
                    active=True,
                    unsubscribe_token=str(uuid.uuid4()),
                ))

        # Optionally mark token as used immediately or let it remain valid until expiry
        # row.used_at = datetime.now(timezone.utc)

        db.session.commit()
        return jsonify({'message': 'Subscriptions updated'})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@api_bp.route('/subscriptions/unsubscribe', methods=['POST'])
def unsubscribe_by_email():
    """Unsubscribe an email address from one or more teams."""
    try:
        payload = request.get_json() or {}
        email_raw = payload.get('email')
        email = (email_raw or '').strip().lower()
        team_ids = payload.get('team_ids') or []

        if not email:
            auth_email = _get_authorized_email()
            if auth_email:
                email = auth_email.strip().lower()

        if not email:
            return jsonify({'error': 'email is required'}), 400

        query = UserSubscription.query.filter_by(email=email)
        parsed_ids: set[int] = set()
        for raw in team_ids:
            try:
                parsed_ids.add(int(raw))
            except (TypeError, ValueError):
                continue
        if parsed_ids:
            query = query.filter(UserSubscription.team_id.in_(parsed_ids))

        subs = query.all()
        if not subs:
            return jsonify({'message': 'No matching subscriptions found', 'count': 0}), 200

        count = 0
        unsub_team_names = []
        for sub in subs:
            if sub.active:
                sub.active = False
                count += 1
                if sub.team and sub.team.name:
                    unsub_team_names.append(sub.team.name)
        db.session.commit()

        if count:
            from src.services.admin_notify_service import notify_unsubscribe
            notify_unsubscribe(email, unsub_team_names[0] if unsub_team_names else None)

        return jsonify({'message': 'Unsubscribed successfully', 'count': count})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


def _unsubscribe_subscription_by_token(token: str) -> tuple[UserSubscription | None, str, int]:
    token = (token or '').strip()
    if not token:
        return None, 'missing_token', 400

    sub = UserSubscription.query.filter_by(unsubscribe_token=token).first()
    if not sub:
        return None, 'not_found', 404

    if sub.active:
        try:
            sub.active = False
            db.session.commit()
        except Exception:
            db.session.rollback()
            raise
        from src.services.admin_notify_service import notify_unsubscribe
        notify_unsubscribe(sub.email, sub.team.name if sub.team else None)
        return sub, 'unsubscribed', 200

    return sub, 'already_unsubscribed', 200


def _public_manage_url() -> str | None:
    base = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    if not base:
        return None
    manage_path = os.getenv('PUBLIC_MANAGE_PATH', '/manage')
    return f"{base}{manage_path}"


@api_bp.route('/subscriptions/unsubscribe/<token>', methods=['GET', 'POST'])
def token_unsubscribe(token: str):
    """Unsubscribe a single subscription by its unsubscribe token.

    POST returns JSON for programmatic callers. GET immediately unsubscribes
    and renders a lightweight confirmation page suitable for email links.
    """
    if request.method == 'POST':
        try:
            sub, status, code = _unsubscribe_subscription_by_token(token)
        except Exception as e:
            logger.exception('Error unsubscribing via token (POST)')
            return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

        if status == 'missing_token':
            return jsonify({'error': 'token is required'}), code
        if status == 'not_found':
            return jsonify({'error': 'invalid token'}), code

        message = 'Unsubscribed successfully' if status == 'unsubscribed' else 'Subscription already inactive'
        return jsonify({'message': message}), code

    # GET: render confirmation page
    try:
        sub, status, code = _unsubscribe_subscription_by_token(token)
    except Exception as e:
        logger.exception('Error unsubscribing via token (GET)')
        error_ctx = {
            'status': 'error',
            'headline': 'Something went wrong',
            'body': 'We were unable to process your unsubscribe request. Please try again later.',
            'manage_url': _public_manage_url(),
        }
        return render_template('unsubscribe_confirmation.html', **error_ctx), 500

    manage_url = _public_manage_url()
    team_name = sub.team.name if sub and getattr(sub, 'team', None) else None

    if status == 'missing_token':
        ctx = {
            'status': 'error',
            'headline': 'Invalid unsubscribe link',
            'body': 'The unsubscribe link is missing required information. Please check the email and try again.',
            'manage_url': manage_url,
            'team_name': team_name,
        }
    elif status == 'not_found':
        ctx = {
            'status': 'error',
            'headline': 'Link expired or invalid',
            'body': 'We could not find a subscription for this link. It may have already been used or expired.',
            'manage_url': manage_url,
            'team_name': team_name,
        }
    elif status == 'unsubscribed':
        ctx = {
            'status': 'ok',
            'headline': 'You are unsubscribed',
            'body': 'You will no longer receive updates for this team. You can manage other preferences anytime.',
            'manage_url': manage_url,
            'team_name': team_name,
            'email': sub.email if sub else None,
        }
    else:  # already_unsubscribed
        ctx = {
            'status': 'ok',
            'headline': 'Already unsubscribed',
            'body': 'This email was already unsubscribed from this team. No further action is required.',
            'manage_url': manage_url,
            'team_name': team_name,
            'email': sub.email if sub else None,
        }

    return render_template('unsubscribe_confirmation.html', **ctx), code


@api_bp.route('/subscriptions/one-click-unsubscribe/<token>', methods=['POST'])
def one_click_unsubscribe(token: str):
    """RFC 8058 One-Click Unsubscribe endpoint for email clients.
    
    This endpoint is designed for email providers (Gmail, Yahoo, etc.) that 
    implement one-click unsubscribe via the List-Unsubscribe-Post header.
    
    The email client sends a POST request with body: List-Unsubscribe=One-Click
    
    Returns 200 on success (required by RFC 8058).
    """
    try:
        # RFC 8058 specifies the body should be "List-Unsubscribe=One-Click"
        # but we accept any POST to this endpoint as valid
        body = request.get_data(as_text=True) or ''
        content_type = request.content_type or ''
        
        logger.info(
            'One-click unsubscribe request: token=%s content_type=%s body_preview=%s',
            token[:8] + '...' if len(token) > 8 else token,
            content_type,
            body[:100] if body else '(empty)'
        )
        
        sub, status, code = _unsubscribe_subscription_by_token(token)
        
        if status == 'missing_token':
            # Return 200 anyway per RFC 8058 best practices
            # (some clients don't handle non-200 well)
            logger.warning('One-click unsubscribe: missing token')
            return '', 200
        
        if status == 'not_found':
            logger.warning('One-click unsubscribe: token not found - %s', token[:8] + '...')
            return '', 200
        
        if status in ('unsubscribed', 'already_unsubscribed'):
            logger.info('One-click unsubscribe successful for token %s', token[:8] + '...')
            return '', 200
        
        return '', 200
        
    except Exception as e:
        logger.exception('One-click unsubscribe failed for token')
        # Still return 200 to avoid retry loops from email clients
        return '', 200


def _build_unsubscribe_headers(unsubscribe_url: str, one_click_url: str) -> dict:
    """Build RFC 8058 compliant List-Unsubscribe headers.
    
    Args:
        unsubscribe_url: URL for the regular unsubscribe page (GET)
        one_click_url: URL for the one-click POST endpoint
        
    Returns:
        dict: Headers to include in the email
    """
    if not unsubscribe_url:
        return {}
    
    return {
        # List-Unsubscribe can include both mailto: and https: URLs
        # We provide the HTTPS URL for the unsubscribe page
        'List-Unsubscribe': f'<{unsubscribe_url}>',
        # List-Unsubscribe-Post enables one-click unsubscribe
        # The value tells the email client what to POST
        'List-Unsubscribe-Post': 'List-Unsubscribe=One-Click',
    }


@api_bp.route('/verify/request', methods=['POST'])
def request_verification_token():
    """Issue a verification token for confirming email ownership."""
    try:
        data = request.get_json() or {}
        email = data.get('email')
        if not email:
            return jsonify({'error': 'email is required'}), 400
        # 48 hours TTL for verification
        tok = _create_email_token(email=email, purpose='verify', ttl_minutes=60 * 24 * 2)
        db.session.commit()
        return jsonify({'message': 'Verification token created', 'token': tok.token, 'expires_at': tok.expires_at.isoformat()})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/verify/<token>', methods=['POST'])
def verify_email_token(token: str):
    """Mark verification token as used; handles generic verification and subscription confirmation."""
    try:
        row = EmailToken.query.filter_by(token=token).first()
        if not row or not row.is_valid():
            return jsonify({'error': 'invalid or expired token'}), 400

        purpose = (row.purpose or '').strip().lower()
        if purpose == 'subscribe_confirm':
            meta = {}
            try:
                meta = json.loads(row.metadata_json or '{}')
            except Exception:
                meta = {}
            team_ids_raw = meta.get('team_ids') or []
            preferred_frequency = meta.get('preferred_frequency', 'weekly')
            try:
                team_ids = [int(tid) for tid in team_ids_raw]
            except Exception:
                team_ids = []
            if not team_ids:
                return jsonify({'error': 'Token metadata missing team ids'}), 400
            result = _activate_subscriptions(row.email, team_ids, preferred_frequency)
            row.used_at = datetime.now(timezone.utc)
            db.session.commit()

            if result['created_count'] or result['updated_count']:
                from src.services.admin_notify_service import notify_subscription_change
                team_rows = Team.query.filter(Team.id.in_(team_ids)).all()
                confirmed_names = [t.name or f'Team #{t.id}' for t in team_rows]
                notify_subscription_change(
                    row.email, confirmed_names,
                    created=result['created_count'], reactivated=result['updated_count'],
                )

            status = 201 if result['created_count'] else 200
            return jsonify({
                'message': 'Subscriptions confirmed',
                'email': row.email,
                **result,
            }), status

        if purpose == 'verify':
            row.used_at = datetime.now(timezone.utc)
            db.session.commit()
            return jsonify({'message': 'Email verified', 'email': row.email})

        return jsonify({'error': f'Unsupported token purpose: {purpose or "unknown"}'}), 400
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/subscriptions/<int:subscription_id>', methods=['DELETE'])
def delete_subscription(subscription_id):
    """Unsubscribe from newsletter."""
    try:
        subscription = UserSubscription.query.get_or_404(subscription_id)
        subscription.active = False
        db.session.commit()
        
        return jsonify({'message': 'Unsubscribed successfully'})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

# Statistics endpoints
@api_bp.route('/stats/overview', methods=['GET'])
def get_overview_stats():
    """Get overview statistics."""
    try:
        # current_season e.g. "2025-26"; also have start-year
        current_season_slug = api_client.current_season
        season_start_year = api_client.current_season_start_year
        if not current_season_slug and season_start_year:
            current_season_slug = f"{season_start_year}-{str(season_start_year + 1)[-2:]}"

        # Distinct teams with active tracked players
        teams_with_active_loans = (
            db.session.query(TrackedPlayer.team_id)
            .filter(TrackedPlayer.is_active.is_(True))
            .distinct()
            .count()
        )

        season_loans_count = TrackedPlayer.query.filter_by(is_active=True).count()

        # Count unique teams (deduplicated by team_id) to avoid counting same team across seasons
        unique_team_count = (
            db.session.query(db.func.count(db.func.distinct(Team.team_id)))
            .filter(Team.is_active.is_(True))
            .scalar() or 0
        )

        stats = {
            'total_teams': unique_team_count,
            'european_leagues': League.query.filter_by(is_european_top_league=True).count(),
            'total_active_loans': TrackedPlayer.query.filter_by(is_active=True).count(),
            'season_loans': season_loans_count,
            'early_terminations': 0,
            'teams_with_loans': teams_with_active_loans,
            'total_subscriptions': UserSubscription.query.filter_by(active=True).count() if hasattr(UserSubscription, 'active') else UserSubscription.query.count(),
            'total_newsletters': Newsletter.query.filter_by(published=True).count(),
            'current_season': current_season_slug
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

# Data sync endpoints
@api_bp.route('/init-data', methods=['POST'])
def init_data():
    """Initialize sample data."""
    try:
        # This would normally sync from API-Football
        # For now, just return success
        return jsonify({
            'message': 'Data initialized successfully',
            'teams_synced': Team.query.count(),
            'leagues_synced': League.query.count()
        })
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/sync-leagues', methods=['POST'])
@require_api_key
def sync_leagues():
    """Sync European leagues from API-Football."""
    try:
        # Use current season for league sync (league metadata doesn't change much)
        season = api_client.current_season_start_year
        leagues_data = api_client.get_european_leagues(season)
        synced_count = 0
        
        for league_data in leagues_data:
            league_info = league_data.get('league', {})
            country_info = league_data.get('country', {})
            seasons = league_data.get('seasons', [])
            current_season = next((s for s in seasons if s.get('current')), seasons[0] if seasons else {})
            
            # Check if league exists
            existing = League.query.filter_by(league_id=league_info.get('id')).first()
            if existing:
                # Update existing league
                existing.name = league_info.get('name')
                existing.country = country_info.get('name')
                existing.season = current_season.get('year', api_client.current_season_start_year)
                existing.logo = league_info.get('logo')
            else:
                # Create new league
                league = League(
                    league_id=league_info.get('id'),
                    name=league_info.get('name'),
                    country=country_info.get('name'),
                    season=current_season.get('year', api_client.current_season_start_year),
                    is_european_top_league=True,
                    logo=league_info.get('logo')
                )
                db.session.add(league)
            
            synced_count += 1
        
        db.session.commit()
        return jsonify({
            'message': f'Successfully synced {synced_count} European leagues',
            'synced_leagues': synced_count,
            'current_season': api_client.current_season
        })
        
    except Exception as e:
        logger.error(f"Error syncing leagues: {e}")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/sync-teams/<int:season>', methods=['POST'])
@require_api_key
def sync_teams(season):
    """Sync teams from API-Football."""
    try:
        # season is provided as path parameter by Flask
        if not season:
            return jsonify({'error': 'Season parameter is required'}), 400
            
        # Get all European teams
        all_teams = api_client.get_all_european_teams(season)
        synced_count = 0
        
        for team_data in all_teams:
            team_info = team_data.get('team', {})
            league_info = team_data.get('league_info', {})
            
            # Find the league
            league = League.query.filter_by(league_id=league_info.get('id')).first()
            if not league:
                continue
            
            # Check if team exists for this season
            existing = Team.query.filter_by(team_id=team_info.get('id'), season=season).first()
            if existing:
                # Update existing team
                existing.name = team_info.get('name')
                existing.country = team_info.get('country')
                existing.founded = team_info.get('founded')
                existing.logo = team_info.get('logo')
                existing.league_id = league.id
            else:
                # Create new team for this season
                team = Team(
                    team_id=team_info.get('id'),
                    name=team_info.get('name'),
                    country=team_info.get('country'),
                    founded=team_info.get('founded'),
                    logo=team_info.get('logo'),
                    league_id=league.id,
                    season=season,
                    is_active=True
                )
                db.session.add(team)
            
            synced_count += 1
        
        db.session.commit()
        return jsonify({
            'message': f'Successfully synced {synced_count} teams from European leagues for season {season}',
            'synced_teams': synced_count,
            'season': season
        })
        
    except Exception as e:
        logger.error(f"Error syncing teams: {e}")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

# Newsletter rendering helpers
try:
    # Reuse lint/enrich if available via weekly agent
    from src.agents.weekly_agent import lint_and_enrich  # type: ignore
except Exception:
    def lint_and_enrich(x: dict) -> dict:  # fallback
        return x

def _load_newsletter_json(n: Newsletter) -> dict | None:
    try:
        raw = n.structured_content or n.content or "{}"
        data = json.loads(raw)
        if isinstance(data, dict):
            try:
                data = lint_and_enrich(data)
            except Exception:
                pass
            
            # Inject YouTube links from the junction table
            try:
                youtube_links = NewsletterPlayerYoutubeLink.query.filter_by(newsletter_id=n.id).all()
                if youtube_links:
                    # Create lookup dictionary by player_id
                    links_by_player_id = {}
                    
                    for link in youtube_links:
                        if link.player_id:
                            links_by_player_id[link.player_id] = link.youtube_link
                    
                    # Inject links into player items
                    sections = data.get('sections', [])
                    if isinstance(sections, list):
                        for section in sections:
                            if isinstance(section, dict):
                                items = section.get('items', [])
                                if isinstance(items, list):
                                    for item in items:
                                        if isinstance(item, dict):
                                            # Check for tracked player
                                            player_id = item.get('player_id')
                                            if player_id and player_id in links_by_player_id:
                                                youtube_url = links_by_player_id[player_id]
                                                # Add to links array
                                                existing_links = item.get('links', [])
                                                if not isinstance(existing_links, list):
                                                    existing_links = []
                                                # Add YouTube link with title
                                                youtube_link_obj = {
                                                    'url': youtube_url,
                                                    'title': 'YouTube Highlights'
                                                }
                                                # Check if not already present
                                                if not any(
                                                    (isinstance(l, dict) and l.get('url') == youtube_url) or 
                                                    (isinstance(l, str) and l == youtube_url)
                                                    for l in existing_links
                                                ):
                                                    existing_links.insert(0, youtube_link_obj)
                                                item['links'] = existing_links
            except Exception as e:
                logger.exception('Failed to inject YouTube links into newsletter')
                pass
            
            return data
        return None
    except Exception:
        return None


# Field names inside player items that hold base64 chart data URIs.
# Each one is typically 50-200 KB; with 6 charts × 10 players × 10 newsletters
# they push the LIST endpoint payload past 25 MB. Strip them in any context
# that doesn't actually render the charts (i.e. the LIST endpoint).
_HEAVY_CHART_FIELDS = (
    'radar_chart_url',
    'trend_chart_url',
    'match_card_url',
    'stat_table_url',
    'rating_graph_url',
    'minutes_graph_url',
)


def _strip_heavy_fields_for_list(enriched: dict | None) -> dict | None:
    """Return a slimmed copy of `enriched_content` with chart base64s and
    embedded rendered HTML removed.

    Used by the LIST endpoint so a 28 MB response shrinks to ~1 MB. The
    detail endpoint still returns the full payload via _load_newsletter_json.
    Walks both the flat `items` shape and the `subsections` shape that the
    weekly agent emits when players span multiple loan leagues.
    """
    if not isinstance(enriched, dict):
        return enriched

    # Shallow copy then mutate. The original dict is cached by SQLAlchemy
    # so we must not strip from it in-place.
    out: dict = dict(enriched)

    # Drop the rendered HTML blobs (web_html / email_html). They embed the
    # same chart images and add several MB on top of the chart_url fields.
    if 'rendered' in out:
        out.pop('rendered', None)

    sections = out.get('sections')
    if isinstance(sections, list):
        new_sections: list = []
        for sec in sections:
            if not isinstance(sec, dict):
                new_sections.append(sec)
                continue
            new_sec = dict(sec)
            if 'subsections' in new_sec and isinstance(new_sec['subsections'], list):
                new_sec['subsections'] = [
                    {**sub, 'items': [_strip_item(i) for i in (sub.get('items') or [])]}
                    if isinstance(sub, dict) else sub
                    for sub in new_sec['subsections']
                ]
            elif isinstance(new_sec.get('items'), list):
                new_sec['items'] = [_strip_item(i) for i in new_sec['items']]
            new_sections.append(new_sec)
        out['sections'] = new_sections
    return out


def _strip_item(item: dict) -> dict:
    """Drop chart base64 fields from a single player item."""
    if not isinstance(item, dict):
        return item
    new_item = dict(item)
    for field in _HEAVY_CHART_FIELDS:
        new_item.pop(field, None)
    return new_item


def _plain_text_from_news(data: dict, meta: Newsletter) -> str:
    team = meta.team.name if meta.team else ""
    title = data.get("title") or meta.title or "Weekly Loan Update"
    rng = data.get("range") or [None, None]
    summary = data.get("summary") or ""
    lines: list[str] = []
    lines.append(f"{title}")
    if team:
        lines.append(f"Team: {team}")
    if rng and rng[0] and rng[1]:
        lines.append(f"Week: {rng[0]} – {rng[1]}")
    if summary:
        lines.append("")
        lines.append(summary)
    highlights = data.get("highlights") or []
    if highlights:
        lines.append("")
        lines.append("Highlights:")
        for h in highlights:
            lines.append(f"- {h}")
    for sec in (data.get("sections") or []):
        if not isinstance(sec, dict):
            continue
        st = sec.get("title") or ""
        items = sec.get("items") or []
        if st:
            lines.append("")
            lines.append(st)
            lines.append("-" * len(st))
        for it in items:
            if not isinstance(it, dict):
                continue
            pname = it.get("player_name") or ""
            loan_team = it.get("loan_team") or it.get("loan_team_name") or ""
            wsum = it.get("week_summary") or ""
            stats = it.get("stats") or {}
            stat_str = (
                f"{int(stats.get('minutes', 0))}’ | "
                f"{int(stats.get('goals', 0))}G {int(stats.get('assists', 0))}A | "
                f"{int(stats.get('yellows', 0))}Y {int(stats.get('reds', 0))}R"
            )
            lines.append(f"• {pname} ({loan_team}) – {wsum}")
            lines.append(f"  {stat_str}")
            # Add graph URLs for markdown (Reddit)
            if it.get("rating_graph_url"):
                graph_url = _absolute_url(it["rating_graph_url"])
                lines.append(f"  📊 [Rating Graph]({graph_url})")
            if it.get("minutes_graph_url"):
                graph_url = _absolute_url(it["minutes_graph_url"])
                lines.append(f"  📊 [Minutes Graph]({graph_url})")
            notes = it.get("match_notes") or []
            for n in notes:
                lines.append(f"  - {n}")
    return "\n".join(lines).strip() + "\n"
def _newsletter_issue_slug(n: Newsletter) -> str:
    slug_value = getattr(n, 'public_slug', None)
    if slug_value:
        return slug_value
    slug_value = compose_newsletter_public_slug(
        team_name=n.team.name if n.team else None,
        newsletter_type=n.newsletter_type,
        week_start=n.week_start_date,
        week_end=n.week_end_date,
        issue_date=n.issue_date,
        identifier=n.id,
    )
    if slug_value:
        n.public_slug = slug_value
        return slug_value
    if n.week_end_date:
        return n.week_end_date.isoformat()
    if n.issue_date:
        return n.issue_date.isoformat()
    created = _as_utc(n.created_at) if n.created_at else datetime.now(timezone.utc)
    return created.date().isoformat()


def _public_base_url(default: str | None = None) -> str:
    base = (os.getenv('PUBLIC_BASE_URL') or os.getenv('PUBLIC_API_BASE_URL') or default or '').strip()
    if base:
        return base.rstrip('/')
    try:
        return (request.url_root or '').rstrip('/')
    except RuntimeError:
        return ''


def _absolute_url(path: str) -> str:
    if not path:
        return path
    if path.startswith(('http://', 'https://', 'data:')):
        return path
    base = _public_base_url()
    if not base:
        return path
    normalized = path if path.startswith('/') else f'/{path}'
    return f'{base}{normalized}'


def _static_url(rel_path: str | None) -> str | None:
    if not rel_path:
        return None
    rel = rel_path.lstrip('/')
    return _absolute_url(f'/static/{rel}')


def _truncate_plain(text: str, limit: int = 200) -> str:
    clean = sanitize_plain_text(text or '')
    stripped = clean.strip()
    if len(stripped) <= limit:
        return stripped
    truncated = stripped[:limit - 1].rstrip()
    return f"{truncated}…"


def _brand_logo_source() -> str:
    override = (os.getenv('GO_ON_LOAN_LOGO_PATH') or '').strip()
    if override:
        return override
    return '/static/assets/loan_army_assets/android-chrome-512x512.png'


def _load_logo_image(source: str | None):
    if not source:
        return None
    try:
        from PIL import Image, ImageFile
    except ImportError:
        return None

    ImageFile.LOAD_TRUNCATED_IMAGES = True
    src = source.strip()
    if not src:
        return None

    try:
        if src.startswith(('http://', 'https://')):
            resp = requests.get(src, timeout=6)
            resp.raise_for_status()
            with BytesIO(resp.content) as buffer:
                with Image.open(buffer) as img:
                    return img.convert('RGBA')

        candidate_paths: list[str] = []
        static_folder = getattr(current_app, 'static_folder', None)

        if src.startswith('/static/') and static_folder:
            candidate_paths.append(os.path.join(static_folder, src[len('/static/') :]))
        if src.startswith('/') and static_folder:
            candidate_paths.append(os.path.join(static_folder, src.lstrip('/')))
        if os.path.isabs(src):
            candidate_paths.append(src)
        if static_folder and not os.path.isabs(src):
            candidate_paths.append(os.path.join(static_folder, src))

        for path in candidate_paths:
            if path and os.path.exists(path):
                with Image.open(path) as img:
                    return img.convert('RGBA')
    except Exception as exc:
        logger.debug('Failed to load logo image from %s: %s', source, exc, exc_info=True)
    return None


def _ensure_newsletter_cover_image(n: Newsletter, *, team_logo: str | None) -> str | None:
    static_folder = getattr(current_app, 'static_folder', None)
    if not static_folder:
        return None

    slug = _newsletter_issue_slug(n)
    rel_dir = os.path.join('newsletters', slug)
    target_dir = os.path.join(static_folder, rel_dir)
    os.makedirs(target_dir, exist_ok=True)

    filename = 'cover.jpg'
    target_path = os.path.join(target_dir, filename)
    if os.path.isfile(target_path):
        return os.path.join(rel_dir, filename)

    try:
        from PIL import Image, ImageDraw, ImageOps
    except ImportError:
        logger.warning('Pillow not installed; falling back to static cover copy')
        fallback_src = _brand_logo_source()
        static_folder = getattr(current_app, 'static_folder', None)
        candidate = None
        if fallback_src.startswith('/static/') and static_folder:
            candidate = os.path.join(static_folder, fallback_src[len('/static/'):])
        elif os.path.isabs(fallback_src):
            candidate = fallback_src
        elif static_folder:
            candidate = os.path.join(static_folder, fallback_src)
        if candidate and os.path.exists(candidate):
            try:
                shutil.copyfile(candidate, target_path)
                return os.path.join(rel_dir, filename)
            except Exception as exc:
                logger.warning('Failed to copy fallback cover %s -> %s: %s', candidate, target_path, exc)
        return None

    canvas = Image.new('RGB', (1200, 630), '#050A1E')
    draw = ImageDraw.Draw(canvas)

    brand_logo = _load_logo_image(_brand_logo_source())
    primary_logo = _load_logo_image(team_logo)

    logos = [logo for logo in (primary_logo, brand_logo) if logo is not None]
    if not logos:
        draw.rectangle([(0, 0), (canvas.width, canvas.height)], fill='#101942')
        draw.rectangle([(80, 120), (canvas.width - 80, canvas.height - 120)], outline='#23306b', width=12)
    else:
        processed: list[Image.Image | None] = []
        for logo in (primary_logo, brand_logo):
            if logo is None:
                processed.append(None)
                continue
            img = logo.copy()
            img = ImageOps.contain(img, (420, 420))
            processed.append(img)

        spacing = 120
        centre_y = canvas.height // 2

        if processed[0] is not None and len(processed) > 1 and processed[1] is not None:
            total_width = processed[0].width + processed[1].width + spacing
            start_x = max((canvas.width - total_width) // 2, 60)
            positions = [
                (start_x, centre_y - processed[0].height // 2),
                (start_x + processed[0].width + spacing, centre_y - processed[1].height // 2),
            ]
            active = [processed[0], processed[1]]
        else:
            existing = processed[0] or (processed[1] if len(processed) > 1 else None)
            if existing is None:
                existing = logos[0]
            positions = [((canvas.width - existing.width) // 2, centre_y - existing.height // 2)]
            active = [existing]

        draw.ellipse([(-320, -80), (canvas.width * 0.8, canvas.height + 180)], fill='#0C1544', outline=None)
        draw.rectangle([(0, canvas.height - 90), (canvas.width, canvas.height)], fill='#131C4E')

        for img, (pos_x, pos_y) in zip(active, positions, strict=False):
            if img is None:
                continue
            rgba = img.convert('RGBA')
            canvas.paste(rgba, (int(pos_x), int(pos_y)), mask=rgba)

    try:
        canvas.save(target_path, format='JPEG', quality=92, optimize=True)
        return os.path.join(rel_dir, filename)
    except Exception as exc:
        logger.warning('Failed to write newsletter cover %s: %s', target_path, exc)
        return None


def _format_iso8601(dt: datetime | None) -> str | None:
    if not dt:
        return None
    as_utc = _as_utc(dt)
    if not as_utc:
        return None
    trimmed = as_utc.replace(microsecond=0)
    iso = trimmed.isoformat()
    if iso.endswith('+00:00'):
        iso = iso[:-6] + 'Z'
    return iso


def _compute_newsletter_social_meta(n: Newsletter, context: dict[str, Any]) -> dict[str, Any]:
    title = context.get('title') or n.title or 'Weekly Loan Update'
    description = context.get('summary') or ''
    description = _truncate_plain(description)
    if not description:
        team_name = context.get('team_name') or (n.team.name if n.team else 'The Academy Watch')
        description = f'{team_name} weekly loan watch from The Academy Watch.'

    canonical_slug = _newsletter_issue_slug(n)
    canonical_url = _absolute_url(f'/newsletters/{canonical_slug}')

    team_logo = context.get('team_logo')
    cover_rel = _ensure_newsletter_cover_image(n, team_logo=team_logo)
    cover_url = _static_url(cover_rel)

    if n.published_date:
        published = _format_iso8601(n.published_date)
    elif n.issue_date:
        published_dt = datetime.combine(n.issue_date, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
        published = _format_iso8601(published_dt)
    else:
        published = None

    site_name = (os.getenv('SITE_NAME') or os.getenv('PUBLIC_SITE_NAME') or 'The Academy Watch').strip() or 'The Academy Watch'
    author = (os.getenv('ARTICLE_AUTHOR_NAME') or site_name).strip() or site_name
    twitter_handle = (os.getenv('TWITTER_HANDLE') or '@theacademywatch').strip()

    return {
        'title': title,
        'description': description,
        'canonical_url': canonical_url,
        'slug': canonical_slug,
        'og_url': canonical_url,
        'og_image': cover_url,
        'og_image_width': '1200' if cover_url else None,
        'og_image_height': '630' if cover_url else None,
        'site_name': site_name,
        'article_author': author,
        'published_time': published,
        'twitter_handle': twitter_handle if twitter_handle else None,
    }

# --- Newsletter delivery helpers ---
def _embed_image(path):
    if not path: return ''
    # Already a data URI (generated inline at newsletter creation time)
    if path.startswith('data:'):
        return path
    # Legacy /static/ path — try to read from disk and base64-encode
    if path.startswith('/static/'):
        try:
            clean_path = path.replace('/static/', '', 1)
            real_path = os.path.join(current_app.static_folder, clean_path)
            if os.path.exists(real_path):
                with open(real_path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode('utf-8')
                    return f"data:image/png;base64,{encoded}"
        except Exception as e:
            logging.error(f"Failed to embed image {path}: {e}")
    return path

def _collect_commentaries_for_newsletter(n: Newsletter) -> list[NewsletterCommentary]:
    """Return all active commentaries associated with a newsletter, including
    week-scoped entries whose newsletter_id may be null. Deduplicates by id."""
    seen: dict[int, NewsletterCommentary] = {}

    def _add(c: NewsletterCommentary | None):
        if not c or not getattr(c, 'is_active', False):
            return
        if c.id not in seen:
            seen[c.id] = c

    # Directly linked commentaries (relationship + explicit query for safety)
    for c in getattr(n, 'commentaries', []) or []:
        _add(c)
    if n.id:
        for c in NewsletterCommentary.query.filter_by(newsletter_id=n.id, is_active=True).all():
            _add(c)

    # Week-scoped commentaries by API team id (cross-season compatibility)
    api_team_id = None
    team_db_id = n.team_id
    if team_db_id:
        api_team_id = db.session.query(Team.team_id).filter(Team.id == team_db_id).scalar()

    if n.week_start_date and n.week_end_date:
        # Primary: join on API team id
        if api_team_id:
            rows = (
                NewsletterCommentary.query.join(Team)
                .filter(
                    Team.team_id == api_team_id,
                    NewsletterCommentary.week_start_date == n.week_start_date,
                    NewsletterCommentary.week_end_date == n.week_end_date,
                    NewsletterCommentary.is_active.is_(True)
                )
                .order_by(NewsletterCommentary.position.asc(), NewsletterCommentary.created_at.asc())
                .all()
            )
            for c in rows:
                _add(c)

        # Fallback: match by DB team_id when join data is missing (older rows)
        if team_db_id:
            rows = (
                NewsletterCommentary.query
                .filter(
                    NewsletterCommentary.team_id == team_db_id,
                    NewsletterCommentary.week_start_date == n.week_start_date,
                    NewsletterCommentary.week_end_date == n.week_end_date,
                    NewsletterCommentary.is_active.is_(True)
                )
                .order_by(NewsletterCommentary.position.asc(), NewsletterCommentary.created_at.asc())
                .all()
            )
            for c in rows:
                _add(c)

    # Stable ordering for presentation
    type_order = {'intro': 0, 'player': 1, 'summary': 2}
    commentaries = list(seen.values())
    commentaries.sort(key=lambda c: (
        type_order.get(getattr(c, 'commentary_type', ''), 99),
        getattr(c, 'position', 0) or 0,
        getattr(c, 'created_at', datetime.min) or datetime.min,
    ))
    return commentaries


def _fetch_community_takes_for_newsletter(n: Newsletter) -> list[dict]:
    """Return approved community takes attached to a newsletter (or recent
    team-level takes as fallback when none are explicitly linked).

    Used by both `_newsletter_render_context` (Flask template path, for
    rendered email/web HTML) and `get_newsletter` (JSON API path, for the
    React newsletter view). Keep the two call sites in sync via this helper.
    """
    community_takes: list[dict] = []
    takes_query = CommunityTake.query.filter_by(status='approved')
    if n.id:
        newsletter_takes = takes_query.filter_by(newsletter_id=n.id).all()
        community_takes.extend([t.to_dict() for t in newsletter_takes])

    # Fallback: when no takes are explicitly attached to this newsletter,
    # surface the most recent team-level takes that aren't tied to a
    # different newsletter.
    if n.team_id and not community_takes:
        team_takes = takes_query.filter_by(
            team_id=n.team_id, newsletter_id=None
        ).order_by(CommunityTake.created_at.desc()).limit(5).all()
        community_takes.extend([t.to_dict() for t in team_takes])

    return community_takes


def _build_twitter_takes_by_player(community_takes: list[dict]) -> dict[int, list[dict]]:
    """Group twitter-source community takes by `player_id` so the per-player
    commentary card can render tweets about that specific player inline.
    Tweets without a `player_id` are surfaced as team-level via `twitter_takes`.
    """
    grouped: dict[int, list[dict]] = {}
    for take in community_takes:
        if take.get('source_type') == 'twitter' and take.get('player_id'):
            grouped.setdefault(take['player_id'], []).append(take)
    return grouped


def _newsletter_render_context(n: Newsletter) -> dict[str, Any]:
    data = _load_newsletter_json(n) or {}
    team_logo = data.get('team_logo')
    if not team_logo and n.team and getattr(n.team, 'logo', None):
        team_logo = n.team.logo

    # Generate web URL for newsletter
    canonical_slug = _newsletter_issue_slug(n)
    web_url = _absolute_url(f'/newsletters/{canonical_slug}')

    commentaries = _collect_commentaries_for_newsletter(n)
    intro_commentary = []
    summary_commentary = []
    player_commentary_map = {}

    for c in commentaries:
        if c.commentary_type == 'intro':
            intro_commentary.append(c.to_dict())
        elif c.commentary_type == 'summary':
            summary_commentary.append(c.to_dict())
        elif c.commentary_type == 'player' and c.player_id:
            player_commentary_map.setdefault(c.player_id, []).append(c.to_dict())

    # Buy Me a Coffee button URL - use official CDN image
    bmc_button_url = 'https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png'

    # Public base URL for player links in emails
    public_base_url = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')

    # Fetch approved community takes + group twitter takes by player.
    # Both helpers are also used by the JSON API endpoint (`get_newsletter`)
    # so the React renderer sees the same shape as the Flask templates.
    community_takes = _fetch_community_takes_for_newsletter(n)
    twitter_takes_by_player = _build_twitter_takes_by_player(community_takes)

    # Submit take URL for footer
    submit_take_url = f"{public_base_url}/submit-take" if public_base_url else None

    # Flag/report URL for data corrections
    flag_base_url = f"{public_base_url}/flag" if public_base_url else None

    # Fetch academy appearances for players in this newsletter's date range.
    # Uses TrackedPlayer (the current model) — status='academy' means they're
    # playing in youth/academy competitions, not yet on loan or first team.
    academy_appearances = []
    if n.week_start_date and n.week_end_date and n.team_id:
        tracked_players = TrackedPlayer.query.filter(
            TrackedPlayer.team_id == n.team_id,
            TrackedPlayer.is_active.is_(True),
            TrackedPlayer.status == 'academy',
        ).all()

        if tracked_players:
            player_api_ids = [p.player_api_id for p in tracked_players if p.player_api_id]
            if player_api_ids:
                appearances = AcademyAppearance.query.filter(
                    AcademyAppearance.player_id.in_(player_api_ids),
                    AcademyAppearance.fixture_date >= n.week_start_date,
                    AcademyAppearance.fixture_date <= n.week_end_date,
                ).order_by(AcademyAppearance.fixture_date.desc()).all()
                academy_appearances = [a.to_dict() for a in appearances]

    context: dict[str, Any] = {
        'embed_image': _embed_image,
        'meta': n,
        'team_name': n.team.name if n.team else '',
        'title': data.get('title') or n.title,
        'range': data.get('range'),
        'summary': data.get('summary'),
        'highlights': data.get('highlights') or [],
        'sections': data.get('sections') or [],
        'toc': data.get('toc') or [],
        'by_numbers': data.get('by_numbers') or {},
        'fan_pulse': data.get('fan_pulse') or [],
        'team_logo': team_logo,
        'web_url': web_url,
        'public_slug': canonical_slug,
        'public_base_url': public_base_url,
        'intro_commentary': intro_commentary,
        'summary_commentary': summary_commentary,
        'player_commentary_map': player_commentary_map,
        'bmc_button_url': bmc_button_url,
        'community_takes': community_takes,
        'twitter_takes': [t for t in community_takes if t.get('source_type') == 'twitter'],
        'twitter_takes_by_player': twitter_takes_by_player,
        'submit_take_url': submit_take_url,
        'flag_base_url': flag_base_url,
        'academy_appearances': academy_appearances,
    }
    context['social_meta'] = _compute_newsletter_social_meta(n, context)
    return context

def _deliver_newsletter_via_webhook(
    n: Newsletter,
    *,
    recipients: list[str] | None = None,
    subject_override: str | None = None,
    webhook_url_override: str | None = None,
    http_method_override: str | None = None,
    dry_run: bool = False,
) -> dict:
    """Render newsletter to HTML/TXT and send via email service.
    Returns dict with 'status', 'http_status', and 'recipient_count'.
    
    Note: webhook_url_override and http_method_override are kept for backward
    compatibility but are ignored when using the direct email service.
    """
    # Check email service is configured
    if not email_service.is_configured():
        raise RuntimeError('Email service is not configured (set MAILGUN_* or SMTP_* env vars)')

    team_ids: list[int] = []
    if n.team_id:
        try:
            team_ids.append(int(n.team_id))
        except (TypeError, ValueError):
            pass

    team_api_id = None
    if getattr(n, 'team', None) is not None:
        team_api_id = getattr(n.team, 'team_id', None)
    if team_api_id is None and n.team_id:
        try:
            team_row = Team.query.with_entities(Team.team_id).filter(Team.id == n.team_id).first()
            if team_row:
                team_api_id = team_row[0]
        except Exception:
            team_api_id = None

    if team_api_id is not None:
        try:
            alt_ids = (
                Team.query.with_entities(Team.id)
                .filter(Team.team_id == team_api_id)
                .all()
            )
            team_ids.extend(int(row[0]) for row in alt_ids if row and row[0])
        except Exception:
            pass

    team_ids = list(dict.fromkeys(team_ids))

    if team_ids:
        subs = (
            UserSubscription.query
            .filter(UserSubscription.active.is_(True))
            .filter(UserSubscription.team_id.in_(team_ids))
            .all()
        )
    else:
        subs = []

    def _normalize_email(value: str | None) -> str:
        return (value or '').strip().lower()

    sub_lookup: dict[str, UserSubscription] = {}
    ordered_sub_emails: list[str] = []
    for s in subs:
        if s.email_bounced:
            continue
        raw_email = (s.email or '').strip()
        key = _normalize_email(raw_email)
        if not raw_email or not key:
            continue
        if key not in sub_lookup:
            sub_lookup[key] = s
            ordered_sub_emails.append(raw_email)

    # Gather recipients from active team subscriptions if not provided
    if recipients is None:
        recipients = ordered_sub_emails

    recipients = [r for r in (recipients or []) if (r or '').strip()]
    total_recipients = len(recipients)
    if total_recipients == 0:
        return {
            'status': 'no_recipients',
            'http_status': None,
            'recipient_count': 0,
            'provider': 'none',
            'response_text': '',
        }

    # Render content
    ctx = _newsletter_render_context(n)
    text_base = _plain_text_from_news(_load_newsletter_json(n) or {}, n)
    subject = subject_override or (ctx['title'] or 'Weekly Loan Update')

    from_addr = {
        'name': os.getenv('EMAIL_FROM_NAME', 'The Academy Watch'),
        'email': os.getenv('EMAIL_FROM_ADDRESS', 'mail@theacademywatch.com'),
    }

    # Optional public base URL for manage/unsubscribe links if the n8n flow uses it
    public_base = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    link_base = os.getenv('NEWSLETTER_LINK_BASE_URL', '').rstrip('/')
    unsubscribe_base = (
        link_base
        or os.getenv('PUBLIC_UNSUBSCRIBE_BASE_URL', '').rstrip('/')
        or os.getenv('PUBLIC_API_BASE_URL', '').rstrip('/')
        or public_base
    )
    manage_url = _public_manage_url()

    meta_base = {
        'issue_date': n.issue_date.isoformat() if n.issue_date else None,
        'week_start': n.week_start_date.isoformat() if n.week_start_date else None,
        'week_end': n.week_end_date.isoformat() if n.week_end_date else None,
        'public_base_url': public_base or None,
        'dry_run': bool(dry_run),
    }

    delivered_count = 0
    digest_queued_count = 0
    failures: list[dict[str, Any]] = []
    last_status_code: int | None = None
    last_response_text = ''
    last_provider = 'none'

    # Import digest queue function
    from src.services.newsletter_deadline_service import queue_newsletter_for_digest

    for email in recipients:
        normalized_email = _normalize_email(email)
        subscription = sub_lookup.get(normalized_email)
        
        # Check if user prefers digest delivery
        user_account = UserAccount.query.filter_by(email=normalized_email).first()
        user_prefers_digest = (
            user_account 
            and getattr(user_account, 'email_delivery_preference', 'individual') == 'digest'
        )
        
        # If user prefers digest, queue instead of sending immediately
        if user_prefers_digest and user_account:
            try:
                queued = queue_newsletter_for_digest(user_account.id, n.id)
                if queued:
                    digest_queued_count += 1
                    logger.info(f"Queued newsletter {n.id} for digest delivery to {email}")
                else:
                    logger.debug(f"Newsletter {n.id} already queued for {email}")
                continue  # Skip sending individual email
            except Exception as queue_err:
                logger.warning(f"Failed to queue for digest, falling back to individual: {queue_err}")
                # Fall through to send individual email
        
        unsubscribe_url = None
        one_click_url = None
        email_headers = {}
        
        if subscription and subscription.unsubscribe_token:
            token = subscription.unsubscribe_token
            # Regular unsubscribe page (for link in email body)
            token_path = f"/subscriptions/unsubscribe/{token}"
            if unsubscribe_base:
                unsubscribe_url = f"{unsubscribe_base.rstrip('/')}{token_path}"
            else:
                unsubscribe_url = token_path
            
            # One-click unsubscribe endpoint (for RFC 8058 / List-Unsubscribe-Post header)
            one_click_path = f"/api/subscriptions/one-click-unsubscribe/{token}"
            if unsubscribe_base:
                one_click_url = f"{unsubscribe_base.rstrip('/')}{one_click_path}"
            
            # Build RFC 8058 compliant headers for email providers
            if one_click_url:
                email_headers = _build_unsubscribe_headers(unsubscribe_url, one_click_url)

        html = render_template(
            'newsletter_email.html',
            **ctx,
            unsubscribe_url=unsubscribe_url,
            manage_url=manage_url,
        )

        text = text_base
        if unsubscribe_url:
            text = f"{text_base}\n\nTo unsubscribe from this team, visit: {unsubscribe_url}\n"

        # Send via email service
        try:
            result = email_service.send_email(
                to=email,
                subject=subject,
                html=html,
                text=text,
                from_name=from_addr['name'],
                from_email=from_addr['email'],
                tags=['newsletter', f'newsletter_{n.id}'],
            )
            last_status_code = result.http_status or (200 if result.success else 500)
            last_response_text = result.message_id or result.error or ''
            last_provider = result.provider
            
            if result.success:
                delivered_count += 1
            else:
                failures.append({
                    'email': email,
                    'error': result.error,
                    'http_status': last_status_code,
                    'provider': result.provider,
                })
        except Exception as exc:
            last_status_code = 500
            last_response_text = str(exc)[:5000]
            last_provider = 'error'
            failures.append({
                'email': email,
                'error': str(exc),
                'http_status': last_status_code,
            })

    # Calculate status including digest queued
    total_processed = delivered_count + digest_queued_count
    status = 'ok' if total_processed == total_recipients else ('partial' if total_processed else 'error')
    result: dict[str, Any] = {
        'status': status,
        'http_status': last_status_code,
        'recipient_count': total_recipients,
        'delivered_count': delivered_count,
        'digest_queued_count': digest_queued_count,
        'provider': last_provider,
        'response_text': last_response_text,
    }
    if failures:
        result['failures'] = failures
    return result

@api_bp.route('/newsletters/<int:newsletter_id>/preview', methods=['POST'])
@require_api_key
def preview_newsletter_custom(newsletter_id: int):
    try:
        newsletter = Newsletter.query.get_or_404(newsletter_id)
        
        # Ensure we reload fresh content if structured_content is available
        data = _load_newsletter_json(newsletter) or {}
        
        # Determine active commentaries based on request
        payload = request.get_json() or {}
        journalist_ids = payload.get('journalist_ids')
        render_mode = payload.get('render_mode', 'web')  # 'web' or 'email'
        use_snippets = payload.get('use_snippets', False)
        
        # Fetch commentaries using week-based query with API Team ID (cross-season compatible)
        commentaries = []
        if newsletter.team_id and newsletter.week_start_date and newsletter.week_end_date:
            # Get the API Team ID for cross-season compatibility
            api_team_id = db.session.query(Team.team_id).filter(Team.id == newsletter.team_id).scalar()
            
            if api_team_id:
                # Query commentaries by API Team ID and week dates
                query = NewsletterCommentary.query.join(Team).filter(
                    Team.team_id == api_team_id,
                    NewsletterCommentary.week_start_date == newsletter.week_start_date,
                    NewsletterCommentary.week_end_date == newsletter.week_end_date,
                    NewsletterCommentary.is_active == True
                )
                
                # Apply journalist filtering if specified
                if journalist_ids is not None:
                    if not isinstance(journalist_ids, list):
                        journalist_ids = []
                    if len(journalist_ids) > 0:
                        query = query.filter(NewsletterCommentary.author_id.in_(journalist_ids))
                    else:
                        # Empty list means show no commentaries (unsubscribed simulation)
                        commentaries = []
                        query = None
                
                if query is not None:
                    commentaries = query.all()
                    print(f"[PREVIEW DEBUG] Found {len(commentaries)} commentaries for team API ID {api_team_id}, week {newsletter.week_start_date} to {newsletter.week_end_date}")
                    for c in commentaries:
                        print(f"  - Commentary ID {c.id}: type={c.commentary_type}, player_id={c.player_id}, author={c.author_name}")
        
        print(f"[PREVIEW DEBUG] Final commentary count after filtering: {len(commentaries)}, journalist_ids filter: {journalist_ids}")
        
        # Render
        from src.agents.weekly_agent import _render_variants_custom
        
        variants = _render_variants_custom(
            news=data,
            team_name=newsletter.team.name if newsletter.team else None,
            commentaries=commentaries,
            use_snippets=use_snippets,
            render_mode=render_mode
        )
        
        return jsonify({
            'html': variants.get(f'{render_mode}_html', ''),
            'meta': {
                'journalist_count': len(commentaries),
                'mode': render_mode,
                'snippets': use_snippets
            }
        })

    except Exception as e:
        logger.exception('Preview rendering failed')
        return jsonify(_safe_error_payload(e, 'Preview generation failed')), 500

@api_bp.route('/newsletters/<int:newsletter_id>/render.<fmt>', methods=['GET'])
@require_api_key
def render_newsletter(newsletter_id: int, fmt: str):
    try:
        n = Newsletter.query.get_or_404(newsletter_id)
        data = _load_newsletter_json(n) or {}
        context = _newsletter_render_context(n)
        if fmt in ('html', 'web'):
            html = render_template('newsletter_web.html', **context)
            return Response(html, mimetype='text/html')
        if fmt in ('email', 'email.html'):
            html = render_template('newsletter_email.html', **context)
            return Response(html, mimetype='text/html')
        if fmt in ('txt', 'text'):
            text = _plain_text_from_news(data, n)
            return Response(text, mimetype='text/plain; charset=utf-8')
        return jsonify({'error': 'Unsupported format. Use html, email, or text'}), 400
    except Exception as e:
        logger.exception('Error rendering newsletter')
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@api_bp.route('/newsletters/<int:newsletter_id>/download.pdf', methods=['GET'])
@require_api_key
def download_newsletter_pdf(newsletter_id: int):
    """Render a newsletter as a paginated PDF and return it as an attachment.

    Reuses the existing Tactical Lens email template as the rendering source,
    then hands the HTML to ``pdf_renderer.html_to_pdf`` which injects print
    CSS (``@page`` margins, ``break-inside: avoid`` on player cards, etc.)
    before calling WeasyPrint. Admin-only via ``@require_api_key``.
    """
    try:
        from src.services.pdf_renderer import html_to_pdf, build_pdf_filename
    except ImportError:
        logger.exception('WeasyPrint not available for PDF rendering')
        return jsonify({
            'error': 'pdf_renderer_unavailable',
            'message': 'PDF generation is not configured on this server.',
        }), 503

    try:
        n = Newsletter.query.get_or_404(newsletter_id)
        context = _newsletter_render_context(n)
        html = render_template('newsletter_email.html', **context)
        try:
            base_url = request.url_root
        except RuntimeError:
            base_url = None
        pdf_bytes = html_to_pdf(html, base_url=base_url)
        filename = build_pdf_filename(
            team_name=n.team.name if n.team else None,
            week_end_date=n.week_end_date or n.issue_date,
            newsletter_id=n.id,
        )
        return send_file(
            BytesIO(pdf_bytes),
            mimetype='application/pdf',
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        logger.exception('Error rendering newsletter PDF')
        return jsonify(_safe_error_payload(e, 'Failed to generate PDF')), 500


@api_bp.route('/newsletters/<int:newsletter_id>/send', methods=['POST'])
@require_api_key
def send_newsletter(newsletter_id: int):
    """Send a newsletter via n8n webhook.
    Body options:
      - test_to: string or list of emails (optional). If provided, bypasses published check and does not mark as sent.
      - subject: override subject (optional)
      - webhook_url: override webhook URL (optional)
      - dry_run: bool, forward to webhook (optional)
    """
    try:
        n = Newsletter.query.get_or_404(newsletter_id)
        payload = request.get_json(silent=True) or {}
        test_to = payload.get('test_to')
        subject_override = payload.get('subject')
        webhook_override = payload.get('webhook_url')
        dry_run = bool(payload.get('dry_run'))

        recipients: list[str] | None = None
        is_test = False
        admin_preview = False
        if test_to:
            if isinstance(test_to, str):
                sentinel = test_to.strip().lower()
                if sentinel in {'__admins__', '__admin__', 'admins'}:
                    recipients = _admin_email_list()
                    if not recipients:
                        return jsonify({
                            'error': 'admin_emails_not_configured',
                            'message': 'Set ADMIN_EMAILS to a comma-separated list before sending admin previews.',
                        }), 400
                    admin_preview = True
                else:
                    recipients = [test_to]
                is_test = True
            elif isinstance(test_to, list):
                recipients = [str(x) for x in test_to if str(x).strip()]
                is_test = True
            else:
                return jsonify({'error': 'test_to must be string or list of strings'}), 400

        if not is_test:
            # Require published before full send
            if not n.published:
                return jsonify({'error': 'newsletter must be published/approved before sending'}), 400
            if n.email_sent:
                return jsonify({'error': 'newsletter already sent'}), 400

        if recipients is not None:
            deduped: list[str] = []
            seen: set[str] = set()
            for email in recipients:
                cleaned = (email or '').strip()
                key = cleaned.lower()
                if cleaned and key not in seen:
                    seen.add(key)
                    deduped.append(cleaned)
            recipients = deduped

        # Deliver
        out = _deliver_newsletter_via_webhook(
            n,
            recipients=recipients,  # None => fetch active subscribers
            subject_override=subject_override,
            webhook_url_override=webhook_override,
            dry_run=dry_run,
        )

        if admin_preview:
            try:
                _append_run_history({
                    'kind': 'newsletter-admin-test-send',
                    'newsletter_id': n.id,
                    'team_id': n.team_id,
                    'status': out.get('status'),
                    'http_status': out.get('http_status'),
                    'recipient_count': out.get('recipient_count'),
                    'delivered_count': out.get('delivered_count'),
                    'admin_recipients': recipients,
                    'dry_run': bool(dry_run),
                    'run_by': getattr(g, 'user_email', None),
                })
            except Exception:
                pass

        # Mark sent only for non-test ok runs
        if out.get('status') == 'ok' and not is_test:
            from datetime import datetime as _dt, timezone as _tz
            # Count recipients used
            if recipients is None:
                subs = UserSubscription.query.filter_by(team_id=n.team_id, active=True).all()
                valid_subs = [s for s in subs if (s.email or '').strip() and not s.email_bounced]
                used_count = len(valid_subs)
            else:
                used_count = len(recipients)
            n.email_sent = True
            n.email_sent_date = _dt.now(_tz.utc)
            n.subscriber_count = used_count
            # Update last_email_sent for subscriptions we attempted to deliver
            try:
                ts = n.email_sent_date
                if recipients is None:
                    for s in valid_subs:
                        s.last_email_sent = ts
                else:
                    # Update only those included in recipients list
                    recip_set = set(recipients)
                    subs_sel = UserSubscription.query.filter_by(team_id=n.team_id, active=True).all()
                    for s in subs_sel:
                        if (s.email or '').strip() in recip_set:
                            s.last_email_sent = ts
            except Exception:
                pass
            db.session.commit()
        response_payload = {'newsletter_id': n.id, **out}
        if admin_preview:
            response_payload['admin_preview'] = True
            response_payload['admin_recipients'] = recipients
        return jsonify(response_payload)
    except Exception as e:
        logger.exception('send_newsletter failed')
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@api_bp.route('/newsletters/<int:newsletter_id>', methods=['DELETE'])
@require_api_key
def delete_newsletter(newsletter_id: int):
    try:
        newsletter = Newsletter.query.get(newsletter_id)
        if not newsletter:
            return jsonify({'error': 'Newsletter not found'}), 404

        try:
            NewsletterComment.query.filter_by(newsletter_id=newsletter.id).delete(synchronize_session=False)
        except Exception:
            db.session.rollback()
            raise

        NewsletterDigestQueue.query.filter_by(newsletter_id=newsletter.id).delete(synchronize_session=False)

        Newsletter.query.filter_by(id=newsletter_id).delete(synchronize_session=False)
        db.session.commit()

        return jsonify({'status': 'deleted', 'newsletter_id': newsletter_id})
    except Exception as e:
        logger.exception('delete_newsletter failed')
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500
@api_bp.route('/newsletters/latest/render.<fmt>', methods=['GET'])
@require_api_key
def render_latest_newsletter(fmt: str):
    try:
        team_id = request.args.get('team', type=int)
        if not team_id:
            return jsonify({'error': 'team query param required'}), 400
        n = (
            Newsletter.query
            .filter_by(team_id=team_id)
            .order_by(Newsletter.generated_date.desc())
            .first()
        )
        if not n:
            return jsonify({'error': 'No newsletters found for team'}), 404
        return render_newsletter(n.id, fmt)
    except Exception as e:
        logger.exception('Error rendering latest newsletter')
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/newsletters/generate-weekly-mcp-team', methods=['POST'])
@require_api_key
def generate_weekly_mcp_team():
    try:
        payload = request.get_json() or {}
        target_date = payload.get('target_date')
        team_db_id = payload.get('team_db_id')
        api_team_id = payload.get('api_team_id')
        if not (team_db_id or api_team_id):
            return jsonify({'error': 'team_db_id or api_team_id is required'}), 400
        from datetime import datetime, date as d
        tdate = datetime.strptime(target_date, "%Y-%m-%d").date() if target_date else d.today()

        # Resolve DB id if only API id provided (use inferred season from date)
        if not team_db_id and api_team_id:
            season = tdate.year if tdate.month >= 8 else tdate.year - 1
            row = Team.query.filter_by(team_id=int(api_team_id), season=season).first()
            if not row:
                return jsonify({'error': f'Team api_id={api_team_id} not found for season {season}'}), 404
            team_db_id = row.id
        from src.agents.weekly_agent import generate_weekly_newsletter_with_mcp_sync
        try:
            out = generate_weekly_newsletter_with_mcp_sync(int(team_db_id), tdate)
        except NoActiveLoaneesError as e:
            return jsonify({
                'team_db_id': team_db_id,
                'ran_for': tdate.isoformat(),
                'status': 'skipped',
                'reason': 'no_active_loanees',
                'message': str(e),
            }), 200
        return jsonify({'team_db_id': team_db_id, 'ran_for': tdate.isoformat(), 'result': out})
    except Exception as e:
        logger.exception("generate-weekly-mcp-team failed")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

# Loan flag endpoints moved to src/routes/loans.py
from src.models.league import PlayerFlag, AdminSetting

# --- Admin config & run control ---

def _get_admin_bool(key: str, default: bool = False) -> bool:
    try:
        row = AdminSetting.query.filter_by(key=key).first()
        if row and row.value_json is not None:
            v = row.value_json.strip().lower()
            return v in ('1', 'true', 'yes', 'y')
    except Exception:
        pass
    return default

def _set_admin_values(kv: dict[str, str]):
    for k, v in kv.items():
        row = AdminSetting.query.filter_by(key=k).first()
        if not row:
            row = AdminSetting(key=k, value_json=str(v))
            db.session.add(row)
        else:
            row.value_json = str(v)
    db.session.commit()

@api_bp.route('/admin/config', methods=['GET'])
@require_api_key
def get_admin_config():
    try:
        rows = AdminSetting.query.all()
        return jsonify({r.key: r.value_json for r in rows})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/config', methods=['POST'])
@require_api_key
def update_admin_config():
    try:
        payload = request.get_json() or {}
        settings = payload.get('settings') or {}
        if not isinstance(settings, dict):
            return jsonify({'error': 'settings must be an object'}), 400
        # store as stringified booleans/values
        to_store = {k: ('true' if bool(v) else 'false') if isinstance(v, bool) else str(v) for k, v in settings.items()}
        _set_admin_values(to_store)
        return jsonify({'message': 'Updated', 'updated': list(settings.keys())})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/run-status', methods=['GET'])
@require_api_key
def get_run_status():
    try:
        paused = _get_admin_bool('runs_paused', False)
        return jsonify({'runs_paused': paused})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/run-status', methods=['POST'])
@require_api_key
def set_run_status():
    try:
        payload = request.get_json() or {}
        paused = bool(payload.get('runs_paused', False))
        _set_admin_values({'runs_paused': 'true' if paused else 'false'})
        return jsonify({'message': 'Run status updated', 'runs_paused': paused})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/jobs/active', methods=['GET'])
@require_api_key
def list_active_jobs():
    """List all currently running background jobs."""
    STALE_THRESHOLD = STALE_JOB_TIMEOUT
    now = datetime.now(timezone.utc)

    running = BackgroundJob.query.filter_by(status='running').order_by(
        BackgroundJob.started_at.desc()
    ).all()

    results = []
    for job in running:
        last_active = (job.updated_at or job.started_at or job.created_at)
        if last_active:
            elapsed = now - last_active.replace(tzinfo=timezone.utc)
            if elapsed > STALE_THRESHOLD:
                job.status = 'failed'
                job.error = f'Stale job auto-failed (no update in {elapsed}).'
                job.completed_at = now
                db.session.commit()
                continue
        results.append(job.to_dict())

    return jsonify({'jobs': results})


@api_bp.route('/admin/jobs/<job_id>', methods=['GET'])
@require_api_key
def get_job_status(job_id: str):
    """Get the status of a background job."""
    job = _get_job(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    return jsonify(job)


@api_bp.route('/admin/jobs/<job_id>/cancel', methods=['POST'])
@require_api_key
def cancel_job_endpoint(job_id: str):
    """Cancel a running background job."""
    from src.utils.background_jobs import cancel_job
    if cancel_job(job_id):
        return jsonify({'message': 'Job cancelled', 'job_id': job_id})
    return jsonify({'error': 'Job not found or not running'}), 404


@api_bp.route('/admin/jobs/<job_id>/force-fail', methods=['POST'])
@require_api_key
def force_fail_job(job_id: str):
    """Force-fail a stuck job, regardless of stale timeout."""
    job = db.session.get(BackgroundJob, job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    if job.status not in ('running', 'cancelled'):
        return jsonify({'error': f'Job already {job.status}'}), 400
    job.status = 'failed'
    job.error = 'Force-failed by admin'
    job.completed_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify({'message': 'Job force-failed', 'job_id': job_id})


@api_bp.route('/admin/jobs/force-fail-all', methods=['POST'])
@require_api_key
def force_fail_all_jobs():
    """Force-fail all running/cancelled jobs."""
    stuck = BackgroundJob.query.filter(
        BackgroundJob.status.in_(('running', 'cancelled'))
    ).all()
    if not stuck:
        return jsonify({'message': 'No stuck jobs found', 'count': 0})
    now = datetime.now(timezone.utc)
    for job in stuck:
        job.status = 'failed'
        job.error = 'Force-failed by admin (bulk)'
        job.completed_at = now
    db.session.commit()
    return jsonify({'message': f'{len(stuck)} jobs force-failed', 'count': len(stuck)})


# --- Admin: Missing names helpers (canonical source: utils/team_resolver.py) ---
from src.utils.team_resolver import (
    is_placeholder_name as _is_placeholder_name,
    is_placeholder_team_name as _is_placeholder_team_name,
    update_team_name_if_missing as _update_team_name_if_missing,
)

@api_bp.route('/admin/backfill-team-leagues/<int:season>', methods=['POST'])
@require_api_key
def admin_backfill_team_leagues(season: int):
    """Backfill league_id for teams in a given season that are missing their
    league mapping. Helpful if teams were created via admin seeding before
    syncing leagues/teams for that season.
    """
    try:
        if not season:
            return jsonify({'error': 'season is required'}), 400

        # Map: API team id -> { name, league_name, league_id, country }
        team_map = api_client.get_teams_with_leagues_for_season(season) or {}

        # Build an internal fallback mapping from existing rows (any season)
        # api_team_id -> existing league FK id
        existing_league_fk_by_api_id: dict[int, int] = {}
        for row in Team.query.filter(Team.league_id.isnot(None)).all():
            existing_league_fk_by_api_id[row.team_id] = row.league_id

        updated = 0
        created_leagues = 0
        examined = 0

        rows = Team.query.filter_by(season=season).all()
        for t in rows:
            examined += 1
            if t.league_id:
                continue
            meta = team_map.get(t.team_id)
            league_row = None
            if meta:
                league_api_id = meta.get('league_id')
                league_name = meta.get('league_name')
                league_country = meta.get('country') or 'Unknown'
                if league_api_id and league_name:
                    league_row = League.query.filter_by(league_id=league_api_id).first()
                    if not league_row:
                        league_row = League(
                            league_id=league_api_id,
                            name=league_name,
                            country=league_country,
                            season=season,
                            is_european_top_league=True,
                        )
                        db.session.add(league_row)
                        db.session.flush()
                        created_leagues += 1
            # Fallback: copy league FK from any season if we have one
            if league_row is None:
                fallback_fk = existing_league_fk_by_api_id.get(t.team_id)
                if fallback_fk:
                    t.league_id = fallback_fk
                    updated += 1
                    continue
            if league_row is None:
                continue
            t.league_id = league_row.id
            updated += 1

        db.session.commit()
        try:
            _append_run_history({
                'kind': 'backfill-team-leagues',
                'season': season,
                'updated': updated,
                'created_leagues': created_leagues,
                'message': f'Backfilled leagues for season {season}: updated {updated}, created {created_leagues}'
            })
        except Exception:
            pass
        return jsonify({
            'season': season,
            'examined': examined,
            'updated_teams': updated,
            'created_leagues': created_leagues,
        })
    except Exception as e:
        logger.exception('admin_backfill_team_leagues failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/backfill-team-leagues', methods=['POST'])
@require_api_key
def admin_backfill_team_leagues_all():
    """
    Backfill Team.league_id across multiple seasons.

    Body (optional): { "seasons": [2023, 2024, ...] }
    If not provided, operates on all distinct Team.season values present.
    """
    try:
        payload = request.get_json() or {}
        seasons = payload.get('seasons')
        if not seasons:
            seasons = [row[0] for row in db.session.query(Team.season).distinct().all()]

        summary = []
        total_updated = 0
        total_created_leagues = 0
        total_examined = 0

        for season in seasons:
            try:
                season = int(season)
                team_map = api_client.get_teams_with_leagues_for_season(season) or {}
                # Build fallback from existing rows (any season)
                existing_league_fk_by_api_id: dict[int, int] = {}
                for row in Team.query.filter(Team.league_id.isnot(None)).all():
                    existing_league_fk_by_api_id[row.team_id] = row.league_id
                updated = 0
                created_leagues = 0
                examined = 0
                rows = Team.query.filter_by(season=season).all()
                for t in rows:
                    examined += 1
                    if t.league_id:
                        continue
                    meta = team_map.get(t.team_id)
                    league_row = None
                    if meta:
                        league_api_id = meta.get('league_id')
                        league_name = meta.get('league_name')
                        league_country = meta.get('country') or 'Unknown'
                        if league_api_id and league_name:
                            league_row = League.query.filter_by(league_id=league_api_id).first()
                            if not league_row:
                                league_row = League(
                                    league_id=league_api_id,
                                    name=league_name,
                                    country=league_country,
                                    season=season,
                                    is_european_top_league=True,
                                )
                                db.session.add(league_row)
                                db.session.flush()
                                created_leagues += 1
                    # Fallback: copy league FK from any season
                    if league_row is None:
                        fallback_fk = existing_league_fk_by_api_id.get(t.team_id)
                        if fallback_fk:
                            t.league_id = fallback_fk
                            updated += 1
                            continue
                    if league_row is None:
                        continue
                    t.league_id = league_row.id
                    updated += 1
                db.session.commit()
                summary.append({
                    'season': season,
                    'examined': examined,
                    'updated_teams': updated,
                    'created_leagues': created_leagues,
                })
                total_updated += updated
                total_created_leagues += created_leagues
                total_examined += examined
            except Exception:
                db.session.rollback()
                summary.append({'season': int(season), 'error': 'failed'})

        try:
            _append_run_history({
                'kind': 'backfill-team-leagues-all',
                'seasons': seasons,
                'updated': total_updated,
                'created_leagues': total_created_leagues,
                'message': f'Backfilled all seasons ({len(seasons)}): updated {total_updated}, created leagues {total_created_leagues}'
            })
        except Exception:
            pass
        return jsonify({
            'summary': summary,
            'totals': {
                'seasons': len(seasons),
                'examined': total_examined,
                'updated_teams': total_updated,
                'created_leagues': total_created_leagues,
            }
        })
    except Exception as e:
        logger.exception('admin_backfill_team_leagues_all failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/players/<int:player_id>/sync-fixtures', methods=['POST'])
@require_api_key
def admin_sync_player_fixtures(player_id: int):
    """
    Sync/backfill all fixtures for a player from API-Football.
    Uses TrackedPlayer to determine current team (loan club or parent club).
    """
    try:
        from src.api_football_client import APIFootballClient
        from src.models.weekly import Fixture, FixturePlayerStats
        from src.models.tracked_player import TrackedPlayer
        
        data = request.get_json() or {}
        dry_run = data.get('dry_run', False)
        
        # Get current season
        now_utc = datetime.now(timezone.utc)
        current_year = now_utc.year
        current_month = now_utc.month
        season = data.get('season', current_year if current_month >= 8 else current_year - 1)
        
        # Try TrackedPlayer first (newer model)
        tp = TrackedPlayer.query.filter_by(
            player_api_id=player_id, is_active=True,
        ).first()
        
        player_name = None
        team_api_id = None
        team_name = None
        
        if tp:
            player_name = tp.player_name
            if tp.status == 'on_loan' and tp.current_club_api_id:
                team_api_id = tp.current_club_api_id
                team_name = tp.current_club_name or resolve_team_name_and_logo(tp.current_club_api_id)[0]
            elif tp.status == 'first_team':
                parent_team = Team.query.get(tp.team_id)
                if parent_team:
                    team_api_id = parent_team.team_id
                    team_name = parent_team.name
        
        if not team_api_id:
            return jsonify({'error': 'No team found for this player in TrackedPlayer'}), 404
        
        api_client = APIFootballClient()
        
        # Fetch all fixtures for this team in the season
        season_start = f"{season}-08-01"
        season_end = f"{season + 1}-06-30"
        
        logger.info(f"Syncing fixtures for player {player_id} ({player_name}) at team {team_api_id} ({team_name})")
        
        fixtures = api_client.get_fixtures_for_team_cached(
            team_api_id,
            season,
            season_start,
            season_end
        )
        
        synced = 0
        skipped = 0
        errors = []
        
        for fx in fixtures:
            fixture_info = fx.get('fixture', {})
            fixture_id_api = fixture_info.get('id')
            fixture_status = fixture_info.get('status', {}).get('short', '')
            
            # Only process finished games
            if fixture_status not in ('FT', 'AET', 'PEN'):
                skipped += 1
                continue
            
            # Check if we already have this fixture
            existing_fixture = Fixture.query.filter_by(fixture_id_api=fixture_id_api).first()
            
            if not existing_fixture:
                # Create the fixture
                if not dry_run:
                    teams = fx.get('teams', {})
                    goals = fx.get('goals', {})
                    league = fx.get('league', {})
                    
                    existing_fixture = Fixture(
                        fixture_id_api=fixture_id_api,
                        date_utc=datetime.fromisoformat(fixture_info.get('date', '').replace('Z', '+00:00')) if fixture_info.get('date') else None,
                        season=season,
                        competition_name=league.get('name'),
                        home_team_api_id=teams.get('home', {}).get('id'),
                        away_team_api_id=teams.get('away', {}).get('id'),
                        home_goals=goals.get('home'),
                        away_goals=goals.get('away'),
                    )
                    db.session.add(existing_fixture)
                    db.session.flush()
            
            # Check if we have player stats for this fixture
            if existing_fixture:
                existing_stats = FixturePlayerStats.query.filter_by(
                    fixture_id=existing_fixture.id,
                    player_api_id=player_id
                ).first()
                
                if existing_stats:
                    skipped += 1
                    continue
            
            # Fetch player stats for this fixture
            try:
                player_stats = api_client.get_player_stats_for_fixture(player_id, season, fixture_id_api)
                
                if player_stats and player_stats.get('statistics'):
                    # statistics is a LIST, get first element
                    stat_list = player_stats['statistics']
                    if not stat_list:
                        skipped += 1
                        continue
                    st = stat_list[0] if isinstance(stat_list, list) else stat_list
                    
                    # Extract stats from the nested structure
                    games = st.get('games', {}) or {}
                    goals_block = st.get('goals', {}) or {}
                    cards = st.get('cards', {}) or {}
                    shots = st.get('shots', {}) or {}
                    passes = st.get('passes', {}) or {}
                    tackles = st.get('tackles', {}) or {}
                    duels = st.get('duels', {}) or {}
                    dribbles = st.get('dribbles', {}) or {}
                    fouls = st.get('fouls', {}) or {}
                    penalty = st.get('penalty', {}) or {}
                    
                    minutes = games.get('minutes', 0) or 0

                    # Record if player played or was listed as substitute
                    if (minutes > 0 or games.get('substitute') is not None) and not dry_run and existing_fixture:
                        formation, grid, formation_pos = _extract_lineup_info(
                            api_client, fixture_id_api, player_id, team_api_id)
                        fps = FixturePlayerStats(
                            fixture_id=existing_fixture.id,
                            player_api_id=player_id,
                            team_api_id=team_api_id,
                            minutes=minutes,
                            substitute=bool(games.get('substitute')),
                            position=games.get('position'),
                            rating=games.get('rating'),
                            goals=goals_block.get('total', 0) or 0,
                            assists=goals_block.get('assists', 0) or 0,
                            yellows=cards.get('yellow', 0) or 0,
                            reds=cards.get('red', 0) or 0,
                            shots_total=shots.get('total'),
                            shots_on=shots.get('on'),
                            passes_total=passes.get('total'),
                            passes_key=passes.get('key'),
                            tackles_total=tackles.get('total'),
                            duels_won=duels.get('won'),
                            duels_total=duels.get('total'),
                            dribbles_success=dribbles.get('success'),
                            saves=goals_block.get('saves'),
                            goals_conceded=goals_block.get('conceded'),
                            fouls_drawn=fouls.get('drawn'),
                            fouls_committed=fouls.get('committed'),
                            penalty_saved=penalty.get('saved'),
                            formation=formation,
                            grid=grid,
                            formation_position=formation_pos,
                        )
                        db.session.add(fps)
                        synced += 1
                    elif minutes > 0 or games.get('substitute') is not None:
                        synced += 1  # Dry run counts this as would-sync
                    else:
                        skipped += 1
                else:
                    skipped += 1

            except Exception as e:
                errors.append(f"Fixture {fixture_id_api}: {str(e)}")

        if not dry_run:
            db.session.commit()

        return jsonify({
            'player_id': player_id,
            'player_name': player_name,
            'team': team_name,
            'season': season,
            'dry_run': dry_run,
            'fixtures_found': len(fixtures),
            'synced': synced,
            'skipped': skipped,
            'errors': errors[:10],  # Limit error list
        })
        
    except Exception as e:
        logger.error(f"Error syncing fixtures for player {player_id}: {e}")
        import traceback
        traceback.print_exc()
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to sync player fixtures')), 500

@api_bp.route('/admin/teams/<int:team_id>/sync-all-fixtures', methods=['POST'])
@require_api_key
def admin_sync_team_fixtures(team_id: int):
    """
    Sync/backfill all fixtures for ALL active players loaned from a specific team.
    This goes through each player loaned FROM the team (where team is primary_team)
    and re-fetches their fixture stats from API-Football.
    
    Supports background processing for large teams.
    
    Body:
    - background: true/false (default: false)
    - dry_run: true/false (default: false)
    - season: int (default: current season)
    """
    try:
        data = request.get_json() or {}
        background = bool(data.get('background', False))
        job_id = str(uuid4()) if background else None
        
        if background:
            _create_background_job('team_fixtures_sync')
            # Override job_id from uuid() to use the one from _create_background_job
            def run_sync_in_background():
                try:
                    result = _run_team_fixtures_sync(team_id, data, job_id)
                    _update_job(job_id, status='completed', results=result, completed_at=datetime.now(timezone.utc).isoformat())
                except Exception as e:
                    logger.exception(f'Background team sync job {job_id} failed')
                    _update_job(job_id, status='failed', error=str(e), completed_at=datetime.now(timezone.utc).isoformat())
            
            thread = threading.Thread(target=run_sync_in_background)
            thread.start()
            return jsonify({'message': 'Team fixture sync started in background', 'job_id': job_id}), 202
        else:
            result = _run_team_fixtures_sync(team_id, data)
            return jsonify(result), 200
            
    except Exception as e:
        logger.exception(f"admin_sync_team_fixtures failed for team {team_id}")
        return jsonify(_safe_error_payload(e, 'Failed to sync team fixtures')), 500


@api_bp.route('/admin/sync-all-player-fixtures', methods=['POST'])
@require_api_key
def admin_sync_all_player_fixtures():
    """
    Batch sync fixture stats for ALL active tracked players.

    Groups players by their current team to minimize API calls:
    - Fetches fixtures per team once (shared across all players at that club)
    - Fetches per-fixture player stats once per fixture (extracts data for all
      tracked players from a single /fixtures/players response)

    Body:
    - dry_run: true/false (default: false)
    - season: int (default: current season)
    - delay: float seconds between fixture API calls (default: 0.1)
    """
    try:
        from src.models.tracked_player import TrackedPlayer

        data = request.get_json() or {}
        dry_run = bool(data.get('dry_run', False))

        job_id = _create_background_job('batch_fixture_sync')

        def _run_batch_sync():
            try:
                result = _run_batch_fixture_sync(data, job_id)
                _update_job(job_id, status='completed', results=result,
                            completed_at=datetime.now(timezone.utc).isoformat())
            except Exception as e:
                logger.exception(f'Batch fixture sync job {job_id} failed')
                _update_job(job_id, status='failed', error=str(e),
                            completed_at=datetime.now(timezone.utc).isoformat())

        thread = threading.Thread(target=_run_batch_sync)
        thread.start()
        return jsonify({
            'message': 'Batch fixture sync started in background',
            'job_id': job_id,
            'dry_run': dry_run,
        }), 202

    except Exception as e:
        logger.exception('admin_sync_all_player_fixtures failed')
        return jsonify(_safe_error_payload(e, 'Failed to start batch fixture sync')), 500


def _run_batch_fixture_sync(data: dict, job_id: str = None) -> dict:
    """
    Core logic for batch fixture sync.

    Groups players by loan club, then for each club:
    1. Fetch fixtures once via get_fixtures_for_team_cached()
    2. For each finished fixture, fetch /fixtures/players once
    3. Extract stats for every tracked player at that club
    """
    from src.api_football_client import APIFootballClient
    from src.models.weekly import Fixture, FixturePlayerStats
    from src.models.tracked_player import TrackedPlayer
    from collections import defaultdict
    import time

    dry_run = bool(data.get('dry_run', False))
    delay = float(data.get('delay', 0.1))

    now_utc = datetime.now(timezone.utc)
    current_year = now_utc.year
    current_month = now_utc.month
    season = data.get('season', current_year if current_month >= 8 else current_year - 1)

    # ── 1. Gather all players grouped by current team API ID ──
    team_players = defaultdict(list)  # {team_api_id: [(player_api_id, player_name), ...]}

    # TrackedPlayer (primary source)
    tracked = TrackedPlayer.query.filter(
        TrackedPlayer.is_active.is_(True),
        TrackedPlayer.status.in_(['on_loan', 'first_team', 'academy']),
    ).all()

    tracked_api_ids = set()
    for tp in tracked:
        if tp.status == 'on_loan' and tp.current_club_api_id:
            team_players[tp.current_club_api_id].append((tp.player_api_id, tp.player_name))
            tracked_api_ids.add(tp.player_api_id)
        elif tp.status in ('first_team', 'academy') and tp.team_id:
            parent_team = Team.query.get(tp.team_id)
            if parent_team and parent_team.team_id:
                team_players[parent_team.team_id].append((tp.player_api_id, tp.player_name))
                tracked_api_ids.add(tp.player_api_id)

    # Create API client early — needed for team discovery below
    api_client = APIFootballClient()

    # Sold/released players — discover their current team via API-Football
    from src.api_football_client import extract_transfer_fee
    sold_released = TrackedPlayer.query.filter(
        TrackedPlayer.is_active.is_(True),
        TrackedPlayer.status.in_(['sold', 'released']),
    ).all()

    discovery_count = 0
    fee_count = 0
    for tp in sold_released:
        if tp.player_api_id in tracked_api_ids:
            continue
        # If we already have a team from a prior backfill, use it
        if tp.current_club_api_id:
            team_players[tp.current_club_api_id].append((tp.player_api_id, tp.player_name))
            tracked_api_ids.add(tp.player_api_id)
            continue
        # Discover team from API-Football /players endpoint
        try:
            from src.utils.academy_classifier import is_national_team
            player_data = api_client.get_player_by_id(tp.player_api_id, season)
            if player_data and player_data.get('statistics'):
                # Find the best CLUB team (skip national teams + parent academy, prefer most appearances)
                # For sold players, we want the club they were sold TO, not the parent
                parent_team = Team.query.get(tp.team_id) if tp.team_id else None
                parent_api_id = parent_team.team_id if parent_team else None
                best_team_block = None
                best_stat = None
                best_apps = -1
                for stat in player_data['statistics']:
                    team_block = stat.get('team', {})
                    team_name = team_block.get('name', '')
                    team_api_id = team_block.get('id')
                    # Skip international/national teams
                    if is_national_team(team_name):
                        continue
                    # Skip parent academy (for sold players, we want the destination club)
                    if parent_api_id and team_api_id == parent_api_id:
                        continue
                    games = stat.get('games', {}) or {}
                    apps = games.get('appearences') or games.get('appearances') or 0
                    if apps > best_apps:
                        best_apps = apps
                        best_team_block = team_block
                        best_stat = stat

                # Cross-reference against transfers before backfilling
                try:
                    from src.api_football_client import is_new_loan_transfer, LOAN_RETURN_TYPES
                    from src.utils.academy_classifier import flatten_transfers
                    raw_transfers = api_client.get_player_transfers(tp.player_api_id)
                    flat = flatten_transfers(raw_transfers)
                    if flat:
                        most_recent = sorted(flat, key=lambda x: x.get('date', ''), reverse=True)[0]
                        tr_type = (most_recent.get('type') or '').strip().lower()
                        dest = most_recent.get('teams', {}).get('in', {})
                        if dest.get('id') and tr_type not in LOAN_RETURN_TYPES:
                            best_team_block = {'id': dest['id'], 'name': dest.get('name', f'Team {dest["id"]}'), 'logo': dest.get('logo')}
                except Exception:
                    pass  # fall through to stats-based result

                if best_team_block:
                    team_api_id = best_team_block.get('id')
                    team_players[team_api_id].append((tp.player_api_id, tp.player_name))
                    tracked_api_ids.add(tp.player_api_id)
                    # Backfill team on TrackedPlayer
                    if not dry_run:
                        tp.current_club_api_id = team_api_id
                        tp.current_club_name = best_team_block.get('name')
                        # Also backfill position if missing
                        if not tp.position:
                            games = (best_stat or {}).get('games', {}) or {}
                            tp.position = games.get('position')
                    discovery_count += 1
            # Fetch transfer fee for sold players
            if tp.status == 'sold' and not tp.sale_fee and not dry_run:
                try:
                    transfers_resp = api_client.get_player_transfers(tp.player_api_id)
                    # Response is a list: [{player: {...}, transfers: [{date, type, teams}]}]
                    all_transfers = []
                    for entry in (transfers_resp or []):
                        all_transfers.extend(entry.get('transfers', []))
                    # Find the most recent non-loan transfer
                    for xfer in reversed(all_transfers):
                        fee = extract_transfer_fee(xfer.get('type', ''))
                        if fee is not None:
                            tp.sale_fee = fee
                            fee_count += 1
                            break
                except Exception:
                    pass
            if not dry_run:
                db.session.commit()
            time.sleep(delay)  # Rate limit API calls
        except Exception as e:
            logger.warning(f"Failed to discover team for player {tp.player_api_id} ({tp.player_name}): {e}")

    total_teams = len(team_players)
    total_players = sum(len(v) for v in team_players.values())
    logger.info(f"Batch sync: {total_players} players across {total_teams} teams, season={season}, dry_run={dry_run}")
    logger.info(f"Team discovery: {discovery_count} sold/released players resolved, {fee_count} fees extracted")

    if job_id:
        _update_job(job_id, total=total_players, progress=0,
                    current_player=f'Starting: {total_players} players across {total_teams} teams')

    season_start = f"{season}-08-01"
    today = now_utc.strftime('%Y-%m-%d')

    summary = {
        'season': season,
        'dry_run': dry_run,
        'total_teams': total_teams,
        'total_players': total_players,
        'total_fixtures_checked': 0,
        'total_synced': 0,
        'total_skipped': 0,
        'total_errors': 0,
        'teams': [],
    }
    players_processed = 0

    # ── 2. Process each team group ──
    for team_api_id, players in team_players.items():
        team_result = {
            'team_api_id': team_api_id,
            'players': len(players),
            'fixtures': 0,
            'synced': 0,
            'skipped': 0,
            'errors': [],
        }

        try:
            fixtures = api_client.get_fixtures_for_team_cached(
                team_api_id, season, season_start, today
            )

            # Filter to finished games only
            finished = [
                fx for fx in fixtures
                if (fx.get('fixture', {}).get('status', {}).get('short', '')) in ('FT', 'AET', 'PEN')
            ]
            team_result['fixtures'] = len(finished)
            summary['total_fixtures_checked'] += len(finished)

            # Build set of player API IDs we care about for this team
            player_ids_at_team = {pid for pid, _ in players}

            for fx in finished:
                fixture_info = fx.get('fixture', {})
                fixture_id_api = fixture_info.get('id')
                if not fixture_id_api:
                    continue

                # Get or create Fixture record
                existing_fixture = Fixture.query.filter_by(fixture_id_api=fixture_id_api).first()
                if not existing_fixture:
                    teams_data = fx.get('teams', {})
                    goals_data = fx.get('goals', {})
                    league_data = fx.get('league', {})
                    existing_fixture = Fixture(
                        fixture_id_api=fixture_id_api,
                        date_utc=datetime.fromisoformat(
                            fixture_info.get('date', '').replace('Z', '+00:00')
                        ) if fixture_info.get('date') else None,
                        season=season,
                        competition_name=league_data.get('name'),
                        home_team_api_id=teams_data.get('home', {}).get('id'),
                        away_team_api_id=teams_data.get('away', {}).get('id'),
                        home_goals=goals_data.get('home'),
                        away_goals=goals_data.get('away'),
                    )
                    if not dry_run:
                        db.session.add(existing_fixture)
                        db.session.flush()

                if dry_run and not existing_fixture.id:
                    # Can't check existing stats in dry_run for new fixtures
                    team_result['synced'] += len(player_ids_at_team)
                    continue

                # Check which players already have stats for this fixture
                existing_player_ids = set()
                if existing_fixture.id:
                    existing_stats = FixturePlayerStats.query.filter(
                        FixturePlayerStats.fixture_id == existing_fixture.id,
                        FixturePlayerStats.player_api_id.in_(player_ids_at_team),
                    ).all()
                    existing_player_ids = {s.player_api_id for s in existing_stats}

                missing_player_ids = player_ids_at_team - existing_player_ids
                if not missing_player_ids:
                    team_result['skipped'] += len(player_ids_at_team)
                    continue

                # Fetch /fixtures/players ONCE for this fixture (all players)
                try:
                    team_blocks = api_client.get_fixture_players(fixture_id_api)
                except Exception as e:
                    team_result['errors'].append(f"Fixture {fixture_id_api}: {e}")
                    continue

                if not team_blocks:
                    team_result['skipped'] += len(missing_player_ids)
                    continue

                # Extract stats for each missing tracked player
                for team_block in team_blocks:
                    for p in team_block.get('players', []):
                        pinfo = p.get('player') or {}
                        pid = pinfo.get('id')
                        if pid not in missing_player_ids:
                            continue

                        statistics = p.get('statistics') or []
                        if not statistics:
                            continue
                        st = statistics[0]

                        games = st.get('games', {}) or {}
                        goals_obj = st.get('goals', {}) or {}
                        cards = st.get('cards', {}) or {}
                        shots = st.get('shots', {}) or {}
                        passes = st.get('passes', {}) or {}
                        tackles = st.get('tackles', {}) or {}
                        duels = st.get('duels', {}) or {}
                        dribbles = st.get('dribbles', {}) or {}
                        fouls = st.get('fouls', {}) or {}
                        penalty = st.get('penalty', {}) or {}

                        minutes = games.get('minutes', 0) or 0

                        if minutes > 0 or games.get('substitute') is not None:
                            if not dry_run:
                                formation, grid_val, formation_pos = _extract_lineup_info(
                                    api_client, fixture_id_api, pid, team_api_id)
                                fps = FixturePlayerStats(
                                    fixture_id=existing_fixture.id,
                                    player_api_id=pid,
                                    team_api_id=team_api_id,
                                    minutes=minutes,
                                    position=games.get('position'),
                                    rating=games.get('rating'),
                                    goals=goals_obj.get('total', 0) or 0,
                                    assists=goals_obj.get('assists', 0) or 0,
                                    yellows=cards.get('yellow', 0) or 0,
                                    reds=cards.get('red', 0) or 0,
                                    shots_total=shots.get('total'),
                                    shots_on=shots.get('on'),
                                    passes_total=passes.get('total'),
                                    passes_key=passes.get('key'),
                                    tackles_total=tackles.get('total'),
                                    duels_won=duels.get('won'),
                                    duels_total=duels.get('total'),
                                    dribbles_success=dribbles.get('success'),
                                    saves=goals_obj.get('saves'),
                                    goals_conceded=goals_obj.get('conceded'),
                                    fouls_drawn=fouls.get('drawn'),
                                    fouls_committed=fouls.get('committed'),
                                    penalty_saved=penalty.get('saved'),
                                    formation=formation,
                                    grid=grid_val,
                                    formation_position=formation_pos,
                                )
                                db.session.add(fps)
                            team_result['synced'] += 1
                        else:
                            team_result['skipped'] += 1

                        # Remove from missing set so we don't double-count
                        missing_player_ids.discard(pid)

                if delay > 0:
                    time.sleep(delay)

            if not dry_run:
                db.session.commit()

        except Exception as e:
            logger.warning(f"Batch sync error for team {team_api_id}: {e}")
            team_result['errors'].append(str(e))
            db.session.rollback()

        summary['total_synced'] += team_result['synced']
        summary['total_skipped'] += team_result['skipped']
        summary['total_errors'] += len(team_result['errors'])
        summary['teams'].append(team_result)

        players_processed += len(players)
        if job_id:
            _update_job(job_id, progress=players_processed,
                        current_player=f'Processed team {team_api_id} ({len(players)} players)')

    logger.info(
        f"Batch sync complete: synced={summary['total_synced']}, "
        f"skipped={summary['total_skipped']}, errors={summary['total_errors']}"
    )
    return summary


@api_bp.route('/admin/fixtures/backfill-raw-json', methods=['POST'])
@require_api_key
def admin_backfill_fixture_raw_json():
    """
    Backfill raw_json for fixtures that are missing it.

    This fetches the full fixture data from API-Football and stores it,
    which enables team name extraction for older fixtures.
    
    Body:
    - player_id: (optional) Only backfill fixtures for this player
    - team_api_id: (optional) Only backfill fixtures involving this team
    - limit: (optional) Max fixtures to process (default 50)
    - dry_run: (optional) If true, don't actually update DB
    """
    try:
        from src.api_football_client import APIFootballClient
        from src.models.weekly import Fixture, FixturePlayerStats
        import json
        
        data = request.get_json() or {}
        player_id = data.get('player_id')
        team_api_id = data.get('team_api_id')
        limit = min(data.get('limit', 50), 200)  # Cap at 200 to avoid API abuse
        dry_run = data.get('dry_run', False)
        
        # Build query for fixtures missing raw_json
        query = Fixture.query.filter(Fixture.raw_json.is_(None))
        
        # Filter by player if specified
        if player_id:
            fixture_ids_subq = db.session.query(FixturePlayerStats.fixture_id).filter(
                FixturePlayerStats.player_api_id == player_id
            ).subquery()
            query = query.filter(Fixture.id.in_(fixture_ids_subq))
        
        # Filter by team if specified
        if team_api_id:
            query = query.filter(
                db.or_(
                    Fixture.home_team_api_id == team_api_id,
                    Fixture.away_team_api_id == team_api_id
                )
            )
        
        # Order by most recent first, limit results
        fixtures_to_update = query.order_by(Fixture.date_utc.desc()).limit(limit).all()
        
        if not fixtures_to_update:
            return jsonify({
                'message': 'No fixtures found with missing raw_json',
                'updated': 0
            })
        
        api_client = APIFootballClient()
        updated = 0
        errors = []
        
        for fixture in fixtures_to_update:
            try:
                # Fetch fixture data from API
                resp = api_client._make_request('fixtures', {'id': fixture.fixture_id_api})
                api_fixtures = resp.get('response', [])
                
                if api_fixtures:
                    # Store the full fixture object as raw_json
                    raw_json_str = json.dumps(api_fixtures[0])
                    
                    if not dry_run:
                        fixture.raw_json = raw_json_str
                        db.session.add(fixture)
                    
                    updated += 1
                    logger.info(f"Backfilled raw_json for fixture {fixture.fixture_id_api}")
                else:
                    errors.append({
                        'fixture_id_api': fixture.fixture_id_api,
                        'error': 'No data returned from API'
                    })
            except Exception as e:
                errors.append({
                    'fixture_id_api': fixture.fixture_id_api,
                    'error': str(e)
                })
        
        if not dry_run:
            db.session.commit()
        
        return jsonify({
            'message': f"{'Would update' if dry_run else 'Updated'} {updated} fixtures",
            'updated': updated,
            'total_found': len(fixtures_to_update),
            'errors': errors[:10] if errors else [],
            'dry_run': dry_run
        })
        
    except Exception as e:
        logger.exception("admin_backfill_fixture_raw_json failed")
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to backfill fixture raw_json')), 500


@api_bp.route('/admin/tracked-players/backfill-ages', methods=['POST'])
@require_api_key
def admin_backfill_ages():
    """Backfill age and birth_date on TrackedPlayer records.

    Phase A: copy birth_date from linked PlayerJourney (zero API calls).
    Phase B: fetch from API-Football /players endpoint for remaining gaps.

    Body:
    - team_api_id: (optional) limit to one parent club
    - limit: (optional) max players to API-fetch (default 500)
    - dry_run: (optional) report only
    """
    try:
        from src.api_football_client import APIFootballClient
        from src.models.tracked_player import TrackedPlayer
        from src.models.journey import PlayerJourney
        from datetime import date

        data = request.get_json() or {}
        limit = min(data.get('limit', 500), 2000)
        dry_run = data.get('dry_run', False)
        team_api_id = data.get('team_api_id')

        # ── Phase A: journey-based fill (no API calls) ──
        journey_q = (
            db.session.query(TrackedPlayer)
            .join(PlayerJourney, TrackedPlayer.journey_id == PlayerJourney.id)
            .filter(
                TrackedPlayer.is_active.is_(True),
                TrackedPlayer.birth_date.is_(None),
                PlayerJourney.birth_date.isnot(None),
            )
        )
        journey_filled = 0
        for tp in journey_q.all():
            journey = tp.journey
            if not journey or not journey.birth_date:
                continue
            if not dry_run:
                tp.birth_date = journey.birth_date
                try:
                    bd = date.fromisoformat(journey.birth_date)
                    today = date.today()
                    tp.age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
                except (ValueError, TypeError):
                    pass
            journey_filled += 1

        if not dry_run and journey_filled:
            db.session.commit()

        # ── Phase B: API-based fill ──
        api_q = (
            TrackedPlayer.query
            .filter(TrackedPlayer.is_active.is_(True), TrackedPlayer.age.is_(None))
        )
        if team_api_id:
            from src.models.league import Team
            team = Team.query.filter_by(team_id=team_api_id).first()
            if team:
                api_q = api_q.filter(TrackedPlayer.team_id == team.id)

        players_to_fill = api_q.limit(limit).all()
        api_client_inst = APIFootballClient()
        api_filled = 0
        api_errors = 0

        for i, tp in enumerate(players_to_fill):
            try:
                # get_player_by_id returns {'player': {...}, 'statistics': [...]} directly
                resp = api_client_inst.get_player_by_id(tp.player_api_id, season=2025)
                if not resp:
                    continue
                player_data = resp.get('player', {})
                birth = player_data.get('birth', {}) or {}

                if not dry_run:
                    if player_data.get('age'):
                        tp.age = int(player_data['age'])
                    if birth.get('date'):
                        tp.birth_date = birth['date']
                        # Compute age from birth_date if API age missing
                        if not tp.age:
                            try:
                                bd = date.fromisoformat(birth['date'])
                                today = date.today()
                                tp.age = today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
                            except (ValueError, TypeError):
                                pass
                    if not tp.nationality and player_data.get('nationality'):
                        tp.nationality = player_data['nationality']
                    if not tp.photo_url and player_data.get('photo'):
                        tp.photo_url = player_data['photo']
                api_filled += 1
            except Exception as e:
                logger.warning(f"Backfill age failed for player {tp.player_api_id}: {e}")
                api_errors += 1

            # Commit in batches
            if not dry_run and (i + 1) % 50 == 0:
                db.session.commit()

        if not dry_run:
            db.session.commit()

        return jsonify({
            'kind': 'backfill-ages',
            'journey_filled': journey_filled,
            'api_filled': api_filled,
            'api_remaining': len(players_to_fill) - api_filled - api_errors,
            'api_errors': api_errors,
            'dry_run': dry_run,
        })

    except Exception as e:
        logger.exception("admin_backfill_ages failed")
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to backfill ages')), 500


@api_bp.route('/admin/fixtures/backfill-formations', methods=['POST'])
@require_api_key
def admin_backfill_formations():
    """Backfill formation, grid, and formation_position on existing FixturePlayerStats.

    Groups by fixture to minimize API calls (one lineup fetch per fixture).

    Body:
    - limit: (optional) max fixtures to process (default 200)
    - dry_run: (optional) report only
    """
    try:
        from src.api_football_client import APIFootballClient
        from src.models.weekly import Fixture, FixturePlayerStats
        from src.utils.formation_roles import grid_to_role
        from sqlalchemy import func

        data = request.get_json() or {}
        limit = min(data.get('limit', 200), 1000)
        dry_run = data.get('dry_run', False)

        # Find distinct fixture IDs that have stats rows missing formation
        fixture_ids = (
            db.session.query(FixturePlayerStats.fixture_id)
            .filter(FixturePlayerStats.formation.is_(None))
            .distinct()
            .limit(limit)
            .all()
        )
        fixture_ids = [row[0] for row in fixture_ids]

        if not fixture_ids:
            return jsonify({'message': 'No fixtures need formation backfill', 'updated': 0})

        api_client_inst = APIFootballClient()
        total_updated = 0
        total_errors = 0

        for fix_id in fixture_ids:
            fixture = Fixture.query.get(fix_id)
            if not fixture:
                continue

            try:
                lineups = api_client_inst.get_fixture_lineups(fixture.fixture_id_api).get('response', [])
            except Exception as e:
                logger.warning(f"Backfill formation: failed to fetch lineups for fixture {fixture.fixture_id_api}: {e}")
                total_errors += 1
                continue

            # Build lookup: {team_api_id: {formation, players: {player_id: grid}}}
            team_lineup = {}
            for lu in lineups:
                team_id = (lu.get('team') or {}).get('id')
                if not team_id:
                    continue
                formation = lu.get('formation')
                player_grids = {}
                for entry in lu.get('startXI') or []:
                    pb = (entry or {}).get('player') or {}
                    if pb.get('id'):
                        player_grids[pb['id']] = pb.get('grid')
                for entry in lu.get('substitutes') or []:
                    pb = (entry or {}).get('player') or {}
                    if pb.get('id'):
                        player_grids[pb['id']] = None  # subs have no grid
                team_lineup[team_id] = {'formation': formation, 'players': player_grids}

            # Update all stats rows for this fixture
            stats_rows = FixturePlayerStats.query.filter_by(fixture_id=fix_id).all()
            for fps in stats_rows:
                tl = team_lineup.get(fps.team_api_id)
                if not tl:
                    continue
                formation = tl['formation']
                grid = tl['players'].get(fps.player_api_id)
                pos = grid_to_role(formation, grid)

                if not dry_run:
                    fps.formation = formation
                    fps.grid = grid
                    fps.formation_position = pos
                total_updated += 1

            if not dry_run:
                db.session.commit()

        return jsonify({
            'kind': 'backfill-formations',
            'fixtures_processed': len(fixture_ids),
            'stats_updated': total_updated,
            'errors': total_errors,
            'dry_run': dry_run,
        })

    except Exception as e:
        logger.exception("admin_backfill_formations failed")
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to backfill formations')), 500


_YOUTH_LEVEL_LEAGUES = {
    'U21': [702],       # Premier League 2 Division One
    'U23': [702],       # Premier League 2 Division One
    'U18': [695, 696],  # U18 Premier League North / South
}
_youth_team_cache: dict[tuple, int | None] = {}  # (team_id, level, season) → youth_api_id


def _resolve_youth_team_for_sync(api_client, team, current_level: str, season: int) -> int | None:
    """Resolve a youth team API ID for fixture sync. Cached per session."""
    cache_key = (team.team_id, current_level, season)
    if cache_key in _youth_team_cache:
        return _youth_team_cache[cache_key]

    from src.services.youth_competition_resolver import resolve_youth_team_for_parent
    league_ids = _YOUTH_LEVEL_LEAGUES.get(current_level, [])
    teams_cache = {}
    for league_id in league_ids:
        youth_id, youth_name = resolve_youth_team_for_parent(
            api_client, league_id, season, team.name, teams_cache)
        if youth_id:
            _youth_team_cache[cache_key] = youth_id
            logger.info(f"[SYNC] Resolved youth team for {team.name} {current_level}: {youth_name} (ID={youth_id})")
            return youth_id

    _youth_team_cache[cache_key] = None
    return None


def _run_team_fixtures_sync(team_id: int, data: dict, job_id: str = None) -> dict:
    """Run the team fixture sync logic, optionally with progress updates.
    
    Uses TrackedPlayer (newer model) to find all active players for a team,
    including both on_loan and first_team players.
    """
    from src.api_football_client import APIFootballClient
    from src.models.weekly import Fixture, FixturePlayerStats
    from src.models.tracked_player import TrackedPlayer
    
    try:
        dry_run = data.get('dry_run', False)
        
        # Get current season
        now_utc = datetime.now(timezone.utc)
        current_year = now_utc.year
        current_month = now_utc.month
        season = data.get('season', current_year if current_month >= 8 else current_year - 1)
        
        team = Team.query.get(team_id)
        if not team:
            result = {'error': f'Team {team_id} not found'}
            return result
        
        # Get all active tracked players for this team (on_loan + first_team)
        tracked_players = TrackedPlayer.query.filter(
            TrackedPlayer.team_id == team_id,
            TrackedPlayer.is_active.is_(True),
            TrackedPlayer.status.in_(['on_loan', 'first_team', 'academy']),
        ).all()
        
        # Build a unified list of (player_api_id, player_name, team_api_id, team_name)
        players_to_sync = []
        for tp in tracked_players:
            if tp.status == 'on_loan' and tp.current_club_api_id:
                players_to_sync.append((
                    tp.player_api_id, tp.player_name,
                    tp.current_club_api_id, tp.current_club_name or resolve_team_name_and_logo(tp.current_club_api_id)[0],
                ))
            elif tp.status == 'on_loan' and not tp.current_club_api_id:
                logger.warning(f"[SYNC] Skipping on-loan {tp.player_name} (id={tp.id}): current_club_api_id is null")
            elif tp.status in ('first_team', 'academy'):
                # Sync parent first-team fixtures
                players_to_sync.append((
                    tp.player_api_id, tp.player_name,
                    team.team_id, team.name,
                ))
                # For academy players, also sync youth team fixtures
                if tp.status == 'academy' and tp.current_level:
                    youth_id = _resolve_youth_team_for_sync(api_client, team, tp.current_level, season)
                    if youth_id:
                        players_to_sync.append((
                            tp.player_api_id, tp.player_name,
                            youth_id, f"{team.name} {tp.current_level}",
                        ))
        
        total_players = len(players_to_sync)
        if job_id:
            _update_job(job_id, total=total_players, progress=0, current_player=f'Syncing {total_players} players from {team.name}...')
        
        api_client = APIFootballClient()
        
        results = []
        total_synced = 0
        total_skipped = 0
        total_errors = 0
        
        for idx, (p_api_id, p_name, p_team_api_id, p_team_name) in enumerate(players_to_sync):
            player_result = {
                'player_id': p_api_id,
                'player_name': p_name,
                'team': p_team_name,
                'synced': 0,
                'skipped': 0,
                'errors': []
            }
            
            try:
                # Fetch all fixtures for this player's team this season
                season_start = f"{season}-08-01"
                season_end = f"{season + 1}-06-30"
                
                fixtures = api_client.get_fixtures_for_team(
                    p_team_api_id, 
                    season, 
                    season_start, 
                    season_end
                )
                
                for fx in fixtures:
                    fixture_info = fx.get('fixture', {})
                    fixture_id_api = fixture_info.get('id')
                    fixture_status = fixture_info.get('status', {}).get('short', '')
                    
                    # Only process finished games
                    if fixture_status not in ('FT', 'AET', 'PEN'):
                        player_result['skipped'] += 1
                        continue
                    
                    # Check if we already have this fixture
                    existing_fixture = Fixture.query.filter_by(fixture_id_api=fixture_id_api).first()
                    
                    if not existing_fixture:
                        # Create the fixture
                        if not dry_run:
                            teams = fx.get('teams', {})
                            goals = fx.get('goals', {})
                            league = fx.get('league', {})
                            
                            existing_fixture = Fixture(
                                fixture_id_api=fixture_id_api,
                                date_utc=datetime.fromisoformat(fixture_info.get('date', '').replace('Z', '+00:00')) if fixture_info.get('date') else None,
                                season=season,
                                competition_name=league.get('name'),
                                home_team_api_id=teams.get('home', {}).get('id'),
                                away_team_api_id=teams.get('away', {}).get('id'),
                                home_goals=goals.get('home'),
                                away_goals=goals.get('away'),
                            )
                            db.session.add(existing_fixture)
                            db.session.flush()
                    
                    # Check if we have player stats for this fixture
                    if existing_fixture:
                        existing_stats = FixturePlayerStats.query.filter_by(
                            fixture_id=existing_fixture.id,
                            player_api_id=p_api_id
                        ).first()
                        
                        if existing_stats:
                            player_result['skipped'] += 1
                            continue
                    
                    # Fetch player stats for this fixture
                    try:
                        player_stats = api_client.get_player_stats_for_fixture(p_api_id, season, fixture_id_api)
                        
                        if player_stats and player_stats.get('statistics'):
                            stat_list = player_stats['statistics']
                            if not stat_list:
                                player_result['skipped'] += 1
                                continue
                            st = stat_list[0] if isinstance(stat_list, list) else stat_list
                            
                            # Extract stats
                            games = st.get('games', {}) or {}
                            goals_block = st.get('goals', {}) or {}
                            cards = st.get('cards', {}) or {}
                            shots = st.get('shots', {}) or {}
                            passes = st.get('passes', {}) or {}
                            tackles = st.get('tackles', {}) or {}
                            duels = st.get('duels', {}) or {}
                            dribbles = st.get('dribbles', {}) or {}
                            fouls = st.get('fouls', {}) or {}
                            penalty = st.get('penalty', {}) or {}
                            
                            minutes = games.get('minutes', 0) or 0
                            
                            if (minutes > 0 or games.get('substitute') is not None) and not dry_run and existing_fixture:
                                formation, grid_val, formation_pos = _extract_lineup_info(
                                    api_client, fixture_id_api, p_api_id, p_team_api_id)
                                fps = FixturePlayerStats(
                                    fixture_id=existing_fixture.id,
                                    player_api_id=p_api_id,
                                    team_api_id=p_team_api_id,
                                    minutes=minutes,
                                    position=games.get('position'),
                                    rating=games.get('rating'),
                                    goals=goals_block.get('total', 0) or 0,
                                    assists=goals_block.get('assists', 0) or 0,
                                    yellows=cards.get('yellow', 0) or 0,
                                    reds=cards.get('red', 0) or 0,
                                    shots_total=shots.get('total'),
                                    shots_on=shots.get('on'),
                                    passes_total=passes.get('total'),
                                    passes_key=passes.get('key'),
                                    tackles_total=tackles.get('total'),
                                    duels_won=duels.get('won'),
                                    duels_total=duels.get('total'),
                                    dribbles_success=dribbles.get('success'),
                                    saves=goals_block.get('saves'),
                                    goals_conceded=goals_block.get('conceded'),
                                    fouls_drawn=fouls.get('drawn'),
                                    fouls_committed=fouls.get('committed'),
                                    penalty_saved=penalty.get('saved'),
                                    formation=formation,
                                    grid=grid_val,
                                    formation_position=formation_pos,
                                )
                                db.session.add(fps)
                                player_result['synced'] += 1
                            elif minutes > 0 or games.get('substitute') is not None:
                                player_result['synced'] += 1  # Dry run counts this
                            else:
                                player_result['skipped'] += 1
                        else:
                            player_result['skipped'] += 1
                            
                    except Exception as e:
                        player_result['errors'].append(f"Fixture {fixture_id_api}: {str(e)[:50]}")
                
                if not dry_run:
                    db.session.commit()
                    
            except Exception as e:
                player_result['errors'].append(str(e)[:100])
                total_errors += 1
            
            total_synced += player_result['synced']
            total_skipped += player_result['skipped']
            results.append(player_result)
            
            if job_id and idx % 5 == 0:
                _update_job(job_id, progress=idx + 1, current_player=f"{loaned.player_name} ({player_result['synced']} new)")
        
        final_result = {
            'team_id': team_id,
            'team_name': team.name,
            'season': season,
            'dry_run': dry_run,
            'players_processed': total_players,
            'total_synced': total_synced,
            'total_skipped': total_skipped,
            'total_errors': total_errors,
            'details': results[:50],  # Limit details for response size
        }
        
        # Note: completion status is handled by the wrapper function for background jobs
        return final_result
        
    except Exception as e:
        logger.exception(f"_run_team_fixtures_sync failed for team {team_id}")
        db.session.rollback()
        return {'error': str(e)}


# --- Public: Flag submission (no auth) ---

_FLAG_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$')

def _flag_hash_ip(ip: str) -> str | None:
    """Hash IP for spam prevention without storing raw IPs."""
    if not ip:
        return None
    import hashlib
    return hashlib.sha256(ip.encode()).hexdigest()

def _flag_get_client_ip() -> str:
    """Get client IP from request, handling proxies."""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    return request.remote_addr

@api_bp.route('/flags/submit', methods=['POST'])
@limiter.limit("10 per minute")
@limiter.limit("30 per hour")
def submit_flag():
    """Public endpoint for users to flag incorrect data."""
    data = request.get_json() or {}

    # Validate required fields
    reason = (data.get('reason') or '').strip()
    if not reason:
        return jsonify({'error': 'reason is required'}), 400
    if len(reason) > 1000:
        return jsonify({'error': 'reason must be 1000 characters or less'}), 400

    category = (data.get('category') or 'other').strip().lower()
    if category not in FLAG_CATEGORIES:
        return jsonify({'error': f'category must be one of: {", ".join(FLAG_CATEGORIES)}'}), 400

    # Sanitize text inputs
    reason = sanitize_plain_text(reason)
    if not reason:
        return jsonify({'error': 'reason contains invalid content'}), 400

    player_name = sanitize_plain_text((data.get('player_name') or '').strip()) or None
    team_name = sanitize_plain_text((data.get('team_name') or '').strip()) or None
    email = (data.get('email') or '').strip() or None

    if email:
        if not _FLAG_EMAIL_RE.match(email) or len(email) > 254:
            return jsonify({'error': 'Invalid email format'}), 400

    # Spam prevention: DB-level rate limiting
    ip_hash = _flag_hash_ip(_flag_get_client_ip())
    user_agent = request.headers.get('User-Agent', '')[:512]

    if ip_hash:
        one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
        recent_count = PlayerFlag.query.filter(
            PlayerFlag.ip_address == ip_hash,
            PlayerFlag.created_at >= one_hour_ago
        ).count()
        if recent_count >= 5:
            return jsonify({'error': 'Too many submissions. Please try again later.'}), 429

    # Duplicate detection: same reason text within 24 hours
    twenty_four_hours_ago = datetime.now(timezone.utc) - timedelta(hours=24)
    duplicate = PlayerFlag.query.filter(
        PlayerFlag.reason == reason,
        PlayerFlag.created_at >= twenty_four_hours_ago
    ).first()
    if duplicate:
        return jsonify({'error': 'This issue has already been reported.'}), 400

    source = (data.get('source') or 'website').strip().lower()
    if source not in ('website', 'newsletter'):
        source = 'website'

    flag = PlayerFlag(
        reason=reason,
        category=category,
        source=source,
        player_api_id=data.get('player_api_id'),
        primary_team_api_id=data.get('primary_team_api_id'),
        player_name=player_name,
        team_name=team_name,
        newsletter_id=data.get('newsletter_id'),
        page_url=sanitize_plain_text((data.get('page_url') or '').strip()[:500]) or None,
        email=email,
        season=data.get('season'),
        ip_address=ip_hash,
        user_agent=user_agent,
        status='pending',
    )
    db.session.add(flag)
    db.session.commit()

    return jsonify({'success': True, 'flag_id': flag.id}), 201


# --- Admin: Flags management (list/update/bulk/stats) ---

@api_bp.route('/admin/flags', methods=['GET'])
@require_api_key
def admin_list_flags():
    try:
        status = (request.args.get('status') or 'all').strip().lower()
        category = (request.args.get('category') or '').strip().lower()
        source = (request.args.get('source') or '').strip().lower()
        search = (request.args.get('search') or '').strip()
        page = max(1, request.args.get('page', 1, type=int))
        per_page = min(100, max(1, request.args.get('per_page', 25, type=int)))

        q = PlayerFlag.query

        if status in FLAG_STATUSES:
            q = q.filter(PlayerFlag.status == status)
        if category in FLAG_CATEGORIES:
            q = q.filter(PlayerFlag.category == category)
        if source in ('website', 'newsletter'):
            q = q.filter(PlayerFlag.source == source)
        if search:
            pattern = f'%{search}%'
            q = q.filter(or_(
                PlayerFlag.reason.ilike(pattern),
                PlayerFlag.player_name.ilike(pattern),
                PlayerFlag.team_name.ilike(pattern),
            ))

        total = q.count()
        rows = q.order_by(PlayerFlag.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()

        return jsonify({
            'flags': [r.to_dict() for r in rows],
            'total': total,
            'page': page,
            'per_page': per_page,
        })
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/flags/<int:flag_id>', methods=['POST'])
@require_api_key
def admin_update_flag(flag_id: int):
    try:
        row = PlayerFlag.query.get_or_404(flag_id)
        data = request.get_json() or {}
        status = (data.get('status') or '').strip().lower()
        note = (data.get('note') or '').strip()
        if status in FLAG_STATUSES:
            row.status = status
            if status in ('resolved', 'dismissed') and not row.resolved_at:
                row.resolved_at = datetime.now(timezone.utc)
        if note:
            row.admin_note = note
        db.session.commit()
        return jsonify({'message': 'updated', 'flag': row.to_dict()})
    except Exception as e:
        logger.exception('admin_update_flag failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/flags/bulk', methods=['POST'])
@require_api_key
def admin_bulk_flags():
    """Bulk update flag statuses."""
    try:
        data = request.get_json() or {}
        flag_ids = data.get('flag_ids', [])
        action = (data.get('action') or '').strip().lower()
        note = (data.get('note') or '').strip()

        if not flag_ids or not isinstance(flag_ids, list):
            return jsonify({'error': 'flag_ids is required'}), 400
        if action not in FLAG_STATUSES:
            return jsonify({'error': f'action must be one of: {", ".join(FLAG_STATUSES)}'}), 400

        rows = PlayerFlag.query.filter(PlayerFlag.id.in_(flag_ids)).all()
        now = datetime.now(timezone.utc)
        for row in rows:
            row.status = action
            if action in ('resolved', 'dismissed') and not row.resolved_at:
                row.resolved_at = now
            if note:
                row.admin_note = note
        db.session.commit()
        return jsonify({'message': f'Updated {len(rows)} flags', 'updated': len(rows)})
    except Exception as e:
        logger.exception('admin_bulk_flags failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/flags/stats', methods=['GET'])
@require_api_key
def admin_flags_stats():
    """Get flag counts by status, category, and source."""
    try:
        by_status = dict(db.session.query(
            PlayerFlag.status, func.count(PlayerFlag.id)
        ).group_by(PlayerFlag.status).all())

        by_category = dict(db.session.query(
            PlayerFlag.category, func.count(PlayerFlag.id)
        ).group_by(PlayerFlag.category).all())

        by_source = dict(db.session.query(
            PlayerFlag.source, func.count(PlayerFlag.id)
        ).group_by(PlayerFlag.source).all())

        return jsonify({
            'by_status': by_status,
            'by_category': by_category,
            'by_source': by_source,
            'total': sum(by_status.values()),
        })
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


# --- Admin: Team Data Management ---

@api_bp.route('/admin/teams/<int:team_id>/data', methods=['DELETE'])
@require_api_key
def admin_delete_team_data(team_id: int):
    """
    Delete all tracking data for a team while keeping the team record.
    
    This removes:
    - All TrackedPlayer records where this team is the parent team
    - All newsletters for this team
    - All weekly loan reports for this team
    - All user subscriptions for this team
    - All journalist assignments for this team
    - All newsletter commentaries for this team
    - Related fixture player stats
    
    The team record itself is preserved but marked as is_tracked=False.
    
    Query params:
    - dry_run: If 'true', only return what would be deleted without actually deleting
    """
    try:
        from src.models.weekly import WeeklyLoanReport, WeeklyLoanAppearance, FixturePlayerStats, Fixture
        
        team = Team.query.get_or_404(team_id)
        dry_run = request.args.get('dry_run', 'false').lower() in ('true', '1', 'yes')
        
        # Collect all data to delete
        summary = {
            'team_id': team.id,
            'team_name': team.name,
            'team_api_id': team.team_id,
            'dry_run': dry_run,
            'deleted': {}
        }
        
        # 1. Get tracked players where this team is the parent team
        tracked_players_del = TrackedPlayer.query.filter_by(team_id=team_id).all()
        player_api_ids = [tp.player_api_id for tp in tracked_players_del]
        summary['deleted']['tracked_players'] = len(tracked_players_del)
        
        # 2. Get newsletters for this team
        newsletters = Newsletter.query.filter_by(team_id=team_id).all()
        newsletter_ids = [n.id for n in newsletters]
        summary['deleted']['newsletters'] = len(newsletters)
        
        # 3. Get weekly loan reports for this team
        weekly_reports = WeeklyLoanReport.query.filter_by(parent_team_id=team_id).all()
        report_ids = [r.id for r in weekly_reports]
        summary['deleted']['weekly_reports'] = len(weekly_reports)
        
        # 4. Get weekly loan appearances for these reports
        appearances_count = 0
        if report_ids:
            appearances_count = WeeklyLoanAppearance.query.filter(
                WeeklyLoanAppearance.weekly_report_id.in_(report_ids)
            ).count()
        summary['deleted']['weekly_appearances'] = appearances_count
        
        # 5. Get user subscriptions for this team
        subscriptions = UserSubscription.query.filter_by(team_id=team_id).all()
        summary['deleted']['subscriptions'] = len(subscriptions)
        
        # 6. Get journalist assignments for this team
        assignments = JournalistTeamAssignment.query.filter_by(team_id=team_id).all()
        summary['deleted']['journalist_assignments'] = len(assignments)
        
        # 7. Get newsletter commentaries for this team
        commentaries = NewsletterCommentary.query.filter_by(team_id=team_id).all()
        # Also get commentaries attached to newsletters
        if newsletter_ids:
            newsletter_commentaries = NewsletterCommentary.query.filter(
                NewsletterCommentary.newsletter_id.in_(newsletter_ids)
            ).all()
            commentaries = list(set(commentaries + newsletter_commentaries))
        summary['deleted']['commentaries'] = len(commentaries)
        
        # 8. Get newsletter comments for these newsletters
        comments_count = 0
        if newsletter_ids:
            comments_count = NewsletterComment.query.filter(
                NewsletterComment.newsletter_id.in_(newsletter_ids)
            ).count()
        summary['deleted']['newsletter_comments'] = comments_count
        
        # 9. Get YouTube links for these newsletters
        youtube_links_count = 0
        if newsletter_ids:
            youtube_links_count = NewsletterPlayerYoutubeLink.query.filter(
                NewsletterPlayerYoutubeLink.newsletter_id.in_(newsletter_ids)
            ).count()
        summary['deleted']['youtube_links'] = youtube_links_count
        
        # 10. Get fixture player stats for loan players (optional, expensive)
        fixture_stats_count = 0
        if player_api_ids:
            fixture_stats_count = FixturePlayerStats.query.filter(
                FixturePlayerStats.player_api_id.in_(player_api_ids)
            ).count()
        summary['deleted']['fixture_player_stats'] = fixture_stats_count
        
        if dry_run:
            summary['message'] = 'Dry run complete. No data was deleted.'
            return jsonify(summary)
        
        # Actually delete the data in correct order (respecting foreign keys)
        
        # Delete fixture player stats
        if player_api_ids:
            FixturePlayerStats.query.filter(
                FixturePlayerStats.player_api_id.in_(player_api_ids)
            ).delete(synchronize_session=False)
        
        # Delete YouTube links
        if newsletter_ids:
            NewsletterPlayerYoutubeLink.query.filter(
                NewsletterPlayerYoutubeLink.newsletter_id.in_(newsletter_ids)
            ).delete(synchronize_session=False)
        
        # Delete newsletter comments
        if newsletter_ids:
            NewsletterComment.query.filter(
                NewsletterComment.newsletter_id.in_(newsletter_ids)
            ).delete(synchronize_session=False)
        
        # Delete commentaries
        for commentary in commentaries:
            db.session.delete(commentary)
        
        # Delete journalist assignments
        for assignment in assignments:
            db.session.delete(assignment)
        
        # Delete user subscriptions
        for sub in subscriptions:
            db.session.delete(sub)
        
        # Delete weekly appearances first (foreign key to reports)
        if report_ids:
            WeeklyLoanAppearance.query.filter(
                WeeklyLoanAppearance.weekly_report_id.in_(report_ids)
            ).delete(synchronize_session=False)
        
        # Delete weekly reports
        for report in weekly_reports:
            db.session.delete(report)
        
        # Delete newsletters
        for newsletter in newsletters:
            db.session.delete(newsletter)
        
        # Delete tracked players
        for tp in tracked_players_del:
            db.session.delete(tp)
        
        # Mark team as not tracked
        team.is_tracked = False
        team.newsletters_active = False
        
        db.session.commit()
        
        summary['message'] = f'Successfully deleted all tracking data for {team.name}'
        return jsonify(summary)
        
    except Exception as e:
        logger.exception('admin_delete_team_data failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to delete team data')), 500


@api_bp.route('/admin/teams/<int:team_id>/tracking', methods=['POST'])
@require_api_key
def admin_update_team_tracking(team_id: int):
    """
    Update tracking status for a team.
    
    Body: { "is_tracked": true/false }
    """
    try:
        team = Team.query.get_or_404(team_id)
        data = request.get_json() or {}

        was_tracked = team.is_tracked
        if 'is_tracked' in data:
            team.is_tracked = bool(data['is_tracked'])

        db.session.commit()

        response = {
            'message': 'updated',
            'team_id': team.id,
            'team_name': team.name,
            'is_tracked': team.is_tracked,
        }

        # Auto-seed academy players when a team is newly tracked
        if team.is_tracked and not was_tracked:
            try:
                seed_job_id = _start_background_seed(team.id)
                response['seed_job_id'] = seed_job_id
            except Exception as seed_err:
                logger.warning('Auto-seed failed for team %s: %s', team.name, seed_err)
                response['seed_error'] = str(seed_err)

        return jsonify(response)
    except Exception as e:
        logger.exception('admin_update_team_tracking failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to update team tracking')), 500


@api_bp.route('/admin/teams/<int:team_id>/name', methods=['PUT'])
@require_api_key
def admin_update_team_name(team_id: int):
    """
    Update the name for a team. Useful for correcting placeholder names like "Team 12345".
    
    Body: { "name": "Correct Team Name" }
    """
    try:
        team = Team.query.get_or_404(team_id)
        data = request.get_json() or {}
        
        new_name = (data.get('name') or '').strip()
        if not new_name:
            return jsonify({'error': 'name is required'}), 400
        
        old_name = team.name
        team.name = new_name
        team.updated_at = datetime.now(timezone.utc)
        
        db.session.commit()
        return jsonify({
            'message': 'updated',
            'team_id': team.id,
            'api_team_id': team.team_id,
            'old_name': old_name,
            'new_name': team.name,
        })
    except Exception as e:
        logger.exception('admin_update_team_name failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to update team name')), 500


@api_bp.route('/admin/teams/placeholder-names', methods=['GET'])
@require_api_key
def admin_list_placeholder_team_names():
    """
    List teams with placeholder names like "Team 12345".
    
    Query params:
      - season: Filter by season year
      - limit: Max results (default 100)
    """
    try:
        season = request.args.get('season')
        limit = request.args.get('limit', 100, type=int)
        
        query = Team.query.filter(
            db.func.lower(Team.name).like('team %')
        )
        
        if season:
            query = query.filter(Team.season == int(season))
        
        teams = query.order_by(Team.name.asc()).limit(limit).all()
        
        return jsonify([{
            'id': t.id,
            'team_id': t.team_id,
            'name': t.name,
            'season': t.season,
            'country': t.country,
            'logo': t.logo,
            'league_name': t.league.name if t.league else None,
        } for t in teams])
    except Exception as e:
        logger.exception('admin_list_placeholder_team_names failed')
        return jsonify(_safe_error_payload(e, 'Failed to list placeholder team names')), 500


@api_bp.route('/admin/teams/bulk-fix-names', methods=['POST'])
@require_api_key
def admin_bulk_fix_team_names():
    """
    Attempt to fix placeholder team names by fetching from API-Football.
    
    Body: {
        "team_ids": [1, 2, 3],  # Optional: specific teams to fix
        "season": 2024,  # Required: season for API lookup
        "dry_run": false  # Preview changes without saving
    }
    """
    try:
        data = request.get_json() or {}
        team_ids = data.get('team_ids', [])
        season = data.get('season')
        dry_run = bool(data.get('dry_run', False))
        
        if not season:
            return jsonify({'error': 'season is required'}), 400
        
        # Find teams to fix
        if team_ids:
            teams = Team.query.filter(
                Team.id.in_(team_ids),
                db.func.lower(Team.name).like('team %')
            ).all()
        else:
            teams = Team.query.filter(
                db.func.lower(Team.name).like('team %'),
                Team.season == int(season)
            ).limit(50).all()
        
        updated = []
        skipped = []
        
        for team in teams:
            result = _update_team_name_if_missing(team, season=int(season), dry_run=dry_run)
            if result.get('status') in ('updated', 'would_update'):
                updated.append({
                    'id': team.id,
                    'api_team_id': team.team_id,
                    'old_name': team.name if dry_run else result.get('old_name', team.name),
                    'new_name': result.get('new_name'),
                })
            else:
                skipped.append({
                    'id': team.id,
                    'api_team_id': team.team_id,
                    'name': team.name,
                    'status': result.get('status'),
                })
        
        if not dry_run:
            db.session.commit()
        
        return jsonify({
            'dry_run': dry_run,
            'updated': updated,
            'skipped': skipped,
            'updated_count': len(updated),
            'skipped_count': len(skipped),
        })
    except Exception as e:
        logger.exception('admin_bulk_fix_team_names failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to bulk fix team names')), 500


@api_bp.route('/admin/teams/propagate-names', methods=['POST'])
@require_api_key
def admin_propagate_team_names():
    """
    Propagate corrected team names from the Teams table to:
    1. Newsletter structured_content JSON

    Body: {
        "team_ids": [1, 2, 3],  # Optional: specific teams to propagate (DB IDs)
        "dry_run": false,  # Preview changes without saving
        "fix_newsletters": true  # Update Newsletter structured_content
    }
    """
    try:
        import json as json_module
        
        data = request.get_json() or {}
        team_ids = data.get('team_ids', [])
        dry_run = bool(data.get('dry_run', False))
        fix_newsletters = bool(data.get('fix_newsletters', True))

        results = {
            'dry_run': dry_run,
            'newsletters_updated': 0,
            'details': []
        }
        
        # Get teams to process
        if team_ids:
            teams = Team.query.filter(Team.id.in_(team_ids)).all()
        else:
            # Only process teams that had placeholder names (now fixed)
            # We can't tell which ones were fixed, so process all
            teams = Team.query.all()
        
        # Build team_id -> name mapping
        team_name_map = {}
        for t in teams:
            team_name_map[t.id] = t.name
        
        if fix_newsletters:
            # Update Newsletter structured_content
            newsletters = Newsletter.query.filter(
                Newsletter.structured_content.isnot(None)
            ).all()
            
            for nl in newsletters:
                try:
                    content = json_module.loads(nl.structured_content) if nl.structured_content else None
                    if not content:
                        continue
                    
                    modified = False
                    
                    # Fix team_name at top level
                    if content.get('team_id') and content['team_id'] in team_name_map:
                        new_name = team_name_map[content['team_id']]
                        if content.get('team_name') != new_name:
                            content['team_name'] = new_name
                            modified = True
                    
                    # Fix player loan_team and loan_team_name in player items
                    for item in content.get('player_items', []):
                        loan_team_id = item.get('loan_team_id')
                        if loan_team_id and loan_team_id in team_name_map:
                            new_name = team_name_map[loan_team_id]
                            if item.get('loan_team') != new_name:
                                item['loan_team'] = new_name
                                modified = True
                            if item.get('loan_team_name') != new_name:
                                item['loan_team_name'] = new_name
                                modified = True
                    
                    if modified:
                        results['details'].append({
                            'type': 'newsletter',
                            'newsletter_id': nl.id,
                            'team_id': nl.team_id
                        })
                        
                        if not dry_run:
                            nl.structured_content = json_module.dumps(content)
                            results['newsletters_updated'] += 1
                            
                except Exception as e:
                    logger.warning(f"Failed to update newsletter {nl.id}: {e}")
        
        if not dry_run:
            db.session.commit()
        
        return jsonify(results)
    except Exception as e:
        logger.exception('admin_propagate_team_names failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to propagate team names')), 500


@api_bp.route('/admin/teams/bulk-tracking', methods=['POST'])
@require_api_key
def admin_bulk_update_team_tracking():
    """
    Bulk update tracking status for multiple teams.
    
    Body: { 
        "team_ids": [1, 2, 3], 
        "is_tracked": true/false,
        "exclude_team_ids": [4, 5]  # Optional: teams to exclude from update
    }
    
    Or to update all teams except some:
    { 
        "all": true,
        "is_tracked": false,
        "exclude_team_ids": [4]  # Keep team 4 tracked
    }
    """
    try:
        data = request.get_json() or {}
        is_tracked = bool(data.get('is_tracked', False))
        exclude_ids = data.get('exclude_team_ids', [])
        
        if data.get('all'):
            # Update all teams except excluded ones
            query = Team.query
            if exclude_ids:
                query = query.filter(~Team.id.in_(exclude_ids))
            teams = query.all()
        else:
            team_ids = data.get('team_ids', [])
            if not team_ids:
                return jsonify({'error': 'team_ids or all=true required'}), 400
            teams = Team.query.filter(Team.id.in_(team_ids)).all()
        
        # Capture previous tracking state before updating
        was_tracked = {t.id: t.is_tracked for t in teams}

        updated_count = 0
        for team in teams:
            if team.id not in exclude_ids:
                team.is_tracked = is_tracked
                updated_count += 1

        db.session.commit()

        # Auto-seed newly tracked teams in a single background process
        seed_info = None
        if is_tracked:
            newly_tracked = [t for t in teams
                             if t.id not in exclude_ids
                             and t.is_active
                             and not was_tracked.get(t.id, False)]
            if newly_tracked:
                import multiprocessing
                job_id = _create_background_job('seed_bulk_tracked')
                team_db_ids = [t.id for t in newly_tracked]
                p = multiprocessing.Process(
                    target=_run_seed_teams_process,
                    args=(job_id, team_db_ids),
                    daemon=False,
                )
                p.start()
                multiprocessing.process._children.discard(p)
                seed_info = {
                    'job_id': job_id,
                    'teams_to_seed': len(newly_tracked),
                    'team_names': [t.name for t in newly_tracked],
                }

        response = {
            'message': f'Updated {updated_count} teams',
            'is_tracked': is_tracked,
            'updated_count': updated_count,
        }
        if seed_info:
            response['seed_job'] = seed_info
            response['message'] += f' (seeding {seed_info["teams_to_seed"]} newly tracked teams)'
        return jsonify(response)
    except Exception as e:
        logger.exception('admin_bulk_update_team_tracking failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to bulk update team tracking')), 500


# --- Admin: Team Tracking Requests ---

@api_bp.route('/admin/tracking-requests', methods=['GET'])
@require_api_key
def admin_list_tracking_requests():
    """List all team tracking requests with optional status filter."""
    try:
        status = (request.args.get('status') or 'all').strip().lower()
        q = TeamTrackingRequest.query
        if status in ('pending', 'approved', 'rejected'):
            q = q.filter(TeamTrackingRequest.status == status)
        rows = q.order_by(TeamTrackingRequest.created_at.desc()).all()
        return jsonify([r.to_dict() for r in rows])
    except Exception as e:
        logger.exception('admin_list_tracking_requests failed')
        return jsonify(_safe_error_payload(e, 'Failed to list tracking requests')), 500


@api_bp.route('/admin/tracking-requests/<int:request_id>', methods=['POST'])
@require_api_key
def admin_update_tracking_request(request_id: int):
    """
    Update a tracking request status (approve/reject).
    
    Body: { "status": "approved"|"rejected", "note": "optional admin note" }
    
    If approved, the team's is_tracked flag will be set to true.
    """
    try:
        req = TeamTrackingRequest.query.get_or_404(request_id)
        data = request.get_json() or {}
        status = (data.get('status') or '').strip().lower()
        note = (data.get('note') or '').strip()
        
        if status not in ('approved', 'rejected', 'pending'):
            return jsonify({'error': 'status must be approved, rejected, or pending'}), 400
        
        req.status = status
        if note:
            req.admin_note = note
        
        if status in ('approved', 'rejected'):
            req.resolved_at = datetime.now(timezone.utc)
        else:
            req.resolved_at = None
        
        # If approved, mark the team as tracked
        if status == 'approved' and req.team_id:
            team = Team.query.get(req.team_id)
            if team:
                team.is_tracked = True
        
        db.session.commit()
        return jsonify({
            'message': 'updated',
            'request': req.to_dict()
        })
    except Exception as e:
        logger.exception('admin_update_tracking_request failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to update tracking request')), 500


# --- Public: Team Tracking Requests ---

@api_bp.route('/teams/<team_identifier>/request-tracking', methods=['POST'])
def submit_tracking_request(team_identifier: str):
    """
    Submit a request to track a team.

    Body: { "email": "optional@email.com", "reason": "Why you want this team tracked" }

    Rate limited to prevent abuse.
    """
    try:
        team = resolve_team_by_identifier(team_identifier)
        team_id = team.id

        # Check if team is already tracked
        if team.is_tracked:
            return jsonify({'error': 'This team is already being tracked'}), 400

        # Check for recent pending request for same team (prevent duplicates)
        recent_cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        existing = TeamTrackingRequest.query.filter(
            TeamTrackingRequest.team_id == team_id,
            TeamTrackingRequest.status == 'pending',
            TeamTrackingRequest.created_at > recent_cutoff
        ).first()
        
        if existing:
            return jsonify({
                'message': 'A tracking request for this team is already pending',
                'existing_request_id': existing.id
            }), 200
        
        data = request.get_json() or {}
        email = (data.get('email') or '').strip()
        reason = (data.get('reason') or '').strip()
        
        # Create the request
        tracking_request = TeamTrackingRequest(
            team_id=team.id,
            team_api_id=team.team_id,
            team_name=team.name,
            email=email[:255] if email else None,
            reason=reason[:1000] if reason else None,
            ip_address=get_client_ip()[:64] if get_client_ip() else None,
            user_agent=(request.headers.get('User-Agent') or '')[:512],
            status='pending'
        )
        
        db.session.add(tracking_request)
        db.session.commit()

        from src.services.admin_notify_service import notify_tracking_request
        notify_tracking_request(team.name, email or None, reason or None)

        return jsonify({
            'message': f'Tracking request submitted for {team.name}',
            'request_id': tracking_request.id
        }), 201

    except Exception as e:
        logger.exception('submit_tracking_request failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to submit tracking request')), 500


@api_bp.route('/teams/<team_identifier>/tracking-status', methods=['GET'])
def get_team_tracking_status(team_identifier: str):
    """
    Get tracking status for a team, including any pending requests.
    """
    try:
        team = resolve_team_by_identifier(team_identifier)
        team_id = team.id

        pending_request = TeamTrackingRequest.query.filter(
            TeamTrackingRequest.team_id == team_id,
            TeamTrackingRequest.status == 'pending'
        ).first()

        return jsonify({
            'team_id': team.id,
            'team_name': team.name,
            'is_tracked': team.is_tracked,
            'has_pending_request': pending_request is not None,
            'pending_request_id': pending_request.id if pending_request else None,
            'loan_count': TrackedPlayer.query.filter_by(team_id=team_id, is_active=True).count()
        })
    except Exception as e:
        logger.exception('get_team_tracking_status failed')
        return jsonify(_safe_error_payload(e, 'Failed to get tracking status')), 500


# --- Admin: Newsletters management (list/view/update) ---


def _normalize_int_list(values) -> list[int]:
    """Normalize a list of values into unique positive integers."""
    if not values:
        return []
    normalized: list[int] = []
    seen = set()
    for value in values:
        try:
            num = int(value)
        except (TypeError, ValueError):
            continue
        if num <= 0 or num in seen:
            continue
        normalized.append(num)
        seen.add(num)
    return normalized


def _get_param_value(source, key):
    if source is None:
        return None
    getter = getattr(source, 'get', None)
    if callable(getter):
        value = getter(key)
    else:
        value = source[key] if isinstance(source, dict) and key in source else None
    if isinstance(value, (list, tuple)):
        return value[0] if value else None
    return value


def _apply_admin_newsletter_filters(base_query, params):
    """Apply shared newsletter filters used by admin endpoints.

    Returns tuple of (query, meta) where meta includes flags about applied filters.
    """
    params = params or {}
    query = base_query
    meta = {
        'issue_filter_applied': False,
    }

    # Team filter
    team_value = _get_param_value(params, 'team')
    try:
        team_id = int(team_value) if team_value not in (None, '') else None
    except (TypeError, ValueError):
        team_id = None
    if team_id:
        query = query.filter(Newsletter.team_id == team_id)
        meta['team_id'] = team_id

    # Published toggle
    published_only_value = _get_param_value(params, 'published_only')
    if published_only_value is not None:
        want = str(published_only_value).lower() in ('true', '1', 'yes', 'y')
        query = query.filter(Newsletter.published.is_(want))
        meta['published_only'] = want

    # Week range
    week_start_str = _get_param_value(params, 'week_start')
    week_end_str = _get_param_value(params, 'week_end')
    if week_start_str and week_end_str:
        try:
            ws = datetime.strptime(week_start_str, '%Y-%m-%d').date()
            we = datetime.strptime(week_end_str, '%Y-%m-%d').date()
            query = query.filter(
                db.and_(
                    Newsletter.week_start_date <= we,
                    Newsletter.week_end_date >= ws,
                )
            )
            meta['week_range'] = (week_start_str, week_end_str)
        except ValueError:
            meta['week_range'] = None

    # Issue date range (primary)
    issue_start_str = _get_param_value(params, 'issue_start')
    issue_end_str = _get_param_value(params, 'issue_end')
    if issue_start_str and issue_end_str:
        try:
            isd = datetime.strptime(issue_start_str, '%Y-%m-%d').date()
            ied = datetime.strptime(issue_end_str, '%Y-%m-%d').date()
            query = query.filter(
                db.and_(
                    Newsletter.issue_date >= isd,
                    Newsletter.issue_date <= ied,
                )
            )
            meta['issue_filter_applied'] = True
            meta['issue_range'] = (issue_start_str, issue_end_str)
        except ValueError:
            meta['issue_filter_applied'] = False

    # Created date range
    created_start_str = _get_param_value(params, 'created_start')
    created_end_str = _get_param_value(params, 'created_end')
    if created_start_str and created_end_str:
        try:
            cs = datetime.strptime(created_start_str, '%Y-%m-%d').date()
            ce = datetime.strptime(created_end_str, '%Y-%m-%d').date()
            cs_dt = datetime.combine(cs, datetime.min.time(), tzinfo=timezone.utc)
            ce_dt = datetime.combine(ce, datetime.max.time(), tzinfo=timezone.utc)
            query = query.filter(
                db.and_(
                    Newsletter.generated_date >= cs_dt,
                    Newsletter.generated_date <= ce_dt,
                )
            )
            meta['created_range'] = (created_start_str, created_end_str)
        except ValueError:
            meta['created_range'] = None

    return query, meta


def _resolve_newsletter_filter_targets(filter_params, exclude_ids):
    base_query, filter_meta = _apply_admin_newsletter_filters(Newsletter.query, filter_params)
    matched_rows = base_query.with_entities(Newsletter.id).all()
    matched_ids = [row.id for row in matched_rows]
    exclude_set = set(_normalize_int_list(exclude_ids))
    excluded_in_matched = [nid for nid in matched_ids if nid in exclude_set]
    exclude_missing = [nid for nid in exclude_set if nid not in matched_ids]
    selected_ids = [nid for nid in matched_ids if nid not in exclude_set]

    meta = {
        'mode': 'filters',
        'total_matched': len(matched_ids),
        'total_selected': len(selected_ids),
        'total_excluded': len(excluded_in_matched),
        'excluded_ids': excluded_in_matched,
        'exclude_missing': exclude_missing,
        'filter_info': filter_meta,
    }
    return selected_ids, matched_ids, meta
@api_bp.route('/admin/newsletters', methods=['GET'])
@require_api_key
def admin_list_newsletters():
    try:
        filtered_query, filter_meta = _apply_admin_newsletter_filters(Newsletter.query, request.args)
        page = request.args.get('page', type=int) or 1
        if page < 1:
            page = 1

        page_size_param = request.args.get('page_size', type=int)
        page_size = None
        if page_size_param is not None:
            page_size = page_size_param
            if page_size < 1:
                page_size = 1
            if page_size > 200:
                page_size = 200

        total = filtered_query.order_by(None).count()

        total_pages = 1
        if page_size is not None:
            total_pages = max(1, math.ceil(total / page_size))
            if page > total_pages:
                page = total_pages
        else:
            page = 1

        # Ordering: issue date first if provided, otherwise created desc
        if filter_meta.get('issue_filter_applied'):
            ordered_query = filtered_query.order_by(Newsletter.issue_date.desc(), Newsletter.generated_date.desc())
        else:
            ordered_query = filtered_query.order_by(Newsletter.generated_date.desc())

        if page_size is not None:
            offset = (page - 1) * page_size
            if offset < 0:
                offset = 0
            ordered_query = ordered_query.offset(offset).limit(page_size)

        rows = ordered_query.all()
        effective_page_size = page_size if page_size is not None else total
        return jsonify({
            'items': [r.to_dict() for r in rows],
            'page': page,
            'page_size': effective_page_size,
            'total': total,
            'total_pages': total_pages,
            'meta': {
                'filters': filter_meta,
            }
        })
    except Exception as e:
        logger.exception('admin_list_newsletters failed')
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/newsletters/<int:nid>', methods=['GET'])
@require_api_key
def admin_get_newsletter(nid: int):
    try:
        n = Newsletter.query.get_or_404(nid)
        payload = n.to_dict()
        try:
            payload['enriched_content'] = _load_newsletter_json(n)
        except Exception:
            payload['enriched_content'] = None
        return jsonify(payload)
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/newsletters/<int:nid>', methods=['PUT'])
@require_api_key
def admin_update_newsletter(nid: int):
    try:
        n = Newsletter.query.get_or_404(nid)
        data = request.get_json() or {}
        # Update title
        title_updated = False
        if 'title' in data:
            new_title = (data.get('title') or '').strip()
            if new_title:
                title_updated = new_title != n.title
                n.title = new_title
        # Update content
        if 'content_json' in data:
            payload = data.get('content_json')
            try:
                if isinstance(payload, str):
                    obj = json.loads(payload)
                else:
                    obj = payload
            except Exception:
                return jsonify({'error': 'content_json must be valid JSON'}), 400
            content_str = json.dumps(obj, ensure_ascii=False)
            n.content = content_str
            n.structured_content = content_str
        elif title_updated:
            # Sync title into existing JSON when only title changes
            raw = n.structured_content or n.content
            try:
                obj = json.loads(raw) if isinstance(raw, str) else raw
            except Exception:
                obj = None
            if isinstance(obj, dict):
                obj['title'] = n.title
                content_str = json.dumps(obj, ensure_ascii=False)
                n.content = content_str
                n.structured_content = content_str
        # Update week/issue dates (optional)
        def _parse_date(s):
            try:
                return datetime.strptime(s, '%Y-%m-%d').date()
            except Exception:
                return None
        if 'issue_date' in data and data.get('issue_date'):
            d = _parse_date(str(data.get('issue_date')))
            if d:
                n.issue_date = d
        if 'week_start_date' in data and data.get('week_start_date'):
            d = _parse_date(str(data.get('week_start_date')))
            if d:
                n.week_start_date = d
        if 'week_end_date' in data and data.get('week_end_date'):
            d = _parse_date(str(data.get('week_end_date')))
            if d:
                n.week_end_date = d
        # Publish/unpublish toggle
        auto_send_trigger = False
        if 'published' in data:
            want_pub = bool(data.get('published'))
            # Detect transition from not published -> published
            auto_send_trigger = (want_pub is True and not n.published)
            n.published = want_pub
            if want_pub:
                n.published_date = datetime.now(timezone.utc)
            else:
                n.published_date = None
        n.updated_at = datetime.now(timezone.utc)
        db.session.commit()

        # Optional: auto-send on approval
        _maybe_auto_send_on_publish(n, auto_send_trigger)

        return jsonify({'message': 'updated', 'newsletter': n.to_dict()})
    except Exception as e:
        logger.exception('admin_update_newsletter failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@api_bp.route('/admin/newsletters/bulk-publish', methods=['POST'])
@require_api_key
def admin_bulk_publish_newsletters():
    """Bulk publish or unpublish newsletters.
    
    Body:
      - publish: Boolean, whether to publish (true) or unpublish (false)
      - ids: Array of newsletter IDs (if not using filter_params)
      - filter_params: Object with filter criteria (alternative to ids)
      - post_to_reddit: Boolean, if true and publishing, also post to Reddit
    """
    try:
        data = request.get_json() or {}
        publish_flag = bool(data.get('publish'))
        post_to_reddit = bool(data.get('post_to_reddit', False))
        filter_params = data.get('filter_params') or data.get('filters')

        meta: dict[str, Any] | None = None
        missing: list[int] = []
        unchanged = 0

        if filter_params:
            if not isinstance(filter_params, dict):
                return jsonify({'error': 'filter_params must be an object'}), 400
            expected_total_raw = data.get('expected_total')
            try:
                expected_total = int(expected_total_raw)
            except (TypeError, ValueError):
                expected_total = None
            if expected_total is None or expected_total < 0:
                return jsonify({'error': 'expected_total is required when using filter_params', 'field': 'expected_total'}), 400

            selected_ids, matched_ids, filter_meta = _resolve_newsletter_filter_targets(filter_params, data.get('exclude_ids'))
            if len(matched_ids) != expected_total:
                return jsonify({
                    'error': 'expected_total_mismatch',
                    'expected_total': expected_total,
                    'actual_total': len(matched_ids),
                }), 409

            target_ids = selected_ids
            meta = dict(filter_meta)
            meta['expected_total'] = expected_total
            meta['total_requested'] = len(matched_ids)
        else:
            normalized_ids = _normalize_int_list(data.get('ids'))
            if not normalized_ids:
                return jsonify({'error': 'ids array required'}), 400
            target_ids = normalized_ids
            meta = {
                'mode': 'ids',
                'total_requested': len(normalized_ids),
            }

        if not target_ids:
            meta.setdefault('total_selected', 0)
            meta.setdefault('excluded_ids', [])
            return jsonify({
                'updated': 0,
                'unchanged': 0,
                'missing': [],
                'publish': publish_flag,
                'total_requested': meta.get('total_requested', 0),
                'meta': meta,
            })

        rows = Newsletter.query.filter(Newsletter.id.in_(target_ids)).all()
        found_ids = {row.id for row in rows}
        missing = [i for i in target_ids if i not in found_ids]
        meta.setdefault('missing_ids', missing)
        meta.setdefault('total_selected', len(target_ids) - len(missing))

        now = datetime.now(timezone.utc)
        updated = 0
        auto_send_targets = []
        for row in rows:
            was_published = row.published
            if publish_flag:
                if not was_published:
                    row.published = True
                    row.published_date = now
                    updated += 1
                    auto_send_targets.append(row)
                else:
                    unchanged += 1
            else:
                if was_published:
                    row.published = False
                    row.published_date = None
                    updated += 1
                else:
                    unchanged += 1
        db.session.commit()

        logger.info(
            'Admin bulk publish user=%s publish=%s updated=%s unchanged=%s selection=%s meta=%s',
            getattr(g, 'user_email', None),
            publish_flag,
            updated,
            unchanged,
            target_ids,
            meta,
        )

        if publish_flag and auto_send_targets:
            for target in auto_send_targets:
                _maybe_auto_send_on_publish(target, auto_send_trigger=True)

        # Post to Reddit if requested
        reddit_results = []
        if publish_flag and post_to_reddit and auto_send_targets:
            reddit_results = _maybe_post_to_reddit_on_publish(auto_send_targets)

        response_data = {
            'updated': updated,
            'missing': missing,
            'publish': publish_flag,
            'unchanged': unchanged,
            'total_requested': meta.get('total_requested', len(target_ids)),
            'meta': meta,
        }
        
        if post_to_reddit:
            response_data['reddit'] = {
                'requested': post_to_reddit,
                'results': reddit_results,
                'posted_count': sum(1 for r in reddit_results if r.get('success_count', 0) > 0)
            }

        return jsonify(response_data)
    except Exception as e:
        logger.exception('admin_bulk_publish_newsletters failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to update newsletter status. Please try again later.')), 500


def _maybe_post_to_reddit_on_publish(newsletters: list) -> list:
    """Attempt to post newsletters to Reddit after publishing.
    
    Args:
        newsletters: List of Newsletter objects that were just published
        
    Returns:
        List of result dicts per newsletter
    """
    results = []
    
    try:
        from src.services.reddit_service import (
            RedditService, RedditServiceError, post_newsletter_to_reddit
        )
        from src.utils.newsletter_markdown import (
            convert_newsletter_to_markdown,
            convert_newsletter_to_compact_markdown,
            generate_post_title
        )
        
        service = RedditService.get_instance()
        if not service.is_configured():
            logger.warning('Reddit not configured, skipping auto-post')
            return [{'newsletter_id': n.id, 'skipped': True, 'reason': 'Reddit not configured'} for n in newsletters]
        
        for newsletter in newsletters:
            newsletter_result = {
                'newsletter_id': newsletter.id,
                'team_name': newsletter.team.name if newsletter.team else None,
                'subreddit_posts': [],
                'success_count': 0,
                'failed_count': 0
            }
            
            # Get active subreddits for this team
            subreddits = TeamSubreddit.query.filter_by(
                team_id=newsletter.team_id,
                is_active=True
            ).all()
            
            if not subreddits:
                newsletter_result['skipped'] = True
                newsletter_result['reason'] = 'No active subreddits configured'
                results.append(newsletter_result)
                continue
            
            # Get newsletter data
            newsletter_data = newsletter.to_dict()
            team_name = newsletter.team.name if newsletter.team else 'Unknown Team'
            title = generate_post_title(newsletter_data, team_name)
            
            web_url = None
            if newsletter.public_slug:
                web_url = f"https://theacademywatch.com/newsletters/{newsletter.public_slug}"
            
            for sub in subreddits:
                try:
                    # Generate markdown
                    if sub.post_format == 'compact':
                        markdown = convert_newsletter_to_compact_markdown(newsletter_data)
                    else:
                        markdown = convert_newsletter_to_markdown(
                            newsletter_data,
                            include_expanded_stats=True,
                            include_links=True,
                            web_url=web_url
                        )
                    
                    result = post_newsletter_to_reddit(
                        newsletter_id=newsletter.id,
                        team_subreddit_id=sub.id,
                        title=title,
                        markdown_content=markdown,
                        post_format=sub.post_format
                    )
                    
                    if result.get('status') == 'success':
                        newsletter_result['success_count'] += 1
                    elif result.get('status') == 'failed':
                        newsletter_result['failed_count'] += 1
                    
                    newsletter_result['subreddit_posts'].append({
                        'subreddit': sub.subreddit_name,
                        **result
                    })
                    
                except Exception as e:
                    newsletter_result['failed_count'] += 1
                    newsletter_result['subreddit_posts'].append({
                        'subreddit': sub.subreddit_name,
                        'status': 'failed',
                        'error': str(e)
                    })
            
            results.append(newsletter_result)
            
            logger.info(
                'Auto-posted newsletter %s to Reddit: success=%s failed=%s',
                newsletter.id,
                newsletter_result['success_count'],
                newsletter_result['failed_count']
            )
        
    except Exception as e:
        logger.exception('_maybe_post_to_reddit_on_publish failed')
        return [{'newsletter_id': n.id, 'error': str(e)} for n in newsletters]
    
    return results

# --- Simple run-history using AdminSetting key 'run_history' ---

def _get_run_history_list() -> list:
    row = AdminSetting.query.filter_by(key='run_history').first()
    if not row or not row.value_json:
        return []
    try:
        return json.loads(row.value_json) or []
    except Exception:
        return []

def _save_run_history_list(items: list):
    row = AdminSetting.query.filter_by(key='run_history').first()
    if not row:
        row = AdminSetting(key='run_history', value_json=json.dumps(items))
        db.session.add(row)
    else:
        row.value_json = json.dumps(items)
    db.session.commit()

def _append_run_history(event: dict):
    try:
        event = dict(event or {})
        event['ts'] = datetime.now(timezone.utc).isoformat()
        items = _get_run_history_list()
        items.insert(0, event)
        _save_run_history_list(items[:200])
    except Exception:
        db.session.rollback()
        logger.exception('append_run_history failed')


def _maybe_auto_send_on_publish(n: Newsletter, auto_send_trigger: bool):
    """Attempt to auto-send a newsletter after it is published."""
    if not auto_send_trigger:
        return None
    try:
        if os.getenv('NEWSLETTER_AUTO_SEND_ON_APPROVAL', '1').lower() not in ('1', 'true', 'yes'):
            return None
        if n.email_sent:
            return None

        out = _deliver_newsletter_via_webhook(n)
        logger.info(
            "Auto-send newsletter %s to team %s - status=%s", n.id, n.team_id, out.get('status')
        )

        if out.get('status') == 'ok':
            from datetime import datetime as _dt, timezone as _tz

            subs = UserSubscription.query.filter_by(team_id=n.team_id, active=True).all()
            valid_subs = [s for s in subs if (s.email or '').strip() and not s.email_bounced]
            used_count = len(valid_subs)
            n.email_sent = True
            n.email_sent_date = _dt.now(_tz.utc)
            n.subscriber_count = used_count

            try:
                ts = n.email_sent_date
                for s in valid_subs:
                    s.last_email_sent = ts
            except Exception:
                pass

            db.session.commit()

        try:
            _append_run_history({
                'kind': 'newsletter-auto-send',
                'newsletter_id': n.id,
                'team_id': n.team_id,
                'status': out.get('status'),
                'http_status': out.get('http_status'),
                'recipient_count': out.get('recipient_count'),
            })
        except Exception:
            pass

        return out
    except Exception:
        logger.exception('auto-send on approval failed')
        try:
            db.session.rollback()
        except Exception:
            pass
        return None


@api_bp.route('/admin/newsletters/bulk', methods=['DELETE'])
@require_api_key
def admin_bulk_delete_newsletters():
    try:
        data = request.get_json() or {}
        filter_params = data.get('filter_params') or data.get('filters')

        meta: dict[str, Any] | None = None
        missing: list[int] = []

        if filter_params:
            if not isinstance(filter_params, dict):
                return jsonify({'error': 'filter_params must be an object'}), 400
            expected_total_raw = data.get('expected_total')
            try:
                expected_total = int(expected_total_raw)
            except (TypeError, ValueError):
                expected_total = None
            if expected_total is None or expected_total < 0:
                return jsonify({'error': 'expected_total is required when using filter_params', 'field': 'expected_total'}), 400

            selected_ids, matched_ids, filter_meta = _resolve_newsletter_filter_targets(filter_params, data.get('exclude_ids'))
            if len(matched_ids) != expected_total:
                return jsonify({
                    'error': 'expected_total_mismatch',
                    'expected_total': expected_total,
                    'actual_total': len(matched_ids),
                }), 409

            target_ids = selected_ids
            meta = dict(filter_meta)
            meta['expected_total'] = expected_total
            meta['total_requested'] = len(matched_ids)
        else:
            normalized_ids = _normalize_int_list(data.get('ids'))
            if not normalized_ids:
                return jsonify({'error': 'ids array required'}), 400
            target_ids = normalized_ids
            meta = {
                'mode': 'ids',
                'total_requested': len(normalized_ids),
            }

        if not target_ids:
            meta.setdefault('total_selected', 0)
            meta.setdefault('excluded_ids', [])
            return jsonify({
                'deleted': 0,
                'missing': [],
                'meta': meta,
            })

        existing_rows = Newsletter.query.filter(Newsletter.id.in_(target_ids)).with_entities(Newsletter.id).all()
        existing_ids = [row.id for row in existing_rows]
        missing = [i for i in target_ids if i not in existing_ids]
        meta.setdefault('missing_ids', missing)
        meta.setdefault('total_selected', len(target_ids) - len(missing))

        deleted_count = 0
        if existing_ids:
            NewsletterComment.query.filter(NewsletterComment.newsletter_id.in_(existing_ids)).delete(synchronize_session=False)
            NewsletterDigestQueue.query.filter(NewsletterDigestQueue.newsletter_id.in_(existing_ids)).delete(synchronize_session=False)
            deleted_count = Newsletter.query.filter(Newsletter.id.in_(existing_ids)).delete(synchronize_session=False)
            db.session.commit()
        else:
            db.session.commit()

        logger.info(
            'Admin bulk delete user=%s deleted=%s selection=%s meta=%s',
            getattr(g, 'user_email', None),
            deleted_count,
            target_ids,
            meta,
        )

        return jsonify({
            'deleted': deleted_count,
            'missing': missing,
            'meta': meta,
        })
    except Exception as e:
        logger.exception('admin_bulk_delete_newsletters failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to delete newsletters. Please try again later.')), 500


@api_bp.route('/admin/newsletters/send-digests', methods=['POST'])
@require_api_key
def admin_send_digest_emails():
    """Trigger sending of weekly digest emails to users who prefer digest delivery.
    
    Body options:
      - week_key: Optional week key to process (e.g., '2025-W48'). Defaults to current week.
    """
    try:
        from src.services.newsletter_deadline_service import send_digest_emails, get_current_week_key
        
        data = request.get_json() or {}
        week_key = data.get('week_key') or get_current_week_key()
        
        result = send_digest_emails(week_key)
        
        logger.info(
            'Admin triggered digest send user=%s week=%s result=%s',
            getattr(g, 'user_email', None),
            week_key,
            result,
        )
        
        return jsonify({
            'week_key': week_key,
            **result
        })
    except Exception as e:
        logger.exception('admin_send_digest_emails failed')
        return jsonify(_safe_error_payload(e, 'Failed to send digest emails. Please try again later.')), 500


@api_bp.route('/admin/newsletters/digest-queue', methods=['GET'])
@require_api_key
def admin_get_digest_queue():
    """Get the current digest queue status."""
    try:
        from src.services.newsletter_deadline_service import get_current_week_key
        
        week_key = request.args.get('week_key') or get_current_week_key()
        
        # Get queue stats
        from sqlalchemy import func
        
        queue_stats = db.session.query(
            NewsletterDigestQueue.sent,
            func.count(NewsletterDigestQueue.id).label('count'),
            func.count(func.distinct(NewsletterDigestQueue.user_id)).label('unique_users')
        ).filter(
            NewsletterDigestQueue.week_key == week_key
        ).group_by(NewsletterDigestQueue.sent).all()
        
        pending_count = 0
        pending_users = 0
        sent_count = 0
        sent_users = 0
        
        for row in queue_stats:
            if row.sent:
                sent_count = row.count
                sent_users = row.unique_users
            else:
                pending_count = row.count
                pending_users = row.unique_users
        
        return jsonify({
            'week_key': week_key,
            'pending': {
                'items': pending_count,
                'users': pending_users
            },
            'sent': {
                'items': sent_count,
                'users': sent_users
            },
            'total': pending_count + sent_count
        })
    except Exception as e:
        logger.exception('admin_get_digest_queue failed')
        return jsonify(_safe_error_payload(e, 'Failed to get digest queue. Please try again later.')), 500


# --- Admin: Reddit Integration Endpoints ---

@api_bp.route('/admin/team-subreddits', methods=['GET'])
@require_api_key
def admin_list_team_subreddits():
    """List all team-subreddit mappings.
    
    Query params:
      - team_id: Filter by specific team ID
      - active_only: If 'true', only return active subreddits
    """
    try:
        team_id = request.args.get('team_id', type=int)
        active_only = request.args.get('active_only', '').lower() in ('true', '1', 'yes')
        
        query = TeamSubreddit.query
        if team_id:
            query = query.filter_by(team_id=team_id)
        if active_only:
            query = query.filter_by(is_active=True)
        
        query = query.order_by(TeamSubreddit.team_id, TeamSubreddit.subreddit_name)
        subreddits = query.all()
        
        return jsonify({
            'subreddits': [s.to_dict() for s in subreddits],
            'count': len(subreddits)
        })
    except Exception as e:
        logger.exception('admin_list_team_subreddits failed')
        return jsonify(_safe_error_payload(e, 'Failed to list subreddits')), 500


@api_bp.route('/admin/team-subreddits', methods=['POST'])
@require_api_key
def admin_add_team_subreddit():
    """Add a subreddit mapping for a team.
    
    Body:
      - team_id: Required team database ID
      - subreddit_name: Required subreddit name (without r/)
      - post_format: Optional, 'full' or 'compact' (default: 'full')
      - is_active: Optional boolean (default: true)
    """
    try:
        data = request.get_json() or {}
        
        team_id = data.get('team_id')
        subreddit_name = (data.get('subreddit_name') or '').strip().lower()
        
        if not team_id:
            return jsonify({'error': 'team_id is required'}), 400
        if not subreddit_name:
            return jsonify({'error': 'subreddit_name is required'}), 400
        
        # Remove r/ prefix if provided
        if subreddit_name.startswith('r/'):
            subreddit_name = subreddit_name[2:]
        
        # Validate team exists
        team = Team.query.get(team_id)
        if not team:
            return jsonify({'error': f'Team {team_id} not found'}), 404
        
        # Check for duplicate
        existing = TeamSubreddit.query.filter_by(
            team_id=team_id,
            subreddit_name=subreddit_name
        ).first()
        if existing:
            return jsonify({
                'error': f'Subreddit r/{subreddit_name} already configured for this team',
                'existing': existing.to_dict()
            }), 409
        
        post_format = data.get('post_format', 'full')
        if post_format not in ('full', 'compact'):
            post_format = 'full'
        
        is_active = data.get('is_active', True)
        if isinstance(is_active, str):
            is_active = is_active.lower() in ('true', '1', 'yes')
        
        subreddit = TeamSubreddit(
            team_id=team_id,
            subreddit_name=subreddit_name,
            post_format=post_format,
            is_active=bool(is_active)
        )
        db.session.add(subreddit)
        db.session.commit()
        
        logger.info(
            'Admin added team subreddit user=%s team_id=%s subreddit=%s',
            getattr(g, 'user_email', None),
            team_id,
            subreddit_name
        )
        
        return jsonify({
            'subreddit': subreddit.to_dict(),
            'message': f'Added r/{subreddit_name} for {team.name}'
        }), 201
    except Exception as e:
        logger.exception('admin_add_team_subreddit failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to add subreddit')), 500


@api_bp.route('/admin/team-subreddits/<int:subreddit_id>', methods=['PUT'])
@require_api_key
def admin_update_team_subreddit(subreddit_id: int):
    """Update a team subreddit mapping.
    
    Body:
      - post_format: Optional, 'full' or 'compact'
      - is_active: Optional boolean
    """
    try:
        subreddit = TeamSubreddit.query.get(subreddit_id)
        if not subreddit:
            return jsonify({'error': 'Subreddit mapping not found'}), 404
        
        data = request.get_json() or {}
        
        if 'post_format' in data:
            post_format = data['post_format']
            if post_format in ('full', 'compact'):
                subreddit.post_format = post_format
        
        if 'is_active' in data:
            is_active = data['is_active']
            if isinstance(is_active, str):
                is_active = is_active.lower() in ('true', '1', 'yes')
            subreddit.is_active = bool(is_active)
        
        db.session.commit()
        
        logger.info(
            'Admin updated team subreddit user=%s subreddit_id=%s',
            getattr(g, 'user_email', None),
            subreddit_id
        )
        
        return jsonify({
            'subreddit': subreddit.to_dict(),
            'message': 'Subreddit mapping updated'
        })
    except Exception as e:
        logger.exception('admin_update_team_subreddit failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to update subreddit')), 500


@api_bp.route('/admin/team-subreddits/<int:subreddit_id>', methods=['DELETE'])
@require_api_key
def admin_delete_team_subreddit(subreddit_id: int):
    """Delete a team subreddit mapping."""
    try:
        subreddit = TeamSubreddit.query.get(subreddit_id)
        if not subreddit:
            return jsonify({'error': 'Subreddit mapping not found'}), 404
        
        subreddit_name = subreddit.subreddit_name
        team_id = subreddit.team_id
        
        db.session.delete(subreddit)
        db.session.commit()
        
        logger.info(
            'Admin deleted team subreddit user=%s subreddit_id=%s team_id=%s subreddit=%s',
            getattr(g, 'user_email', None),
            subreddit_id,
            team_id,
            subreddit_name
        )
        
        return jsonify({
            'message': f'Deleted r/{subreddit_name} mapping',
            'deleted_id': subreddit_id
        })
    except Exception as e:
        logger.exception('admin_delete_team_subreddit failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to delete subreddit mapping')), 500


@api_bp.route('/admin/newsletters/<int:newsletter_id>/reddit-posts', methods=['GET'])
@require_api_key
def admin_get_newsletter_reddit_posts(newsletter_id: int):
    """Get all Reddit posts for a specific newsletter."""
    try:
        newsletter = Newsletter.query.get(newsletter_id)
        if not newsletter:
            return jsonify({'error': 'Newsletter not found'}), 404
        
        posts = RedditPost.query.filter_by(newsletter_id=newsletter_id).all()
        
        return jsonify({
            'newsletter_id': newsletter_id,
            'posts': [p.to_dict() for p in posts],
            'count': len(posts)
        })
    except Exception as e:
        logger.exception('admin_get_newsletter_reddit_posts failed')
        return jsonify(_safe_error_payload(e, 'Failed to get Reddit posts')), 500


@api_bp.route('/admin/newsletters/<int:newsletter_id>/post-to-reddit', methods=['POST'])
@require_api_key
def admin_post_newsletter_to_reddit(newsletter_id: int):
    """Post a newsletter to Reddit.
    
    Body:
      - subreddit_id: Optional specific subreddit ID to post to.
                      If not provided, posts to all active subreddits for the team.
    """
    try:
        from src.services.reddit_service import (
            RedditService, RedditServiceError, post_newsletter_to_reddit
        )
        from src.utils.newsletter_markdown import (
            convert_newsletter_to_markdown,
            convert_newsletter_to_compact_markdown,
            generate_post_title
        )
        
        newsletter = Newsletter.query.get(newsletter_id)
        if not newsletter:
            return jsonify({'error': 'Newsletter not found'}), 404
        
        if not newsletter.published:
            return jsonify({'error': 'Newsletter must be published before posting to Reddit'}), 400
        
        # Check if Reddit is configured
        service = RedditService.get_instance()
        if not service.is_configured():
            return jsonify({
                'error': 'Reddit credentials not configured',
                'message': 'Please set REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USERNAME, and REDDIT_PASSWORD environment variables'
            }), 503
        
        data = request.get_json() or {}
        specific_subreddit_id = data.get('subreddit_id')
        
        # Get target subreddits
        if specific_subreddit_id:
            subreddits = TeamSubreddit.query.filter_by(
                id=specific_subreddit_id,
                team_id=newsletter.team_id,
                is_active=True
            ).all()
            if not subreddits:
                return jsonify({'error': 'Subreddit not found or not active'}), 404
        else:
            subreddits = TeamSubreddit.query.filter_by(
                team_id=newsletter.team_id,
                is_active=True
            ).all()
        
        if not subreddits:
            return jsonify({
                'error': 'No subreddits configured for this team',
                'message': 'Please configure subreddit(s) for this team first'
            }), 400
        
        # Get newsletter data for markdown conversion
        newsletter_data = newsletter.to_dict()
        team_name = newsletter.team.name if newsletter.team else 'Unknown Team'
        
        # Generate the post title
        title = generate_post_title(newsletter_data, team_name)
        
        # Get web URL for linking back
        web_url = None
        if newsletter.public_slug:
            web_url = f"https://theacademywatch.com/newsletters/{newsletter.public_slug}"
        
        results = []
        for sub in subreddits:
            try:
                # Generate markdown based on format preference
                if sub.post_format == 'compact':
                    markdown = convert_newsletter_to_compact_markdown(newsletter_data)
                else:
                    markdown = convert_newsletter_to_markdown(
                        newsletter_data,
                        include_expanded_stats=True,
                        include_links=True,
                        web_url=web_url
                    )
                
                result = post_newsletter_to_reddit(
                    newsletter_id=newsletter_id,
                    team_subreddit_id=sub.id,
                    title=title,
                    markdown_content=markdown,
                    post_format=sub.post_format
                )
                results.append({
                    'subreddit': sub.subreddit_name,
                    **result
                })
            except RedditServiceError as e:
                results.append({
                    'subreddit': sub.subreddit_name,
                    'status': 'failed',
                    'error': str(e)
                })
        
        success_count = sum(1 for r in results if r.get('status') == 'success')
        already_posted = sum(1 for r in results if r.get('status') == 'already_posted')
        failed_count = sum(1 for r in results if r.get('status') == 'failed')
        
        logger.info(
            'Admin posted newsletter to Reddit user=%s newsletter_id=%s success=%s already=%s failed=%s',
            getattr(g, 'user_email', None),
            newsletter_id,
            success_count,
            already_posted,
            failed_count
        )
        
        return jsonify({
            'newsletter_id': newsletter_id,
            'results': results,
            'summary': {
                'success': success_count,
                'already_posted': already_posted,
                'failed': failed_count,
                'total': len(results)
            }
        })
    except Exception as e:
        logger.exception('admin_post_newsletter_to_reddit failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to post to Reddit')), 500


@api_bp.route('/admin/reddit/status', methods=['GET'])
@require_api_key
def admin_reddit_status():
    """Check Reddit integration status — disabled."""
    return jsonify({
        'configured': False,
        'authenticated': False,
        'message': 'Reddit integration is disabled'
    })


# Newsletter YouTube Links endpoints
@api_bp.route('/admin/newsletters/<int:newsletter_id>/youtube-links', methods=['GET'])
@require_api_key
def admin_get_newsletter_youtube_links(newsletter_id: int):
    """Get all YouTube links for a specific newsletter."""
    try:
        newsletter = Newsletter.query.get_or_404(newsletter_id)
        links = NewsletterPlayerYoutubeLink.query.filter_by(newsletter_id=newsletter_id).order_by(NewsletterPlayerYoutubeLink.player_name).all()
        return jsonify([link.to_dict() for link in links])
    except Exception as e:
        logger.exception('admin_get_newsletter_youtube_links failed')
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/newsletters/<int:newsletter_id>/youtube-links', methods=['POST'])
@require_api_key
def admin_create_newsletter_youtube_link(newsletter_id: int):
    """Add a YouTube link for a player in this newsletter."""
    try:
        newsletter = Newsletter.query.get_or_404(newsletter_id)
        data = request.get_json() or {}
        
        player_id = data.get('player_id')
        player_name = (data.get('player_name') or '').strip()
        youtube_link = (data.get('youtube_link') or '').strip()
        
        if not player_name:
            return jsonify({'error': 'player_name is required'}), 400
        if not youtube_link:
            return jsonify({'error': 'youtube_link is required'}), 400
        if not player_id:
            return jsonify({'error': 'player_id is required'}), 400
        
        # Check for duplicate entries
        existing = NewsletterPlayerYoutubeLink.query.filter_by(
            newsletter_id=newsletter_id,
            player_id=player_id
        ).first()
        
        if existing:
            return jsonify({'error': 'YouTube link already exists for this player in this newsletter'}), 409
        
        link = NewsletterPlayerYoutubeLink(
            newsletter_id=newsletter_id,
            player_id=player_id,
            player_name=player_name,
            youtube_link=youtube_link
        )
        
        db.session.add(link)
        db.session.commit()
        
        return jsonify({'message': 'created', 'link': link.to_dict()}), 201
    except Exception as e:
        logger.exception('admin_create_newsletter_youtube_link failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/newsletters/<int:newsletter_id>/youtube-links/<int:link_id>', methods=['PUT'])
@require_api_key
def admin_update_newsletter_youtube_link(newsletter_id: int, link_id: int):
    """Update a YouTube link."""
    try:
        link = NewsletterPlayerYoutubeLink.query.filter_by(id=link_id, newsletter_id=newsletter_id).first_or_404()
        data = request.get_json() or {}
        
        if 'player_name' in data:
            player_name = (data.get('player_name') or '').strip()
            if player_name:
                link.player_name = player_name
        
        if 'youtube_link' in data:
            youtube_link = (data.get('youtube_link') or '').strip()
            if youtube_link:
                link.youtube_link = youtube_link
        
        if 'player_id' in data:
            link.player_id = data.get('player_id')
        
        link.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        
        return jsonify({'message': 'updated', 'link': link.to_dict()})
    except Exception as e:
        logger.exception('admin_update_newsletter_youtube_link failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/newsletters/<int:newsletter_id>/youtube-links/<int:link_id>', methods=['DELETE'])
@require_api_key
def admin_delete_newsletter_youtube_link(newsletter_id: int, link_id: int):
    """Delete a YouTube link."""
    try:
        link = NewsletterPlayerYoutubeLink.query.filter_by(id=link_id, newsletter_id=newsletter_id).first_or_404()
        db.session.delete(link)
        db.session.commit()
        
        return jsonify({'message': 'deleted'})
    except Exception as e:
        logger.exception('admin_delete_newsletter_youtube_link failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@api_bp.route('/newsletters/pending-games/<int:team_id>', methods=['GET'])
@require_api_key
def admin_check_pending_games(team_id: int):
    """Check if any active loanees for a team have unplayed games WITHIN the target week."""
    try:
        # Get target date (default to today)
        target_date_str = request.args.get('target_date')
        if target_date_str:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        else:
            target_date = datetime.now(timezone.utc).date()

        # Calculate week range (Monday to Sunday) for the newsletter
        week_start = target_date - timedelta(days=target_date.weekday())
        week_end = week_start + timedelta(days=6)
        
        logger.info(f"Checking pending games for team {team_id}, week {week_start} to {week_end}")

        # 1. Find the parent team
        parent_team = Team.query.get(team_id)
        if not parent_team:
            return jsonify({'error': 'Team not found'}), 404
            
        # 2. Find active tracked players for this team
        active_loans = parent_team.unique_active_players()
        
        if not active_loans:
            return jsonify({'pending': False, 'games': [], 'message': 'No active loans found'})
            
        # 3. Group players by loan team API ID
        loan_team_map = {} # api_id -> list of TrackedPlayer objects
        for loan in active_loans:
            if loan.borrowing_team and loan.borrowing_team.team_id:
                api_id = loan.borrowing_team.team_id
                if api_id not in loan_team_map:
                    loan_team_map[api_id] = []
                loan_team_map[api_id].append(loan)
        
        if not loan_team_map:
            return jsonify({'pending': False, 'games': [], 'message': 'No loan teams with API IDs found'})

        # 4. Check fixtures for each loan team WITHIN the target week
        detailed_pending_games = []
        
        for loan_api_id, players in loan_team_map.items():
            # Fetch ALL fixtures for this loan team in the ENTIRE week
            season = api_client.current_season_start_year
            fixtures = api_client.get_fixtures_for_team(
                loan_api_id, 
                season, 
                week_start.strftime('%Y-%m-%d'),  # Check the entire week
                week_end.strftime('%Y-%m-%d')
            )
            
            for f in fixtures:
                fixture_date_str = (f.get('fixture') or {}).get('date')
                status = (f.get('fixture') or {}).get('status', {}).get('short')
                
                # Parse the fixture date to check if it's within the week
                try:
                    if fixture_date_str:
                        fixture_date = datetime.fromisoformat(fixture_date_str.replace('Z', '+00:00')).date()
                    else:
                        continue
                except:
                    continue
                
                # Only include games WITHIN the target week that haven't been played
                # NS = Not Started, TBD = Time To Be Defined
                if week_start <= fixture_date <= week_end and status in ['NS', 'TBD']:
                    opponent = (f.get('teams') or {}).get('away', {}).get('name') \
                                if (f.get('teams') or {}).get('home', {}).get('id') == loan_api_id \
                                else (f.get('teams') or {}).get('home', {}).get('name')
                    league = (f.get('league') or {}).get('name')
                    
                    # Add an entry for EACH player at this club
                    for player in players:
                        detailed_pending_games.append({
                            'player_name': player.player_name,
                            'loan_team': player.loan_team_name,
                            'opponent': opponent,
                            'date': fixture_date_str,
                            'league': league,
                            'status': status,
                            'fixture_id': (f.get('fixture') or {}).get('id')
                        })
                        logger.info(f"Found pending game for {player.player_name} on {fixture_date}: {opponent}")

        # Sort by date
        detailed_pending_games.sort(key=lambda x: x['date'])
        
        logger.info(f"Total pending games found: {len(detailed_pending_games)}")
        
        return jsonify({
            'pending': len(detailed_pending_games) > 0,
            'games': detailed_pending_games
        })

    except Exception as e:
        logger.exception(f"admin_check_pending_games failed for team {team_id}")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred.')), 500


@api_bp.route('/newsletters/readiness', methods=['GET'])
@require_api_key
def admin_check_newsletter_readiness():
    """
    Check newsletter generation readiness for all tracked teams.
    Returns a summary showing which teams have all games completed vs pending games.
    
    Query params:
      - target_date: YYYY-MM-DD (defaults to today)
      - team_ids: comma-separated list of team DB IDs to check (optional, defaults to all tracked teams)
    
    Returns:
    {
        "target_date": "2024-11-25",
        "week_start": "2024-11-25",
        "week_end": "2024-12-01",
        "ready": true/false,  # All teams ready?
        "teams": [
            {
                "team_id": 1,
                "team_name": "Manchester United",
                "ready": true,
                "pending_count": 0,
                "total_loans": 5
            },
            ...
        ],
        "summary": {
            "total_teams": 10,
            "ready_count": 8,
            "pending_count": 2
        }
    }
    """
    try:
        # Get target date
        target_date_str = request.args.get('target_date')
        if target_date_str:
            target_date = datetime.strptime(target_date_str, '%Y-%m-%d').date()
        else:
            target_date = datetime.now(timezone.utc).date()

        # Calculate week range (Monday to Sunday)
        week_start = target_date - timedelta(days=target_date.weekday())
        week_end = week_start + timedelta(days=6)
        
        # Get teams to check
        team_ids_param = request.args.get('team_ids', '')
        if team_ids_param:
            team_ids = [int(tid.strip()) for tid in team_ids_param.split(',') if tid.strip()]
            teams = Team.query.filter(Team.id.in_(team_ids)).all()
        else:
            # Get all tracked teams
            teams = Team.query.filter(Team.is_tracked == True).all()
        
        if not teams:
            return jsonify({
                'target_date': target_date.isoformat(),
                'week_start': week_start.isoformat(),
                'week_end': week_end.isoformat(),
                'ready': True,
                'teams': [],
                'summary': {
                    'total_teams': 0,
                    'ready_count': 0,
                    'pending_count': 0
                }
            })
        
        results = []
        season = api_client.current_season_start_year
        
        for team in teams:
            # Get active tracked players for this team
            active_loans = team.unique_active_players()
            
            if not active_loans:
                results.append({
                    'team_id': team.id,
                    'team_name': team.name,
                    'ready': True,
                    'pending_count': 0,
                    'total_loans': 0,
                    'pending_games': []
                })
                continue
            
            # Group players by loan team API ID
            loan_team_map = {}
            for loan in active_loans:
                if loan.borrowing_team and loan.borrowing_team.team_id:
                    api_id = loan.borrowing_team.team_id
                    if api_id not in loan_team_map:
                        loan_team_map[api_id] = []
                    loan_team_map[api_id].append(loan)
            
            pending_games = []
            
            # Check fixtures for each loan team within the week
            for loan_api_id, players in loan_team_map.items():
                try:
                    fixtures = api_client.get_fixtures_for_team(
                        loan_api_id, 
                        season, 
                        week_start.strftime('%Y-%m-%d'),
                        week_end.strftime('%Y-%m-%d')
                    )
                    
                    for f in fixtures:
                        fixture_date_str = (f.get('fixture') or {}).get('date')
                        status = (f.get('fixture') or {}).get('status', {}).get('short')
                        
                        try:
                            if fixture_date_str:
                                fixture_date = datetime.fromisoformat(fixture_date_str.replace('Z', '+00:00')).date()
                            else:
                                continue
                        except:
                            continue
                        
                        # Only include games within the week that haven't been played
                        if week_start <= fixture_date <= week_end and status in ['NS', 'TBD']:
                            opponent = (f.get('teams') or {}).get('away', {}).get('name') \
                                        if (f.get('teams') or {}).get('home', {}).get('id') == loan_api_id \
                                        else (f.get('teams') or {}).get('home', {}).get('name')
                            
                            for player in players:
                                pending_games.append({
                                    'player_name': player.player_name,
                                    'loan_team': player.loan_team_name,
                                    'opponent': opponent,
                                    'date': fixture_date_str,
                                })
                except Exception as e:
                    logger.warning(f"Failed to check fixtures for loan team {loan_api_id}: {e}")
            
            results.append({
                'team_id': team.id,
                'team_name': team.name,
                'ready': len(pending_games) == 0,
                'pending_count': len(pending_games),
                'total_loans': len(active_loans),
                'pending_games': pending_games[:5]  # Only first 5 for brevity
            })
        
        # Sort: not-ready teams first
        results.sort(key=lambda x: (x['ready'], x['team_name']))
        
        ready_count = sum(1 for r in results if r['ready'])
        pending_count = len(results) - ready_count
        
        return jsonify({
            'target_date': target_date.isoformat(),
            'week_start': week_start.isoformat(),
            'week_end': week_end.isoformat(),
            'ready': pending_count == 0,
            'teams': results,
            'summary': {
                'total_teams': len(results),
                'ready_count': ready_count,
                'pending_count': pending_count
            }
        })

    except Exception as e:
        logger.exception("admin_check_newsletter_readiness failed")
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred.')), 500


# --------------------------------------------------------------------------------
# Newsletter Commentary Endpoints
# --------------------------------------------------------------------------------

def require_commentary_author(f):
    """Decorator to require can_author_commentary permission."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # First check basic API key authentication
        # The user email should be in g.admin_email after require_api_key
        if not hasattr(g, 'admin_email') or not g.admin_email:
            return jsonify({'error': 'Authentication required'}), 401
        
        # Check if user has commentary authorship permission
        user = UserAccount.query.filter_by(email=g.admin_email).first()
        if not user or not user.can_author_commentary:
            return jsonify({'error': 'You do not have permission to author commentary'}), 403
        
        # Store user in g for the handler to use
        g.commentary_author = user
        return f(*args, **kwargs)
    
    return decorated_function


@api_bp.route('/admin/newsletters/<int:newsletter_id>/commentary', methods=['GET'])
@require_api_key
def admin_list_newsletter_commentary(newsletter_id: int):
    """List all commentary for a newsletter."""
    try:
        newsletter = Newsletter.query.get_or_404(newsletter_id)
        commentaries = NewsletterCommentary.query.filter_by(
            newsletter_id=newsletter_id,
            is_active=True
        ).order_by(
            NewsletterCommentary.commentary_type,
            NewsletterCommentary.position
        ).all()
        
        return jsonify({
            'newsletter_id': newsletter_id,
            'commentaries': [c.to_dict() for c in commentaries]
        })
    except Exception as e:
        logger.exception('admin_list_newsletter_commentary failed')
        return jsonify(_safe_error_payload(e, 'Failed to list commentary')), 500


@api_bp.route('/admin/newsletters/<int:newsletter_id>/commentary', methods=['POST'])
@require_api_key
@require_commentary_author
def admin_create_newsletter_commentary(newsletter_id: int):
    """Create new commentary for a newsletter."""
    try:
        newsletter = Newsletter.query.get_or_404(newsletter_id)
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        commentary_type = data.get('commentary_type')
        content = data.get('content')
        player_id = data.get('player_id')
        position = data.get('position', 0)
        
        # Validation
        if not commentary_type:
            return jsonify({'error': 'commentary_type is required'}), 400
        if not content:
            return jsonify({'error': 'content is required'}), 400
        if commentary_type not in ['player', 'intro', 'summary']:
            return jsonify({'error': 'commentary_type must be player, intro, or summary'}), 400
        if commentary_type == 'player' and not player_id:
            return jsonify({'error': 'player_id is required for player commentary'}), 400
        
        # Get author from g (set by require_commentary_author)
        author = g.commentary_author
        
        # Create commentary using the factory method (which sanitizes)
        try:
            commentary = NewsletterCommentary.sanitize_and_create(
                newsletter_id=newsletter_id,
                author_id=author.id,
                author_name=author.display_name,
                commentary_type=commentary_type,
                content=content,
                player_id=player_id,
                position=position
            )
        except ValueError as ve:
            return jsonify({'error': str(ve)}), 400
        
        db.session.add(commentary)
        db.session.commit()
        
        return jsonify(commentary.to_dict()), 201
        
    except Exception as e:
        logger.exception('admin_create_newsletter_commentary failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to create commentary')), 500


@api_bp.route('/admin/commentary/<int:commentary_id>', methods=['PUT'])
@require_api_key
@require_commentary_author
def admin_update_commentary(commentary_id: int):
    """Update existing commentary."""
    try:
        commentary = NewsletterCommentary.query.get_or_404(commentary_id)
        author = g.commentary_author
        
        # Check ownership (only author or admin can edit)
        admin_emails = _admin_email_list()
        is_admin = g.admin_email in admin_emails
        if commentary.author_id != author.id and not is_admin:
            return jsonify({'error': 'You can only edit your own commentary'}), 403
        
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Request body is required'}), 400
        
        # Update fields if provided
        if 'content' in data:
            try:
                commentary.content = sanitize_commentary_html(data['content'])
            except ValueError as ve:
                return jsonify({'error': str(ve)}), 400
        
        if 'position' in data:
            commentary.position = int(data['position'])
        
        if 'is_active' in data:
            commentary.is_active = bool(data['is_active'])
        
        commentary.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        
        return jsonify(commentary.to_dict())
        
    except Exception as e:
        logger.exception('admin_update_commentary failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to update commentary')), 500


@api_bp.route('/admin/commentary/<int:commentary_id>', methods=['DELETE'])
@require_api_key
@require_commentary_author
def admin_delete_commentary(commentary_id: int):
    """Delete commentary."""
    try:
        commentary = NewsletterCommentary.query.get_or_404(commentary_id)
        author = g.commentary_author
        
        # Check ownership (only author or admin can delete)
        admin_emails = _admin_email_list()
        is_admin = g.admin_email in admin_emails
        if commentary.author_id != author.id and not is_admin:
            return jsonify({'error': 'You can only delete your own commentary'}), 403
        
        db.session.delete(commentary)
        db.session.commit()
        
        return jsonify({'message': 'deleted'})
        
    except Exception as e:
        logger.exception('admin_delete_commentary failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to delete commentary')), 500


@api_bp.route('/admin/authors', methods=['GET'])
@require_api_key
def admin_list_authors():
    """List all users with commentary authorship permission."""
    try:
        authors = UserAccount.query.filter_by(can_author_commentary=True).all()
        
        # Include commentary count for each author
        result = []
        for author in authors:
            author_dict = author.to_dict()
            commentary_count = NewsletterCommentary.query.filter_by(author_id=author.id).count()
            author_dict['commentary_count'] = commentary_count
            result.append(author_dict)
        
        return jsonify({'authors': result})
        
    except Exception as e:
        logger.exception('admin_list_authors failed')
        return jsonify(_safe_error_payload(e, 'Failed to list authors')), 500


@api_bp.route('/admin/users/<int:user_id>/author-permission', methods=['PUT'])
@require_api_key
def admin_update_author_permission(user_id: int):
    """Grant or revoke commentary authorship permission. Admin only."""
    try:
        # Check if requester is admin
        admin_emails = _admin_email_list()
        if not hasattr(g, 'admin_email') or g.admin_email not in admin_emails:
            return jsonify({'error': 'Only admins can manage author permissions'}), 403
        
        user = UserAccount.query.get_or_404(user_id)
        data = request.get_json()
        
        if not data or 'can_author_commentary' not in data:
            return jsonify({'error': 'can_author_commentary field is required'}), 400
        
        user.can_author_commentary = bool(data['can_author_commentary'])
        user.updated_at = datetime.now(timezone.utc)
        db.session.commit()
        
        return jsonify({
            'user_id': user.id,
            'email': user.email,
            'display_name': user.display_name,
            'can_author_commentary': user.can_author_commentary
        })
        
    except Exception as e:
        logger.exception('admin_update_author_permission failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to update author permission')), 500


# Unified Player Management endpoints
@api_bp.route('/admin/players', methods=['GET'])
@require_api_key
def admin_list_players():
    """
    List all players with comprehensive information, team filtering, and pagination.
    Query params:
    - team_id: filter by primary or loan team
    - search: search player names
    - has_sofascore: filter by sofascore ID presence ('true', 'false', or omit for all)
    - page: page number (default 1)
    - page_size: items per page (default 50, max 200)
    """
    try:
        page = request.args.get('page', type=int, default=1)
        page_size = request.args.get('page_size', type=int, default=50)
        if page < 1:
            page = 1
        if page_size < 1 or page_size > 200:
            page_size = 50
        
        team_id_param = request.args.get('team_id', type=int)
        search_query = request.args.get('search', '').strip()
        has_sofascore_param = request.args.get('has_sofascore', '').lower()
        
        # Get all tracked players
        tp_query = TrackedPlayer.query

        # Apply team filter
        if team_id_param:
            tp_query = tp_query.filter(
                or_(
                    TrackedPlayer.team_id == team_id_param,
                    TrackedPlayer.current_club_db_id == team_id_param
                )
            )

        # Apply search filter
        if search_query:
            tp_query = tp_query.filter(TrackedPlayer.player_name.ilike(f'%{search_query}%'))

        # Get all tracked players
        all_tracked = tp_query.all()

        # Group by player_api_id
        player_map = {}
        for tp in all_tracked:
            if tp.player_api_id not in player_map:
                parent_team = Team.query.get(tp.team_id) if tp.team_id else None
                player_map[tp.player_api_id] = {
                    'player_id': tp.player_api_id,
                    'player_name': tp.player_name,
                    'primary_team_name': parent_team.name if parent_team else None,
                    'loan_team_name': tp.current_club_name,
                    'primary_team_id': tp.team_id,
                    'loan_team_id': tp.current_club_db_id,
                    'is_active': tp.is_active,
                    'loan_count': 0,
                    'loan_id': tp.id,
                    'window_key': None,
                    'loan_season': None
                }
            player_map[tp.player_api_id]['loan_count'] += 1
        
        # Get Player records with sofascore IDs
        player_ids = list(player_map.keys())
        player_records = {}
        if player_ids:
            try:
                players = Player.query.filter(Player.player_id.in_(player_ids)).all()
                player_records = {p.player_id: p for p in players}
            except Exception as player_error:
                logger.warning(f'Could not fetch Player records: {player_error}')
                # Continue without player records if table doesn't exist yet
                player_records = {}
        
        # Build comprehensive player list
        players_data = []
        for player_id, player_info in player_map.items():
            player_record = player_records.get(player_id)
            sofascore_id = player_record.sofascore_id if player_record else None
            display_name = ''
            if player_record and player_record.name:
                display_name = player_record.name.strip()
            if not display_name:
                display_name = (player_info.get('player_name') or '').strip()
            if not display_name:
                display_name = f'Player {player_id}'
            
            # Apply sofascore filter
            if has_sofascore_param == 'true' and not sofascore_id:
                continue
            if has_sofascore_param == 'false' and sofascore_id:
                continue
            
            player_data = {
                'player_id': player_info['player_id'],
                'player_name': display_name,
                'primary_team_name': player_info['primary_team_name'],
                'loan_team_name': player_info['loan_team_name'],
                'primary_team_id': player_info['primary_team_id'],
                'loan_team_id': player_info['loan_team_id'],
                'is_active': player_info['is_active'],
                'loan_count': player_info['loan_count'],
                'window_key': player_info.get('window_key'),
                'loan_season': player_info.get('loan_season'),
                'loan_id': player_info['loan_id'],  # Primary loan record ID for team updates
                'sofascore_id': sofascore_id,
                'has_sofascore_id': bool(sofascore_id),
                'photo_url': player_record.photo_url if player_record else None,
                'position': player_record.position if player_record else None,
                'nationality': player_record.nationality if player_record else None,
                'age': player_record.age if player_record else None,
            }
            players_data.append(player_data)
        
        # Sort by name
        players_data.sort(key=lambda x: x['player_name'].lower())
        
        # Paginate
        total = len(players_data)
        total_pages = max(1, math.ceil(total / page_size)) if total > 0 else 1
        start = (page - 1) * page_size
        end = start + page_size
        paginated_data = players_data[start:end]
        
        return jsonify({
            'items': paginated_data,
            'page': page,
            'page_size': page_size,
            'total': total,
            'total_pages': total_pages
        })
    except Exception as e:
        logger.exception('admin_list_players failed')
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/players/<player_id>', methods=['GET'])
@require_api_key
def admin_get_player(player_id):
    """Get detailed player information."""
    try:
        # Convert player_id to int (supports negative IDs for manual players)
        try:
            player_id = int(player_id)
        except ValueError:
            return jsonify({'error': 'Invalid player ID'}), 400
        # Get Player record
        player_record = Player.query.filter_by(player_id=player_id).first()
        
        # Get all tracked player records for this player
        tracked_records = TrackedPlayer.query.filter_by(player_api_id=player_id).order_by(TrackedPlayer.created_at.desc()).all()

        player_data = {
            'player_id': player_id,
            'name': player_record.name if player_record else (tracked_records[0].player_name if tracked_records else f"Player {player_id}"),
            'sofascore_id': player_record.sofascore_id if player_record else None,
            'photo_url': player_record.photo_url if player_record else None,
            'position': player_record.position if player_record else None,
            'nationality': player_record.nationality if player_record else None,
            'age': player_record.age if player_record else None,
            'height': player_record.height if player_record else None,
            'weight': player_record.weight if player_record else None,
            'firstname': player_record.firstname if player_record else None,
            'lastname': player_record.lastname if player_record else None,
            'loans': [tp.to_dict() for tp in tracked_records],
            'supplemental_loans': [],
            'total_loans': len(tracked_records),
            'created_at': player_record.created_at.isoformat() if player_record and player_record.created_at else None,
            'updated_at': player_record.updated_at.isoformat() if player_record and player_record.updated_at else None,
        }
        
        return jsonify(player_data)
    except Exception as e:
        logger.exception('admin_get_player failed')
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/players/<player_id>', methods=['PUT'])
@require_api_key
def admin_update_player(player_id):
    """Update player information including sofascore_id."""
    try:
        # Convert player_id to int (supports negative IDs for manual players)
        try:
            player_id = int(player_id)
        except ValueError:
            return jsonify({'error': 'Invalid player ID'}), 400
        data = request.get_json() or {}
        
        # Get or create Player record
        player_record = Player.query.filter_by(player_id=player_id).first()
        if not player_record:
            player_record = Player(player_id=player_id)
            player_record.created_at = datetime.now(timezone.utc)
            db.session.add(player_record)
        
        # Update fields
        propagated_name = None
        if 'name' in data:
            name = (data.get('name') or '').strip()
            if name:
                player_record.name = name
                propagated_name = name
        
        if 'sofascore_id' in data:
            sofascore_id = data.get('sofascore_id')
            # Check for duplicates
            if sofascore_id:
                existing = Player.query.filter(
                    Player.sofascore_id == sofascore_id,
                    Player.player_id != player_id
                ).first()
                if existing:
                    return jsonify({
                        'error': f'Sofascore ID {sofascore_id} is already assigned to player #{existing.player_id}'
                    }), 409
            player_record.sofascore_id = sofascore_id
        
        if 'position' in data:
            player_record.position = data.get('position')
        
        if 'nationality' in data:
            player_record.nationality = data.get('nationality')
        
        if 'age' in data:
            player_record.age = data.get('age')
        
        if 'height' in data:
            player_record.height = data.get('height')
        
        if 'weight' in data:
            player_record.weight = data.get('weight')
        
        if 'firstname' in data:
            player_record.firstname = data.get('firstname')
        
        if 'lastname' in data:
            player_record.lastname = data.get('lastname')
        
        if 'photo_url' in data:
            player_record.photo_url = data.get('photo_url')
        
        player_record.updated_at = datetime.now(timezone.utc)
        if propagated_name:
            updated_rows = TrackedPlayer.query.filter_by(player_api_id=player_id).update(
                {
                    'player_name': propagated_name,
                    'updated_at': datetime.now(timezone.utc),
                },
                synchronize_session=False,
            )
            if updated_rows:
                logger.info('Propagated name update to %d TrackedPlayer rows for player_api_id=%s', updated_rows, player_id)

        db.session.commit()
        
        return jsonify({'message': 'updated', 'player': player_record.to_dict()})
    except Exception as e:
        logger.exception('admin_update_player failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/players/bulk-update-sofascore', methods=['POST'])
@require_api_key
def admin_bulk_update_sofascore():
    """Bulk update Sofascore IDs for multiple players."""
    try:
        data = request.get_json() or {}
        updates = data.get('updates', [])
        
        if not isinstance(updates, list):
            return jsonify({'error': 'updates must be an array'}), 400
        
        results = {
            'updated': [],
            'failed': [],
            'skipped': []
        }
        
        for update in updates:
            player_id = update.get('player_id')
            sofascore_id = update.get('sofascore_id')
            
            if not player_id:
                results['failed'].append({'error': 'missing player_id', 'update': update})
                continue
            
            try:
                # Get or create player record
                player_record = Player.query.filter_by(player_id=player_id).first()
                if not player_record:
                    player_record = Player(player_id=player_id)
                    player_record.name = update.get('player_name', f'Player {player_id}')
                    player_record.created_at = datetime.now(timezone.utc)
                    db.session.add(player_record)
                
                # Check for duplicate sofascore_id
                if sofascore_id:
                    existing = Player.query.filter(
                        Player.sofascore_id == sofascore_id,
                        Player.player_id != player_id
                    ).first()
                    if existing:
                        results['failed'].append({
                            'player_id': player_id,
                            'error': f'Sofascore ID already assigned to player #{existing.player_id}'
                        })
                        continue
                
                player_record.sofascore_id = sofascore_id
                player_record.updated_at = datetime.now(timezone.utc)
                
                results['updated'].append({
                    'player_id': player_id,
                    'sofascore_id': sofascore_id
                })
            except Exception as e:
                results['failed'].append({
                    'player_id': player_id,
                    'error': str(e)
                })
        
        db.session.commit()
        
        return jsonify({
            'message': 'bulk update completed',
            'results': results
        })
    except Exception as e:
        logger.exception('admin_bulk_update_sofascore failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/players/field-options', methods=['GET'])
@require_api_key
def admin_get_player_field_options():
    """
    Get existing values for player fields (positions, nationalities) for dropdown population.
    This helps normalize data entry by providing existing values.
    """
    try:
        # Get unique positions from Player table
        positions_query = db.session.query(Player.position).filter(
            Player.position.isnot(None),
            Player.position != ''
        ).distinct().all()
        positions = sorted([p[0] for p in positions_query if p[0]])
        
        # Get unique nationalities from Player table
        nationalities_query = db.session.query(Player.nationality).filter(
            Player.nationality.isnot(None),
            Player.nationality != ''
        ).distinct().all()
        nationalities = sorted([n[0] for n in nationalities_query if n[0]])
        
        return jsonify({
            'positions': positions,
            'nationalities': nationalities
        })
    except Exception as e:
        logger.exception('admin_get_player_field_options failed')
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@api_bp.route('/admin/players', methods=['POST'])
@require_api_key
def admin_create_player():
    """
    Create a new manual player with loan association.
    
    This creates both a Player record and a TrackedPlayer record to properly
    track the player's loan status and team associations.
    """
    try:
        data = request.get_json() or {}
        
        # Validate required fields
        name = (data.get('name') or '').strip()
        if not name:
            return jsonify({'error': 'Player name is required'}), 400
        
        window_key = data.get('window_key')
        if not window_key:
            return jsonify({'error': 'Season/window is required'}), 400
        
        # Handle primary team (either from database or custom)
        primary_team_id = data.get('primary_team_id')
        custom_primary_team_name = (data.get('custom_primary_team_name') or '').strip()
        
        if primary_team_id:
            # Using team from database
            primary_team = Team.query.get(primary_team_id)
            if not primary_team:
                return jsonify({'error': f'Primary team ID {primary_team_id} not found'}), 404
            primary_team_name = primary_team.name
            primary_team_api_id = primary_team.team_id
        elif custom_primary_team_name:
            # Using custom team name
            primary_team = None
            primary_team_id = None
            primary_team_name = custom_primary_team_name
            primary_team_api_id = None
        else:
            return jsonify({'error': 'Primary team or custom primary team name is required'}), 400
        
        # Handle loan team (either from database or custom)
        loan_team_id = data.get('loan_team_id')
        custom_loan_team_name = (data.get('custom_loan_team_name') or '').strip()
        
        if loan_team_id:
            # Using team from database
            loan_team = Team.query.get(loan_team_id)
            if not loan_team:
                return jsonify({'error': f'Loan team ID {loan_team_id} not found'}), 404
            loan_team_name = loan_team.name
            loan_team_api_id = loan_team.team_id
        elif custom_loan_team_name:
            # Using custom team name
            loan_team = None
            loan_team_id = None
            loan_team_name = custom_loan_team_name
            loan_team_api_id = None
        else:
            return jsonify({'error': 'Loan team or custom loan team name is required'}), 400
        
        # Generate a unique player_id for manual players (negative IDs to avoid conflicts with API-Football)
        existing_manual_players = Player.query.filter(Player.player_id < 0).order_by(Player.player_id.asc()).all()
        if existing_manual_players:
            new_player_id = existing_manual_players[0].player_id - 1
        else:
            new_player_id = -1
        
        # Create player record
        player_record = Player(player_id=new_player_id)
        player_record.name = name
        player_record.firstname = data.get('firstname')
        player_record.lastname = data.get('lastname')
        player_record.position = data.get('position')
        player_record.nationality = data.get('nationality')
        player_record.age = data.get('age')
        player_record.height = data.get('height')
        player_record.weight = data.get('weight')
        player_record.photo_url = data.get('photo_url')
        player_record.created_at = datetime.now(timezone.utc)
        player_record.updated_at = datetime.now(timezone.utc)
        
        # Handle sofascore_id with duplicate check
        sofascore_id = data.get('sofascore_id')
        if sofascore_id:
            existing = Player.query.filter_by(sofascore_id=sofascore_id).first()
            if existing:
                return jsonify({
                    'error': f'Sofascore ID {sofascore_id} is already assigned to player #{existing.player_id}'
                }), 409
            player_record.sofascore_id = sofascore_id
        
        db.session.add(player_record)
        db.session.flush()  # Get player_id before creating tracked player record

        # Create TrackedPlayer record to track the loan
        tracked_player = TrackedPlayer(
            player_api_id=new_player_id,
            player_name=name,
            team_id=primary_team_id,
            status='on_loan',
            current_club_db_id=loan_team_id,
            current_club_api_id=loan_team_api_id,
            current_club_name=loan_team_name,
            is_active=True,
            data_source='manual',
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        db.session.add(tracked_player)
        db.session.commit()

        return jsonify({
            'message': f'Player "{name}" created successfully with loan from {primary_team_name} to {loan_team_name}',
            'player': player_record.to_dict(),
            'tracked_player': tracked_player.to_dict()
        }), 201
    except Exception as e:
        logger.exception('admin_create_player failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/players/<player_id>', methods=['DELETE'])
@require_api_key
def admin_delete_player(player_id):
    """
    Delete a player from the system.
    This removes the player from tracking and cleans up associated data.
    Useful for removing false positives from API-Football.
    """
    try:
        # Convert player_id to int (supports negative IDs for manual players)
        try:
            player_id = int(player_id)
        except ValueError:
            return jsonify({'error': 'Invalid player ID'}), 400
        # Check for tracked player records
        tracked_records = TrackedPlayer.query.filter_by(player_api_id=player_id).all()
        tracked_count = len(tracked_records)
        
        # Check for YouTube links
        youtube_links = NewsletterPlayerYoutubeLink.query.filter_by(player_id=player_id).all()
        youtube_count = len(youtube_links)
        
        # Get player record if it exists
        player_record = Player.query.filter_by(player_id=player_id).first()
        
        # If no data exists anywhere, player not found
        if not player_record and tracked_count == 0 and youtube_count == 0:
            return jsonify({'error': 'Player not found'}), 404
        
        # Delete all associated data
        # 1. Delete YouTube links
        for link in youtube_links:
            db.session.delete(link)
        
        # 2. Delete tracked player records
        for tp in tracked_records:
            db.session.delete(tp)
        
        # 3. Delete player record if it exists
        if player_record:
            db.session.delete(player_record)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Player deleted successfully',
            'deleted': {
                'tracked_records': tracked_count,
                'youtube_links': youtube_count,
                'player_record': player_record is not None
            }
        })
    except Exception as e:
        logger.exception('admin_delete_player failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/runs/history', methods=['GET', 'POST'])
@require_api_key
def admin_runs_history():
    try:
        if request.method == 'GET':
            return jsonify(_get_run_history_list())
        _append_run_history(request.get_json() or {})
        return jsonify({'message': 'appended'})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/admin/runs/history/clear', methods=['POST'])
@require_api_key
def admin_runs_history_clear():
    try:
        _save_run_history_list([])
        return jsonify({'message': 'cleared'})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500



# --- Admin: Dashboard Stats ---
@api_bp.route('/admin/dashboard-stats', methods=['GET'])
@require_api_key
def admin_dashboard_stats():
    """Get overview stats for the admin dashboard."""
    try:
        # Player stats from TrackedPlayer
        total_players = TrackedPlayer.query.filter_by(is_active=True).count()
        academy_count = TrackedPlayer.query.filter_by(is_active=True, status='academy').count()
        on_loan_count = TrackedPlayer.query.filter_by(is_active=True, status='on_loan').count()
        first_team_count = TrackedPlayer.query.filter_by(is_active=True, status='first_team').count()
        released_count = TrackedPlayer.query.filter_by(is_active=True, status='released').count()

        # Team stats
        tracked_teams = Team.query.filter_by(is_tracked=True).count()

        # Newsletter stats
        total_newsletters = Newsletter.query.count()
        published_newsletters = Newsletter.query.filter_by(published=True).count()
        draft_newsletters = total_newsletters - published_newsletters

        return jsonify({
            'players': {
                'total': total_players,
                'academy': academy_count,
                'on_loan': on_loan_count,
                'first_team': first_team_count,
                'released': released_count,
            },
            'teams': {
                'tracked': tracked_teams,
            },
            'newsletters': {
                'total': total_newsletters,
                'published': published_newsletters,
                'drafts': draft_newsletters,
            },
        })
    except Exception as e:
        logger.exception('admin_dashboard_stats failed')
        return jsonify(_safe_error_payload(e, 'Failed to fetch dashboard stats')), 500


# --- Admin: Subscriber Analytics ---
@api_bp.route('/admin/subscriber-stats', methods=['GET'])
@require_api_key
def admin_subscriber_stats():
    """Get subscriber statistics aggregated by team."""
    request_id = request.headers.get('X-Debug-Request-ID') or uuid4().hex[:12]
    started_at = time.monotonic()
    try:
        search = request.args.get('search', '').strip()
        min_subs = request.args.get('min_subscribers', type=int)
        sort_order = request.args.get('sort', 'desc').lower()
        logger.info(
            'admin_subscriber_stats request request_id=%s search=%s min_subs=%s sort=%s',
            request_id,
            search or '',
            min_subs,
            sort_order,
        )
        
        # Query for teams with their subscriber counts
        from sqlalchemy import func
        
        # Subquery to get the latest season for each team_id
        latest_season_subq = db.session.query(
            Team.team_id,
            func.max(Team.season).label('latest_season')
        ).group_by(Team.team_id).subquery()
        
        # Subquery to aggregate subscriptions by team_id (API team ID) across all seasons
        # This ensures we count all subscriptions for a team regardless of which season's team record they're linked to
        subscription_agg_subq = db.session.query(
            Team.team_id,
            func.count(UserSubscription.id).label('subscriber_count'),
            func.count(db.case((UserSubscription.active == True, 1))).label('active_subscriber_count')
        ).join(
            UserSubscription, Team.id == UserSubscription.team_id
        ).group_by(Team.team_id).subquery()
        
        # Subquery to get latest newsletter date by team_id
        newsletter_agg_subq = db.session.query(
            Team.team_id,
            func.max(Newsletter.published_date).label('latest_newsletter_date')
        ).join(
            Newsletter, Team.id == Newsletter.team_id
        ).group_by(Team.team_id).subquery()
        
        # Main query: get latest season team records and join with aggregated subscription data
        query = db.session.query(
            Team,
            func.coalesce(subscription_agg_subq.c.subscriber_count, 0).label('subscriber_count'),
            func.coalesce(subscription_agg_subq.c.active_subscriber_count, 0).label('active_subscriber_count'),
            newsletter_agg_subq.c.latest_newsletter_date.label('latest_newsletter_date')
        ).join(
            latest_season_subq,
            db.and_(
                Team.team_id == latest_season_subq.c.team_id,
                Team.season == latest_season_subq.c.latest_season
            )
        ).outerjoin(
            subscription_agg_subq, Team.team_id == subscription_agg_subq.c.team_id
        ).outerjoin(
            newsletter_agg_subq, Team.team_id == newsletter_agg_subq.c.team_id
        )
        
        # Apply search filter
        if search:
            query = query.filter(Team.name.ilike(f'%{search}%'))
        
        # Execute query
        results = query.all()
        
        # Filter by minimum subscribers if specified
        if min_subs is not None:
            results = [r for r in results if r.subscriber_count >= min_subs]
        
        # Sort by subscriber count
        if sort_order == 'asc':
            results.sort(key=lambda r: r.subscriber_count)
        else:
            results.sort(key=lambda r: r.subscriber_count, reverse=True)
        
        # Format response
        teams_data = []
        for team, sub_count, active_sub_count, latest_date in results:
            teams_data.append({
                'id': team.id,
                'team_id': team.team_id,
                'name': team.name,
                'logo': team.logo,
                'season': team.season,
                'subscriber_count': sub_count,
                'active_subscriber_count': active_sub_count,
                'newsletters_active': team.newsletters_active,
                'latest_newsletter_date': latest_date.isoformat() if latest_date else None
            })
        
        # Calculate total unique subscribers
        total_subscribers = db.session.query(
            func.count(func.distinct(UserSubscription.email))
        ).filter(UserSubscription.active == True).scalar() or 0

        duration_ms = (time.monotonic() - started_at) * 1000
        logger.info(
            'admin_subscriber_stats success request_id=%s team_count=%d total_subscribers=%d duration_ms=%.1f',
            request_id,
            len(teams_data),
            total_subscribers,
            duration_ms,
        )
        
        payload = {
            'teams': teams_data,
            'total_subscribers': total_subscribers,
            'request_id': request_id,
        }
        response = jsonify(payload)
        response.headers['X-Request-ID'] = request_id
        return response
    except Exception as e:
        duration_ms = (time.monotonic() - started_at) * 1000
        logger.exception('admin_subscriber_stats failed request_id=%s duration_ms=%.1f', request_id, duration_ms)
        payload = _safe_error_payload(e, 'An unexpected error occurred. Please try again later.')
        payload['request_id'] = request_id
        response = jsonify(payload)
        response.headers['X-Request-ID'] = request_id
        return response, 500


@api_bp.route('/admin/teams/<int:team_id>/newsletter-status', methods=['PATCH'])
@require_api_key
def admin_toggle_newsletter_status(team_id: int):
    """Toggle the newsletters_active status for a team."""
    try:
        team = Team.query.get_or_404(team_id)
        data = request.get_json() or {}
        
        if 'newsletters_active' in data:
            team.newsletters_active = bool(data['newsletters_active'])
            team.updated_at = datetime.now(timezone.utc)
            db.session.commit()
            
            return jsonify({
                'message': 'Newsletter status updated',
                'team': team.to_dict()
            })
        else:
            return jsonify({'error': 'newsletters_active field required'}), 400
    except Exception as e:
        logger.exception('admin_toggle_newsletter_status failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500

@api_bp.route('/commentaries/<int:commentary_id>/applaud', methods=['POST'])
@limiter.limit("10 per minute")
def applaud_commentary(commentary_id):
    """Applaud a commentary (Like)."""
    try:
        commentary = NewsletterCommentary.query.get(commentary_id)
        if not commentary:
            return jsonify({'error': 'Commentary not found'}), 404
            
        # Optional: Track user if logged in
        user_id = None
        auth = request.headers.get('Authorization', '')
        if auth.startswith('Bearer '):
            try:
                token = auth.split(' ', 1)[1]
                s = _user_serializer()
                data = s.loads(token, max_age=60 * 60 * 24 * 30)
                email = data.get('email')
                user = UserAccount.query.filter_by(email=email).first()
                if user:
                    user_id = user.id
            except Exception:
                pass # Ignore auth errors for applause, treat as anonymous
        
        # Simple session tracking to prevent spamming from same session?
        # For now, we'll just rely on rate limiting and allow multiple claps (Medium style)
        # But we'll log the session_id if available or generate one
        session_id = request.headers.get('X-Session-ID')
        
        applause = CommentaryApplause(
            commentary_id=commentary.id,
            user_id=user_id,
            session_id=session_id
        )
        db.session.add(applause)
        db.session.commit()
        
        # Get updated count
        count = commentary.applause.count()
        
        return jsonify({
            'message': 'Applauded',
            'applause_count': count
        })
    except Exception as e:
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to applaud')), 500


@api_bp.route('/admin/subscriptions/backfill-tokens', methods=['POST'])
@require_api_key
def admin_backfill_unsubscribe_tokens():
    """Backfill unsubscribe_token for all subscriptions that don't have one."""
    try:
        subs_without_token = UserSubscription.query.filter(
            UserSubscription.unsubscribe_token.is_(None)
        ).all()
        
        count = 0
        for sub in subs_without_token:
            sub.unsubscribe_token = str(uuid.uuid4())
            count += 1
        
        db.session.commit()
        
        return jsonify({
            'message': f'Backfilled {count} subscription(s) with unsubscribe tokens',
            'updated_count': count,
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to backfill unsubscribe tokens')
        return jsonify(_safe_error_payload(e, 'Failed to backfill tokens')), 500


# ─────────────────────────────────────────────────────────────────────────────
# Sponsor Endpoints
# ─────────────────────────────────────────────────────────────────────────────

@api_bp.route('/sponsors', methods=['GET'])
def get_sponsors():
    """Public endpoint to get active sponsors for display."""
    try:
        sponsors = Sponsor.query.filter_by(is_active=True).order_by(Sponsor.display_order.asc()).all()
        return jsonify({
            'sponsors': [s.to_public_dict() for s in sponsors]
        })
    except Exception as e:
        logger.exception('Failed to fetch sponsors')
        return jsonify(_safe_error_payload(e, 'Failed to fetch sponsors')), 500


@api_bp.route('/sponsors/<int:sponsor_id>/click', methods=['POST'])
def track_sponsor_click(sponsor_id):
    """Track a click on a sponsor link (basic analytics)."""
    try:
        sponsor = Sponsor.query.get(sponsor_id)
        if not sponsor:
            return jsonify({'error': 'Sponsor not found'}), 404
        
        sponsor.click_count = (sponsor.click_count or 0) + 1
        db.session.commit()
        
        return jsonify({'message': 'Click tracked'})
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to track sponsor click')
        return jsonify(_safe_error_payload(e, 'Failed to track click')), 500


@api_bp.route('/admin/sponsors', methods=['GET'])
@require_api_key
def admin_get_sponsors():
    """Admin endpoint to get all sponsors with full details."""
    try:
        sponsors = Sponsor.query.order_by(Sponsor.display_order.asc()).all()
        return jsonify({
            'sponsors': [s.to_dict() for s in sponsors]
        })
    except Exception as e:
        logger.exception('Failed to fetch sponsors')
        return jsonify(_safe_error_payload(e, 'Failed to fetch sponsors')), 500


@api_bp.route('/admin/sponsors', methods=['POST'])
@require_api_key
def admin_create_sponsor():
    """Create a new sponsor."""
    try:
        data = request.get_json() or {}
        
        name = (data.get('name') or '').strip()
        image_url = (data.get('image_url') or '').strip()
        link_url = (data.get('link_url') or '').strip()
        
        if not name:
            return jsonify({'error': 'Name is required'}), 400
        if not image_url:
            return jsonify({'error': 'Image URL is required'}), 400
        if not link_url:
            return jsonify({'error': 'Link URL is required'}), 400
        
        # Get the next display order (put new sponsors at the end)
        max_order = db.session.query(db.func.max(Sponsor.display_order)).scalar() or 0
        
        sponsor = Sponsor(
            name=name,
            image_url=image_url,
            link_url=link_url,
            description=(data.get('description') or '').strip() or None,
            is_active=data.get('is_active', True),
            display_order=max_order + 1,
        )
        
        db.session.add(sponsor)
        db.session.commit()
        
        return jsonify({
            'message': 'Sponsor created',
            'sponsor': sponsor.to_dict()
        }), 201
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to create sponsor')
        return jsonify(_safe_error_payload(e, 'Failed to create sponsor')), 500


@api_bp.route('/admin/sponsors/<int:sponsor_id>', methods=['PUT'])
@require_api_key
def admin_update_sponsor(sponsor_id):
    """Update an existing sponsor."""
    try:
        sponsor = Sponsor.query.get(sponsor_id)
        if not sponsor:
            return jsonify({'error': 'Sponsor not found'}), 404
        
        data = request.get_json() or {}
        
        if 'name' in data:
            name = (data['name'] or '').strip()
            if not name:
                return jsonify({'error': 'Name cannot be empty'}), 400
            sponsor.name = name
        
        if 'image_url' in data:
            image_url = (data['image_url'] or '').strip()
            if not image_url:
                return jsonify({'error': 'Image URL cannot be empty'}), 400
            sponsor.image_url = image_url
        
        if 'link_url' in data:
            link_url = (data['link_url'] or '').strip()
            if not link_url:
                return jsonify({'error': 'Link URL cannot be empty'}), 400
            sponsor.link_url = link_url
        
        if 'description' in data:
            sponsor.description = (data['description'] or '').strip() or None
        
        if 'is_active' in data:
            sponsor.is_active = bool(data['is_active'])
        
        if 'display_order' in data:
            sponsor.display_order = int(data['display_order'])
        
        db.session.commit()
        
        return jsonify({
            'message': 'Sponsor updated',
            'sponsor': sponsor.to_dict()
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to update sponsor')
        return jsonify(_safe_error_payload(e, 'Failed to update sponsor')), 500


@api_bp.route('/admin/sponsors/<int:sponsor_id>', methods=['DELETE'])
@require_api_key
def admin_delete_sponsor(sponsor_id):
    """Delete a sponsor."""
    try:
        sponsor = Sponsor.query.get(sponsor_id)
        if not sponsor:
            return jsonify({'error': 'Sponsor not found'}), 404
        
        db.session.delete(sponsor)
        db.session.commit()
        
        return jsonify({'message': 'Sponsor deleted'})
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to delete sponsor')
        return jsonify(_safe_error_payload(e, 'Failed to delete sponsor')), 500


@api_bp.route('/admin/sponsors/reorder', methods=['POST'])
@require_api_key
def admin_reorder_sponsors():
    """Reorder sponsors by providing an array of sponsor IDs in the desired order."""
    try:
        data = request.get_json() or {}
        sponsor_ids = data.get('sponsor_ids', [])
        
        if not sponsor_ids or not isinstance(sponsor_ids, list):
            return jsonify({'error': 'sponsor_ids array is required'}), 400
        
        for index, sponsor_id in enumerate(sponsor_ids):
            sponsor = Sponsor.query.get(sponsor_id)
            if sponsor:
                sponsor.display_order = index
        
        db.session.commit()
        
        return jsonify({'message': 'Sponsors reordered'})
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to reorder sponsors')
        return jsonify(_safe_error_payload(e, 'Failed to reorder sponsors')), 500


@api_bp.route('/admin/team-aliases', methods=['GET'])
@require_api_key
def admin_list_team_aliases():
    """List all team aliases."""
    try:
        aliases = TeamAlias.query.order_by(TeamAlias.canonical_name.asc(), TeamAlias.alias.asc()).all()
        return jsonify([a.to_dict() for a in aliases])
    except Exception as e:
        logger.exception('Failed to list team aliases')
        return jsonify(_safe_error_payload(e, 'Failed to list team aliases')), 500


@api_bp.route('/admin/team-aliases', methods=['POST'])
@require_api_key
def admin_create_team_alias():
    """Create a new team alias."""
    try:
        data = request.get_json() or {}
        canonical_name = (data.get('canonical_name') or '').strip()
        alias_name = (data.get('alias') or '').strip()
        
        if not canonical_name or not alias_name:
            return jsonify({'error': 'canonical_name and alias are required'}), 400
            
        # Check if alias already exists
        existing = TeamAlias.query.filter(func.lower(TeamAlias.alias) == func.lower(alias_name)).first()
        if existing:
            return jsonify({'error': f'Alias "{alias_name}" already exists for "{existing.canonical_name}"'}), 400
            
        # Try to find team_id for canonical name
        team = Team.query.filter(func.lower(Team.name) == func.lower(canonical_name)).first()
        team_id = team.id if team else None
        
        alias = TeamAlias(
            canonical_name=canonical_name,
            alias=alias_name,
            team_id=team_id
        )
        db.session.add(alias)
        db.session.commit()
        
        return jsonify(alias.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to create team alias')
        return jsonify(_safe_error_payload(e, 'Failed to create team alias')), 500


@api_bp.route('/admin/team-aliases/<int:alias_id>', methods=['DELETE'])
@require_api_key
def admin_delete_team_alias(alias_id):
    """Delete a team alias."""
    try:
        alias = db.session.get(TeamAlias, alias_id)
        if not alias:
            return jsonify({'error': 'Alias not found'}), 404
            
        db.session.delete(alias)
        db.session.commit()
        
        return jsonify({'message': 'Alias deleted'})
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to delete team alias')
        return jsonify(_safe_error_payload(e, 'Failed to delete team alias')), 500


@api_bp.route('/admin/manual-players', methods=['GET'])
@require_api_key
def admin_list_manual_players():
    """List all manual player submissions."""
    try:
        status = request.args.get('status')
        query = ManualPlayerSubmission.query
        
        if status:
            query = query.filter_by(status=status)
            
        submissions = query.order_by(ManualPlayerSubmission.created_at.desc()).all()
        return jsonify([s.to_dict() for s in submissions])
    except Exception as e:
        logger.exception('Failed to list manual players')
        return jsonify(_safe_error_payload(e, 'Failed to list manual players')), 500


@api_bp.route('/admin/manual-players/<int:submission_id>/review', methods=['POST'])
@require_api_key
def admin_review_manual_player(submission_id):
    """Review (approve/reject) a manual player submission."""
    try:
        submission = db.session.get(ManualPlayerSubmission, submission_id)
        if not submission:
            return jsonify({'error': 'Submission not found'}), 404
            
        data = request.get_json() or {}
        status = data.get('status')
        admin_notes = data.get('admin_notes')
        
        if status not in ['approved', 'rejected']:
            return jsonify({'error': 'Invalid status. Must be approved or rejected'}), 400
            
        submission.status = status
        if admin_notes is not None:
            submission.admin_notes = admin_notes
            
        submission.reviewed_at = datetime.now(timezone.utc)
        
        db.session.commit()
        
        return jsonify(submission.to_dict())
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to review manual player')
        return jsonify(_safe_error_payload(e, 'Failed to review manual player')), 500


# =============================================================================
# Player Journey Endpoints
# =============================================================================
# Note: GET /players/<id>/journey is handled by journey_bp (routes/journey.py).
# Only the /journey/map sub-route lives here.

@api_bp.route('/players/<int:player_id>/journey/map', methods=['GET'])
def get_player_journey_map(player_id: int):
    """
    Get a player's journey in map-optimized format (grouped by club with coordinates).

    Query params:
    - sync: bool - Trigger sync if journey doesn't exist (default: false)
    """
    try:
        from src.models.journey import PlayerJourney, ClubLocation

        should_sync = request.args.get('sync', 'false').lower() == 'true'

        journey = PlayerJourney.query.filter_by(player_api_id=player_id).first()

        # Re-sync if journey is missing, has a sync error, or has no entries
        needs_sync = (
            not journey
            or journey.sync_error is not None
            or not journey.entries.first()
        )
        if needs_sync and should_sync:
            from src.services.journey_sync import JourneySyncService
            service = JourneySyncService()
            journey = service.sync_player(player_id, force_full=bool(journey))

        if not journey:
            # Fallback: build a minimal journey from TrackedPlayer if available
            tracked = TrackedPlayer.query.filter_by(player_api_id=player_id, is_active=True).first()
            if tracked and tracked.team:
                map_data = {
                    'player_api_id': player_id,
                    'player_name': tracked.player_name,
                    'player_photo': tracked.photo_url,
                    'stops': [{
                        'club_id': tracked.team.team_id,
                        'club_name': tracked.team.name,
                        'club_logo': tracked.team.logo,
                        'years': str(datetime.now().year),
                        'levels': [tracked.current_level or tracked.status or 'Academy'],
                        'entry_types': ['academy'],
                        'total_apps': 0,
                        'total_goals': 0,
                        'total_assists': 0,
                        'breakdown': {},
                        'competitions': [],
                        'lat': None,
                        'lng': None,
                    }],
                    'path': [],
                    'source': 'tracked-player',
                }
                # Add loan club stop if on loan
                if tracked.current_club_api_id:
                    loan_team = Team.query.filter_by(team_id=tracked.current_club_api_id).first()
                    if loan_team:
                        map_data['stops'].append({
                            'club_id': tracked.current_club_api_id,
                            'club_name': tracked.current_club_name or loan_team.name,
                            'club_logo': loan_team.logo,
                            'years': str(datetime.now().year),
                            'levels': ['First Team'],
                            'entry_types': ['loan'],
                            'total_apps': 0,
                            'total_goals': 0,
                            'total_assists': 0,
                            'breakdown': {},
                            'competitions': [],
                            'lat': None,
                            'lng': None,
                        })
                return jsonify(map_data)
            return jsonify({'error': 'Journey not found', 'player_id': player_id}), 404

        map_data = journey.to_map_dict()
        
        # Add coordinates for each stop
        club_ids = [stop['club_id'] for stop in map_data['stops']]
        locations = ClubLocation.query.filter(ClubLocation.club_api_id.in_(club_ids)).all()
        location_map = {loc.club_api_id: loc for loc in locations}
        
        for stop in map_data['stops']:
            loc = location_map.get(stop['club_id'])
            if loc:
                stop['lat'] = loc.latitude
                stop['lng'] = loc.longitude
                stop['city'] = loc.city
                stop['country'] = loc.country
            else:
                stop['lat'] = None
                stop['lng'] = None
        
        # Build path (ordered list of coordinates)
        map_data['path'] = [
            [stop['lat'], stop['lng']]
            for stop in map_data['stops']
            if stop.get('lat') and stop.get('lng')
        ]
        
        return jsonify(map_data)
        
    except Exception as e:
        logger.exception(f'Failed to get journey map for player {player_id}')
        return jsonify(_safe_error_payload(e, 'Failed to get player journey map')), 500


@api_bp.route('/admin/journey/sync/<int:player_id>', methods=['POST'])
@require_api_key
def admin_sync_player_journey(player_id: int):
    """
    Trigger journey sync for a specific player.
    
    Body params:
    - force_full: bool - Re-sync all seasons even if already synced
    """
    try:
        from src.services.journey_sync import JourneySyncService
        
        data = request.get_json() or {}
        force_full = data.get('force_full', False)
        
        service = JourneySyncService()
        journey = service.sync_player(player_id, force_full=force_full)
        
        if not journey:
            return jsonify({'error': 'Sync failed', 'player_id': player_id}), 500
        
        return jsonify({
            'success': True,
            'player_id': player_id,
            'journey': journey.to_dict(include_entries=True)
        })
        
    except Exception as e:
        logger.exception(f'Failed to sync journey for player {player_id}')
        return jsonify(_safe_error_payload(e, 'Failed to sync player journey')), 500


@api_bp.route('/admin/journey/bulk-sync', methods=['POST'])
@require_api_key
def admin_bulk_sync_journeys():
    """
    Trigger journey sync for multiple players.
    
    Body params:
    - player_ids: list[int] - List of player API IDs to sync
    - force_full: bool - Re-sync all seasons even if already synced
    """
    try:
        from src.services.journey_sync import JourneySyncService
        
        data = request.get_json() or {}
        player_ids = data.get('player_ids', [])
        force_full = data.get('force_full', False)
        
        if not player_ids:
            return jsonify({'error': 'No player_ids provided'}), 400
        
        if len(player_ids) > 50:
            return jsonify({'error': 'Maximum 50 players per bulk sync'}), 400
        
        service = JourneySyncService()
        results = {'success': [], 'failed': []}
        
        for player_id in player_ids:
            try:
                journey = service.sync_player(player_id, force_full=force_full)
                if journey:
                    results['success'].append(player_id)
                else:
                    results['failed'].append({'player_id': player_id, 'error': 'Sync returned None'})
            except Exception as e:
                results['failed'].append({'player_id': player_id, 'error': str(e)})
        
        return jsonify(results)
        
    except Exception as e:
        logger.exception('Failed to bulk sync journeys')
        return jsonify(_safe_error_payload(e, 'Failed to bulk sync journeys')), 500


@api_bp.route('/admin/journey/diagnostics', methods=['GET'])
@require_api_key
def admin_journey_diagnostics():
    """Report journey data health for all tracked players."""
    try:
        from src.models.journey import PlayerJourney, PlayerJourneyEntry
        from sqlalchemy import func

        total_active = TrackedPlayer.query.filter(
            TrackedPlayer.is_active == True,
        ).count()

        with_journey = TrackedPlayer.query.filter(
            TrackedPlayer.is_active == True,
            TrackedPlayer.journey_id.isnot(None),
        ).count()

        missing_journey_link = total_active - with_journey

        with_errors = db.session.query(func.count(PlayerJourney.id)).filter(
            PlayerJourney.sync_error.isnot(None)
        ).scalar()

        # Journeys with 0 entries
        journeys_with_entries = db.session.query(
            PlayerJourneyEntry.journey_id
        ).distinct().subquery()
        empty_journeys = db.session.query(func.count(PlayerJourney.id)).filter(
            ~PlayerJourney.id.in_(
                db.session.query(journeys_with_entries.c.journey_id)
            )
        ).scalar()

        # Sample of error messages for debugging
        error_samples = db.session.query(
            PlayerJourney.player_api_id,
            PlayerJourney.player_name,
            PlayerJourney.sync_error,
        ).filter(
            PlayerJourney.sync_error.isnot(None)
        ).limit(10).all()

        return jsonify({
            'total_active_tracked': total_active,
            'with_journey': with_journey,
            'missing_journey_link': missing_journey_link,
            'journeys_with_sync_error': with_errors,
            'journeys_with_zero_entries': empty_journeys,
            'coverage_pct': round(with_journey / total_active * 100, 1) if total_active else 0,
            'error_samples': [
                {'player_api_id': e[0], 'player_name': e[1], 'sync_error': e[2]}
                for e in error_samples
            ],
        })
    except Exception as e:
        logger.exception('Failed to get journey diagnostics')
        return jsonify(_safe_error_payload(e, 'Failed to get journey diagnostics')), 500


@api_bp.route('/admin/journey/repair', methods=['POST'])
@require_api_key
def admin_repair_journeys():
    """Re-sync broken journeys: those with sync_error or 0 entries.

    Body: { limit?: int (default 20), category?: 'error'|'empty'|'unlinked'|'all' }
    """
    try:
        from src.models.journey import PlayerJourney, PlayerJourneyEntry
        from src.services.journey_sync import JourneySyncService
        from sqlalchemy import func

        data = request.get_json(silent=True) or {}
        limit = min(int(data.get('limit', 20)), 100)
        category = data.get('category', 'all')

        service = JourneySyncService()
        player_ids_to_sync = []

        # error category — only journeys linked to active tracked players
        if category in ('error', 'all'):
            error_journeys = db.session.query(PlayerJourney.player_api_id).join(
                TrackedPlayer, TrackedPlayer.journey_id == PlayerJourney.id
            ).filter(
                TrackedPlayer.is_active == True,
                PlayerJourney.sync_error.isnot(None),
            ).distinct().limit(limit).all()
            player_ids_to_sync.extend([j[0] for j in error_journeys])

        # empty category — same scoping
        if category in ('empty', 'all') and len(player_ids_to_sync) < limit:
            journeys_with_entries = db.session.query(
                PlayerJourneyEntry.journey_id
            ).distinct().subquery()
            empty_journeys = db.session.query(PlayerJourney.player_api_id).join(
                TrackedPlayer, TrackedPlayer.journey_id == PlayerJourney.id
            ).filter(
                TrackedPlayer.is_active == True,
                ~PlayerJourney.id.in_(
                    db.session.query(journeys_with_entries.c.journey_id)
                ),
            ).distinct().limit(limit - len(player_ids_to_sync)).all()
            player_ids_to_sync.extend([j[0] for j in empty_journeys])

        if category in ('unlinked', 'all') and len(player_ids_to_sync) < limit:
            unlinked = TrackedPlayer.query.filter(
                TrackedPlayer.is_active == True,
                TrackedPlayer.journey_id.is_(None),
            ).limit(limit - len(player_ids_to_sync)).all()
            player_ids_to_sync.extend([tp.player_api_id for tp in unlinked])

        # Deduplicate
        player_ids_to_sync = list(dict.fromkeys(player_ids_to_sync))[:limit]

        results = []
        for pid in player_ids_to_sync:
            try:
                journey = service.sync_player(pid, force_full=True)
                if journey:
                    # Link any unlinked TrackedPlayers
                    unlinked_tps = TrackedPlayer.query.filter(
                        TrackedPlayer.player_api_id == pid,
                        TrackedPlayer.journey_id.is_(None),
                    ).all()
                    for tp in unlinked_tps:
                        tp.journey_id = journey.id
                    results.append({'player_api_id': pid, 'status': 'repaired',
                                    'entries': len(journey.entries.all())})
                else:
                    results.append({'player_api_id': pid, 'status': 'sync_returned_none'})
            except Exception as sync_err:
                results.append({'player_api_id': pid, 'status': 'error',
                                'error': str(sync_err)})

        db.session.commit()

        repaired = sum(1 for r in results if r['status'] == 'repaired')
        return jsonify({
            'total_attempted': len(results),
            'repaired': repaired,
            'failed': len(results) - repaired,
            'details': results,
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to repair journeys')
        return jsonify(_safe_error_payload(e, 'Failed to repair journeys')), 500


@api_bp.route('/admin/journey/seed-locations', methods=['POST'])
@require_api_key
def admin_seed_club_locations():
    """Seed initial club locations for major clubs."""
    try:
        from src.services.journey_sync import seed_club_locations
        
        added = seed_club_locations()
        
        return jsonify({
            'success': True,
            'clubs_added': added
        })
        
    except Exception as e:
        logger.exception('Failed to seed club locations')
        return jsonify(_safe_error_payload(e, 'Failed to seed club locations')), 500


@api_bp.route('/club-locations', methods=['GET'])
def get_club_locations():
    """Get all club locations for map display."""
    try:
        from src.models.journey import ClubLocation
        
        locations = ClubLocation.query.all()
        
        return jsonify({
            'locations': [loc.to_dict() for loc in locations],
            'count': len(locations)
        })
        
    except Exception as e:
        logger.exception('Failed to get club locations')
        return jsonify(_safe_error_payload(e, 'Failed to get club locations')), 500


@api_bp.route('/club-locations/<int:club_api_id>', methods=['GET'])
def get_club_location(club_api_id: int):
    """Get location for a specific club."""
    try:
        from src.models.journey import ClubLocation
        
        location = ClubLocation.query.filter_by(club_api_id=club_api_id).first()
        
        if not location:
            return jsonify({'error': 'Club location not found'}), 404
        
        return jsonify(location.to_dict())
        
    except Exception as e:
        logger.exception(f'Failed to get location for club {club_api_id}')
        return jsonify(_safe_error_payload(e, 'Failed to get club location')), 500


@api_bp.route('/admin/club-locations', methods=['POST'])
@require_api_key
def admin_add_club_location():
    """Add or update a club location."""
    try:
        from src.models.journey import ClubLocation
        
        data = request.get_json() or {}
        
        required = ['club_api_id', 'club_name', 'latitude', 'longitude']
        missing = [f for f in required if f not in data]
        if missing:
            return jsonify({'error': f'Missing required fields: {missing}'}), 400
        
        location = ClubLocation.query.filter_by(club_api_id=data['club_api_id']).first()
        
        if location:
            # Update existing
            location.club_name = data.get('club_name', location.club_name)
            location.city = data.get('city', location.city)
            location.country = data.get('country', location.country)
            location.country_code = data.get('country_code', location.country_code)
            location.latitude = data['latitude']
            location.longitude = data['longitude']
            location.geocode_source = data.get('geocode_source', 'manual')
        else:
            # Create new
            location = ClubLocation(
                club_api_id=data['club_api_id'],
                club_name=data['club_name'],
                city=data.get('city'),
                country=data.get('country'),
                country_code=data.get('country_code'),
                latitude=data['latitude'],
                longitude=data['longitude'],
                geocode_source=data.get('geocode_source', 'manual'),
                geocode_confidence=1.0,
            )
            db.session.add(location)
        
        db.session.commit()
        
        return jsonify(location.to_dict())
        
    except Exception as e:
        db.session.rollback()
        logger.exception('Failed to add club location')
        return jsonify(_safe_error_payload(e, 'Failed to add club location')), 500


# ====================================================================
# 📊 API-Football Usage & Cache Admin Endpoints
# ====================================================================

@api_bp.route('/admin/api-usage', methods=['GET'])
@require_api_key
def admin_api_usage():
    """Return API-Football usage stats: today by endpoint + last 7 days trend."""
    try:
        from src.models.api_cache import APIUsageDaily
        days = request.args.get('days', 7, type=int)
        summary = APIUsageDaily.usage_summary(days=days)
        return jsonify(summary)
    except Exception as e:
        logger.exception('admin_api_usage failed')
        return jsonify(_safe_error_payload(e, 'Failed to retrieve API usage')), 500


@api_bp.route('/admin/api-cache/stats', methods=['GET'])
@require_api_key
def admin_api_cache_stats():
    """Return cache stats: entry counts by endpoint, oldest/newest entries."""
    try:
        from src.models.api_cache import APICache
        stats = APICache.stats()
        return jsonify(stats)
    except Exception as e:
        logger.exception('admin_api_cache_stats failed')
        return jsonify(_safe_error_payload(e, 'Failed to retrieve cache stats')), 500


@api_bp.route('/admin/api-cache/cleanup', methods=['POST'])
@require_api_key
def admin_api_cache_cleanup():
    """Delete expired cache entries. Returns the number of rows removed."""
    try:
        from src.models.api_cache import APICache
        deleted = APICache.cleanup_expired()
        return jsonify({'deleted': deleted})
    except Exception as e:
        db.session.rollback()
        logger.exception('admin_api_cache_cleanup failed')
        return jsonify(_safe_error_payload(e, 'Cache cleanup failed')), 500


# ====================================================================
# Player Classification Sandbox
# ====================================================================

@api_bp.route('/admin/players/search-api', methods=['GET'])
@require_api_key
def admin_search_api_players():
    """Proxy search to API-Football player search endpoint."""
    query = request.args.get('q', '').strip()
    if not query or len(query) < 2:
        return jsonify({'results': []})
    season = request.args.get('season', type=int)
    try:
        from src.api_football_client import APIFootballClient
        api = APIFootballClient()
        raw = api.search_player_profiles(query, season=season)
        results = []
        for item in raw[:20]:
            player = item.get('player', {})
            stats = item.get('statistics', [{}])
            team_info = stats[0].get('team', {}) if stats else {}
            results.append({
                'id': player.get('id'),
                'name': player.get('name'),
                'photo': player.get('photo'),
                'nationality': player.get('nationality'),
                'age': player.get('age'),
                'team': team_info.get('name'),
                'team_id': team_info.get('id'),
            })
        return jsonify({'results': results})
    except Exception as e:
        logger.exception('admin_search_api_players failed')
        return jsonify(_safe_error_payload(e, 'Player search failed')), 500


@api_bp.route('/admin/players/test-classify', methods=['POST'])
@require_api_key
def admin_test_classify():
    """Run the classifier pipeline on a single player and return detailed reasoning."""
    data = request.get_json() or {}
    player_api_id = data.get('player_api_id')
    if not player_api_id:
        return jsonify({'error': 'player_api_id is required'}), 400
    try:
        player_api_id = int(player_api_id)
    except (ValueError, TypeError):
        return jsonify({'error': 'player_api_id must be an integer'}), 400

    force_sync = data.get('force_sync', False)

    try:
        from src.models.journey import PlayerJourney, PlayerJourneyEntry
        from src.services.journey_sync import JourneySyncService
        from src.api_football_client import APIFootballClient
        service = JourneySyncService()
        journey = service.sync_player(player_api_id, force_full=force_sync)
        if not journey:
            return jsonify({'error': f'Could not sync journey for player {player_api_id}'}), 404

        entries = PlayerJourneyEntry.query.filter_by(
            journey_id=journey.id
        ).order_by(PlayerJourneyEntry.season, PlayerJourneyEntry.sort_priority).all()

        # Determine which parent clubs to classify against
        parent_api_id = data.get('parent_api_id')
        if parent_api_id:
            parent_ids = [int(parent_api_id)]
        else:
            parent_ids = journey.academy_club_ids or []

        # Fetch transfers for upgrade check
        api = APIFootballClient()
        raw_transfers = api.get_player_transfers(player_api_id)
        transfers = flatten_transfers(raw_transfers)

        # Run classification with reasoning for each parent
        classifications = []
        for pid in parent_ids:
            team = Team.query.filter_by(team_id=pid, is_active=True).order_by(Team.season.desc()).first()
            parent_name = team.name if team else str(pid)

            status, loan_id, loan_name, reasoning = classify_tracked_player(
                journey.current_club_api_id, journey.current_club_name,
                journey.current_level, pid, parent_name,
                transfers=transfers,
                with_reasoning=True,
                latest_season=_get_latest_season(journey.id, parent_api_id=pid, parent_club_name=parent_name),
            )

            classifications.append({
                'parent_api_id': pid,
                'parent_club_name': parent_name,
                'status': status,
                'current_club_api_id': loan_id,
                'current_club_name': loan_name,
                'reasoning': reasoning,
            })

        # Transfer summary
        transfer_summary = []
        for t in (transfers or []):
            teams = t.get('teams', {})
            transfer_summary.append({
                'date': t.get('date'),
                'from': teams.get('out', {}).get('name'),
                'to': teams.get('in', {}).get('name'),
                'type': t.get('type'),
            })

        # Check existing tracked player for diff
        existing = TrackedPlayer.query.filter_by(
            player_api_id=player_api_id, is_active=True
        ).all()
        existing_info = []
        for tp in existing:
            parent_tid = tp.team.team_id if tp.team else None
            matching = next((c for c in classifications if c['parent_api_id'] == parent_tid), None)
            existing_info.append({
                'parent_api_id': parent_tid,
                'parent_club_name': tp.team.name if tp.team else None,
                'current_status': tp.status,
                'new_status': matching['status'] if matching else None,
                'would_change': matching['status'] != tp.status if matching else False,
            })

        return jsonify({
            'player': {
                'api_id': player_api_id,
                'name': journey.player_name,
                'photo': journey.player_photo,
                'nationality': journey.nationality,
                'birth_date': journey.birth_date,
                'birth_country': getattr(journey, 'birth_country', None),
            },
            'journey': {
                'id': journey.id,
                'origin_club': journey.origin_club_name,
                'current_club': journey.current_club_name,
                'current_club_api_id': journey.current_club_api_id,
                'current_level': journey.current_level,
                'total_clubs': journey.total_clubs,
                'academy_club_ids': journey.academy_club_ids,
                'entries': [{
                    'season': e.season,
                    'club_name': e.club_name,
                    'club_api_id': e.club_api_id,
                    'club_logo': e.club_logo,
                    'league_name': e.league_name,
                    'level': e.level,
                    'entry_type': e.entry_type,
                    'appearances': e.appearances,
                    'goals': e.goals,
                    'assists': e.assists,
                    'minutes': e.minutes,
                    'is_youth': e.is_youth,
                    'is_international': e.is_international,
                } for e in entries],
            },
            'classifications': classifications,
            'transfer_summary': transfer_summary,
            'existing_tracked': existing_info,
        })
    except Exception as e:
        logger.exception('admin_test_classify failed')
        return jsonify(_safe_error_payload(e, 'Classification failed')), 500


@api_bp.route('/admin/players/explain-academy', methods=['POST'])
@require_api_key
def admin_explain_academy():
    """Explain why a player is (or isn't) classified as an academy product.

    Shows the full evidence chain: youth entries, entry_type classification
    reasoning, name resolution, academy_club_ids, and TrackedPlayer rows.

    Body: { player_api_id: int, team_api_id?: int, force_sync?: bool }
    """
    data = request.get_json() or {}
    player_api_id = data.get('player_api_id')
    if not player_api_id:
        return jsonify({'error': 'player_api_id is required'}), 400
    try:
        player_api_id = int(player_api_id)
    except (ValueError, TypeError):
        return jsonify({'error': 'player_api_id must be an integer'}), 400

    team_api_id = data.get('team_api_id')
    if team_api_id:
        team_api_id = int(team_api_id)
    force_sync = data.get('force_sync', False)

    try:
        from src.models.journey import PlayerJourney, PlayerJourneyEntry
        from src.services.journey_sync import JourneySyncService
        from src.api_football_client import APIFootballClient, is_new_loan_transfer, LOAN_RETURN_TYPES
        from src.utils.academy_classifier import strip_youth_suffix

        api = APIFootballClient()
        service = JourneySyncService(api)

        journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()
        if not journey or force_sync:
            journey = service.sync_player(player_api_id, force_full=force_sync)
        if not journey:
            return jsonify({'error': f'No journey data for player {player_api_id}'}), 404

        entries = PlayerJourneyEntry.query.filter_by(
            journey_id=journey.id
        ).order_by(PlayerJourneyEntry.season, PlayerJourneyEntry.sort_priority).all()

        # Replay _apply_development_classification reasoning
        first_team_debut_by_club = {}
        for e in entries:
            if e.level == 'First Team' and not e.is_international:
                base = strip_youth_suffix(e.club_name)
                if base not in first_team_debut_by_club or e.season < first_team_debut_by_club[base]:
                    first_team_debut_by_club[base] = e.season

        # Detect permanent transfer destinations
        raw_transfers = api.get_player_transfers(player_api_id)
        transfers = flatten_transfers(raw_transfers)
        permanent_dest_ids = set()
        permanent_dest_info = []
        for t in (transfers or []):
            ttype = (t.get('type') or '').strip().lower()
            if not ttype or is_new_loan_transfer(ttype) or ttype in LOAN_RETURN_TYPES:
                continue
            teams = t.get('teams', {})
            dest = teams.get('in', {})
            dest_id = dest.get('id')
            if dest_id:
                permanent_dest_ids.add(dest_id)
                permanent_dest_info.append({
                    'date': t.get('date'),
                    'type': t.get('type'),
                    'from': teams.get('out', {}).get('name'),
                    'to': dest.get('name'),
                    'to_id': dest_id,
                })

        # Parse birth year
        birth_year = None
        if journey.birth_date:
            try:
                birth_year = int(str(journey.birth_date)[:4])
            except (ValueError, TypeError):
                pass

        # Track earliest youth season per club
        earliest_youth = {}
        for e in entries:
            if e.is_youth and not e.is_international:
                base = strip_youth_suffix(e.club_name)
                if base not in earliest_youth or e.season < earliest_youth[base]:
                    earliest_youth[base] = e.season

        # Build detailed entry analysis
        entry_analysis = []
        for e in entries:
            analysis = {
                'season': e.season,
                'club_name': e.club_name,
                'club_api_id': e.club_api_id,
                'league_name': e.league_name,
                'league_country': getattr(e, 'league_country', None),
                'level': e.level,
                'entry_type': e.entry_type,
                'is_youth': e.is_youth,
                'is_international': e.is_international,
                'appearances': e.appearances,
            }
            if e.is_youth and not e.is_international:
                base = strip_youth_suffix(e.club_name)
                reasons = []
                if e.entry_type == 'integration':
                    for club, debut in first_team_debut_by_club.items():
                        if club != base and debut <= e.season:
                            reasons.append(f'first-team at {club} in season {debut}')
                            break
                    if e.club_api_id in permanent_dest_ids:
                        reasons.append('permanent transfer destination')
                    if birth_year:
                        first_s = earliest_youth.get(base)
                        if first_s and (first_s - birth_year) >= 21:
                            reasons.append(f'age {first_s - birth_year} at first youth appearance')
                    if not reasons:
                        reasons.append('classified by journey sync')
                elif e.entry_type == 'development':
                    same_debut = first_team_debut_by_club.get(base)
                    if same_debut is not None:
                        reasons.append(f'first-team debut at same club in season {same_debut}')
                elif e.entry_type == 'academy':
                    reasons.append('genuine academy entry')
                analysis['classification_reasons'] = reasons
                analysis['included_in_academy_computation'] = (
                    e.entry_type in ('academy', 'development')
                )
            entry_analysis.append(analysis)

        # Academy club IDs computation trace
        academy_entries = [
            e for e in entries
            if e.is_youth and not e.is_international
            and e.entry_type in ('academy', 'development')
        ]
        club_apps = {}
        for e in academy_entries:
            base = strip_youth_suffix(e.club_name)
            club_apps[base] = club_apps.get(base, 0) + (e.appearances or 0)

        academy_computation = []
        senior_name_to_id = {}
        for e in entries:
            if not e.is_youth and not e.is_international:
                senior_name_to_id[e.club_name] = e.club_api_id

        for base_name, apps in club_apps.items():
            passed = apps >= 3
            entry_country = None
            for e in academy_entries:
                if strip_youth_suffix(e.club_name) == base_name and getattr(e, 'league_country', None):
                    entry_country = e.league_country
                    break
            comp = {
                'base_name': base_name,
                'total_youth_appearances': apps,
                'passed_min_threshold': passed,
                'league_country': entry_country,
            }
            if passed:
                if base_name in senior_name_to_id:
                    comp['resolution_method'] = 'senior_entry_match'
                    comp['resolved_api_id'] = senior_name_to_id[base_name]
                else:
                    profile = TeamProfile.query.filter(TeamProfile.name == base_name).first()
                    if profile:
                        comp['resolution_method'] = 'team_profile_exact'
                        comp['resolved_api_id'] = profile.team_id
                    else:
                        team_match = Team.query.filter(Team.name == base_name).first()
                        if team_match:
                            comp['resolution_method'] = 'team_table_exact'
                            comp['resolved_api_id'] = team_match.team_id
                        else:
                            comp['resolution_method'] = 'substring_fallback_or_unresolved'
                            comp['resolved_api_id'] = None
            academy_computation.append(comp)

        # Team-specific result
        team_result = None
        if team_api_id:
            is_in = team_api_id in (journey.academy_club_ids or [])
            team_result = {'team_api_id': team_api_id, 'is_academy_for_team': is_in}
            if not is_in:
                reasons = []
                has_youth = any(
                    e.is_youth and not e.is_international and e.club_api_id == team_api_id
                    for e in entries
                )
                if not has_youth:
                    reasons.append('No youth entries found for this team')
                else:
                    excluded = [
                        e for e in entries
                        if e.is_youth and not e.is_international
                        and e.club_api_id == team_api_id
                        and e.entry_type == 'integration'
                    ]
                    if excluded:
                        reasons.append(f'{len(excluded)} youth entries classified as integration')
                    below = [
                        e for e in entries
                        if e.is_youth and not e.is_international
                        and e.club_api_id == team_api_id
                        and e.entry_type in ('academy', 'development')
                    ]
                    if below:
                        total = sum(e.appearances or 0 for e in below)
                        if total < 3:
                            reasons.append(f'Only {total} youth appearances (minimum 3 required)')
                team_result['exclusion_reasons'] = reasons

        # Existing TrackedPlayer rows
        existing = TrackedPlayer.query.filter_by(player_api_id=player_api_id).all()
        tracked_info = [{
            'team_name': tp.team.name if tp.team else None,
            'team_api_id': tp.team.team_id if tp.team else None,
            'status': tp.status,
            'is_active': tp.is_active,
            'data_source': tp.data_source,
        } for tp in existing]

        return jsonify({
            'player': {
                'api_id': player_api_id,
                'name': journey.player_name,
                'birth_date': journey.birth_date,
                'birth_year': birth_year,
                'nationality': journey.nationality,
            },
            'academy_club_ids': journey.academy_club_ids or [],
            'team_result': team_result,
            'first_team_history': first_team_debut_by_club,
            'permanent_transfers_in': permanent_dest_info,
            'entries': entry_analysis,
            'academy_computation': academy_computation,
            'existing_tracked_players': tracked_info,
        })
    except Exception as e:
        logger.exception('admin_explain_academy failed')
        return jsonify(_safe_error_payload(e, 'Explain academy failed')), 500


@api_bp.route('/admin/tracked-players/recompute-academy-ids', methods=['POST'])
@require_api_key
def admin_recompute_academy_ids():
    """Batch recompute origins and academy_club_ids for all journeys.

    Replays _update_journey_aggregates() which resolves youth-team origins
    to parent clubs and recomputes academy_club_ids with current rules.
    Players whose academy_club_ids shrinks will have orphaned TrackedPlayer
    rows deactivated.

    Body (optional): { dry_run?: bool (default true) }
    """
    data = request.get_json(force=True) if request.data else {}
    dry_run = data.get('dry_run', True)

    try:
        from src.models.journey import PlayerJourney, PlayerJourneyEntry
        from src.services.journey_sync import JourneySyncService
        from src.utils.academy_classifier import strip_youth_suffix

        service = JourneySyncService()

        journeys = PlayerJourney.query.filter(
            PlayerJourney.academy_club_ids.isnot(None),
            db.func.jsonb_array_length(PlayerJourney.academy_club_ids) > 0,
        ).all()

        changes = []
        unchanged = 0
        total = len(journeys)

        # Use a savepoint so dry-run can roll back all mutations
        # (_apply_development_classification mutates entry_type,
        # _compute_academy_club_ids writes academy_club_ids and
        # calls _upsert_tracked_players).
        if dry_run:
            savepoint = db.session.begin_nested()

        for journey in journeys:
            old_ids = set(journey.academy_club_ids or [])
            old_origin_id = journey.origin_club_api_id
            old_origin_name = journey.origin_club_name

            entries = PlayerJourneyEntry.query.filter_by(
                journey_id=journey.id
            ).order_by(PlayerJourneyEntry.season).all()

            if not entries:
                continue

            # Fetch transfers for enhanced integration detection
            transfers = []
            try:
                from src.api_football_client import APIFootballClient
                api_client = APIFootballClient()
                raw = api_client.get_player_transfers(journey.player_api_id)
                transfers = flatten_transfers(raw)
            except Exception:
                pass

            # Re-run development classification on entries
            service._apply_development_classification(
                entries, transfers=transfers,
                birth_date=journey.birth_date,
            )

            # Re-run journey aggregates (origin resolution + academy computation).
            # _update_journey_aggregates resolves youth origins to parent clubs
            # and internally calls _compute_academy_club_ids.
            service._update_journey_aggregates(journey, transfers=transfers)
            new_ids = set(journey.academy_club_ids or [])

            removed = old_ids - new_ids
            added = new_ids - old_ids
            origin_changed = (journey.origin_club_api_id != old_origin_id
                              or journey.origin_club_name != old_origin_name)

            if removed or added or origin_changed:
                change = {
                    'player_api_id': journey.player_api_id,
                    'player_name': journey.player_name,
                    'old_academy_ids': sorted(old_ids),
                    'new_academy_ids': sorted(new_ids),
                    'removed': sorted(removed),
                    'added': sorted(added),
                }
                if origin_changed:
                    change['old_origin'] = {
                        'api_id': old_origin_id,
                        'name': old_origin_name,
                    }
                    change['new_origin'] = {
                        'api_id': journey.origin_club_api_id,
                        'name': journey.origin_club_name,
                    }
                changes.append(change)
            else:
                unchanged += 1

        if dry_run:
            # Roll back all mutations — entry_type changes, academy_club_ids,
            # and any TrackedPlayer deactivations from _upsert_tracked_players
            savepoint.rollback()
            deactivated = sum(len(c['removed']) for c in changes)
        else:
            db.session.commit()
            deactivated = sum(len(c['removed']) for c in changes)

        return jsonify({
            'dry_run': dry_run,
            'total_journeys': total,
            'unchanged': unchanged,
            'changed': len(changes),
            'would_deactivate' if dry_run else 'deactivated': deactivated,
            'changes': changes[:100],
            'truncated': len(changes) > 100,
        })
    except Exception as e:
        logger.exception('admin_recompute_academy_ids failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Recompute failed')), 500


@api_bp.route('/admin/api-football/status', methods=['GET'])
@require_api_key
def admin_api_football_status():
    """Composite API-Football connection status: mode, key, usage, cache."""
    import os
    result = {}

    # Connection info
    key = os.getenv('API_FOOTBALL_KEY', '')
    result['mode'] = os.getenv('API_FOOTBALL_MODE', 'direct')
    result['key_present'] = bool(key)
    result['key_prefix'] = (key[:4] + '****') if len(key) >= 4 else ('****' if key else '')

    # Usage stats
    try:
        from src.models.api_cache import APIUsageDaily
        result['usage'] = APIUsageDaily.usage_summary(days=7)
    except Exception:
        result['usage'] = None

    # Cache stats
    try:
        from src.models.api_cache import APICache
        result['cache'] = APICache.stats()
    except Exception:
        result['cache'] = None

    return jsonify(result)


# ====================================================================
# Tracked Players CRUD
# ====================================================================

@api_bp.route('/admin/tracked-players', methods=['GET'])
@require_api_key
def admin_list_tracked_players():
    """List tracked players with filters and pagination."""
    try:
        query = TrackedPlayer.query.filter_by(is_active=True)

        # Filters
        team_id = request.args.get('team_id', type=int)
        if team_id:
            query = query.filter_by(team_id=team_id)

        status = request.args.get('status')
        if status:
            query = query.filter_by(status=status)

        level = request.args.get('level')
        if level:
            query = query.filter_by(current_level=level)

        data_source = request.args.get('data_source')
        if data_source:
            query = query.filter_by(data_source=data_source)

        search = request.args.get('search', '').strip()
        if search:
            query = query.filter(TrackedPlayer.player_name.ilike(f'%{search}%'))

        # Pagination
        page = request.args.get('page', 1, type=int)
        if page < 1:
            page = 1
        page_size = request.args.get('page_size', 50, type=int)
        if page_size < 1:
            page_size = 1
        if page_size > 200:
            page_size = 200

        total = query.count()
        total_pages = max(1, math.ceil(total / page_size))
        if page > total_pages:
            page = total_pages

        offset = (page - 1) * page_size
        players = query.order_by(TrackedPlayer.player_name).offset(offset).limit(page_size).all()

        return jsonify({
            'items': [p.to_dict() for p in players],
            'total': total,
            'page': page,
            'page_size': page_size,
            'total_pages': total_pages,
        })
    except Exception as e:
        logger.exception('admin_list_tracked_players failed')
        return jsonify(_safe_error_payload(e, 'Failed to list tracked players')), 500


@api_bp.route('/admin/tracked-players', methods=['POST'])
@require_api_key
def admin_create_tracked_player():
    """Create a new tracked player."""
    try:
        data = request.get_json(force=True)
        player_name = (data.get('player_name') or '').strip()
        if not player_name:
            return jsonify({'error': 'player_name is required'}), 400

        team_id = data.get('team_id')
        if not team_id:
            return jsonify({'error': 'team_id is required'}), 400

        # Auto-generate a negative player_api_id for manual entries
        player_api_id = data.get('player_api_id')
        if not player_api_id:
            min_id = db.session.query(func.min(TrackedPlayer.player_api_id)).scalar() or 0
            player_api_id = min(min_id, 0) - 1

        player = TrackedPlayer(
            player_api_id=player_api_id,
            player_name=player_name,
            team_id=team_id,
            status=data.get('status', 'academy'),
            current_level=data.get('current_level'),
            position=data.get('position'),
            nationality=data.get('nationality'),
            age=data.get('age'),
            current_club_api_id=data.get('current_club_api_id'),
            current_club_name=data.get('current_club_name'),
            data_source=data.get('data_source', 'manual'),
            notes=data.get('notes'),
        )
        db.session.add(player)
        db.session.commit()
        return jsonify(player.to_dict()), 201
    except Exception as e:
        db.session.rollback()
        logger.exception('admin_create_tracked_player failed')
        return jsonify(_safe_error_payload(e, 'Failed to create tracked player')), 500


@api_bp.route('/admin/tracked-players/<int:player_id>', methods=['PUT'])
@require_api_key
def admin_update_tracked_player(player_id):
    """Update a tracked player (partial updates)."""
    try:
        player = TrackedPlayer.query.get(player_id)
        if not player:
            return jsonify({'error': 'Player not found'}), 404

        data = request.get_json(force=True)
        allowed = ['status', 'current_level', 'current_club_api_id', 'current_club_name',
                    'notes', 'position', 'is_active', 'photo_url', 'team_id',
                    'pinned_parent']
        for field in allowed:
            if field in data:
                setattr(player, field, data[field])

        db.session.commit()
        return jsonify(player.to_dict())
    except Exception as e:
        db.session.rollback()
        logger.exception('admin_update_tracked_player failed')
        return jsonify(_safe_error_payload(e, 'Failed to update tracked player')), 500


@api_bp.route('/admin/tracked-players/<int:player_id>', methods=['DELETE'])
@require_api_key
def admin_delete_tracked_player(player_id):
    """Soft-delete a tracked player (set is_active=False)."""
    try:
        player = TrackedPlayer.query.get(player_id)
        if not player:
            return jsonify({'error': 'Player not found'}), 404

        player.is_active = False
        db.session.commit()
        return jsonify({'message': 'Player deactivated', 'id': player_id})
    except Exception as e:
        db.session.rollback()
        logger.exception('admin_delete_tracked_player failed')
        return jsonify(_safe_error_payload(e, 'Failed to delete tracked player')), 500


@api_bp.route('/admin/tracked-players/refresh-statuses', methods=['POST'])
@require_api_key
def admin_refresh_tracked_player_statuses():
    """Re-derive status/loan fields for TrackedPlayers using the academy classifier.

    Body: { team_id?: int, resync_journeys?: bool } — if omitted, refreshes all active TrackedPlayers.
    When resync_journeys is true, re-syncs each player's journey data from API-Football
    before re-deriving statuses (fixes stale current_club data).

    Default changed 2026-04 (post O. Hammond incident): resync_journeys now
    defaults to True. The previous default of False silently ran the classifier
    against cached journey data, so a naive "refresh statuses" click did
    nothing useful for stale rows. Operators who explicitly want the
    cache-only behaviour must now pass resync_journeys=false.
    """
    try:
        data = request.get_json(force=True) or {}
        team_id = data.get('team_id')
        resync_journeys = data.get('resync_journeys', True)

        from src.services.transfer_heal_service import refresh_and_heal
        result = refresh_and_heal(
            team_id=team_id,
            resync_journeys=resync_journeys,
            cascade_fixtures=False,
        )

        # Return the same shape as before for backwards compatibility,
        # plus the new fail-loud prefetch fields so operators can see at a
        # glance whether any players were deliberately skipped.
        response = {
            'total': result['total'],
            'updated': result['updated'],
            'skipped_by_failed_prefetch': result.get('skipped_by_failed_prefetch', 0),
            'failed_squad_clubs': result.get('failed_squad_clubs', []),
        }
        if resync_journeys:
            response['journeys_resynced'] = result['journeys_resynced']
        return jsonify(response)
    except Exception as e:
        db.session.rollback()
        logger.exception('admin_refresh_tracked_player_statuses failed')
        return jsonify(_safe_error_payload(e, 'Failed to refresh statuses')), 500


def _seed_single_team(team, max_age=30, sync_journeys=True, years=4, season=None):
    """Core seed logic: discover academy players and create TrackedPlayer rows.

    Can be called from the HTTP endpoint or from a background worker.
    Returns a dict with result stats.
    """
    from src.models.journey import PlayerJourney
    from src.services.journey_sync import JourneySyncService
    from sqlalchemy import cast
    from sqlalchemy.dialects.postgresql import JSONB as PG_JSONB

    _api = APIFootballClient()
    if season is None:
        season = _api.current_season_start_year

    parent_api_id = team.team_id
    team_id = team.id
    logger.info(
        'seed_tracked_players: starting for %s (api_id=%s, season=%s, '
        'max_age=%s, sync_journeys=%s)',
        team.name, parent_api_id, season, max_age, sync_journeys,
    )

    # ── Source 1: Players already identified as academy products ──
    known_journeys = PlayerJourney.query.filter(
        PlayerJourney.academy_club_ids.contains(cast([parent_api_id], PG_JSONB))
    ).all()
    candidate_ids = {j.player_api_id: j for j in known_journeys}
    logger.info(
        'seed_tracked_players: %d players already have academy_club_ids containing %s',
        len(candidate_ids), parent_api_id,
    )

    # ── Source 2: Fetch squads for each season in the window ──
    seasons_to_fetch = range(season - years + 1, season + 1)
    all_squad_player_ids = set()
    squad_data = []

    for fetch_season in seasons_to_fetch:
        season_squad = _api.get_team_players(parent_api_id, season=fetch_season)
        logger.info(
            'seed_tracked_players: API squad returned %d entries for %s season %d',
            len(season_squad), team.name, fetch_season,
        )
        for entry in season_squad:
            player_info = (entry or {}).get('player') or {}
            pid = player_info.get('id')
            if pid:
                all_squad_player_ids.add(int(pid))
        squad_data.extend(season_squad)

    logger.info(
        'seed_tracked_players: %d unique players across %d seasons for %s',
        len(all_squad_player_ids), len(list(seasons_to_fetch)), team.name,
    )

    journey_svc = JourneySyncService(_api)
    synced = 0
    not_academy = 0

    for entry in squad_data:
        player_info = (entry or {}).get('player') or {}
        pid = player_info.get('id')
        if not pid:
            continue
        pid = int(pid)

        if pid in candidate_ids:
            continue

        age = player_info.get('age')
        if age and int(age) > max_age:
            continue

        existing_journey = PlayerJourney.query.filter_by(player_api_id=pid).first()
        if existing_journey and season in (existing_journey.seasons_synced or []):
            if parent_api_id in (existing_journey.academy_club_ids or []):
                candidate_ids[pid] = existing_journey
            continue

        if sync_journeys:
            try:
                journey = journey_svc.sync_player(pid)
                synced += 1
                if journey and parent_api_id in (journey.academy_club_ids or []):
                    candidate_ids[pid] = journey
                elif pid not in candidate_ids:
                    # Transfer-based fallback for clubs without youth league data
                    # (e.g., Serie A, La Liga, Ligue 1 clubs whose youth teams
                    # aren't in API-Football as separate entries)
                    age = player_info.get('age')
                    if age and int(age) <= 22:
                        was_bought = False
                        try:
                            transfers_resp = _api.get_player_transfers(pid)
                            for tentry in (transfers_resp or []):
                                for xfer in tentry.get('transfers', []):
                                    teams_in = xfer.get('teams', {}).get('in', {})
                                    xfer_type = (xfer.get('type') or '').strip().lower()
                                    if teams_in.get('id') == parent_api_id and xfer_type not in (
                                        'loan', 'back from loan', 'return from loan',
                                        'end of loan', 'loan end', 'loan return',
                                    ):
                                        was_bought = True
                                        break
                                if was_bought:
                                    break
                        except Exception:
                            pass
                        if not was_bought:
                            candidate_ids[pid] = journey
                            logger.info('seed: transfer-fallback accepted %d (%s) age %s for %s',
                                        pid, player_info.get('name'), age, team.name)
                        else:
                            not_academy += 1
                    else:
                        not_academy += 1
            except Exception as sync_err:
                logger.warning('seed: journey sync failed for %d: %s', pid, sync_err)
        else:
            journey = PlayerJourney.query.filter_by(player_api_id=pid).first()
            if journey and parent_api_id in (journey.academy_club_ids or []):
                candidate_ids[pid] = journey

    # ── Source 3: CohortMember records (via AcademyCohort) ──
    try:
        from src.models.cohort import AcademyCohort, CohortMember
        cohort_ids = [c.id for c in AcademyCohort.query.filter_by(
            team_api_id=parent_api_id
        ).filter(
            AcademyCohort.sync_status != 'duplicate'
        ).all()]
        if cohort_ids:
            cohort_members = CohortMember.query.filter(
                CohortMember.cohort_id.in_(cohort_ids)
            ).all()
            for cm in cohort_members:
                if cm.player_api_id and cm.player_api_id not in candidate_ids:
                    journey = PlayerJourney.query.filter_by(
                        player_api_id=cm.player_api_id
                    ).first()
                    if journey and parent_api_id in (journey.academy_club_ids or []):
                        candidate_ids[cm.player_api_id] = journey
            logger.info(
                'seed_tracked_players: %d cohort members across %d cohorts for api_id=%s',
                len(cohort_members), len(cohort_ids), parent_api_id,
            )
        else:
            logger.info('seed_tracked_players: no cohorts found for api_id=%s', parent_api_id)
    except Exception as cohort_err:
        logger.warning('seed: cohort lookup failed: %s', cohort_err)

    # ── Build a lookup of squad player info for enrichment ──
    squad_by_id = {}
    for entry in squad_data:
        pi = (entry or {}).get('player') or {}
        if pi.get('id'):
            squad_by_id[int(pi['id'])] = entry

    # ── Create TrackedPlayer rows ──
    created = 0
    skipped = 0
    errors = []

    for pid, journey in candidate_ids.items():
        try:
            existing = TrackedPlayer.query.filter_by(
                player_api_id=pid, team_id=team_id,
            ).first()
            if existing:
                new_status, new_loan_id, new_loan_name = classify_tracked_player(
                    current_club_api_id=journey.current_club_api_id if journey else None,
                    current_club_name=journey.current_club_name if journey else None,
                    current_level=journey.current_level if journey else None,
                    parent_api_id=parent_api_id,
                    parent_club_name=team.name,
                    player_api_id=pid,
                    api_client=_api,
                    latest_season=_get_latest_season(journey.id, parent_api_id=parent_api_id, parent_club_name=team.name) if journey else None,
                )
                if existing.status != new_status or existing.current_club_api_id != new_loan_id:
                    existing.status = new_status
                    existing.current_club_api_id = new_loan_id
                    existing.current_club_name = new_loan_name
                skipped += 1
                continue

            squad_entry = squad_by_id.get(pid) or {}
            pi = squad_entry.get('player') or {}
            stats_list = squad_entry.get('statistics') or []

            player_name = (
                (journey.player_name if journey else None)
                or pi.get('name')
                or f'Player {pid}'
            )
            photo_url = (journey.player_photo if journey else None) or pi.get('photo')
            nationality = (journey.nationality if journey else None) or pi.get('nationality')
            birth_date = (journey.birth_date if journey else None) or (pi.get('birth') or {}).get('date')
            position = pi.get('position') or ''
            if not position and stats_list:
                position = (stats_list[0].get('games') or {}).get('position') or ''
            age = pi.get('age')

            status, current_club_api_id, current_club_name = classify_tracked_player(
                current_club_api_id=journey.current_club_api_id if journey else None,
                current_club_name=journey.current_club_name if journey else None,
                current_level=journey.current_level if journey else None,
                parent_api_id=parent_api_id,
                parent_club_name=team.name,
                player_api_id=pid,
                api_client=_api,
                latest_season=_get_latest_season(journey.id, parent_api_id=parent_api_id, parent_club_name=team.name) if journey else None,
            )

            current_level = None
            if journey and journey.current_level:
                current_level = journey.current_level

            tp = TrackedPlayer(
                player_api_id=pid,
                player_name=player_name,
                photo_url=photo_url,
                position=position,
                nationality=nationality,
                birth_date=birth_date,
                age=int(age) if age else None,
                team_id=team_id,
                status=status,
                current_level=current_level,
                current_club_api_id=current_club_api_id,
                current_club_name=current_club_name,
                data_source='api-football',
                data_depth='full_stats',
                journey_id=journey.id if journey else None,
            )
            db.session.add(tp)
            created += 1
        except Exception as entry_err:
            errors.append(f'Player {pid}: {entry_err}')
            logger.warning('seed_tracked_players: error for player %d: %s', pid, entry_err)

    db.session.commit()
    logger.info(
        'seed_tracked_players: done for %s — created=%d, skipped=%d, '
        'candidates=%d, journeys_synced=%d, not_academy=%d',
        team.name, created, skipped, len(candidate_ids), synced, not_academy,
    )
    return {
        'team_id': team_id,
        'team_name': team.name,
        'api_team_id': parent_api_id,
        'season': season,
        'years': years,
        'seasons_fetched': list(seasons_to_fetch),
        'created': created,
        'skipped': skipped,
        'candidates_found': len(candidate_ids),
        'journeys_synced': synced,
        'not_academy': not_academy,
        'unique_squad_players': len(all_squad_player_ids),
        'errors': errors[:10] if errors else [],
    }


# ── Background seed workers ──

def _run_seed_team_process(job_id, team_id, max_age=30, sync_journeys=True, years=4):
    """Background worker: seed TrackedPlayers for one team."""
    import signal
    import sys
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True,
    )
    from src.main import app

    def _sigterm_handler(signum, frame):
        try:
            with app.app_context():
                from src.utils.background_jobs import update_job as _upd
                _upd(job_id, status='failed',
                     error='Process terminated (SIGTERM)',
                     completed_at=datetime.now(timezone.utc).isoformat())
        except Exception:
            pass
        sys.exit(1)

    signal.signal(signal.SIGTERM, _sigterm_handler)

    with app.app_context():
        from src.utils.background_jobs import update_job
        try:
            team = Team.query.get(team_id)
            if not team:
                update_job(job_id, status='failed', error=f'Team {team_id} not found',
                           completed_at=datetime.now(timezone.utc).isoformat())
                return
            update_job(job_id, status='running', progress=0, total=1,
                       current_player=f'Discovering cohorts for {team.name}...')

            # Phase 1: Cohort discovery (youth league data)
            try:
                from src.services.big6_seeding_service import run_big6_seed
                now = datetime.now()
                current_season = now.year if now.month >= 8 else now.year - 1
                run_big6_seed(job_id, seasons=[current_season], team_ids=[team.team_id])
            except Exception as cohort_err:
                logger.warning('Cohort discovery for %s failed (continuing with squad seed): %s',
                               team.name, cohort_err)

            # Phase 2: TrackedPlayer seeding from cohorts + squads
            update_job(job_id, current_player=f'Seeding {team.name}...')
            result = _seed_single_team(team, max_age=max_age,
                                       sync_journeys=sync_journeys, years=years)
            update_job(job_id, status='completed', progress=1, total=1,
                       results=result,
                       completed_at=datetime.now(timezone.utc).isoformat())
        except Exception as e:
            logger.exception('Background seed for team %s failed', team_id)
            db.session.rollback()
            update_job(job_id, status='failed', error=str(e),
                       completed_at=datetime.now(timezone.utc).isoformat())


def _run_seed_teams_process(job_id, team_db_ids, max_age=30, sync_journeys=True, years=4):
    """Background worker: seed a specific list of teams (cohort discovery + TrackedPlayers).

    Unlike _run_seed_all_tracked_process, this processes ALL specified teams
    regardless of existing TrackedPlayer rows — suitable for bulk-tracking
    where re-enabled teams need cohort refresh and player status updates.
    """
    import signal
    import sys
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True,
    )
    from src.main import app

    def _sigterm_handler(signum, frame):
        try:
            with app.app_context():
                from src.utils.background_jobs import update_job as _upd
                _upd(job_id, status='failed',
                     error='Process terminated (SIGTERM)',
                     completed_at=datetime.now(timezone.utc).isoformat())
        except Exception:
            pass
        sys.exit(1)

    signal.signal(signal.SIGTERM, _sigterm_handler)

    with app.app_context():
        from src.utils.background_jobs import update_job, is_job_cancelled
        try:
            if not team_db_ids:
                update_job(job_id, status='completed', progress=0, total=0,
                           results={'teams': {}, 'errors': []},
                           completed_at=datetime.now(timezone.utc).isoformat())
                return

            target_teams = Team.query.filter(Team.id.in_(team_db_ids)).all()
            if not target_teams:
                update_job(job_id, status='completed', progress=0, total=0,
                           results={'teams': {}, 'errors': []},
                           completed_at=datetime.now(timezone.utc).isoformat())
                return

            update_job(job_id, status='running', progress=0, total=len(target_teams))

            # Phase 1: Cohort discovery for all target teams
            try:
                from src.services.big6_seeding_service import run_big6_seed
                now = datetime.now()
                current_season = now.year if now.month >= 8 else now.year - 1
                team_api_ids = [t.team_id for t in target_teams]
                update_job(job_id, current_player='Discovering cohorts...')
                run_big6_seed(job_id, seasons=[current_season], team_ids=team_api_ids)
            except Exception as cohort_err:
                logger.warning('Bulk cohort discovery failed (continuing with squad seed): %s',
                               cohort_err)

            # Phase 2: TrackedPlayer seeding per team
            results = {'teams': {}, 'errors': []}
            for i, team in enumerate(target_teams):
                if is_job_cancelled(job_id):
                    update_job(job_id, status='cancelled',
                               error=f'Cancelled after {i}/{len(target_teams)} teams',
                               results=results,
                               completed_at=datetime.now(timezone.utc).isoformat())
                    return
                update_job(job_id, progress=i, total=len(target_teams),
                           current_player=f'Seeding {team.name}...')
                try:
                    team_result = _seed_single_team(team, max_age=max_age,
                                                     sync_journeys=sync_journeys, years=years)
                    results['teams'][team.name] = {
                        'created': team_result.get('created', 0),
                        'skipped': team_result.get('skipped', 0),
                        'candidates': team_result.get('candidates_found', 0),
                    }
                except Exception as team_err:
                    logger.warning('seed_teams: failed for %s: %s', team.name, team_err)
                    results['errors'].append(f'{team.name}: {team_err}')
            update_job(job_id, status='completed', progress=len(target_teams),
                       total=len(target_teams), results=results,
                       completed_at=datetime.now(timezone.utc).isoformat())
        except Exception as e:
            logger.exception('Background seed-teams failed')
            db.session.rollback()
            update_job(job_id, status='failed', error=str(e),
                       completed_at=datetime.now(timezone.utc).isoformat())


def _run_seed_all_tracked_process(job_id, max_age=30, sync_journeys=True, years=4,
                                   team_db_ids=None):
    """Background worker: seed tracked teams that have no TrackedPlayers.

    If team_db_ids is provided, only those teams are considered (used by
    bulk-tracking auto-seed).  Otherwise all tracked+active teams are used.
    """
    import signal
    import sys
    logging.basicConfig(
        stream=sys.stderr, level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', force=True,
    )
    from src.main import app

    def _sigterm_handler(signum, frame):
        try:
            with app.app_context():
                from src.utils.background_jobs import update_job as _upd
                _upd(job_id, status='failed',
                     error='Process terminated (SIGTERM)',
                     completed_at=datetime.now(timezone.utc).isoformat())
        except Exception:
            pass
        sys.exit(1)

    signal.signal(signal.SIGTERM, _sigterm_handler)

    with app.app_context():
        from src.utils.background_jobs import update_job, is_job_cancelled
        try:
            if team_db_ids:
                teams = Team.query.filter(Team.id.in_(team_db_ids)).all()
            else:
                teams = Team.query.filter_by(is_tracked=True, is_active=True).all()
            empty_teams = [t for t in teams
                           if TrackedPlayer.query.filter_by(team_id=t.id, is_active=True).count() == 0]
            if not empty_teams:
                update_job(job_id, status='completed', progress=0, total=0,
                           results={'teams': {}, 'errors': []},
                           completed_at=datetime.now(timezone.utc).isoformat())
                return

            update_job(job_id, status='running', progress=0, total=len(empty_teams))

            # Phase 1: Cohort discovery for all empty teams
            try:
                from src.services.big6_seeding_service import run_big6_seed
                now = datetime.now()
                current_season = now.year if now.month >= 8 else now.year - 1
                team_api_ids = [t.team_id for t in empty_teams]
                update_job(job_id, current_player='Discovering cohorts for all teams...')
                run_big6_seed(job_id, seasons=[current_season], team_ids=team_api_ids)
            except Exception as cohort_err:
                logger.warning('Bulk cohort discovery failed (continuing with squad seed): %s',
                               cohort_err)

            # Phase 2: TrackedPlayer seeding per team
            results = {'teams': {}, 'errors': []}
            for i, team in enumerate(empty_teams):
                if is_job_cancelled(job_id):
                    update_job(job_id, status='cancelled',
                               error=f'Cancelled after {i}/{len(empty_teams)} teams',
                               results=results,
                               completed_at=datetime.now(timezone.utc).isoformat())
                    return
                update_job(job_id, progress=i, total=len(empty_teams),
                           current_player=f'Seeding {team.name}...')
                try:
                    team_result = _seed_single_team(team, max_age=max_age,
                                                     sync_journeys=sync_journeys, years=years)
                    results['teams'][team.name] = {
                        'created': team_result.get('created', 0),
                        'skipped': team_result.get('skipped', 0),
                        'candidates': team_result.get('candidates_found', 0),
                    }
                except Exception as team_err:
                    logger.warning('seed_all_tracked: failed for %s: %s', team.name, team_err)
                    results['errors'].append(f'{team.name}: {team_err}')
            update_job(job_id, status='completed', progress=len(empty_teams),
                       total=len(empty_teams), results=results,
                       completed_at=datetime.now(timezone.utc).isoformat())
        except Exception as e:
            logger.exception('Background seed-all-tracked failed')
            db.session.rollback()
            update_job(job_id, status='failed', error=str(e),
                       completed_at=datetime.now(timezone.utc).isoformat())


def _start_background_seed(team_id, max_age=30, sync_journeys=True, years=4):
    """Launch a background process to seed TrackedPlayers for a team. Returns job_id."""
    import multiprocessing
    job_id = _create_background_job('seed_team')
    p = multiprocessing.Process(
        target=_run_seed_team_process,
        args=(job_id, team_id),
        kwargs={'max_age': max_age, 'sync_journeys': sync_journeys, 'years': years},
        daemon=False,
    )
    p.start()
    multiprocessing.process._children.discard(p)
    return job_id


@api_bp.route('/admin/tracked-players/seed-team', methods=['POST'])
@require_api_key
def admin_seed_tracked_players():
    """Seed TrackedPlayer records for a team using existing academy identification rules.

    Uses three sources to discover academy players:
      1. PlayerJourney.academy_club_ids — players whose journey data marks this
         club as an academy parent.
      2. API-Football squad — fetches the current squad and runs journey sync for
         each player to determine academy connection.
      3. CohortMember records linked to this team.

    Body: { team_id: int (db id), season?: int, max_age?: int, sync_journeys?: bool }
    """
    try:
        data = request.get_json(force=True)
        team_id = data.get('team_id')
        if not team_id:
            return jsonify({'error': 'team_id is required'}), 400

        team = Team.query.get(team_id)
        if not team:
            return jsonify({'error': 'Team not found'}), 404

        max_age = data.get('max_age', 30)
        sync_journeys = data.get('sync_journeys', True)
        years = data.get('years', 4)
        season = data.get('season')

        result = _seed_single_team(team, max_age=max_age, sync_journeys=sync_journeys,
                                   years=years, season=season)
        return jsonify(result)
    except Exception as e:
        db.session.rollback()
        logger.exception('admin_seed_tracked_players failed')
        return jsonify(_safe_error_payload(e, 'Failed to seed tracked players')), 500


@api_bp.route('/admin/tracked-players/seed-all-tracked', methods=['POST'])
@require_api_key
def admin_seed_all_tracked():
    """Backfill: seed TrackedPlayers for all tracked teams that have none.

    Finds teams with is_tracked=True and 0 active TrackedPlayers, then runs
    the seed logic for each in a single background job.

    Body (all optional): { max_age?: int, sync_journeys?: bool, years?: int }
    """
    try:
        import multiprocessing
        data = request.get_json(force=True) if request.data else {}
        max_age = data.get('max_age', 30)
        sync_journeys = data.get('sync_journeys', True)
        years = data.get('years', 4)

        # Preview which teams would be seeded
        teams = Team.query.filter_by(is_tracked=True, is_active=True).all()
        empty_teams = [t for t in teams
                       if TrackedPlayer.query.filter_by(team_id=t.id, is_active=True).count() == 0]

        if not empty_teams:
            return jsonify({
                'message': 'All tracked teams already have TrackedPlayers',
                'tracked_teams': len(teams),
                'empty_teams': 0,
            })

        job_id = _create_background_job('seed_all_tracked')
        p = multiprocessing.Process(
            target=_run_seed_all_tracked_process,
            args=(job_id,),
            kwargs={'max_age': max_age, 'sync_journeys': sync_journeys, 'years': years},
            daemon=False,
        )
        p.start()
        multiprocessing.process._children.discard(p)

        return jsonify({
            'message': f'Background seed started for {len(empty_teams)} teams',
            'job_id': job_id,
            'tracked_teams': len(teams),
            'teams_to_seed': len(empty_teams),
            'team_names': [t.name for t in empty_teams],
        })
    except Exception as e:
        logger.exception('admin_seed_all_tracked failed')
        db.session.rollback()
        return jsonify(_safe_error_payload(e, 'Failed to start seed-all-tracked')), 500


@api_bp.route('/admin/tracked-players/sync-journeys', methods=['POST'])
@require_api_key
def admin_sync_tracked_player_journeys():
    """Batch-sync PlayerJourney records for TrackedPlayers missing or broken journey data.

    Three passes:
      1. Link pass — if a PlayerJourney already exists for the player_api_id,
         just set TrackedPlayer.journey_id (no API call needed).
      2. Sync pass — for remaining unlinked players, call JourneySyncService.sync_player()
         to fetch career data from API-Football.
      3. Repair pass — re-sync players whose linked journey has sync_error or 0 entries.

    Returns a summary of what was done.
    """
    try:
        from src.models.journey import PlayerJourney, PlayerJourneyEntry
        from src.services.journey_sync import JourneySyncService

        unlinked = TrackedPlayer.query.filter(
            TrackedPlayer.is_active == True,
            TrackedPlayer.journey_id.is_(None),
        ).all()

        linked = 0
        synced = 0
        repaired = 0
        failed = 0
        details = []

        # Pass 1: link existing journeys
        for tp in unlinked:
            journey = PlayerJourney.query.filter_by(player_api_id=tp.player_api_id).first()
            if journey:
                tp.journey_id = journey.id
                linked += 1
                details.append({'player': tp.player_name, 'api_id': tp.player_api_id, 'action': 'linked'})

        db.session.flush()

        # Pass 2: sync missing journeys
        still_missing = [tp for tp in unlinked if tp.journey_id is None]
        service = JourneySyncService()
        for tp in still_missing:
            try:
                journey = service.sync_player(tp.player_api_id)
                if journey:
                    tp.journey_id = journey.id
                    synced += 1
                    details.append({'player': tp.player_name, 'api_id': tp.player_api_id, 'action': 'synced'})
                else:
                    failed += 1
                    details.append({'player': tp.player_name, 'api_id': tp.player_api_id, 'action': 'sync_returned_none'})
            except Exception as sync_err:
                failed += 1
                details.append({'player': tp.player_name, 'api_id': tp.player_api_id, 'action': 'error', 'error': str(sync_err)})
                logger.warning('sync-journeys: failed for %s (%d): %s', tp.player_name, tp.player_api_id, sync_err)

        db.session.flush()

        # Pass 3: repair broken journeys (sync_error or 0 entries)
        journeys_with_entries = db.session.query(
            PlayerJourneyEntry.journey_id
        ).distinct().subquery()

        broken_linked = TrackedPlayer.query.filter(
            TrackedPlayer.is_active == True,
            TrackedPlayer.journey_id.isnot(None),
        ).join(PlayerJourney, TrackedPlayer.journey_id == PlayerJourney.id).filter(
            db.or_(
                PlayerJourney.sync_error.isnot(None),
                ~PlayerJourney.id.in_(
                    db.session.query(journeys_with_entries.c.journey_id)
                ),
            )
        ).all()

        # Deduplicate by player_api_id to avoid redundant API calls
        seen_pids = set()
        unique_broken = []
        for tp in broken_linked:
            if tp.player_api_id not in seen_pids:
                seen_pids.add(tp.player_api_id)
                unique_broken.append(tp)

        for tp in unique_broken:
            try:
                journey = service.sync_player(tp.player_api_id, force_full=True)
                if journey:
                    repaired += 1
                    details.append({'player': tp.player_name, 'api_id': tp.player_api_id, 'action': 'repaired'})
                else:
                    failed += 1
                    details.append({'player': tp.player_name, 'api_id': tp.player_api_id, 'action': 'repair_returned_none'})
            except Exception as sync_err:
                failed += 1
                details.append({'player': tp.player_name, 'api_id': tp.player_api_id, 'action': 'repair_error', 'error': str(sync_err)})
                logger.warning('sync-journeys: repair failed for %s (%d): %s', tp.player_name, tp.player_api_id, sync_err)

        db.session.commit()
        return jsonify({
            'total_unlinked': len(unlinked),
            'total_broken': len(unique_broken),
            'linked': linked,
            'synced': synced,
            'repaired': repaired,
            'failed': failed,
            'details': details,
        })
    except Exception as e:
        db.session.rollback()
        logger.exception('admin_sync_tracked_player_journeys failed')
        return jsonify(_safe_error_payload(e, 'Failed to sync journeys')), 500


# ====================================================================
# Public: Team Players
# ====================================================================

@api_bp.route('/teams/<team_identifier>/players', methods=['GET'])
def get_team_players(team_identifier):
    """Return tracked players for a team in loan-compatible shape (public endpoint)."""
    try:
        team = resolve_team_by_identifier(team_identifier)
        team_id = team.id

        from src.utils.academy_classifier import is_academy_product

        all_tracked = TrackedPlayer.query.filter_by(
            team_id=team_id,
            is_active=True,
        ).order_by(TrackedPlayer.player_name).all()

        # Filter to academy products only
        players = [
            tp for tp in all_tracked
            if is_academy_product(tp.player_api_id, team.team_id, data_source=tp.data_source, birth_date=tp.birth_date)
        ]

        # Batch-compute parent club appearances from journey entries
        from src.models.journey import PlayerJourneyEntry
        journey_ids = [tp.journey_id for tp in players if tp.journey_id]
        parent_club_apps = {}
        if journey_ids:
            # Get all non-international entries for these journeys
            all_entries = PlayerJourneyEntry.query.filter(
                PlayerJourneyEntry.journey_id.in_(journey_ids),
                PlayerJourneyEntry.entry_type != 'international',
            ).all()
            for entry in all_entries:
                # Count entries at parent club (by API ID or youth-suffix name match)
                if entry.club_api_id == team.team_id or is_same_club(entry.club_name or '', team.name):
                    parent_club_apps[entry.journey_id] = parent_club_apps.get(entry.journey_id, 0) + (entry.appearances or 0)

        # Batch-compute loan stats from FixturePlayerStats (1 query)
        from src.models.weekly import FixturePlayerStats
        from sqlalchemy import func as sa_func

        player_api_ids_on_loan = [tp.player_api_id for tp in players if tp.current_club_api_id]
        player_stats_map = {}
        if player_api_ids_on_loan:
            stats_rows = db.session.query(
                FixturePlayerStats.player_api_id,
                sa_func.count().label('appearances'),
                sa_func.coalesce(sa_func.sum(FixturePlayerStats.goals), 0).label('goals'),
                sa_func.coalesce(sa_func.sum(FixturePlayerStats.assists), 0).label('assists'),
                sa_func.coalesce(sa_func.sum(FixturePlayerStats.minutes), 0).label('minutes_played'),
                sa_func.coalesce(sa_func.sum(FixturePlayerStats.saves), 0).label('saves'),
                sa_func.coalesce(sa_func.sum(FixturePlayerStats.yellows), 0).label('yellows'),
                sa_func.coalesce(sa_func.sum(FixturePlayerStats.reds), 0).label('reds'),
            ).filter(
                FixturePlayerStats.player_api_id.in_(player_api_ids_on_loan),
            ).group_by(FixturePlayerStats.player_api_id).all()

            for row in stats_rows:
                player_stats_map[row.player_api_id] = {
                    'appearances': row.appearances or 0,
                    'goals': int(row.goals or 0),
                    'assists': int(row.assists or 0),
                    'minutes_played': int(row.minutes_played or 0),
                    'saves': int(row.saves or 0),
                    'yellows': int(row.yellows or 0),
                    'reds': int(row.reds or 0),
                }

        # Batch-fetch Player records for photo and position enrichment (1 query)
        all_player_api_ids = [tp.player_api_id for tp in players]
        player_records_map = {}
        if all_player_api_ids:
            player_records = Player.query.filter(Player.player_id.in_(all_player_api_ids)).all()
            player_records_map = {pr.player_id: pr for pr in player_records}

        # Batch-fetch position from FixturePlayerStats as final fallback (1 query)
        players_needing_pos = [
            tp for tp in players
            if not tp.position and not getattr(player_records_map.get(tp.player_api_id), 'position', None)
        ]
        fps_position_map = {}
        if players_needing_pos:
            pos_api_ids = [tp.player_api_id for tp in players_needing_pos]
            pos_rows = db.session.query(
                FixturePlayerStats.player_api_id,
                FixturePlayerStats.position,
            ).filter(
                FixturePlayerStats.player_api_id.in_(pos_api_ids),
                FixturePlayerStats.position.isnot(None),
            ).distinct().all()
            for row in pos_rows:
                fps_position_map.setdefault(row.player_api_id, row.position)

        # Batch-compute parent club minutes for first-team tier split (1 query)
        ESTABLISHED_MIN_MINUTES = 500
        ESTABLISHED_MIN_APPEARANCES = 10
        first_team_player_ids = [tp.player_api_id for tp in players if tp.status == 'first_team']
        parent_minutes_map = {}
        if first_team_player_ids:
            mins_rows = db.session.query(
                FixturePlayerStats.player_api_id,
                sa_func.count().label('apps'),
                sa_func.coalesce(sa_func.sum(FixturePlayerStats.minutes), 0).label('mins'),
            ).filter(
                FixturePlayerStats.player_api_id.in_(first_team_player_ids),
                FixturePlayerStats.team_api_id == team.team_id,
            ).group_by(FixturePlayerStats.player_api_id).all()
            for row in mins_rows:
                parent_minutes_map[row.player_api_id] = {
                    'apps': row.apps, 'mins': int(row.mins or 0)
                }

        # Batch-fetch loan team logos (1 query)
        current_club_api_ids = list({tp.current_club_api_id for tp in players if tp.current_club_api_id})
        loan_team_logos = {}
        if current_club_api_ids:
            loan_teams = Team.query.filter(Team.team_id.in_(current_club_api_ids)).all()
            loan_team_logos = {lt.team_id: lt.logo for lt in loan_teams}

        # Build results with batch-enriched data
        results = []
        for tp in players:
            d = tp.to_public_dict()
            d['parent_club_appearances'] = parent_club_apps.get(tp.journey_id, 0)

            # First-team tier split: academy (0 apps) / debut / established
            if tp.status == 'first_team':
                pm = parent_minutes_map.get(tp.player_api_id, {})
                parent_apps = pm.get('apps', 0)
                parent_mins = pm.get('mins', 0)
                if parent_apps == 0 and parent_mins == 0:
                    # Registered but never played — still academy
                    d['status'] = 'academy'
                    d['pathway_status'] = 'academy'
                elif (parent_mins < ESTABLISHED_MIN_MINUTES
                        and parent_apps < ESTABLISHED_MIN_APPEARANCES):
                    d['status'] = 'first_team_debut'
                    d['pathway_status'] = 'first_team_debut'

            # Enrich stats from batch query
            if tp.player_api_id in player_stats_map:
                d.update(player_stats_map[tp.player_api_id])

            # Enrich photo and position from Player table
            pr = player_records_map.get(tp.player_api_id)
            if pr:
                if not d.get('player_photo') and pr.photo_url:
                    d['player_photo'] = pr.photo_url
                if not d.get('position') and pr.position:
                    d['position'] = pr.position

            # Final fallback: position from FixturePlayerStats (G/D/M/F)
            if not d.get('position'):
                fps_pos = fps_position_map.get(tp.player_api_id)
                if fps_pos:
                    POSITION_MAP = {'G': 'Goalkeeper', 'D': 'Defender', 'M': 'Midfielder', 'F': 'Attacker'}
                    d['position'] = POSITION_MAP.get(fps_pos, fps_pos)

            # Fill in loan team logo
            if tp.current_club_api_id:
                logo = loan_team_logos.get(tp.current_club_api_id)
                if logo:
                    d['loan_team_logo'] = logo

            # Enrich with international honors from journey entries
            # Use entry_type='international' to get actual national team duty,
            # not club entries in international competitions (e.g. Arsenal in UEFA Youth League)
            if tp.journey_id:
                from src.models.journey import PlayerJourneyEntry
                intl_entries = PlayerJourneyEntry.query.filter_by(
                    journey_id=tp.journey_id,
                    entry_type='international',
                ).all()
                if intl_entries:
                    # Group by national team, pick the highest level one
                    teams_map = {}
                    for ie in intl_entries:
                        key = ie.club_api_id
                        if key not in teams_map:
                            teams_map[key] = {
                                'team': ie.club_name,
                                'logo': ie.club_logo,
                                'caps': 0,
                                'level': ie.level,
                            }
                        teams_map[key]['caps'] += ie.appearances or 0
                        # Prefer senior level over youth
                        if ie.level == 'International':
                            teams_map[key]['level'] = 'International'
                    # Return only the highest-level national team
                    level_rank = {'International': 2, 'International Youth': 1}
                    best = max(teams_map.values(), key=lambda t: (level_rank.get(t['level'], 0), t['caps']))
                    d['international_team'] = best['team']
                    d['international_caps'] = best['caps']
                    d['international_logo'] = best['logo']

            results.append(d)

        return jsonify({
            'team': {
                'id': team.id,
                'team_id': team.team_id,
                'name': team.name,
                'logo': team.logo,
            },
            'players': results,
            'total': len(results),
        })
    except Exception as e:
        logger.exception('get_team_players failed')
        return jsonify(_safe_error_payload(e, 'Failed to fetch team players')), 500
