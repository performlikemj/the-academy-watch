#!/usr/bin/env python3
"""Attach an existing development video fixture to a private club console.

This script is intentionally unavailable unless the operator supplies the
explicit development opt-in. It must never be run against production.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path

from flask import current_app, has_app_context
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.environ.setdefault("SKIP_API_HANDSHAKE", "1")

ALLOW_ENV = "ALLOW_FIXTURE_BRIDGE"
DEV_LEAGUE_NAME = "Dev fixture league"
MY_CLUB_PATH = "/my-club"
SCRIPT_ACTOR = "dev-fixture-bridge"
COUNT_KEYS = (
    "funding_leagues",
    "club_programs",
    "program_claims",
    "program_managers",
    "local_players",
    "roster_members",
    "roster_entry_links",
)


class BridgeRefused(RuntimeError):
    """Raised when a safety guard or fixture invariant refuses the bridge."""


def _looks_like_production(value: str | None) -> bool:
    normalized = (value or "").strip().lower()
    if not normalized:
        return False
    tokens = {token for token in re.split(r"[^a-z0-9]+", normalized) if token}
    return (
        normalized.startswith(("prod", "stag"))
        or normalized in {"live", "production", "staging", "stage"}
        or bool(tokens & {"prod", "production", "stage", "staging", "live"})
    )


def guard_runtime_environment() -> None:
    """Refuse before importing the Flask application or opening a DB session."""

    if os.getenv(ALLOW_ENV) != "1":
        raise BridgeRefused(f"refusing fixture bridge: set {ALLOW_ENV}=1 explicitly")
    for env_name in ("FLASK_ENV", "APP_ENV"):
        value = os.getenv(env_name)
        if _looks_like_production(value):
            raise BridgeRefused(f"refusing fixture bridge: {env_name}={value!r} looks like production")


def guard_database_target(database_uri) -> None:
    """Reject known hosted-production database endpoints from the resolved URL."""

    try:
        host = (make_url(database_uri).host or "").lower()
    except Exception as exc:
        raise BridgeRefused("refusing fixture bridge: could not resolve the database host") from exc
    if "supabase" in host or "pooler" in host:
        raise BridgeRefused(f"refusing fixture bridge: database host {host!r} is not an allowed dev target")


def _empty_counts() -> dict[str, dict[str, int]]:
    return {key: {"created": 0, "existing": 0} for key in COUNT_KEYS}


def _record(counts: dict[str, dict[str, int]], key: str, *, created: bool) -> None:
    counts[key]["created" if created else "existing"] += 1


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (normalized[:160] or "club") + "-dev-fixture"


def _resolve_program_name(match, requested_name: str | None) -> str:
    if requested_name is not None:
        name = requested_name.strip()
    else:
        name = (match.team.name if match.team is not None else "").strip()
    if not name:
        raise BridgeRefused("match has no team name; pass --program-name explicitly")
    if len(name) > 180:
        raise BridgeRefused("program name must be at most 180 characters")
    return name


def _current_program_or_refuse(match, program_name: str):
    """Resolve an existing match association before any fixture rows are made."""

    if match.club_program_id is None:
        return None

    from src.models.funding import ClubProgram
    from src.models.league import db

    current = db.session.get(ClubProgram, match.club_program_id)
    if current is None:
        raise BridgeRefused(
            f"match {match.id} has dangling club_program_id={match.club_program_id}; refusing to overwrite it"
        )
    if current.name.casefold() != program_name.casefold():
        raise BridgeRefused(f"match {match.id} already has different club_program_id={current.id} ({current.name!r})")
    return current


def _get_or_create_league(manager, now, counts):
    from src.models.funding import FundingLeague
    from src.models.league import db

    rows = FundingLeague.query.filter_by(name=DEV_LEAGUE_NAME).order_by(FundingLeague.id.asc()).all()
    if len(rows) > 1:
        raise BridgeRefused(f"multiple funding leagues named {DEV_LEAGUE_NAME!r}; resolve the ambiguity first")
    if rows:
        league = rows[0]
        _record(counts, "funding_leagues", created=False)
    else:
        league = FundingLeague(
            name=DEV_LEAGUE_NAME,
            country="Development",
            region="Local",
            level="recreational",
            age_bands=[],
            gender_program="both",
            season_calendar="calendar_year",
            data_tier="film_room",
            registry_status="approved",
            admission_state="open",
            proposed_by_user_id=manager.id,
            reviewed_by=SCRIPT_ACTOR,
            review_reason="Development fixture bridge",
            reviewed_at=now,
        )
        db.session.add(league)
        db.session.flush()
        _record(counts, "funding_leagues", created=True)

    league.registry_status = "approved"
    league.admission_state = "open"
    return league


def _available_slug(program_name: str) -> str:
    from src.models.funding import ClubProgram

    base = _slug(program_name)
    candidate = base
    suffix = 2
    while ClubProgram.query.filter_by(slug=candidate).first() is not None:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _get_or_create_program(match, program_name, league, current_program, now, counts):
    from src.models.funding import ClubProgram
    from src.models.league import db

    if current_program is not None:
        program = current_program
        created = False
    else:
        matches = ClubProgram.query.filter_by(name=program_name).order_by(ClubProgram.id.asc()).all()
        if len(matches) > 1:
            raise BridgeRefused(f"multiple club programs named {program_name!r}; resolve the ambiguity first")
        program = matches[0] if matches else None
        created = program is None

    if program is None:
        program = ClubProgram(
            funding_league_id=league.id,
            name=program_name,
            legal_name=program_name,
            slug=_available_slug(program_name),
            country=league.country,
            region=league.region,
            currency="USD",
            provenance_tier="film_room_verified",
            platform_status="approved",
            donations_enabled=False,
            emergency_hidden=False,
            reviewed_by=SCRIPT_ACTOR,
            review_reason="Development fixture bridge",
            reviewed_at=now,
            verified_at=now,
        )
        db.session.add(program)
        db.session.flush()

    if match.club_program_id is not None and match.club_program_id != program.id:
        raise BridgeRefused(
            f"match {match.id} already has different club_program_id={match.club_program_id}; "
            f"resolved target is {program.id}"
        )

    program.platform_status = "approved"
    program.emergency_hidden = False
    _record(counts, "club_programs", created=created)
    return program


def _get_or_create_claim(program, manager, now, counts):
    from src.models.funding import ClubProgramClaim
    from src.models.league import db

    claim = ClubProgramClaim.query.filter_by(program_id=program.id, user_account_id=manager.id).first()
    created = claim is None
    if claim is None:
        claim = ClubProgramClaim(
            program_id=program.id,
            user_account_id=manager.id,
            relationship_type="club_official",
            applicant_message="Development fixture bridge",
        )
        db.session.add(claim)
        db.session.flush()
    claim.status = "approved"
    claim.reviewed_by = SCRIPT_ACTOR
    claim.review_reason = "Development fixture bridge"
    claim.reviewed_at = claim.reviewed_at or now
    _record(counts, "program_claims", created=created)
    return claim


def _get_or_create_manager(program, manager, claim, now, counts):
    from src.models.funding import ClubProgramManager
    from src.models.league import db

    grant = ClubProgramManager.query.filter_by(program_id=program.id, user_account_id=manager.id).first()
    created = grant is None
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
    _record(counts, "program_managers", created=created)
    return grant


def _member_marker(match_id: int, entry_id: int) -> str:
    return f"{SCRIPT_ACTOR}:match={match_id}:entry={entry_id}"


def _validate_existing_local(entry, member, manager, program):
    from src.models.league import db
    from src.models.showcase import LocalPlayer

    if member.program_id != program.id or member.player_api_id is not None or member.local_player_id is None:
        raise BridgeRefused(f"roster entry #{entry.jersey_number} is linked to an incompatible club roster member")
    local_player = db.session.get(LocalPlayer, member.local_player_id)
    if local_player is None:
        raise BridgeRefused(f"roster entry #{entry.jersey_number} points to a missing local player")
    if local_player.created_by_user_id != manager.id:
        raise BridgeRefused(
            f"roster entry #{entry.jersey_number} points to a local player owned by a different account"
        )
    if local_player.display_name != entry.player_name:
        raise BridgeRefused(f"roster entry #{entry.jersey_number} name does not match its existing local player")
    return local_player


def _get_or_create_member(entry, match, program, manager, now, counts):
    from src.models.funding import ClubRosterMember
    from src.models.league import db
    from src.models.showcase import LocalPlayer

    marker = _member_marker(match.id, entry.id)
    if entry.club_roster_member_id is not None:
        member = db.session.get(ClubRosterMember, entry.club_roster_member_id)
        if member is None:
            raise BridgeRefused(
                f"roster entry #{entry.jersey_number} has dangling club_roster_member_id={entry.club_roster_member_id}"
            )
        local_player = _validate_existing_local(entry, member, manager, program)
        member_created = False
        local_created = False
    else:
        members = ClubRosterMember.query.filter_by(program_id=program.id, note=marker).all()
        if len(members) > 1:
            raise BridgeRefused(f"multiple fixture members found for roster entry #{entry.jersey_number}")
        member = members[0] if members else None
        if member is not None:
            local_player = _validate_existing_local(entry, member, manager, program)
            member_created = False
            local_created = False
        else:
            local_player = LocalPlayer(
                display_name=entry.player_name,
                position=entry.position,
                country=program.country,
                club_name=program.name,
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
                role=entry.position,
                note=marker,
            )
            db.session.add(member)
            db.session.flush()
            member_created = True
            local_created = True

    local_player.status = "approved"
    local_player.position = entry.position
    local_player.club_name = program.name
    member.role = entry.position
    if member.note is None or member.note == marker:
        member.note = marker

    _record(counts, "local_players", created=local_created)
    _record(counts, "roster_members", created=member_created)
    link_created = entry.club_roster_member_id != member.id
    entry.club_roster_member_id = member.id
    _record(counts, "roster_entry_links", created=link_created)
    return member


def bridge_match_to_club(*, match_id: int, manager_email: str, program_name: str | None = None) -> dict:
    """Apply the bridge in the caller's transaction and return primitive summary data."""

    from sqlalchemy import func
    from src.models.league import UserAccount, db
    from src.models.video import VideoMatch, VideoRosterEntry

    if match_id <= 0:
        raise BridgeRefused("match id must be a positive integer")
    normalized_email = manager_email.strip().lower()
    if not normalized_email:
        raise BridgeRefused("manager email is required")

    manager = UserAccount.query.filter(func.lower(UserAccount.email) == normalized_email).first()
    if manager is None:
        raise BridgeRefused(f"manager account {normalized_email!r} was not found")
    match = db.session.get(VideoMatch, match_id)
    if match is None:
        raise BridgeRefused(f"video match {match_id} was not found")

    resolved_name = _resolve_program_name(match, program_name)
    current_program = _current_program_or_refuse(match, resolved_name)
    counts = _empty_counts()
    now = datetime.now(UTC)
    league = _get_or_create_league(manager, now, counts)
    program = _get_or_create_program(match, resolved_name, league, current_program, now, counts)
    claim = _get_or_create_claim(program, manager, now, counts)
    _get_or_create_manager(program, manager, claim, now, counts)

    roster_entries = match.roster_entries.order_by(VideoRosterEntry.jersey_number, VideoRosterEntry.id).all()
    if not roster_entries:
        raise BridgeRefused(f"video match {match.id} has no roster entries")
    members = []
    for entry in roster_entries:
        member = _get_or_create_member(entry, match, program, manager, now, counts)
        members.append(
            {
                "jersey_number": entry.jersey_number,
                "roster_entry_id": entry.id,
                "club_roster_member_id": member.id,
            }
        )

    match.club_program_id = program.id
    db.session.flush()
    return {
        "match_id": match.id,
        "program_id": program.id,
        "program_name": program.name,
        "manager_email": normalized_email,
        "counts": counts,
        "members": members,
        "my_club_path": MY_CLUB_PATH,
    }


def execute_bridge(app, *, match_id: int, manager_email: str, program_name: str | None = None, dry_run=False) -> dict:
    """Run all guards and commit or roll back the bridge atomically."""

    guard_runtime_environment()
    context = nullcontext() if has_app_context() and current_app._get_current_object() is app else app.app_context()
    with context:
        from src.models.league import db

        guard_database_target(db.engine.url)
        try:
            summary = bridge_match_to_club(
                match_id=match_id,
                manager_email=manager_email,
                program_name=program_name,
            )
            if dry_run:
                db.session.rollback()
            else:
                db.session.commit()
            summary["dry_run"] = bool(dry_run)
            return summary
        except Exception:
            db.session.rollback()
            raise


def print_summary(summary: dict) -> None:
    print("\nFixture bridge summary")
    print(f"Match ID: {summary['match_id']}")
    print(f"Program: {summary['program_name']} (id={summary['program_id']})")
    print(f"Manager: {summary['manager_email']}")
    print()
    print(f"{'Resource':<24} {'Created':>8} {'Existing':>9}")
    print(f"{'-' * 24} {'-' * 8} {'-' * 9}")
    labels = {
        "funding_leagues": "Funding leagues",
        "club_programs": "Club programs",
        "program_claims": "Program claims",
        "program_managers": "Program managers",
        "local_players": "Local players",
        "roster_members": "Roster members",
        "roster_entry_links": "Roster entry links",
    }
    for key in COUNT_KEYS:
        values = summary["counts"][key]
        print(f"{labels[key]:<24} {values['created']:>8} {values['existing']:>9}")
    print()
    print(f"{'Jersey':>6} {'Roster entry':>13} {'Member ID':>10}")
    print(f"{'-' * 6} {'-' * 13} {'-' * 10}")
    for member in summary["members"]:
        print(f"{member['jersey_number']:>6} {member['roster_entry_id']:>13} {member['club_roster_member_id']:>10}")
    if summary["dry_run"]:
        print("\nDRY RUN: transaction rolled back; no fixture rows were committed.")
    print(f"\nMyClub URL path: {summary['my_club_path']}")


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--match-id", type=int, required=True)
    parser.add_argument("--manager-email", required=True)
    parser.add_argument("--program-name")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = _parse_args(argv)
    try:
        guard_runtime_environment()
        from src.main import app

        summary = execute_bridge(
            app,
            match_id=args.match_id,
            manager_email=args.manager_email,
            program_name=args.program_name,
            dry_run=args.dry_run,
        )
    except BridgeRefused as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print_summary(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
