"""Read-only club inbox. Queue keys are absent without their live capability."""

from src.models.contact import ContactRequest
from src.models.opportunities import ClubOpportunity, OpportunityApplication, now
from src.models.scout_attendance import ScoutAttendance
from src.models.video import VideoMatch, VideoRosterEntry
from src.services import opportunities
from src.services import scout_attendance as attendance
from src.services.club_access import current_access, match_bytes_in_scope, match_summary
from src.services.public_adult import public_adult_ids


def summary(program_id):
    access = current_access()
    result = {"program_id": program_id, "queues": {}}
    queues = result["queues"]
    if access.can("recruiting") and opportunities.applications_enabled():
        counts = {}
        # Batch current claim/adult/hold eligibility; no private applicant DTO or write-side reconciliation.
        last = None
        while True:
            query = OpportunityApplication.query.filter(
                OpportunityApplication.program_id == program_id, OpportunityApplication.retention_expires_at > now()
            )
            if last:
                query = query.filter(OpportunityApplication.id > last)
            apps = query.order_by(OpportunityApplication.id).limit(100).all()
            if not apps:
                break
            eligible = opportunities.eligible_application_claims(apps)
            for app in apps:
                if app.id in eligible:
                    item = counts.setdefault(app.opportunity_id, {"total": 0, "new": 0})
                    item["total"] += 1
                    item["new"] += app.status == "new"
            last = apps[-1].id
        posts = (
            ClubOpportunity.query.filter(ClubOpportunity.program_id == program_id)
            .order_by(ClubOpportunity.created_at.desc())
            .limit(30)
            .all()
        )
        queues["applications"] = [
            {"opportunity_id": p.id, "title": p.title, **counts.get(p.id, {"total": 0, "new": 0})} for p in posts
        ]
    if access.can("contact"):
        if opportunities.enabled("CONTACT_RAIL_ENABLED"):
            rows = (
                ContactRequest.query.filter_by(club_program_id=program_id, club_consent_status="pending")
                .filter(ContactRequest.status.in_(("pending", "accepted")), ContactRequest.expires_at > now())
                .order_by(ContactRequest.created_at)
                .all()
            )
            eligible = public_adult_ids(r.player_api_id for r in rows)
            queues["introductions"] = [
                {"id": r.id, "created_at": opportunities.iso(r.created_at)} for r in rows if r.player_api_id in eligible
            ]
        requests = (
            ScoutAttendance.query.filter_by(program_id=program_id, status="pending")
            .filter(ScoutAttendance.retention_expires_at > now())
            .order_by(ScoutAttendance.created_at)
            .all()
        )
        visible = []
        for row in requests:
            if attendance.visible_event(
                opportunities.db.session.get(ClubOpportunity, row.opportunity_id), accepting=True
            ):
                try:
                    attendance.verified(row.scout_user_id)
                except attendance.Error:
                    continue
                visible.append(attendance.serialize(row, club=True))
        queues["attendance"] = visible[:30]
        result["attendance_has_more"] = len(visible) > 30
    if access.can("matches.view"):
        team_sheet, analysing = [], []
        matches = (
            VideoMatch.query.filter(
                VideoMatch.club_program_id == program_id,
                VideoMatch.status.in_(("uploaded", "preflight", "queued", "processing")),
            )
            .order_by(VideoMatch.created_at.desc())
            .all()
        )
        for match in matches:
            # Includes durable all-roster coverage, completed snapshot and assigned-squad rules.
            if not match_bytes_in_scope(match):
                continue
            if match.status == "uploaded" and not VideoRosterEntry.query.filter_by(video_match_id=match.id).first():
                team_sheet.append(match_summary(match))
            elif match.status in {"preflight", "queued", "processing"}:
                analysing.append(match_summary(match))
        queues["team_sheet"] = team_sheet[:30]
        queues["analysing"] = analysing[:30]
        result["matches_has_more"] = len(team_sheet) > 30 or len(analysing) > 30
    return result
