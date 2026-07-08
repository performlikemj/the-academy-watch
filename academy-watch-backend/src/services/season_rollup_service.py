"""Season-rollup service (D3b) — the SOLE writer of the sea02 read surface.

Implements proposal §3 steady state (ledgers/research/seasons-design-proposal.md):
every hot stats surface reads ONE precomputed indexed row instead of a live
cross-source aggregation on the 0.5 CPU prod box. This module derives the two
sea02 grains — ``player_season_cells`` (fine, one row per SOURCE-contributed
cell) and ``player_season_totals`` (coarse, the hot-read row) — as a pure,
reconstructable function of the underlying sources.

Sources (feeders)
-----------------
- ``fixtures`` — :class:`FixturePlayerStats` joined to :class:`Fixture`, grouped
  per ``(season, team, competition_tier)``; rich per-match detail summed,
  ``avg_rating`` minutes-weighted; ``level_group`` always ``senior`` (FPS is
  senior per-match data).
- ``journey``  — :class:`PlayerJourneyEntry` read by the denormalized
  ``player_api_id`` (ix_pje_player_season), grouped per ``(season, club,
  competition_tier)``; ``level_group`` from ``is_international`` / ``is_youth``
  exactly as the D1 provenance code partitions senior/youth/international; rich
  detail lifted from the sea01 columns when ``stats_source == 'journey-api'``.
- ``apss``     — :class:`AcademyPlayerSeasonStats` → ``level_group='youth'``.
- ``shadow``   — :class:`PlayerShadowStats` → ``source='shadow'``.

Totals resolution (the double-count guard — proposal §2, non-negotiable)
-----------------------------------------------------------------------
Per ``(player, season, level_group)`` totals NEVER sum across sources. Each
source's own total is computed independently; the HEADLINE is the larger-minutes
source taken WHOLE (``journey`` wins ties / ``>=`` — the cup-inclusive
convention; ``fixtures`` wins only when strictly larger →
``journey-under-sync``). ``fixtures_minutes`` and ``journey_minutes`` are always
both stored; ``reconcile_flag`` follows the coverage-map buckets; ``avg_rating``
is ALWAYS fixtures-sourced (NULL when there are no fixtures).

Transactionality
----------------
:func:`refresh_player` does DELETE+re-INSERT of a player's cells (scoped to a
season when given) and re-resolves totals, all on the caller's session and
WITHOUT committing — it participates in whatever transaction the caller owns:

- journey sync calls it before its own commit (same transaction, so a club-ID
  correction can never orphan cells);
- the FPS choke point drains a per-session dirty set AFTER the batch commit via
  :func:`flush_player_refresh_queue`, which owns its own single commit so a
  refresh bug can never roll back the expensive fixture writes.

Noise filter: feeders skip any source row with 0 apps AND 0 minutes AND 0 goals
(kills the ~740 pre-season PJE stubs and near-empty APSS rows).
"""

import logging
from datetime import UTC, datetime

from src.models.follow import PlayerShadowStats
from src.models.journey import PlayerJourneyEntry
from src.models.league import AcademyPlayerSeasonStats, db
from src.models.season_rollup import PlayerSeasonCell, PlayerSeasonTotal
from src.models.weekly import Fixture, FixturePlayerStats

logger = logging.getLogger(__name__)

# ---- source / level / tier vocabularies (mirror sea02 column comments) -------
SOURCE_FIXTURES = "fixtures"
SOURCE_JOURNEY = "journey"
SOURCE_APSS = "apss"
SOURCE_SHADOW = "shadow"

LEVEL_SENIOR = "senior"
LEVEL_YOUTH = "youth"
LEVEL_INTERNATIONAL = "international"

TIER_LEAGUE = "league"
TIER_DOMESTIC_CUP = "domestic_cup"
TIER_LEAGUE_CUP = "league_cup"
TIER_CONTINENTAL = "continental"
TIER_OTHER = "other"
TIER_YOUTH = "youth"

# Headline tie-break priority: on EQUAL minutes the higher-priority source wins
# the headline. journey beats fixtures (cup-inclusive convention, proposal §2);
# the supplementary sources only win when strictly larger in minutes.
_SOURCE_PRIORITY = {SOURCE_JOURNEY: 4, SOURCE_FIXTURES: 3, SOURCE_APSS: 2, SOURCE_SHADOW: 1}

# Per-session dirty set (player_api_id, season) awaiting a post-commit refresh.
_DIRTY_KEY = "_season_rollup_dirty"

# The eight aggregatable stat keys shared by cells and totals.
_STAT_KEYS = ("appearances", "goals", "assists", "minutes", "yellows", "reds", "saves", "goals_conceded")


# ---------------------------------------------------------------------------
# Competition-tier classification (documented NAME heuristic)
# ---------------------------------------------------------------------------
def classify_competition_tier(name: str | None) -> str:
    """Best-effort ``league|cup|continental`` tier from a competition NAME.

    Fixtures carry only ``competition_name`` and journey entries only
    ``league_name`` — neither source exposes a structural cup/league flag — so
    this is a deliberate name heuristic (proposal §2/§3: "if league metadata
    cannot classify cups vs league reliably, use tier 'league' vs 'other' and
    document"). Anything not clearly a cup falls back to ``league``; the
    ambiguous domestic-vs-league-cup split is never guessed beyond the keyword
    lists below. This only enriches per-cell display — totals fold every tier
    WITHIN a source, so a misclassification never changes a headline number.
    """
    if not name:
        return TIER_LEAGUE
    n = name.lower()
    # League (secondary knockout) cups — checked first because their names also
    # contain the generic "cup"/"coupe" tokens the domestic branch matches.
    if any(kw in n for kw in ("efl cup", "carabao", "league cup", "coupe de la ligue", "efl trophy")):
        return TIER_LEAGUE_CUP
    # Continental / cross-border club competitions.
    if any(
        kw in n
        for kw in (
            "champions league",
            "europa",
            "conference league",
            "uefa",
            "libertadores",
            "sudamericana",
            "concacaf",
            "afc champions",
            "club world cup",
            "super cup",
            "supercopa",
            "supercup",
        )
    ):
        return TIER_CONTINENTAL
    # Domestic cups (generic tokens across the big-5 + common locales).
    if any(
        kw in n for kw in ("cup", "copa", "coupe", "coppa", "pokal", "taça", "taca", "beker", "trophy", "dfb", "shield")
    ):
        return TIER_DOMESTIC_CUP
    return TIER_LEAGUE


# ---------------------------------------------------------------------------
# Small aggregation helpers
# ---------------------------------------------------------------------------
def _is_noise(agg: dict) -> bool:
    """A source row/cell with 0 apps AND 0 minutes AND 0 goals is noise."""
    return not (agg.get("appearances") or agg.get("minutes") or agg.get("goals"))


def _sum_opt(values) -> int | None:
    """Sum treating None as absent: return None if every contributor was None,
    else the sum of the non-None ints (so keeper stats stay NULL for outfielders
    rather than reading a misleading observed-zero)."""
    seen = False
    total = 0
    for v in values:
        if v is not None:
            seen = True
            total += v
    return total if seen else None


def _blank_agg() -> dict:
    agg = {k: None for k in _STAT_KEYS}
    agg["_detail"] = {}
    agg["_rating_wsum"] = 0.0
    agg["_rating_min"] = 0
    return agg


def _add(agg: dict, key: str, value):
    if value is None:
        return
    agg[key] = (agg[key] or 0) + value


def _add_detail(agg: dict, mapping: dict):
    detail = agg["_detail"]
    for out_key, value in mapping.items():
        if value is None:
            continue
        detail[out_key] = (detail.get(out_key) or 0) + value


def _add_rating(agg: dict, rating, minutes):
    if rating is None or not minutes or minutes <= 0:
        return
    agg["_rating_wsum"] += float(rating) * minutes
    agg["_rating_min"] += minutes


def _finish_cell(
    agg: dict,
    *,
    player_api_id: int,
    season: int,
    source: str,
    club_api_id: int,
    club_name: str | None,
    competition_tier: str,
    level_group: str,
    now: datetime,
) -> dict | None:
    """Turn an accumulated group into a cell payload (noise-filtered)."""
    if _is_noise(agg):
        return None
    avg_rating = round(agg["_rating_wsum"] / agg["_rating_min"], 2) if agg["_rating_min"] else None
    detail = agg["_detail"] or None
    return {
        "player_api_id": player_api_id,
        "season": season,
        "source": source,
        "club_api_id": club_api_id,
        "club_name": club_name,
        "competition_tier": competition_tier,
        "level_group": level_group,
        **{k: agg[k] for k in _STAT_KEYS},
        "avg_rating": avg_rating,
        "detail": detail,
        "synced_at": now,
        # internal fields (dropped before ORM build; used for totals avg_rating)
        "_rating_wsum": agg["_rating_wsum"],
        "_rating_min": agg["_rating_min"],
    }


# ---------------------------------------------------------------------------
# Feeders — each returns a list of cell payload dicts for the player[, season]
# ---------------------------------------------------------------------------
def _fixture_cells(player_api_id: int, season: int | None, session, now: datetime) -> list[dict]:
    """Aggregate FixturePlayerStats (joined to fixtures) per (season, team, tier)."""
    q = (
        session.query(FixturePlayerStats, Fixture.season, Fixture.competition_name)
        .join(Fixture, FixturePlayerStats.fixture_id == Fixture.id)
        .filter(FixturePlayerStats.player_api_id == player_api_id)
    )
    if season is not None:
        q = q.filter(Fixture.season == season)

    groups: dict[tuple, dict] = {}
    for fps, fx_season, comp_name in q.all():
        tier = classify_competition_tier(comp_name)
        key = (fx_season, fps.team_api_id, tier)
        agg = groups.get(key)
        if agg is None:
            agg = _blank_agg()
            groups[key] = agg
        minutes = fps.minutes or 0
        if minutes > 0:
            _add(agg, "appearances", 1)
        _add(agg, "goals", fps.goals or 0)
        _add(agg, "assists", fps.assists or 0)
        _add(agg, "minutes", minutes)
        _add(agg, "yellows", fps.yellows or 0)
        _add(agg, "reds", fps.reds or 0)
        _add(agg, "saves", fps.saves)
        _add(agg, "goals_conceded", fps.goals_conceded)
        _add_rating(agg, fps.rating, minutes)
        _add_detail(
            agg,
            {
                "shots_total": fps.shots_total,
                "shots_on": fps.shots_on,
                "passes_total": fps.passes_total,
                "passes_key": fps.passes_key,
                "tackles_total": fps.tackles_total,
                "tackles_blocks": fps.tackles_blocks,
                "tackles_interceptions": fps.tackles_interceptions,
                "duels_total": fps.duels_total,
                "duels_won": fps.duels_won,
                "dribbles_attempts": fps.dribbles_attempts,
                "dribbles_success": fps.dribbles_success,
                "fouls_drawn": fps.fouls_drawn,
                "fouls_committed": fps.fouls_committed,
                "penalty_scored": fps.penalty_scored,
                "penalty_missed": fps.penalty_missed,
                "penalty_saved": fps.penalty_saved,
            },
        )

    cells = []
    for (fx_season, team_api_id, tier), agg in groups.items():
        cell = _finish_cell(
            agg,
            player_api_id=player_api_id,
            season=fx_season,
            source=SOURCE_FIXTURES,
            club_api_id=team_api_id or 0,
            club_name=None,
            competition_tier=tier,
            level_group=LEVEL_SENIOR,
            now=now,
        )
        if cell:
            cells.append(cell)
    return cells


def _journey_level_and_tier(entry: PlayerJourneyEntry) -> tuple[str, str]:
    """Mirror the D1 provenance senior/youth/international partition.

    D1 (routes/players.py::_season_provenance) treats a journey entry as SENIOR
    only when ``not is_youth and not is_international``; the youth-window logic
    keys on ``is_youth and not is_international``. So international wins over
    youth (international-youth caps read as international). The tier map keeps
    ``(club, tier)`` a 1:1 proxy for level_group, which the cell unique key
    requires (senior never maps to 'other'; 'other' therefore == international).
    """
    if entry.is_international:
        return LEVEL_INTERNATIONAL, TIER_OTHER
    if entry.is_youth:
        return LEVEL_YOUTH, TIER_YOUTH
    return LEVEL_SENIOR, classify_competition_tier(entry.league_name)


def _journey_cells(player_api_id: int, season: int | None, session, now: datetime) -> list[dict]:
    """Aggregate PlayerJourneyEntry per (season, club, tier) via ix_pje_player_season."""
    q = session.query(PlayerJourneyEntry).filter(PlayerJourneyEntry.player_api_id == player_api_id)
    if season is not None:
        q = q.filter(PlayerJourneyEntry.season == season)

    groups: dict[tuple, dict] = {}
    names: dict[tuple, str | None] = {}
    for e in q.all():
        level_group, tier = _journey_level_and_tier(e)
        key = (e.season, e.club_api_id, tier)
        agg = groups.get(key)
        if agg is None:
            agg = _blank_agg()
            agg["_level"] = level_group
            groups[key] = agg
            names[key] = e.club_name
        minutes = e.minutes or 0
        _add(agg, "appearances", e.appearances or 0)
        _add(agg, "goals", e.goals or 0)
        _add(agg, "assists", e.assists or 0)
        _add(agg, "minutes", minutes)
        # Rich fields only exist on journey-api rows; legacy-basic rows leave them NULL.
        if e.stats_source == "journey-api":
            _add(agg, "yellows", e.cards_yellow)
            _add(agg, "reds", e.cards_red)
            _add(agg, "saves", e.saves)
            _add(agg, "goals_conceded", e.goals_conceded)
            _add_rating(agg, e.rating, minutes)
            _add_detail(
                agg,
                {
                    "shots_total": e.shots_total,
                    "shots_on": e.shots_on,
                    "passes_total": e.passes_total,
                    "passes_key": e.passes_key,
                    "tackles_total": e.tackles_total,
                    "tackles_blocks": e.tackles_blocks,
                    "tackles_interceptions": e.tackles_interceptions,
                    "duels_total": e.duels_total,
                    "duels_won": e.duels_won,
                    "dribbles_attempts": e.dribbles_attempts,
                    "dribbles_success": e.dribbles_success,
                    "fouls_drawn": e.fouls_drawn,
                    "fouls_committed": e.fouls_committed,
                    "penalty_scored": e.penalty_scored,
                    "penalty_missed": e.penalty_missed,
                    "penalty_saved": e.penalty_saved,
                },
            )

    cells = []
    for key, agg in groups.items():
        fx_season, club_api_id, tier = key
        cell = _finish_cell(
            agg,
            player_api_id=player_api_id,
            season=fx_season,
            source=SOURCE_JOURNEY,
            club_api_id=club_api_id or 0,
            club_name=names.get(key),
            competition_tier=tier,
            level_group=agg["_level"],
            now=now,
        )
        if cell:
            cells.append(cell)
    return cells


def _apss_cells(player_api_id: int, season: int | None, session, now: datetime) -> list[dict]:
    """Aggregate AcademyPlayerSeasonStats per (season, team) → level_group youth."""
    q = session.query(AcademyPlayerSeasonStats).filter(AcademyPlayerSeasonStats.player_api_id == player_api_id)
    if season is not None:
        q = q.filter(AcademyPlayerSeasonStats.season == season)

    groups: dict[tuple, dict] = {}
    names: dict[tuple, str | None] = {}
    for r in q.all():
        key = (r.season, r.team_api_id or 0)
        agg = groups.get(key)
        if agg is None:
            agg = _blank_agg()
            groups[key] = agg
            names[key] = r.team_name
        minutes = r.minutes or 0
        _add(agg, "appearances", r.appearances or 0)
        _add(agg, "goals", r.goals or 0)
        _add(agg, "assists", r.assists or 0)
        _add(agg, "minutes", minutes)
        _add(agg, "yellows", r.yellow_cards)
        _add(agg, "reds", r.red_cards)
        _add_rating(agg, r.rating, minutes)
        _add_detail(
            agg,
            {
                "shots_total": r.shots_total,
                "shots_on": r.shots_on,
                "passes_total": r.passes_total,
                "passes_key": r.passes_key,
                "tackles_total": r.tackles_total,
                "tackles_interceptions": r.interceptions,
                "duels_total": r.duels_total,
                "duels_won": r.duels_won,
                "dribbles_attempts": r.dribbles_attempts,
                "dribbles_success": r.dribbles_success,
                "fouls_drawn": r.fouls_drawn,
                "fouls_committed": r.fouls_committed,
                "penalty_scored": r.penalty_scored,
                "penalty_missed": r.penalty_missed,
            },
        )

    cells = []
    for key, agg in groups.items():
        fx_season, team_api_id = key
        cell = _finish_cell(
            agg,
            player_api_id=player_api_id,
            season=fx_season,
            source=SOURCE_APSS,
            club_api_id=team_api_id,
            club_name=names.get(key),
            competition_tier=TIER_YOUTH,
            level_group=LEVEL_YOUTH,
            now=now,
        )
        if cell:
            cells.append(cell)
    return cells


def _shadow_cells(player_api_id: int, season: int | None, session, now: datetime) -> list[dict]:
    """Aggregate PlayerShadowStats per (season, team) → source shadow, senior.

    Shadow rows carry no competition metadata, so the tier is documented as the
    plain ``league`` default (proposal §2 honest-fallback rule)."""
    q = session.query(PlayerShadowStats).filter(PlayerShadowStats.player_api_id == player_api_id)
    if season is not None:
        q = q.filter(PlayerShadowStats.season == season)

    groups: dict[tuple, dict] = {}
    names: dict[tuple, str | None] = {}
    for r in q.all():
        key = (r.season, r.team_api_id or 0)
        agg = groups.get(key)
        if agg is None:
            agg = _blank_agg()
            groups[key] = agg
            names[key] = r.team_name
        _add(agg, "appearances", r.appearances or 0)
        _add(agg, "goals", r.goals or 0)
        _add(agg, "assists", r.assists or 0)
        _add(agg, "minutes", r.minutes or 0)

    cells = []
    for key, agg in groups.items():
        fx_season, team_api_id = key
        cell = _finish_cell(
            agg,
            player_api_id=player_api_id,
            season=fx_season,
            source=SOURCE_SHADOW,
            club_api_id=team_api_id,
            club_name=names.get(key),
            competition_tier=TIER_LEAGUE,
            level_group=LEVEL_SENIOR,
            now=now,
        )
        if cell:
            cells.append(cell)
    return cells


_FEEDERS = (_fixture_cells, _journey_cells, _apss_cells, _shadow_cells)


# ---------------------------------------------------------------------------
# Totals resolution — never-cross-source-sum (proposal §2)
# ---------------------------------------------------------------------------
def _source_subtotal(cells: list[dict]) -> dict:
    """Sum a single source's cells (WITHIN-source aggregation is allowed)."""
    sub = {k: _sum_opt([c[k] for c in cells]) for k in _STAT_KEYS}
    sub["_rating_wsum"] = sum(c["_rating_wsum"] for c in cells)
    sub["_rating_min"] = sum(c["_rating_min"] for c in cells)
    return sub


def _reconcile_flag(fixtures_minutes: int, journey_minutes: int) -> str | None:
    """The fixtures-vs-journey provenance axis (identical to D1 _season_provenance)."""
    if fixtures_minutes == 0 and journey_minutes > 0:
        return "fixtures-invisible"
    if journey_minutes > fixtures_minutes > 0:
        return "cup-gap"
    if fixtures_minutes > journey_minutes:
        return "journey-under-sync"
    return None


def _resolve_totals(cells: list[dict], now: datetime) -> list[dict]:
    """Build one totals payload per (season, level_group) from the cells."""
    # group cells by (season, level_group) then by source
    grouped: dict[tuple, dict[str, list[dict]]] = {}
    for c in cells:
        gkey = (c["season"], c["level_group"])
        grouped.setdefault(gkey, {}).setdefault(c["source"], []).append(c)

    totals = []
    for (season, level_group), by_source in grouped.items():
        subtotals = {src: _source_subtotal(src_cells) for src, src_cells in by_source.items()}

        fixtures_minutes = (subtotals.get(SOURCE_FIXTURES) or {}).get("minutes") or 0
        journey_minutes = (subtotals.get(SOURCE_JOURNEY) or {}).get("minutes") or 0

        # Headline = larger-minutes source taken whole; tie → higher priority
        # (journey > fixtures > apss > shadow). NEVER a cross-source sum.
        headline_src = max(
            subtotals.keys(),
            key=lambda s: ((subtotals[s].get("minutes") or 0), _SOURCE_PRIORITY.get(s, 0)),
        )
        headline = subtotals[headline_src]

        # avg_rating is ALWAYS fixtures-sourced (NULL when no fixtures).
        fx_sub = subtotals.get(SOURCE_FIXTURES)
        avg_rating = None
        if fx_sub and fx_sub["_rating_min"]:
            avg_rating = round(fx_sub["_rating_wsum"] / fx_sub["_rating_min"], 2)

        source_breakdown = {src: {k: sub[k] for k in _STAT_KEYS} for src, sub in subtotals.items()}
        clubs = _clubs_array(by_source[headline_src])

        totals.append(
            {
                "player_api_id": cells and cells[0]["player_api_id"],
                "season": season,
                "level_group": level_group,
                **{k: headline[k] for k in _STAT_KEYS},
                "avg_rating": avg_rating,
                "primary_source": headline_src,
                "fixtures_minutes": fixtures_minutes,
                "journey_minutes": journey_minutes,
                "reconcile_flag": _reconcile_flag(fixtures_minutes, journey_minutes),
                "source_breakdown": source_breakdown,
                "clubs": clubs,
                "computed_at": now,
            }
        )
    return totals


def _clubs_array(headline_cells: list[dict]) -> list[dict]:
    """Compact per-club render array for the headline source's cells."""
    by_club: dict[int, dict] = {}
    for c in headline_cells:
        club = by_club.get(c["club_api_id"])
        if club is None:
            club = {
                "id": c["club_api_id"],
                "name": c["club_name"],
                "minutes": 0,
                "appearances": 0,
                "goals": 0,
                "assists": 0,
                "competition_tiers": [],
            }
            by_club[c["club_api_id"]] = club
        club["minutes"] += c["minutes"] or 0
        club["appearances"] += c["appearances"] or 0
        club["goals"] += c["goals"] or 0
        club["assists"] += c["assists"] or 0
        if c["competition_tier"] not in club["competition_tiers"]:
            club["competition_tiers"].append(c["competition_tier"])
    return sorted(by_club.values(), key=lambda x: (-(x["minutes"] or 0), x["id"]))


# ---------------------------------------------------------------------------
# Public write API
# ---------------------------------------------------------------------------
def _delete_scope(session, model, player_api_id: int, season: int | None):
    q = session.query(model).filter(model.player_api_id == player_api_id)
    if season is not None:
        q = q.filter(model.season == season)
    q.delete(synchronize_session=False)


def refresh_player(player_api_id: int, season: int | None = None, session=None) -> dict:
    """Rebuild a player's rollup cells + totals from the sources, in ONE transaction.

    Participates in the caller's session/transaction and does NOT commit — the
    caller (journey sync, or :func:`flush_player_refresh_queue`) owns the commit.

    DELETEs the player's existing cells and totals (scoped to ``season`` when
    given), re-INSERTs cells from every feeder, then re-resolves totals from
    those fresh cells. Idempotent: re-running yields exactly the same rows.
    """
    session = session or db.session
    now = datetime.now(UTC)

    # 1) Clear the slate (scoped). Bulk DELETE executes immediately, so the
    #    subsequent INSERTs cannot collide with stale rows on the unique keys.
    _delete_scope(session, PlayerSeasonCell, player_api_id, season)
    _delete_scope(session, PlayerSeasonTotal, player_api_id, season)
    session.flush()

    # 2) Rebuild cells from every source.
    cells: list[dict] = []
    for feeder in _FEEDERS:
        cells.extend(feeder(player_api_id, season, session, now))

    for c in cells:
        session.add(
            PlayerSeasonCell(
                player_api_id=c["player_api_id"],
                season=c["season"],
                source=c["source"],
                club_api_id=c["club_api_id"],
                club_name=c["club_name"],
                competition_tier=c["competition_tier"],
                level_group=c["level_group"],
                appearances=c["appearances"],
                goals=c["goals"],
                assists=c["assists"],
                minutes=c["minutes"],
                yellows=c["yellows"],
                reds=c["reds"],
                saves=c["saves"],
                goals_conceded=c["goals_conceded"],
                avg_rating=c["avg_rating"],
                detail=c["detail"],
                synced_at=c["synced_at"],
            )
        )

    # 3) Re-resolve totals (never cross-source sum).
    totals = _resolve_totals(cells, now)
    for t in totals:
        session.add(
            PlayerSeasonTotal(
                player_api_id=t["player_api_id"],
                season=t["season"],
                level_group=t["level_group"],
                appearances=t["appearances"],
                goals=t["goals"],
                assists=t["assists"],
                minutes=t["minutes"],
                yellows=t["yellows"],
                reds=t["reds"],
                saves=t["saves"],
                goals_conceded=t["goals_conceded"],
                avg_rating=t["avg_rating"],
                primary_source=t["primary_source"],
                fixtures_minutes=t["fixtures_minutes"],
                journey_minutes=t["journey_minutes"],
                reconcile_flag=t["reconcile_flag"],
                source_breakdown=t["source_breakdown"],
                clubs=t["clubs"],
                computed_at=t["computed_at"],
            )
        )

    session.flush()
    return {"cells": len(cells), "totals": len(totals)}


# ---------------------------------------------------------------------------
# FPS choke point — one enqueue function + one post-commit drain
# ---------------------------------------------------------------------------
def queue_player_refresh(player_api_id, season, session=None) -> None:
    """Mark a ``(player, season)`` rollup dirty — the ONE function every
    FixturePlayerStats writer routes through.

    Pure in-memory set insert on the session (no DB work, no mid-transaction
    refresh), so a batch writing 30 players enqueues at most 30 distinct pairs
    and a single :func:`flush_player_refresh_queue` after the batch commit
    refreshes each affected player exactly once.
    """
    if player_api_id is None or season is None:
        return
    session = session or db.session
    try:
        session.info.setdefault(_DIRTY_KEY, set()).add((int(player_api_id), int(season)))
    except (TypeError, ValueError):
        return


def flush_player_refresh_queue(session=None) -> int:
    """Drain the dirty set and refresh each ``(player, season)`` once.

    Called AFTER a batch's own commit so a refresh failure can never roll back
    the expensive fixture writes. Each pair runs inside a SAVEPOINT so one bad
    player cannot poison the rest; the whole drain lands in a SINGLE commit.
    Returns the number of pairs refreshed.
    """
    session = session or db.session
    dirty = session.info.get(_DIRTY_KEY)
    if not dirty:
        return 0

    pairs = sorted(dirty)
    dirty.clear()

    refreshed = 0
    for player_api_id, season in pairs:
        try:
            with session.begin_nested():
                refresh_player(player_api_id, season=season, session=session)
            refreshed += 1
        except Exception:
            logger.exception("season-rollup refresh failed for player=%s season=%s", player_api_id, season)

    session.commit()
    return refreshed
