"""
Admin Notification Service

Sends lightweight email notifications to the admin when key user actions occur.
Uses the existing Mailgun-based email_service in a background thread so
user-facing requests are never slowed down.

All public functions are fire-and-forget: failures are logged, never propagated.
"""

import logging
import os
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _get_admin_email() -> str | None:
    """Return the first email from ADMIN_EMAILS env var, or None."""
    raw = os.getenv('ADMIN_EMAILS') or ''
    emails = [e.strip().lower() for e in raw.split(',') if e.strip()]
    return emails[0] if emails else None


def _mask_email(email: str) -> str:
    """Mask an email for use in subject lines: jo***@gmail.com"""
    if not email or '@' not in email:
        return email or ''
    local, domain = email.rsplit('@', 1)
    if len(local) <= 2:
        masked = local[0] + '***'
    else:
        masked = local[:2] + '***'
    return f'{masked}@{domain}'


def _notify_in_background(subject: str, text: str, html: str) -> None:
    """Send an admin notification email in a background thread."""
    admin_email = _get_admin_email()
    if not admin_email:
        logger.debug('Admin notification skipped: ADMIN_EMAILS not configured')
        return

    from src.services.email_service import email_service
    app = email_service._app

    def _send():
        try:
            ctx = app.app_context() if app else None
            if ctx:
                with ctx:
                    email_service.send_email(
                        to=admin_email,
                        subject=subject,
                        html=html,
                        text=text,
                        tags=['admin-notification'],
                    )
            else:
                email_service.send_email(
                    to=admin_email,
                    subject=subject,
                    html=html,
                    text=text,
                    tags=['admin-notification'],
                )
        except Exception:
            logger.exception('Failed to send admin notification: %s', subject)

    thread = threading.Thread(target=_send, daemon=True)
    thread.start()


def _simple_html(body_lines: list[str]) -> str:
    """Wrap body lines in minimal HTML for admin emails."""
    body = ''.join(f'<p style="margin:4px 0">{line}</p>' for line in body_lines)
    return (
        f'<div style="font-family:sans-serif;font-size:14px;color:#333;max-width:500px">'
        f'{body}'
        f'<hr style="margin-top:20px;border:none;border-top:1px solid #ddd">'
        f'<p style="font-size:12px;color:#999">Automated admin notification from Academy Watch</p>'
        f'</div>'
    )


# ── Public notification functions ──────────────────────────────


def notify_new_user(email: str, display_name: str | None = None) -> None:
    """Notify admin that a new user account was created."""
    try:
        subject = f'[Academy Watch] New user: {_mask_email(email)}'
        name_line = f'Display name: {display_name}' if display_name else 'Display name: (not yet set)'
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

        text = (
            f'New user account created on Academy Watch.\n\n'
            f'Email: {email}\n'
            f'{name_line}\n'
            f'Time: {now}\n'
        )
        html = _simple_html([
            '<strong>New user account created</strong>',
            f'Email: {email}',
            name_line,
            f'Time: {now}',
        ])
        _notify_in_background(subject, text, html)
    except Exception:
        logger.exception('notify_new_user failed for %s', email)


def notify_subscription_change(
    email: str,
    team_names: list[str],
    created: int = 0,
    reactivated: int = 0,
    deactivated: int = 0,
) -> None:
    """Notify admin when a user creates or changes subscriptions."""
    try:
        subject = f'[Academy Watch] Subscription update: {_mask_email(email)}'
        teams_str = ', '.join(team_names) if team_names else '(none)'
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

        parts = []
        if created:
            parts.append(f'{created} new')
        if reactivated:
            parts.append(f'{reactivated} reactivated')
        if deactivated:
            parts.append(f'{deactivated} deactivated')
        action_summary = ', '.join(parts) if parts else 'no changes'

        text = (
            f'Subscription update on Academy Watch.\n\n'
            f'Email: {email}\n'
            f'Teams: {teams_str}\n'
            f'Changes: {action_summary}\n'
            f'Time: {now}\n'
        )
        html = _simple_html([
            '<strong>Subscription update</strong>',
            f'Email: {email}',
            f'Teams: {teams_str}',
            f'Changes: {action_summary}',
            f'Time: {now}',
        ])
        _notify_in_background(subject, text, html)
    except Exception:
        logger.exception('notify_subscription_change failed for %s', email)


def notify_tracking_request(team_name: str, email: str | None = None, reason: str | None = None) -> None:
    """Notify admin when someone requests tracking for a team."""
    try:
        subject = f'[Academy Watch] Tracking request: {team_name}'
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

        lines = [f'Team: {team_name}']
        if email:
            lines.append(f'Contact email: {email}')
        if reason:
            lines.append(f'Reason: {reason}')
        lines.append(f'Time: {now}')

        text = 'New tracking request on Academy Watch.\n\n' + '\n'.join(lines) + '\n'
        html = _simple_html(['<strong>New tracking request</strong>'] + lines)
        _notify_in_background(subject, text, html)
    except Exception:
        logger.exception('notify_tracking_request failed for %s', team_name)


def notify_unsubscribe(email: str, team_name: str | None = None) -> None:
    """Notify admin when a user unsubscribes."""
    try:
        subject = f'[Academy Watch] Unsubscribe: {_mask_email(email)}'
        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')

        lines = [f'Email: {email}']
        if team_name:
            lines.append(f'Team: {team_name}')
        lines.append(f'Time: {now}')

        text = 'User unsubscribed on Academy Watch.\n\n' + '\n'.join(lines) + '\n'
        html = _simple_html(['<strong>User unsubscribed</strong>'] + lines)
        _notify_in_background(subject, text, html)
    except Exception:
        logger.exception('notify_unsubscribe failed for %s', email)
