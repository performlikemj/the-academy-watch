"""
Email Service Module

Provides direct email sending via Mailgun API (primary) with SMTP fallback.
Replaces n8n webhook-based email delivery for cost savings.

Usage:
    from src.services.email_service import email_service
    
    # Synchronous send
    result = email_service.send_email(
        to="user@example.com",
        subject="Hello",
        html="<p>Hello World</p>",
        text="Hello World"
    )
    
    # Background send (non-blocking)
    job_id = email_service.send_email_background(
        to=["user1@example.com", "user2@example.com"],
        subject="Newsletter",
        html=html_content,
        text=text_content
    )
"""

import logging
import os
import smtplib
import threading
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Union
from uuid import uuid4

import requests

logger = logging.getLogger(__name__)


@dataclass
class EmailResult:
    """Result of an email send attempt."""
    success: bool
    provider: str
    message_id: Optional[str] = None
    error: Optional[str] = None
    http_status: Optional[int] = None
    
    def to_dict(self) -> dict:
        return {
            'success': self.success,
            'provider': self.provider,
            'message_id': self.message_id,
            'error': self.error,
            'http_status': self.http_status,
        }


class EmailProvider(ABC):
    """Abstract base class for email providers."""
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name for logging."""
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """Check if provider has required configuration."""
        pass
    
    @abstractmethod
    def send(
        self,
        to: Union[str, List[str]],
        subject: str,
        html: str,
        text: str,
        from_name: Optional[str] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> EmailResult:
        """Send an email. Returns EmailResult."""
        pass


class MailgunProvider(EmailProvider):
    """Send emails via Mailgun HTTP API."""
    
    @property
    def name(self) -> str:
        return 'mailgun'
    
    def is_configured(self) -> bool:
        return bool(
            os.getenv('MAILGUN_API_KEY') and 
            os.getenv('MAILGUN_DOMAIN')
        )
    
    def send(
        self,
        to: Union[str, List[str]],
        subject: str,
        html: str,
        text: str,
        from_name: Optional[str] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> EmailResult:
        api_key = os.getenv('MAILGUN_API_KEY')
        domain = os.getenv('MAILGUN_DOMAIN')
        api_url = os.getenv('MAILGUN_API_URL', 'https://api.mailgun.net/v3').rstrip('/')
        
        if not api_key or not domain:
            return EmailResult(
                success=False,
                provider=self.name,
                error='Mailgun not configured (missing API_KEY or DOMAIN)',
            )
        
        # Build from address
        default_from_name = os.getenv('EMAIL_FROM_NAME', 'The Academy Watch')
        default_from_email = os.getenv('EMAIL_FROM_ADDRESS', f'no-reply@{domain}')
        from_name = from_name or default_from_name
        from_email = from_email or default_from_email
        from_addr = f"{from_name} <{from_email}>"
        
        # Normalize recipients to list
        recipients = [to] if isinstance(to, str) else list(to)
        
        # Build request data
        data = {
            'from': from_addr,
            'to': recipients,
            'subject': subject,
            'text': text,
            'html': html,
        }
        
        if reply_to:
            data['h:Reply-To'] = reply_to
        
        if tags:
            data['o:tag'] = tags
        
        url = f"{api_url}/{domain}/messages"
        
        try:
            response = requests.post(
                url,
                auth=('api', api_key),
                data=data,
                timeout=30,
            )
            
            if response.ok:
                result_data = response.json()
                return EmailResult(
                    success=True,
                    provider=self.name,
                    message_id=result_data.get('id'),
                    http_status=response.status_code,
                )
            else:
                error_msg = response.text[:500] if response.text else f'HTTP {response.status_code}'
                logger.warning(
                    'Mailgun API error: status=%s body=%s',
                    response.status_code,
                    error_msg,
                )
                return EmailResult(
                    success=False,
                    provider=self.name,
                    error=error_msg,
                    http_status=response.status_code,
                )
                
        except requests.exceptions.Timeout:
            logger.error('Mailgun API timeout')
            return EmailResult(
                success=False,
                provider=self.name,
                error='Request timeout',
            )
        except requests.exceptions.RequestException as e:
            logger.exception('Mailgun API request failed')
            return EmailResult(
                success=False,
                provider=self.name,
                error=str(e),
            )


class SMTPProvider(EmailProvider):
    """Send emails via SMTP (fallback provider)."""
    
    @property
    def name(self) -> str:
        return 'smtp'
    
    def is_configured(self) -> bool:
        return bool(
            os.getenv('SMTP_HOST') and
            os.getenv('SMTP_USERNAME') and
            os.getenv('SMTP_PASSWORD')
        )
    
    def send(
        self,
        to: Union[str, List[str]],
        subject: str,
        html: str,
        text: str,
        from_name: Optional[str] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        tags: Optional[List[str]] = None,  # Not used for SMTP but kept for interface
    ) -> EmailResult:
        host = os.getenv('SMTP_HOST')
        port = int(os.getenv('SMTP_PORT', '587'))
        username = os.getenv('SMTP_USERNAME')
        password = os.getenv('SMTP_PASSWORD')
        use_tls = os.getenv('SMTP_USE_TLS', 'true').lower() in ('true', '1', 'yes')
        
        if not host or not username or not password:
            return EmailResult(
                success=False,
                provider=self.name,
                error='SMTP not configured (missing HOST, USERNAME, or PASSWORD)',
            )
        
        # Build from address
        default_from_name = os.getenv('EMAIL_FROM_NAME', 'The Academy Watch')
        default_from_email = os.getenv('EMAIL_FROM_ADDRESS', f'no-reply@theacademywatch.com')
        from_name = from_name or default_from_name
        from_email = from_email or default_from_email
        from_addr = f"{from_name} <{from_email}>"
        
        # Normalize recipients
        recipients = [to] if isinstance(to, str) else list(to)
        
        # Build MIME message
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_addr
        msg['To'] = ', '.join(recipients)
        
        if reply_to:
            msg['Reply-To'] = reply_to
        
        # Attach text and HTML parts
        part_text = MIMEText(text, 'plain', 'utf-8')
        part_html = MIMEText(html, 'html', 'utf-8')
        msg.attach(part_text)
        msg.attach(part_html)
        
        try:
            if use_tls:
                server = smtplib.SMTP(host, port, timeout=30)
                server.starttls()
            else:
                server = smtplib.SMTP_SSL(host, port, timeout=30)
            
            server.login(username, password)
            server.sendmail(from_email, recipients, msg.as_string())
            server.quit()
            
            # Generate a pseudo message ID for tracking
            message_id = f"<smtp-{uuid4().hex[:16]}@{from_email.split('@')[-1]}>"
            
            return EmailResult(
                success=True,
                provider=self.name,
                message_id=message_id,
            )
            
        except smtplib.SMTPAuthenticationError as e:
            logger.error('SMTP authentication failed: %s', e)
            return EmailResult(
                success=False,
                provider=self.name,
                error=f'Authentication failed: {e}',
            )
        except smtplib.SMTPException as e:
            logger.exception('SMTP error')
            return EmailResult(
                success=False,
                provider=self.name,
                error=str(e),
            )
        except Exception as e:
            logger.exception('SMTP unexpected error')
            return EmailResult(
                success=False,
                provider=self.name,
                error=str(e),
            )


class EmailService:
    """
    Email service with automatic fallback.
    
    Primary: Mailgun API
    Fallback: SMTP
    
    Includes retry logic and background sending via BackgroundJob.
    """
    
    def __init__(self):
        self.mailgun = MailgunProvider()
        self.smtp = SMTPProvider()
        self._app = None
    
    def init_app(self, app):
        """Initialize with Flask app for background job context."""
        self._app = app
    
    @property
    def primary_provider(self) -> EmailProvider:
        """Get the primary (Mailgun) provider."""
        return self.mailgun
    
    @property
    def fallback_provider(self) -> EmailProvider:
        """Get the fallback (SMTP) provider."""
        return self.smtp
    
    def is_configured(self) -> bool:
        """Check if at least one provider is configured."""
        return self.mailgun.is_configured() or self.smtp.is_configured()
    
    def get_status(self) -> dict:
        """Get configuration status of all providers."""
        return {
            'mailgun_configured': self.mailgun.is_configured(),
            'smtp_configured': self.smtp.is_configured(),
            'any_configured': self.is_configured(),
        }
    
    def send_email(
        self,
        to: Union[str, List[str]],
        subject: str,
        html: str,
        text: str,
        from_name: Optional[str] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        tags: Optional[List[str]] = None,
        use_fallback: bool = True,
        max_retries: int = 1,
    ) -> EmailResult:
        """
        Send an email synchronously.
        
        Attempts Mailgun first, retries once on failure, then falls back to SMTP.
        
        Args:
            to: Recipient email(s)
            subject: Email subject
            html: HTML body
            text: Plain text body
            from_name: Sender name (optional, uses env default)
            from_email: Sender email (optional, uses env default)
            reply_to: Reply-to address (optional)
            tags: Tags for tracking (Mailgun only)
            use_fallback: Whether to try SMTP if Mailgun fails
            max_retries: Number of retries per provider
        
        Returns:
            EmailResult with success status and details
        """
        recipients = [to] if isinstance(to, str) else list(to)
        
        # Mask email in logs for privacy
        masked_recipients = [self._mask_email(r) for r in recipients]
        logger.info(
            'Sending email: to=%s subject=%s',
            masked_recipients,
            subject[:50],
        )
        
        # Try primary provider (Mailgun)
        if self.mailgun.is_configured():
            for attempt in range(max_retries + 1):
                result = self.mailgun.send(
                    to=to,
                    subject=subject,
                    html=html,
                    text=text,
                    from_name=from_name,
                    from_email=from_email,
                    reply_to=reply_to,
                    tags=tags,
                )
                
                if result.success:
                    logger.info(
                        'Email sent via Mailgun: to=%s message_id=%s',
                        masked_recipients,
                        result.message_id,
                    )
                    return result
                
                # Don't retry on 4xx errors (client errors)
                if result.http_status and 400 <= result.http_status < 500:
                    logger.warning(
                        'Mailgun client error (no retry): status=%s error=%s',
                        result.http_status,
                        result.error,
                    )
                    break
                
                if attempt < max_retries:
                    logger.warning(
                        'Mailgun attempt %d failed, retrying: %s',
                        attempt + 1,
                        result.error,
                    )
        else:
            logger.warning('Mailgun not configured, skipping primary provider')
        
        # Try fallback provider (SMTP)
        if use_fallback and self.smtp.is_configured():
            logger.info('Attempting SMTP fallback')
            
            for attempt in range(max_retries + 1):
                result = self.smtp.send(
                    to=to,
                    subject=subject,
                    html=html,
                    text=text,
                    from_name=from_name,
                    from_email=from_email,
                    reply_to=reply_to,
                )
                
                if result.success:
                    logger.info(
                        'Email sent via SMTP fallback: to=%s message_id=%s',
                        masked_recipients,
                        result.message_id,
                    )
                    return result
                
                if attempt < max_retries:
                    logger.warning(
                        'SMTP attempt %d failed, retrying: %s',
                        attempt + 1,
                        result.error,
                    )
            
            # Return last SMTP error
            return result
        elif use_fallback:
            logger.warning('SMTP fallback not configured')
        
        # All providers failed
        return EmailResult(
            success=False,
            provider='none',
            error='All email providers failed or not configured',
        )
    
    def send_email_background(
        self,
        to: Union[str, List[str]],
        subject: str,
        html: str,
        text: str,
        from_name: Optional[str] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> str:
        """
        Send email in a background thread.
        
        Creates a BackgroundJob record for tracking and runs the send
        in a separate thread to avoid blocking the request.
        
        Returns:
            job_id: UUID of the background job for status tracking
        """
        from src.models.league import db, BackgroundJob
        
        # Create background job record
        job_id = str(uuid4())
        recipients = [to] if isinstance(to, str) else list(to)
        
        try:
            job = BackgroundJob(
                id=job_id,
                job_type='email_send',
                status='running',
                progress=0,
                total=len(recipients),
                started_at=datetime.now(timezone.utc),
            )
            db.session.add(job)
            db.session.commit()
        except Exception as e:
            logger.error('Failed to create email background job: %s', e)
            db.session.rollback()
        
        # Get app context for background thread
        app = self._app
        
        def send_in_background():
            try:
                if app:
                    with app.app_context():
                        self._execute_background_send(
                            job_id=job_id,
                            to=to,
                            subject=subject,
                            html=html,
                            text=text,
                            from_name=from_name,
                            from_email=from_email,
                            reply_to=reply_to,
                            tags=tags,
                        )
                else:
                    # No app context available - try without
                    self._execute_background_send(
                        job_id=job_id,
                        to=to,
                        subject=subject,
                        html=html,
                        text=text,
                        from_name=from_name,
                        from_email=from_email,
                        reply_to=reply_to,
                        tags=tags,
                    )
            except Exception as e:
                logger.exception('Background email send failed: %s', e)
        
        thread = threading.Thread(target=send_in_background, daemon=True)
        thread.start()
        
        return job_id
    
    def _execute_background_send(
        self,
        job_id: str,
        to: Union[str, List[str]],
        subject: str,
        html: str,
        text: str,
        from_name: Optional[str] = None,
        from_email: Optional[str] = None,
        reply_to: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ):
        """Execute the actual email send and update job status."""
        from src.models.league import db, BackgroundJob
        
        try:
            result = self.send_email(
                to=to,
                subject=subject,
                html=html,
                text=text,
                from_name=from_name,
                from_email=from_email,
                reply_to=reply_to,
                tags=tags,
            )
            
            # Update job status
            job = db.session.get(BackgroundJob, job_id)
            if job:
                recipients = [to] if isinstance(to, str) else list(to)
                job.status = 'completed' if result.success else 'failed'
                job.progress = len(recipients) if result.success else 0
                job.completed_at = datetime.now(timezone.utc)
                job.results_json = json.dumps(result.to_dict())
                if not result.success:
                    job.error = result.error
                db.session.commit()
                
        except Exception as e:
            logger.exception('Background email job %s failed: %s', job_id, e)
            try:
                job = db.session.get(BackgroundJob, job_id)
                if job:
                    job.status = 'failed'
                    job.error = str(e)
                    job.completed_at = datetime.now(timezone.utc)
                    db.session.commit()
            except Exception:
                db.session.rollback()
    
    @staticmethod
    def _mask_email(email: str) -> str:
        """Mask email for logging (e.g., u***@example.com)."""
        if '@' not in email:
            return '***'
        local, domain = email.split('@', 1)
        if len(local) <= 1:
            return f'*@{domain}'
        return f'{local[0]}***@{domain}'

    def send_claim_invitation(
        self,
        to_email: str,
        writer_name: str,
        claim_url: str,
        inviter_name: str,
    ) -> EmailResult:
        """Send a claim invitation email to an external writer.

        Args:
            to_email: The writer's email address
            writer_name: The writer's display name
            claim_url: The URL to claim the account
            inviter_name: Name of the editor/admin who created the account
        """
        subject = "Claim your The Academy Watch writer account"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif; line-height: 1.6; color: #333; }}
        .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
        h2 {{ color: #1a1a1a; }}
        .button {{ display: inline-block; background-color: #2563eb; color: white !important; padding: 12px 24px; text-decoration: none; border-radius: 6px; font-weight: bold; margin: 20px 0; }}
        .button:hover {{ background-color: #1d4ed8; }}
        .footer {{ margin-top: 30px; font-size: 0.875rem; color: #666; }}
    </style>
</head>
<body>
    <div class="container">
        <h2>Welcome to The Academy Watch, {writer_name}!</h2>

        <p>{inviter_name} has created a writer account for you on The Academy Watch,
        the football loan tracking platform.</p>

        <p>Click the button below to claim your account and start writing directly on the platform:</p>

        <p style="text-align: center;">
            <a href="{claim_url}" class="button">Claim Your Account</a>
        </p>

        <p>Or copy and paste this link into your browser:</p>
        <p style="word-break: break-all; color: #2563eb;">{claim_url}</p>

        <div class="footer">
            <p><strong>This link expires in 24 hours.</strong></p>
            <p>If you didn't expect this email, you can safely ignore it.</p>
            <p>&mdash; The Academy Watch Team</p>
        </div>
    </div>
</body>
</html>
"""

        text_content = f"""Welcome to The Academy Watch, {writer_name}!

{inviter_name} has created a writer account for you on The Academy Watch, the football loan tracking platform.

Claim your account here:
{claim_url}

This link expires in 24 hours.

If you didn't expect this email, you can safely ignore it.

-- The Academy Watch Team
"""

        return self.send_email(
            to=to_email,
            subject=subject,
            html=html_content,
            text=text_content,
            tags=['claim-invitation', 'writer-onboarding'],
        )


# Singleton instance
email_service = EmailService()








