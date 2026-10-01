"""Highlight privacy lifecycle, including private asset cleanup while the rollout is dark."""

from datetime import timedelta

import sqlalchemy as sa
from src.models.highlights import HighlightRenderJob, now
from src.models.league import db


def export_highlights(user, schema):
    result = {}
    if schema.has_columns("player_highlights", "recipient_user_id"):
        rows = db.session.execute(
            sa.text(
                "SELECT id,program_id,title,start_s,end_s,player_decision,decision_at,revoked_at,render_status,created_at "
                "FROM player_highlights WHERE recipient_user_id=:uid OR picker_user_id=:uid ORDER BY created_at"
            ),
            {"uid": user.id},
        ).mappings()
        values = [
            {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in row.items()}
            for row in rows
        ]
        if values:
            result["highlights"] = values
    if schema.has_columns("highlight_consent_events", "actor_user_id"):
        values = [
            dict(row)
            for row in db.session.execute(
                sa.text(
                    "SELECT highlight_id,action,version,source_version,created_at FROM highlight_consent_events WHERE actor_user_id=:uid ORDER BY id"
                ),
                {"uid": user.id},
            ).mappings()
        ]
        if values:
            result["highlight_decisions"] = [
                {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in row.items()}
                for row in values
            ]
    if schema.has_columns("highlight_footage_reviews", "reviewer_user_id"):
        values = [
            dict(row)
            for row in db.session.execute(
                sa.text(
                    "SELECT video_match_id,classification,reviewed_at FROM highlight_footage_reviews WHERE reviewer_user_id=:uid"
                ),
                {"uid": user.id},
            ).mappings()
        ]
        if values:
            result["highlight_recording_reviews"] = [
                {key: value.isoformat() if hasattr(value, "isoformat") else value for key, value in row.items()}
                for row in values
            ]
    return result


def erase_highlights(user_id, schema):
    if not schema.has_columns("player_highlights", "recipient_user_id"):
        return {}
    # Revoke/remove the subject's cuts; remove picks and footage reviews authored by the erased account too.
    ids = [
        row[0]
        for row in db.session.execute(
            sa.text(
                "SELECT id FROM player_highlights WHERE recipient_user_id=:uid OR picker_user_id=:uid OR decision_user_id=:uid "
                "OR video_match_id IN (SELECT video_match_id FROM highlight_footage_reviews WHERE reviewer_user_id=:uid)"
            ),
            {"uid": user_id},
        )
    ]
    if ids:
        params = {"ids": ids}
        paths = {
            row[0]
            for row in db.session.execute(
                sa.text(
                    "SELECT output_blob_path FROM player_highlights WHERE id IN :ids AND output_blob_path IS NOT NULL "
                    "UNION SELECT blob_path FROM highlight_render_jobs WHERE highlight_id IN :ids AND blob_path IS NOT NULL"
                ).bindparams(sa.bindparam("ids", expanding=True)),
                params,
            )
        }
        for path in paths:
            # Wait beyond the maximum worker lease: a late upload cannot outrun erasure cleanup.
            db.session.add(
                HighlightRenderJob(kind="highlight_delete", blob_path=path, created_at=now() + timedelta(minutes=20))
            )
        db.session.execute(
            sa.text("DELETE FROM highlight_consent_events WHERE highlight_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)
            ),
            params,
        )
        db.session.execute(
            sa.text(
                "UPDATE highlight_render_jobs SET highlight_id=NULL,status='cancelled',lease_token=NULL WHERE highlight_id IN :ids"
            ).bindparams(sa.bindparam("ids", expanding=True)),
            params,
        )
        db.session.execute(
            sa.text("DELETE FROM player_highlights WHERE id IN :ids").bindparams(sa.bindparam("ids", expanding=True)),
            params,
        )
    db.session.execute(sa.text("DELETE FROM highlight_consent_events WHERE actor_user_id=:uid"), {"uid": user_id})
    db.session.execute(sa.text("DELETE FROM highlight_footage_reviews WHERE reviewer_user_id=:uid"), {"uid": user_id})
    return {"highlights_deleted": len(ids)} if ids else {}
