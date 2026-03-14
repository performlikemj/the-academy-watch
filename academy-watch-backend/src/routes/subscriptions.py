"""Subscription management endpoints for newsletter subscriptions.

This blueprint handles all subscription-related operations including:
- Creating and managing subscriptions
- Unsubscribe flows (token-based, one-click)
- Subscription management via email tokens
"""

import json
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from flask import Blueprint, g, jsonify, render_template, request
from werkzeug.exceptions import NotFound

from src.auth import require_api_key, require_user_auth, _get_authorized_email, _safe_error_payload
from src.models.league import (
    db,
    Team,
    UserSubscription,
    EmailToken,
)

logger = logging.getLogger(__name__)

subscriptions_bp = Blueprint('subscriptions', __name__)

# Configuration - read dynamically to support testing
def _subscriptions_require_verify() -> bool:
    """Check if subscription verification is required."""
    return os.getenv('SUBSCRIPTIONS_REQUIRE_VERIFY', '1').lower() in ('1', 'true', 'yes', 'on')


def _subscriptions_verify_ttl_minutes() -> int:
    """Get TTL for subscription verification tokens."""
    try:
        return int(os.getenv('SUBSCRIPTIONS_VERIFY_TTL_MINUTES') or 60 * 24)
    except ValueError:
        return 60 * 24


def _get_email_service():
    """Lazy import of email service to avoid circular imports."""
    from src.services.email_service import email_service
    return email_service


def _send_email_via_service(
    *,
    email: str,
    subject: str,
    text: str,
    html: str | None = None,
    meta: dict | None = None,
) -> dict:
    """Send email via email service (Mailgun/SMTP)."""
    email_service = _get_email_service()
    if not email_service.is_configured():
        raise RuntimeError('Email service is not configured (set MAILGUN_* or SMTP_* env vars)')

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
    """Send verification email for subscription confirmation."""
    public_base = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    confirm_path = f"/verify?token={token}"
    confirm_url = f"{public_base}{confirm_path}" if public_base else confirm_path

    subject = "Confirm your newsletter subscription"

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
    return _send_email_via_service(email=email, subject=subject, text=text, html=html, meta=meta)


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
    return _send_email_via_service(email=email, subject=subject, text=text, html=html, meta=meta)


def _create_email_token(email: str, purpose: str, metadata: dict | None = None, ttl_minutes: int = 60) -> EmailToken:
    """Create a new email token for verification or management."""
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


def _activate_subscriptions(email: str, team_ids: list[int], preferred_frequency: str = 'weekly') -> dict[str, Any]:
    """Activate or create subscriptions for the given teams."""
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
    """Process subscription request, potentially requiring email verification."""
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

    if _subscriptions_require_verify():
        try:
            token_row = _create_email_token(
                email=email,
                purpose='subscribe_confirm',
                metadata={'team_ids': valid_ids, 'preferred_frequency': preferred_frequency},
                ttl_minutes=_subscriptions_verify_ttl_minutes(),
            )
            db.session.flush()
            _send_subscription_verification_email(email, team_names, token_row.token)
            db.session.commit()
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
    status = 201 if result['created_count'] else 200
    return result, status


def _unsubscribe_subscription_by_token(token: str) -> tuple[UserSubscription | None, str, int]:
    """Unsubscribe a subscription by its unsubscribe token."""
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
        return sub, 'unsubscribed', 200

    return sub, 'already_unsubscribed', 200


def _public_manage_url() -> str | None:
    """Get the public URL for the manage subscriptions page."""
    base = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    if not base:
        return None
    manage_path = os.getenv('PUBLIC_MANAGE_PATH', '/manage')
    return f"{base}{manage_path}"


# ============================================================
# User-authenticated subscription endpoints
# ============================================================

@subscriptions_bp.route('/subscriptions/me', methods=['GET'])
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


@subscriptions_bp.route('/subscriptions/me', methods=['POST'])
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


# ============================================================
# Admin subscription endpoints
# ============================================================

@subscriptions_bp.route('/subscriptions', methods=['GET'])
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


# ============================================================
# Public subscription endpoints
# ============================================================

@subscriptions_bp.route('/subscriptions', methods=['POST'])
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


@subscriptions_bp.route('/subscriptions/bulk_create', methods=['POST'])
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


@subscriptions_bp.route('/subscriptions/request-manage-link', methods=['POST'])
def request_manage_link():
    """Issue a one-time manage token emailed to the user."""
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


@subscriptions_bp.route('/subscriptions/manage/<token>', methods=['GET'])
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


@subscriptions_bp.route('/subscriptions/manage/<token>', methods=['POST'])
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

        db.session.commit()
        return jsonify({'message': 'Subscriptions updated'})
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@subscriptions_bp.route('/subscriptions/unsubscribe', methods=['POST'])
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
        for sub in subs:
            if sub.active:
                sub.active = False
                count += 1
        db.session.commit()
        return jsonify({'message': 'Unsubscribed successfully', 'count': count})
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500


@subscriptions_bp.route('/subscriptions/unsubscribe/<token>', methods=['GET', 'POST'])
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


@subscriptions_bp.route('/subscriptions/one-click-unsubscribe/<token>', methods=['POST'])
def one_click_unsubscribe(token: str):
    """RFC 8058 One-Click Unsubscribe endpoint for email clients.

    This endpoint is designed for email providers (Gmail, Yahoo, etc.) that
    implement one-click unsubscribe via the List-Unsubscribe-Post header.

    The email client sends a POST request with body: List-Unsubscribe=One-Click

    Returns 200 on success (required by RFC 8058).
    """
    try:
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


@subscriptions_bp.route('/subscriptions/<int:subscription_id>', methods=['DELETE'])
def delete_subscription(subscription_id):
    """Unsubscribe from newsletter by subscription ID."""
    try:
        subscription = UserSubscription.query.get_or_404(subscription_id)
        subscription.active = False
        db.session.commit()

        return jsonify({'message': 'Unsubscribed successfully'})
    except NotFound:
        raise
    except Exception as e:
        return jsonify(_safe_error_payload(e, 'An unexpected error occurred. Please try again later.')), 500
