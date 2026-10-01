"""Two-key highlights: every read and byte request rechecks current eligibility."""

import hashlib
import json
import math
import os
import re
from collections import defaultdict
from functools import wraps

import sqlalchemy as sa
from flask import abort, g, has_request_context, request
from src.models.follow import PlayerShadow
from src.models.funding import ClubProgram, ClubRosterMember, ClubSquad, FundingLeague
from src.models.highlights import (
    HighlightConsentEvent,
    HighlightFootageReview,
    HighlightRenderJob,
    PlayerHighlight,
    now,
)
from src.models.journey import PlayerJourney
from src.models.league import UserAccount, db
from src.models.showcase import LocalPlayer, PlayerProfileClaim
from src.models.tracked_player import TrackedPlayer
from src.models.video import VideoMatch, VideoPlayerReport, VideoRosterEntry, VideoTracklet
from src.services.account_standing import account_can_act, is_account_active
from src.services.admin_audit import record_admin_event
from src.services.club_directory import directory_eligibility, is_listed
from src.services.club_publication_hold import club_publication_held
from src.services.public_adult import is_public_adult, public_adult_ids
from src.services.public_player_subject import resolve_public_adult_subject
from src.utils.academy_window import age_from_birth_date

MAX_CLIPS_PER_MATCH = 100
MAX_CLIP_SECONDS = 60


def enabled():
    return os.getenv("HIGHLIGHTS_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def gated(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        if not enabled():
            abort(404)
        return fn(*args, **kwargs)

    return wrapped


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def read_evidence():
    return (
        getattr(g, "highlight_evidence", None) if has_request_context() and request.method in {"GET", "HEAD"} else None
    )


def lookup(model, key):
    evidence = read_evidence()
    if evidence is not None:
        return evidence["models"].get(model, {}).get(key)
    return db.session.get(model, key) if key is not None else None


def roster_entries(match_id):
    evidence = read_evidence()
    if evidence is not None:
        return evidence["rosters"].get(match_id, [])
    return VideoRosterEntry.query.filter_by(video_match_id=match_id).order_by(VideoRosterEntry.id).all()


def prepare_reads(rows, *, matches=(), candidates=False):
    """Bounded set reads; no policy/source/claim work per clip. Request lifetime only."""
    if not has_request_context() or request.method not in {"GET", "HEAD"}:
        return
    from sqlalchemy.orm import aliased

    match_ids = {row.video_match_id for row in rows if row.video_match_id} | {match.id for match in matches}
    program_ids = {row.program_id for row in rows} | {match.club_program_id for match in matches}
    evidence = {"models": defaultdict(dict), "rosters": defaultdict(list), "listed": set(), "eligible": {}}
    g.highlight_evidence = evidence

    def remember(*objects):
        for obj in objects:
            if obj is not None:
                key = obj.video_match_id if isinstance(obj, HighlightFootageReview) else obj.id
                evidence["models"][type(obj)][key] = obj

    if not rows and not matches:
        evidence.update(adults=set(), dates={}, years={})
        return
    for program, match, squad, review, listed in (
        db.session.query(ClubProgram, VideoMatch, ClubSquad, HighlightFootageReview, directory_eligibility())
        .join(FundingLeague, FundingLeague.id == ClubProgram.funding_league_id)
        .outerjoin(VideoMatch, sa.and_(VideoMatch.club_program_id == ClubProgram.id, VideoMatch.id.in_(match_ids)))
        .outerjoin(ClubSquad, ClubSquad.id == VideoMatch.squad_id)
        .outerjoin(HighlightFootageReview, HighlightFootageReview.video_match_id == VideoMatch.id)
        .filter(ClubProgram.id.in_(program_ids))
        .populate_existing()
        .all()
    ):
        remember(program, match, squad, review)
        if listed:
            evidence["listed"].add(program.id)
    claim_local = aliased(LocalPlayer)
    # Include every self claim for candidate subjects too, without per-player lookup.
    roster_subjects = set()
    for entry, member, local, report in (
        db.session.query(VideoRosterEntry, ClubRosterMember, LocalPlayer, VideoPlayerReport)
        .outerjoin(ClubRosterMember, ClubRosterMember.id == VideoRosterEntry.club_roster_member_id)
        .outerjoin(LocalPlayer, LocalPlayer.id == ClubRosterMember.local_player_id)
        .outerjoin(
            VideoPlayerReport,
            sa.and_(
                VideoPlayerReport.video_match_id == VideoRosterEntry.video_match_id,
                VideoPlayerReport.roster_entry_id == VideoRosterEntry.id,
            ),
        )
        .filter(VideoRosterEntry.video_match_id.in_(match_ids))
        .order_by(VideoRosterEntry.id)
        .populate_existing()
        .all()
    ):
        remember(entry, member, local, report)
        evidence["rosters"][entry.video_match_id].append(entry)
        pid = member_subject(member)
        if pid is not None:
            roster_subjects.add(pid)
    ids = {row.signed_id for row in rows} | roster_subjects
    for claim, user, local in (
        db.session.query(PlayerProfileClaim, UserAccount, claim_local)
        .outerjoin(claim_local, claim_local.id == PlayerProfileClaim.local_player_id)
        .outerjoin(UserAccount, UserAccount.id == PlayerProfileClaim.user_account_id)
        .filter(
            sa.or_(
                PlayerProfileClaim.id.in_({row.claim_id for row in rows}),
                PlayerProfileClaim.player_api_id.in_(ids),
                claim_local.api_player_id.in_(ids),
            )
        )
        .populate_existing()
        .all()
    ):
        remember(claim, user, local)
    for track in VideoTracklet.query.filter(VideoTracklet.video_match_id.in_(match_ids)).populate_existing():
        remember(track)
    evidence["adults"] = public_adult_ids(ids)
    # A single narrow UNION adds historical DOB evidence without per-source queries.
    dates, years = defaultdict(list), defaultdict(list)
    birth_evidence = sa.union_all(
        sa.select(
            LocalPlayer.api_player_id.label("pid"),
            sa.cast(LocalPlayer.birth_date, sa.String).label("born"),
            LocalPlayer.birth_year.label("year"),
        ).where(sa.or_(LocalPlayer.api_player_id.in_(ids), LocalPlayer.id.in_({-pid for pid in ids if pid < 0}))),
        sa.select(TrackedPlayer.player_api_id, TrackedPlayer.birth_date, sa.literal(None)).where(
            TrackedPlayer.player_api_id.in_(ids)
        ),
        sa.select(PlayerJourney.player_api_id, PlayerJourney.birth_date, sa.literal(None)).where(
            PlayerJourney.player_api_id.in_(ids)
        ),
        sa.select(PlayerShadow.player_api_id, sa.cast(PlayerShadow.birth_date, sa.String), sa.literal(None)).where(
            PlayerShadow.player_api_id.in_(ids), PlayerShadow.is_active.is_(True)
        ),
    )
    for pid, born, year in db.session.execute(birth_evidence):
        if born is not None:
            dates[pid].append(born)
        if year is not None:
            years[pid].append(year)
    evidence.update(dates=dates, years=years)


def recording_date_error(match):
    if not match.match_date or match.match_date > now().date():
        return "recording_date_unknown_or_future"
    uploaded = match.uploaded_at or match.created_at
    if not uploaded or match.match_date > uploaded.date():
        return "recording_date_after_upload"
    return None


def squad_classification(squad):
    if squad is None:
        return "unknown"
    if squad.age_limit is not None and squad.age_limit <= 18:
        return "youth"
    if squad.kind == "age_group" and (squad.age_limit is None or squad.age_limit <= 18):
        return "youth"
    label = squad.name or ""
    if re.search(r"\b(?:youth|academy|juniors?|colts|minis)\b", label, re.I):
        return "youth"
    if any(int(m[1]) <= 18 for m in re.finditer(r"\b(?:u|under)[\s-]?(\d{1,2})(?:s|\b)", label, re.I)):
        return "youth"
    return "adult" if squad.kind in {"first_team", "reserves"} or (squad.age_limit or 0) > 18 else "unknown"


def recording_block_reason(match, *, frozen_etag=None):
    if recording_date_error(match):
        return recording_date_error(match)
    squad = lookup(ClubSquad, match.squad_id) if match.squad_id else None
    kind = squad_classification(squad)
    if kind == "youth":
        return "youth_recording_private"
    review = lookup(HighlightFootageReview, match.id)
    if kind == "unknown" and not (review and review.squad_adult_attested):
        return "senior_squad_attestation_required"
    if not (
        review
        and review.classification == "adult_only"
        and review.source_etag == (frozen_etag or match.blob_etag)
        and review.source_snapshot == match.scoped_snapshot
    ):
        return "review_required"
    if not adult_recording(match, frozen_etag=frozen_etag):
        return "roster_or_source_unavailable"
    return None


def member_subject(member):
    if member is None:
        return None
    if member.player_api_id is not None:
        return member.player_api_id
    local = lookup(LocalPlayer, member.local_player_id)
    return local.api_player_id if local and local.api_player_id is not None else None


def own_claim(claim, signed_id, user_id=None):
    if claim is None or claim.status != "approved" or claim.relationship_type != "player":
        return False
    if user_id is not None and claim.user_account_id != user_id:
        return False
    evidence = read_evidence()
    if not (
        account_can_act(lookup(UserAccount, claim.user_account_id))
        if evidence is not None
        else is_account_active(claim.user_account_id)
    ):
        return False
    if claim.local_player_id is not None:
        local = lookup(LocalPlayer, claim.local_player_id)
        return bool(local and local.api_player_id == signed_id and local.merged_into_local_player_id is None)
    return claim.player_api_id == signed_id


def claim_for_subject(signed_id):
    evidence = read_evidence()
    if evidence is not None:
        claims = [
            claim for claim in evidence["models"].get(PlayerProfileClaim, {}).values() if own_claim(claim, signed_id)
        ]
        return claims[0] if len(claims) == 1 else None
    claims = (
        PlayerProfileClaim.query.outerjoin(LocalPlayer, LocalPlayer.id == PlayerProfileClaim.local_player_id)
        .filter(
            PlayerProfileClaim.status == "approved",
            PlayerProfileClaim.relationship_type == "player",
            sa.or_(PlayerProfileClaim.player_api_id == signed_id, LocalPlayer.api_player_id == signed_id),
        )
        .order_by(PlayerProfileClaim.id)
        .all()
    )
    claims = [claim for claim in claims if own_claim(claim, signed_id)]
    # Ambiguous ownership is reviewed rather than silently selecting somebody's second key.
    return claims[0] if len(claims) == 1 else None


def adult_recording(match, *, frozen_etag=None):
    # Request-local only: repeated clips from one recording reuse the same read snapshot.
    # Workers/writes never cache eligibility across their storage/commit boundary.
    if has_request_context() and request.method == "GET":
        cache = g.setdefault("highlight_recording_checks", {})
        key = (match.id if match else None, frozen_etag)
        if key not in cache:
            cache[key] = _adult_recording(match, frozen_etag=frozen_etag)
        return cache[key]
    return _adult_recording(match, frozen_etag=frozen_etag)


def recording_adults(ids, recorded_on):
    """Current canonical adults must also have been adults when this footage was recorded."""
    if recorded_on is None or recorded_on > now().date():
        return set()
    batch = read_evidence()
    if batch is not None:
        dates, years = batch["dates"], batch["years"]
        return {
            pid
            for pid in set(ids) & batch["adults"]
            if all((age_from_birth_date(born, today=recorded_on) or 0) >= 18 for born in dates.get(pid, []))
            and (
                bool(dates.get(pid))
                or (bool(years.get(pid)) and all(year < recorded_on.year - 18 for year in years[pid]))
            )
        }
    adults = public_adult_ids(ids)
    evidence = defaultdict(list)
    years = defaultdict(list)
    local_rows = LocalPlayer.query.filter(
        sa.or_(LocalPlayer.api_player_id.in_(ids), LocalPlayer.id.in_([-pid for pid in ids if pid < 0]))
    ).all()
    for local in local_rows:
        pid = local.api_player_id
        if local.birth_date:
            evidence[pid].append(local.birth_date)
        if local.birth_year:
            years[pid].append(local.birth_year)
    for model, active in ((TrackedPlayer, False), (PlayerJourney, False), (PlayerShadow, True)):
        query = db.session.query(model.player_api_id, model.birth_date).filter(model.player_api_id.in_(ids))
        if active:
            query = query.filter(model.is_active.is_(True))
        for pid, born in query:
            if born:
                evidence[pid].append(born)

    def adult_then(pid):
        dates = evidence[pid]
        if dates:
            return all((age_from_birth_date(born, today=recorded_on) or 0) >= 18 for born in dates)
        return bool(years[pid]) and all(year < recorded_on.year - 18 for year in years[pid])

    return {pid for pid in adults if adult_then(pid)}


def _adult_recording(match, *, frozen_etag=None):
    """Fail closed without a source-bound human review of EVERY visible person."""
    etag = frozen_etag or (match.blob_etag if match else None)
    if not match or not etag or not match.scoped_snapshot or match.scoped_ready_etag != etag:
        return False
    review = lookup(HighlightFootageReview, match.id)
    if not (
        review
        and review.classification == "adult_only"
        and review.source_etag == etag
        and review.source_snapshot == match.scoped_snapshot
    ):
        return False
    squad = lookup(ClubSquad, match.squad_id) if match.squad_id else None
    if recording_date_error(match):
        return False
    kind = squad_classification(squad)
    if kind == "youth" or (kind == "unknown" and not review.squad_adult_attested):
        return False
    entries = roster_entries(match.id)
    if not entries:
        return False
    ids = set()
    for entry in entries:
        member = lookup(ClubRosterMember, entry.club_roster_member_id) if entry.club_roster_member_id else None
        pid = member_subject(member)
        if not member or member.program_id != match.club_program_id or pid is None:
            return False
        ids.add(pid)
    return ids == recording_adults(ids, match.match_date)


def source_fingerprint(match, entry, tracklet, *, frozen_etag=None):
    review = lookup(HighlightFootageReview, match.id)
    members = []
    for roster in roster_entries(match.id):
        member = lookup(ClubRosterMember, roster.club_roster_member_id) if roster.club_roster_member_id else None
        members.append([roster.id, roster.club_roster_member_id, roster.jersey_number, member_subject(member)])
    return digest(
        {
            "match": [
                match.id,
                match.club_program_id,
                match.squad_id,
                match.match_date,
                frozen_etag or match.blob_etag,
                match.scoped_snapshot,
                match.scoped_ready_etag,
                match.duration_s,
                match.finalized_at,
            ],
            "roster": members,
            "entry": entry.id,
            "track": [
                tracklet.id,
                tracklet.roster_entry_id,
                tracklet.tag_source,
                tracklet.review_action,
                tracklet.reviewed_at,
                tracklet.contaminated,
                tracklet.dismissed,
                tracklet.first_s,
                tracklet.last_s,
                tracklet.evidence,
            ],
            "review": [
                review.classification,
                review.reviewed_at,
                review.source_etag,
                review.source_snapshot,
                review.squad_adult_attested,
            ]
            if review
            else None,
        }
    )


def reviewed_window(match, entry, tracklet_id, start_s, end_s, *, reel=None):
    """Client selects a window; its time range and identity are resolved by the server."""
    from src.routes.video import _reel_payload

    track = lookup(VideoTracklet, tracklet_id)
    evidence = read_evidence()
    report = (
        next(
            (
                r
                for r in evidence["models"].get(VideoPlayerReport, {}).values()
                if r.video_match_id == match.id and r.roster_entry_id == entry.id
            ),
            None,
        )
        if evidence is not None
        else VideoPlayerReport.query.filter_by(video_match_id=match.id, roster_entry_id=entry.id).first()
    )
    if not (
        match.status == "finalized"
        and track
        and track.video_match_id == match.id
        and track.roster_entry_id == entry.id
        and track.reviewed_at
        and track.review_action in {"confirmed", "reassigned"}
        and not track.contaminated
        and not track.dismissed
        and report
        and report.identity_confidence == "human_confirmed"
        and report.club_program_id_at_finalize == match.club_program_id
        and report.club_roster_member_id_at_finalize == entry.club_roster_member_id
    ):
        return None
    if any(
        isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
        for value in (start_s, end_s)
    ):
        return None
    if not 0 <= start_s < end_s <= (match.duration_s or 0) or end_s - start_s > MAX_CLIP_SECONDS:
        return None
    if end_s - start_s >= (match.duration_s or 0):  # a short recording still cannot become a full-match public URL
        return None
    reel = reel or _reel_payload(match, [entry])
    player = next((row for row in reel["players"] if row["roster_entry_id"] == entry.id), None)
    if not player or player["number_mismatch"]:
        return None
    window = next(
        (
            window
            for window in player["windows"]
            if window["tracklet_id"] == track.id and window["start_s"] == start_s and window["end_s"] == end_s
        ),
        None,
    )
    return (track, window) if window else None


def current_source(row):
    match = lookup(VideoMatch, row.video_match_id) if row.video_match_id else None
    entry = lookup(VideoRosterEntry, row.roster_entry_id) if row.roster_entry_id else None
    track = lookup(VideoTracklet, row.tracklet_id) if row.tracklet_id else None
    if not match or not entry or not track or entry.video_match_id != match.id:
        return False
    member = lookup(ClubRosterMember, entry.club_roster_member_id) if entry.club_roster_member_id else None
    expired = match.status == "expired" and match.blob_path is None and match.blob_etag is None
    if expired and (row.render_status != "ready" or row.player_decision != "approve"):
        return False  # a missing source cannot create a new cut
    frozen_etag = row.source_etag if expired else None
    return bool(
        match.club_program_id == row.program_id
        and member_subject(member) == row.signed_id
        and match.status in {"finalized", "expired"}
        and track.roster_entry_id == entry.id
        and source_fingerprint(match, entry, track, frozen_etag=frozen_etag) == row.source_fingerprint
        and adult_recording(match, frozen_etag=frozen_etag)
    )


def eligible(row):
    evidence = read_evidence()
    if evidence is not None and row.id in evidence["eligible"]:
        return evidence["eligible"][row.id]
    program = lookup(ClubProgram, row.program_id)
    claim = lookup(PlayerProfileClaim, row.claim_id) if row.claim_id else None
    # Pending/private previews never outlive either their response window or raw retention.
    if row.player_decision != "approve":
        from datetime import timedelta

        match = lookup(VideoMatch, row.video_match_id)
        raw_deadline = (
            match.expires_at or ((match.uploaded_at or match.created_at) + timedelta(days=90)) if match else None
        )
        if row.created_at < now() - timedelta(days=14) or (raw_deadline is not None and raw_deadline <= now()):
            return False
    allowed = bool(
        enabled()
        and not row.revoked_at
        and row.club_picked_at
        and program
        and (row.program_id in evidence["listed"] if evidence is not None else is_listed(program))
        and (row.signed_id in evidence["adults"] if evidence is not None else is_public_adult(row.signed_id))
        and own_claim(claim, row.signed_id, row.recipient_user_id)
        and current_source(row)
    )
    if evidence is not None:
        evidence["eligible"][row.id] = allowed
    return allowed


def public(row, *, allowed=None):
    return bool(
        (eligible(row) if allowed is None else allowed)
        and row.player_decision == "approve"
        and row.decision_user_id == row.recipient_user_id
        and row.approved_source_version == row.source_version
        and preview_ready(row)
    )


def preview_ready(row):
    return bool(
        row.render_status == "ready"
        and row.render_source_version == row.source_version
        and row.output_blob_path
        and row.output_etag
    )


def event(row, actor_id, action):
    db.session.add(
        HighlightConsentEvent(
            highlight_id=row.id,
            actor_user_id=actor_id,
            action=action,
            version=row.version,
            source_version=row.source_version,
        )
    )


def notify(row):
    # Notification failure must never prevent revocation or consent writes.
    from sqlalchemy.exc import SQLAlchemyError
    from src.services.notification_outbox import enqueue

    try:
        with db.session.begin_nested():
            enqueue(
                dedupe_key=f"highlight:{row.id}:{row.version}:{row.recipient_user_id}",
                recipient_user_id=row.recipient_user_id,
                event_type="highlight_request",
                entity_type="user_account",
                entity_id=row.recipient_user_id,
                template="highlight_request",
                payload={"highlight_id": row.id, "version": row.version},
            )
    except SQLAlchemyError:
        pass  # Savepoint preserves the publication/consent transaction.


def queue_cut(row):
    live = (
        HighlightRenderJob.query.filter_by(highlight_id=row.id, source_version=row.source_version)
        .filter(HighlightRenderJob.kind == "highlight_cut", HighlightRenderJob.status.in_(("queued", "running")))
        .first()
    )
    if not live:
        db.session.add(HighlightRenderJob(highlight_id=row.id, source_version=row.source_version, kind="highlight_cut"))
        row.render_status = "queued"


def pick(match, data, actor):
    # Program+match lock serializes picks/caps and source editing on this match.
    db.session.refresh(match, with_for_update=True)
    if not adult_recording(match) or club_publication_held(match.club_program_id):
        raise ValueError("adult_recording_review_required")
    entry_id = data.get("roster_entry_id")
    tracklet_id = data.get("tracklet_id")
    if type(entry_id) is not int or type(tracklet_id) is not int:
        raise ValueError("reviewed_window_required")
    entry = VideoRosterEntry.query.filter_by(id=entry_id, video_match_id=match.id).first()
    if not entry:
        raise ValueError("reviewed_window_required")
    selected = reviewed_window(match, entry, tracklet_id, data.get("start_s"), data.get("end_s"))
    if selected is None:
        raise ValueError("reviewed_window_required")
    track, window = selected
    member = lookup(ClubRosterMember, entry.club_roster_member_id)
    pid = member_subject(member)
    claim = claim_for_subject(pid)
    if not claim or not is_public_adult(pid) or not resolve_public_adult_subject(pid):
        raise ValueError("adult_self_claim_required")
    if (pid > 0 and report_subject(match, entry) != pid) or (pid < 0 and report_subject(match, entry) != pid):
        raise ValueError("reviewed_identity_required")
    title = data.get("title", "Match moment")
    if not isinstance(title, str) or not title.strip() or len(title) > 160 or any(ord(c) < 32 for c in title):
        raise ValueError("invalid_title")
    fingerprint = source_fingerprint(match, entry, track)
    key = digest([match.id, entry.id, track.id, window, fingerprint, title.strip(), claim.id])
    existing = PlayerHighlight.query.filter_by(pick_key=key).first()
    while existing and existing.revoked_at:
        # A new club pick after removal is a fresh request with no inherited consent.
        key = digest([key, existing.id, existing.version])
        existing = PlayerHighlight.query.filter_by(pick_key=key).first()
    if existing:
        return existing, False
    if (
        PlayerHighlight.query.filter_by(video_match_id=match.id).filter(PlayerHighlight.revoked_at.is_(None)).count()
        >= MAX_CLIPS_PER_MATCH
    ):
        raise ValueError("highlight_limit_reached")
    from datetime import timedelta

    if (
        PlayerHighlight.query.filter_by(video_match_id=match.id)
        .filter(PlayerHighlight.created_at >= now() - timedelta(days=1))
        .count()
        >= 500
    ):
        raise ValueError("highlight_daily_limit_reached")
    row = PlayerHighlight(
        program_id=match.club_program_id,
        video_match_id=match.id,
        roster_entry_id=entry.id,
        tracklet_id=track.id,
        player_api_id=pid if pid > 0 else None,
        local_player_id=-pid if pid < 0 else None,
        claim_id=claim.id,
        recipient_user_id=claim.user_account_id,
        picker_user_id=actor.id,
        source_etag=match.blob_etag,
        source_snapshot=match.scoped_snapshot,
        source_fingerprint=fingerprint,
        pick_key=key,
        start_s=window["start_s"],
        end_s=window["end_s"],
        title=title.strip(),
    )
    db.session.add(row)
    db.session.flush()
    event(row, actor.id, "club_pick")
    record_admin_event(
        actor,
        "highlight_pick",
        "player_highlight",
        row.id,
        "Club selected reviewed window",
        meta={"program_id": row.program_id, "match_id": match.id},
    )
    queue_cut(row)
    notify(row)
    return row, True


def report_subject(match, entry):
    evidence = read_evidence()
    report = (
        next(
            (
                r
                for r in evidence["models"].get(VideoPlayerReport, {}).values()
                if r.video_match_id == match.id and r.roster_entry_id == entry.id
            ),
            None,
        )
        if evidence is not None
        else VideoPlayerReport.query.filter_by(video_match_id=match.id, roster_entry_id=entry.id).first()
    )
    return (
        (
            report.club_player_api_id_at_finalize
            if report.club_player_api_id_at_finalize is not None
            else -report.club_local_player_id_at_finalize
            if report.club_local_player_id_at_finalize
            else None
        )
        if report
        else None
    )


def revoke(row, actor_id, reason):
    if row.revoked_at:
        return
    from src.workers.highlight_worker import queue_cleanup

    paths = {job.blob_path for job in HighlightRenderJob.query.filter_by(highlight_id=row.id) if job.blob_path}
    if row.output_blob_path:
        paths.add(row.output_blob_path)
    for path in paths:
        queue_cleanup(path)
    row.revoked_at = now()
    row.revoke_reason = reason
    row.player_decision = "private"
    row.approved_source_version = None
    row.version += 1
    HighlightRenderJob.query.filter_by(highlight_id=row.id).filter(
        HighlightRenderJob.status.in_(("queued", "running"))
    ).update({"status": "cancelled", "lease_token": None}, synchronize_session=False)
    event(row, actor_id, reason)


def decide(row, actor, decision, version):
    if type(version) is not int or version != row.version:
        raise ValueError("version_conflict")
    if decision not in {"approve", "private"}:
        raise ValueError("invalid_decision")
    if row.recipient_user_id != actor.id or not own_claim(
        lookup(PlayerProfileClaim, row.claim_id), row.signed_id, actor.id
    ):
        raise ValueError("adult_self_claim_required")
    if decision == "approve" and (not eligible(row) or not preview_ready(row)):
        raise ValueError("highlight_unavailable")
    row.player_decision = decision
    row.decision_at = now()
    row.decision_user_id = actor.id
    row.approved_source_version = row.source_version if decision == "approve" else None
    row.version += 1
    event(row, actor.id, decision)
    if decision == "private":
        discard_preview(row)


def discard_preview(row):
    from src.workers.highlight_worker import queue_cleanup

    paths = {job.blob_path for job in HighlightRenderJob.query.filter_by(highlight_id=row.id) if job.blob_path}
    if row.output_blob_path:
        paths.add(row.output_blob_path)
    for path in paths:
        queue_cleanup(path)
    HighlightRenderJob.query.filter_by(highlight_id=row.id).filter(
        HighlightRenderJob.kind == "highlight_cut", HighlightRenderJob.status.in_(("queued", "running"))
    ).update({"status": "cancelled", "lease_token": None}, synchronize_session=False)
    row.render_status = "stale"
    row.output_blob_path = None
    row.output_etag = None
    row.output_bytes = None
    row.render_source_version = None


def dto(row, *, private=False):
    allowed = eligible(row)
    is_public = public(row, allowed=allowed)
    if row.revoked_at:
        label = "Taken back" if row.revoke_reason == "player_revoke" else "Removed · private"
    elif is_public:
        label = "Public on your page"
    elif row.render_status == "failed":
        label = "Clip not made · still private"
    elif row.player_decision == "approve":
        label = "Approved · preparing clip" if allowed else "Unavailable · still private"
    elif row.player_decision == "private":
        label = "Kept private"
    else:
        label = "Waiting for you"
    program = lookup(ClubProgram, row.program_id)
    out = {
        "id": row.id,
        "title": row.title,
        "duration_s": round(row.end_s - row.start_s, 2),
        "program_id": row.program_id,
        "club_name": program.name if program else None,
        "player_id": row.signed_id,
        "clip_url": f"/api/highlights/{row.id}/clip" if is_public else None,
    }
    if private:
        out.update(
            version=row.version,
            player_decision=row.player_decision,
            render_status=row.render_status,
            status_label=label,
            can_approve=allowed and preview_ready(row),
            can_retry=allowed and row.render_status in {"failed", "stale"},
            revoked=bool(row.revoked_at),
            preview_url=f"/api/me/highlight-requests/{row.id}/preview" if preview_ready(row) and allowed else None,
            start_s=row.start_s,
            end_s=row.end_s,
            roster_entry_id=row.roster_entry_id,
            tracklet_id=row.tracklet_id,
        )
    return out


def register_notifications():
    from src.services.notification_outbox import register_template

    def notification_eligible(intent, user):
        row = db.session.get(PlayerHighlight, (intent.payload or {}).get("highlight_id"))
        return bool(
            row
            and row.recipient_user_id == user.id
            and row.version == (intent.payload or {}).get("version")
            and row.player_decision == "pending"
            and eligible(row)
        )

    register_template(
        "highlight_request",
        eligible=notification_eligible,
        render=notification_render,
    )


def candidates(match):
    if not adult_recording(match):
        return []
    from src.routes.video import _reel_payload

    out = []
    evidence = read_evidence()
    if evidence is not None:
        from src.services.video_reels import build_reel_payload

        tracks = [
            t
            for t in evidence["models"].get(VideoTracklet, {}).values()
            if t.video_match_id == match.id and t.kind != "tombstone"
        ]
        reel = build_reel_payload(match, roster_entries(match.id), tracks)
    else:
        reel = _reel_payload(match)
    for player in reel["players"]:
        entry = lookup(VideoRosterEntry, player["roster_entry_id"])
        member = lookup(ClubRosterMember, entry.club_roster_member_id) if entry.club_roster_member_id else None
        pid = member_subject(member)
        if (
            not pid
            or not (pid in evidence["adults"] if evidence is not None else is_public_adult(pid))
            or not claim_for_subject(pid)
            or report_subject(match, entry) != pid
        ):
            continue
        for window in player["windows"]:
            if len(out) >= 100:
                return out
            if reviewed_window(match, entry, window["tracklet_id"], window["start_s"], window["end_s"], reel=reel):
                out.append(
                    {"roster_entry_id": entry.id, "player_name": player["player_name"], "player_id": pid, **window}
                )
    return out


def notification_render(intent, user):
    from html import escape

    link = os.getenv("PUBLIC_BASE_URL", "https://theacademywatch.com").rstrip("/") + "/highlight-approvals"
    return {
        "subject": "A highlight is waiting for your decision",
        "html": f'<p>Sign in to Academy Watch to review a highlight request.</p><p><a href="{escape(link, quote=True)}">Review highlights</a></p>',
        "text": f"Sign in to Academy Watch to review a highlight request. {link}",
    }
