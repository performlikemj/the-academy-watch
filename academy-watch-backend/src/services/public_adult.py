"""Canonical, batched public-adult eligibility for new Phase 2 paths.

Mirrors resolve_public_adult_subject identity/bridge/suppression gates, with
stricter DOB evidence. Legacy age policy is unchanged. Both scalar and paged
checks share this loaded-source evaluation instead of per-candidate queries.
"""

from collections import defaultdict
from datetime import UTC, datetime
from hashlib import sha256

import sqlalchemy as sa
from src.models.follow import PlayerShadow
from src.models.journey import PlayerJourney
from src.models.league import db
from src.models.player_suppression import PlayerSuppression
from src.models.showcase import LocalPlayer, local_player_is_minor
from src.models.tracked_player import TrackedPlayer
from src.services.club_publication_hold import held_subject_ids
from src.services.public_player_subject import MAX_SIGNED_PLAYER_ID
from src.utils.academy_window import age_from_birth_date


def _valid_id(pid):
    return isinstance(pid, int) and not isinstance(pid, bool) and 0 < abs(pid) <= MAX_SIGNED_PLAYER_ID


def public_adult_ids(signed_ids, *, trusted_birth_dates=None, allow_journeys=False, ignore_publication_holds=False):
    """Load only policy columns in four set queries, regardless of candidate count.

    GOL alone may admit a stored journey as identity evidence. Scout discovery
    and Phase 2 keep their existing tracked/shadow/local identity universe.
    Only reversible B2 reconciliation may ignore publication holds.
    """
    # Only server-fetched API profiles may supply additional DOB evidence.
    # Request payloads, age snapshots and caller-supplied seeds are never evidence.
    trusted_birth_dates = trusted_birth_dates or {}
    ids = set(pid for pid in signed_ids if _valid_id(pid))
    if not ids:
        return set()
    positive = {pid for pid in ids if pid > 0}
    local_ids = {-pid for pid in ids if pid < 0}
    locals_ = (
        db.session.query(
            LocalPlayer.id,
            LocalPlayer.api_player_id,
            LocalPlayer.status,
            LocalPlayer.provenance,
            LocalPlayer.merged_into_local_player_id,
            LocalPlayer.birth_date,
            LocalPlayer.birth_year,
        )
        .filter(sa.or_(LocalPlayer.api_player_id.in_(ids), LocalPlayer.id.in_(local_ids)))
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
    # A narrow evidence relation avoids loading ORM identities/JSON blobs and
    # keeps SQL count constant as the desk grows. Cast Date shadows to the same
    # ISO strings used by tracked/journey evidence; parsing remains fail closed.
    evidence = sa.union_all(
        sa.select(
            TrackedPlayer.player_api_id,
            TrackedPlayer.birth_date,
            TrackedPlayer.age,
            TrackedPlayer.data_source,
            sa.literal("tracked").label("kind"),
        ).where(TrackedPlayer.player_api_id.in_(positive)),
        sa.select(
            PlayerJourney.player_api_id,
            PlayerJourney.birth_date,
            sa.literal(None),
            sa.literal(None),
            sa.literal("journey"),
        ).where(PlayerJourney.player_api_id.in_(positive)),
        sa.select(
            PlayerShadow.player_api_id,
            sa.cast(PlayerShadow.birth_date, sa.String),
            sa.literal(None),
            sa.literal(None),
            sa.literal("shadow"),
        ).where(PlayerShadow.player_api_id.in_(ids), PlayerShadow.is_active.is_(True)),
    )
    for row in db.session.execute(evidence):
        if row.kind == "tracked":
            tracked[row.player_api_id].append(row)
        elif row.kind == "journey":
            journeys[row.player_api_id] = row
        else:
            # Negative shadows carry DOB evidence too. Local approval still
            # decides admission; orphan shadows cannot create a public local.
            shadows[row.player_api_id] = row
    local_to_subjects = defaultdict(set)
    for pid, rows in locals_by_subject.items():
        for local in rows:
            local_to_subjects[local.id].add(pid)
    suppressed = set()
    for row in (
        db.session.query(PlayerSuppression.player_api_id, PlayerSuppression.local_player_id)
        .filter(
            PlayerSuppression.status == "active",
            sa.or_(
                PlayerSuppression.player_api_id.in_(ids),
                PlayerSuppression.local_player_id.in_(set(local_to_subjects) | local_ids),
            ),
        )
        .all()
    ):
        if row.player_api_id in ids:
            suppressed.add(row.player_api_id)
        if row.local_player_id is not None:
            suppressed.update(local_to_subjects[row.local_player_id])
            if -row.local_player_id in ids:
                suppressed.add(-row.local_player_id)
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
                and local.provenance != "club"
                for local in local_rows
            ):
                continue
        elif not (
            any(row.data_source != "owning-club" for row in tracked[pid])
            or pid in shadows
            or pid in trusted_birth_dates
            or (allow_journeys and pid in journeys)
        ):
            continue
        if any(local.provenance == "club" or local_player_is_minor(local, today=today) for local in local_rows):
            continue
        sources = list(local_rows) + tracked[pid]
        sources += [row for row in (shadows.get(pid), journeys.get(pid)) if row is not None]
        dates = [row.birth_date for row in sources if row.birth_date is not None]
        dates.extend(value for value in trusted_birth_dates.get(pid, []) if value is not None)
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


def gol_public_adult_ids(signed_ids):
    """GOL identity adapter: exact stored journey DOBs may establish adulthood."""
    return public_adult_ids(signed_ids, allow_journeys=True)


def filter_public_adult_query(query, signed_id_column, *, eligibility_cache=None, allow_journeys=False):
    """Filter constrained candidates before ordering, pagination or ranking.

    Cache lifetime belongs to the caller: one request or one digest run. Policy
    columns are loaded together, rather than repeating source queries per 500
    identities. GOL explicitly opts in to its historical journey universe.
    """
    ids = [pid for (pid,) in query.with_entities(signed_id_column).order_by(None).distinct().all()]
    if allow_journeys:
        eligible = gol_public_adult_ids(ids)
    else:
        eligible = cached_public_adult_ids(ids, eligibility_cache if eligibility_cache is not None else {})
    return query.filter(signed_id_column.in_(eligible)).execution_options(public_adult_candidate_count=len(eligible))


def public_adult_profile_ids(profiles):
    """Strict rule for trusted upstream search results, without persisting them.

    Existing contradictory DOBs, local bridges, suppression and holds still
    veto a result. Missing upstream DOB does not establish adult age.
    """
    dates = {}
    for row in profiles:
        player = (row or {}).get("player") or {}
        pid = player.get("id")
        if _valid_id(pid) and pid > 0:
            dates.setdefault(pid, []).append((player.get("birth") or {}).get("date"))
    return public_adult_ids(dates, trusted_birth_dates=dates)


def scout_adult_policy_revision():
    """Bind stored GOL replays to current eligibility, including legacy answers.

    Stored prose does not reliably carry referenced IDs, so hash both the known
    universe and excluded set. Removals, DOB corrections, suppression and holds
    invalidate answers; additions also invalidate as a conservative trade-off.
    Versioning rejects older replays. GOL journey identities are included, so
    deletion of a journey-only adult also invalidates stored prose.
    """
    ids = {
        pid
        for model in (TrackedPlayer, PlayerShadow, LocalPlayer, PlayerJourney)
        for (pid,) in db.session.query(model.api_player_id if model is LocalPlayer else model.player_api_id)
        .distinct()
        .all()
        if _valid_id(pid)
    }
    ordered = sorted(ids)
    eligible = gol_public_adult_ids(ordered)
    excluded = ",".join(str(pid) for pid in sorted(ids - eligible))
    known = ",".join(str(pid) for pid in ordered)
    return sha256(f"scout-adults-v3:{known}:{excluded}".encode()).hexdigest()


def is_public_adult(subject) -> bool:
    """Signed ID or PlayerSubject; recheck current sources rather than stale flags."""
    pid = getattr(subject, "signed_id", subject)
    return _valid_id(pid) and pid in public_adult_ids([pid])


def cached_public_adult_ids(signed_ids, cache: dict) -> set[int]:
    """Batch and memoise eligible AND ineligible IDs in a caller-owned run cache.

    The namespace is separate from integer-keyed player states, so even a
    prefilled state must pass eligibility once. Never reuse this cache across
    runs; ordinary public reads continue to recheck current eligibility.
    """
    ids = {pid for pid in signed_ids if _valid_id(pid)}
    eligibility = cache.setdefault("__public_adult_eligibility__", {})
    missing = sorted(pid for pid in ids if pid not in eligibility)
    if missing:
        adults = public_adult_ids(missing)
        eligibility.update((pid, pid in adults) for pid in missing)
    return {pid for pid in ids if eligibility[pid]}


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
