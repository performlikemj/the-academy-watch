"""Bridge approved showcase club claims into club-console grants.

The caller owns the transaction. This module never commits and never starts
Connect onboarding.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from src.models.funding import (
    ClubProgram,
    ClubProgramClaim,
    ClubProgramManager,
    FundingAdminEvent,
    FundingLeague,
)
from src.models.league import Team, TeamProfile, db
from src.models.showcase import ClubOfficialClaim, LocalClub

CONSOLE_LEAGUE_NAME = "Console (unlisted)"
CONSOLE_LEAGUE_COUNTRY = "Global"
CONSOLE_LEAGUE_REGION = "Unlisted"
LOCAL_PROGRAM_SLUG_PREFIX = "console-local-club-"
BRIDGE_LOCK_KEY = 4_343_203
BRIDGE_EVIDENCE_PREFIX = "Bridged from ClubOfficialClaim #"
BRIDGE_EVIDENCE_SEPARATOR = "\n\nExisting program-claim evidence:\n"


class ClubConsoleBridgeConflict(RuntimeError):
    """A pre-existing row cannot safely be adopted by the bridge."""


def _lock_bridge_writes() -> None:
    """Serialize bridge writes where no database row exists to lock yet."""
    if db.session.get_bind().dialect.name == "postgresql":
        db.session.execute(
            sa.text("SELECT pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": BRIDGE_LOCK_KEY},
        )


def _audit(
    action: str,
    target_type: str,
    target_id: int,
    *,
    actor: str,
    reason: str,
    metadata: dict,
) -> None:
    """Write the same append-only event shape used by the funding routes."""
    db.session.add(
        FundingAdminEvent(
            actor_email=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            reason=reason,
            event_metadata=metadata,
        )
    )


def _console_league() -> FundingLeague:
    league = FundingLeague.query.filter_by(
        name=CONSOLE_LEAGUE_NAME,
        country=CONSOLE_LEAGUE_COUNTRY,
        region=CONSOLE_LEAGUE_REGION,
    ).first()
    if league is None:
        league = FundingLeague(
            name=CONSOLE_LEAGUE_NAME,
            country=CONSOLE_LEAGUE_COUNTRY,
            region=CONSOLE_LEAGUE_REGION,
            level="recreational",
            age_bands=[],
            gender_program="both",
            season_calendar="calendar_year",
            data_tier="self_reported",
            registry_status="proposed",
            admission_state="closed",
        )
        db.session.add(league)
        db.session.flush()
        return league

    # This exact identity is reserved for private console access. Keep the
    # visibility marker closed even if the row predated this bridge.
    league.level = "recreational"
    league.age_bands = []
    league.gender_program = "both"
    league.season_calendar = "calendar_year"
    league.data_tier = "self_reported"
    league.league_api_id = None
    league.existing_league_id = None
    league.registry_status = "proposed"
    league.admission_state = "closed"
    return league


def _latest_team(team_api_id: int) -> Team | None:
    return (
        Team.query.filter_by(team_id=team_api_id).order_by(Team.season.desc(), Team.id.desc()).with_for_update().first()
    )


def _team_profile(team_api_id: int) -> tuple[TeamProfile, Team | None]:
    profile = db.session.get(TeamProfile, team_api_id)
    team = _latest_team(team_api_id)
    if profile is None:
        profile = TeamProfile(
            team_id=team_api_id,
            name=team.name if team else f"Team {team_api_id}",
            country=team.country if team else None,
            logo_url=team.logo if team else None,
            venue_city=team.venue_city if team else None,
        )
        db.session.add(profile)
        db.session.flush()
    return profile, team


def _local_program_slug(local_club_id: int) -> str:
    return f"{LOCAL_PROGRAM_SLUG_PREFIX}{local_club_id}"


def _available_team_program_slug(team_api_id: int) -> str:
    base = f"console-team-{team_api_id}"
    candidate = base
    suffix = 2
    while ClubProgram.query.filter_by(slug=candidate).first() is not None:
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def _is_bridge_created_local_program(program: ClubProgram, local_club_id: int) -> bool:
    events = FundingAdminEvent.query.filter_by(
        action="program.console_bridge_created",
        target_type="program",
        target_id=program.id,
    ).all()
    return any((event.event_metadata or {}).get("local_club_id") == local_club_id for event in events)


def _program_for_official_claim(
    claim: ClubOfficialClaim,
    *,
    create: bool,
) -> tuple[ClubProgram | None, bool]:
    has_team = claim.team_api_id is not None
    has_local = claim.local_club_id is not None
    if has_team == has_local:
        raise ValueError("club-official claim must reference exactly one club")

    if has_team:
        team_api_id = int(claim.team_api_id)
        program = ClubProgram.query.filter_by(team_api_id=team_api_id).with_for_update().first()
        if program is not None or not create:
            return program, False

        profile, team = _team_profile(team_api_id)
        full_name = profile.name or (team.name if team else None) or f"Team {team_api_id}"
        country = profile.country or (team.country if team else None) or "Unknown"
        city = profile.venue_city or (team.venue_city if team else None)
        program = ClubProgram(
            funding_league_id=_console_league().id,
            team_api_id=team_api_id,
            name=full_name[:180],
            legal_name=full_name[:220],
            slug=_available_team_program_slug(team_api_id),
            crest_url=profile.logo_url,
            country=country[:80],
            region=(city or country)[:120],
            city=city[:120] if city else None,
            currency="USD",
            provenance_tier="provider_covered",
            platform_status="approved",
            donations_enabled=False,
            emergency_hidden=False,
        )
    else:
        local_club_id = int(claim.local_club_id)
        slug = _local_program_slug(local_club_id)
        program = ClubProgram.query.filter_by(slug=slug).with_for_update().first()
        if program is not None:
            if not _is_bridge_created_local_program(program, local_club_id):
                if create:
                    raise ClubConsoleBridgeConflict("reserved local-club console identity is already in use")
                return None, False
            return program, False
        if not create:
            return None, False

        local_club = db.session.get(LocalClub, local_club_id)
        if local_club is not None:
            db.session.refresh(local_club, with_for_update=True)
        display_club = local_club
        if local_club and local_club.status == "merged" and local_club.merged_into_local_club_id:
            display_club = db.session.get(LocalClub, local_club.merged_into_local_club_id) or local_club
        full_name = display_club.name if display_club else f"Local club {local_club_id}"
        country = ((display_club.country if display_club else None) or "Unknown")[:80]
        city = display_club.city if display_club else None
        program = ClubProgram(
            funding_league_id=_console_league().id,
            team_api_id=None,
            name=full_name[:180],
            legal_name=full_name[:220],
            slug=slug,
            country=country,
            region=(city or country)[:120],
            city=city[:120] if city else None,
            currency="USD",
            provenance_tier="self_reported",
            platform_status="approved",
            donations_enabled=False,
            emergency_hidden=False,
        )

    db.session.add(program)
    db.session.flush()
    return program, True


def _bridge_claim_id(program_claim: ClubProgramClaim | None) -> int | None:
    if program_claim is None or not program_claim.applicant_message:
        return None
    first_line = program_claim.applicant_message.splitlines()[0]
    if not first_line.startswith(BRIDGE_EVIDENCE_PREFIX):
        return None
    try:
        return int(first_line.removeprefix(BRIDGE_EVIDENCE_PREFIX))
    except ValueError:
        return None


def _original_applicant_message(program_claim: ClubProgramClaim) -> str | None:
    message = program_claim.applicant_message or ""
    if not message.startswith(BRIDGE_EVIDENCE_PREFIX):
        return message or None
    if BRIDGE_EVIDENCE_SEPARATOR not in message:
        return None
    return message.split(BRIDGE_EVIDENCE_SEPARATOR, 1)[1] or None


def _claim_evidence_reference(claim: ClubOfficialClaim, program_claim: ClubProgramClaim) -> str:
    references = [f"{BRIDGE_EVIDENCE_PREFIX}{claim.id}"]
    if claim.verification_proof_url:
        references.append(f"Proof URL: {claim.verification_proof_url.strip()}")
    if claim.verification_code:
        references.append(f"Verification code: {claim.verification_code.strip()}")
    original_message = _original_applicant_message(program_claim)
    if original_message:
        references.append(f"{BRIDGE_EVIDENCE_SEPARATOR}{original_message}")
    return "\n".join(references)


def _other_approved_claim_for_user(claim: ClubOfficialClaim) -> ClubOfficialClaim | None:
    query = ClubOfficialClaim.query.filter(
        ClubOfficialClaim.id != claim.id,
        ClubOfficialClaim.user_account_id == claim.user_account_id,
        ClubOfficialClaim.status == "approved",
    )
    if claim.team_api_id is not None:
        query = query.filter(ClubOfficialClaim.team_api_id == claim.team_api_id)
    else:
        query = query.filter(ClubOfficialClaim.local_club_id == claim.local_club_id)
    return query.order_by(ClubOfficialClaim.id.asc()).first()


def grant_console_for_official_claim(
    claim: ClubOfficialClaim,
    *,
    actor: str | None,
    now: datetime,
) -> ClubProgramManager:
    """Create or reactivate the rows required by ``require_club_manager``."""
    _lock_bridge_writes()
    if claim.id is None or claim.status != "approved":
        raise ValueError("club-official claim must be approved before console access is granted")
    if _other_approved_claim_for_user(claim) is not None:
        raise ClubConsoleBridgeConflict("another approved official claim already owns this club grant")

    audit_actor = actor or "admin"
    program, program_created = _program_for_official_claim(claim, create=True)
    if program is None:  # pragma: no cover - create=True guarantees a row
        raise RuntimeError("club console program could not be created")
    if not program_created and program.emergency_hidden:
        raise ClubConsoleBridgeConflict("club program is emergency-hidden; console access was not granted")
    if not program_created and program.platform_status in {"rejected", "suspended"}:
        raise ClubConsoleBridgeConflict(f"club program is {program.platform_status}; console access was not granted")

    program_claim = ClubProgramClaim.query.filter_by(
        program_id=program.id,
        user_account_id=claim.user_account_id,
    ).first()
    manager = ClubProgramManager.query.filter_by(
        program_id=program.id,
        user_account_id=claim.user_account_id,
    ).first()
    independent_access_exists = bool(
        program_claim is not None
        and program_claim.status == "approved"
        and _bridge_claim_id(program_claim) is None
        and manager is not None
        and manager.status == "active"
        and manager.source_claim_id == program_claim.id
    )
    if independent_access_exists:
        raise ClubConsoleBridgeConflict("an independent club-manager grant already exists for this user")

    program.league = _console_league()
    program.platform_status = "approved"
    program.donations_enabled = False
    program.reviewed_by = audit_actor
    program.review_reason = f"Console access granted from official claim #{claim.id}"
    program.reviewed_at = now
    if program_created:
        _audit(
            "program.console_bridge_created",
            "program",
            program.id,
            actor=audit_actor,
            reason=f"Console-only program created from official claim #{claim.id}",
            metadata={
                "official_claim_id": claim.id,
                "team_api_id": claim.team_api_id,
                "local_club_id": claim.local_club_id,
            },
        )

    if program_claim is None:
        program_claim = ClubProgramClaim(
            program_id=program.id,
            user_account_id=claim.user_account_id,
            relationship_type="club_official",
        )
        db.session.add(program_claim)
    program_claim.relationship_type = "club_official"
    program_claim.status = "approved"
    program_claim.applicant_message = _claim_evidence_reference(claim, program_claim)
    program_claim.reviewed_by = audit_actor
    program_claim.review_reason = f"Approved via ClubOfficialClaim #{claim.id}"
    program_claim.reviewed_at = now
    db.session.flush()

    if manager is None:
        manager = ClubProgramManager(
            program_id=program.id,
            user_account_id=claim.user_account_id,
            source_claim_id=program_claim.id,
            status="active",
            granted_by=audit_actor,
            granted_at=now,
        )
        db.session.add(manager)
    else:
        manager.source_claim_id = program_claim.id
        manager.status = "active"
        manager.granted_by = audit_actor
        manager.granted_at = now
        manager.revoked_by = None
        manager.revoked_reason = None
        manager.revoked_at = None
    db.session.flush()

    _audit(
        "claim.console_bridge_granted",
        "claim",
        program_claim.id,
        actor=audit_actor,
        reason=f"Club console granted from official claim #{claim.id}",
        metadata={
            "official_claim_id": claim.id,
            "program_id": program.id,
            "manager_grant_id": manager.id,
        },
    )
    return manager


def revoke_console_for_official_claim(
    claim: ClubOfficialClaim,
    *,
    actor: str | None,
    now: datetime,
    reason: str | None = None,
) -> ClubProgramManager | None:
    """Revoke the user-specific manager grant produced by an official claim."""
    _lock_bridge_writes()
    program, _ = _program_for_official_claim(claim, create=False)
    if program is None:
        return None
    program_claim = ClubProgramClaim.query.filter_by(
        program_id=program.id,
        user_account_id=claim.user_account_id,
    ).first()
    if program_claim is None or _bridge_claim_id(program_claim) != claim.id:
        return None

    audit_actor = actor or "admin"
    review_reason = reason or f"Console access revoked with official claim #{claim.id}"
    manager = ClubProgramManager.query.filter_by(
        program_id=program.id,
        user_account_id=claim.user_account_id,
        source_claim_id=program_claim.id,
    ).first()
    remaining_claim = _other_approved_claim_for_user(claim)
    if remaining_claim is not None:
        program_claim.applicant_message = _claim_evidence_reference(remaining_claim, program_claim)
    else:
        program_claim.status = "revoked"
        program_claim.reviewed_by = audit_actor
        program_claim.review_reason = review_reason
        program_claim.reviewed_at = now
        if manager is not None:
            manager.status = "revoked"
            manager.revoked_by = audit_actor
            manager.revoked_reason = review_reason
            manager.revoked_at = now

    db.session.flush()
    _audit(
        "claim.console_bridge_revoked",
        "claim",
        program_claim.id,
        actor=audit_actor,
        reason=review_reason,
        metadata={
            "official_claim_id": claim.id,
            "program_id": program.id,
            "manager_grant_id": manager.id if manager else None,
            "remaining_official_claim_id": remaining_claim.id if remaining_claim else None,
        },
    )
    return manager
