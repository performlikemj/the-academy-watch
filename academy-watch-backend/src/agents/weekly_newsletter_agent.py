import os
import json
import re
import uuid
import requests
from urllib.parse import urlparse, urlunparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta, datetime, timezone
from typing import Any, Dict, List, Annotated, Optional
from pydantic import BaseModel, Field
from agents import (
    set_default_openai_client
)
from openai import OpenAI  # OpenAI Agents SDK
try:  # Optional Groq dependency for newsletter summaries
    from groq import Groq
except ImportError:  # pragma: no cover
    Groq = None
from src.models.league import db, Team, AcademyPlayer, Newsletter, AdminSetting, NewsletterCommentary
from src.models.tracked_player import TrackedPlayer
from src.models.journey import PlayerJourney, PlayerJourneyEntry, derive_journey_context
from src.api_football_client import APIFootballClient
from src.agents.weekly_agent import (
    lint_and_enrich as legacy_lint_and_enrich,
    _apply_player_lookup,
    _set_latest_player_lookup,
    _normalize_player_key,
    to_initial_last,
    _render_variants,
)
from src.utils.newsletter_slug import compose_newsletter_public_slug
from src.services.graph_service import GraphService

# If you have an MCP client already for Brave (Model Context Protocol), import it here.
# This is a thin wrapper that exposes a Python function brave_search(query: str, since: str, until: str) -> List[dict]
from src.mcp.brave import brave_search  # implement this wrapper to call your MCP tool
from .weekly_agent import get_league_localization
import dotenv
dotenv.load_dotenv(dotenv.find_dotenv())

# client = OpenAI(
#     base_url="https://openrouter.ai/api/v1",
#     api_key=os.getenv("OPENROUTER_API_KEY")
# )
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
set_default_openai_client(client)
api_client = APIFootballClient()
graph_service = GraphService()
_GROQ_CLIENT: Optional["Groq"] = None

def _get_groq_client() -> Groq:
    global _GROQ_CLIENT
    if _GROQ_CLIENT is not None:
        return _GROQ_CLIENT
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or Groq is None:
        raise RuntimeError("GROQ_API_KEY is not configured")
    _GROQ_CLIENT = Groq(api_key=api_key)
    return _GROQ_CLIENT

# Always-on debug output during development
def _nl_dbg(*args):
    # Temporarily disabled to reduce noise during commentary testing
    # try:
    #     print("[NEWSLETTER DBG]", *args)
    # except Exception:
    #     pass
    pass


def _llm_dbg(event: str, payload: dict | None = None) -> None:
    """Lightweight helper to keep LLM instrumentation consistent."""
    if payload:
        _nl_dbg(f"[LLM] {event}", payload)
    else:
        _nl_dbg(f"[LLM] {event}")


def _coerce_text(value: Any, *, fallback: str = "") -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, dict):
        for key in ("text", "title", "name", "value", "label"):
            candidate = value.get(key)
            if isinstance(candidate, str):
                return candidate
    if value is None:
        return fallback
    try:
        return str(value)
    except Exception:
        return fallback


def _strip_text(value: Any, *, fallback: str = "") -> str:
    return _coerce_text(value, fallback=fallback).strip()

# 
# Feature toggles (soft ranking, site boosts, cup synonyms)
# Default to conservative behavior: only cup synonyms enabled by default to improve recall.
ENV_SOFT_RANK = os.getenv("BRAVE_SOFT_RANK", "1").lower() in ("1", "true", "yes")
ENV_SITE_BOOST = os.getenv("BRAVE_SITE_BOOST", "1").lower() in ("1", "true", "yes")
ENV_USE_CUP_SYNS = os.getenv("BRAVE_CUP_SYNONYMS", "1").lower() in ("1", "true", "yes")
ENV_STRICT_RANGE = os.getenv("BRAVE_STRICT_RANGE", "0").lower() in ("1", "true", "yes")
ENV_CHECK_LINKS = os.getenv("NEWSLETTER_CHECK_LINKS", "1").lower() in ("1", "true", "yes")
ENV_VALIDATE_FINAL_LINKS = os.getenv("NEWSLETTER_VALIDATE_FINAL_LINKS", "1").lower() in ("1", "true", "yes")
ENV_ENABLE_GROQ_SUMMARIES = os.getenv("NEWSLETTER_USE_GROQ", "1").lower() in ("1", "true", "yes", "on")
ENV_ENABLE_GROQ_TEAM_SUMMARIES = os.getenv(
    "NEWSLETTER_USE_GROQ_TEAM",
    os.getenv("NEWSLETTER_USE_GROQ", "1"),
).lower() in ("1", "true", "yes", "on")
LINK_TIMEOUT_SEC = float(os.getenv("NEWSLETTER_LINK_TIMEOUT", "6"))
LINK_MAX_WORKERS = int(os.getenv("NEWSLETTER_LINK_MAX_WORKERS", "8"))
LINKS_MAX_PER_ITEM = int(os.getenv("NEWSLETTER_LINKS_MAX_PER_ITEM", "3"))

UNTRACKED_MESSAGE = "We can’t track detailed stats for this player yet."

# Minimal localization (GB defaults). We keep this simple here to avoid importing heavy modules.
LOCALIZATION_DEFAULT = {"country": "GB", "search_lang": "en", "ui_lang": "en-GB"}

BRAVE_LOCALIZATION_BY_ISO = {
    "GB": {"country": "GB", "search_lang": "en", "ui_lang": "en-GB"},
    "IE": {"country": "IE", "search_lang": "en", "ui_lang": "en-IE"},
    "US": {"country": "US", "search_lang": "en", "ui_lang": "en-US"},
    "CA": {"country": "CA", "search_lang": "en", "ui_lang": "en-CA"},
    "FR": {"country": "FR", "search_lang": "fr", "ui_lang": "fr-FR"},
    "ES": {"country": "ES", "search_lang": "es", "ui_lang": "es-ES"},
    "PT": {"country": "PT", "search_lang": "pt", "ui_lang": "pt-PT"},
    "BR": {"country": "BR", "search_lang": "pt", "ui_lang": "pt-BR"},
    "DE": {"country": "DE", "search_lang": "de", "ui_lang": "de-DE"},
    "AT": {"country": "AT", "search_lang": "de", "ui_lang": "de-AT"},
    "CH-DE": {"country": "CH", "search_lang": "de", "ui_lang": "de-CH"},
    "CH-FR": {"country": "CH", "search_lang": "fr", "ui_lang": "fr-CH"},
    "CH-IT": {"country": "CH", "search_lang": "it", "ui_lang": "it-CH"},
    "IT": {"country": "IT", "search_lang": "it", "ui_lang": "it-IT"},
    "NL": {"country": "NL", "search_lang": "nl", "ui_lang": "nl-NL"},
    "BE-NL": {"country": "BE", "search_lang": "nl", "ui_lang": "nl-BE"},
    "BE-FR": {"country": "BE", "search_lang": "fr", "ui_lang": "fr-BE"},
    "SE": {"country": "SE", "search_lang": "sv", "ui_lang": "sv-SE"},
    "NO": {"country": "NO", "search_lang": "no", "ui_lang": "no-NO"},
    "DK": {"country": "DK", "search_lang": "da", "ui_lang": "da-DK"},
    "FI": {"country": "FI", "search_lang": "fi", "ui_lang": "fi-FI"},
    "PL": {"country": "PL", "search_lang": "pl", "ui_lang": "pl-PL"},
    "HR": {"country": "HR", "search_lang": "hr", "ui_lang": "hr-HR"},
    "BA": {"country": "BA", "search_lang": "bs", "ui_lang": "bs-BA"},
}

COUNTRY_FALLBACKS = {
    "BE": ["BE-FR", "BE-NL", "NL", "FR"],
    "CH": ["CH-DE", "CH-FR", "CH-IT", "DE", "FR", "IT"],
    "CA": ["US", "GB"],
    "BR": ["PT"],
    "MX": ["ES", "US"],
    "AR": ["ES"],
    "CO": ["ES"],
    "JP": ["US"]
}

def resolve_localization_for_country(iso_code: str | None, default: dict[str, str] | None = None) -> dict[str, str]:
    base = dict(default or LOCALIZATION_DEFAULT)
    if not iso_code:
        return base
    key = iso_code.upper()
    if key in BRAVE_LOCALIZATION_BY_ISO:
        return dict(BRAVE_LOCALIZATION_BY_ISO[key])
    for fallback in COUNTRY_FALLBACKS.get(key, []):
        if fallback in BRAVE_LOCALIZATION_BY_ISO:
            return dict(BRAVE_LOCALIZATION_BY_ISO[fallback])
    return base


def _enforce_player_metadata(
    content: dict,
    meta_by_pid: dict[int, dict[str, Any]],
    meta_by_key: dict[str, dict[str, Any]],
) -> dict:
    if not isinstance(content, dict):
        return content

    sections = content.get('sections')
    if not isinstance(sections, list):
        return content

    internet_links: dict[str, list[Any]] = {}
    manual_player_items: list[dict[str, Any]] = []
    new_sections: list[dict[str, Any]] = []
    tracked_pids: set[int] = set()
    tracked_keys: set[str] = set()

    def _process_item_list(raw_items: list) -> list:
        """Process a list of player items: enrich metadata, dedup, filter untracked."""
        filtered: list[dict[str, Any]] = []
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            meta = None
            pid = item.get('player_id')
            try:
                pid_int = int(pid)
            except (TypeError, ValueError):
                pid_int = None
            player_key = _normalize_player_key(item.get('player_name'))
            if pid_int is not None and pid_int in meta_by_pid:
                meta = meta_by_pid[pid_int]
            else:
                if player_key:
                    meta = meta_by_key.get(player_key)

            explicit_can_fetch = item.get('can_fetch_stats')
            if explicit_can_fetch is False:
                can_track = False
            elif explicit_can_fetch is True:
                can_track = True
            else:
                can_track = bool(meta.get('can_fetch_stats', True) if meta else True)
            item['can_fetch_stats'] = can_track
            if not can_track:
                item.pop('stats', None)

            if meta:
                sofa = meta.get('sofascore_player_id')
                if sofa and not item.get('sofascore_player_id'):
                    item['sofascore_player_id'] = sofa

            is_untracked = not can_track
            if is_untracked:
                if pid_int is not None:
                    meta_pid = meta_by_pid.get(pid_int)
                    if (meta_pid and meta_pid.get('can_fetch_stats', True)) or pid_int in tracked_pids:
                        continue
                if player_key:
                    meta_key = meta_by_key.get(player_key)
                    if (meta_key and meta_key.get('can_fetch_stats', True)) or player_key in tracked_keys:
                        continue

                if not _strip_text(item.get('week_summary')):
                    item['week_summary'] = UNTRACKED_MESSAGE
                manual_player_items.append(item)
                continue

            filtered.append(item)
            if pid_int is not None:
                tracked_pids.add(pid_int)
            if player_key:
                tracked_keys.add(player_key)
        return filtered

    for sec in sections:
        if not isinstance(sec, dict):
            continue

        # Handle sections with subsections (On Loan, Academy Rising)
        if 'subsections' in sec and isinstance(sec['subsections'], list):
            title = _strip_text(sec.get('title')).lower()
            if title == 'what the internet is saying':
                continue
            for sub in sec['subsections']:
                raw_items = sub.get('items')
                if isinstance(raw_items, list):
                    sub['items'] = _process_item_list(raw_items)
            # Keep section even if some subsections are empty
            sec['subsections'] = [s for s in sec['subsections'] if s.get('items')]
            if sec['subsections']:
                new_sections.append(sec)
            continue

        raw_items = sec.get('items')
        if not isinstance(raw_items, list):
            continue
        title = _strip_text(sec.get('title')).lower()
        if title == 'what the internet is saying':
            for item in raw_items:
                if not isinstance(item, dict):
                    continue
                links = item.get('links')
                if not isinstance(links, list):
                    continue
                key = _normalize_player_key(item.get('player_name'))
                if not key:
                    continue
                bucket = internet_links.setdefault(key, [])
                bucket.extend(link for link in links if link)
            continue

        filtered_items = _process_item_list(raw_items)
        if filtered_items:
            sec['items'] = filtered_items
            new_sections.append(sec)

    if manual_player_items:
        new_sections.append({'title': 'Manual Player Entries', 'items': manual_player_items})

    if internet_links:
        def _all_items_in_section(sec):
            """Yield all items from a section, whether flat or subsectioned."""
            if 'subsections' in sec and isinstance(sec.get('subsections'), list):
                for sub in sec['subsections']:
                    yield from (sub.get('items') or [])
            else:
                yield from (sec.get('items') if isinstance(sec.get('items'), list) else [])

        for sec in new_sections:
            for item in _all_items_in_section(sec):
                if not isinstance(item, dict):
                    continue
                key = _normalize_player_key(item.get('player_name'))
                if not key or key not in internet_links:
                    continue

                existing = item.get('links') if isinstance(item.get('links'), list) else []
                merged: list[Any] = []
                seen: set[str] = set()

                def _push(link: Any) -> None:
                    if isinstance(link, str):
                        url = _strip_text(link)
                        payload = url
                    elif isinstance(link, dict):
                        url = _strip_text(link.get('url'))
                        if not url:
                            return
                        payload = {k: v for k, v in link.items()}
                    else:
                        return
                    if not url or url in seen:
                        return
                    seen.add(url)
                    merged.append(payload)

                for link in existing:
                    _push(link)
                for link in internet_links.get(key, []):
                    _push(link)

                if merged:
                    item['links'] = merged[:LINKS_MAX_PER_ITEM]
                elif 'links' in item:
                    item['links'] = []

    content['sections'] = new_sections
    return content

# Cup synonyms to improve recall for competition names in headlines
CUP_SYNONYMS = {
    "EFL Trophy": ["Papa Johns Trophy", "E.F.L. Trophy", "Football League Trophy"],
    "FA Cup": ["Emirates FA Cup", "FA Cup First Round", "FA Cup Round One"],
    "League Cup": ["Carabao Cup", "EFL Cup"],
}

def _admin_bool(key: str, default: bool) -> bool:
    try:
        row = db.session.query(AdminSetting).filter_by(key=key).first()
        if row and row.value_json:
            return _strip_text(row.value_json).lower() in ("1","true","yes","y")
    except Exception:
        pass
    return default

def _get_flags() -> dict:
    return {
        'soft_rank': _admin_bool('brave_soft_rank', ENV_SOFT_RANK),
        'site_boost': _admin_bool('brave_site_boost', ENV_SITE_BOOST),
        'cup_synonyms': _admin_bool('brave_cup_synonyms', ENV_USE_CUP_SYNS),
        'strict_range': _admin_bool('search_strict_range', ENV_STRICT_RANGE),
    }

def expand_competition_terms(comp: str, *, use_synonyms: bool) -> list[str]:
    base = [comp] if comp else []
    if not use_synonyms:
        return base
    return base + CUP_SYNONYMS.get(comp, [])

# Optional site boosts (only used if SITE_BOOST is enabled)
SITE_BOOSTS_BY_COUNTRY = {
    "GB": [
        "bbc.co.uk/sport", "yorkshirepost.co.uk", "manchesterworld.uk",
        # club sites
        "chelseafc.com", "nottinghamforest.co.uk", "rotherhamunited.co.uk",
        "cheltenhamtownfc.com", "doncasterroversfc.co.uk", "walsallfc.co.uk",
        "carlisleunited.co.uk",
    ]
}

# Soft ranking weights and helpers
RANK_WEIGHTS = {
    "domain_boost": 3,
    "name_team_match": 2,
    "opponent_match": 1,
    "recency": 1,
    "noisy_penalty": -2,
}
NOISY_HOST_SNIPS = ("fandom.com", "ea.com/games/ea-sports-fc")

def _strip_diacritics(s: str) -> str:
    try:
        import unicodedata
        return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")
    except Exception:
        return s

def _parse_any_date(s: str):
    if not s or not isinstance(s, str):
        return None
    st = _strip_text(s)
    try:
        from datetime import datetime
        iso = st.replace('Z', '+00:00')
        return datetime.fromisoformat(iso)
    except Exception:
        pass
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(st)
    except Exception:
        pass
    try:
        from datetime import date as _date
        return _date.fromisoformat(st[:10])
    except Exception:
        return None

def _score_hit(hit: dict, player_last: str, team_l: str, opponent: str | None, country: str, site_boost_flag: bool) -> int:
    try:
        url = (hit.get("url") or "").lower()
        title = (hit.get("title") or "").lower()
        snip = (hit.get("snippet") or "").lower()
        txt = f"{title} {snip}"
        score = 0
        if any(nh in url for nh in NOISY_HOST_SNIPS):
            score += RANK_WEIGHTS["noisy_penalty"]
        if site_boost_flag and any(site in url for site in SITE_BOOSTS_BY_COUNTRY.get(country, [])):
            score += RANK_WEIGHTS["domain_boost"]
        if player_last and player_last in txt and (team_l and team_l in txt):
            score += RANK_WEIGHTS["name_team_match"]
        elif player_last and player_last in txt:
            score += 1
        if opponent and opponent.lower() in txt:
            score += RANK_WEIGHTS["opponent_match"]
        if _parse_any_date(hit.get("date")):
            score += RANK_WEIGHTS["recency"]
        return score
    except Exception:
        return 0

def _gentle_filter(hit: dict, player_last: str, team_l: str) -> bool:
    # Keep transfers and match-intent pages; drop generic listicles if they lack both player+team
    title = (hit.get("title") or "").lower()
    snip = (hit.get("snippet") or "").lower()
    txt = f"{title} {snip}"
    if "transfer" in txt or "loan" in txt:
        return True
    match_terms = ("match report", "match reaction", "player ratings", "verdict", "talking points", "highlights")
    if any(t in txt for t in match_terms):
        return True
    if team_l and team_l in txt:
        return True
    if player_last and player_last in txt:
        return True
    return False


def _pluralize(value: int | float, singular: str, plural: str | None = None) -> str:
    plural_form = plural or f"{singular}s"
    return singular if abs(int(value)) == 1 else plural_form


def _to_int(value: Any) -> int:
    try:
        if value is None:
            return 0
        if isinstance(value, bool):
            return int(value)
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _safe_float(value: Any) -> float | None:
    try:
        f = float(value)
        if f != f:  # NaN check
            return None
        return f
    except (TypeError, ValueError):
        return None


def _combine_phrases(parts: list[Any]) -> str:
    cleaned: list[str] = []
    for part in parts:
        text = _strip_text(part)
        if text:
            cleaned.append(text)
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    return ", ".join(cleaned[:-1]) + f" and {cleaned[-1]}"


def _stat_highlights(stats: dict) -> list[str]:
    phrases: list[str] = []
    goals = _to_int(stats.get("goals"))
    assists = _to_int(stats.get("assists"))
    shots_total = _to_int(stats.get("shots_total"))
    shots_on = _to_int(stats.get("shots_on"))
    passes_total = _to_int(stats.get("passes_total"))
    passes_key = _to_int(stats.get("passes_key"))
    tackles_total = _to_int(stats.get("tackles_total"))
    duels_won = _to_int(stats.get("duels_won"))
    duels_total = _to_int(stats.get("duels_total"))
    saves = _to_int(stats.get("saves"))
    rating = _safe_float(stats.get("rating"))

    if goals:
        phrases.append(f"{goals} {_pluralize(goals, 'goal')}")
    if assists:
        phrases.append(f"{assists} {_pluralize(assists, 'assist')}")
    if shots_total:
        shot_phrase = f"{shots_total} {_pluralize(shots_total, 'shot')}"
        if shots_on:
            shot_phrase += f" ({shots_on} on target)"
        phrases.append(shot_phrase)
    if passes_total and passes_total >= 20:
        phrases.append(f"{passes_total} completed {_pluralize(passes_total, 'pass')}")
    if passes_key:
        phrases.append(f"{passes_key} key {_pluralize(passes_key, 'pass')}")
    if tackles_total:
        phrases.append(f"{tackles_total} {_pluralize(tackles_total, 'tackle')}")
    if duels_won and duels_total:
        phrases.append(f"{duels_won}/{duels_total} duels won")
    if saves:
        phrases.append(f"{saves} {_pluralize(saves, 'save')}")
    if rating and rating > 0:
        phrases.append(f"a {rating:.1f} rating")
    return phrases[:4]


def _match_result_phrase(loanee: dict | None) -> str | None:
    if not isinstance(loanee, dict):
        return None
    matches = loanee.get("matches")
    if not isinstance(matches, list) or not matches:
        return None
    chosen = None
    for match in matches:
        if isinstance(match, dict) and match.get("played") is not False:
            chosen = match
            break
    if chosen is None:
        chosen = matches[0] if isinstance(matches[0], dict) else None
    if not isinstance(chosen, dict):
        return None
    opponent = _strip_text(chosen.get("opponent"))
    raw_score = chosen.get("score") or chosen.get("scoreline")
    score = _format_score(raw_score, chosen)
    competition = _strip_text(chosen.get("competition"))
    result_code = _strip_text(chosen.get("result")).upper()
    result_word = {"W": "win", "D": "draw", "L": "defeat"}.get(result_code)

    parts: list[str] = []
    if result_word and opponent:
        if score:
            parts.append(f"{result_word} {score} over {opponent}")
        else:
            parts.append(f"{result_word} against {opponent}")
    elif opponent and score:
        parts.append(f"{score} against {opponent}")
    elif opponent:
        parts.append(f"against {opponent}")

    if competition:
        if parts:
            parts[-1] = f"{parts[-1]} in {competition}"
        else:
            parts.append(f"in {competition}")

    return parts[0] if parts else None


def _hits_by_player(brave_ctx: dict) -> dict[str, list[dict[str, Any]]]:
    mapping: dict[str, list[dict[str, Any]]] = {}
    if not isinstance(brave_ctx, dict):
        return mapping
    for query, hits in brave_ctx.items():
        if not isinstance(query, str):
            continue
        names = re.findall(r'"([^"]+)"', query)
        player_name = names[0] if names else None
        if not player_name:
            continue
        key = _normalize_player_key(player_name)
        if not key:
            continue
        bucket = mapping.setdefault(key, [])
        if isinstance(hits, list):
            for hit in hits:
                if isinstance(hit, dict):
                    bucket.append(hit)
    return mapping


def _merge_links_from_hits(item: dict, hits: list[dict[str, Any]]) -> None:
    if not isinstance(item, dict):
        return
    if not isinstance(hits, list):
        return
    existing_links = item.get("links")
    if not isinstance(existing_links, list):
        existing_links = []
    seen_urls: set[str] = set()
    for link in existing_links:
        if isinstance(link, str):
            url = _strip_text(link)
            if url:
                seen_urls.add(url)
        elif isinstance(link, dict):
            url = _strip_text(link.get("url"))
            if url:
                seen_urls.add(url)
    for hit in hits:
        if not isinstance(hit, dict):
            continue
        url = _strip_text(hit.get("url"))
        if not url or url in seen_urls:
            continue
        title = _strip_text(hit.get("title")) or url
        existing_links.append({"title": title, "url": url})
        seen_urls.add(url)
        if len(existing_links) >= LINKS_MAX_PER_ITEM:
            break
    item["links"] = existing_links


def _ensure_period(text: str) -> str:
    if not text:
        return text
    stripped = _strip_text(text)
    if not stripped:
        return stripped
    last = stripped[-1]
    if last in ".!?":
        return stripped
    if last in ",;:":
        stripped = stripped[:-1].rstrip()
        if not stripped:
            return ""
    return stripped + "."


def _build_player_summary(item: dict, loanee: dict | None, stats: dict, match_phrase: str | None, hits: list[dict[str, Any]]) -> tuple[str, str, str | None]:
    player_display = _strip_text(item.get("player_name")) or (
        _strip_text(loanee.get("player_name")) if isinstance(loanee, dict) else ""
    )
    minutes = _to_int(stats.get("minutes"))
    team_label = (
        _strip_text(item.get("loan_team"))
        or (_strip_text(loanee.get("loan_team_name")) if isinstance(loanee, dict) else "")
        or "his loan side"
    )
    can_track = bool(item.get("can_fetch_stats", loanee.get("can_fetch_stats", True) if isinstance(loanee, dict) else True))

    matches = loanee.get("matches") if isinstance(loanee, dict) else item.get("matches") if isinstance(item, dict) else []
    played_matches = [m for m in matches or [] if isinstance(m, dict) and m.get("played") is not False]
    match_count = len(played_matches) or len([m for m in matches or [] if isinstance(m, dict)])
    multi_match_week = match_count > 1
    if multi_match_week:
        match_phrase = None
    elif match_phrase is None:
        match_phrase = _match_result_phrase(loanee)

    # Check if player was in matchday squad by looking at role field
    # role can be: 'startXI', 'substitutes', or None (not in squad)
    def _was_in_squad(match_list: list) -> bool:
        for m in match_list or []:
            if isinstance(m, dict) and m.get("role") in ("startXI", "substitutes"):
                return True
        return False
    
    def _was_unused_sub(match_list: list) -> bool:
        for m in match_list or []:
            if isinstance(m, dict) and m.get("role") == "substitutes":
                return True
        return False
    
    was_in_squad = _was_in_squad(matches)
    was_unused_sub = _was_unused_sub(matches)

    if not can_track:
        base = UNTRACKED_MESSAGE
        if player_display and team_label:
            base += f" {player_display} is currently with {team_label}."
    else:
        if multi_match_week and minutes > 0:
            if match_count:
                base = f"Played {minutes}' across {match_count} matches for {team_label}"
            else:
                base = f"Played {minutes}' across multiple matches for {team_label}"
        elif multi_match_week and minutes == 0:
            if was_in_squad:
                if match_count:
                    base = f"Was an unused substitute across {match_count} matches for {team_label}"
                else:
                    base = f"Was an unused substitute across this week's fixtures for {team_label}"
            else:
                if match_count:
                    base = f"Was not in the matchday squad across {match_count} matches for {team_label}"
                else:
                    base = f"Was not in the matchday squad for {team_label}'s fixtures this week"
        else:
            if minutes > 0:
                base = f"Played {minutes}' for {team_label}"
            elif minutes == 0 and was_unused_sub:
                base = f"Was an unused substitute for {team_label}"
            elif minutes == 0 and not was_in_squad:
                base = f"Was not in the matchday squad for {team_label}"
            else:
                base = f"Featured for {team_label}"

        if match_phrase and not multi_match_week:
            connector = " in " if minutes > 0 else " during "
            base += connector + match_phrase

    stat_phrases = _stat_highlights(stats) if can_track else []
    if stat_phrases:
        if minutes > 0:
            base += f", finishing with {_combine_phrases(stat_phrases)}"
        else:
            base += f"; notable numbers: {_combine_phrases(stat_phrases)}"

    base_sentence = _ensure_period(base)

    first_title = None
    if isinstance(hits, list):
        for hit in hits:
            title = _strip_text(hit.get("title"))
            if title:
                first_title = title
                break

    if not first_title:
        existing_links = item.get("links")
        if isinstance(existing_links, list):
            for link in existing_links:
                if isinstance(link, dict):
                    title = _strip_text(link.get("title"))
                    if title:
                        first_title = title
                        break
                elif isinstance(link, str):
                    url_title = _strip_text(link)
                    if url_title:
                        first_title = url_title
                        break

    if first_title:
        if can_track:
            article_sentence = f"Latest coverage: {first_title}."
        else:
            article_sentence = f"Here’s what the internet is saying: {first_title}."
    else:
        article_sentence = ""

    summary_parts = [base_sentence]
    if article_sentence:
        summary_parts.append(article_sentence)
    summary_text = " ".join(filter(None, ( _strip_text(part) for part in summary_parts )))

    headline_fragments: list[str] = []
    if can_track:
        if multi_match_week:
            if minutes > 0:
                label = f"{match_count} matches" if match_count else "multiple matches"
                headline_fragments.append(f"logged {minutes}’ across {label} for {team_label}")
            elif minutes == 0:
                label = f"{match_count} matches" if match_count else "multiple matches"
                headline_fragments.append(f"unused across {label} for {team_label}")
        else:
            if minutes > 0:
                headline_fragments.append(f"logged {minutes}’ for {team_label}")
            elif minutes == 0:
                headline_fragments.append(f"was unused for {team_label}")
        if stat_phrases:
            headline_fragments.append(_combine_phrases(stat_phrases))
        if match_phrase and not multi_match_week:
            headline_fragments.append(match_phrase)
    else:
        headline_fragments.append("stats unavailable; monitoring media chatter")
    headline_text = _combine_phrases(headline_fragments) or ""

    return summary_text, headline_text, first_title


def _season_context_sentence(full_name: str, season_stats: dict | None, trends: dict | None) -> str:
    stats = season_stats or {}
    name = _strip_text(full_name)
    if not name:
        return ""

    games = _to_int(stats.get("games_played"))
    minutes = _to_int(stats.get("minutes"))
    goals = _to_int(stats.get("goals"))
    assists = _to_int(stats.get("assists"))
    yellows = _to_int(stats.get("yellows"))
    reds = _to_int(stats.get("reds"))

    parts: list[str] = []
    if games:
        parts.append(f"{games} {_pluralize(games, 'appearance')}")
    if minutes:
        parts.append(f"{minutes} {_pluralize(minutes, 'minute')}")
    if goals or assists:
        goal_phrase = f"{goals} {_pluralize(goals, 'goal')}"
        assist_phrase = f"{assists} {_pluralize(assists, 'assist')}"
        parts.append(f"{goal_phrase} and {assist_phrase}")
    if yellows:
        parts.append(f"{yellows} yellow {_pluralize(yellows, 'card')}")
    if reds:
        parts.append(f"{reds} red {_pluralize(reds, 'card')}")

    if parts:
        sentence = f"Season to date, {name} has {', '.join(parts)}."
    else:
        sentence = f"Season to date, {name} has limited recorded minutes."

    trend_bits: list[str] = []
    trends = trends or {}
    if trends.get("goals_per_90"):
        trend_bits.append(f"{trends['goals_per_90']} goals/90")
    if trends.get("assists_per_90"):
        trend_bits.append(f"{trends['assists_per_90']} assists/90")
    if trends.get("shot_accuracy"):
        trend_bits.append(f"{trends['shot_accuracy']}% shot accuracy")
    if trends.get("goals_last_5"):
        trend_bits.append(f"{trends['goals_last_5']} goals in the last five")
    if trends.get("assists_last_5"):
        trend_bits.append(f"{trends['assists_last_5']} assists in the last five")
    if trends.get("duels_win_rate"):
        trend_bits.append(f"{trends['duels_win_rate']}% duels win rate")

    if trend_bits:
        sentence += f" Trends: {', '.join(trend_bits)}."

    return _ensure_period(sentence)


def _extract_hits_for_loanee(loanee: dict, hits_by_player: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    aliases = [
        loanee.get("player_name"),
        loanee.get("player_full_name"),
        to_initial_last(loanee.get("player_full_name") or ""),
        to_initial_last(loanee.get("player_name") or ""),
    ]
    for alias in filter(None, aliases):
        key = _normalize_player_key(alias)
        if key and key in hits_by_player:
            return hits_by_player[key]
    return []


def _build_links_from_hits(hits: list[dict[str, Any]], *, limit: int = LINKS_MAX_PER_ITEM) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    seen: set[str] = set()
    for hit in hits or []:
        if not isinstance(hit, dict):
            continue
        url = _strip_text(hit.get("url"))
        title = _strip_text(hit.get("title")) or url
        if not url or url in seen:
            continue
        links.append({"title": title, "url": url})
        seen.add(url)
        if len(links) >= limit:
            break
    return links


def _format_score(value: Any, match: dict | None = None) -> str:
    def _coerce_goal(goal_value: Any) -> str | None:
        if goal_value is None:
            return None
        try:
            if isinstance(goal_value, (int, float)):
                return str(int(goal_value))
            goal_text = _strip_text(goal_value)
            if goal_text:
                return goal_text
        except Exception:
            pass
        return None

    def _pick(*candidates):
        for candidate in candidates:
            if candidate is not None:
                return candidate
        return None

    if isinstance(value, dict):
        home = _coerce_goal(_pick(value.get("home"), value.get("home_goals")))
        away = _coerce_goal(_pick(value.get("away"), value.get("away_goals")))
        if home is not None and away is not None:
            return f"{home}-{away}"
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        home = _coerce_goal(value[0])
        away = _coerce_goal(value[1])
        if home is not None and away is not None:
            return f"{home}-{away}"

    text = _strip_text(value)
    if text:
        return text

    if match and isinstance(match, dict):
        home = _coerce_goal(match.get("home_goals"))
        away = _coerce_goal(match.get("away_goals"))
        if home is not None and away is not None:
            return f"{home}-{away}"
    return "score unavailable"


def _media_spotlight_sentence(player_name: str, links: list[dict[str, str]]) -> str | None:
    titles: list[str] = []
    for link in links or []:
        if not isinstance(link, dict):
            continue
        title = _strip_text(link.get("title")) or _strip_text(link.get("url"))
        if not title:
            continue
        titles.append(title)
        if len(titles) >= 3:
            break
    if not titles:
        return None
    if len(titles) == 1:
        coverage = titles[0]
    elif len(titles) == 2:
        coverage = f"{titles[0]} and {titles[1]}"
    else:
        coverage = f"{titles[0]}, {titles[1]} and more coverage"
    return _ensure_period(f"Media spotlight on {player_name or 'this player'}: {coverage}.")


PLAYER_SUMMARY_SYSTEM_PROMPT = (
    "You are a football journalist writing engaging weekly academy pipeline reports. "
    "The player may be on loan at another club, in the parent club's first team, or in the academy. "
    "Adapt your language to their pathway_status:\n"
    "- 'on_loan': Frame as a loan report—mention the loan club, how they performed away from the parent club\n"
    "- 'first_team': Frame as an established first-team player—they've cemented their place in the senior squad\n"
    "- 'first_team_debut': Frame as an exciting debut/cameo—they've broken through but are still establishing themselves\n"
    "- 'academy': Frame as an academy prospect update—focus on development and season progress\n\n"
    "Write in a warm, narrative style—like a knowledgeable fan updating friends at the pub. "
    "You receive stats and a 'draft_summary' with the raw facts. Transform this into compelling prose that:\n"
    "- Weaves stats naturally into sentences (not just listing them)\n"
    "- Uses vivid verbs: 'bagged', 'delivered', 'anchored', 'orchestrated', 'struggled'\n"
    "- Contextualizes performances using ONLY the provided stats\n"
    "- Varies sentence rhythm—mix short punchy lines with flowing observations\n\n"
    "JOURNEY CONTEXT:\n"
    "- If 'journey_context' is provided, weave it naturally into the narrative\n"
    "- Examples: 'promoted from U21', 'on second loan spell', 'first-team graduate'\n"
    "- This adds depth about the player's development pathway\n\n"
    "ROLE DATA (CRITICAL for accuracy - determines how player entered the match):\n"
    "- Each match includes 'role' showing how the player was selected:\n"
    "  - 'startXI' = Player STARTED the match (was in starting lineup)\n"
    "  - 'substitutes' = Player was a SUBSTITUTE (came off the bench OR was an unused sub)\n"
    "  - null/None = Player was NOT in the matchday squad (injured, suspended, not selected)\n"
    "- If role='startXI' → use 'started', 'was named in the starting XI', 'began the match'\n"
    "- If role='substitutes' AND minutes > 0 → use 'came off the bench', 'was introduced as a substitute'\n"
    "- If role='substitutes' AND minutes = 0 → 'was an unused substitute'\n"
    "- If role is null AND minutes = 0 → 'was not in the matchday squad'\n"
    "- If a player started but played few minutes (e.g. 15-20), they were likely subbed off early (injury/tactical)\n\n"
    "POSITION DATA (critical for accuracy):\n"
    "- Each match includes 'position' showing what role they played THAT game (G=Goalkeeper, D=Defender, M=Midfielder, F=Forward)\n"
    "- A player registered as midfielder may play forward in some matches—use the per-match position\n"
    "- When describing goals/assists, reference the position they played IN THAT MATCH\n"
    "- Example: If position='F' and they scored, say 'found the net from his advanced role', not 'scored from midfield'\n\n"
    "STRICT RULES (never break these):\n"
    "- ONLY use facts from the provided data—never invent goals, assists, or events\n"
    "- Keep ALL numbers exactly as given (minutes, goals, assists, cards, ratings)\n"
    "- Never claim 'debut', 'first goal', 'milestone' unless explicitly in draft_summary\n"
    "- Never compare to 'average strikers' or generic benchmarks—only this player's data\n"
    "- NEVER invent atmospheric/contextual details: no weather (rain, sun, cold), no crowd size, no time of day, no pitch conditions\n"
    "- NEVER invent match narrative: no 'late equalizer', 'opening minutes', 'second half surge' unless the data says so\n"
    "- If draft_summary is missing, write 1–2 paragraphs from the stats alone\n\n"
    "Aim for 2–3 sentences that feel like a scout's notebook entry, not a spreadsheet."
)

TEAM_SUMMARY_SYSTEM_PROMPT = (
    "You are a football journalist writing the opening hook for a weekly academy pipeline newsletter. "
    "The newsletter covers four categories of players: established first-team players, first-team debutants, players out on loan, and academy prospects. "
    "Capture the week's story in 2–3 punchy sentences that make readers want to dive into the player details. "
    "Use the provided player summaries to highlight standout performers, surprising results, or emerging themes. "
    "Keep every stat and fact accurate—do not invent or embellish. "
    "Write like you're teasing the best bits to a fellow fan, not reading a match report."
)

def _summarize_player_with_groq(
    loanee: dict,
    stats: dict,
    season_context: dict | None,
    links: list[dict[str, str]] | None,
    draft_summary: str | None = None,
) -> str:
    model = os.getenv("NEWSLETTER_GROQ_MODEL", "openai/gpt-oss-120b")
    client = _get_groq_client()
    # Build per-match breakdown with positions and roles for accurate attribution
    matches_data = []
    for m in (loanee.get("matches") or [])[:3]:
        if isinstance(m, dict):
            player_match = m.get("player") or {}
            matches_data.append({
                "opponent": m.get("opponent"),
                "competition": m.get("competition"),
                "position": player_match.get("position"),  # G/D/M/F for THIS match
                "role": m.get("role"),  # 'startXI', 'substitutes', or None (not in squad)
                "goals": player_match.get("goals", 0),
                "assists": player_match.get("assists", 0),
                "minutes": player_match.get("minutes", 0),
                "result": m.get("result"),
            })
    
    payload = {
        "player": {
            "name": loanee.get("player_full_name") or loanee.get("player_name"),
            "loan_team": loanee.get("loan_team_name") or loanee.get("loan_team"),
            "position": stats.get("position"),  # Most recent/primary position
            "pathway_status": loanee.get("pathway_status", "on_loan"),
        },
        "matches": matches_data,  # Per-match breakdown with positions
        "week": stats,
        "season": (season_context or {}).get("season_stats"),
        "trends": (season_context or {}).get("trends"),
        "recent_form": (season_context or {}).get("recent_form"),
        "media_links": links or [],
    }
    if loanee.get("journey_context"):
        payload["journey_context"] = loanee["journey_context"]
    if draft_summary:
        payload["draft_summary"] = draft_summary
    player_meta = {
        "player": payload["player"]["name"],
        "loan_team": payload["player"]["loan_team"],
        "model": model,
        "link_count": len(links or []),
        "minutes": stats.get("minutes"),
        "goals": stats.get("goals"),
        "assists": stats.get("assists"),
        "has_draft": bool(draft_summary),
    }
    _llm_dbg("player.start", player_meta)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": PLAYER_SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.3,
            max_tokens=240,
        )
    except Exception as exc:
        _llm_dbg("player.error", {**player_meta, "error": str(exc)})
        raise
    content = response.choices[0].message.content if response.choices else ""
    usage = getattr(response, "usage", None)
    usage_payload = None
    if usage:
        usage_payload = {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
        }
    has_content = bool(content)
    event_payload = {**player_meta, "has_content": has_content, "chars": len(content or "")}
    if usage_payload:
        event_payload["usage"] = usage_payload
    _llm_dbg("player.finish", event_payload)
    if not has_content:
        _llm_dbg("player.empty-output", player_meta)
    content = (content or "").strip()
    if content:
        last_stop = max(content.rfind("."), content.rfind("!"), content.rfind("?"))
        if last_stop != -1:
            content = content[: last_stop + 1].strip()
    return _ensure_period(content) if content else ""


def _summarize_team_with_groq(
    team_name: str,
    week_range: list[str] | tuple[str, str],
    player_items: list[dict[str, Any]],
    draft_summary: str | None = None,
) -> str:
    model = os.getenv("NEWSLETTER_GROQ_MODEL", "openai/gpt-oss-120b")
    client = _get_groq_client()
    payload = {
        "team": team_name,
        "range": week_range,
        "players": [
            {
                "name": item.get("player_full_name") or item.get("player_name"),
                "summary": item.get("week_summary"),
                "stats": item.get("stats"),
            }
            for item in player_items
        ],
    }
    if draft_summary:
        payload["draft_summary"] = draft_summary
    _llm_dbg("team.start", {"team": team_name, "model": model, "players": len(player_items), "has_draft": bool(draft_summary)})
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": TEAM_SUMMARY_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
            temperature=0.4,
            max_tokens=200,
        )
    except Exception as exc:
        _llm_dbg("team.error", {"team": team_name, "error": str(exc)})
        raise
    content = response.choices[0].message.content if response.choices else ""
    _llm_dbg("team.finish", {"team": team_name, "has_content": bool(content), "chars": len(content or "")})
    content = (content or "").strip()
    if content:
        last_stop = max(content.rfind("."), content.rfind("!"), content.rfind("?"))
        if last_stop != -1:
            content = content[: last_stop + 1].strip()
    return _ensure_period(content) if content else ""


def _build_player_report_item(loanee: dict, hits: list[dict[str, Any]], *, week_start: date, week_end: date) -> dict:
    display_name = to_initial_last(_strip_text(loanee.get("player_full_name")) or _strip_text(loanee.get("player_name"))) or _strip_text(loanee.get("player_name")) or ""
    full_name = _strip_text(loanee.get("player_full_name")) or _strip_text(loanee.get("player_name")) or display_name
    loan_team = _strip_text(loanee.get("loan_team_name") or loanee.get("loan_team") or "their loan side")
    can_track = bool(loanee.get("can_fetch_stats", True))
    stats_src = loanee.get("totals") or {}

    stats: dict[str, Any] = {
        "minutes": _to_int(stats_src.get("minutes")),
        "goals": _to_int(stats_src.get("goals")),
        "assists": _to_int(stats_src.get("assists")),
        "yellows": _to_int(stats_src.get("yellows") or stats_src.get("yellow_cards")),
        "reds": _to_int(stats_src.get("reds") or stats_src.get("red_cards")),
    }
    for key, value in (stats_src or {}).items():
        if key in stats and stats[key]:
            continue
        stats[key] = value

    minutes = _to_int(stats.get("minutes"))
    meaningful_minutes = minutes > 0
    assists = _to_int(stats.get("assists"))
    matches = loanee.get("matches") if isinstance(loanee, dict) else []
    played_matches = [m for m in matches or [] if isinstance(m, dict) and m.get("played") is not False]
    match_count = len(played_matches) or len([m for m in matches or [] if isinstance(m, dict)])
    multi_match_week = match_count > 1
    match_phrase = None if multi_match_week else _match_result_phrase(loanee)
    stat_phrases = _stat_highlights(stats_src if can_track else {})
    paragraphs: list[str] = []
    links = _build_links_from_hits(hits)
    media_sentence = _media_spotlight_sentence(display_name, links)

    # Determine if player was in matchday squad by checking role in matches
    # role can be: 'startXI', 'substitutes', or None (not in squad)
    def _player_was_in_squad(match_list: list) -> bool:
        """Check if player was in at least one matchday squad this week."""
        for m in match_list or []:
            if isinstance(m, dict) and m.get("role") in ("startXI", "substitutes"):
                return True
        return False
    
    def _player_started_match(match_list: list) -> bool:
        """Check if player started (was in starting XI) in any match this week."""
        for m in match_list or []:
            if isinstance(m, dict) and m.get("role") == "startXI":
                return True
        return False
    
    def _player_was_unused_sub(match_list: list) -> bool:
        """Check if player was on the bench but didn't play in any match."""
        for m in match_list or []:
            if isinstance(m, dict) and m.get("role") == "substitutes":
                return True
        return False
    
    was_in_squad = _player_was_in_squad(matches)
    started_match = _player_started_match(matches)
    was_unused_sub = _player_was_unused_sub(matches)
    
    if not can_track:
        base_sentence = f"{UNTRACKED_MESSAGE} {display_name} is currently with {loan_team}."
        paragraphs.append(_ensure_period(base_sentence))
    else:
        if multi_match_week and minutes > 0:
            if match_count:
                action = f"logged {minutes} minutes across {match_count} matches for {loan_team}"
            else:
                action = f"logged {minutes} minutes across multiple matches for {loan_team}"
        elif multi_match_week and minutes == 0:
            if was_in_squad:
                if match_count:
                    action = f"was an unused substitute across {match_count} matches for {loan_team}"
                else:
                    action = f"was an unused substitute across this week's fixtures for {loan_team}"
            else:
                if match_count:
                    action = f"was not in the matchday squad across {match_count} matches for {loan_team}"
                else:
                    action = f"was not in the matchday squad for {loan_team}'s fixtures this week"
        else:
            if minutes >= 60:
                action = f"logged {minutes} minutes for {loan_team}"
            elif minutes > 0:
                # Check role to determine if player started or came off the bench
                if started_match:
                    # Player started but was subbed off (injury/tactical)
                    action = f"started for {loan_team} but was substituted off after {minutes} minutes"
                else:
                    # Player came on as a substitute
                    action = f"came off the bench for {loan_team}, playing {minutes} minutes"
            elif minutes == 0 and was_unused_sub:
                action = f"was an unused substitute for {loan_team}"
            elif minutes == 0 and not was_in_squad:
                action = f"was not in the matchday squad for {loan_team}"
            else:
                action = f"featured for {loan_team}"

        sentence = f"{display_name} {action}"
        if match_phrase and not multi_match_week:
            connector = " in " if minutes != 0 else " during "
            sentence += connector + match_phrase

        remaining_phrases = list(stat_phrases)
        if minutes > 0 and assists > 0 and minutes < 60:
            # Only say "off the bench" if they actually came on as a sub
            if started_match:
                sentence += f", delivering {assists} {_pluralize(assists, 'assist')} before being substituted"
            else:
                sentence += f", delivering {assists} {_pluralize(assists, 'assist')} off the bench"
            remaining_phrases = [p for p in remaining_phrases if "assist" not in p.lower()]
            if remaining_phrases:
                sentence += f" alongside {_combine_phrases(remaining_phrases)}"
        elif remaining_phrases:
            if minutes > 0:
                sentence += f", finishing with {_combine_phrases(remaining_phrases)}"
            else:
                sentence += f"; notable numbers: {_combine_phrases(remaining_phrases)}"

        paragraphs.append(_ensure_period(sentence))

    season_context = loanee.get("season_context") or {}
    season_sentence = _season_context_sentence(full_name, season_context.get("season_stats"), season_context.get("trends"))
    if season_sentence:
        paragraphs.append(season_sentence)

    draft_summary = "\n\n".join(paragraphs)
    week_summary = ""
    summary_origin = "template"
    fallback_reason = None
    should_use_llm = can_track and ENV_ENABLE_GROQ_SUMMARIES and meaningful_minutes and bool(draft_summary.strip())
    if should_use_llm:
        try:
            try:
                llm_summary = _summarize_player_with_groq(loanee, stats_src, season_context, links, draft_summary=draft_summary)
            except TypeError:
                llm_summary = _summarize_player_with_groq(loanee, stats_src, season_context, links)
        except Exception as groq_error:
            _nl_dbg("player-summary-groq-error", str(groq_error))
            llm_summary = ""
            fallback_reason = "groq_error"
        if llm_summary:
            clean_llm = (llm_summary or "").strip()
            too_short = len(clean_llm) < 40 or len(clean_llm.split()) < 6
            if too_short:
                _llm_dbg(
                    "player.summary.too-short",
                    {
                        "player": full_name,
                        "loan_team": loan_team,
                        "chars": len(clean_llm),
                        "words": len(clean_llm.split()),
                        "minutes": minutes,
                    },
                )
                fallback_reason = "llm_too_short"
                llm_summary = ""
            else:
                llm_paragraphs = [clean_llm]
                if links:
                    llm_paragraphs.append(_ensure_period(f"Latest coverage: {links[0]['title']}"))
                week_summary = "\n\n".join(llm_paragraphs)
                summary_origin = "groq"
        else:
            fallback_reason = fallback_reason or "empty_llm_response"
    elif can_track and not ENV_ENABLE_GROQ_SUMMARIES:
        fallback_reason = "llm_disabled"
    elif not can_track:
        fallback_reason = "stats_unavailable"
    else:
        fallback_reason = "no_minutes"

    appended_media_spotlight = False
    if not meaningful_minutes and media_sentence:
        paragraphs.append(media_sentence)
        summary_origin = summary_origin or "media"
        appended_media_spotlight = True

    if not week_summary:
        if links and not appended_media_spotlight:
            paragraphs.append(_ensure_period(f"Latest coverage: {links[0]['title']}"))
        week_summary = "\n\n".join(paragraphs)
        summary_origin = summary_origin or "template"

    item: dict[str, Any] = {
        "player_name": display_name or full_name,
        "player_full_name": full_name,
        "loan_team": loan_team,
        "loan_team_name": loan_team,
        "player_id": loanee.get("player_api_id") or loanee.get("player_id"),
        "player_api_id": loanee.get("player_api_id"),
        "loan_team_api_id": loanee.get("loan_team_api_id") or loanee.get("loan_team_id"),
        "loan_team_id": loanee.get("loan_team_id"),
        "loan_team_country": loanee.get("loan_team_country"),
        "can_fetch_stats": can_track,
        "stats": stats,
        "season_stats": season_context.get("season_stats"),
        "season_totals": loanee.get("season_totals"),
        "season_trends": season_context.get("trends"),
        "recent_form": season_context.get("recent_form"),
        "week_summary": week_summary,
        "links": links,
        "source": loanee.get("source"),
        "upcoming_fixtures": list(loanee.get("upcoming_fixtures") or []),
        "loan_league_name": loanee.get("loan_league_name"),
    }
    if isinstance(matches, list):
        formatted_notes: list[str] = []
        structured_matches: list[dict] = []
        for match in matches[:3]:
            if not isinstance(match, dict):
                continue
            comp = _strip_text(match.get("competition")) or "Match"
            opponent = _strip_text(match.get("opponent")) or "opponent"
            score_text = _format_score(match.get("score") or match.get("scoreline"), match)
            formatted_notes.append(_ensure_period(f"{comp} vs {opponent}: {score_text}"))
            # Build structured match data with opponent visuals and per-match stats
            player_stats_this_match = match.get("player") or {}
            structured_matches.append({
                "opponent": opponent,
                "opponent_id": match.get("opponent_id"),
                "opponent_logo": match.get("opponent_logo"),
                "competition": comp,
                "date": match.get("date"),
                "home": match.get("home"),
                "score": match.get("score"),
                "result": match.get("result"),
                "played": match.get("played"),
                "role": match.get("role"),  # 'startXI', 'substitutes', or None (not in squad)
                "position": player_stats_this_match.get("position"),  # Position played THIS match
                "goals": player_stats_this_match.get("goals", 0),
                "assists": player_stats_this_match.get("assists", 0),
                "minutes": player_stats_this_match.get("minutes", 0),
            })
        if formatted_notes:
            item["match_notes"] = formatted_notes
        if structured_matches:
            item["matches"] = structured_matches
    if summary_origin == "groq":
        _llm_dbg(
            "player.summary.groq",
            {
                "player": full_name,
                "loan_team": loan_team,
                "paragraphs": week_summary.count("\n\n") + 1,
                "links_used": bool(links),
            },
        )
    else:
        _llm_dbg(
            "player.summary.fallback",
            {
                "player": full_name,
                "loan_team": loan_team,
                "reason": fallback_reason or summary_origin or "template",
                "has_links": bool(links),
            },
        )
    return item


def _compose_team_summary_from_player_items(team_name: str, week_range: list[str] | tuple[str, str], player_items: list[dict[str, Any]]) -> str:
    if not player_items:
        return f"No academy pipeline updates for {team_name} this week."

    start, end = week_range
    sentences: list[str] = []
    for item in player_items:
        summary = (item.get("week_summary") or "").split("\n\n")[0]
        full_name = _strip_text(item.get("player_full_name") or item.get("player_name"))
        display_name = item.get("player_name") or ""
        if summary and full_name:
            if display_name and display_name in summary:
                summary = summary.replace(display_name, full_name, 1)
            sentences.append(_ensure_period(summary))

    key_players = sentences[:3]
    summary_text = f"{team_name} academy pipeline update ({start} to {end}): " + " ".join(key_players)

    total_goals = sum(_to_int(item.get("stats", {}).get("goals")) for item in player_items)
    total_assists = sum(_to_int(item.get("stats", {}).get("assists")) for item in player_items)
    total_minutes = sum(_to_int(item.get("stats", {}).get("minutes")) for item in player_items)

    summary_text += _ensure_period(f" Combined output: {total_goals} {_pluralize(total_goals, 'goal')}, {total_assists} {_pluralize(total_assists, 'assist')} and {total_minutes} {_pluralize(total_minutes, 'minute')}.")
    if ENV_ENABLE_GROQ_SUMMARIES and ENV_ENABLE_GROQ_TEAM_SUMMARIES:
        try:
            try:
                llm_summary = _summarize_team_with_groq(team_name, week_range, player_items, draft_summary=summary_text)
            except TypeError:
                llm_summary = _summarize_team_with_groq(team_name, week_range, player_items)
        except Exception as groq_error:
            _nl_dbg("team-summary-groq-error", str(groq_error))
            llm_summary = ""
        if llm_summary:
            _llm_dbg("team.summary.groq", {"team": team_name, "players": len(player_items)})
            return llm_summary

    fallback_reason = "llm_disabled" if not (ENV_ENABLE_GROQ_SUMMARIES and ENV_ENABLE_GROQ_TEAM_SUMMARIES) else "llm_empty"
    _llm_dbg(
        "team.summary.fallback",
        {
            "team": team_name,
            "players": len(player_items),
            "reason": fallback_reason,
        },
    )
    return summary_text


POSITION_STAT_KEYS = {
    'Forward': ['goals', 'assists', 'shots_total', 'dribbles_success', 'rating'],
    'Midfielder': ['goals', 'assists', 'passes_key', 'tackles_total', 'rating'],
    'Defender': ['tackles_total', 'tackles_interceptions', 'duels_won', 'passes_total', 'rating'],
    'Goalkeeper': ['saves', 'goals_conceded', 'passes_total', 'rating'],
}


def _generate_player_charts(player_api_id: int, player_name: str,
                            week_start, week_end) -> dict:
    """Generate platform data charts for a player's newsletter section.

    Returns a dict of chart file URLs (``/static/charts/...``) keyed by chart
    type.  All errors are swallowed so chart generation never blocks the
    newsletter pipeline.
    """
    try:
        from src.routes.journalist import (
            _fetch_chart_data_for_rendering,
            _get_primary_position,
            _categorize_position,
        )
        from src.services.chart_renderer import save_chart_to_file
    except Exception:
        return {}

    if not player_api_id:
        return {}

    ts = int(datetime.now(timezone.utc).timestamp())
    charts: dict[str, str] = {}

    # Helper: determine position-appropriate stat keys from season data
    position_category = 'Midfielder'  # default
    try:
        season_data = _fetch_chart_data_for_rendering(
            player_api_id, 'stat_table', ['rating'], 'season')
        if season_data and season_data.get('data'):
            pos = _get_primary_position([
                {'stats': row} for row in season_data['data']
            ])
            position_category = _categorize_position(pos)
    except Exception:
        pass

    stat_keys = POSITION_STAT_KEYS.get(position_category, POSITION_STAT_KEYS['Midfielder'])
    ws = week_start.isoformat() if hasattr(week_start, 'isoformat') else str(week_start)
    we = week_end.isoformat() if hasattr(week_end, 'isoformat') else str(week_end)

    # 1. Radar chart (season-level)
    try:
        radar_data = _fetch_chart_data_for_rendering(
            player_api_id, 'radar', stat_keys, 'season')
        if radar_data and radar_data.get('data'):
            fname = f"{player_api_id}_radar_{ts}"
            path = save_chart_to_file('radar', radar_data, fname, width=400, height=400)
            charts['radar_chart_url'] = '/static/charts/' + os.path.basename(path)
    except Exception:
        pass

    # 2. Stat table (week data)
    try:
        table_data = _fetch_chart_data_for_rendering(
            player_api_id, 'stat_table', stat_keys, 'week',
            week_start=ws, week_end=we)
        if table_data and table_data.get('data'):
            fname = f"{player_api_id}_stat_table_{ts}"
            path = save_chart_to_file('stat_table', table_data, fname, width=500, height=250)
            charts['stat_table_url'] = '/static/charts/' + os.path.basename(path)
    except Exception:
        pass

    # 3. Season trend line (rating)
    try:
        trend_data = _fetch_chart_data_for_rendering(
            player_api_id, 'line', ['rating'], 'season')
        if trend_data and trend_data.get('data'):
            fname = f"{player_api_id}_trend_{ts}"
            path = save_chart_to_file('line', trend_data, fname, width=500, height=300)
            charts['trend_chart_url'] = '/static/charts/' + os.path.basename(path)
    except Exception:
        pass

    # 4. Match performance card (week data)
    try:
        card_data = _fetch_chart_data_for_rendering(
            player_api_id, 'match_card', stat_keys, 'week',
            week_start=ws, week_end=we)
        if card_data and card_data.get('fixtures'):
            fname = f"{player_api_id}_match_card_{ts}"
            path = save_chart_to_file('match_card', card_data, fname, width=500, height=200)
            charts['match_card_url'] = '/static/charts/' + os.path.basename(path)
    except Exception:
        pass

    return charts


def _merge_stats_into_item(item: dict, totals: dict | None) -> dict:
    base = dict(totals or {})
    existing = item.get("stats") if isinstance(item.get("stats"), dict) else {}
    base.update(existing)
    item["stats"] = base
    return base


def _impact_score(stats: dict) -> float:
    return (
        _to_int(stats.get("goals")) * 6
        + _to_int(stats.get("assists")) * 4
        + _to_int(stats.get("shots_on")) * 2
        + _to_int(stats.get("shots_total"))
        + _to_int(stats.get("passes_key")) * 2
        + _to_int(stats.get("tackles_total")) * 1.5
        + _to_int(stats.get("duels_won"))
        + (_safe_float(stats.get("rating")) or 0.0)
    )


def _apply_stat_driven_summaries(content: dict, report: dict, brave_ctx: dict) -> dict:
    if not isinstance(content, dict):
        return content
    sections = content.get("sections")
    if not isinstance(sections, list):
        return content

    loanee_lookup: dict[str, dict[str, Any]] = {}
    loanee_lookup_by_id: dict[int, dict[str, Any]] = {}
    for loanee in report.get("loanees") or []:
        if not isinstance(loanee, dict):
            continue
        aliases = [
            loanee.get("player_name"),
            loanee.get("player_full_name"),
            to_initial_last(loanee.get("player_full_name") or ""),
            to_initial_last(loanee.get("player_name") or ""),
        ]
        for alias in filter(None, aliases):
            key = _normalize_player_key(alias)
            if key:
                loanee_lookup.setdefault(key, loanee)
        pid_candidates = [
            loanee.get("player_id"),
            loanee.get("player_api_id"),
        ]
        for candidate in pid_candidates:
            try:
                pid = int(candidate)
            except (TypeError, ValueError):
                continue
            if pid not in loanee_lookup_by_id:
                loanee_lookup_by_id[pid] = loanee

    hits_by_player = _hits_by_player(brave_ctx)
    player_entries: list[dict[str, Any]] = []

    for sec in sections:
        if not isinstance(sec, dict):
            continue
        title = _strip_text(sec.get("title")).lower()
        if title not in ("active loans", "manual player entries"):
            continue
        is_manual_section = title == "manual player entries"
        items = sec.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            original_player_name = _strip_text(item.get("player_name"))
            name_key = _normalize_player_key(original_player_name)

            loanee = None
            canonical_pid = None
            pid_candidates = [item.get("player_id"), item.get("player_api_id")]
            for candidate in pid_candidates:
                try:
                    canonical_pid = int(candidate)
                except (TypeError, ValueError):
                    canonical_pid = None
                    continue
                loanee = loanee_lookup_by_id.get(canonical_pid)
                if loanee:
                    break
            if loanee is None and name_key:
                loanee = loanee_lookup.get(name_key)

            if loanee:
                if canonical_pid is None:
                    pid_source = loanee.get("player_id") or loanee.get("player_api_id")
                    try:
                        canonical_pid = int(pid_source)
                    except (TypeError, ValueError):
                        canonical_pid = None
                    if canonical_pid is not None:
                        item["player_id"] = canonical_pid
                full_name = _strip_text(loanee.get("player_full_name")) or _strip_text(loanee.get("player_name"))
                if full_name:
                    item["player_full_name"] = full_name
                    display = to_initial_last(full_name) or full_name
                    item["player_name"] = display

                if canonical_pid:
                    try:
                        rating_graph = graph_service.generate_player_rating_graph(canonical_pid, item.get("player_name"))
                        if rating_graph:
                            item["rating_graph_url"] = rating_graph
                        minutes_graph = graph_service.generate_player_minutes_graph(canonical_pid, item.get("player_name"))
                        if minutes_graph:
                            item["minutes_graph_url"] = minutes_graph
                    except Exception as e:
                        _nl_dbg(f"Graph generation failed for {canonical_pid}: {e}")

                    # Generate platform data charts (radar, stat table, trend, match card)
                    if item.get("can_fetch_stats", True):
                        try:
                            range_info = report.get("range") or []
                            ws = range_info[0] if len(range_info) > 0 else None
                            we = range_info[1] if len(range_info) > 1 else None
                            if ws and we:
                                charts = _generate_player_charts(
                                    canonical_pid, item.get("player_name"), ws, we)
                                if charts:
                                    item.update(charts)
                        except Exception as e:
                            _nl_dbg(f"Chart generation failed for {canonical_pid}: {e}")

                loan_team_name = _strip_text(loanee.get("loan_team_name"))
                if loan_team_name:
                    item.setdefault("loan_team", loan_team_name)
                    item.setdefault("loan_team_name", loan_team_name)
                loan_team_api_id = loanee.get("loan_team_api_id")
                if loan_team_api_id:
                    item.setdefault("loan_team_api_id", loan_team_api_id)
                loan_team_db_id = loanee.get("loan_team_id")
                if loan_team_db_id:
                    item.setdefault("loan_team_id", loan_team_db_id)

            # Determine canonical tracking flag before merging stats
            if isinstance(loanee, dict):
                can_track = bool(loanee.get("can_fetch_stats", True))
            else:
                can_track = bool(item.get("can_fetch_stats", True))
            item["can_fetch_stats"] = can_track

            totals = loanee.get("totals") if isinstance(loanee, dict) else None
            if can_track and totals:
                stats = _merge_stats_into_item(item, totals)
            else:
                if not can_track:
                    item["stats"] = {}
                stats = item.get("stats") if isinstance(item.get("stats"), dict) else {}
                item["stats"] = stats

            lookup_keys: list[str] = []
            display_key = _normalize_player_key(_strip_text(item.get("player_name")))
            if display_key:
                lookup_keys.append(display_key)
            if name_key and name_key not in lookup_keys:
                lookup_keys.append(name_key)
            if isinstance(loanee, dict):
                loanee_aliases = [
                    _strip_text(loanee.get("player_name")),
                    _strip_text(loanee.get("player_full_name")),
                    to_initial_last(_strip_text(loanee.get("player_name")) or ""),
                    to_initial_last(_strip_text(loanee.get("player_full_name")) or ""),
                ]
                for alias in filter(None, loanee_aliases):
                    alias_key = _normalize_player_key(alias)
                    if alias_key and alias_key not in lookup_keys:
                        lookup_keys.append(alias_key)

            hits: list[dict[str, Any]] = []
            for lk in lookup_keys:
                hits = hits_by_player.get(lk, [])
                if hits:
                    break
            if hits:
                _merge_links_from_hits(item, hits)

            summary_text, headline_text, article_title = _build_player_summary(
                item,
                loanee,
                stats,
                None if is_manual_section else _match_result_phrase(loanee),
                hits,
            )
            if summary_text:
                item["week_summary"] = summary_text
            player_entries.append(
                {
                    "player": item.get("player_name") or (loanee.get("player_name") if isinstance(loanee, dict) else ""),
                    "headline": headline_text,
                    "score": _impact_score(stats),
                    "article_title": article_title,
                }
            )

    if player_entries:
        player_entries.sort(key=lambda entry: entry["score"], reverse=True)
        summary_bits: list[str] = []
        for entry in player_entries[:2]:
            phrase = _strip_text(f"{entry['player']} {entry['headline']}")
            if phrase:
                summary_bits.append(_ensure_period(phrase))
        article_title = next((entry["article_title"] for entry in player_entries if entry.get("article_title")), None)
        if article_title:
            summary_bits.append(f"Coverage spotlight: {article_title}.")
        if summary_bits:
            content["summary"] = " ".join(summary_bits)

    return content


def _monday_range(target: date) -> tuple[date, date]:
    # Monday–Sunday window for weekly issues
    start = target - timedelta(days=target.weekday())
    end = start + timedelta(days=6)
    return start, end

def fetch_pipeline_report_tool(parent_team_db_id: int, season_start_year: int, start: date, end: date) -> Dict[str, Any]:
    """Fetch a grouped report from TrackedPlayer.

    Returns a report dict with:
      - groups.first_team, groups.on_loan, groups.academy  (player dicts)
      - parent_team, season, range, has_tracked_players
    """
    from src.models.weekly import Fixture, FixturePlayerStats

    team = Team.query.get(parent_team_db_id)
    if not team:
        raise ValueError(f"Team DB id {parent_team_db_id} not found")

    api_client.set_season_year(season_start_year)
    api_client._prime_team_cache(season_start_year)

    # Query all currently-signed academy products
    tracked = TrackedPlayer.query.filter(
        TrackedPlayer.team_id == parent_team_db_id,
        TrackedPlayer.is_active.is_(True),
        TrackedPlayer.status.notin_(['released', 'sold']),
    ).all()

    groups: Dict[str, list] = {'first_team': [], 'on_loan': [], 'academy': []}

    # Thresholds for reclassifying first-team players with minimal involvement back to academy
    ACADEMY_THRESHOLD_MINUTES = 200  # ~2 full matches
    ACADEMY_THRESHOLD_APPS = 5

    for tp in tracked:
        # A1: Flag academy products vs bought players (for AI commentary context)
        is_academy_product = True  # default assumption
        if tp.journey_id:
            journey = PlayerJourney.query.get(tp.journey_id)
            if journey and journey.academy_club_ids:
                is_academy_product = team.team_id in (journey.academy_club_ids or [])

        player_dict = {
            'is_academy_product': is_academy_product,
            'player_api_id': tp.player_api_id,
            'player_id': tp.player_api_id,
            'player_name': tp.player_name,
            'player_full_name': tp.player_name,
            'photo_url': tp.photo_url,
            'position': tp.position,
            'nationality': tp.nationality,
            'age': tp.age,
            'pathway_status': tp.status,
            'current_level': tp.current_level,
            'parent_team_name': team.name,
            'parent_team_api_id': team.team_id,
            'can_fetch_stats': tp.data_depth == 'full_stats',
            'journey_id': tp.journey_id,
            'journey_context': derive_journey_context(tp.journey_id, tp.status) if tp.journey_id else None,
        }

        if tp.status == 'on_loan':
            player_dict['loan_team_name'] = tp.current_club_name
            player_dict['loan_team_api_id'] = tp.current_club_api_id
            player_dict['loan_team'] = tp.current_club_name
            # Delegate to existing loan stats pipeline via AcademyPlayer bridge
            if tp.loaned_player_id:
                lp = AcademyPlayer.query.get(tp.loaned_player_id)
                if lp:
                    player_dict['can_fetch_stats'] = bool(lp.can_fetch_stats)
                    player_dict['sofascore_player_id'] = getattr(lp, 'sofascore_player_id', None)
            # Get weekly stats from FixturePlayerStats
            _enrich_on_loan_stats(player_dict, tp, start, end, season_start_year)
            # Fallback: derive loan league from Team record if not set from match data
            if not player_dict.get('loan_league_name') and tp.current_club_api_id:
                loan_team_row = Team.query.filter_by(team_id=tp.current_club_api_id).first()
                if loan_team_row and loan_team_row.league:
                    player_dict['loan_league_name'] = loan_team_row.league.name
            groups['on_loan'].append(player_dict)

        elif tp.status == 'first_team':
            # Enrich first — we need season_totals to decide classification
            _enrich_first_team_stats(player_dict, tp, team, start, end, season_start_year)

            # A2: Reclassify to academy if minimal first-team involvement
            st = player_dict.get('season_totals') or {}
            season_mins = st.get('minutes', 0)
            season_apps = st.get('appearances', 0)

            if season_mins < ACADEMY_THRESHOLD_MINUTES and season_apps < ACADEMY_THRESHOLD_APPS:
                # Academy player with a brief first-team cameo
                player_dict['pathway_status'] = 'academy'
                player_dict['loan_team_name'] = f"{team.name} {tp.current_level or 'Academy'}"
                player_dict['loan_team'] = player_dict['loan_team_name']
                if season_mins > 0:
                    player_dict['first_team_cameo'] = True
                _enrich_academy_stats(player_dict, tp, season_start_year)
                groups['academy'].append(player_dict)
            else:
                player_dict['loan_team_name'] = team.name
                player_dict['loan_team'] = team.name
                player_dict['loan_team_api_id'] = team.team_id
                groups['first_team'].append(player_dict)

        elif tp.status == 'academy':
            player_dict['loan_team_name'] = f"{team.name} {tp.current_level or 'Academy'}"
            player_dict['loan_team'] = player_dict['loan_team_name']
            _enrich_academy_stats(player_dict, tp, season_start_year)
            groups['academy'].append(player_dict)

    has_active = len(tracked) > 0

    report = {
        'parent_team': {'db_id': team.id, 'id': team.team_id, 'name': team.name},
        'season': season_start_year,
        'range': [start.isoformat(), end.isoformat()],
        'has_tracked_players': has_active,
        'groups': groups,
    }
    db.session.commit()
    return report


def _enrich_on_loan_stats(player_dict: dict, tp: "TrackedPlayer", start: date, end: date, season: int) -> None:
    """Enrich an on-loan player dict with weekly FixturePlayerStats."""
    from src.models.weekly import Fixture, FixturePlayerStats
    import logging
    _enrich_logger = logging.getLogger('newsletter.enrich')

    # Guard: skip if player_api_id is missing
    if not tp.player_api_id:
        _enrich_logger.warning(f"[ENRICH-LOAN] player_api_id is null for tp.id={getattr(tp, 'id', '?')} ({tp.player_name})")
        player_dict['totals'] = {}
        player_dict['matches'] = []
        return

    try:
        _enrich_logger.info(f"[ENRICH-LOAN] player={tp.player_api_id} ({tp.player_name}) range={start}..{end}")
        stats_rows = db.session.query(FixturePlayerStats, Fixture).join(
            Fixture, FixturePlayerStats.fixture_id == Fixture.id
        ).filter(
            FixturePlayerStats.player_api_id == tp.player_api_id,
            db.func.date(Fixture.date_utc) >= start,
            db.func.date(Fixture.date_utc) <= end,
        ).all()
        _enrich_logger.info(f"[ENRICH-LOAN] player={tp.player_api_id} found {len(stats_rows)} rows")

        if not stats_rows:
            any_ever = db.session.query(db.func.count(FixturePlayerStats.id)).filter(
                FixturePlayerStats.player_api_id == tp.player_api_id
            ).scalar()
            _enrich_logger.warning(
                f"[ENRICH-LOAN] 0 weekly rows for {tp.player_name} (api_id={tp.player_api_id}) "
                f"in {start}..{end}. Total rows in DB: {any_ever}. "
                f"current_club_api_id={tp.current_club_api_id}"
            )

        totals = {'minutes': 0, 'goals': 0, 'assists': 0, 'yellows': 0, 'reds': 0, 'saves': 0}
        matches = []
        for row, fixture in stats_rows:
            totals['minutes'] += row.minutes or 0
            totals['goals'] += row.goals or 0
            totals['assists'] += row.assists or 0
            totals['yellows'] += row.yellows or 0
            totals['reds'] += row.reds or 0
            totals['saves'] += getattr(row, 'saves', 0) or 0
            if fixture:
                is_home = fixture.home_team_api_id == tp.current_club_api_id
                opp_api_id = fixture.away_team_api_id if is_home else fixture.home_team_api_id
                # Resolve team name from Team table (Fixture model has no name columns)
                opp_team_row = Team.query.filter_by(team_id=opp_api_id).first()
                opp_name = opp_team_row.name if opp_team_row else str(opp_api_id)
                matches.append({
                    'opponent': opp_name,
                    'opponent_id': opp_api_id,
                    'competition': getattr(fixture, 'competition_name', None),
                    'date': fixture.date_utc.isoformat() if fixture.date_utc else None,
                    'home': is_home,
                    'score': {'home': fixture.home_goals, 'away': fixture.away_goals},
                    'played': (row.minutes or 0) > 0,
                    'role': getattr(row, 'role', None),
                    'player': {
                        'position': getattr(row, 'position', None),
                        'goals': row.goals or 0,
                        'assists': row.assists or 0,
                        'minutes': row.minutes or 0,
                    },
                })
        player_dict['totals'] = totals
        player_dict['matches'] = matches
        # Derive loan league name from match competitions for newsletter grouping
        league_names = [m.get('competition') for m in matches if m.get('competition')]
        if league_names:
            from collections import Counter
            player_dict['loan_league_name'] = Counter(league_names).most_common(1)[0][0]

        # Season-level totals for context (full season, no week filter)
        try:
            season_start = date(season, 8, 1)
            season_end = date(season + 1, 6, 30)
            season_rows = db.session.query(FixturePlayerStats).join(
                Fixture, FixturePlayerStats.fixture_id == Fixture.id
            ).filter(
                FixturePlayerStats.player_api_id == tp.player_api_id,
                db.func.date(Fixture.date_utc) >= season_start,
                db.func.date(Fixture.date_utc) <= season_end,
            ).all()
            if season_rows:
                player_dict['season_totals'] = {
                    'minutes': sum(r.minutes or 0 for r in season_rows),
                    'goals': sum(r.goals or 0 for r in season_rows),
                    'assists': sum(r.assists or 0 for r in season_rows),
                    'appearances': sum(1 for r in season_rows if (r.minutes or 0) > 0),
                }
        except Exception:
            pass

        # Wire season_context so _build_player_report_item and Groq get real season data
        if player_dict.get('season_totals'):
            player_dict['season_context'] = {
                'season_stats': player_dict['season_totals'],
            }

    except Exception as e:
        import traceback
        _enrich_logger.error(f"[ENRICH-LOAN] ERROR player={tp.player_api_id}: {e}\n{traceback.format_exc()}")
        player_dict['totals'] = {}
        player_dict['matches'] = []


def _enrich_first_team_stats(player_dict: dict, tp: "TrackedPlayer", team: "Team", start: date, end: date, season: int) -> None:
    """Enrich a first-team player dict with parent club FixturePlayerStats."""
    from src.models.weekly import Fixture, FixturePlayerStats
    import logging
    _enrich_logger = logging.getLogger('newsletter.enrich')

    # Guard: skip if player_api_id is missing
    if not tp.player_api_id:
        _enrich_logger.warning(f"[ENRICH-FT] player_api_id is null for tp.id={getattr(tp, 'id', '?')} ({tp.player_name})")
        player_dict['totals'] = {}
        player_dict['matches'] = []
        return

    try:
        _enrich_logger.info(f"[ENRICH-FT] player={tp.player_api_id} ({tp.player_name}) team_api={team.team_id} range={start}..{end}")
        stats_rows = db.session.query(FixturePlayerStats, Fixture).join(
            Fixture, FixturePlayerStats.fixture_id == Fixture.id
        ).filter(
            FixturePlayerStats.player_api_id == tp.player_api_id,
            db.func.date(Fixture.date_utc) >= start,
            db.func.date(Fixture.date_utc) <= end,
            db.or_(
                Fixture.home_team_api_id == team.team_id,
                Fixture.away_team_api_id == team.team_id,
            ),
        ).all()
        _enrich_logger.info(f"[ENRICH-FT] player={tp.player_api_id} found {len(stats_rows)} rows")

        if not stats_rows:
            any_ever = db.session.query(db.func.count(FixturePlayerStats.id)).filter(
                FixturePlayerStats.player_api_id == tp.player_api_id
            ).scalar()
            _enrich_logger.warning(
                f"[ENRICH-FT] 0 weekly rows for {tp.player_name} (api_id={tp.player_api_id}) "
                f"in {start}..{end}. Total rows in DB: {any_ever}."
            )

        totals = {'minutes': 0, 'goals': 0, 'assists': 0, 'yellows': 0, 'reds': 0, 'saves': 0}
        matches = []
        for row, fixture in stats_rows:
            totals['minutes'] += row.minutes or 0
            totals['goals'] += row.goals or 0
            totals['assists'] += row.assists or 0
            totals['yellows'] += row.yellows or 0
            totals['reds'] += row.reds or 0
            totals['saves'] += getattr(row, 'saves', 0) or 0
            if fixture:
                is_home = fixture.home_team_api_id == team.team_id
                opp_api_id = fixture.away_team_api_id if is_home else fixture.home_team_api_id
                opp_team_row = Team.query.filter_by(team_id=opp_api_id).first()
                opp_name = opp_team_row.name if opp_team_row else str(opp_api_id)
                matches.append({
                    'opponent': opp_name,
                    'opponent_id': opp_api_id,
                    'competition': getattr(fixture, 'competition_name', None),
                    'date': fixture.date_utc.isoformat() if fixture.date_utc else None,
                    'home': is_home,
                    'score': {'home': fixture.home_goals, 'away': fixture.away_goals},
                    'played': (row.minutes or 0) > 0,
                    'role': getattr(row, 'role', None),
                    'player': {
                        'position': getattr(row, 'position', None),
                        'goals': row.goals or 0,
                        'assists': row.assists or 0,
                        'minutes': row.minutes or 0,
                    },
                })
        player_dict['totals'] = totals
        player_dict['matches'] = matches
    except Exception as e:
        _nl_dbg('_enrich_first_team_stats error:', str(e))
        player_dict['totals'] = {}
        player_dict['matches'] = []

    # Season-level stats from journey entries — stored separately, never overwrites weekly totals
    if tp.journey_id:
        try:
            entries = PlayerJourneyEntry.query.filter(
                PlayerJourneyEntry.journey_id == tp.journey_id,
                PlayerJourneyEntry.season == season,
                PlayerJourneyEntry.entry_type == 'first_team',
            ).all()
            if entries:
                player_dict['season_totals'] = {
                    'minutes': sum(e.minutes or 0 for e in entries),
                    'goals': sum(e.goals or 0 for e in entries),
                    'assists': sum(e.assists or 0 for e in entries),
                    'appearances': sum(1 for e in entries if (e.minutes or 0) > 0),
                }
        except Exception:
            pass

    # Wire season_context so _build_player_report_item and Groq get real season data
    if player_dict.get('season_totals'):
        player_dict['season_context'] = {
            'season_stats': player_dict['season_totals'],
        }


def _enrich_academy_stats(player_dict: dict, tp: "TrackedPlayer", season: int) -> None:
    """Enrich an academy player dict with stats.

    Tries FixturePlayerStats first (youth team fixtures synced from API-Football).
    Falls back to PlayerJourneyEntry season totals if no fixture data available.
    """
    from src.models.weekly import Fixture, FixturePlayerStats

    player_dict['totals'] = {'minutes': 0, 'goals': 0, 'assists': 0, 'yellows': 0, 'reds': 0, 'saves': 0}
    player_dict['matches'] = []
    player_dict['_stats_source'] = 'academy_season'

    # Try FixturePlayerStats first (match-level data from youth fixture sync)
    if tp.player_api_id:
        try:
            season_start = date(season, 8, 1)
            season_end = date(season + 1, 6, 30)
            stats_rows = db.session.query(FixturePlayerStats, Fixture).join(
                Fixture, FixturePlayerStats.fixture_id == Fixture.id
            ).filter(
                FixturePlayerStats.player_api_id == tp.player_api_id,
                db.func.date(Fixture.date_utc) >= season_start,
                db.func.date(Fixture.date_utc) <= season_end,
            ).all()

            if stats_rows:
                totals = {'minutes': 0, 'goals': 0, 'assists': 0, 'yellows': 0, 'reds': 0, 'saves': 0}
                matches = []
                for row, fixture in stats_rows:
                    totals['minutes'] += row.minutes or 0
                    totals['goals'] += row.goals or 0
                    totals['assists'] += row.assists or 0
                    totals['yellows'] += row.yellows or 0
                    totals['reds'] += row.reds or 0
                    totals['saves'] += getattr(row, 'saves', 0) or 0
                    if fixture:
                        matches.append({
                            'competition': getattr(fixture, 'competition_name', None),
                            'date': fixture.date_utc.isoformat() if fixture.date_utc else None,
                            'played': (row.minutes or 0) > 0,
                            'role': getattr(row, 'role', None),
                            'player': {
                                'position': getattr(row, 'position', None),
                                'goals': row.goals or 0,
                                'assists': row.assists or 0,
                                'minutes': row.minutes or 0,
                            },
                        })
                player_dict['season_totals'] = {
                    'minutes': totals['minutes'],
                    'goals': totals['goals'],
                    'assists': totals['assists'],
                    'appearances': sum(1 for r, _ in stats_rows if (r.minutes or 0) > 0),
                }
                player_dict['_stats_source'] = 'fixture_stats'
                if player_dict.get('season_totals'):
                    player_dict['season_context'] = {
                        'season_stats': player_dict['season_totals'],
                    }
                return
        except Exception as e:
            _nl_dbg('_enrich_academy_stats fixture query error:', str(e))

    # Fallback: season totals from PlayerJourneyEntry
    if not tp.journey_id:
        return

    try:
        entries = PlayerJourneyEntry.query.filter(
            PlayerJourneyEntry.journey_id == tp.journey_id,
            PlayerJourneyEntry.season == season,
            PlayerJourneyEntry.is_youth.is_(True),
        ).all()
        if entries:
            player_dict['season_totals'] = {
                'minutes': sum(e.minutes or 0 for e in entries),
                'goals': sum(e.goals or 0 for e in entries),
                'assists': sum(e.assists or 0 for e in entries),
                'appearances': sum(1 for e in entries if (e.minutes or 0) > 0),
            }
            if player_dict.get('season_totals'):
                player_dict['season_context'] = {
                    'season_stats': player_dict['season_totals'],
                }
    except Exception as e:
        _nl_dbg('_enrich_academy_stats error:', str(e))


def _build_first_team_report_item(player: dict, hits: list[dict[str, Any]], *, week_start: date, week_end: date) -> dict:
    """Build a report item for a first-team graduate. Same dict shape as loan items."""
    display_name = to_initial_last(_strip_text(player.get("player_full_name")) or _strip_text(player.get("player_name"))) or _strip_text(player.get("player_name")) or ""
    full_name = _strip_text(player.get("player_full_name")) or display_name
    parent_team = _strip_text(player.get("parent_team_name") or player.get("loan_team") or "the first team")
    stats_src = player.get("totals") or {}

    stats: dict[str, Any] = {
        "minutes": _to_int(stats_src.get("minutes")),
        "goals": _to_int(stats_src.get("goals")),
        "assists": _to_int(stats_src.get("assists")),
        "yellows": _to_int(stats_src.get("yellows")),
        "reds": _to_int(stats_src.get("reds")),
    }
    for key, value in (stats_src or {}).items():
        if key in stats and stats[key]:
            continue
        stats[key] = value

    minutes = _to_int(stats.get("minutes"))
    matches = player.get("matches") if isinstance(player, dict) else []
    match_count = len(matches or [])
    links = _build_links_from_hits(hits)
    paragraphs: list[str] = []

    if minutes > 0:
        if match_count > 1:
            action = f"made {match_count} appearances for {parent_team}, playing {minutes} minutes"
        else:
            action = f"featured for {parent_team}, logging {minutes} minutes"
        stat_phrases = _stat_highlights(stats_src)
        sentence = f"{display_name} {action}"
        if stat_phrases:
            sentence += f", finishing with {_combine_phrases(stat_phrases)}"
        paragraphs.append(_ensure_period(sentence))
    elif minutes == 0 and match_count > 0:
        paragraphs.append(_ensure_period(f"{display_name} was in the matchday squad for {parent_team} but did not feature"))
    else:
        paragraphs.append(_ensure_period(f"{display_name} did not feature for {parent_team} this week"))

    # Add season context from season_totals if available
    season_totals = player.get("season_totals")
    if season_totals and season_totals.get("minutes", 0) > 0:
        st_mins = season_totals['minutes']
        st_goals = season_totals.get('goals', 0)
        st_assists = season_totals.get('assists', 0)
        st_apps = season_totals.get('appearances', 0)
        season_parts = [f"{st_mins} minutes"]
        if st_apps:
            season_parts[0] = f"{st_apps} appearances ({st_mins} minutes)"
        if st_goals:
            season_parts.append(f"{st_goals} {_pluralize(st_goals, 'goal')}")
        if st_assists:
            season_parts.append(f"{st_assists} {_pluralize(st_assists, 'assist')}")
        paragraphs.append(_ensure_period(f"Season to date: {', '.join(season_parts)}"))

    journey_ctx = player.get("journey_context")
    if journey_ctx:
        paragraphs.append(_ensure_period(journey_ctx))

    week_summary = "\n\n".join(paragraphs)
    if links:
        week_summary += "\n\n" + _ensure_period(f"Latest coverage: {links[0]['title']}")

    item: dict[str, Any] = {
        "player_name": display_name or full_name,
        "player_full_name": full_name,
        "loan_team": parent_team,
        "loan_team_name": parent_team,
        "player_id": player.get("player_api_id") or player.get("player_id"),
        "player_api_id": player.get("player_api_id"),
        "loan_team_api_id": player.get("parent_team_api_id"),
        "can_fetch_stats": player.get("can_fetch_stats", True),
        "pathway_status": "first_team",
        "stats": stats,
        "season_totals": player.get("season_totals"),
        "week_summary": week_summary,
        "links": links,
        "matches": _format_matches_for_item(matches),
    }
    return item


def _build_academy_report_item(player: dict, hits: list[dict[str, Any]], *, week_start: date, week_end: date) -> dict:
    """Build a lightweight report item for an academy player (season-level stats)."""
    display_name = to_initial_last(_strip_text(player.get("player_full_name")) or _strip_text(player.get("player_name"))) or _strip_text(player.get("player_name")) or ""
    full_name = _strip_text(player.get("player_full_name")) or display_name
    level = player.get("current_level") or "Academy"
    parent_team = _strip_text(player.get("parent_team_name") or "the academy")
    stats_src = player.get("totals") or {}

    stats: dict[str, Any] = {
        "minutes": _to_int(stats_src.get("minutes")),
        "goals": _to_int(stats_src.get("goals")),
        "assists": _to_int(stats_src.get("assists")),
        "yellows": _to_int(stats_src.get("yellows")),
        "reds": _to_int(stats_src.get("reds")),
    }

    # Academy stats are season-level — use season_totals for context
    season_totals = player.get("season_totals") or {}
    paragraphs: list[str] = []

    st_mins = _to_int(season_totals.get("minutes"))
    if st_mins > 0:
        sentence = f"{display_name} ({level}) — {st_mins} minutes this season at {parent_team}"
        goals = _to_int(season_totals.get("goals"))
        assists = _to_int(season_totals.get("assists"))
        if goals or assists:
            sentence += f" with {goals}G {assists}A"
        paragraphs.append(_ensure_period(sentence))
    else:
        paragraphs.append(_ensure_period(f"{display_name} ({level}) is progressing through the {parent_team} academy"))

    journey_ctx = player.get("journey_context")
    if journey_ctx:
        paragraphs.append(_ensure_period(journey_ctx))

    links = _build_links_from_hits(hits)
    week_summary = "\n\n".join(paragraphs)

    item: dict[str, Any] = {
        "player_name": display_name or full_name,
        "player_full_name": full_name,
        "loan_team": f"{parent_team} {level}",
        "loan_team_name": f"{parent_team} {level}",
        "player_id": player.get("player_api_id") or player.get("player_id"),
        "player_api_id": player.get("player_api_id"),
        "can_fetch_stats": False,  # Academy stats are season-level only
        "pathway_status": "academy",
        "current_level": level,
        "stats": stats,
        "week_summary": week_summary,
        "links": links,
        "matches": [],
    }
    return item


def _format_matches_for_item(matches: list | None) -> list[dict]:
    """Format raw match dicts for inclusion in a report item."""
    if not matches:
        return []
    formatted = []
    for match in (matches or [])[:3]:
        if not isinstance(match, dict):
            continue
        player_stats = match.get("player") or {}
        formatted.append({
            "opponent": match.get("opponent"),
            "opponent_id": match.get("opponent_id"),
            "opponent_logo": match.get("opponent_logo"),
            "competition": match.get("competition"),
            "date": match.get("date"),
            "home": match.get("home"),
            "score": match.get("score"),
            "result": match.get("result"),
            "played": match.get("played"),
            "role": match.get("role"),
            "position": player_stats.get("position"),
            "goals": player_stats.get("goals", 0),
            "assists": player_stats.get("assists", 0),
            "minutes": player_stats.get("minutes", 0),
        })
    return formatted


def brave_context_for_team_and_loans(team_name: str, report: Dict[str, Any], *, default_loc: Dict[str, str]) -> Dict[str, List[Dict[str, Any]]]:
    # Build a small set of targeted queries for context enrichment.
    # We avoid embedding date ranges inside the query text and rely on the
    # Brave API 'freshness' parameter, then strictly post-filter by date.
    start, end = report["range"]  # ISO strings
    queries = set()

    safe_team = f'"{team_name}"'
    queries.add(f"{safe_team} academy pipeline")
    queries.add(f"{safe_team} youth players")

    groups = report.get("groups", {})

    q_meta: Dict[str, Dict[str, str]] = {}
    flags = _get_flags()
    soft_rank = flags['soft_rank']
    site_boost = flags['site_boost']
    use_cup_syns = flags['cup_synonyms']
    strict_range = flags['strict_range']

    # Search for on_loan + first_team players (skip academy — minimal web coverage)
    search_players = groups.get("on_loan", []) + groups.get("first_team", [])

    for loanee in search_players:
        pname = _strip_text(loanee.get("player_name"))
        loan_team = _strip_text(loanee.get("loan_team_name"))
        loan_country = _strip_text(loanee.get("loan_team_country"))
        loan_team_api_id = loanee.get("loan_team_api_id") or loanee.get("loan_team_id")
        if not pname or not loan_team:
            continue
        p = f'"{pname}"'
        lt = f'"{loan_team}"'
        # Core weekly query per loanee
        base_qs = [f"{p} {lt} match report", f"{p} {lt} performance"]
        for bq in base_qs:
            queries.add(bq)
            q_meta[bq] = {
                "player": pname,
                "loan_team": loan_team,
                "loan_team_country": loan_country,
                "loan_team_api_id": loan_team_api_id,
            }
        # Match-specific queries
        for m in loanee.get("matches", []):
            opponent = _strip_text(m.get("opponent"))
            comp = _strip_text(m.get("competition"))
            if opponent:
                o = f'"{opponent}"'
                if comp:
                    terms = expand_competition_terms(comp, use_synonyms=use_cup_syns)[:2]  # cap to 2 synonyms
                    if terms:
                        for t in terms:
                            c = f'"{t}"'
                            q = f"{p} {lt} {o} {c}"
                            queries.add(q)
                            q_meta[q] = {
                                "player": pname,
                                "loan_team": loan_team,
                                "opponent": opponent,
                                "loan_team_country": loan_country,
                                "loan_team_api_id": loan_team_api_id,
                            }
                    else:
                        q = f"{p} {lt} {o}"
                        queries.add(q)
                        q_meta[q] = {
                            "player": pname,
                            "loan_team": loan_team,
                            "opponent": opponent,
                            "loan_team_country": loan_country,
                            "loan_team_api_id": loan_team_api_id,
                        }
                else:
                    q = f"{p} {lt} {o}"
                    queries.add(q)
                    q_meta[q] = {
                        "player": pname,
                        "loan_team": loan_team,
                        "opponent": opponent,
                        "loan_team_country": loan_country,
                        "loan_team_api_id": loan_team_api_id,
                    }

    results: Dict[str, List[Dict[str, Any]]] = {}
    _nl_dbg(f"Brave context week start={start} end={end} players={len(search_players)} queries={len(queries)}")

    loc_cache: Dict[str, Dict[str, str]] = {}

    def _loc_for_meta(meta: Dict[str, Any]) -> Dict[str, str]:
        key = (meta.get("loan_team_country") or "").upper()
        if key:
            if key not in loc_cache:
                loc_cache[key] = resolve_localization_for_country(key, default=default_loc)
            return loc_cache[key]

        api_id = meta.get("loan_team_api_id")
        fallback_key = None
        if api_id:
            try:
                team = Team.query.filter(Team.team_id == int(api_id)).order_by(Team.updated_at.desc()).first()
                if team and getattr(team, 'country', None):
                    fallback_key = team.country.upper()
            except Exception:
                fallback_key = None

        if not fallback_key:
            fallback_key = ''

        if fallback_key not in loc_cache:
            loc_cache[fallback_key] = resolve_localization_for_country(fallback_key or None, default=default_loc)
        return loc_cache[fallback_key]

    # First pass: use Brave freshness window; strictness controlled by admin flag
    for q in queries:
        try:
            _nl_dbg(f"Searching (freshness, strict={strict_range}):", q)
            meta = q_meta.get(q, {})
            locale = _loc_for_meta(meta)
            hits = brave_search(query=q, since=start, until=end, count=8, strict_range=strict_range,
                                country=locale["country"], search_lang=locale["search_lang"], ui_lang=locale["ui_lang"])
            # Optional site boost: add 1–2 site‑scoped queries for better local coverage
            if site_boost:
                for site in SITE_BOOSTS_BY_COUNTRY.get(default_loc["country"], [])[:2]:
                    q_site = f"{q} site:{site}"
                    _nl_dbg("  Boost site query:", q_site)
                    extra = brave_search(query=q_site, since=start, until=end, count=6, strict_range=strict_range,
                                         country=locale["country"], search_lang=locale["search_lang"], ui_lang=locale["ui_lang"])
                    hits.extend(extra)

            # Gentle post-filter and soft ranking per query if enabled
            player_last = _strip_diacritics((meta.get("player") or "").split(" ")[-1]).lower()
            team_l = _strip_diacritics(meta.get("loan_team") or "").lower()
            opponent = meta.get("opponent")

            # Gentle filter
            filtered_hits = []
            for h in hits:
                try:
                    ok = _gentle_filter(h, player_last, team_l)
                except Exception:
                    ok = True
                if ok:
                    filtered_hits.append(h)

            # Soft rank
            if soft_rank:
                try:
                    filtered_hits.sort(key=lambda h: _score_hit(h, player_last, team_l, opponent, locale["country"], site_boost), reverse=True)
                    # Log top picks rationale
                    for h in filtered_hits[:2]:
                        sc = _score_hit(h, player_last, team_l, opponent, locale["country"], site_boost)
                        _nl_dbg("   rank pick:", meta.get("player"), sc, h.get("url"))
                except Exception:
                    pass

            hits = filtered_hits
            _nl_dbg(" -> hits:", len(hits))
            results[q] = hits[:5]
        except Exception as e:
            results[q] = []
            _nl_dbg(" -> error, recorded 0 hits", str(e))

    # If we got absolutely nothing, fallback to no date window (revert to prior behavior)
    try:
        total = sum(len(v) for v in results.values())
    except Exception:
        total = 0
    if total == 0 and not strict_range:
        _nl_dbg("No hits with freshness; falling back to open search")
        for q in queries:
            try:
                _nl_dbg("Searching (open):", q)
                meta = q_meta.get(q, {})
                locale = _loc_for_meta(meta)
                hits = brave_search(query=q, since="", until="", count=8, strict_range=False,
                                     country=locale["country"], search_lang=locale["search_lang"], ui_lang=locale["ui_lang"])
                _nl_dbg(" -> hits:", len(hits))
                results[q] = hits[:5]
            except Exception as e:
                results[q] = []
                _nl_dbg(" -> error, recorded 0 hits (open)", str(e))

    try:
        total = sum(len(v) for v in results.values())
        _nl_dbg("Brave total hits:", total)
    except Exception:
        total = 0

    # Optional: verify URLs resolve before passing to the LLM
    if ENV_CHECK_LINKS and total:
        try:
            # Collect unique URLs
            url_set = set()
            for arr in results.values():
                for h in arr:
                    u = _strip_text(h.get("url"))
                    if u:
                        url_set.add(u)

            ok_map = _check_urls_batch(list(url_set), timeout=LINK_TIMEOUT_SEC, max_workers=LINK_MAX_WORKERS)
            ok_urls = {u for u, ok in ok_map.items() if ok}
            _nl_dbg("Link check:", f"ok={len(ok_urls)} / total={len(url_set)}")

            # Filter per-query hits based on ok_urls
            for q, arr in list(results.items()):
                filtered = []
                for h in (arr or []):
                    url_value = _strip_text(h.get("url"))
                    if url_value and url_value in ok_urls:
                        filtered.append(h)
                if len(filtered) != len(arr or []):
                    _nl_dbg("Pruned dead links for query:", q, f"{len(arr or [])}->{len(filtered)}")
                results[q] = filtered
        except Exception as e:
            _nl_dbg("Link check failed:", str(e))

    return results

# ---- URL validation helpers ----
def _normalize_url(u: str) -> str:
    try:
        p = urlparse(u)
        # Lowercase host, drop fragment
        netloc = (p.netloc or "").lower()
        return urlunparse((p.scheme, netloc, p.path or "", p.params or "", p.query or "", ""))
    except Exception:
        return u

def _url_ok(u: str, *, timeout: float = 6.0) -> bool:
    if not u or not isinstance(u, str):
        return False
    try:
        # Try HEAD first
        r = requests.head(u, allow_redirects=True, timeout=timeout)
        if 200 <= r.status_code < 400:
            return True
        # Some hosts reject HEAD; try a lightweight GET
        if r.status_code in (401, 403, 405, 501):
            r2 = requests.get(u, allow_redirects=True, timeout=timeout, stream=True)
            try:
                return 200 <= r2.status_code < 400
            finally:
                try:
                    r2.close()
                except Exception:
                    pass
        return False
    except Exception:
        return False

def _check_urls_batch(urls: list[str], *, timeout: float = 6.0, max_workers: int = 8) -> dict[str, bool]:
    out: dict[str, bool] = {}
    if not urls:
        return out
    # Normalize and dedupe
    norm_map = {u: _normalize_url(u) for u in urls if u}
    uniq = list(set(norm_map.values()))
    # Map normalized back to original for stable keys
    rev_map: dict[str, list[str]] = {}
    for orig, norm in norm_map.items():
        rev_map.setdefault(norm, []).append(orig)
    try:
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {ex.submit(_url_ok, nu, timeout=timeout): nu for nu in uniq}
            for fut in as_completed(futs):
                nu = futs[fut]
                ok = False
                try:
                    ok = bool(fut.result())
                except Exception:
                    ok = False
                # Assign result to all originals that normalize to this URL
                for orig in rev_map.get(nu, [nu]):
                    out[orig] = ok
    except Exception:
        # Best-effort fallback: sequential
        for nu in uniq:
            ok = _url_ok(nu, timeout=timeout)
            for orig in rev_map.get(nu, [nu]):
                out[orig] = ok
    return out


def _sanitize_links_in_content(obj: dict) -> dict:
    """
    Traverse the newsletter content and remove broken links. Keeps at most
    LINKS_MAX_PER_ITEM per section item. Supports both string links and
    objects with {title, url}.
    """
    if not isinstance(obj, dict):
        return obj

    # Collect all candidate URLs
    urls: list[str] = []
    sections = obj.get("sections") if isinstance(obj.get("sections"), list) else []
    for sec in sections:
        items = sec.get("items") if isinstance(sec, dict) and isinstance(sec.get("items"), list) else []
        for it in items:
            links = it.get("links") if isinstance(it, dict) else None
            if not isinstance(links, list):
                continue
            for l in links:
                if isinstance(l, str):
                    if l:
                        urls.append(l)
                elif isinstance(l, dict):
                    u = l.get("url")
                    if u:
                        urls.append(u)

    ok_map = _check_urls_batch(list(set(urls)), timeout=LINK_TIMEOUT_SEC, max_workers=LINK_MAX_WORKERS) if urls else {}

    # Rebuild links per item with only OK URLs
    pruned_count = 0
    for sec in sections:
        items = sec.get("items") if isinstance(sec, dict) and isinstance(sec.get("items"), list) else []
        for it in items:
            links = it.get("links") if isinstance(it, dict) else None
            if not isinstance(links, list):
                continue
            kept: list = []
            for l in links:
                if len(kept) >= LINKS_MAX_PER_ITEM:
                    break
                if isinstance(l, str):
                    ok = ok_map.get(l, False)
                    if ok:
                        kept.append(l)
                    else:
                        pruned_count += 1
                elif isinstance(l, dict):
                    u = l.get("url")
                    if u and ok_map.get(u, False):
                        kept.append(l)
                    else:
                        pruned_count += 1
                else:
                    pruned_count += 1
            it["links"] = kept

    try:
        _nl_dbg("final-link-sanitize:", f"checked={len(ok_map)} pruned={pruned_count}")
    except Exception:
        pass
    return obj

def persist_newsletter(team_db_id: int, content_json_str: str, week_start: date, week_end: date, issue_date: date, newsletter_type: str = "weekly") -> Newsletter:
    # Reset any prior failed transaction to avoid InFailedSqlTransaction
    try:
        db.session.rollback()
    except Exception:
        pass

    parsed = json.loads(content_json_str)
    title = parsed.get("title") or "Academy Pipeline Update"

    # Get team info for rendering
    team = Team.query.get(team_db_id)
    team_name = team.name if team else None

    # Log sample stats before rendering
    try:
        sections = parsed.get('sections', [])
        if sections:
            first_section = sections[0]
            items = first_section.get('items', [])
            if items:
                first_item = items[0]
                stats_snapshot = {
                    "player": first_item.get('player_name'),
                    "stats_keys": list(first_item.get('stats', {}).keys()),
                    "position": first_item.get('stats', {}).get('position'),
                    "rating": first_item.get('stats', {}).get('rating'),
                    "shots": first_item.get('stats', {}).get('shots_total'),
                    "passes": first_item.get('stats', {}).get('passes_total'),
                }
                _nl_dbg("[persist_newsletter] sample_item_stats", stats_snapshot)
    except Exception as e:
        _nl_dbg("[persist_newsletter] sample_item_stats_error", str(e))

    # Render and embed variants (web_html, email_html, text) for convenience
    try:
        _nl_dbg("[persist_newsletter] rendering_variants", {"team": team_name})
        variants = _render_variants(parsed, team_name)
        web_html = variants.get('web_html', '') or ''
        render_meta = {
            "web_html_len": len(web_html),
            "email_html_len": len(variants.get('email_html', '') or ''),
            "has_expanded_stats": any(token in web_html for token in ("Shots", "Saves", "Key Passes")),
        }
        _nl_dbg("[persist_newsletter] rendered_variants", render_meta)
        parsed['rendered'] = variants
        content_json_str = json.dumps(parsed, ensure_ascii=False)
    except Exception as e:
        # Non-fatal; continue without rendered variants
        _nl_dbg("[persist_newsletter] render_variants_error", str(e))
        import traceback
        traceback.print_exc()
        pass

    now = datetime.now(timezone.utc)
    placeholder_slug = f"tmp-{uuid.uuid4().hex}"
    newsletter = Newsletter(
        team_id=team_db_id,
        newsletter_type=newsletter_type,
        title=title,
        content=content_json_str,           # store JSON with rendered variants
        structured_content=content_json_str,
        public_slug=placeholder_slug,
        week_start_date=week_start,
        week_end_date=week_end,
        issue_date=issue_date,
        generated_date=now,
        # Leave unpublished by default so it can be reviewed/approved
        published=False,
        published_date=None,
    )
    db.session.add(newsletter)
    try:
        db.session.flush()
        team_name_for_slug = team_name or (newsletter.team.name if newsletter.team else None)
        newsletter.public_slug = compose_newsletter_public_slug(
            team_name=team_name_for_slug,
            newsletter_type=newsletter.newsletter_type,
            week_start=newsletter.week_start_date,
            week_end=newsletter.week_end_date,
            issue_date=newsletter.issue_date,
            identifier=newsletter.id,
        )
        db.session.commit()
    except Exception:
        # Ensure session usable for subsequent requests
        db.session.rollback()
        raise
    return newsletter

def compose_team_weekly_newsletter(team_db_id: int, target_date: date, force_refresh: bool = False) -> dict:
    """Compose (but do not persist) a weekly newsletter.
    Returns a dict with keys: content_json (str), week_start (date), week_end (date), season_start_year (int).
    """
    # Compute week window
    week_start, week_end = _monday_range(target_date)

    # Derive season from the week we are processing (European season starts Aug 1)
    season_start_year = week_start.year if week_start.month >= 8 else week_start.year - 1
    
    if force_refresh:
        api_client.clear_stats_cache(season=season_start_year)
        
    api_client.set_season_year(season_start_year)
    try:
        # Log current season view on the client after setting
        _nl_dbg(
            "Season inference:",
            {
                "target_date": target_date.isoformat(),
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
                "season_start_year": season_start_year,
                "api_client.current_season": getattr(api_client, "current_season", None),
                "api_client.current_season_start_year": getattr(api_client, "current_season_start_year", None),
                "api_client.current_season_end_year": getattr(api_client, "current_season_end_year", None),
            }
        )
    except Exception:
        pass
    api_client._prime_team_cache(season_start_year)

    # Fetch report via pipeline tool
    _nl_dbg("Compose for team:", team_db_id, "week:", week_start, week_end, "season:", season_start_year)
    report = fetch_pipeline_report_tool(team_db_id, season_start_year, week_start, week_end)
    try:
        _nl_dbg(
            "Report summary:",
            {
                "report.season": report.get("season"),
                "report.range": report.get("range"),
                "has_tracked_players": report.get("has_tracked_players"),
            }
        )
    except Exception:
        pass

    has_any_players = report.get("has_tracked_players", False)
    groups = report.get("groups", {})
    if not has_any_players:
        _llm_dbg(
            "compose.empty",
            {
                "team_db_id": team_db_id,
                "week_start": week_start.isoformat(),
                "week_end": week_end.isoformat(),
            },
        )
    else:
        _llm_dbg(
            "compose.start",
            {
                "team_db_id": team_db_id,
                "tracked_players": sum(len(v) for v in groups.values()),
                "groq_enabled": ENV_ENABLE_GROQ_SUMMARIES,
            },
        )

    # Build player lookup to help post-processing attach player_id + sofascore ids later
    player_lookup: dict[str, list[dict[str, Any]]] = {}
    player_meta_by_pid: dict[int, dict[str, Any]] = {}
    player_meta_by_key: dict[str, dict[str, Any]] = {}

    def _register_alias(alias: str | None, entry: dict[str, Any]) -> None:
        if not alias:
            return
        key = _normalize_player_key(alias)
        if not key:
            return
        player_lookup.setdefault(key, []).append(entry)

    def _register_meta(alias: str | None, meta: dict[str, Any]) -> None:
        if not alias:
            return
        key = _normalize_player_key(alias)
        if not key:
            return
        player_meta_by_key[key] = meta

    all_players = groups.get("on_loan", []) + groups.get("first_team", []) + groups.get("academy", [])

    player_items: list[dict[str, Any]] = []
    first_team_items: list[dict[str, Any]] = []
    on_loan_items: list[dict[str, Any]] = []
    academy_items: list[dict[str, Any]] = []
    brave_ctx: dict[str, Any] = {}

    if has_any_players:
        for player in all_players:
            pid = player.get("player_api_id") or player.get("player_id")
            entry = None
            if pid:
                entry = {
                    "player_id": int(pid),
                    "loan_team_api_id": player.get("loan_team_api_id") or player.get("loan_team_id"),
                    "loan_team_id": player.get("loan_team_db_id") or player.get("loan_team_id"),
                    "loan_team_name": player.get("loan_team_name") or player.get("loan_team"),
                }
            meta_entry = {
                "can_fetch_stats": bool(player.get("can_fetch_stats", True)),
                "sofascore_player_id": player.get("sofascore_player_id"),
            }
            if pid:
                try:
                    player_meta_by_pid[int(pid)] = meta_entry
                except Exception:
                    pass
            primary_name = player.get("player_name") or player.get("name")
            full_name = player.get("player_full_name")
            display = to_initial_last(primary_name or full_name or "")
            if entry:
                _register_alias(primary_name, entry)
                _register_alias(full_name, entry)
                if display and display != primary_name:
                    _register_alias(display, entry)
                if full_name:
                    alt = to_initial_last(full_name)
                    if alt and alt != display:
                        _register_alias(alt, entry)
            for alias in filter(None, [primary_name, full_name, display, to_initial_last(full_name or primary_name or "")]):
                _register_meta(alias, meta_entry)

        _set_latest_player_lookup(player_lookup)

        # Brave context
        brave_ctx = brave_context_for_team_and_loans(report["parent_team"]["name"], report, default_loc=LOCALIZATION_DEFAULT)
        try:
            total_links = sum(len(v) for v in brave_ctx.values())
            _nl_dbg("Search contexts:", len(brave_ctx), "total links:", total_links)
        except Exception:
            pass

        hits_by_player = _hits_by_player(brave_ctx)

        # Build items per group using the appropriate builder
        for player in groups.get("on_loan", []):
            hits = _extract_hits_for_loanee(player, hits_by_player)
            item = _build_player_report_item(player, hits, week_start=week_start, week_end=week_end)
            item["pathway_status"] = "on_loan"
            # Generate platform data charts for players with stats coverage
            if item.get("can_fetch_stats") and item.get("player_id"):
                try:
                    charts = _generate_player_charts(
                        item["player_id"], item.get("player_name"),
                        week_start, week_end)
                    if charts:
                        item.update(charts)
                except Exception as e:
                    _nl_dbg(f"Chart generation failed for {item.get('player_id')}: {e}")
            on_loan_items.append(item)

        for player in groups.get("first_team", []):
            hits = _extract_hits_for_loanee(player, hits_by_player)
            item = _build_first_team_report_item(player, hits, week_start=week_start, week_end=week_end)
            # Generate platform data charts for first-team players with stats
            if item.get("can_fetch_stats") and item.get("player_id"):
                try:
                    charts = _generate_player_charts(
                        item["player_id"], item.get("player_name"),
                        week_start, week_end)
                    if charts:
                        item.update(charts)
                except Exception as e:
                    _nl_dbg(f"Chart generation failed for {item.get('player_id')}: {e}")
            first_team_items.append(item)

        for player in groups.get("academy", []):
            hits = _extract_hits_for_loanee(player, hits_by_player)
            item = _build_academy_report_item(player, hits, week_start=week_start, week_end=week_end)
            academy_items.append(item)

        # Flat list for summary generation and post-processing
        player_items = first_team_items + on_loan_items + academy_items

        missing_summaries = sum(1 for item in player_items if not _strip_text(item.get("week_summary")))
        _nl_dbg(
            "compose.player_items",
            {
                "player_items": len(player_items),
                "missing_summaries": missing_summaries,
            },
        )
        if missing_summaries:
            _llm_dbg(
                "player.summary.empty_count",
                {
                    "team_db_id": team_db_id,
                    "count": missing_summaries,
                },
            )
    else:
        _set_latest_player_lookup({})

    team_name = report.get("parent_team", {}).get("name") or "Academy Pipeline"
    range_window = report.get("range") or [week_start.isoformat(), week_end.isoformat()]
    summary_text = _compose_team_summary_from_player_items(team_name, range_window, player_items)

    # Fetch journalist commentaries for this week
    # ROBUST FIX: Query by API Team ID (e.g. 33) instead of DB ID (e.g. 234)
    # This ensures we find commentaries even if they are linked to an older season's team record
    current_team = Team.query.get(team_db_id)
    api_team_id = current_team.team_id if current_team else None
    
    print(f"\n{'='*60}")
    print(f"[COMMENTARY QUERY DEBUG - ROBUST MODE]")
    print(f"{'='*60}")
    print(f"Searching for commentaries with:")
    print(f"  API Team ID: {api_team_id} (derived from DB ID {team_db_id})")
    print(f"  week_start_date: {week_start}")
    print(f"  week_end_date: {week_end}")
    print(f"  is_active: True")
    print(f"{'='*60}\n")
    
    if api_team_id:
        commentaries = db.session.query(NewsletterCommentary)\
            .join(Team, NewsletterCommentary.team_id == Team.id)\
            .filter(
                Team.team_id == api_team_id,
                NewsletterCommentary.week_start_date == week_start,
                NewsletterCommentary.week_end_date == week_end,
                NewsletterCommentary.is_active == True
            )\
            .order_by(NewsletterCommentary.position.asc(), NewsletterCommentary.created_at.asc())\
            .all()
    else:
        print("[ERROR] Could not resolve API Team ID, falling back to simple query")
        commentaries = NewsletterCommentary.query.filter(
            NewsletterCommentary.team_id == team_db_id,
            NewsletterCommentary.week_start_date == week_start,
            NewsletterCommentary.week_end_date == week_end,
            NewsletterCommentary.is_active == True
        ).order_by(NewsletterCommentary.position.asc(), NewsletterCommentary.created_at.asc()).all()
    
    print(f"[COMMENTARY QUERY RESULT] Found {len(commentaries)} matching commentaries")
    
    # Show ALL commentaries in DB for debugging
    all_commentaries = NewsletterCommentary.query.filter(NewsletterCommentary.is_active == True).all()
    print(f"\n[ALL ACTIVE COMMENTARIES IN DB] Total: {len(all_commentaries)}")
    for ac in all_commentaries:
        # Resolve team info for debug
        t = Team.query.get(ac.team_id)
        t_info = f"API:{t.team_id}/S:{t.season}" if t else "Unknown"
        print(f"  ID:{ac.id} | TeamDB:{ac.team_id}({t_info}) | Week:{ac.week_start_date} to {ac.week_end_date} | Title:{ac.title}")
    print("")

    intro_commentary = []
    summary_commentary = []
    player_commentary_map = {}

    for c in commentaries:
        c_dict = c.to_dict()
        if c.commentary_type == 'intro':
            intro_commentary.append(c_dict)
        elif c.commentary_type == 'summary':
            summary_commentary.append(c_dict)
        elif c.commentary_type == 'player' and c.player_id:
            if c.player_id not in player_commentary_map:
                player_commentary_map[c.player_id] = []
            player_commentary_map[c.player_id].append(c_dict)

    print(f"[DEBUG] Found {len(commentaries)} active commentaries for team {team_db_id} week {week_start}-{week_end}")
    print(f"[DEBUG] Intro: {len(intro_commentary)}, Summary: {len(summary_commentary)}, Player-specific: {sum(len(v) for v in player_commentary_map.values())}")
    if player_commentary_map:
        print(f"[DEBUG] Player IDs with commentary: {list(player_commentary_map.keys())}")
        
        # Inject commentary into player items
        for item in player_items:
            pid = item.get("player_id")
            if pid and pid in player_commentary_map:
                # Take the first commentary for this player (or join multiple if needed)
                # For now, we'll just take the content of the first one
                coms = player_commentary_map[pid]
                if coms:
                    # Inject the commentary content directly into the player item
                    # This ensures it appears in the JSON output
                    item["commentary"] = coms[0].get("content")
                    item["commentary_title"] = coms[0].get("title")
                    print(f"[DEBUG] Injected commentary for player {pid} ({item.get('player_name')})")

    # Build multi-section content grouped by pathway status, with sub-groups
    def _group_items_by(items: list[dict], key: str, fallback: str = "Other") -> list[dict[str, Any]]:
        """Group items into subsections by a given key."""
        from collections import OrderedDict
        groups_map: OrderedDict[str, list] = OrderedDict()
        for item in items:
            label = item.get(key) or fallback
            groups_map.setdefault(label, []).append(item)
        return [{"label": label, "items": sub_items} for label, sub_items in groups_map.items()]

    # ── Split first-team into "established" vs "debut" tiers ──
    # Established: 500+ season minutes OR 10+ season appearances
    # First Team Debut: made the senior squad but not yet established
    # Cameo players already reclassified to academy in fetch_pipeline_report_tool,
    # so all remaining first_team_items are genuinely established first-team players.
    sections: list[dict[str, Any]] = []
    if first_team_items:
        sections.append({"title": "First Team", "items": first_team_items})
    if on_loan_items:
        subsections = _group_items_by(on_loan_items, "loan_league_name", fallback="Other")
        if len(subsections) > 1:
            sections.append({"title": "On Loan", "subsections": subsections})
        else:
            sections.append({"title": "On Loan", "items": on_loan_items})
    if academy_items:
        subsections = _group_items_by(academy_items, "current_level", fallback="Academy")
        if len(subsections) > 1:
            sections.append({"title": "Academy Rising", "subsections": subsections})
        else:
            sections.append({"title": "Academy Rising", "items": academy_items})
    if not sections:
        sections.append({"title": "Player Reports", "items": []})

    # Build table of contents
    toc: list[dict[str, Any]] = []
    for sec in sections:
        toc_entry: dict[str, Any] = {"section": sec["title"]}
        if "subsections" in sec:
            toc_entry["count"] = sum(len(sub["items"]) for sub in sec["subsections"])
            toc_entry["subsections"] = [
                {"label": sub["label"], "count": len(sub["items"])}
                for sub in sec["subsections"]
            ]
        else:
            toc_entry["count"] = len(sec.get("items", []))
        toc.append(toc_entry)

    newsletter_title = f"{team_name} Academy Pipeline Update"

    content_payload: dict[str, Any] = {
        "title": newsletter_title,
        "toc": toc,
        "summary": summary_text,
        "season": report.get("season"),
        "range": range_window,
        "highlights": [],
        "sections": sections,
        "intro_commentary": intro_commentary,
        "summary_commentary": summary_commentary,
        "player_commentary_map": player_commentary_map,
    }

    try:
        content_payload, _ = _apply_player_lookup(content_payload, player_lookup)
        content_payload = legacy_lint_and_enrich(content_payload)
        if has_any_players:
            content_payload = _enforce_player_metadata(content_payload, player_meta_by_pid, player_meta_by_key)
    except Exception as enrich_error:
        _nl_dbg("lint-and-enrich failed:", str(enrich_error))

    # Post-process: validate outbound links in the final content
    if ENV_VALIDATE_FINAL_LINKS:
        try:
            content_payload = _sanitize_links_in_content(content_payload)
        except Exception as e:
            _nl_dbg("final-link-sanitize failed:", str(e))

    content = json.dumps(content_payload, ensure_ascii=False)
    _nl_dbg("Structured content length:", len(content))

    return {
        "content_json": content,
        "week_start": week_start,
        "week_end": week_end,
        "season_start_year": season_start_year,
    }

def generate_team_weekly_newsletter(team_db_id: int, target_date: date, force_refresh: bool = False) -> dict:
    """Compose and persist a weekly newsletter; returns row.to_dict().
    Used by batch jobs. For API routes, prefer composing then persisting at the route level.
    """
    out = compose_team_weekly_newsletter(team_db_id, target_date, force_refresh=force_refresh)
    row = persist_newsletter(
        team_db_id=team_db_id,
        content_json_str=out["content_json"],
        week_start=out["week_start"],
        week_end=out["week_end"],
        issue_date=target_date,
        newsletter_type="weekly",
    )
    return row.to_dict()
BRAVE_LOCALIZATION_BY_ISO = {
    "GB": {"country": "GB", "search_lang": "en", "ui_lang": "en-GB"},
    "IE": {"country": "IE", "search_lang": "en", "ui_lang": "en-IE"},
    "FR": {"country": "FR", "search_lang": "fr", "ui_lang": "fr-FR"},
    "ES": {"country": "ES", "search_lang": "es", "ui_lang": "es-ES"},
    "DE": {"country": "DE", "search_lang": "de", "ui_lang": "de-DE"},
    "IT": {"country": "IT", "search_lang": "it", "ui_lang": "it-IT"},
    "PT": {"country": "PT", "search_lang": "pt", "ui_lang": "pt-PT"},
    "BR": {"country": "BR", "search_lang": "pt", "ui_lang": "pt-BR"},
    "NL": {"country": "NL", "search_lang": "nl", "ui_lang": "nl-NL"},
    "BE": {"country": "BE", "search_lang": "nl", "ui_lang": "nl-BE"},
    "BE-FR": {"country": "BE", "search_lang": "fr", "ui_lang": "fr-BE"},
    "SE": {"country": "SE", "search_lang": "sv", "ui_lang": "sv-SE"},
    "NO": {"country": "NO", "search_lang": "no", "ui_lang": "no-NO"},
    "DK": {"country": "DK", "search_lang": "da", "ui_lang": "da-DK"},
    "FI": {"country": "FI", "search_lang": "fi", "ui_lang": "fi-FI"},
    "CH": {"country": "CH", "search_lang": "de", "ui_lang": "de-CH"},
    "AT": {"country": "AT", "search_lang": "de", "ui_lang": "de-AT"},
    "PL": {"country": "PL", "search_lang": "pl", "ui_lang": "pl-PL"},
    "HR": {"country": "HR", "search_lang": "hr", "ui_lang": "hr-HR"},
    "BA": {"country": "BA", "search_lang": "bs", "ui_lang": "bs-BA"},
    "US": {"country": "US", "search_lang": "en", "ui_lang": "en-US"},
}

COUNTRY_FALLBACKS = {
    "BE": ["BE-FR", "FR", "NL"],
    "CA": ["US", "GB"],
    "CH": ["DE", "FR", "IT"],
    "BR": ["PT"],
    "MX": ["ES", "US"],
    "AR": ["ES"],
    "CO": ["ES"],
    "JP": ["US"],
}

def resolve_localization_for_country(iso_code: str | None, *, default: dict[str, str] | None = None) -> dict[str, str]:
    default_loc = default or LOCALIZATION_DEFAULT
    if not iso_code:
        return dict(default_loc)
    code = iso_code.upper()
    if code in BRAVE_LOCALIZATION_BY_ISO:
        return dict(BRAVE_LOCALIZATION_BY_ISO[code])
    for fallback in COUNTRY_FALLBACKS.get(code, []):
        if fallback in BRAVE_LOCALIZATION_BY_ISO:
            return dict(BRAVE_LOCALIZATION_BY_ISO[fallback])
    return dict(default_loc)
