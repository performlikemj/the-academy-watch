"""Private, revision-scoped practice actions and coach-reviewed match evidence."""

import math
from datetime import date

from src.models.player_feedback import FeedbackError, plain_text


def action_payload(value):
    if value is None:
        return None
    if not isinstance(value, dict) or set(value) != {"focus", "practice", "success", "review_on"}:
        raise FeedbackError()
    result = {
        key: plain_text(value[key], limit) for key, limit in (("focus", 160), ("practice", 1000), ("success", 500))
    }
    review_on = value["review_on"]
    if review_on is not None:
        if not isinstance(review_on, str):
            raise FeedbackError()
        try:
            parsed = date.fromisoformat(review_on)
        except ValueError:
            raise FeedbackError() from None
        if parsed.isoformat() != review_on:
            raise FeedbackError()
    result["review_on"] = review_on
    return result


def progress_payload(payload, current, *, coach=False):
    if not isinstance(payload, dict) or set(payload) != {"expected_version", "status", "note"}:
        raise FeedbackError()
    version = payload["expected_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        raise FeedbackError()
    if version != (current or {}).get("version", 0):
        raise FeedbackError("development_progress_conflict", 409)
    allowed = {"working_on_it", "reviewed"} if coach else {"working_on_it", "ready_for_review"}
    if not isinstance(payload["status"], str) or payload["status"] not in allowed:
        raise FeedbackError()
    note = payload["note"]
    if not isinstance(note, str) or len(note) > 1000:
        raise FeedbackError()
    note = plain_text(note, 1000) if note.strip() else ""
    if (coach or payload["status"] == "ready_for_review") and not note:
        raise FeedbackError()
    if coach and (current or {}).get("status") != "ready_for_review":
        raise FeedbackError("development_not_ready", 409)
    return version, payload["status"], note


def update_progress(row, payload, *, coach=False):
    from src.models.club_invitation import utcnow

    if not row.development_action:
        raise FeedbackError("development_action_unavailable", 409)
    current = row.development_progress or {}
    version, status, note = progress_payload(payload, current, coach=coach)
    stamp = utcnow().isoformat() + "Z"
    event = {
        "version": version + 1,
        "actor": "coach" if coach else "player",
        "status": status,
        "note": note,
        "at": stamp,
    }
    row.development_progress = {
        "version": version + 1,
        "status": status,
        "reflection": current.get("reflection", "") if coach else note,
        "coach_note": note if coach else None,
        "updated_at": stamp,
        "history": [*(current.get("history") or []), event][-20:],
    }


def evidence_candidates(session, invitation):
    """Return a bounded allowlist of grounded captions for this finalized player.

    Never match names or shirt numbers alone, return footage URLs, or invent a
    practice prescription. The coach explicitly selects and edits each draft.
    """
    from src.models.video import VideoMatch, VideoPlayerReport

    query = (
        session.query(VideoPlayerReport, VideoMatch)
        .join(VideoMatch, VideoMatch.id == VideoPlayerReport.video_match_id)
        .filter(
            VideoMatch.club_program_id == invitation.program_id,
            VideoMatch.status == "finalized",
            VideoPlayerReport.club_program_id_at_finalize == invitation.program_id,
        )
    )
    query = query.filter(
        VideoPlayerReport.club_player_api_id_at_finalize == invitation.player_api_id
        if invitation.player_api_id > 0
        else VideoPlayerReport.club_local_player_id_at_finalize == -invitation.player_api_id
    )
    candidates = []
    for report, match in query.order_by(VideoMatch.id.desc(), VideoPlayerReport.id.desc()).limit(6):
        capture = match.capture_meta if isinstance(match.capture_meta, dict) else {}
        analysis = capture.get("qwen_analysis")
        if not isinstance(analysis, dict):
            continue
        captions = analysis.get("window_captions")
        if not isinstance(captions, list):
            continue
        for index, caption in enumerate(captions[:500]):
            if not isinstance(caption, dict) or caption.get("grounded") is not True:
                continue
            roster_id = caption.get("roster_entry_id")
            if isinstance(roster_id, bool) or not isinstance(roster_id, int) or roster_id != report.roster_entry_id:
                continue
            stamp = caption.get("box_t")
            if isinstance(stamp, bool) or not isinstance(stamp, (int, float)):
                continue
            try:
                if not math.isfinite(stamp) or stamp < 0 or (match.duration_s is not None and stamp > match.duration_s):
                    continue
            except OverflowError:
                continue
            try:
                text = plain_text(caption.get("caption"), 1000)
            except FeedbackError:
                continue
            candidates.append(
                {
                    "id": f"{match.id}:{report.roster_entry_id}:{index}",
                    "video_match_id": match.id,
                    "label": text[:160],
                    "text": text,
                    "timestamp_s": float(stamp),
                    "source": "grounded_ai_observation",
                }
            )
            if len(candidates) == 12:
                return candidates
    return candidates
