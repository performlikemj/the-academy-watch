"""Dynamic youth competition resolution helpers.

Resolves current API-Football youth league IDs and parent->youth team IDs
with static fallback defaults when live lookup fails.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.utils.academy_classifier import strip_youth_suffix

logger = logging.getLogger(__name__)


# Current known-good fallback IDs (validated against API-Football catalog).
DEFAULT_YOUTH_LEAGUES = [
    {
        "key": "pl2_div1",
        "name": "Premier League 2 Division One",
        "search": "Premier League 2",
        "country": "England",
        "type": "League",
        "level": "U23",
        "fallback_id": 702,
        "match_tokens": ("premier", "league", "2"),
    },
    {
        "key": "u18_north",
        "name": "U18 Premier League - North",
        "search": "U18 Premier League - North",
        "country": "England",
        "type": "League",
        "level": "U18",
        "fallback_id": 695,
        "match_tokens": ("u18", "north"),
    },
    {
        "key": "u18_south",
        "name": "U18 Premier League - South",
        "search": "U18 Premier League - South",
        "country": "England",
        "type": "League",
        "level": "U18",
        "fallback_id": 696,
        "match_tokens": ("u18", "south"),
    },
    {
        "key": "u18_championship",
        "name": "U18 Premier League - Championship",
        "search": "U18 Premier League - Championship",
        "country": "England",
        "type": "League",
        "level": "U18",
        "fallback_id": 987,
        "match_tokens": ("u18", "championship"),
    },
    {
        "key": "fa_youth_cup",
        "name": "FA Youth Cup",
        "search": "FA Youth Cup",
        "country": "England",
        "type": "Cup",
        "level": "U18",
        "fallback_id": 1068,
        "match_tokens": ("fa", "youth", "cup"),
    },
    {
        "key": "uefa_youth_league",
        "name": "UEFA Youth League",
        "search": "UEFA Youth League",
        "country": "World",
        "type": "League",
        "level": "U19",
        "fallback_id": 14,
        "match_tokens": ("uefa", "youth", "league"),
    },
]

# UEFA Youth League entry shared across all countries.
_UEFA_YOUTH_LEAGUE = DEFAULT_YOUTH_LEAGUES[-1]  # uefa_youth_league

ITALY_YOUTH_LEAGUES = [
    {
        "key": "primavera_1",
        "name": "Campionato Primavera - 1",
        "search": "Campionato Primavera - 1",
        "country": "Italy",
        "type": "League",
        "level": "U20",
        "fallback_id": 705,
        "match_tokens": ("campionato", "primavera", "1"),
    },
    {
        "key": "primavera_2",
        "name": "Campionato Primavera - 2",
        "search": "Campionato Primavera - 2",
        "country": "Italy",
        "type": "League",
        "level": "U20",
        "fallback_id": 706,
        "match_tokens": ("campionato", "primavera", "2"),
    },
    {
        "key": "coppa_italia_primavera",
        "name": "Coppa Italia Primavera",
        "search": "Coppa Italia Primavera",
        "country": "Italy",
        "type": "Cup",
        "level": "U20",
        "fallback_id": 704,
        "match_tokens": ("coppa", "italia", "primavera"),
    },
    _UEFA_YOUTH_LEAGUE,
]

GERMANY_YOUTH_LEAGUES = [
    {
        "key": "u19_bundesliga",
        "name": "U19 Bundesliga",
        "search": "U19 Bundesliga",
        "country": "Germany",
        "type": "League",
        "level": "U19",
        "fallback_id": 488,
        "match_tokens": ("u19", "bundesliga"),
    },
    {
        "key": "dfb_junioren_pokal",
        "name": "DFB Junioren Pokal",
        "search": "DFB Junioren Pokal",
        "country": "Germany",
        "type": "Cup",
        "level": "U19",
        "fallback_id": 715,
        "match_tokens": ("dfb", "junioren", "pokal"),
    },
    _UEFA_YOUTH_LEAGUE,
]

# Spain and France have no youth competitions in API-Football;
# only UEFA Youth League is available for clubs in those countries.
UEFA_ONLY_YOUTH_LEAGUES = [_UEFA_YOUTH_LEAGUE]

# Country -> youth league definitions. Used by the seeding pipeline to
# resolve the right youth competitions per parent team's country.
YOUTH_LEAGUES_BY_COUNTRY = {
    "England": DEFAULT_YOUTH_LEAGUES,
    "Italy": ITALY_YOUTH_LEAGUES,
    "Germany": GERMANY_YOUTH_LEAGUES,
    "Spain": UEFA_ONLY_YOUTH_LEAGUES,
    "France": UEFA_ONLY_YOUTH_LEAGUES,
}


def _norm(text: str | None) -> str:
    value = (text or "").lower().strip()
    value = value.replace("hotspur", "")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _league_score(row: dict[str, Any], target: dict[str, Any]) -> int:
    league = row.get("league", {}) or {}
    country = row.get("country", {}) or {}

    row_name = _norm(league.get("name"))
    target_name = _norm(target.get("name"))
    target_search = _norm(target.get("search"))
    row_country = _norm(country.get("name"))
    target_country = _norm(target.get("country"))
    row_type = _norm(league.get("type"))
    target_type = _norm(target.get("type"))

    score = 0
    if row_name == target_name:
        score += 100
    if target_search and target_search in row_name:
        score += 35
    if target_name and target_name in row_name:
        score += 25
    if target_country and row_country == target_country:
        score += 20
    if target_type and row_type == target_type:
        score += 10

    tokens = target.get("match_tokens", ())
    if tokens:
        hits = sum(1 for t in tokens if _norm(t) in row_name)
        score += hits * 8

    return score


def _pick_best_league_match(rows: list[dict[str, Any]], target: dict[str, Any]) -> dict[str, Any] | None:
    if not rows:
        return None
    scored = sorted(
        ((row, _league_score(row, target)) for row in rows),
        key=lambda item: item[1],
        reverse=True,
    )
    best_row, best_score = scored[0]
    if best_score <= 0:
        return None
    return best_row


def get_default_youth_league_map() -> dict[int, str]:
    """Fallback mapping of league_id -> display name."""
    return {entry["fallback_id"]: entry["name"] for entry in DEFAULT_YOUTH_LEAGUES}


def resolve_youth_leagues(api_client=None, explicit_league_ids: list[int] | None = None,
                          country: str | None = None) -> list[dict[str, Any]]:
    """Resolve youth leagues dynamically with static fallback defaults.

    Args:
        api_client: Optional API client for dynamic resolution.
        explicit_league_ids: Override with specific league IDs.
        country: Country name to select the right youth league set
                 (e.g. 'England', 'Italy', 'Germany'). Defaults to England.

    Returns list of dicts with keys:
      key, league_id, name, country, type, level, source, fallback_id
    """
    # Select the target youth league definitions for this country.
    target_leagues = YOUTH_LEAGUES_BY_COUNTRY.get(country or "England", DEFAULT_YOUTH_LEAGUES)

    if explicit_league_ids:
        # Build lookup across ALL known youth leagues for metadata.
        all_youth = []
        for yl_list in YOUTH_LEAGUES_BY_COUNTRY.values():
            all_youth.extend(yl_list)
        fallback_by_id = {e["fallback_id"]: e for e in all_youth}
        resolved = []
        for league_id in explicit_league_ids:
            meta = fallback_by_id.get(int(league_id), {})
            resolved.append(
                {
                    "key": meta.get("key", f"league_{league_id}"),
                    "league_id": int(league_id),
                    "name": meta.get("name", f"League {league_id}"),
                    "country": meta.get("country"),
                    "type": meta.get("type"),
                    "level": meta.get("level"),
                    "source": "explicit",
                    "fallback_id": meta.get("fallback_id", int(league_id)),
                }
            )
        return resolved

    resolved: list[dict[str, Any]] = []
    for target in target_leagues:
        fallback_entry = {
            "key": target["key"],
            "league_id": int(target["fallback_id"]),
            "name": target["name"],
            "country": target["country"],
            "type": target["type"],
            "level": target["level"],
            "source": "static_fallback",
            "fallback_id": int(target["fallback_id"]),
        }

        if api_client is None:
            resolved.append(fallback_entry)
            continue

        try:
            response = api_client._make_request("leagues", {"search": target["search"]})
            rows = response.get("response", []) if isinstance(response, dict) else []
            best = _pick_best_league_match(rows, target)
            if best:
                league = best.get("league", {}) or {}
                country = best.get("country", {}) or {}
                resolved.append(
                    {
                        "key": target["key"],
                        "league_id": int(league.get("id")),
                        "name": league.get("name") or target["name"],
                        "country": country.get("name") or target["country"],
                        "type": league.get("type") or target["type"],
                        "level": target["level"],
                        "source": "dynamic",
                        "fallback_id": int(target["fallback_id"]),
                    }
                )
                continue
        except Exception as exc:
            logger.warning("Youth league resolution failed for '%s': %s", target["name"], exc)

        resolved.append(fallback_entry)

    # De-duplicate by resolved league_id while preserving order.
    seen = set()
    deduped = []
    for item in resolved:
        lid = item["league_id"]
        if lid in seen:
            continue
        seen.add(lid)
        deduped.append(item)
    return deduped


def build_academy_league_seed_rows(api_client=None, season: int | None = None) -> list[dict[str, Any]]:
    """Build rows for AcademyLeague seed/update from dynamic resolution."""
    rows = []
    for league in resolve_youth_leagues(api_client=api_client):
        rows.append(
            {
                "api_league_id": league["league_id"],
                "name": league["name"],
                "country": league.get("country") or "Unknown",
                "level": league.get("level") or "Unknown",
                "season": season,
            }
        )
    return rows


def resolve_team_name(api_client, team_api_id: int, fallback_name: str | None = None) -> str:
    """Resolve parent team display name, with fallback to provided name or ID."""
    if fallback_name:
        return fallback_name
    try:
        data = api_client.get_team_by_id(int(team_api_id))
        team_obj = data.get("team", {}) if isinstance(data, dict) else {}
        name = team_obj.get("name")
        if name:
            return name
    except Exception:
        pass
    return str(team_api_id)


def resolve_youth_team_for_parent(
    api_client,
    league_id: int,
    season: int,
    parent_team_name: str,
    teams_cache: dict[tuple[int, int], list[dict[str, Any]]],
) -> tuple[int | None, str | None]:
    """Resolve youth team ID in a league/season for a parent club name."""
    cache_key = (int(league_id), int(season))
    rows = teams_cache.get(cache_key)
    if rows is None:
        rows = api_client.get_league_teams(int(league_id), int(season)) or []
        teams_cache[cache_key] = rows

    parent_norm = _norm(strip_youth_suffix(parent_team_name or ""))
    if not parent_norm:
        return None, None

    candidates: list[tuple[int, int, str]] = []
    for row in rows:
        team = row.get("team", {}) or {}
        team_id = team.get("id")
        team_name = team.get("name") or ""
        if not team_id:
            continue

        base_name = strip_youth_suffix(team_name)
        base_norm = _norm(base_name)
        full_norm = _norm(team_name)

        score = 0
        if base_norm == parent_norm:
            score += 100
        elif parent_norm and parent_norm in full_norm:
            score += 40
        elif full_norm and full_norm in parent_norm:
            score += 20

        # Prefer explicit youth variants where names are tied.
        if re.search(r"\b(u\d{2}|youth|reserve|development)\b", team_name.lower()):
            score += 10

        if score > 0:
            candidates.append((score, int(team_id), team_name))

    if not candidates:
        return None, None

    candidates.sort(key=lambda item: item[0], reverse=True)
    _, best_id, best_name = candidates[0]
    return best_id, best_name
