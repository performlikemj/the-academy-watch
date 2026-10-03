"""Best-effort applicant emails for Trust Desk decisions."""

import logging
import os
from html import escape

from src.models.showcase import ClubOfficialClaim, PlayerProfileClaim
from src.models.trust import ScoutVerification

logger = logging.getLogger(__name__)


def _send_decision_email(*, recipient: str | None, subject: str, text: str, html: str, tag: str) -> bool:
    if not recipient:
        logger.warning("Trust decision email skipped because the applicant has no email")
        return False
    try:
        from src.services.email_service import email_service

        result = email_service.send_email(
            to=recipient,
            subject=subject,
            text=text,
            html=html,
            tags=[tag],
            use_fallback=False,
        )
    except Exception:
        logger.exception("Trust decision email dispatch failed: %s", subject)
        return False
    if not getattr(result, "success", False):
        logger.warning("Trust decision email was not delivered: %s", subject)
        return False
    return True


def send_scout_verification_decision_email(verification: ScoutVerification, action: str) -> bool:
    """Email a scout applicant after an approve/reject decision."""
    recipient = verification.user.email if verification.user else None
    name = verification.full_name or "there"
    if action == "approve":
        subject = "Your scout verification was approved"
        decision = (
            "Your scout verification has been approved. You can now request introductions "
            "to eligible player profile owners through The Academy Watch."
        )
        note_text = ""
        note_html = ""
    else:
        subject = "Your scout verification application was not approved"
        decision = (
            "Your scout verification application was not approved. You may review your application details "
            "and submit a new application when eligible."
        )
        note_text = f"\n\nReview note: {verification.review_notes}" if verification.review_notes else ""
        note_html = (
            f"<p><strong>Review note:</strong> {escape(verification.review_notes)}</p>"
            if verification.review_notes
            else ""
        )

    text = f"Hello {name},\n\n{decision}{note_text}\n\nThe Academy Watch"
    html = f"<p>Hello {escape(name)},</p><p>{escape(decision)}</p>{note_html}<p>The Academy Watch</p>"
    return _send_decision_email(
        recipient=recipient,
        subject=subject,
        text=text,
        html=html,
        tag="scout-verification-decision",
    )


def send_player_claim_decision_email(claim: PlayerProfileClaim, action: str, player_name: str | None) -> bool:
    """Email a profile claimant after an approve/reject decision."""
    recipient = claim.user.email if claim.user else None
    name = claim.user.display_name if claim.user and claim.user.display_name else "there"
    player_reference = player_name or (
        f"player profile {claim.player_api_id}" if claim.player_api_id is not None else "the player profile"
    )
    if action == "approve":
        subject = "Your player profile claim was approved"
        decision = (
            f"Your claim for {player_reference} has been approved. Profile ownership is now live, "
            "and you can manage the profile's showcase content through The Academy Watch."
        )
    else:
        subject = "Your player profile claim was not approved"
        decision = (
            f"Your claim for {player_reference} was not approved. You may review your claim details "
            "and submit a new claim if appropriate."
        )

    text = f"Hello {name},\n\n{decision}\n\nThe Academy Watch"
    html = f"<p>Hello {escape(name)},</p><p>{escape(decision)}</p><p>The Academy Watch</p>"
    return _send_decision_email(
        recipient=recipient,
        subject=subject,
        text=text,
        html=html,
        tag="player-claim-decision",
    )


def send_club_claim_decision_email(claim: ClubOfficialClaim, action: str) -> bool:
    """Email a club claimant after an approve/reject decision."""
    from src.routes.showcase import _club_reference_name

    recipient = claim.user.email if claim.user else None
    name = claim.user.display_name if claim.user and claim.user.display_name else "there"
    club_name = _club_reference_name(
        team_api_id=claim.team_api_id,
        local_club_id=claim.local_club_id,
    )
    club_reference = club_name or "the club"
    if action == "approve":
        subject = "Your club claim was approved"
        decision = f"Your claim for {club_reference} has been approved."
        base = (os.getenv("PUBLIC_BASE_URL") or "https://theacademywatch.com").strip().rstrip("/")
        console_url = f"{base}/my-club"
        console_text = f"Manage your club on the web — roster, match video and player reports: {console_url}"
        console_html = (
            "<p>Manage your club on the web — roster, match video and player reports: "
            f'<a href="{escape(console_url, quote=True)}">{escape(console_url)}</a></p>'
        )
    else:
        subject = "Your club claim was not approved"
        decision = (
            f"Your claim for {club_reference} was not approved. You may review your claim details "
            "and submit a new claim if appropriate."
        )
        console_text = ""
        console_html = ""

    text = f"Hello {name},\n\n{decision}"
    if console_text:
        text += f"\n\n{console_text}"
    text += "\n\nThe Academy Watch"
    html = f"<p>Hello {escape(name)},</p><p>{escape(decision)}</p>{console_html}<p>The Academy Watch</p>"
    return _send_decision_email(
        recipient=recipient,
        subject=subject,
        text=text,
        html=html,
        tag="club-claim-decision",
    )


__all__ = [
    "send_club_claim_decision_email",
    "send_player_claim_decision_email",
    "send_scout_verification_decision_email",
]
