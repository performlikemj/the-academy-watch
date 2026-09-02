#!/usr/bin/env python3
"""Seed the dedicated, synthetic-only club-console fixture used by App Sim."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("SKIP_API_HANDSHAKE", "1")

ALLOW_ENV = "ALLOW_SIM_FIXTURE_SEED"
SCRIPT_ACTOR = "sim-fixture-seed"
SIM_LEAGUE_NAME = "Synthetic sim fixture league"
SIM_PROGRAM_NAME = "Academy Watch Synthetic Sim"
SIM_PROGRAM_SLUG = "academy-watch-synthetic-sim-fixture"
SIM_MEMBER_MARKER = "sim-fixture-seed:synthetic-player"
SIM_MATCH_BLOB_MARKER = "sim-fixture://synthetic-match"
SYNTHETIC_BRIEF = "Maintain wide support before receiving\nRecover inside after possession changes."
COACHS_BRIEF_HONEST_LIMIT = (
    "Coach's-brief expectations were checked against sampled frames only; "
    "'no evidence' is not 'did not happen'; an evidence frame verifies the "
    "player's identity and location, not the behaviour."
)


class SimFixtureRefused(RuntimeError):
    """Raised when the seed target or existing marker rows are unsafe."""


def guard_runtime_environment() -> None:
    from scripts.dev.bridge_match_to_club import _looks_like_production

    if os.getenv(ALLOW_ENV) != "1":
        raise SimFixtureRefused(f"refusing sim fixture seed: set {ALLOW_ENV}=1 explicitly")
    for env_name in ("FLASK_ENV", "APP_ENV"):
        value = os.getenv(env_name)
        if _looks_like_production(value):
            raise SimFixtureRefused(f"refusing sim fixture seed: {env_name}={value!r} looks like production")


def _synthetic_analysis(brief_hash: str) -> dict:
    expectation_checks = [
        {
            "expectation_index": 1,
            "verdict": "evidence_found",
            "box_t": 21.25,
            "box": [180, 90, 310, 430],
        },
        {
            "expectation_index": 2,
            "verdict": "no_evidence",
            "box_t": None,
            "box": None,
        },
    ]
    brief_checks = [
        {
            "expectation_index": check["expectation_index"],
            "brief_hash": brief_hash,
            "verdict": check["verdict"],
            **({"t": check["box_t"], "box": check["box"], "iou": 0.72} if check["verdict"] == "evidence_found" else {}),
        }
        for check in expectation_checks
    ]
    return {
        "schema_version": "qwen-analysis-v1",
        "model": "synthetic-sim-fixture",
        "generated_at": "2026-09-03T00:00:00+00:00",
        "sampling": {
            "interval_s": 30,
            "frames_analyzed": 2,
            "frames_failed": 0,
            "in_play_windows": [[0, 60]],
            "zone_coverage": {"left": 0, "central": 2, "right": 0, "unclear": 0},
            "captions_failed": 0,
            "captions_action_type_coerced": 0,
            "captions_action_type_recovered": 0,
            "captions_zone_coerced": 0,
            "captions_claims_dropped": 0,
            "brief_checks_total": 2,
            "brief_checks_evidence_found": 1,
            "brief_checks_downgraded": 0,
            "notes_scope": "ours",
            "grounding": {
                "caption_windows": 0,
                "caption_grounded": 0,
                "read_observations": 1,
                "read_grounded": 1,
                "iou_threshold": 0.5,
                "containment_threshold": 0.8,
            },
        },
        "match_summary": "Synthetic match summary for the sim fixture.",
        "team_analysis": [
            {
                "kit_color": "blue",
                "is_ours": True,
                "style": "Synthetic team style.",
                "strengths": ["Synthetic strength."],
                "weaknesses": ["Synthetic limitation."],
                "shape_notes": "Synthetic shape note.",
            }
        ],
        "player_notes": [
            {
                "kit_color": "blue",
                "jersey_number": 8,
                "observations": ["Synthetic verified observation."],
                "evidence": [{"t": 21.25, "box": [180, 90, 310, 430], "iou": 0.72}],
                "times_seen": 1,
                "confidence": "medium",
                "read_model": "synthetic-sim-fixture",
                "brief_checks": brief_checks,
            }
        ],
        "honest_limits": [
            "Synthetic sampled frames do not represent a full match.",
            COACHS_BRIEF_HONEST_LIMIT,
        ],
        "window_captions": [],
    }


def seed_sim_fixture(*, manager_email: str) -> dict:
    from sqlalchemy import func
    from src.models.funding import (
        ClubProgram,
        ClubProgramClaim,
        ClubProgramManager,
        ClubRosterMember,
        FundingLeague,
    )
    from src.models.league import UserAccount, db
    from src.models.showcase import LocalPlayer
    from src.models.video import VideoMatch, VideoRosterEntry, VideoTracklet
    from src.services.coach_brief import brief_payload

    normalized_email = manager_email.strip().lower()
    manager = UserAccount.query.filter(func.lower(UserAccount.email) == normalized_email).first()
    if manager is None:
        raise SimFixtureRefused(f"sim fixture manager account {normalized_email!r} was not found")

    now = datetime.now(UTC)
    program = ClubProgram.query.filter_by(slug=SIM_PROGRAM_SLUG).first()
    members = []
    if program is not None:
        if program.name != SIM_PROGRAM_NAME or program.country != "Development":
            raise SimFixtureRefused("existing sim program marker has incompatible identity fields")
        if program.system_brief_body not in (None, SYNTHETIC_BRIEF):
            raise SimFixtureRefused("sim program contains a non-synthetic system brief")
        members = ClubRosterMember.query.filter_by(program_id=program.id).all()
        if any(member.coach_brief_body not in (None, SYNTHETIC_BRIEF) for member in members):
            raise SimFixtureRefused("sim program contains a non-synthetic coach brief")

    league = FundingLeague.query.filter_by(
        name=SIM_LEAGUE_NAME,
        country="Development",
        region="Synthetic",
    ).first()
    if league is None:
        league = FundingLeague(
            name=SIM_LEAGUE_NAME,
            country="Development",
            region="Synthetic",
            level="recreational",
            age_bands=[],
            gender_program="both",
            season_calendar="calendar_year",
            data_tier="film_room",
            registry_status="approved",
            admission_state="open",
            proposed_by_user_id=manager.id,
            reviewed_by=SCRIPT_ACTOR,
            review_reason="Synthetic App Sim fixture",
            reviewed_at=now,
        )
        db.session.add(league)
        db.session.flush()

    if program is None:
        program = ClubProgram(
            funding_league_id=league.id,
            name=SIM_PROGRAM_NAME,
            legal_name=SIM_PROGRAM_NAME,
            slug=SIM_PROGRAM_SLUG,
            country="Development",
            region="Synthetic",
            currency="USD",
            provenance_tier="film_room_verified",
            platform_status="approved",
            donations_enabled=False,
            emergency_hidden=False,
            reviewed_by=SCRIPT_ACTOR,
            review_reason="Synthetic App Sim fixture",
            reviewed_at=now,
            verified_at=now,
        )
        db.session.add(program)
        db.session.flush()

    program.platform_status = "approved"
    program.emergency_hidden = False
    program.system_brief_body = None
    program.system_brief_updated_at = None
    program.system_brief_updated_by_user_id = None

    claim = ClubProgramClaim.query.filter_by(program_id=program.id, user_account_id=manager.id).first()
    if claim is None:
        claim = ClubProgramClaim(
            program_id=program.id,
            user_account_id=manager.id,
            relationship_type="club_official",
            applicant_message="Synthetic App Sim fixture",
        )
        db.session.add(claim)
        db.session.flush()
    claim.status = "approved"
    claim.reviewed_by = SCRIPT_ACTOR
    claim.review_reason = "Synthetic App Sim fixture"
    claim.reviewed_at = claim.reviewed_at or now

    grant = ClubProgramManager.query.filter_by(program_id=program.id, user_account_id=manager.id).first()
    if grant is None:
        grant = ClubProgramManager(
            program_id=program.id,
            user_account_id=manager.id,
            source_claim_id=claim.id,
            status="active",
            granted_by=SCRIPT_ACTOR,
            granted_at=now,
        )
        db.session.add(grant)
    else:
        grant.source_claim_id = claim.id
        grant.status = "active"
        grant.revoked_by = None
        grant.revoked_reason = None
        grant.revoked_at = None

    if not members:
        members = ClubRosterMember.query.filter_by(program_id=program.id).all()
    if any(member.note != SIM_MEMBER_MARKER for member in members):
        raise SimFixtureRefused("sim program contains an unmarked roster member")
    member = members[0] if members else None
    if len(members) > 1:
        raise SimFixtureRefused("sim program contains multiple synthetic roster members")
    if member is None:
        local_player = LocalPlayer(
            display_name="Synthetic Sim Player",
            birth_date=date(2000, 1, 1),
            position="Midfielder",
            country="Development",
            club_name=SIM_PROGRAM_NAME,
            status="approved",
            provenance="user",
            created_by_user_id=manager.id,
            reviewed_by=SCRIPT_ACTOR,
            reviewed_at=now,
        )
        db.session.add(local_player)
        db.session.flush()
        member = ClubRosterMember(
            program_id=program.id,
            local_player_id=local_player.id,
            added_by_user_id=manager.id,
            role="Midfielder",
            note=SIM_MEMBER_MARKER,
        )
        db.session.add(member)
        db.session.flush()
    elif member.player_api_id is not None or member.local_player_id is None:
        raise SimFixtureRefused("sim roster marker points to an incompatible subject")
    else:
        local_player = db.session.get(LocalPlayer, member.local_player_id)
        if (
            local_player is None
            or local_player.created_by_user_id != manager.id
            or local_player.reviewed_by != SCRIPT_ACTOR
        ):
            raise SimFixtureRefused("sim roster marker points to an unowned local player")
        local_player.display_name = "Synthetic Sim Player"
        local_player.birth_date = date(2000, 1, 1)
        local_player.position = "Midfielder"
        local_player.country = "Development"
        local_player.club_name = SIM_PROGRAM_NAME
        local_player.status = "approved"
    member.coach_brief_body = None
    member.brief_updated_at = None
    member.brief_updated_by_user_id = None

    matches = VideoMatch.query.filter_by(club_program_id=program.id).all()
    if any(match.blob_path != SIM_MATCH_BLOB_MARKER for match in matches):
        raise SimFixtureRefused("sim program contains an unmarked video match")
    if len(matches) > 1:
        raise SimFixtureRefused("sim program contains multiple synthetic video matches")
    match = matches[0] if matches else None
    if match is None:
        match = VideoMatch(club_program_id=program.id, blob_path=SIM_MATCH_BLOB_MARKER)
        db.session.add(match)
        db.session.flush()

    brief = brief_payload(SYNTHETIC_BRIEF)
    if brief is None:
        raise SimFixtureRefused("synthetic brief no longer satisfies the shared brief contract")
    match.opponent_name = "Synthetic Opponent"
    match.match_date = date(2026, 9, 3)
    match.competition = "Synthetic Sim Match"
    match.our_kit_color = "blue"
    match.opponent_kit_color = "orange"
    match.capture_meta = {"qwen_analysis": _synthetic_analysis(brief["hash"]), "sim_fixture": True}
    match.duration_s = 60.0
    match.kickoff_s = 0.0
    match.our_team_cluster = 0
    match.status = "finalized"
    match.finalized_at = now

    entries = match.roster_entries.all()
    if len(entries) > 1:
        raise SimFixtureRefused("sim match contains multiple roster entries")
    entry = entries[0] if entries else None
    if entry is None:
        entry = VideoRosterEntry(
            video_match_id=match.id,
            player_name="Synthetic Sim Player",
            jersey_number=8,
            position="Midfielder",
            club_roster_member_id=member.id,
        )
        db.session.add(entry)
        db.session.flush()
    entry.player_name = "Synthetic Sim Player"
    entry.jersey_number = 8
    entry.position = "Midfielder"
    entry.club_roster_member_id = member.id

    tracklets = match.tracklets.all()
    if len(tracklets) > 1:
        raise SimFixtureRefused("sim match contains multiple tracklets")
    tracklet = tracklets[0] if tracklets else None
    if tracklet is None:
        tracklet = VideoTracklet(video_match_id=match.id)
        db.session.add(tracklet)
    tracklet.kind = "chain"
    tracklet.pipeline_key = "SIM#8"
    tracklet.team_cluster = 0
    tracklet.suggested_number = 8
    tracklet.confidence = "high"
    tracklet.contaminated = False
    tracklet.first_s = 20.0
    tracklet.last_s = 25.0
    tracklet.visible_s = 5.0
    tracklet.evidence = {"member_fragment_ids": [], "votes": {"sim": {"8": 1}}}
    tracklet.roster_entry_id = entry.id
    tracklet.dismissed = False

    db.session.commit()
    return {
        "program_id": program.id,
        "program_name": program.name,
        "program_slug": program.slug,
        "match_id": match.id,
        "member_id": member.id,
        "brief_hash": brief["hash"],
    }


def execute_seed(app, *, manager_email: str) -> dict:
    from scripts.dev.bridge_match_to_club import guard_database_target
    from src.models.league import db

    guard_runtime_environment()
    with app.app_context():
        guard_database_target(db.engine.url)
        try:
            return seed_sim_fixture(manager_email=manager_email)
        except Exception:
            db.session.rollback()
            raise


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manager-email", required=True)
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    try:
        guard_runtime_environment()
        from src.main import app

        summary = execute_seed(app, manager_email=args.manager_email)
    except SimFixtureRefused as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(
        "Synthetic sim fixture seeded: "
        f"{summary['program_name']} (program={summary['program_id']}, match={summary['match_id']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
