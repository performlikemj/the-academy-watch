"""Academy tracking window — the platform's core data scope.

The Academy Watch tracks players who are in a club's academy NOW or were in
it within the past ACADEMY_WINDOW_YEARS seasons (default 4). Older alumni —
however famous — are out of scope: a 28-year-old who left the academy a
decade ago is not "up-and-coming talent".

Seasons are API-Football season-start years (2025 == the 2025-26 season).
The current season rolls over on 1 July, matching the European calendar.
"""

import os
from datetime import date, datetime

# Oldest age at which a player can plausibly still be an academy/development
# squad member (aligns with UEFA development squad rules). Shared with
# academy_classifier's development-signing benefit-of-the-doubt rule.
DEVELOPMENT_AGE_CUTOFF = 21


def _window_years() -> int:
    try:
        return max(int(os.getenv("ACADEMY_WINDOW_YEARS", "4")), 0)
    except ValueError:
        return 4


def current_academy_season(today: date | None = None) -> int:
    """Season-start year of the season in progress (July rollover)."""
    today = today or date.today()
    return today.year if today.month >= 7 else today.year - 1


def academy_window_start(today: date | None = None) -> int:
    """Oldest season-start year still inside the tracking window."""
    return current_academy_season(today) - _window_years()


def current_stats_season(today: date | datetime | None = None) -> int:
    """Season-start year for STATS DISPLAY / fixture data (August rollover).

    Two "current season" rules exist on purpose — do NOT collapse them:

    - ``current_academy_season`` rolls over on **1 July** because it gates the
      ACADEMY TRACKING WINDOW: when the youth calendar turns over in summer a
      player's academy eligibility should advance immediately, so July is the
      right hinge for who is still "in window".
    - ``current_stats_season`` rolls over on **1 August** because it selects
      which SEASON'S FIXTURES to show. European league football starts in
      August; rolling in July would point at a season that has no matches yet
      and blank every stats page for a month.

    Callers that display or sync fixture/stats data want THIS helper; callers
    that gate academy eligibility want ``current_academy_season``.
    """
    if isinstance(today, datetime):
        today = today.date()
    today = today or date.today()
    return today.year if today.month >= 8 else today.year - 1


def stats_season_with_data(db_session, today: date | datetime | None = None) -> int:
    """``current_stats_season`` but never point at a season with no fixtures.

    The calendar season (e.g. 2026 on 1 Aug 2026) can roll over before any
    fixtures for it have been ingested. Using it directly would blank every
    stats page platform-wide until the new season's fixtures land. When the
    calendar season has zero fixture rows this falls back to the latest season
    that actually HAS fixtures (``MAX(fixtures.season)``).

    DISPLAY paths only. Data-fetching / sync paths (transfer heal, newsletter
    generation, API-Football season priming) must use ``current_stats_season``
    so they fetch the real upcoming season instead of being pinned to old data.
    """
    from sqlalchemy import func
    from src.models.weekly import Fixture

    calendar_season = current_stats_season(today)
    has_current = db_session.query(Fixture.id).filter(Fixture.season == calendar_season).first() is not None
    if has_current:
        return calendar_season
    latest = db_session.query(func.max(Fixture.season)).scalar()
    return latest if latest is not None else calendar_season


def age_from_birth_date(birth_date, today: date | None = None) -> int | None:
    """Floor years between a 'YYYY-MM-DD...' birth date string and today.

    Returns None when the value is missing, unparseable, or yields a
    nonsensical age.
    """
    if not birth_date:
        return None
    try:
        born = date.fromisoformat(str(birth_date).strip()[:10])
    except ValueError:
        return None
    today = today or date.today()
    age = today.year - born.year - ((today.month, today.day) < (born.month, born.day))
    if age < 0 or age > 100:
        return None
    return age


def is_within_academy_window(
    last_academy_season: int | None,
    *,
    status: str | None = None,
    birth_date: str | None = None,
    today: date | datetime | None = None,
) -> bool:
    """Should a player still be tracked by their academy club?

    Evidence order:
    1. status == 'academy' → currently in the academy, always in window
       (protects current academy kids whose youth-league entries lag).
    2. last_academy_season (their last youth season at the parent club)
       inside [current_season - window, current_season].
    3. No season evidence → development age (≤ DEVELOPMENT_AGE_CUTOFF) from
       birth_date. Unknown birth date → out of window: with no evidence of
       recent academy involvement we do not track.
    """
    if isinstance(today, datetime):
        today = today.date()
    if status == "academy":
        return True
    if last_academy_season is not None:
        return last_academy_season >= academy_window_start(today)
    age = age_from_birth_date(birth_date, today)
    return age is not None and age <= DEVELOPMENT_AGE_CUTOFF


def last_academy_season_for(journey, parent_api_id: int) -> int | None:
    """Last youth season evidence for a journey at a given parent club.

    Prefers the per-club academy_last_seasons map. Journeys synced before
    migration aw18 have no map yet — fall back to the most recent youth
    season anywhere in the journey, so seed/rebuild gates don't silently
    drop in-window 22-25-year-old alumni before the recompute repair has
    populated the map (provenance is already established by the caller via
    academy_club_ids membership).
    """
    if journey is None:
        return None
    mapped = (journey.academy_last_seasons or {}).get(str(parent_api_id))
    if mapped is not None:
        return mapped
    from src.models.journey import PlayerJourneyEntry

    row = (
        PlayerJourneyEntry.query.filter_by(journey_id=journey.id)
        .filter(
            PlayerJourneyEntry.is_youth.is_(True),
            PlayerJourneyEntry.is_international.is_(False),
            PlayerJourneyEntry.entry_type.in_(("academy", "development")),
        )
        .order_by(PlayerJourneyEntry.season.desc())
        .first()
    )
    return row.season if row else None
