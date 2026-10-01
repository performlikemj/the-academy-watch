"""Canonical, batched public-adult eligibility for new Phase 2 paths.

Mirrors resolve_public_adult_subject identity/bridge/suppression gates, with
stricter DOB evidence. Legacy age policy is unchanged. Both scalar and paged
checks share this loaded-source evaluation instead of per-candidate queries.
"""

from collections import defaultdict
from datetime import UTC, datetime

import sqlalchemy as sa
from src.models.follow import PlayerShadow
from src.models.journey import PlayerJourney
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import LocalPlayer, local_player_is_minor
from src.models.tracked_player import TrackedPlayer
from src.services.club_publication_hold import held_subject_ids
from src.services.public_player_subject import MAX_SIGNED_PLAYER_ID
from src.utils.academy_window import age_from_birth_date


def _valid_id(pid):
    return isinstance(pid, int) and not isinstance(pid, bool) and 0 < abs(pid) <= MAX_SIGNED_PLAYER_ID


def public_adult_ids(signed_ids, *, ignore_publication_holds=False):
    """At most five IN-source queries plus one hold query, regardless of page size."""
    ids = set(pid for pid in signed_ids if _valid_id(pid))
    if not ids:
        return set()
    positive = {pid for pid in ids if pid > 0}
    local_ids = {-pid for pid in ids if pid < 0}
    locals_ = (
        LocalPlayer.query.filter(sa.or_(LocalPlayer.api_player_id.in_(ids), LocalPlayer.id.in_(local_ids)))
        .populate_existing()
        .all()
    )
    locals_by_subject = defaultdict(list)
    for local in locals_:
        if local.api_player_id in ids:
            locals_by_subject[local.api_player_id].append(local)
        if -local.id in ids and local.api_player_id != -local.id:
            locals_by_subject[-local.id].append(local)
    tracked = defaultdict(list)
    shadows, journeys = {}, {}
    if positive:
        for row in TrackedPlayer.query.filter(TrackedPlayer.player_api_id.in_(positive)).populate_existing().all():
            tracked[row.player_api_id].append(row)
        shadows = {
            row.player_api_id: row
            for row in PlayerShadow.query.filter(
                PlayerShadow.player_api_id.in_(positive), PlayerShadow.is_active.is_(True)
            )
            .populate_existing()
            .all()
        }
        journeys = {
            row.player_api_id: row
            for row in PlayerJourney.query.filter(PlayerJourney.player_api_id.in_(positive)).populate_existing().all()
        }
    if local_ids:
        shadows.update(
            {
                row.player_api_id: row
                for row in PlayerShadow.query.filter(
                    PlayerShadow.player_api_id.in_(ids), PlayerShadow.is_active.is_(True)
                )
                .populate_existing()
                .all()
            }
        )
    local_to_subjects = defaultdict(set)
    for pid, rows in locals_by_subject.items():
        for local in rows:
            local_to_subjects[local.id].add(pid)
    suppressed = set()
    for row in PlayerSuppression.query.filter(
        PlayerSuppression.status == "active",
        sa.or_(
            PlayerSuppression.player_api_id.in_(ids),
            PlayerSuppression.local_player_id.in_(set(local_to_subjects) | local_ids),
        ),
    ).all():
        if row.player_api_id in ids:
            suppressed.add(row.player_api_id)
        if row.local_player_id is not None:
            suppressed.update(local_to_subjects[row.local_player_id])
            if -row.local_player_id in ids:
                suppressed.add(-row.local_player_id)
    from src.services.club_player_publication import enabled, publication_local_ids

    published = set()
    if enabled() and any(row.provenance == "club" for row in locals_):
        published = {
            id_
            for (id_,) in LocalPlayer.query.with_entities(LocalPlayer.id)
            .filter(LocalPlayer.id.in_([row.id for row in locals_]), LocalPlayer.id.in_(publication_local_ids()))
            .all()
        }
    # Only reversible B2 application reconciliation bypasses holds; public reads use the default.
    excluded = suppressed | (set() if ignore_publication_holds else held_subject_ids(ids))
    today = datetime.now(UTC).date()
    eligible = set()
    for pid in ids - excluded:
        local_rows = locals_by_subject[pid]
        if pid < 0:
            if not any(
                local.id == -pid
                and local.api_player_id == pid
                and local.status == "approved"
                and local.merged_into_local_player_id is None
                and (local.provenance != "club" or local.id in published)
                for local in local_rows
            ):
                continue
        elif not (any(row.data_source != "owning-club" for row in tracked[pid]) or pid in shadows):
            continue
        if any(
            (local.provenance == "club" and (pid > 0 or local.id not in published))
            or local_player_is_minor(local, today=today)
            for local in local_rows
        ):
            continue
        sources = list(local_rows) + tracked[pid]
        sources += [row for row in (shadows.get(pid), journeys.get(pid)) if row is not None]
        dates = [row.birth_date for row in sources if row.birth_date is not None]
        if dates:
            ages = [age_from_birth_date(value, today=today) for value in dates]
            adult = all(age is not None and age >= 18 for age in ages)
        else:
            adult = not any(row.age is not None and row.age < 18 for row in tracked[pid]) and any(
                local.birth_year is not None and local.birth_year < today.year - 18 for local in local_rows
            )
        if adult:
            eligible.add(pid)
    return eligible


def is_public_adult(subject) -> bool:
    """Signed ID or PlayerSubject; recheck current sources rather than stale flags."""
    pid = getattr(subject, "signed_id", subject)
    return _valid_id(pid) and pid in public_adult_ids([pid])


def filter_public_adults(query, signed_id_column, *, max_candidates=100, after=None):
    """Return a filtered Query for one signed-ID candidate page (default 100).

    Apply search constraints first. Keyset pagination uses `after`, the last
    candidate signed ID (including ineligible candidates), returned in the
    Query execution option `p2_adult_next_cursor` (None at end). Apply presentation ordering after this helper.
    Empty eligible pages do not mean the candidate universe is exhausted.
    Revalidate final reads/bytes. No OFFSET or per-candidate DB work is needed.
    """
    if isinstance(max_candidates, bool) or not isinstance(max_candidates, int) or not 1 <= max_candidates <= 100:
        raise ValueError("max_candidates must be between 1 and 100")
    if after is not None and not _valid_id(after):
        raise ValueError("after must be a nonzero signed player ID")
    candidates = query.with_entities(signed_id_column).order_by(None).distinct()
    if after is not None:
        candidates = candidates.filter(signed_id_column > after)
    ids = [pid for (pid,) in candidates.order_by(signed_id_column).limit(max_candidates + 1).all()]
    next_cursor = ids[max_candidates - 1] if len(ids) > max_candidates else None
    ids = ids[:max_candidates]
    return query.filter(signed_id_column.in_(public_adult_ids(ids))).execution_options(p2_adult_next_cursor=next_cursor)
