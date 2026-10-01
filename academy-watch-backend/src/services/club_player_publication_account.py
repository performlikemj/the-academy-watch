"""Privacy and neutral notifications remain safe after the feature is dark."""

from datetime import timedelta

import sqlalchemy as sa
from src.models.club_player_publication import ClubPlayerPublication as Publication
from src.models.league import db
from src.services.club_player_publication import enabled


def purge_invited_emails(*, limit=100, at=None):
    """Bounded privacy maintenance, even while dark; caller commits."""
    from src.models.club_player_publication import now

    if not 1 <= limit <= 1000:
        raise ValueError("limit must be 1–1000")
    at = at or now()
    rows = (
        Publication.query.filter(
            Publication.recipient_email.is_not(None),
            sa.or_(
                Publication.withdrawn_at.is_not(None),
                Publication.club_revoked_at.is_not(None),
                sa.and_(Publication.claimed_at.is_(None), Publication.invite_expires_at <= at),
                Publication.created_at <= at - timedelta(days=180),
            ),
        )
        .order_by(Publication.id)
        .limit(limit)
        .with_for_update()
        .all()
    )
    for row in rows:
        row.recipient_email = None
        row.invite_token_hash = None
        row.invite_expires_at = None
    return {"invited_emails_purged": len(rows)}


def export_publications(user, schema):
    if not schema.has_table("club_player_publications"):
        return {}
    rows = Publication.query.filter(
        sa.or_(
            Publication.recipient_user_id == user.id,
            Publication.creator_user_id == user.id,
            Publication.recipient_email == user.email,
        )
    ).all()
    columns = [c.name for c in Publication.__table__.columns if c.name not in {"invite_token_hash", "recipient_email"}]
    result = [
        {k: v.isoformat() if hasattr(v, "isoformat") else v for k in columns if (v := getattr(r, k)) is not None}
        for r in rows
    ]
    return {"club_player_publications": result} if result else {}


def erase_publications(user_id, email, schema):
    if not schema.has_table("club_player_publications"):
        return {}
    from src.services.club_player_publication import revoke

    rows = Publication.query.filter(
        sa.or_(Publication.recipient_user_id == user_id, Publication.recipient_email == email)
    ).all()
    ids = [r.id for r in rows]
    for row in rows:
        revoke(row)
    from src.models.p2_foundation import NotificationOutbox

    if ids and schema.has_table("notification_outbox"):
        NotificationOutbox.query.filter(
            NotificationOutbox.template == "c1_publication",
            NotificationOutbox.entity_id.in_([str(i) for i in ids]),
        ).delete(synchronize_session=False)
    count = Publication.query.filter(Publication.id.in_(ids)).delete(synchronize_session=False)
    Publication.query.filter_by(creator_user_id=user_id).update({"creator_user_id": None})
    Publication.query.filter_by(association_confirmed_by=user_id).update({"association_confirmed_by": None})
    Publication.query.filter_by(reviewed_by=email).update({"reviewed_by": "Account deleted"})
    return {"club_player_publications": count} if count else {}


def erase_introductions(user_id, claim_ids):
    """Account erasure includes withheld requests, independent of export visibility."""
    from src.models.contact import ContactAuditEvent, ContactMessage, ContactOutcome, ContactRequest
    from src.models.p2_foundation import NotificationOutbox

    ids = [
        id_
        for (id_,) in db.session.query(ContactRequest.id)
        .filter(
            ContactRequest.club_first.is_(True),
            sa.or_(ContactRequest.scout_user_id == user_id, ContactRequest.claim_id.in_(claim_ids)),
        )
        .all()
    ]
    if not ids:
        return 0
    NotificationOutbox.query.filter(
        NotificationOutbox.template == "c1_introduction", NotificationOutbox.entity_id.in_(ids)
    ).delete(synchronize_session=False)
    for model in (ContactMessage, ContactOutcome, ContactAuditEvent):
        model.query.filter(model.contact_request_id.in_(ids)).delete(synchronize_session=False)
    return ContactRequest.query.filter(ContactRequest.id.in_(ids)).delete(synchronize_session=False)


def register_publication_notifications():
    from src.services.notification_outbox import register_template

    def eligible(intent, user):
        row = db.session.get(Publication, int(intent.entity_id))
        return bool(enabled() and row and row.recipient_user_id == user.id and row.claimed_at)

    def render(intent, user):
        return {
            "subject": "Your profile publication status changed",
            "html": "<p>Sign in to review your profile publication status.</p>",
            "text": "Sign in to review your profile publication status.",
        }

    register_template("c1_publication", eligible=eligible, render=render)

    def intro_eligible(intent, user):
        from src.models.contact import ContactRequest
        from src.services.club_access import club_can
        from src.services.club_player_publication import club_request_available

        contact = db.session.get(ContactRequest, intent.entity_id)
        if not contact or not contact.club_first or not club_request_available(contact):
            return False
        if contact.status not in {"pending", "accepted"}:
            return False
        from src.services.contact import utcnow
        from src.services.user_blocks import users_have_block_relationship

        if contact.expires_at <= utcnow() or users_have_block_relationship(
            first_user_id=contact.claim.user_account_id, second_user_id=contact.scout_user_id
        ):
            return False
        if contact.claim and contact.claim.user_account_id == user.id:
            return contact.club_consent_status == "granted"
        return contact.club_consent_status == "pending" and club_can(user.id, contact.club_program_id, "contact")

    register_template(
        "c1_introduction",
        eligible=intro_eligible,
        render=lambda row, user: {
            "subject": "An introduction needs your decision",
            "html": "<p>Sign in to review an introduction.</p>",
            "text": "Sign in to review an introduction.",
        },
    )


def intro_notice(contact, *, player=False):
    from src.services.club_registry import active_program_manager_user_ids
    from src.services.notification_outbox import enqueue

    if not contact.club_first:
        return
    recipients = [contact.claim.user_account_id] if player else active_program_manager_user_ids(contact.club_program_id)
    for recipient in recipients:
        enqueue(
            dedupe_key=f"c1intro:{contact.id}:{'player' if player else 'club'}:{recipient}",
            recipient_user_id=recipient,
            event_type="introduction_decision",
            entity_type="contact_request",
            entity_id=contact.id,
            template="c1_introduction",
            payload={},
        )
