"""Schema-aware personal export and the audit's sole erasure exception."""

import sqlalchemy as sa
from src.models.league import db


def export_foundation_rows(user, schema):
    result = {}
    if schema.has_columns("notification_outbox", "recipient_user_id"):
        result["notifications"] = [
            {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in row.items()}
            for row in db.session.execute(
                sa.text(
                    "SELECT id, event_type, entity_type, entity_id, template, status, attempts, created_at, sent_at "
                    "FROM notification_outbox WHERE recipient_user_id = :user_id ORDER BY id"
                ),
                {"user_id": user.id},
            ).mappings()
        ]
    if schema.has_columns("admin_action_events", "actor_email"):
        # Export own actions only, omitting free-text reason/metadata that can
        # contain a safeguarding report about someone else.
        result["admin_actions"] = [
            {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in row.items()}
            for row in db.session.execute(
                sa.text(
                    "SELECT id, action, target_type, target_id, created_at FROM admin_action_events "
                    "WHERE lower(actor_email) = :email ORDER BY id"
                ),
                {"email": (user.email or "").strip().lower()},
            ).mappings()
        ]
    # Keep empty exports identical while the rollout is dark, but always
    # expose retained personal data even after the rollout is switched off.
    return {key: rows for key, rows in result.items() if rows}


def erase_foundation_rows(user_id, email, schema):
    counts = {"notifications_deleted": 0, "admin_actions_redacted": 0}
    if schema.has_columns("notification_outbox", "recipient_user_id"):
        counts["notifications_deleted"] = db.session.execute(
            sa.text("DELETE FROM notification_outbox WHERE recipient_user_id = :user_id"), {"user_id": user_id}
        ).rowcount
    if email and schema.has_columns("admin_action_events", "actor_email"):
        # Append-only action/target/time survive; identity and possibly personal
        # reason/metadata are scrubbed. PostgreSQL trigger permits only this form.
        counts["admin_actions_redacted"] = db.session.execute(
            sa.text(
                "UPDATE admin_action_events SET actor_email = 'Account deleted', reason = '[redacted]', "
                "event_metadata = '{}' WHERE lower(actor_email) = :email"
            ),
            {"email": email},
        ).rowcount
    return counts
