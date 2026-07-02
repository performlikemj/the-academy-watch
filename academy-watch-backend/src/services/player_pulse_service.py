"""Player pulse — deterministic per-player-per-window newsworthiness scoring.

This is the CHEAP half of the digest split: no LLM, no per-audience work. Every
followed player (deduped across all active follow lists + the legacy watchlist)
is scored ONCE per window into ``player_pulse``. LLM cost (the separate card
step) then scales with the newsworthy slice of the content universe, never with
audience size.

Signals (documented weighted sum — see ``PULSE_WEIGHTS``):

- stat deltas — goals / assists / appearances / minutes in the window, windowed
  by ``Fixture.date_utc`` at the player's current club (the same delta concept
  scout_digest_service renders today, computed globally instead of per user).
- status change — ``PlayerJourney.current_status`` coalesced with
  ``TrackedPlayer.status`` vs the previous window's recorded status.
- milestones — first senior appearance (debut), first senior goal, first senior
  start, and level jump (U18 -> U21 -> ... -> Senior) vs the prior window. The
  "firsts" are inferred from partial-coverage FixturePlayerStats, so they fire
  ONLY when the fuller career history (PlayerJourney entries + PlayerStatsCache)
  corroborates them (``_senior_career_evidence``) — otherwise a player whose
  earlier senior career lives out of coverage would fabricate a career-first.
- per-90 spike — this window's goal-involvement per 90 vs the player's own
  prior-fixtures baseline (reuses ``radar_stats_service.compute_player_per90``).
- injury new / cleared — OPT-IN only: skipped unless an ``api_client`` is passed
  explicitly. The bulk path never passes one, so pulse makes ZERO live API
  calls — the load-bearing "flat cost / audience-independent" invariant.

``delta_json`` records every contributing signal with its raw value, weight and
points (provenance) plus a small verified player-context block the card prompt is
allowed to read. Upserts are idempotent so re-running a window is a no-op.
"""

import logging
import os
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import func, or_
from src.models.follow import FollowList, PlayerShadow
from src.models.journey import PlayerJourney
from src.models.league import PlayerStatsCache, db
from src.models.pulse import PlayerPulse
from src.models.scout_watchlist import ScoutWatchlistEntry
from src.models.tracked_player import TrackedPlayer
from src.models.weekly import Fixture, FixturePlayerStats

logger = logging.getLogger(__name__)

# Window length (days) ending on window_end. Weekly by default; env-tunable.
DEFAULT_WINDOW_DAYS = int(os.getenv("PULSE_WINDOW_DAYS", "7"))

# Documented weighted sum. Each signal contributes ``value * weight`` (counting
# signals) or a flat ``weight`` (event signals). Tuned so a single high-value
# event (promotion, debut, first goal, brace) clears the default card threshold
# (PULSE_CARD_THRESHOLD=3.0) on its own.
PULSE_WEIGHTS = {
    "goal": 2.0,  # per goal in window
    "assist": 1.5,  # per assist in window
    "appearance": 0.5,  # per appearance in window
    "minutes": 0.5,  # per full 90 played in window (minutes / 90 * weight)
    "status_change": 3.5,  # promoted / loaned / sold / released this window
    "milestone_debut": 4.0,  # first ever senior appearance
    "milestone_first_goal": 3.5,  # first ever senior goal
    "milestone_first_start": 2.5,  # first ever senior start
    "milestone_level_jump": 3.5,  # U18 -> U21 -> ... -> Senior
    "per90_spike": 2.0,  # goal-involvement per 90 spiking vs own baseline
    "injury_new": 1.5,  # new absence(s) since last window (opt-in)
    "injury_cleared": 1.5,  # absence(s) cleared since last window (opt-in)
}

# Per-90 spike gates: enough evidence both sides, and a real jump.
PER90_SPIKE_RATIO = 1.5
PER90_MIN_WINDOW_MINUTES = 45
PER90_MIN_BASELINE_MINUTES = 180

# Ordered levels for jump detection (higher rank = more advanced).
_LEVEL_RANK = {
    "U15": 1,
    "U16": 2,
    "U17": 3,
    "U18": 4,
    "U19": 5,
    "U21": 6,
    "U23": 7,
    "Reserve": 8,
    "Senior": 9,
    "First Team": 9,
}

# Local copy (not imported) so pulse does not couple to scout_digest_service.
_STATUS_LABELS = {
    "first_team": "Promoted to first team",
    "on_loan": "Sent on loan",
    "sold": "Sold",
    "released": "Released",
    "academy": "Back in the academy",
    "left": "Left the club",
}

# Top-N preview returned to the admin compute endpoint.
_TOP_PREVIEW = 10


def _coerce_window_end(window_end) -> date:
    """Accept a date, datetime, ISO string, or None (-> today, UTC)."""
    if window_end is None:
        return datetime.now(UTC).date()
    if isinstance(window_end, datetime):
        return window_end.date()
    if isinstance(window_end, date):
        return window_end
    return date.fromisoformat(str(window_end))


def _window_bounds(window_end: date, window_days: int):
    """(start_dt, end_dt, start_date) — half-open [start_dt, end_dt) covering the
    ``window_days`` calendar days ending on (and including) window_end."""
    start_date = window_end - timedelta(days=window_days - 1)
    start_dt = datetime.combine(start_date, time.min)
    end_dt = datetime.combine(window_end + timedelta(days=1), time.min)
    return start_dt, end_dt, start_date


def _all_followed_player_ids() -> set[int]:
    """Every player followed by anyone: legacy watchlist DISTINCT ids UNION each
    active FollowList's resolved set (dedup handled by the resolver, which also
    inherits the owning-club exclusion). Computed once, reused across the run."""
    from src.services.follow_resolver import resolve_list

    ids: set[int] = set()
    for (pid,) in db.session.query(ScoutWatchlistEntry.player_api_id).distinct():
        if pid is not None:
            ids.add(int(pid))
    for follow_list in FollowList.query.filter_by(is_active=True).all():
        try:
            for item in resolve_list(follow_list, limit=None):
                ids.add(int(item["player_api_id"]))
        except Exception:
            logger.exception("resolve_list failed for follow_list %s", follow_list.id)
    return ids


def _player_context(player_api_id: int) -> dict | None:
    """Verified display/status context, or None when the player is neither an
    active academy-origin TrackedPlayer nor an active PlayerShadow.

    owning-club rows are excluded (deprecated everywhere else on the scout
    surface); the player-level journey status overrides the academy-relative
    TrackedPlayer.status when set."""
    tracked = (
        TrackedPlayer.query.filter_by(player_api_id=player_api_id, is_active=True)
        .filter(TrackedPlayer.data_source != "owning-club")
        .order_by(TrackedPlayer.id)
        .first()
    )
    journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()
    if tracked is not None:
        status = (journey.current_status if journey else None) or tracked.status
        level = tracked.current_level or (journey.current_level if journey else None)
        return {
            "kind": "tracked",
            "name": tracked.player_name,
            "position": tracked.position,
            "parent_club": tracked.team.name if tracked.team else None,
            "current_club": tracked.current_club_name,
            "current_club_api_id": tracked.current_club_api_id,
            "status": status,
            "current_level": level,
        }
    shadow = PlayerShadow.query.filter_by(player_api_id=player_api_id, is_active=True).first()
    if shadow is not None:
        return {
            "kind": "shadow",
            "name": shadow.player_name,
            "position": shadow.position,
            "parent_club": None,
            "current_club": shadow.current_club_name,
            "current_club_api_id": shadow.current_club_api_id,
            "status": (journey.current_status if journey else None),
            "current_level": (journey.current_level if journey else None),
        }
    return None


def _windowed_rows(player_api_id: int, start_dt: datetime, end_dt: datetime) -> list:
    """FixturePlayerStats rows (all teams) whose fixture falls in the window."""
    return (
        db.session.query(FixturePlayerStats)
        .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
        .filter(
            FixturePlayerStats.player_api_id == player_api_id,
            Fixture.date_utc >= start_dt,
            Fixture.date_utc < end_dt,
        )
        .all()
    )


def _is_start(row) -> bool:
    return not bool(row.substitute) and int(row.minutes or 0) > 0


def _aggregate_rows(rows) -> dict:
    apps = len(rows)
    goals = sum(int(r.goals or 0) for r in rows)
    assists = sum(int(r.assists or 0) for r in rows)
    minutes = sum(int(r.minutes or 0) for r in rows)
    starts = sum(1 for r in rows if _is_start(r))
    return {"appearances": apps, "goals": goals, "assists": assists, "minutes": minutes, "starts": starts}


def _cumulative_before(player_api_id: int, start_dt: datetime) -> dict:
    """Career totals (all teams) strictly BEFORE the window — for milestone
    firsts and the per-90 baseline."""
    row = (
        db.session.query(
            func.count().label("appearances"),
            func.coalesce(func.sum(FixturePlayerStats.goals), 0).label("goals"),
            func.coalesce(func.sum(FixturePlayerStats.assists), 0).label("assists"),
            func.coalesce(func.sum(FixturePlayerStats.minutes), 0).label("minutes"),
        )
        .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
        .filter(
            FixturePlayerStats.player_api_id == player_api_id,
            Fixture.date_utc < start_dt,
        )
        .first()
    )
    starts = (
        db.session.query(func.count())
        .select_from(FixturePlayerStats)
        .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
        .filter(
            FixturePlayerStats.player_api_id == player_api_id,
            Fixture.date_utc < start_dt,
            or_(FixturePlayerStats.substitute.is_(False), FixturePlayerStats.substitute.is_(None)),
            FixturePlayerStats.minutes > 0,
        )
        .scalar()
    )
    if row is None:
        return {"appearances": 0, "goals": 0, "assists": 0, "minutes": 0, "starts": int(starts or 0)}
    return {
        "appearances": int(row.appearances or 0),
        "goals": int(row.goals or 0),
        "assists": int(row.assists or 0),
        "minutes": int(row.minutes or 0),
        "starts": int(starts or 0),
    }


def _senior_career_evidence(player_api_id: int) -> dict:
    """Fuller-career senior appearance/goal totals used to CORROBORATE milestone
    "firsts" that are otherwise inferred from partial-coverage FixturePlayerStats.

    ``FixturePlayerStats`` only covers top leagues, so a player whose earlier
    senior career lives in a lower league (``PlayerStatsCache``) or a foreign /
    prior club (``PlayerJourney`` career entries) has ``_cumulative_before`` == 0
    even though he is not a debutant — which would fabricate a career-first
    milestone. This reads the authoritative career sources so the caller can
    require positive corroboration before claiming a first.

    Returns ``has_journey`` (whether ANY career record exists to corroborate
    against — absent one we cannot confirm a first at all) plus the highest
    senior appearance / goal totals known to those sources (senior = non-youth,
    non-international journey entries; PlayerStatsCache rows are senior)."""
    journey = PlayerJourney.query.filter_by(player_api_id=player_api_id).first()
    journey_apps = 0
    journey_goals = 0
    if journey is not None:
        for entry in journey.entries.all():
            if entry.is_youth or entry.is_international:
                continue
            journey_apps += int(entry.appearances or 0)
            journey_goals += int(entry.goals or 0)
    cache_row = (
        db.session.query(
            func.coalesce(func.sum(PlayerStatsCache.appearances), 0),
            func.coalesce(func.sum(PlayerStatsCache.goals), 0),
        )
        .filter(PlayerStatsCache.player_api_id == player_api_id)
        .first()
    )
    cache_apps = int(cache_row[0] or 0) if cache_row else 0
    cache_goals = int(cache_row[1] or 0) if cache_row else 0
    return {
        "has_journey": journey is not None,
        "apps": max(journey_apps, cache_apps),
        "goals": max(journey_goals, cache_goals),
    }


def _involvement_per90(minutes: int, goals: int, assists: int) -> float:
    if minutes <= 0:
        return 0.0
    return round((goals + assists) * 90.0 / minutes, 3)


def _window_per90_involvement(club_rows) -> float:
    """Reuse the radar per-90 pure function for the window's goal involvement."""
    from src.services.radar_stats_service import compute_player_per90

    fixtures_data = [
        {"stats": {"minutes": int(r.minutes or 0), "goals": int(r.goals or 0), "assists": int(r.assists or 0)}}
        for r in club_rows
    ]
    per90 = compute_player_per90(fixtures_data)
    return round(float(per90.get("goals", 0.0)) + float(per90.get("assists", 0.0)), 3)


def _absence_count(api_client, player_api_id: int) -> int | None:
    if api_client is None:
        return None
    try:
        return len(api_client.get_player_injuries(player_api_id) or [])
    except Exception as exc:
        logger.warning("Absence lookup failed for player %s: %s", player_api_id, exc)
        return None


def _previous_pulse(player_api_id: int, window_end: date) -> PlayerPulse | None:
    return (
        PlayerPulse.query.filter(
            PlayerPulse.player_api_id == player_api_id,
            PlayerPulse.window_end < window_end,
        )
        .order_by(PlayerPulse.window_end.desc())
        .first()
    )


def _add_signal(signals: dict, name: str, *, value, weight: float, points: float, **extra) -> float:
    signals[name] = {"value": value, "weight": weight, "points": round(points, 3), **extra}
    return points


def _score_player(
    player_api_id: int,
    context: dict,
    window_end: date,
    start_dt: datetime,
    end_dt: datetime,
    start_date: date,
    window_days: int,
    api_client,
) -> tuple[float, dict]:
    """Return (score, delta_json) for one player. Deterministic given DB state
    (+ the prior pulse row for status/level/injury baselines)."""
    all_rows = _windowed_rows(player_api_id, start_dt, end_dt)
    club_api_id = context.get("current_club_api_id")
    club_rows = [r for r in all_rows if club_api_id and int(r.team_api_id or 0) == int(club_api_id)]
    window_all = _aggregate_rows(all_rows)
    window_club = _aggregate_rows(club_rows)
    before = _cumulative_before(player_api_id, start_dt)
    prev = _previous_pulse(player_api_id, window_end)
    prev_ctx = ((prev.delta_json or {}).get("context") if prev else None) or {}

    signals: dict = {}
    score = 0.0

    # --- stat deltas (current club, mirrors compute_stats' team filter) --------
    if window_club["goals"] > 0:
        score += _add_signal(
            signals,
            "goals",
            value=window_club["goals"],
            weight=PULSE_WEIGHTS["goal"],
            points=window_club["goals"] * PULSE_WEIGHTS["goal"],
        )
    if window_club["assists"] > 0:
        score += _add_signal(
            signals,
            "assists",
            value=window_club["assists"],
            weight=PULSE_WEIGHTS["assist"],
            points=window_club["assists"] * PULSE_WEIGHTS["assist"],
        )
    if window_club["appearances"] > 0:
        score += _add_signal(
            signals,
            "appearances",
            value=window_club["appearances"],
            weight=PULSE_WEIGHTS["appearance"],
            points=window_club["appearances"] * PULSE_WEIGHTS["appearance"],
        )
    if window_club["minutes"] > 0:
        score += _add_signal(
            signals,
            "minutes",
            value=window_club["minutes"],
            weight=PULSE_WEIGHTS["minutes"],
            points=window_club["minutes"] / 90.0 * PULSE_WEIGHTS["minutes"],
        )

    # --- milestones (career firsts, all teams) --------------------------------
    # "Firsts" are inferred from FixturePlayerStats, which is PARTIAL coverage
    # (top leagues only). A player whose earlier senior career lives elsewhere
    # (PlayerStatsCache lower-league rows, or PlayerJourney career entries for a
    # foreign / prior club) has _cumulative_before == 0 yet is no debutant, so a
    # raw fire would fabricate a career-first that ships to every subscriber as
    # an authorized claim. Only fire when the fuller career history POSITIVELY
    # corroborates the first (FixturePlayerStats holds the player's ENTIRE senior
    # history for that stat); absent a career record we stay silent.
    maybe_debut = before["appearances"] == 0 and window_all["appearances"] > 0
    maybe_first_goal = before["goals"] == 0 and window_all["goals"] > 0
    maybe_first_start = before["starts"] == 0 and window_all["starts"] > 0
    if maybe_debut or maybe_first_goal or maybe_first_start:
        evidence = _senior_career_evidence(player_api_id)
        fps_total_apps = before["appearances"] + window_all["appearances"]
        fps_total_goals = before["goals"] + window_all["goals"]
        apps_are_first = evidence["has_journey"] and evidence["apps"] <= fps_total_apps
        goals_are_first = evidence["has_journey"] and evidence["goals"] <= fps_total_goals
        if maybe_debut and apps_are_first:
            score += _add_signal(
                signals,
                "milestone_debut",
                value=True,
                weight=PULSE_WEIGHTS["milestone_debut"],
                points=PULSE_WEIGHTS["milestone_debut"],
                label="Senior debut",
            )
        if maybe_first_goal and goals_are_first:
            score += _add_signal(
                signals,
                "milestone_first_goal",
                value=True,
                weight=PULSE_WEIGHTS["milestone_first_goal"],
                points=PULSE_WEIGHTS["milestone_first_goal"],
                label="First senior goal",
            )
        # A first start requires full appearance coverage: if any senior
        # appearance is unknown to FixturePlayerStats it may have been a start.
        if maybe_first_start and apps_are_first:
            score += _add_signal(
                signals,
                "milestone_first_start",
                value=True,
                weight=PULSE_WEIGHTS["milestone_first_start"],
                points=PULSE_WEIGHTS["milestone_first_start"],
                label="First senior start",
            )

    # --- status change (vs prior window) --------------------------------------
    status = context.get("status")
    prev_status = prev_ctx.get("status")
    if status and prev_status and prev_status != status:
        label = _STATUS_LABELS.get(status, f"Status changed to {status}")
        score += _add_signal(
            signals,
            "status_change",
            value=status,
            weight=PULSE_WEIGHTS["status_change"],
            points=PULSE_WEIGHTS["status_change"],
            from_status=prev_status,
            to_status=status,
            label=label,
        )

    # --- level jump (vs prior window) -----------------------------------------
    level = context.get("current_level")
    prev_level = prev_ctx.get("current_level")
    cur_rank = _LEVEL_RANK.get(level or "")
    prev_rank = _LEVEL_RANK.get(prev_level or "")
    if cur_rank and prev_rank and cur_rank > prev_rank:
        score += _add_signal(
            signals,
            "milestone_level_jump",
            value=level,
            weight=PULSE_WEIGHTS["milestone_level_jump"],
            points=PULSE_WEIGHTS["milestone_level_jump"],
            from_level=prev_level,
            to_level=level,
            label=f"Stepped up from {prev_level} to {level}",
        )

    # --- per-90 spike vs own baseline -----------------------------------------
    baseline_per90 = _involvement_per90(before["minutes"], before["goals"], before["assists"])
    window_per90 = _window_per90_involvement(club_rows)
    if (
        window_club["minutes"] >= PER90_MIN_WINDOW_MINUTES
        and before["minutes"] >= PER90_MIN_BASELINE_MINUTES
        and baseline_per90 > 0
        and window_per90 >= PER90_SPIKE_RATIO * baseline_per90
    ):
        score += _add_signal(
            signals,
            "per90_spike",
            value=window_per90,
            weight=PULSE_WEIGHTS["per90_spike"],
            points=PULSE_WEIGHTS["per90_spike"],
            baseline_per90=baseline_per90,
            label="Form spike vs baseline",
        )

    # --- injury new / cleared (OPT-IN; bulk path passes api_client=None) -------
    absences = _absence_count(api_client, player_api_id)
    prev_absences = prev_ctx.get("absences")
    if absences is not None and prev_absences is not None:
        delta = absences - int(prev_absences or 0)
        if delta > 0:
            score += _add_signal(
                signals,
                "injury_new",
                value=delta,
                weight=PULSE_WEIGHTS["injury_new"],
                points=PULSE_WEIGHTS["injury_new"],
                label="New absence",
            )
        elif delta < 0:
            score += _add_signal(
                signals,
                "injury_cleared",
                value=-delta,
                weight=PULSE_WEIGHTS["injury_cleared"],
                points=PULSE_WEIGHTS["injury_cleared"],
                label="Back from absence",
            )

    context_block = {
        "name": context.get("name"),
        "position": context.get("position"),
        "parent_club": context.get("parent_club"),
        "current_club": context.get("current_club"),
        "status": status,
        "current_level": level,
        # Carried forward so the NEXT window can diff status/level/injuries.
        "absences": absences,
    }
    delta_json = {
        "window_start": start_date.isoformat(),
        "window_end": window_end.isoformat(),
        "window_days": window_days,
        "signals": signals,
        "window_totals": {
            "appearances": window_club["appearances"],
            "goals": window_club["goals"],
            "assists": window_club["assists"],
            "minutes": window_club["minutes"],
            "starts": window_club["starts"],
        },
        "context": context_block,
        "score": round(score, 2),
    }
    return round(score, 2), delta_json


def _upsert_pulse(player_api_id: int, window_end: date, score: float, delta_json: dict) -> None:
    existing = PlayerPulse.query.filter_by(player_api_id=player_api_id, window_end=window_end).first()
    if existing is not None:
        existing.score = score
        existing.delta_json = delta_json
    else:
        db.session.add(
            PlayerPulse(player_api_id=player_api_id, window_end=window_end, score=score, delta_json=delta_json)
        )


def compute_pulse(
    window_end,
    player_api_ids=None,
    *,
    api_client=None,
    window_days: int | None = None,
    dry_run: bool = False,
) -> dict:
    """Score followed players once for the window ending ``window_end``.

    ``player_api_ids=None`` scores every player followed by anyone (legacy
    watchlist + active follow lists, deduped). A passed iterable is a targeted
    recompute. Each player is scored EXACTLY ONCE (deduped) and upserted into
    ``player_pulse`` (idempotent: re-running the same window overwrites rows,
    never duplicates). ``dry_run`` computes + previews without writing.

    ``api_client`` is OPT-IN and defaults to None so the bulk path makes ZERO
    live API calls (injury signals are simply absent). Returns counts + a
    top-``10`` scored preview.
    """
    window_end = _coerce_window_end(window_end)
    window_days = int(window_days) if window_days else DEFAULT_WINDOW_DAYS
    start_dt, end_dt, start_date = _window_bounds(window_end, window_days)

    if player_api_ids is None:
        ids = _all_followed_player_ids()
    else:
        ids = {int(pid) for pid in player_api_ids}

    results: list[dict] = []
    considered = 0
    scored = 0
    upserted = 0
    for player_api_id in sorted(ids):
        context = _player_context(player_api_id)
        if context is None:
            continue
        considered += 1
        score, delta_json = _score_player(
            player_api_id, context, window_end, start_dt, end_dt, start_date, window_days, api_client
        )
        if score > 0:
            scored += 1
        if not dry_run:
            _upsert_pulse(player_api_id, window_end, score, delta_json)
            upserted += 1
        results.append(
            {
                "player_api_id": player_api_id,
                "name": context.get("name"),
                "score": score,
                "signals": sorted(delta_json["signals"].keys()),
            }
        )

    if not dry_run:
        db.session.commit()

    results.sort(key=lambda r: (-r["score"], r["player_api_id"]))
    return {
        "window_end": window_end.isoformat(),
        "window_start": start_date.isoformat(),
        "window_days": window_days,
        "dry_run": dry_run,
        "players_considered": considered,
        "scored": scored,
        "upserted": upserted,
        "top": results[:_TOP_PREVIEW],
    }
