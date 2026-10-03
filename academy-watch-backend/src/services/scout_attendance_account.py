"""Flag-independent account privacy and bounded expiry maintenance."""

from src.models.league import db
from src.models.opportunities import ClubOpportunity, now
from src.models.p2_foundation import NotificationOutbox
from src.models.scout_attendance import ScoutAttendance
from src.services.account_standing import account_can_act
from src.services.scout_attendance import visible_event
from src.services.trust import is_verified_scout


def _delete(ids):
    if not ids:
        return 0
    NotificationOutbox.query.filter(
        NotificationOutbox.template == "c4_attendance", NotificationOutbox.payload["attendance_id"].as_string().in_(ids)
    ).delete(synchronize_session=False)
    return ScoutAttendance.query.filter(ScoutAttendance.id.in_(ids)).delete(synchronize_session=False)


def export_attendance(user, schema):
    if not schema.has_table("scout_attendance_requests"):
        return {}
    trusted = account_can_act(user) and is_verified_scout(user)
    rows = ScoutAttendance.query.filter_by(scout_user_id=user.id).all()
    readable = {
        r.id
        for r in rows
        if trusted
        and r.status == "accepted"
        and r.retention_expires_at > now()
        and visible_event(db.session.get(ClubOpportunity, r.opportunity_id))
    }
    return (
        {
            "scout_attendance": [
                {
                    c.name: (v.isoformat() if hasattr(v, "isoformat") else v)
                    for c in r.__table__.columns
                    if (v := getattr(r, c.name)) is not None
                    and c.name != "decision_user_id"
                    and (c.name != "arrival_instructions" or r.id in readable)
                }
                for r in rows
            ]
        }
        if rows
        else {}
    )


def erase_attendance(user_id, schema):
    if not schema.has_table("scout_attendance_requests"):
        return {}
    ids = [r.id for r in ScoutAttendance.query.filter_by(scout_user_id=user_id)]
    deleted = _delete(ids)
    redacted = ScoutAttendance.query.filter_by(decision_user_id=user_id).update(
        {"decision_user_id": None}, synchronize_session=False
    )
    return (
        {"scout_attendance": {"deleted": deleted, "decision_actors_redacted": redacted}} if deleted or redacted else {}
    )


def purge_expired(*, limit=100):
    rows = (
        ScoutAttendance.query.filter(ScoutAttendance.retention_expires_at <= now())
        .order_by(ScoutAttendance.retention_expires_at)
        .limit(limit)
        .all()
    )
    return _delete([r.id for r in rows])
