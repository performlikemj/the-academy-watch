"""Safe B3 account export and retained-history identity erasure, schema aware."""

import sqlalchemy as sa
from src.models.league import db


def export_admin_control(user, schema):
    result = {}
    if schema.has_columns("user_accounts", "account_status") and user.account_status != "active":
        result["account_standing"] = {
            "status": user.account_status,
            "suspended_at": user.suspended_at.isoformat() if user.suspended_at else None,
        }
    if schema.has_columns("safeguarding_cases", "report_id") and schema.has_columns(
        "content_reports", "reporter_user_id"
    ):
        rows = db.session.execute(
            sa.text(
                "SELECT c.id,c.status,c.received_at,c.first_action_due_at,c.first_action_at,c.closed_at,c.notification_state FROM safeguarding_cases c JOIN content_reports r ON r.id=c.report_id WHERE r.reporter_user_id=:uid ORDER BY c.id"
            ),
            {"uid": user.id},
        ).mappings()
        cases = [
            {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in row.items()}
            for row in rows
        ]
        if cases:
            result["safeguarding_cases"] = cases
    if schema.has_columns("billing_cash_events", "purchaser_user_id"):
        rows = db.session.execute(
            sa.text(
                "SELECT id,kind,amount_cents,currency,occurred_at,product_code FROM billing_cash_events WHERE purchaser_user_id=:uid ORDER BY id"
            ),
            {"uid": user.id},
        ).mappings()
        cash = [
            {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in row.items()}
            for row in rows
        ]
        if cash:
            result["billing_cash"] = cash
    return result


def erase_admin_control(user_id, email, schema):
    counts = {}
    if schema.has_columns("billing_cash_events", "purchaser_user_id"):
        counts["cash_anonymized"] = db.session.execute(
            sa.text(
                "UPDATE billing_cash_events SET purchaser_user_id=NULL, scope_id=CASE WHEN scope_type='user' THEN NULL ELSE scope_id END WHERE purchaser_user_id=:uid OR (scope_type='user' AND scope_id=:uid)"
            ),
            {"uid": user_id},
        ).rowcount
    if email:
        if (
            schema.has_columns("safeguarding_cases", "suppression_id", "report_id")
            and schema.has_columns("safeguarding_case_events", "actor_email")
            and schema.has_columns("player_suppressions", "requester_contact", "request_statement", "notes")
        ):
            from src.models.admin_control import SafeguardingCase, SafeguardingCaseEvent
            from src.models.player_suppression import PlayerSuppression

            # A report's suppression_id is assigned only when its case creates
            # a new suppression. Guardian intake cases have no report_id; reused
            # requester holds are never assigned to the report's source key.
            generated = PlayerSuppression.query.join(
                SafeguardingCase, SafeguardingCase.suppression_id == PlayerSuppression.id
            ).filter(SafeguardingCase.report_id.is_not(None))
            count = 0
            for row in generated:
                first_hide = (
                    SafeguardingCaseEvent.query.join(
                        SafeguardingCase, SafeguardingCase.id == SafeguardingCaseEvent.case_id
                    )
                    .filter(SafeguardingCase.suppression_id == row.id, SafeguardingCaseEvent.action == "hide")
                    .order_by(SafeguardingCaseEvent.id)
                    .first()
                )
                if first_hide is None:
                    continue
                if first_hide.actor_email.lower() == email.lower():
                    row.requester_contact = "Account deleted"
                    row.request_statement = "[redacted]"
                    # Notes may have been replaced by a later moderator. Scrub
                    # only a copy of this creator's reason, never other evidence.
                    if row.notes == first_hide.reason:
                        row.notes = "[redacted]"
                    count += 1
                if (row.decided_by or "").lower() == email.lower():
                    row.notes = "[redacted]"
            if count:
                counts["case_suppression_copies_redacted"] = count
            db.session.flush()  # capture provenance before append-only event redaction
        for table, actor in (("safeguarding_case_events", "actor_email"), ("safeguarding_cases", "resolver_email")):
            if schema.has_columns(table, actor):
                extra = ", reason='[redacted]'" if table.endswith("events") else ""
                counts[table + "_redacted"] = db.session.execute(
                    sa.text(f"UPDATE {table} SET {actor}='Account deleted'{extra} WHERE lower({actor})=:email"),
                    {"email": email.lower()},
                ).rowcount
        if schema.has_columns("user_accounts", "suspended_by"):
            db.session.execute(
                sa.text(
                    "UPDATE user_accounts SET suspended_by='Account deleted',suspension_reason='[redacted]' WHERE lower(suspended_by)=:email"
                ),
                {"email": email.lower()},
            )
    return {key: value for key, value in counts.items() if value}
