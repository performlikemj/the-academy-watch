"""Transactional case intake and hide-first actions using existing visibility bits."""

from datetime import timedelta

import sqlalchemy as sa
from src.models.admin_control import SafeguardingCase, SafeguardingCaseEvent, now
from src.models.follow import PlayerShadow
from src.models.funding import ClubProgram
from src.models.league import UserAccount, db
from src.models.player_suppression import PlayerSuppression
from src.models.trust import ContentReport
from src.services.admin_audit import record_admin_event
from src.services.notification_outbox import enqueue, register_template


def safety_enabled():
    import os

    return os.getenv("ADMIN_SAFETY_ENABLED", "").lower() in {"1", "true", "yes", "on"}


def _intake(mapper, connection, source):
    if not safety_enabled() or getattr(source, "_skip_safety_intake", False):
        return
    is_report = isinstance(source, ContentReport)
    received = source.created_at or now()
    target_type = source.subject_type if is_report else "player_profile"
    target_id = source.subject_id if is_report else str(source.player_api_id or -source.local_player_id)
    result = connection.execute(
        SafeguardingCase.__table__.insert().values(
            report_id=source.id if is_report else None,
            suppression_id=None if is_report else source.id,
            target_type=target_type,
            target_id=target_id,
            status="open",
            received_at=received,
            first_action_due_at=received + timedelta(hours=24),
            version=1,
            notification_state="none",
        )
    )
    connection.execute(
        SafeguardingCaseEvent.__table__.insert().values(
            case_id=result.inserted_primary_key[0],
            action="received",
            actor_email="system",
            reason="Request received",
            created_at=received,
        )
    )


def register_safety():
    for model in (ContentReport, PlayerSuppression):
        if not sa.event.contains(model, "after_insert", _intake):
            sa.event.listen(model, "after_insert", _intake)
    register_template(
        "safeguarding_update",
        eligible=_notification_eligible,
        render=_notification_render,
        payload_enums={"state": {"hidden", "closed"}},
    )


def _recipient(case):
    if case.report_id:
        report = db.session.get(ContentReport, case.report_id)
        return db.session.get(UserAccount, report.reporter_user_id) if report else None
    source = db.session.get(PlayerSuppression, case.suppression_id) if case.suppression_id else None
    if source:
        return UserAccount.query.filter_by(email=source.requester_contact.strip().lower()).first()
    return None


def _notification_eligible(intent, user):
    case = db.session.get(SafeguardingCase, intent.payload.get("case_id"), populate_existing=True)
    recipient = _recipient(case) if case else None
    if recipient is None or recipient.id != user.id or recipient.is_tombstone:
        return False
    state = intent.payload.get("state")
    return (state == "closed" and case.status == "closed") or (state == "hidden" and case_hidden(case))


def _notification_render(intent, user):
    text = (
        "The reported page has been hidden while we review your request."
        if intent.payload["state"] == "hidden"
        else "Our review of your safeguarding request is complete. Sign in to review its status."
    )
    return {"subject": "Your safeguarding request", "text": text, "html": f"<p>{text}</p>"}


def notify(case, state):
    user = _recipient(case)
    if user is None or user.is_tombstone:
        case.notification_state = "no_account_recipient"
        return
    intent = enqueue(
        dedupe_key=f"safety:{case.id}:{case.version}:{state}:{user.id}",
        recipient_user_id=user.id,
        event_type="safeguarding_update",
        entity_type="user_account",
        entity_id=user.id,
        template="safeguarding_update",
        payload={"case_id": case.id, "version": case.version, "state": state},
    )
    case.notification_state = "queued" if intent else "foundation_disabled"


def _player_id(case):
    if case.target_type == "showcase_content":
        from src.models.showcase import PlayerShowcaseMedia

        try:
            media = db.session.get(PlayerShowcaseMedia, int(case.target_id))
        except ValueError:
            return None
        return (media.player_api_id or -media.local_player_id) if media else None
    if case.target_type != "player_profile":
        return None
    try:
        subject = -int(case.target_id[6:]) if case.target_id.startswith("local:") else int(case.target_id)
        return subject if subject != 0 else None
    except ValueError:
        return None


def case_hidden(case):
    if case.target_type == "club_program":
        try:
            from src.services.club_publication_hold import club_publication_held

            return club_publication_held(int(case.target_id))
        except ValueError:
            return False
    subject = _player_id(case)
    if subject:
        from src.services.club_publication_hold import subject_publication_held
        from src.services.player_suppression import is_player_suppressed

        return is_player_suppressed(subject) or subject_publication_held(subject)
    return False


def _hide(case, actor, reason):
    if case.target_type == "club_program":
        try:
            program_id = int(case.target_id)
        except ValueError:
            raise ValueError("Club target must be a program ID") from None
        program = ClubProgram.query.filter_by(id=program_id).with_for_update().first()
        if program is None:
            raise ValueError("Club program not found")
        if not program.emergency_hidden:
            program.emergency_hidden = True
            case.held_program_id = program.id
        record_admin_event(actor, "emergency_hide", "club_program", program.id, reason, {"case_id": case.id})
        return
    subject = _player_id(case)
    if subject is None:
        raise ValueError("This target needs review in the existing moderation tool; no automatic hide is available")
    column = PlayerSuppression.player_api_id if subject > 0 else PlayerSuppression.local_player_id
    suppression = (
        PlayerSuppression.query.filter(column == abs(subject), PlayerSuppression.status.in_(("requested", "active")))
        .with_for_update()
        .first()
    )
    if suppression is None:
        suppression = PlayerSuppression(
            player_api_id=subject if subject > 0 else None,
            local_player_id=-subject if subject < 0 else None,
            reason_code="admin_other",
            requester_role="other",
            requester_contact=actor,
            request_statement=reason,
            status="requested",
        )
        suppression._skip_safety_intake = True
        db.session.add(suppression)
        db.session.flush()
    # Never own a pre-existing active suppression: restoring this case cannot lift it.
    if suppression.status != "active":
        case.owned_suppression_id = suppression.id
        suppression.status = "active"
        suppression.notes = reason
        suppression.decided_at = now()
        suppression.decided_by = actor
        if subject > 0:
            PlayerShadow.query.filter_by(player_api_id=subject).update({PlayerShadow.is_active: False})


def act(case, action, actor, reason):
    if action not in {"hide", "investigate", "club_contact", "close", "restore"}:
        raise ValueError("Unknown case action")
    if case.status == "closed" and action != "restore":
        raise ValueError("Case is closed")
    record_admin_event(actor, f"safeguarding_{action}", "safeguarding_case", case.id, reason)
    if action == "hide":
        _hide(case, actor, reason)
        case.status = "investigating"
    elif action == "restore":
        # Restoration is deliberately routed to the original authoritative tools.
        # Another incident could have renewed the same club/player hold meanwhile.
        raise ValueError("Review and lift the hold in its original moderation tool; closing a case never lifts a hold")
    elif action == "close":
        case.status, case.closed_at, case.resolver_email = "closed", now(), actor
        if case.report_id:
            report = db.session.get(ContentReport, case.report_id)
            report.status, report.resolved_at, report.resolution_notes = "resolved", now(), reason
    else:
        case.status = "investigating"
    case.first_action_at = case.first_action_at or now()
    case.version += 1
    db.session.add(SafeguardingCaseEvent(case_id=case.id, action=action, actor_email=actor, reason=reason))
    if action in {"hide", "close"}:
        notify(case, "hidden" if action == "hide" else "closed")


def reconcile_safety_boot(app):
    """Import requests received during dark periods when the page is enabled."""
    if not safety_enabled():
        return
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    with app.app_context():
        table = SafeguardingCase.__table__
        insert = pg_insert if db.engine.dialect.name == "postgresql" else sqlite_insert
        for model, source_key in ((ContentReport, "report_id"), (PlayerSuppression, "suppression_id")):
            source = model.__table__
            columns = [source.c.id, source.c.status, source.c.created_at]
            if model is ContentReport:
                columns += [source.c.subject_type, source.c.subject_id, source.c.resolved_at]
            else:
                columns += [source.c.player_api_id, source.c.local_player_id, source.c.decided_at]
            after = 0
            while True:
                rows = (
                    db.session.execute(
                        sa.select(*columns)
                        .where(source.c.id > after, ~sa.exists().where(table.c[source_key] == source.c.id))
                        .order_by(source.c.id)
                        .limit(500)
                    )
                    .mappings()
                    .all()
                )
                if not rows:
                    break
                values = []
                for row in rows:
                    report = model is ContentReport
                    closed = row["status"] in {"resolved", "dismissed", "lifted", "rejected"}
                    acted = row["resolved_at"] if report else row["decided_at"]
                    values.append(
                        {
                            source_key: row["id"],
                            "target_type": row["subject_type"] if report else "player_profile",
                            "target_id": row["subject_id"]
                            if report
                            else str(row["player_api_id"] or -row["local_player_id"]),
                            "received_at": row["created_at"],
                            "first_action_due_at": row["created_at"] + timedelta(hours=24),
                            "first_action_at": acted,
                            "closed_at": acted if closed else None,
                            "status": "closed"
                            if closed
                            else "investigating"
                            if row["status"] in {"reviewing", "active"}
                            else "open",
                        }
                    )
                db.session.execute(insert(table).values(values).on_conflict_do_nothing(index_elements=[source_key]))
                after = rows[-1]["id"]
        db.session.commit()
