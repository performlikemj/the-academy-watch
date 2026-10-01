"""Invalidate consent in the source writer's transaction, including dark-period edits."""

from datetime import timedelta
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.orm import Session
from src.models.funding import ClubRosterMember
from src.models.highlights import (
    HighlightConsentEvent,
    HighlightFootageReview,
    HighlightRenderJob,
    PlayerHighlight,
    now,
)
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry, VideoTracklet

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
            if ordinary_expiry:
                continue  # independent rendered assets survive the raw-footage retention sweep
            if row in session.deleted or any(state.attrs[key].history.has_changes() for key in MATCH_FIELDS):
                matches.add(row.id)
        elif isinstance(row, HighlightFootageReview):
            if row in session.deleted or session.is_modified(row, include_collections=False):
                matches.add(row.video_match_id)
        elif isinstance(row, ClubRosterMember):
            if row in session.deleted or any(
                state.attrs[key].history.has_changes()
                for key in ("player_api_id", "local_player_id", "program_id", "squad_id")
            ):
                matches.update(
                    session.connection()
                    .execute(
                        sa.select(VideoRosterEntry.video_match_id).where(
                            VideoRosterEntry.club_roster_member_id == row.id
                        )
                    )
                    .scalars()
                )
        elif isinstance(row, (VideoRosterEntry, VideoTracklet, VideoPlayerReport)):
            if row in session.deleted or session.is_modified(row, include_collections=False):
                matches.add(row.video_match_id)
    for row in session.new:
        if isinstance(row, (VideoRosterEntry, VideoTracklet, VideoPlayerReport)) and row.video_match_id:
            matches.add(row.video_match_id)
    if not matches:
        return
    connection = session.connection()
    if not sa.inspect(connection).has_table("player_highlights"):
        return
    # Lock order: match -> highlight -> render jobs. Same as decision/finalization.
    connection.execute(
        sa.select(VideoMatch.id).where(VideoMatch.id.in_(matches)).order_by(VideoMatch.id).with_for_update()
    )
    rows = connection.execute(
        sa.select(PlayerHighlight.id, PlayerHighlight.version, PlayerHighlight.source_version)
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
