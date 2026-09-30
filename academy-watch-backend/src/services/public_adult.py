"""Canonical eligibility for NEW Phase 2 public paths; legacy callers unchanged."""

from datetime import UTC, datetime

from src.models.follow import PlayerShadow
from src.models.journey import PlayerJourney
from src.models.showcase import LocalPlayer, local_player_is_minor
from src.models.tracked_player import TrackedPlayer
from src.services.club_publication_hold import subject_publication_held
from src.services.public_player_subject import resolve_public_adult_subject
from src.utils.academy_window import age_from_birth_date


def is_public_adult(subject) -> bool:
    """Accept a signed ID or PlayerSubject; re-resolve rather than trust stale flags.

    Require DOB evidence or a conservatively adult local birth year. Stored API
    age alone is insufficient for new publication. All known DOBs must be adult.
    """
    signed_id = getattr(subject, "signed_id", subject)
    resolved = resolve_public_adult_subject(signed_id)
    if resolved is None or subject_publication_held(signed_id):
        return False
    locals_ = LocalPlayer.query.filter_by(api_player_id=signed_id).all()
    if any(local_player_is_minor(local) for local in locals_):
        return False
    sources = list(locals_)
    if signed_id > 0:
        sources += TrackedPlayer.query.filter_by(player_api_id=signed_id).all()
        sources += PlayerJourney.query.filter_by(player_api_id=signed_id).all()
        sources += PlayerShadow.query.filter_by(player_api_id=signed_id, is_active=True).all()
    today = datetime.now(UTC).date()
    dates = [source.birth_date for source in sources if source.birth_date is not None]
    if dates:
        ages = [age_from_birth_date(value, today=today) for value in dates]
        return all(age is not None and age >= 18 for age in ages)
    return any(local.birth_year is not None and local.birth_year < today.year - 18 for local in locals_)


def filter_public_adults(query, signed_id_column, *, max_candidates=1000):
    """Filter a bounded SQLAlchemy Query using the exact canonical predicate.

    Apply ordinary search constraints first, this filter before limit/offset.
    It intentionally avoids a second SQL age policy. Final read/byte endpoints
    must revalidate with is_public_adult. Large discovery must page candidates
    explicitly (exceeding the bound raises rather than silently truncate).
    """
    if isinstance(max_candidates, bool) or not isinstance(max_candidates, int) or not 1 <= max_candidates <= 1000:
        raise ValueError("max_candidates must be between 1 and 1000")
    ids = query.with_entities(signed_id_column).order_by(None).distinct().limit(max_candidates + 1).all()
    if len(ids) > max_candidates:
        raise ValueError("public adult candidate query exceeds its bound")
    eligible = [signed_id for (signed_id,) in ids if is_public_adult(signed_id)]
    return query.filter(signed_id_column.in_(eligible))
