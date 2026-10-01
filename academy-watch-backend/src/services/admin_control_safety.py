"""Transactional case intake and hide-first actions using existing visibility bits."""

import logging
import time
from datetime import timedelta

import sqlalchemy as sa
from src.models.admin_control import SafeguardingCase, SafeguardingCaseEvent, now
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
    acted = source.resolved_at if is_report else source.decided_at
    closed = source.status in {"resolved", "dismissed", "lifted", "rejected"}
    result = connection.execute(
        SafeguardingCase.__table__.insert().values(
            report_id=source.id if is_report else None,
            suppression_id=None if is_report else source.id,
            target_type=target_type,
            target_id=target_id,
            status="closed" if closed else "investigating" if source.status in {"reviewing", "active"} else "open",
            first_action_at=acted,
            closed_at=acted if closed else None,
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
    # Anonymous takedown contact is unverified and must never select an account recipient.
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
        dedupe_key=f"safety:{case.id}:{state}:{user.id}",
        recipient_user_id=user.id,
        event_type="safeguarding_update",
        entity_type="user_account",
        entity_id=user.id,
        template="safeguarding_update",
        payload={"case_id": case.id, "version": case.version, "state": state},
    )
    case.notification_state = "queued" if intent else "foundation_disabled"


def bounded_id(value):
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError("Target must be an integer ID") from None
    if not 0 < result <= 2147483647:
        raise ValueError("Target ID is out of range")
    return result


def _player_id(case):
    if case.target_type == "showcase_content":
        from src.models.showcase import PlayerShowcaseMedia

        media = db.session.get(PlayerShowcaseMedia, bounded_id(case.target_id))
        return (media.player_api_id or -media.local_player_id) if media else None
    if case.target_type != "player_profile":
        return None
    if case.target_id.startswith("local:"):
        return -bounded_id(case.target_id[6:])
    try:
        subject = int(case.target_id)
    except ValueError:
        return None
    bounded_id(abs(subject))
    return subject


def _resolved_player_id(case):
    subject = _player_id(case)
    if subject is None:
        raise ValueError("This target needs review in the existing moderation tool; no automatic hide is available")
    from src.models.follow import PlayerShadow
    from src.models.showcase import LocalPlayer
    from src.models.tracked_player import TrackedPlayer

    exists = (
        db.session.get(LocalPlayer, -subject)
        if subject < 0
        else (
            TrackedPlayer.query.filter_by(player_api_id=subject).first()
            or PlayerShadow.query.filter_by(player_api_id=subject).first()
        )
    )
    if exists is None:
        raise ValueError("Player target not found")
    return subject


def case_hidden(case):
    if case.target_type == "club_program":
        try:
            from src.services.club_publication_hold import club_publication_held

            return club_publication_held(bounded_id(case.target_id))
        except ValueError:
            return False
    try:
        subject = _player_id(case)
    except ValueError:
        return False
    if subject:
        from src.services.club_publication_hold import subject_publication_held
        from src.services.player_suppression import is_player_suppressed

        return is_player_suppressed(subject) or subject_publication_held(subject)
    return False


def _hide(case, actor, reason):
    if case.target_type == "club_program":
        try:
            program_id = bounded_id(case.target_id)
        except ValueError:
            raise ValueError("Club target must be a program ID") from None
        program = ClubProgram.query.filter_by(id=program_id).with_for_update().first()
        if program is None:
            raise ValueError("Club program not found")
        before = bool(program.emergency_hidden)
        if not before:
            program.emergency_hidden = True
            case.held_program_id = program.id
        if not before:
            record_admin_event(
                actor,
                "emergency_hide",
                "club_program",
                program.id,
                reason,
                {"case_id": case.id, "before_hidden": before, "after_hidden": True},
            )
        return not before
    subject = _resolved_player_id(case)
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
        case.suppression_id = suppression.id  # durable source identity survives restore/ownership changes
    # Never own a pre-existing active suppression: restoring this case cannot lift it.
    if suppression.status != "active":
        case.owned_suppression_id = suppression.id
        from src.services.suppression_decision import decide_suppression

        decide_suppression(suppression, "activate", actor, reason, preserve_notes=True)
        return True
    return False


def _restore(case, actor, reason):
    if case.held_program_id:
        from src.models.p2_foundation import AdminActionEvent

        program = ClubProgram.query.filter_by(id=case.held_program_id).with_for_update().first()
        latest = (
            AdminActionEvent.query.filter_by(
                target_type="club_program", target_id=str(case.held_program_id), action="emergency_hide"
            )
            .order_by(AdminActionEvent.id.desc())
            .first()
        )
        if program and program.emergency_hidden:
            if latest is None or latest.event_metadata.get("case_id") != case.id:
                raise ValueError("Another moderation decision owns the club hold")
            program.emergency_hidden = False
            record_admin_event(
                actor,
                "emergency_lift",
                "club_program",
                program.id,
                reason,
                {"case_id": case.id, "before_hidden": True, "after_hidden": False},
            )
        case.held_program_id = None
    elif case.owned_suppression_id:
        suppression = PlayerSuppression.query.filter_by(id=case.owned_suppression_id).with_for_update().first()
        if suppression and suppression.status == "active":
            from src.services.suppression_decision import decide_suppression

            decide_suppression(suppression, "lift", actor, reason)
        case.owned_suppression_id = None
    else:
        raise ValueError("This case does not own a hold; use the original moderation tool")


def act(case, action, actor, reason):
    if action not in {"hide", "investigate", "club_contact", "close", "restore"}:
        raise ValueError("Unknown case action")
    if case.status == "closed" and action != "restore":
        raise ValueError("Case is closed")
    record_admin_event(actor, f"safeguarding_{action}", "safeguarding_case", case.id, reason)
    changed = False
    if action == "hide":
        changed = _hide(case, actor, reason)
        case.status = "investigating"
    elif action == "restore":
        _restore(case, actor, reason)
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
    if action == "close" or (action == "hide" and changed):
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
            for _ in range(1):  # one bounded batch per source per lazy pass
                missing = ~sa.exists().where(table.c[source_key] == source.c.id)
                if model is PlayerSuppression:
                    missing = sa.and_(missing, ~sa.exists().where(table.c.owned_suppression_id == source.c.id))
                rows = (
                    db.session.execute(
                        sa.select(*columns).where(source.c.id > after, missing).order_by(source.c.id).limit(500)
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


def sync_source_case(source, actor, reason):
    """Both existing moderation paths update linked cases in their own transaction."""
    if not sa.inspect(db.session.connection()).has_table("safeguarding_cases"):
        return
    report = isinstance(source, ContentReport)
    key = SafeguardingCase.report_id if report else SafeguardingCase.suppression_id
    predicate = key == source.id
    if not report:
        predicate = sa.or_(predicate, SafeguardingCase.owned_suppression_id == source.id)
    for case in SafeguardingCase.query.filter(predicate).with_for_update():
        closed = source.status in {"resolved", "dismissed", "lifted", "rejected"}
        acted = source.resolved_at if report else source.decided_at
        case.first_action_at = case.first_action_at or acted or now()
        if closed:
            case.status, case.closed_at, case.resolver_email = "closed", acted or now(), actor
        elif case.status != "closed":
            case.status = "investigating"
        if not report:
            # A later independent moderation decision supersedes case ownership.
            case.owned_suppression_id = None
        case.version += 1
        db.session.add(
            SafeguardingCaseEvent(case_id=case.id, action=f"source_{source.status}", actor_email=actor, reason=reason)
        )
        if closed:
            notify(case, "closed")


def register_control_reconciliation(app):
    """Register only: zero import/boot queries. Throttle bounded admin-read repair."""
    app.extensions["b3_reconcile"] = {}


def lazy_reconcile(app, which):
    last = app.extensions.setdefault("b3_reconcile", {})
    if time.monotonic() - last.get(which, -300) < 300:
        return
    last[which] = time.monotonic()
    try:
        if which == "safety":
            reconcile_safety_boot(app)
        elif which == "business":
            from src.services.admin_control_business import record_business_boot

            record_business_boot(app)
    except Exception:
        db.session.rollback()
        logging.getLogger(__name__).exception("Admin reconciliation deferred for %s", which)
