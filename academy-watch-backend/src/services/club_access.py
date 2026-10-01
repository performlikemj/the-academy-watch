"""Club staff access: capability checks, squad scope and the invite lifecycle.

Everything here is dark behind ``CLUB_STAFF_ACCESS_ENABLED``.  With the flag
off, ``require_club_permission`` is byte-for-byte ``require_club_manager`` and
every scope helper is a no-op, so the console behaves exactly as before.

Roles follow the ClubStaff board (PHASE2 decision 2):

- owner   — everything.  Assigned only by an audited admin action, and only to
            an account that is already a claim-verified manager of the club.
- manager — everything except billing and staff access.
- coach   — assigned squads: players, match upload/reports, feedback.
- analyst — assigned squads: players, match upload/reports.
- viewer  — assigned squads: read-only players + reports.

Whole-club access is owner/manager only.  A coach/analyst/viewer granted "all squads" is still
squad-scoped: the scope is every squad the club has at request time, behind the same gates.

Claim-verified managers (``ClubProgramManager`` + approved claim) keep full
whole-club access.  Actions that speak for the club's verified identity to a
player or the public record (club player invitations, club-confirmed results,
scout-request decisions) stay with claim-verified managers/owners only; an
invited "manager" has no verified claim, so those capabilities are withheld.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from functools import wraps

from flask import g, jsonify, request
from sqlalchemy.exc import IntegrityError
from src.auth import require_user_auth
from src.models.club_access import INVITE_ROLES, ClubAccessGrant, ClubAccessGrantSquad, ClubStaffInvite
from src.models.league import db
from src.services.club_registry import is_manager_of_approved_program

DENIED_ERROR = "Club manager access denied"

CAPABILITIES = (
    "players.view",
    "players.manage",
    "matches.view",
    "matches.upload",
    "feedback",
    "recruiting",
    "contact",
    "results",
    "player_invitations",
    "branding",
    "staff.directory",
    "access.view",
    "access.manage",
    "billing",
)
# Capabilities that assert the club's verified identity; never granted by invite.
VERIFIED_ONLY = frozenset({"contact", "results", "player_invitations"})
SCOPED_ROLES = frozenset({"coach", "analyst", "viewer"})
ROLE_CAPABILITIES = {
    "owner": frozenset(CAPABILITIES),
    "manager": frozenset(CAPABILITIES) - {"access.manage", "billing"},
    "coach": frozenset({"players.view", "matches.view", "matches.upload", "feedback"}),
    "analyst": frozenset({"players.view", "matches.view", "matches.upload"}),
    "viewer": frozenset({"players.view", "matches.view"}),
}
# The board's seven rows, in board order, for the Staff & access screen.
BOARD_MATRIX = (
    ("See their squads' players", "players.view"),
    ("Upload matches & see reports", "matches.upload"),
    ("Send feedback to players", "feedback"),
    ("Recruiting & trials", "recruiting"),
    ("Decide on scout requests", "contact"),
    ("Edit club page & branding", "branding"),
    ("Billing & staff access", "access.manage"),
)

INVITE_TTL_DAYS_DEFAULT = 7
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]+\.[^@\s]{2,}$")


def staff_access_enabled() -> bool:
    return os.getenv("CLUB_STAFF_ACCESS_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


class AccessError(ValueError):
    def __init__(self, code, status=422):
        super().__init__(code)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class ClubAccess:
    program_id: int
    user_id: int
    role: str
    verified: bool
    all_squads: bool = True
    squad_ids: frozenset = field(default_factory=frozenset)
    grant_id: int | None = None
    capabilities: frozenset = field(default_factory=frozenset)

    @property
    def whole_club(self) -> bool:
        """Owner/manager only. ``all_squads`` on a scoped role widens the squad list, never the gates."""
        return self.role not in SCOPED_ROLES

    def can(self, capability: str) -> bool:
        return capability in self.capabilities

    def squad_visible(self, squad_id) -> bool:
        return self.whole_club or (squad_id is not None and squad_id in self.squad_ids)

    def to_dict(self) -> dict:
        return {
            "program_id": self.program_id,
            "role": self.role,
            "verified": self.verified,
            "whole_club": self.whole_club,
            "all_squads": self.whole_club or self.all_squads,
            "squad_ids": sorted(self.squad_ids),
            "capabilities": sorted(self.capabilities),
        }


def _legacy_manager_access(program_id, user_id) -> ClubAccess:
    return ClubAccess(
        program_id=program_id, user_id=user_id, role="manager", verified=True, capabilities=frozenset(CAPABILITIES)
    )


def _program_operational(program_id) -> bool:
    from src.models.funding import ClubProgram

    program = db.session.get(ClubProgram, program_id)
    return bool(program and program.platform_status == "approved" and not program.emergency_hidden)


def active_grant(program_id, user_id) -> ClubAccessGrant | None:
    if program_id is None or user_id is None:
        return None
    return ClubAccessGrant.query.filter_by(program_id=program_id, user_account_id=user_id, status="active").first()


def resolve_club_access(user_id, program_id) -> ClubAccess | None:
    """Current access for one account on one club, or None.  Evaluated per request."""
    if user_id is None or program_id is None:
        return None
    from src.services.account_standing import is_account_active

    if not is_account_active(user_id):  # p2-b3 standing
        return None
    verified = is_manager_of_approved_program(user_id, program_id)
    if not staff_access_enabled():
        return _legacy_manager_access(program_id, user_id) if verified else None
    grant = active_grant(program_id, user_id)
    if verified:
        role = "owner" if grant is not None and grant.role == "owner" else "manager"
        return ClubAccess(
            program_id=program_id,
            user_id=user_id,
            role=role,
            verified=True,
            grant_id=grant.id if grant is not None else None,
            capabilities=ROLE_CAPABILITIES[role],
        )
    # An owner grant is inert without the verified manager grant behind it.
    if grant is None or grant.role == "owner" or not _program_operational(program_id):
        return None
    all_squads = bool(grant.all_squads) or grant.role not in SCOPED_ROLES
    return ClubAccess(
        program_id=program_id,
        user_id=user_id,
        role=grant.role,
        verified=False,
        all_squads=all_squads,
        # Scoped roles with "all squads": every current squad, through the scoped gates (never whole-club).
        squad_ids=(
            _current_squad_ids(program_id) if all_squads and grant.role in SCOPED_ROLES else frozenset(grant.squad_ids)
        ),
        grant_id=grant.id,
        capabilities=ROLE_CAPABILITIES[grant.role] - VERIFIED_ONLY,
    )


def board_permissions(access) -> list[bool]:
    """The Staff & access board's rows for one RESOLVED access (``None`` = no access right now).

    The board never derives rights from a role table of its own: it shows exactly the capabilities
    ``resolve_club_access`` returned for that account, so verified-only rights and inert grants match.
    """
    capabilities = access.capabilities if access is not None else frozenset()
    return [cap in capabilities for _, cap in BOARD_MATRIX]


def _current_squad_ids(program_id) -> frozenset:
    """Every squad the club has right now ("all squads" is resolved per request, so new squads count)."""
    from src.models.funding import ClubSquad

    return frozenset(row[0] for row in db.session.query(ClubSquad.id).filter_by(program_id=program_id))


def club_can(user_id, program_id, capability) -> bool:
    """Non-decorator check; flag off this equals ``is_manager_of_approved_program``."""
    access = resolve_club_access(user_id, program_id)
    return bool(access and access.can(capability))


def require_club_permission(capability, program_id_arg: str = "program_id"):
    """Capability-checked replacement for ``require_club_manager``.

    ``capability`` may be one name or a tuple that must ALL be held.
    Flag off: identical to ``require_club_manager`` (same neutral 403).
    Flag on: resolves the caller's role/scope, stores it on ``g.club_access``.
    Resource routes must still apply the scope helpers below.
    """
    capabilities = (capability,) if isinstance(capability, str) else tuple(capability)
    if not capabilities or any(cap not in CAPABILITIES for cap in capabilities):
        raise ValueError(f"unknown club capability {capability}")

    def decorator(view):
        @wraps(view)
        def checked(*args, **kwargs):
            program_id = kwargs.get(program_id_arg)
            user_id = getattr(g, "user_id", None)
            if not staff_access_enabled():
                if not is_manager_of_approved_program(user_id, program_id):
                    return jsonify({"error": DENIED_ERROR}), 403
                g.club_access = _legacy_manager_access(program_id, user_id)
                return view(*args, **kwargs)
            access = resolve_club_access(user_id, program_id)
            if access is None or not all(access.can(cap) for cap in capabilities):
                return jsonify({"error": DENIED_ERROR}), 403
            g.club_access = access
            return view(*args, **kwargs)

        return require_user_auth(checked)

    return decorator


def require_club_permission_by_method(capabilities: dict):
    """One view serving several methods (GET list + POST create) with a capability per method."""

    def decorator(view):
        guarded = {method: require_club_permission(cap)(view) for method, cap in capabilities.items()}
        if "GET" in capabilities and "HEAD" not in capabilities:
            # Flask adds HEAD to every GET route, but these views branch on request.method, so a HEAD
            # runs their non-GET branch. Flag off: the GET guard == require_club_manager, i.e. the
            # legacy behaviour byte-for-byte. Flag on: HEAD must hold every capability the view declares.
            legacy_head = guarded["GET"]
            strict_head = require_club_permission(tuple(sorted(set(capabilities.values()))))(view)
            guarded["HEAD"] = lambda *a, **kw: (strict_head if staff_access_enabled() else legacy_head)(*a, **kw)

        @wraps(view)
        def dispatch(*args, **kwargs):
            handler = guarded.get(request.method)
            if handler is None:
                return jsonify({"error": "Method not allowed"}), 405
            return handler(*args, **kwargs)

        return dispatch

    return decorator


# ---------------------------------------------------------------------------
# Scope helpers — no-ops for owner/manager access (and always when the flag is off)
# ---------------------------------------------------------------------------


def current_access() -> ClubAccess | None:
    return getattr(g, "club_access", None)


def scoped_squad_ids() -> frozenset | None:
    """None = whole club (owner/manager); otherwise the only squads the caller may see.

    For an "all squads" coach/analyst/viewer this is every current squad of the club, never None.
    """
    access = current_access()
    if access is None or access.whole_club:
        return None
    return access.squad_ids


def member_in_scope(member) -> bool:
    access = current_access()
    return access is None or access.squad_visible(member.squad_id)


def match_visible_to(access, match, *, require_bytes=False) -> bool:
    """May this caller see this club match? (No-op for whole-club roles and while the flag is off.)

    Squad-scoped staff need ALL of:
      - the match's squad label in their squads;
      - a grant-time ``origin`` marker (written when the match and its first upload URL were
        created). Without it the match is LEGACY: whole-club only, forever;
      - no ``uncertain`` marker (an unidentified roster row was present at some point);
      - every player it covers -- today's roster plus every ``member`` coverage row, which is
        append-only from the origin onward -- currently in their squads (dangling ids refuse);
      - with ``require_bytes``: a completed upload (``uploaded_at`` and ``blob_etag`` set).
    ``require_bytes`` guards everything that serves footage or analysis derived from it:
    media tokens, footage/crops/bbox, reels, reports, profile film, roster film totals and
    feedback evidence/citations. Without it (match detail, list and the upload workflow) no
    footage-derived data is returned for an in-progress upload.
    """
    if access is None or access.whole_club:
        return True
    if match is None or match.squad_id is None or match.squad_id not in access.squad_ids:
        return False
    if require_bytes and not upload_completed(match):
        return False
    from src.models.club_access import VideoMatchCoverage
    from src.models.funding import ClubRosterMember
    from src.models.video import VideoRosterEntry

    coverage = VideoMatchCoverage.query.filter_by(video_match_id=match.id).all()
    kinds = {row.kind for row in coverage}
    if "origin" not in kinds or "uncertain" in kinds:
        return False
    member_ids = [
        row[0] for row in db.session.query(VideoRosterEntry.club_roster_member_id).filter_by(video_match_id=match.id)
    ] + [row.club_roster_member_id for row in coverage if row.kind == "member"]
    if any(member_id is None for member_id in member_ids):
        return False
    if not member_ids:
        return True
    rows = ClubRosterMember.query.filter(
        ClubRosterMember.id.in_(sorted(set(member_ids))), ClubRosterMember.program_id == match.club_program_id
    ).all()
    return len(rows) == len(set(member_ids)) and all(row.squad_id in access.squad_ids for row in rows)


def upload_completed(match) -> bool:
    """A finished, verified upload that is currently published for scoped reads.

    Needs the verified ETag to be the published one AND an immutable snapshot of that generation.
    Never true for bytes sitting in storage before completion, while an admin replacement grant
    has the recording "replacing", or when no snapshot could be taken.
    """
    etag = getattr(match, "blob_etag", None)
    return bool(
        getattr(match, "uploaded_at", None)
        and etag
        and getattr(match, "scoped_ready_etag", None) == etag
        and getattr(match, "scoped_snapshot", None)
    )


def recording_completed(match) -> bool:
    """A verified upload exists (regardless of scoped readiness): the recording is immutable for clubs."""
    return bool(getattr(match, "uploaded_at", None) and getattr(match, "blob_etag", None))


REPLACING = "replacing"  # scoped_ready_etag value while an admin replacement grant is outstanding


def replacement_granted(match) -> bool:
    """An admin replacement grant is outstanding: the only state in which a completed club
    recording may be completed again with a different generation."""
    return getattr(match, "scoped_ready_etag", None) == REPLACING


def publish_recording(match) -> None:
    """Called only right after a verified upload-complete stamped ``blob_etag`` (flag on or off).

    Takes an immutable snapshot of exactly that generation (conditional on its ETag) and publishes
    it for scoped reads. A same-generation retry keeps the existing snapshot. If no snapshot can be
    taken the recording stays unpublished for scoped staff (whole-club access is unaffected).
    """
    from src.services import video_storage

    if match is None or match.club_program_id is None:
        return
    if match.scoped_snapshot and match.scoped_ready_etag == match.blob_etag:
        return
    snapshot = video_storage.create_verified_snapshot(match.blob_path, match.blob_etag)
    match.scoped_snapshot = snapshot
    match.scoped_ready_etag = match.blob_etag if snapshot else None


def unpublish_recording(match) -> None:
    """An upload grant was re-issued for a completed recording: scoped reads stop until re-verified."""
    if match is not None and match.club_program_id is not None:
        match.scoped_ready_etag = REPLACING
        match.scoped_snapshot = None


def scoped_recording_intact(match) -> bool:
    """The stored object is still the verified one (guards a still-live write SAS overwriting it).

    Checked on every scoped token mint and byte request. Without verifiable storage (local
    dev artifacts) immutability cannot be established, so scoped staff get nothing.
    """
    from src.services import video_storage

    if not upload_completed(match) or not match.blob_path or not video_storage.is_configured():
        return False
    try:
        return bool(video_storage.verify_expected_blob(match.blob_path, match.blob_etag).get("ok"))
    except Exception:
        return False


def evidence_in_scope(video_match_id) -> bool:
    """May the current caller read footage-derived evidence citing this match? (True unless scoped.)"""
    from flask import has_request_context

    if not has_request_context():
        return True
    access = current_access()
    if access is None or access.whole_club:
        return True
    if video_match_id is None:
        return False
    from src.models.video import VideoMatch

    return match_visible_to(access, db.session.get(VideoMatch, video_match_id), require_bytes=True)


def record_coverage(match, *, origin=False) -> None:
    """Append (never remove) coverage for a club match, in the caller's transaction.

    ``origin=True`` is used ONLY where a club match and its first upload URL are created
    (``create_club_match``): coverage history starts before any bytes can exist. Every other
    caller (roster writes before and after mutation, upload-URL re-mints, completion) only
    appends to a match that already has an origin; for a LEGACY match (no origin) it is a no-op,
    so completion or re-attestation can never create or upgrade provenance. Runs regardless of
    the staff-access flag so history is complete when the flag is switched on.
    """
    from src.models.club_access import VideoMatchCoverage
    from src.models.funding import ClubRosterMember
    from src.models.video import VideoRosterEntry

    if match is None or match.club_program_id is None:
        return
    db.session.flush()
    have = {
        (row.kind, row.club_roster_member_id)
        for row in VideoMatchCoverage.query.filter_by(video_match_id=match.id).all()
    }
    if not origin and ("origin", None) not in have:
        return
    want = {("origin", None)}
    for (member_id,) in db.session.query(VideoRosterEntry.club_roster_member_id).filter_by(video_match_id=match.id):
        member = db.session.get(ClubRosterMember, member_id) if member_id is not None else None
        if member is None or member.program_id != match.club_program_id:
            want.add(("uncertain", None))
        else:
            want.add(("member", member_id))
    for kind, member_id in sorted(want - have, key=lambda item: (item[0], item[1] or 0)):
        db.session.add(VideoMatchCoverage(video_match_id=match.id, kind=kind, club_roster_member_id=member_id))


def match_in_scope(match, *, require_bytes=False) -> bool:
    return match_visible_to(current_access(), match, require_bytes=require_bytes)


def match_bytes_in_scope(match) -> bool:
    """Gate for footage and anything derived from it (see ``match_visible_to``)."""
    return match_in_scope(match, require_bytes=True)


def roster_fits_squad(match_squad_id, members) -> bool:
    """Write-side coverage rule (flag on): a squad-labelled match holds only that squad's players."""
    return match_squad_id is None or all(member.squad_id == match_squad_id for member in members)


# Role-aware allowlist serializers: one place decides what each staff role may read.
MEMBER_FIELDS = frozenset(
    {
        "id",
        "program_id",
        "squad_id",
        "shirt_number",
        "role",
        "created_at",
        "available",
        "public_stats_allowed",
        "subject_type",
        "player_api_id",
        "local_player_id",
        "display_name",
        "position",
        "is_minor",
        "photo",
        "age",
        "age_label",
        "film",
        "squad",
        "claim_status",
        "has_club_photo",
    }
)
PROFILE_FIELDS = frozenset({"identity", "pathway", "results", "film"})


def _full_reader(access) -> bool:
    return access is None or access.role in ("owner", "manager")


def member_view(member_dict, access=None):
    """Roster member DTO for the caller. Managers (and flag off) get the legacy dict unchanged."""
    access = current_access() if access is None else access
    if _full_reader(access) or not isinstance(member_dict, dict):
        return member_dict
    allowed = set(MEMBER_FIELDS)
    if access.role != "viewer":
        allowed.add("brief")
    return {key: value for key, value in member_dict.items() if key in allowed}


def match_summary(match) -> dict:
    """Narrow match DTO for scoped staff: no blob paths, capture metadata, jobs or AI analysis."""
    return {
        "id": match.id,
        "club_program_id": match.club_program_id,
        "squad_id": match.squad_id,
        "opponent_name": match.opponent_name,
        "match_date": match.match_date.isoformat() if match.match_date else None,
        "competition": match.competition,
        "status": match.status,
    }


def profile_view(body, access=None):
    """Club player profile for the caller (allowlist per capability)."""
    access = current_access() if access is None else access
    if _full_reader(access) or not isinstance(body, dict):
        return body
    allowed = set(PROFILE_FIELDS)
    if access.role != "viewer":
        allowed.add("coach_brief")
    if access.can("players.manage"):
        allowed.add("note")
    if access.can("feedback"):
        allowed.add("development")
    out = {key: value for key, value in body.items() if key in allowed}
    if "scout_interest" in body:
        out["scout_interest"] = (
            body["scout_interest"]
            if access.can("contact")
            else {k: v for k, v in body["scout_interest"].items() if k in {"locked", "reason"}}
        )
    if isinstance(out.get("identity"), dict):
        out["identity"] = member_view(out["identity"], access)
    return out


def signed_member_id(member) -> int | None:
    if member.player_api_id is not None:
        return member.player_api_id
    if member.local_player_id is not None:
        return -member.local_player_id
    return None


def scoped_signed_player_ids(program_id, squad_ids) -> set[int]:
    from src.models.funding import ClubRosterMember

    if not squad_ids:
        return set()
    rows = ClubRosterMember.query.filter(
        ClubRosterMember.program_id == program_id, ClubRosterMember.squad_id.in_(sorted(squad_ids))
    ).all()
    return {sid for sid in (signed_member_id(row) for row in rows) if sid is not None}


def club_actor_allowed(session, program_id, user_id, capability, *, subject_signed_id=None) -> bool:
    """Inner re-check used by services that previously called ``strict_manager`` for the actor."""
    from src.models.club_invitation import strict_manager
    from src.services.account_standing import is_account_active

    if not is_account_active(user_id):  # p2-b3 standing
        return False
    if strict_manager(session, program_id, user_id) is not None:
        return True
    if not staff_access_enabled():
        return False
    access = resolve_club_access(user_id, program_id)
    if access is None or not access.can(capability):
        return False
    if subject_signed_id is None or access.whole_club:
        return True
    return subject_signed_id in scoped_signed_player_ids(program_id, access.squad_ids)


def programs_with_capability(user_id, capability) -> list[int]:
    """Grant-backed (non-verified) programs where the user holds ``capability``."""
    if not staff_access_enabled() or user_id is None:
        return []
    rows = ClubAccessGrant.query.filter_by(user_account_id=user_id, status="active").all()
    out = []
    for row in rows:
        access = resolve_club_access(user_id, row.program_id)
        if access is not None and access.can(capability):
            out.append(row.program_id)
    return sorted(out)


# ---------------------------------------------------------------------------
# Audit: A1's admin_action_events via record_admin_event
# ---------------------------------------------------------------------------


def audit(action, program_id, *, reason="club staff access", metadata=None, actor_email=None):
    """Append an access event via A1's admin audit (caller's transaction; never commits).

    Metadata carries only IDs and role codes (``bounded_meta`` rejects anything else).
    """
    from src.services.admin_audit import record_admin_event

    actor = (actor_email or getattr(g, "user_email", None) or "system")[:254]
    return record_admin_event(actor, f"club_access_{action}", "club_program", int(program_id), reason, metadata)


def recent_activity(program_id, limit=8) -> list[dict]:
    from src.models.league import UserAccount
    from src.models.p2_foundation import AdminActionEvent

    rows = (
        AdminActionEvent.query.filter(
            AdminActionEvent.target_type == "club_program",
            AdminActionEvent.target_id == str(program_id),
            AdminActionEvent.action.like("club_access_%"),
        )
        .order_by(AdminActionEvent.created_at.desc(), AdminActionEvent.id.desc())
        .limit(limit)
        .all()
    )
    out = []
    for row in rows:
        actor = UserAccount.query.filter(db.func.lower(UserAccount.email) == (row.actor_email or "").lower()).first()
        meta = row.event_metadata or {}
        out.append(
            {
                "action": row.action.removeprefix("club_access_"),
                "actor": actor.display_name if actor and actor.display_name else "The Academy Watch",
                "role": meta.get("role"),
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Grants and invites
# ---------------------------------------------------------------------------


def normalize_email(value) -> str:
    if not isinstance(value, str):
        raise AccessError("invalid_email")
    email = value.strip().lower()
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise AccessError("invalid_email")
    return email


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _validate_scope(program_id, role, all_squads, squad_ids):
    from src.models.funding import ClubSquad

    if role not in SCOPED_ROLES:
        return True, []
    if not isinstance(all_squads, bool):
        raise AccessError("invalid_scope")
    if squad_ids is None:
        squad_ids = []
    if not isinstance(squad_ids, list) or any(isinstance(s, bool) or not isinstance(s, int) for s in squad_ids):
        raise AccessError("invalid_scope")
    squad_ids = sorted(set(squad_ids))
    if all_squads:
        return True, []
    if not squad_ids:
        raise AccessError("scope_required")
    found = {s.id for s in ClubSquad.query.filter(ClubSquad.program_id == program_id, ClubSquad.id.in_(squad_ids))}
    if found != set(squad_ids):
        raise AccessError("squad_not_found", 404)
    return False, squad_ids


def _apply_scope(grant, all_squads, squad_ids):
    """Reconcile scope rows by squad id: keep retained rows, delete removed ones, insert only new ones."""
    grant.all_squads = all_squads
    wanted = set(squad_ids)
    for row in list(grant.squads):
        if row.squad_id not in wanted:
            grant.squads.remove(row)
    have = {row.squad_id for row in grant.squads}
    for squad_id in sorted(wanted - have):
        grant.squads.append(ClubAccessGrantSquad(squad_id=squad_id))


def _user_by_email(email):
    from src.models.league import UserAccount

    return UserAccount.query.filter(db.func.lower(UserAccount.email) == email).first()


def invite_ttl_days() -> int:
    try:
        return max(1, min(30, int(os.getenv("CLUB_STAFF_INVITE_TTL_DAYS", INVITE_TTL_DAYS_DEFAULT))))
    except ValueError:
        return INVITE_TTL_DAYS_DEFAULT


def create_invite(program_id, actor_id, data) -> tuple[ClubStaffInvite, str]:
    if not isinstance(data, dict):
        raise AccessError("invalid_payload")
    email = normalize_email(data.get("email"))
    role = data.get("role")
    if role not in INVITE_ROLES:
        raise AccessError("invalid_role")
    all_squads, squad_ids = _validate_scope(program_id, role, data.get("all_squads", False), data.get("squad_ids"))
    existing_user = _user_by_email(email)
    if existing_user is not None and (
        is_manager_of_approved_program(existing_user.id, program_id)
        or active_grant(program_id, existing_user.id) is not None
    ):
        raise AccessError("already_has_access", 409)
    now = _now()
    # Re-inviting the same address supersedes the earlier link (old token stops working).
    for old in ClubStaffInvite.query.filter_by(program_id=program_id, email=email, status="pending").with_for_update():
        old.status = "revoked"
        old.revoked_at = now
        old.revoked_by_user_id = actor_id
    token = secrets.token_urlsafe(32)
    invite = ClubStaffInvite(
        program_id=program_id,
        email=email,
        role=role,
        all_squads=all_squads,
        squad_ids=squad_ids,
        token_hash=hash_token(token),
        status="pending",
        invited_by_user_id=actor_id,
        created_at=now,
        expires_at=now + timedelta(days=invite_ttl_days()),
    )
    db.session.add(invite)
    db.session.flush()
    audit("invite_sent", program_id, metadata={"invite_id": invite.id, "role": role})
    return invite, token


def revoke_invite(program_id, invite_id, actor_id) -> ClubStaffInvite:
    invite = ClubStaffInvite.query.filter_by(id=str(invite_id), program_id=program_id).with_for_update().first()
    if invite is None:
        raise AccessError("invite_not_found", 404)
    if invite.status != "pending":
        raise AccessError("invite_not_pending", 409)
    invite.status = "revoked"
    invite.revoked_at = _now()
    invite.revoked_by_user_id = actor_id
    audit("invite_revoked", program_id, metadata={"invite_id": invite.id, "role": invite.role})
    return invite


def _invite_for_token(token, *, lock=False) -> ClubStaffInvite:
    if not isinstance(token, str) or not 20 <= len(token) <= 200:
        raise AccessError("invite_not_found", 404)
    query = ClubStaffInvite.query.filter_by(token_hash=hash_token(token))
    invite = (query.with_for_update() if lock else query).first()
    if invite is None:
        raise AccessError("invite_not_found", 404)
    return invite


def _check_invite_usable(invite, user):
    status = invite.effective_status()
    if status == "revoked":
        raise AccessError("invite_revoked", 410)
    if status == "accepted":
        raise AccessError("invite_used", 409)
    if status == "expired":
        raise AccessError("invite_expired", 410)
    if (user.email or "").strip().lower() != invite.email:
        raise AccessError("invite_wrong_account", 403)
    if not _program_operational(invite.program_id):
        raise AccessError("invite_not_found", 404)


def preview_invite(user, token) -> dict:
    from src.models.funding import ClubProgram

    invite = _invite_for_token(token)
    program = db.session.get(ClubProgram, invite.program_id)
    try:
        _check_invite_usable(invite, user)
        state = "ready"
    except AccessError as exc:
        state = exc.code
    out = {"state": state, "role": invite.role}
    # Club identity is only revealed to the invited account.
    if state == "ready" and program is not None:
        out["program"] = {"id": program.id, "name": program.name}
    return out


def accept_invite(user, token) -> ClubAccessGrant:
    invite = _invite_for_token(token, lock=True)
    _check_invite_usable(invite, user)
    program_id = invite.program_id
    if is_manager_of_approved_program(user.id, program_id):
        raise AccessError("already_has_access", 409)
    grant = ClubAccessGrant.query.filter_by(program_id=program_id, user_account_id=user.id).with_for_update().first()
    if grant is not None and grant.status == "active":
        raise AccessError("already_has_access", 409)
    from src.models.funding import ClubSquad

    squad_ids = sorted(int(s) for s in (invite.squad_ids or []))
    if invite.role in SCOPED_ROLES and not invite.all_squads:
        # Squads deleted since the invite was sent drop out of scope.
        squad_ids = sorted(
            s.id for s in ClubSquad.query.filter(ClubSquad.program_id == program_id, ClubSquad.id.in_(squad_ids))
        )
        if not squad_ids:
            raise AccessError("invite_scope_unavailable", 409)
    now = _now()
    if grant is None:
        grant = ClubAccessGrant(program_id=program_id, user_account_id=user.id, created_at=now)
        db.session.add(grant)
    else:
        grant.version = (grant.version or 1) + 1
        grant.revoked_at = None
        grant.revoked_by_user_id = None
    grant.role = invite.role
    grant.status = "active"
    grant.source = "invite"
    grant.source_invite_id = invite.id
    grant.granted_by_user_id = invite.invited_by_user_id
    grant.updated_at = now
    _apply_scope(grant, bool(invite.all_squads) or invite.role not in SCOPED_ROLES, squad_ids)
    invite.status = "accepted"
    invite.accepted_at = now
    invite.accepted_by_user_id = user.id
    db.session.flush()
    audit("invite_accepted", program_id, metadata={"grant_id": grant.id, "role": grant.role})
    return grant


def _grant_for_update(program_id, grant_id) -> ClubAccessGrant:
    if isinstance(grant_id, bool) or not isinstance(grant_id, int):
        raise AccessError("grant_not_found", 404)
    grant = ClubAccessGrant.query.filter_by(id=grant_id, program_id=program_id).with_for_update().first()
    if grant is None or grant.status != "active":
        raise AccessError("grant_not_found", 404)
    if grant.role == "owner":
        raise AccessError("owner_admin_only", 409)
    return grant


def update_grant(program_id, grant_id, actor_id, data) -> ClubAccessGrant:
    if not isinstance(data, dict):
        raise AccessError("invalid_payload")
    grant = _grant_for_update(program_id, grant_id)
    if grant.user_account_id == actor_id:
        raise AccessError("cannot_change_own_access", 409)
    expected = data.get("expected_version")
    if expected is not None and expected != grant.version:
        raise AccessError("grant_version_conflict", 409)
    role = data.get("role", grant.role)
    if role not in INVITE_ROLES:
        raise AccessError("invalid_role")
    all_squads, squad_ids = _validate_scope(
        program_id,
        role,
        data.get("all_squads", bool(grant.all_squads)),
        data.get("squad_ids", grant.squad_ids),
    )
    grant.role = role
    _apply_scope(grant, all_squads, squad_ids)
    grant.version = (grant.version or 1) + 1
    grant.updated_at = _now()
    audit("grant_changed", program_id, metadata={"grant_id": grant.id, "role": role})
    return grant


def revoke_grant(program_id, grant_id, actor_id, *, reason="club staff access") -> ClubAccessGrant:
    grant = _grant_for_update(program_id, grant_id)
    grant.status = "revoked"
    grant.revoked_at = _now()
    grant.revoked_by_user_id = actor_id
    grant.version = (grant.version or 1) + 1
    grant.squads = []
    audit("grant_revoked", program_id, reason=reason, metadata={"grant_id": grant.id, "role": grant.role})
    return grant


def _lock_program(program_id):
    """Serialize owner changes per club: take the ``club_programs`` row lock before reading owners.

    ``FOR NO KEY UPDATE`` still excludes every other program-row locker (they all take the program
    first, then child rows) but not the ``FOR KEY SHARE`` an unrelated FK insert needs.
    """
    from src.models.funding import ClubProgram

    return ClubProgram.query.filter_by(id=program_id).populate_existing().with_for_update(key_share=True).first()


def _active_owners_locked(program_id) -> list[ClubAccessGrant]:
    return (
        ClubAccessGrant.query.filter_by(program_id=program_id, role="owner", status="active")
        .populate_existing()
        .with_for_update()
        .all()
    )


def _flush_owner_change():
    """One active owner per club is also a database rule (``uq_club_access_grants_one_active_owner``)."""
    try:
        db.session.flush()
    except IntegrityError as exc:
        raise AccessError("owner_conflict", 409) from exc


def assign_owner(program_id, user_id, reason) -> ClubAccessGrant:
    """Admin-only: make an existing claim-verified manager the club owner (transfer if one exists)."""
    _lock_program(program_id)
    if not is_manager_of_approved_program(user_id, program_id):
        raise AccessError("owner_must_be_verified_manager", 409)
    now = _now()
    previous = []
    for row in _active_owners_locked(program_id):
        if row.user_account_id == user_id:
            return row
        row.status = "revoked"
        row.revoked_at = now
        row.version = (row.version or 1) + 1
        previous.append(row.id)
    # The outgoing owner must be revoked in the database before the new one becomes active.
    _flush_owner_change()
    grant = (
        ClubAccessGrant.query.filter_by(program_id=program_id, user_account_id=user_id)
        .populate_existing()
        .with_for_update()
        .first()
    )
    if grant is None:
        grant = ClubAccessGrant(program_id=program_id, user_account_id=user_id, created_at=now)
        db.session.add(grant)
    else:
        grant.version = (grant.version or 1) + 1
        grant.revoked_at = None
        grant.revoked_by_user_id = None
    grant.role = "owner"
    grant.status = "active"
    grant.source = "admin"
    grant.source_invite_id = None
    grant.updated_at = now
    _apply_scope(grant, True, [])
    _flush_owner_change()
    audit(
        "owner_assigned",
        program_id,
        reason=reason,
        metadata={"grant_id": grant.id, "role": "owner", "replaced_grant_count": len(previous)},
    )
    return grant


def remove_owner(program_id, reason) -> ClubAccessGrant:
    _lock_program(program_id)
    owners = _active_owners_locked(program_id)
    if not owners:
        raise AccessError("owner_not_found", 404)
    grant = owners[0]
    grant.status = "revoked"
    grant.revoked_at = _now()
    grant.version = (grant.version or 1) + 1
    audit("owner_removed", program_id, reason=reason, metadata={"grant_id": grant.id, "role": "owner"})
    return grant


def invite_email_content(program_name, role, link) -> tuple[str, str, str]:
    from html import escape

    from src.utils.sanitize import sanitize_plain_text

    club = sanitize_plain_text(str(program_name or "A club")).strip()[:180] or "A club"
    role_label = {"manager": "club manager", "coach": "coach", "analyst": "analyst", "viewer": "viewer"}[role]
    subject = f"You're invited to join {club} on The Academy Watch"
    text = (
        f"{club} has invited you to their private Club Home on The Academy Watch as a {role_label}.\n\n"
        f"Accept the invitation here: {link}\n\n"
        "Sign in with this email address to accept. The link works once and expires in "
        f"{invite_ttl_days()} days. If you weren't expecting this, you can ignore it.\n\n"
        "The Academy Watch"
    )
    html = (
        f"<p>{escape(club)} has invited you to their private Club Home on The Academy Watch as a "
        f"{escape(role_label)}.</p>"
        f'<p><a href="{escape(link)}">Accept the invitation</a></p>'
        f"<p>Sign in with this email address to accept. The link works once and expires in "
        f"{invite_ttl_days()} days. If you weren't expecting this, you can ignore it.</p>"
        "<p>The Academy Watch</p>"
    )
    return subject, text, html


def invite_link(token) -> str:
    base = (os.getenv("PUBLIC_BASE_URL") or "https://theacademywatch.com").strip().rstrip("/")
    # Fragment: the token never reaches server logs or Referer headers.
    return f"{base}/staff-invite#token={token}"


def send_invite_email(invite, token, program_name) -> bool:
    """Best-effort delivery after commit.

    Not on A1's notification_outbox: its enqueue() needs a recipient_user_id (invitees usually have no account
    yet) and forbids credentials in payloads, while the one-use token exists only here (stored hashed).
    Delivery is synchronous (no daemon thread); the invite row is authoritative and "resend" = re-invite.
    """
    import logging

    from src.services.email_service import email_service

    subject, text, html = invite_email_content(program_name, invite.role, invite_link(token))
    from src.auth import _is_production

    if not _is_production() and os.getenv("FLASK_ENV", "").lower() not in ("stage", "staging"):
        # Same convention as the dev login code: local testing without a mail provider. Never in production.
        logging.getLogger(__name__).info("[DEV] Staff invite link for %s: %s", invite.email, invite_link(token))
    try:
        result = email_service.send_email(to=invite.email, subject=subject, html=html, text=text, tags=["staff-invite"])
        return bool(getattr(result, "success", False))
    except Exception:
        logging.getLogger(__name__).exception("Staff invite email failed")
        return False
