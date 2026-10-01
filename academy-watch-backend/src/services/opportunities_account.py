"""Privacy hooks and retention run even with rollout flags off."""

from datetime import timedelta

import sqlalchemy as sa
from src.models.league import db
from src.models.opportunities import ApplicationEvent, ApplicationNote, ClubOpportunity, OpportunityApplication, now

TABLES = ("club_opportunities", "opportunity_applications", "application_events", "application_notes")


def _ready(schema):
    return all(schema.has_table(t) for t in TABLES)


def _serialize(row, columns=None):
    return {
        key: value.isoformat() if hasattr(value, "isoformat") else value
        for key in (columns or row.__table__.columns.keys())
        if (value := getattr(row, key)) is not None
    }


def export_opportunities(user, schema):
    if not _ready(schema):
        return {}
    apps = OpportunityApplication.query.filter_by(applicant_user_id=user.id).all()
    ids = [a.id for a in apps]
    result = {
        "created_opportunities": [
            _serialize(r) for r in ClubOpportunity.query.filter_by(creator_user_id=user.id).all()
        ],
        "applications": [
            _serialize(r, [k for k in OpportunityApplication.__table__.columns.keys() if k != "request_hash"])
            for r in apps
        ],
        "application_events": [
            _serialize(
                r,
                ["application_id", "from_state", "to_state", "version", "created_at"]
                + (["actor_user_id"] if r.actor_user_id == user.id else []),
            )
            for r in ApplicationEvent.query.filter(
                sa.or_(ApplicationEvent.application_id.in_(ids), ApplicationEvent.actor_user_id == user.id)
            ).all()
        ],
        # Internal review text isn't an applicant-facing DTO; export own authored notes only.
        "authored_application_notes": [
            _serialize(r) for r in ApplicationNote.query.filter_by(author_user_id=user.id).all()
        ],
    }
    return {"recruiting": result} if any(result.values()) else {}


def _privacy_context():
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(sa.text("SET LOCAL academy_watch.application_privacy = 'on'"))


def _delete_applications(ids):
    if not ids:
        return {"applications": 0, "application_events": 0, "application_notes": 0, "notifications": 0}
    _privacy_context()
    counts = {}
    from src.models.p2_foundation import NotificationOutbox

    # JSON IDs are the only persisted payload; delete all dispositions, including sent history.
    counts["notifications"] = NotificationOutbox.query.filter(
        NotificationOutbox.template == "b2_application",
        NotificationOutbox.payload["application_id"].as_string().in_(ids),
    ).delete(synchronize_session=False)
    counts["application_notes"] = ApplicationNote.query.filter(ApplicationNote.application_id.in_(ids)).delete(
        synchronize_session=False
    )
    counts["application_events"] = ApplicationEvent.query.filter(ApplicationEvent.application_id.in_(ids)).delete(
        synchronize_session=False
    )
    counts["applications"] = OpportunityApplication.query.filter(OpportunityApplication.id.in_(ids)).delete(
        synchronize_session=False
    )
    return counts


def erase_opportunities(user_id, schema):
    if not _ready(schema):
        return {}
    ids = [id_ for (id_,) in db.session.query(OpportunityApplication.id).filter_by(applicant_user_id=user_id).all()]
    counts = _delete_applications(ids)
    _privacy_context()
    counts["authored_notes"] = ApplicationNote.query.filter_by(author_user_id=user_id).delete(synchronize_session=False)
    counts["event_actors_redacted"] = ApplicationEvent.query.filter_by(actor_user_id=user_id).update(
        {"actor_user_id": None}, synchronize_session=False
    )
    counts["opportunity_creators_redacted"] = ClubOpportunity.query.filter_by(creator_user_id=user_id).update(
        {"creator_user_id": None}, synchronize_session=False
    )
    return {"recruiting": counts} if any(counts.values()) else {}


def purge_retained(*, limit=100, at=None):
    """Bounded maintenance transaction; callers commit. No lifetime signed exemption."""
    at = at or now()
    # Oldest verification first: bounded daily sweeps eventually cover every retained identity.
    from src.models.funding import ClubProgram
    from src.services.opportunities import reconcile_applications

    due = (
        OpportunityApplication.query.filter(OpportunityApplication.eligibility_checked_at <= at - timedelta(days=1))
        .order_by(OpportunityApplication.eligibility_checked_at, OpportunityApplication.id)
        .limit(limit)
        .all()
    )
    for program_id, opportunity_id in sorted({(a.program_id, a.opportunity_id) for a in due}):
        ClubProgram.query.filter_by(id=program_id).with_for_update().first()
        ClubOpportunity.query.filter_by(id=opportunity_id).with_for_update().first()
        apps = (
            OpportunityApplication.query.filter(
                OpportunityApplication.id.in_([a.id for a in due]),
                OpportunityApplication.opportunity_id == opportunity_id,
            )
            .populate_existing()
            .order_by(OpportunityApplication.id)
            .with_for_update()
            .all()
        )
        reconcile_applications(apps, at=at, locked=True)
    db.session.flush()
    # Same program -> opportunity -> application lock ordering as HTTP mutations.
    candidates = (
        ClubOpportunity.query.filter(
            sa.or_(
                sa.and_(ClubOpportunity.status.in_(("draft", "published")), ClubOpportunity.closes_at <= at),
                sa.and_(
                    ClubOpportunity.status.in_(("closed", "cancelled")),
                    sa.func.coalesce(ClubOpportunity.closed_at, ClubOpportunity.closes_at) <= at - timedelta(days=90),
                    ~sa.exists(
                        sa.select(OpportunityApplication.id).where(
                            OpportunityApplication.opportunity_id == ClubOpportunity.id
                        )
                    ),
                ),
                ClubOpportunity.id.in_(
                    sa.select(OpportunityApplication.opportunity_id).where(
                        OpportunityApplication.retention_expires_at <= at
                    )
                ),
            )
        )
        .order_by(ClubOpportunity.program_id, ClubOpportunity.id)
        .limit(limit)
        .all()
    )
    removed = {
        "applications": 0,
        "application_events": 0,
        "application_notes": 0,
        "notifications": 0,
        "opportunities": 0,
        "eligibility_checked": len(due),
    }
    for candidate in candidates:
        ClubProgram.query.filter_by(id=candidate.program_id).with_for_update().first()
        row = ClubOpportunity.query.filter_by(id=candidate.id).populate_existing().with_for_update().first()
        if row is None:
            continue
        if row.status in {"draft", "published"} and row.closes_at <= at:
            row.status, row.closed_at = "closed", row.closes_at
            row.version += 1
        expired = (
            OpportunityApplication.query.filter(
                OpportunityApplication.opportunity_id == row.id,
                OpportunityApplication.retention_expires_at <= at,
                sa.or_(
                    OpportunityApplication.trial_at.is_(None),
                    OpportunityApplication.trial_at <= at,
                    ~OpportunityApplication.reservation_state.in_(("pending", "confirmed")),
                ),
            )
            .order_by(OpportunityApplication.retention_expires_at, OpportunityApplication.id)
            .limit(max(0, limit - removed["applications"]))
            .with_for_update()
            .all()
        )
        counts = _delete_applications([app.id for app in expired])
        for key, count in counts.items():
            removed[key] += count
        if (
            row.status in {"closed", "cancelled"}
            and (row.closed_at or row.closes_at) + timedelta(days=90) <= at
            and not OpportunityApplication.query.filter_by(opportunity_id=row.id).first()
        ):
            db.session.delete(row)
            removed["opportunities"] += 1
    return removed
