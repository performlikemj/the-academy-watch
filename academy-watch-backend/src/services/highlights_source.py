"""Invalidate consent in the source writer's transaction, including dark-period edits."""

from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4
from weakref import WeakKeyDictionary

import sqlalchemy as sa
from sqlalchemy.orm import Session
from src.models.funding import ClubRosterMember, ClubSquad
from src.models.highlights import (
    HighlightConsentEvent,
    HighlightFootageReview,
    HighlightRenderJob,
    PlayerHighlight,
    now,
)
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry, VideoTracklet
from src.services.highlights_squads import squad_classification

# Positive discovery only: preapply can introduce the table after process start.
# Engines are replaced on fixture/schema lifecycle changes and process restarts.
_available_engines = WeakKeyDictionary()


def highlight_schema_available(connection):
    if _available_engines.get(connection.engine):
        return True
    available = sa.inspect(connection).has_table("player_highlights")
    if available:
        _available_engines[connection.engine] = True
    return available


MATCH_FIELDS = {
    "match_date",
    "blob_path",
    "blob_etag",
    "scoped_snapshot",
    "scoped_ready_etag",
    "duration_s",
    "finalized_at",
    "club_program_id",
    "squad_id",
    "our_team_cluster",
    "kickoff_s",
    "halftime_s",
    "second_half_kickoff_s",
}


@sa.event.listens_for(Session, "before_flush")
def invalidate_sources(session, flush_context, instances):
    matches = set()
    changed_contexts = set()
    for row in session.dirty | session.deleted:
        state = sa.inspect(row)
        if not state.persistent:
            continue
        if isinstance(row, VideoMatch):
            changed = {key for key in MATCH_FIELDS if state.attrs[key].history.has_changes()}
            ordinary_expiry = (
                row not in session.deleted
                and row.status == "expired"
                and state.attrs.status.history.deleted == ["finalized"]
                and row.blob_path is None
                and row.blob_etag is None
                and changed <= {"blob_path", "blob_etag"}
            )
            if changed & {"match_date", "squad_id", "finalized_at"}:
                changed_contexts.add(row.id)
            if ordinary_expiry:
                continue  # independent rendered assets survive the raw-footage retention sweep
            if row in session.deleted or any(state.attrs[key].history.has_changes() for key in MATCH_FIELDS):
                matches.add(row.id)
        elif isinstance(row, ClubSquad):
            previous = (
                session.connection()
                .execute(sa.select(ClubSquad.name, ClubSquad.kind, ClubSquad.age_limit).where(ClubSquad.id == row.id))
                .one()
            )
            old = SimpleNamespace(name=previous.name, kind=previous.kind, age_limit=previous.age_limit)
            if (
                row in session.deleted
                or squad_classification(old) != squad_classification(row)
                or any(state.attrs[key].history.has_changes() for key in ("kind", "age_limit"))
            ):
                changed_contexts.update(
                    session.connection()
                    .execute(
                        sa.select(VideoMatch.id).where(
                            sa.or_(
                                VideoMatch.squad_id == row.id,
                                VideoMatch.id.in_(
                                    sa.select(VideoRosterEntry.video_match_id)
                                    .join(
                                        ClubRosterMember, ClubRosterMember.id == VideoRosterEntry.club_roster_member_id
                                    )
                                    .where(ClubRosterMember.squad_id == row.id)
                                ),
                            )
                        )
                    )
                    .scalars()
                )
                matches.update(changed_contexts)
        elif isinstance(row, HighlightFootageReview):
            if row in session.deleted or any(
                state.attrs[key].history.has_changes()
                for key in (
                    "classification",
                    "source_etag",
                    "source_snapshot",
                    "reviewed_at",
                    "squad_adult_attested",
                    "source_context",
                    "classification_context",
                )
            ):
                matches.add(row.video_match_id)
        elif isinstance(row, ClubRosterMember):
            if row in session.deleted or any(
                state.attrs[key].history.has_changes()
                for key in ("player_api_id", "local_player_id", "program_id", "squad_id")
            ):
                affected = set(
                    session.connection()
                    .execute(
                        sa.select(VideoRosterEntry.video_match_id).where(
                            VideoRosterEntry.club_roster_member_id == row.id
                        )
                    )
                    .scalars()
                )
                matches.update(affected)
                changed_contexts.update(affected)
        elif isinstance(row, (VideoRosterEntry, VideoTracklet, VideoPlayerReport)):
            if row in session.deleted or session.is_modified(row, include_collections=False):
                matches.add(row.video_match_id)
    for row in session.new:
        if isinstance(row, (VideoRosterEntry, VideoTracklet, VideoPlayerReport)) and row.video_match_id:
            matches.add(row.video_match_id)
    if not matches:
        return
    connection = session.connection()
    if not highlight_schema_available(connection):
        return
    # Lock order: match -> highlight -> render jobs. Same as decision/finalization.
    connection.execute(
        sa.select(VideoMatch.id).where(VideoMatch.id.in_(matches)).order_by(VideoMatch.id).with_for_update()
    )
    if changed_contexts:
        connection.execute(
            sa.update(HighlightFootageReview)
            .where(HighlightFootageReview.video_match_id.in_(changed_contexts))
            .values(source_context=None)
        )
    rows = connection.execute(
        sa.select(
            PlayerHighlight.id, PlayerHighlight.version, PlayerHighlight.source_version, PlayerHighlight.player_decision
        )
        .where(PlayerHighlight.video_match_id.in_(matches), PlayerHighlight.revoked_at.is_(None))
        .order_by(PlayerHighlight.id)
        .with_for_update()
    ).all()
    if not rows:
        return
    ids = [row.id for row in rows]
    paths = set(
        connection.execute(sa.select(PlayerHighlight.output_blob_path).where(PlayerHighlight.id.in_(ids))).scalars()
    )
    paths.update(
        connection.execute(
            sa.select(HighlightRenderJob.blob_path).where(HighlightRenderJob.highlight_id.in_(ids))
        ).scalars()
    )
    assets = [
        {
            "id": str(uuid4()),
            "kind": "highlight_delete",
            "status": "queued",
            "attempt": 0,
            "blob_path": path,
            "created_at": now() + timedelta(minutes=20),
        }
        for path in paths
        if path
    ]
    if assets:
        connection.execute(sa.insert(HighlightRenderJob), assets)
    connection.execute(
        sa.update(PlayerHighlight)
        .where(PlayerHighlight.id.in_(ids))
        .values(
            player_decision="pending",
            approved_source_version=None,
            revoked_at=now(),
            revoke_reason="source_changed",
            render_status="stale",
            version=PlayerHighlight.version + 1,
            source_version=PlayerHighlight.source_version + 1,
        )
    )
    connection.execute(
        sa.update(HighlightRenderJob)
        .where(HighlightRenderJob.highlight_id.in_(ids), HighlightRenderJob.status.in_(("queued", "running")))
        .values(status="cancelled", lease_token=None)
    )
    connection.execute(
        sa.insert(HighlightConsentEvent),
        [
            {
                "highlight_id": row.id,
                "actor_user_id": None,
                "action": "source_changed",
                "version": row.version + 1,
                "source_version": row.source_version + 1,
                "created_at": now(),
            }
            for row in rows
        ],
    )
    notify_source_changes(connection, [row.id for row in rows if row.player_decision != "private"])


def notify_source_changes(connection, ids):
    """Same-transaction neutral intents; SQL guards mirror this for non-ORM writers."""
    from src.models.funding import ClubProgramClaim, ClubProgramManager
    from src.models.p2_foundation import NotificationOutbox

    managers = (
        sa.select(ClubProgramManager.program_id, ClubProgramManager.user_account_id)
        .join(ClubProgramClaim, ClubProgramClaim.id == ClubProgramManager.source_claim_id)
        .where(
            ClubProgramManager.status == "active",
            ClubProgramClaim.status == "approved",
            ClubProgramClaim.program_id == ClubProgramManager.program_id,
            ClubProgramClaim.user_account_id == ClubProgramManager.user_account_id,
        )
        .subquery()
    )
    recipients = sa.union(
        sa.select(
            PlayerHighlight.id,
            PlayerHighlight.version,
            PlayerHighlight.video_match_id,
            PlayerHighlight.recipient_user_id.label("uid"),
        ).where(PlayerHighlight.id.in_(ids), PlayerHighlight.recipient_user_id.is_not(None)),
        sa.select(
            PlayerHighlight.id, PlayerHighlight.version, PlayerHighlight.video_match_id, managers.c.user_account_id
        )
        .join(managers, managers.c.program_id == PlayerHighlight.program_id)
        .where(PlayerHighlight.id.in_(ids)),
    )
    event = str(uuid4())
    grouped = {}
    for hid, version, mid, uid in connection.execute(recipients):
        grouped.setdefault((mid, uid), (hid, version))
    values = [
        dict(
            dedupe_key=f"highlight_source:{mid}:{event}:{uid}",
            recipient_user_id=uid,
            event_type="highlight_source_changed",
            entity_type="user_account",
            entity_id=str(uid),
            template="highlight_source_changed",
            payload={"highlight_id": hid, "version": version},
        )
        for (mid, uid), (hid, version) in grouped.items()
    ]
    if values:
        connection.execute(sa.insert(NotificationOutbox), values)
