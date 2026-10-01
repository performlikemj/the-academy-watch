"""Read-only bounded club inbox. Queue keys are absent without their live capability."""

import sqlalchemy as sa
from src.models.club_access import VideoMatchCoverage
from src.models.contact import ContactRequest
from src.models.funding import ClubProgram, ClubRosterMember
from src.models.league import UserAccount, db
from src.models.opportunities import ClubOpportunity, OpportunityApplication, now
from src.models.scout_attendance import ScoutAttendance
from src.models.trust import ScoutVerification
from src.models.video import VideoMatch, VideoRosterEntry
from src.services import opportunities
from src.services import scout_attendance as attendance
from src.services.club_access import current_access, match_bytes_in_scope, match_summary
from src.services.public_adult import public_adult_ids


def summary(program_id, *, accepted_after=None):
    access = current_access()
    result = {"program_id": program_id, "queues": {}}
    queues = result["queues"]
    if access.can("recruiting") and opportunities.applications_enabled():
        counts = {}
        posts = (
            ClubOpportunity.query.filter_by(program_id=program_id)
            .order_by(ClubOpportunity.created_at.desc(), ClubOpportunity.id)
            .limit(31)
            .all()
        )
        result["applications_posts_has_more"] = len(posts) > 30
        posts = posts[:30]
        # Bounded sample, clearly labelled; canonical eligibility stays ahead of counts.
        apps = (
            (
                OpportunityApplication.query.filter(
                    OpportunityApplication.program_id == program_id,
                    OpportunityApplication.opportunity_id.in_([p.id for p in posts]),
                    OpportunityApplication.retention_expires_at > now(),
                )
                .order_by(OpportunityApplication.submitted_at.desc(), OpportunityApplication.id)
                .limit(101)
                .all()
            )
            if posts
            else []
        )
        result["applications_partial"] = len(apps) > 100
        eligible = opportunities.eligible_application_claims(apps[:100])
        for app in apps[:100]:
            if app.id in eligible:
                item = counts.setdefault(app.opportunity_id, {"total": 0, "new": 0})
                item["total"] += 1
                item["new"] += app.status == "new"
        queues["applications"] = [
            {"opportunity_id": p.id, "title": p.title, **counts.get(p.id, {"total": 0, "new": 0})} for p in posts
        ]
    if access.can("contact"):
        if opportunities.enabled("CONTACT_RAIL_ENABLED"):
            rows = (
                ContactRequest.query.filter_by(club_program_id=program_id, club_consent_status="pending")
                .filter(ContactRequest.status.in_(("pending", "accepted")), ContactRequest.expires_at > now())
                .order_by(ContactRequest.created_at)
                .limit(31)
                .all()
            )
            result["introductions_has_more"] = len(rows) > 30
            rows = rows[:30]
            eligible = public_adult_ids(r.player_api_id for r in rows)
            queues["introductions"] = [
                {"id": r.id, "created_at": opportunities.iso(r.created_at)} for r in rows if r.player_api_id in eligible
            ]
        program = ClubProgram.query.filter_by(id=program_id).filter(opportunities.public_club_eligibility()).first()
        for state, queue in (("pending", "attendance"), ("accepted", "accepted_attendance")):
            rows = (
                (
                    db.session.query(ScoutAttendance, ClubOpportunity, ScoutVerification)
                    .join(ClubOpportunity, ClubOpportunity.id == ScoutAttendance.opportunity_id)
                    .join(UserAccount, UserAccount.id == ScoutAttendance.scout_user_id)
                    .join(
                        ScoutVerification,
                        sa.and_(
                            ScoutVerification.user_account_id == UserAccount.id, ScoutVerification.status == "approved"
                        ),
                    )
                    .filter(
                        ScoutAttendance.program_id == program_id,
                        ScoutAttendance.status == state,
                        ScoutAttendance.retention_expires_at > now(),
                        UserAccount.account_status == "active",
                        UserAccount.is_tombstone.is_(False),
                        ClubOpportunity.type.in_(("trial", "open_session")),
                        ClubOpportunity.status.in_(("published", "closed")),
                        # Accepted permissions remain visible for check-in/rescinds;
                        # only undecided requests expire at session start.
                        sa.func.coalesce(ClubOpportunity.starts_at, ClubOpportunity.ends_at) > now()
                        if state == "pending"
                        else sa.true(),
                    )
                    .filter(
                        ScoutAttendance.id > accepted_after if state == "accepted" and accepted_after else sa.true()
                    )
                    .order_by(ScoutAttendance.id)
                    .limit(31)
                    .all()
                )
                if program
                else []
            )
            queues[queue] = [
                attendance.serialize(row, club=True, opp=opp, program=program, scout=scout, trusted=True)
                for row, opp, scout in rows[:30]
            ]
            if state == "accepted":
                queues[queue] = [
                    {k: r[k] for k in ("id", "opportunity_id", "title", "status", "version", "scout")}
                    for r in queues[queue]
                ]
            result[queue + "_has_more"] = len(rows) > 30
            if state == "accepted":
                result["accepted_next_cursor"] = rows[29][0].id if len(rows) > 30 else None
    if access.can("matches.view"):
        team_sheet, analysing = [], []
        matches = (
            VideoMatch.query.filter(
                VideoMatch.club_program_id == program_id,
                VideoMatch.status.in_(("uploaded", "preflight", "queued", "processing")),
            )
            .order_by(VideoMatch.created_at.desc())
            .limit(31)
            .all()
        )
        result["matches_has_more"] = len(matches) > 30
        matches = matches[:30]
        ids = [m.id for m in matches]
        roster = VideoRosterEntry.query.filter(VideoRosterEntry.video_match_id.in_(ids)).all() if ids else []
        roster_ids = {m: [] for m in ids}
        for r in roster:
            roster_ids[r.video_match_id].append(r.club_roster_member_id)
        coverage = (
            VideoMatchCoverage.query.filter(VideoMatchCoverage.video_match_id.in_(ids)).all()
            if ids and not access.whole_club
            else []
        )
        coverage_by_match = {m: [] for m in ids}
        for r in coverage:
            coverage_by_match[r.video_match_id].append(r)
        member_ids = {r.club_roster_member_id for r in [*roster, *coverage] if r.club_roster_member_id is not None}
        members = (
            {
                r.id: r
                for r in ClubRosterMember.query.filter(
                    ClubRosterMember.id.in_(member_ids), ClubRosterMember.program_id == program_id
                ).all()
            }
            if member_ids and not access.whole_club
            else {}
        )
        evidence = {"roster": roster_ids, "coverage": coverage_by_match, "members": members}
        for match in matches:
            # Includes durable all-roster coverage, completed snapshot and assigned-squad rules.
            if not match_bytes_in_scope(match, scope_evidence=evidence):
                continue
            if match.status == "uploaded" and not roster_ids[match.id]:
                team_sheet.append(match_summary(match))
            elif match.status in {"preflight", "queued", "processing"}:
                analysing.append(match_summary(match))
        queues["team_sheet"] = team_sheet[:30]
        queues["analysing"] = analysing[:30]
    return result
