from __future__ import annotations
from src.mcp import brave as brave_api
import os
import json
import asyncio
import random
import shutil
import subprocess
import logging
import re
import unicodedata
import uuid
from urllib.parse import urlparse
from datetime import date, timedelta, datetime, timezone
from typing import Any, Dict, Annotated
import dataclasses
from collections.abc import Mapping
from pydantic import BaseModel, Field, Json, StringConstraints
from openai import AsyncOpenAI
from agents import (Agent, 
                    FunctionTool, 
                    Runner,
                    set_default_openai_client,
                    ToolCallItem,
                    ToolCallOutputItem,
                    )
from agents.run_context import RunContextWrapper

from src.models.league import db, Team, Newsletter, Player, TeamProfile, LeagueLocalization
from src.models.tracked_player import TrackedPlayer
from sqlalchemy import func
from src.agents.errors import NoActiveLoaneesError
from jinja2 import Environment, FileSystemLoader, select_autoescape
from src.api_football_client import APIFootballClient
from src.utils.newsletter_slug import compose_newsletter_public_slug
import dotenv
dotenv.load_dotenv(dotenv.find_dotenv())

# Debug flags for search logging
DEBUG_MCP = os.getenv("MCP_DEBUG") == "1"
try:
    MCP_LOG_SAMPLE_N = int(os.getenv("MCP_LOG_SAMPLE_N") or "2")
except Exception:
    MCP_LOG_SAMPLE_N = 2

# Freshness policy flags
STRICT_FRESHNESS = (os.getenv("MCP_STRICT_FRESHNESS", "1").lower() in ("1", "true", "yes"))
ALLOW_WIDE_FRESHNESS = (os.getenv("MCP_ALLOW_WIDE_FRESHNESS", "0").lower() in ("1", "true", "yes"))
ENABLE_SOFA_NAME_FALLBACK = (os.getenv("ENABLE_SOFA_NAME_FALLBACK", "0").lower() in ("1", "true", "yes", "on"))

def _log_sample(tag: str, pid: str, query: str, results: list[dict]):
    if not DEBUG_MCP:
        return
    log = logging.getLogger(__name__)
    try:
        log.info("BRAVE %s | pid=%s | q=%r | total=%d", tag, pid, query, len(results or []))
        for r in (results or [])[:MCP_LOG_SAMPLE_N]:
            title = (r.get('title') or '')[:140]
            url = (r.get('url') or '')[:160]
            pub = r.get('publisher')
            sent = r.get('sentiment')
            log.info("  · %s | %s | pub=%s | sent=%s", title, url, pub, sent)
        # also log raw JSON samples for debugging integration issues
        try:
            import json as _json
            log.info("BRAVE %s RAW | pid=%s | %s", tag, pid, _json.dumps((results or [])[:MCP_LOG_SAMPLE_N], ensure_ascii=False)[:1000])
        except Exception:
            pass
    except Exception:
        pass

# Module-level cache to make search_context available to persist tool when the agent omits it
_LATEST_SEARCH_CONTEXT: dict[str, dict] | None = None
_LATEST_PLAYER_LOOKUP: dict[str, list[dict[str, Any]]] = {}

# --- String sanitization helpers (remove ASCII control chars except \t, \n, \r) ---
import re
from urllib.parse import urlparse
_CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

def _clean_str(s: str) -> str:
    if not isinstance(s, str):
        return s
    return _CONTROL_RE.sub('', s)

def _sanitize(obj):
    if isinstance(obj, str):
        return _clean_str(obj)
    if isinstance(obj, list):
        return [_sanitize(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    return obj


def _normalize_player_key(name: str) -> str:
    if not name:
        return ''
    cleaned = to_initial_last(name)
    cleaned = strip_diacritics(cleaned)
    cleaned = ''.join(ch for ch in cleaned.lower() if ch.isalnum())
    return cleaned


def _set_latest_player_lookup(mapping: dict[str, list[dict[str, Any]]] | None) -> None:
    global _LATEST_PLAYER_LOOKUP
    if not mapping:
        _LATEST_PLAYER_LOOKUP = {}
        return
    normalized: dict[str, list[dict[str, Any]]] = {}
    for key, values in mapping.items():
        if not key or not isinstance(values, list):
            continue
        normalized[key] = [v for v in values if isinstance(v, dict)]
    _LATEST_PLAYER_LOOKUP = normalized


def _apply_player_lookup(content_json: dict, lookup: dict[str, list[dict[str, Any]]] | None = None) -> tuple[dict, bool]:
    if not isinstance(content_json, dict):
        return content_json, False
    active_lookup = lookup or _LATEST_PLAYER_LOOKUP or {}
    if not active_lookup:
        return content_json, False

    changed = False
    sections = content_json.get('sections') or []
    for sec in sections:
        items = sec.get('items') if isinstance(sec, dict) else None
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, dict):
                continue
            if item.get('skip_lookup'):
                continue
            if item.get('player_id'):
                continue
            name = item.get('player_name') or item.get('player') or ''
            if not name:
                continue
            keys = []
            keys.append(_normalize_player_key(name))
            alt = to_initial_last(name)
            if alt and alt != name:
                keys.append(_normalize_player_key(alt))
            full = item.get('full_name')
            if isinstance(full, str):
                keys.append(_normalize_player_key(full))

            candidate = None
            for key in keys:
                if not key:
                    continue
                matches = active_lookup.get(key)
                if not matches:
                    continue
                if len(matches) == 1:
                    candidate = matches[0]
                else:
                    loan_team = (item.get('loan_team') or item.get('loan_team_name') or '').strip().lower()
                    for match in matches:
                        lt_name = (match.get('loan_team_name') or '').strip().lower()
                        if loan_team and lt_name and loan_team == lt_name:
                            candidate = match
                            break
                    if candidate is None:
                        candidate = matches[0]
                if candidate:
                    break

            if candidate and candidate.get('player_id'):
                item['player_id'] = candidate['player_id']
                if candidate.get('loan_team_api_id') and not item.get('loan_team_api_id'):
                    item['loan_team_api_id'] = candidate['loan_team_api_id']
                if candidate.get('loan_team_id') and not item.get('loan_team_id'):
                    item['loan_team_id'] = candidate['loan_team_id']
                if candidate.get('loan_team_name') and not item.get('loan_team'):
                    item['loan_team'] = candidate['loan_team_name']
                if candidate.get('loan_team_name') and not item.get('loan_team_name'):
                    item['loan_team_name'] = candidate['loan_team_name']
                changed = True

    if changed:
        content_json['sections'] = sections
    return content_json, changed

# ---------- Utilities ----------
def monday_range(target: date) -> tuple[date, date]:
    start = target - timedelta(days=target.weekday())
    return start, start + timedelta(days=6)

def freshness_range_str(start_date: date, end_date: date | None = None, *, fallback: str = "pw") -> str:
    """
    Build Brave MCP freshness strings. Always return a plain str.
    - If both dates provided: 'YYYY-MM-DDtoYYYY-MM-DD'
    - Else: fallback shorthand (pd|pw|pm|py)
    Strips any non-printable characters defensively.
    """
    try:
        s = str(start_date)[:10]
        if end_date is not None:
            e = str(end_date)[:10]
            val = f"{s}to{e}"
        else:
            val = fallback
        return "".join(ch for ch in val if ch.isprintable())
    except Exception:
        return fallback

def get_league_localization(league_name: str) -> dict:
    """
    Get Brave Search localization parameters based on league.
    Returns country code, search language, and UI language for optimal results.
    """
    try:
        loc = LeagueLocalization.query.filter_by(league_name=league_name).first()
        if loc:
            return {'country': loc.country, 'search_lang': loc.search_lang, 'ui_lang': loc.ui_lang}
    except Exception:
        # If DB is unavailable or query fails, fall back to hard-coded mapping
        pass

    localizations = {
        'Premier League': {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'},
        'La Liga': {'country': 'ES', 'search_lang': 'es', 'ui_lang': 'es-ES'},
        'Segunda División': {'country': 'ES', 'search_lang': 'es', 'ui_lang': 'es-ES'},
        'Ligue 1': {'country': 'FR', 'search_lang': 'fr', 'ui_lang': 'fr-FR'},
        'Ligue 2': {'country': 'FR', 'search_lang': 'fr', 'ui_lang': 'fr-FR'},
        'Bundesliga': {'country': 'DE', 'search_lang': 'de', 'ui_lang': 'de-DE'},
        'Bundesliga 2': {'country': 'DE', 'search_lang': 'de', 'ui_lang': 'de-DE'},
        '2. Bundesliga': {'country': 'DE', 'search_lang': 'de', 'ui_lang': 'de-DE'},
        'Serie A': {'country': 'IT', 'search_lang': 'it', 'ui_lang': 'it-IT'},
        'Serie B': {'country': 'IT', 'search_lang': 'it', 'ui_lang': 'it-IT'},
        'Championship': {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'},
        'League One': {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'},
        'League Two': {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'},
        'Eredivisie': {'country': 'NL', 'search_lang': 'nl', 'ui_lang': 'nl-NL'},
        'Eerste Divisie': {'country': 'NL', 'search_lang': 'nl', 'ui_lang': 'nl-NL'},
        'Primeira Liga': {'country': 'PT', 'search_lang': 'pt', 'ui_lang': 'pt-PT'},
        'Liga Portugal 2': {'country': 'PT', 'search_lang': 'pt', 'ui_lang': 'pt-PT'},
        'Scottish Premiership': {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'},
        'Scottish Championship': {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'},
        'MLS': {'country': 'US', 'search_lang': 'en', 'ui_lang': 'en-US'},
        'Major League Soccer': {'country': 'US', 'search_lang': 'en', 'ui_lang': 'en-US'},
        'Belgian Pro League': {'country': 'BE', 'search_lang': 'nl', 'ui_lang': 'nl-BE'},
        'Jupiler Pro League': {'country': 'BE', 'search_lang': 'nl', 'ui_lang': 'nl-BE'},
        'Belgian First Division A': {'country': 'BE', 'search_lang': 'nl', 'ui_lang': 'nl-BE'},
        'Belgian First Division B': {'country': 'BE', 'search_lang': 'nl', 'ui_lang': 'nl-BE'},
        'Süper Lig': {'country': 'TR', 'search_lang': 'tr', 'ui_lang': 'tr-TR'},
        'TFF First League': {'country': 'TR', 'search_lang': 'tr', 'ui_lang': 'tr-TR'},
    }
    return localizations.get(league_name, {'country': 'GB', 'search_lang': 'en', 'ui_lang': 'en-GB'})

def build_enhanced_queries(player: str, loan_team: str, opponent: str, competition: str, league_lang: str) -> list:
    """
    Build enhanced search queries with multiple synonyms and local language terms.
    Returns a list of query variations for better search coverage.
    """
    # Base English terms that work across all leagues
    base_terms = [
        "player ratings", "match reaction", "analysis", "performance review", 
        "what fans said", "match report", "player performance", "fan reaction"
    ]
    
    # Add local language terms based on league
    if league_lang == 'es':
        base_terms.extend([
            "análisis", "valoración", "reacción de aficionados", "reporte del partido",
            "rendimiento del jugador", "opinión de la afición"
        ])
    elif league_lang == 'fr':
        base_terms.extend([
            "analyse", "évaluation", "réaction des supporters", "rapport de match",
            "performance du joueur", "avis des fans"
        ])
    elif league_lang == 'de':
        base_terms.extend([
            "Analyse", "Bewertung", "Fan-Reaktionen", "Spielbericht",
            "Spielerleistung", "Fan-Meinung"
        ])
    elif league_lang == 'it':
        base_terms.extend([
            "analisi", "valutazione", "reazione dei tifosi", "rapporto partita",
            "prestazione giocatore", "opinione tifosi"
        ])
    
    # Build queries with different term combinations
    queries = []
    for term in base_terms:
        # Per-match specific query
        if opponent and competition:
            queries.append(f'"{player}" "{loan_team}" "{opponent}" "{competition}" {term}')
        # Weekly overview query
        queries.append(f'"{player}" "{loan_team}" {term}')
    
    # Add some broader queries for better coverage
    queries.extend([
        f'"{player}" {loan_team} {term}' for term in ["news", "latest", "update", "performance"]
    ])
    
    return queries[:8]  # Limit to 8 queries to avoid overwhelming the API

def categorize_and_deduplicate_results(web_results: list, news_results: list) -> dict:
    """
    Categorize and deduplicate search results for better organization.
    Returns categorized results with sentiment indicators.
    """
    # Deduplicate by URL
    seen_urls = set()
    unique_web = []
    unique_news = []
    
    for result in web_results:
        url = result.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_web.append(result)
    
    for result in news_results:
        url = result.get('url', '')
        if url and url not in seen_urls:
            seen_urls.add(url)
            unique_news.append(result)
    
    # Categorize web results
    discussions = []
    videos = []
    articles = []
    
    for result in unique_web:
        url = result.get('url', '').lower()
        title = result.get('title', '').lower()
        snippet = (result.get('description') or result.get('snippet') or '').lower()
        
        # Simple categorization based on URL patterns and content
        if any(word in url for word in ['forum', 'reddit', 'twitter', 'facebook', 'instagram']):
            discussions.append(result)
        elif any(word in url for word in ['youtube', 'vimeo', 'dailymotion', '.mp4', '.avi']):
            videos.append(result)
        else:
            articles.append(result)
    
    # Basic sentiment analysis based on keywords
    def analyze_sentiment(text: str) -> str:
        text_lower = text.lower()
        positive_words = ['excellent', 'outstanding', 'brilliant', 'amazing', 'fantastic', 'great', 'good', 'impressive']
        negative_words = ['poor', 'terrible', 'awful', 'disappointing', 'bad', 'weak', 'struggled', 'failed']
        
        positive_count = sum(1 for word in positive_words if word in text_lower)
        negative_count = sum(1 for word in negative_words if word in text_lower)
        
        if positive_count > negative_count:
            return 'positive'
        elif negative_count > positive_count:
            return 'negative'
        else:
            return 'neutral'
    
    # Add sentiment to all results
    for result in unique_web + unique_news:
        text = f"{result.get('title', '')} {(result.get('snippet') or result.get('description') or '')}"
        result['sentiment'] = analyze_sentiment(text)
    
    return {
        "web": articles[:10],
        "news": unique_news[:10],
        "discussions": discussions[:8],
        "videos": videos[:5],
        "summaries": [r.get('summary') for r in unique_web + unique_news if r.get('summary')],
        "sentiment_breakdown": {
            "positive": len([r for r in unique_web + unique_news if r.get('sentiment') == 'positive']),
            "negative": len([r for r in unique_web + unique_news if r.get('sentiment') == 'negative']),
            "neutral": len([r for r in unique_web + unique_news if r.get('sentiment') == 'neutral'])
        }
    }

# --- Post-filter helpers for Brave results (date/name/team/domain gates) ---
from datetime import datetime

_ALLOWED_FORUM_HOSTS = (
    "reddit.com",
    "old.reddit.com",
)

_DENY_WEB_HOST_SUBSTR = (
    "fandom.com",
    "ea.com/games/ea-sports-fc",
)

def _parse_any_date(val: str | None) -> date | None:
    if not val or not isinstance(val, str):
        return None
    s = val.strip()
    # ISO-like: 2024-10-31 or 2024-10-31T00:23:16
    try:
        if len(s) >= 10 and s[4] == '-' and s[7] == '-':
            return date.fromisoformat(s[:10])
    except Exception:
        pass
    # Common textual forms
    fmts = [
        "%d %B %Y", "%d %b %Y", "%B %d, %Y", "%b %d, %Y",
        "%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y",
    ]
    for fmt in fmts:
        try:
            return datetime.strptime(s, fmt).date()
        except Exception:
            continue
    return None

def _text_matches_player_team(text: str, player_name: str, loan_team: str) -> bool:
    txt = strip_diacritics(text or '').lower()
    # Require last-name match
    last = strip_diacritics((player_name or '').split()[-1]).lower().strip('. ')
    if last and last not in txt:
        return False
    # Team match improves precision; allow transfer/global pieces if last name present
    team = strip_diacritics(loan_team or '').lower()
    if team and team in txt:
        return True
    # If team missing in text, still allow for purely transfer/rumour contexts.
    # Heuristic: presence of common transfer terms keeps it; otherwise drop.
    transfer_terms = ("transfer", "loan", "linked", "talks", "negotiation", "sign", "move")
    if any(t in txt for t in transfer_terms):
        return True
    return False

def _host(url: str) -> str:
    try:
        return urlparse(url).netloc.lower()
    except Exception:
        return ""

def _filter_hits_for_player(cat: dict, player_name: str, loan_team: str, week_start: date, week_end: date) -> dict:
    """Apply date/name/team/domain gates to categorized results.
    - Keep items within week window ± (−2, +3) days when a usable date exists.
    - Require last name in title/snippet; prefer team mention or transfer terms.
    - Drop denylisted web hosts.
    - Limit discussions to forum domains (reddit) only for fan pulse.
    """
    lower = week_start - timedelta(days=2)
    upper = week_end + timedelta(days=3)

    def ok_item(r: dict) -> bool:
        if not isinstance(r, dict):
            return False
        url = (r.get('url') or r.get('link') or '').strip()
        if not url:
            return False
        h = _host(url)
        # deny some obviously noisy hosts for web/news
        if any(bad in h or bad in url for bad in _DENY_WEB_HOST_SUBSTR):
            return False
        title = r.get('title') or r.get('name') or ''
        snippet = r.get('snippet') or r.get('description') or ''
        if not _text_matches_player_team(f"{title} {snippet}", player_name, loan_team):
            return False
        # Date gate (if present)
        d = _parse_any_date(r.get('date') or r.get('published') or r.get('published_date') or r.get('age') or r.get('page_age'))
        if d is not None and not (lower <= d <= upper):
            return False
        return True

    def ok_forum(r: dict) -> bool:
        url = (r.get('url') or '').strip()
        h = _host(url)
        if not h:
            return False
        if h in _ALLOWED_FORUM_HOSTS or 'forum' in h:
            # name/team gate still applies
            title = r.get('title') or ''
            snip = r.get('snippet') or r.get('description') or ''
            if not _text_matches_player_team(f"{title} {snip}", player_name, loan_team):
                return False
            d = _parse_any_date(r.get('date') or r.get('published') or r.get('published_date') or r.get('age') or r.get('page_age'))
            if d is not None and not (lower <= d <= upper):
                return False
            return True
        return False

    try:
        web = [r for r in (cat.get('web') or []) if ok_item(r)]
        news = [r for r in (cat.get('news') or []) if ok_item(r)]
        disc = [r for r in (cat.get('discussions') or []) if ok_forum(r)]
        vids = [r for r in (cat.get('videos') or []) if ok_item(r)]
        return {
            **cat,
            'web': web,
            'news': news,
            'discussions': disc,
            'videos': vids,
        }
    except Exception:
        return cat

api_client = APIFootballClient()

# Cache player photo lookups keyed by API-Football player id
_PLAYER_PHOTO_CACHE: dict[int, str | None] = {}
# Cache team logo lookups keyed by API-Football team id
_TEAM_LOGO_CACHE: dict[int, str | None] = {}
# aio_client = AsyncOpenAI(
#     base_url="https://openrouter.ai/api/v1",
#     api_key=os.getenv("OPENROUTER_API_KEY")
# )
aio_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))
set_default_openai_client(aio_client)
print(f'weekly agent client: {aio_client}')

# ---------- JSON safety helpers ----------

def _to_jsonable(obj: Any) -> Any:
    """Convert SDK/runtime objects (e.g., ResponseFunctionToolCall) into JSON-serializable data.

    - Preserves primitives and mappings
    - Recursively converts sequences
    - Supports dataclasses and Pydantic models
    - Falls back to extracting common tool-call fields (name, arguments)
    - Ultimately falls back to str(obj)
    """
    # Primitives and None
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj

    # Mappings
    if isinstance(obj, Mapping):
        return {str(_to_jsonable(k)): _to_jsonable(v) for k, v in obj.items()}

    # Common sequences
    if isinstance(obj, (list, tuple, set)):
        return [_to_jsonable(x) for x in obj]

    # Dataclasses
    if dataclasses.is_dataclass(obj):
        try:
            return _to_jsonable(dataclasses.asdict(obj))
        except Exception:
            pass

    # Pydantic v2
    if hasattr(obj, "model_dump") and callable(getattr(obj, "model_dump")):
        try:
            return _to_jsonable(obj.model_dump())
        except Exception:
            pass

    # Pydantic v1 style
    if hasattr(obj, "dict") and callable(getattr(obj, "dict")):
        try:
            return _to_jsonable(obj.dict())
        except Exception:
            pass

    # Try to extract common tool-call fields if present
    try:
        name = getattr(obj, "name", None)
        arguments = getattr(obj, "arguments", None)
        if name is not None or arguments is not None:
            # arguments may be a JSON string or a dict
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except Exception:
                    # keep as string if not JSON
                    pass
            return {
                "type": obj.__class__.__name__,
                "name": name,
                "arguments": _to_jsonable(arguments),
            }
    except Exception:
        pass

    # Best-effort fallback
    try:
        return str(obj)
    except Exception:
        return repr(obj)

# reusable type for ISO-date string
DateStr = Annotated[
    str,
    StringConstraints(
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        min_length=10,
        max_length=10
    )
]

class FetchWeeklyReportArgs(BaseModel):
    parent_team_db_id: int = Field(..., description="DB PK of the parent team")
    target_date: DateStr = Field(..., description="YYYY-MM-DD ISO date")

class PersistNewsletterArgs(BaseModel):
    team_db_id: int = Field(..., description="DB PK of the parent team")
    content_json: Json[Any] = Field(..., description="Structured newsletter payload")
    issue_date: DateStr = Field(..., description="YYYY-MM-DD ISO date")
    player_lookup: Json[Any] | None = Field(None, description="Optional mapping of player aliases to metadata")

SYSTEM_INSTRUCTIONS = """
You are a football newsletter editor creating comprehensive weekly loan reports. Tools available: Python tools. The search context is precomputed using the Brave Search API.

Workflow:
1) Call fetch_weekly_report(team, date). You get comprehensive data per player:
   - Week totals: minutes, goals, assists, cards, rating, shots, passes, tackles, duels, dribbles
   - Per-match breakdown with 'match_notes' containing ALL stats for each specific game
   - Each match_notes entry shows: "vs [Opponent]: [detailed stats]"
   
   CRITICAL: match_notes tie EVERY stat to a specific opponent. Always reference the exact opponent when mentioning any performance detail.

2) The search context provides rich external data:
   - Localized searches (country, language)
   - Categorized: web articles, news, discussions, videos
   - Sentiment analysis + summaries
   - Deduplicated and ranked results

DATA STRUCTURE EXPLANATION:
Each player has:
- matches[]: array of games with 'match_notes', 'opponent', 'competition', 'date', 'role', 'player' (all stats for that game)
- totals: aggregated weekly stats across all matches
- season_context: cumulative season stats and trends for narrative depth
  - season_stats: total games, goals, assists, minutes, ratings, etc. for the entire season
  - recent_form: last 5 games with goals/assists/ratings
  - trends: goals_per_90, assists_per_90, shot_accuracy, goals_last_5, duels_win_rate, etc.
- The 'player' field in each match contains: minutes, goals, assists, rating, shots_total, shots_on, passes_key, 
  dribbles_success, dribbles_attempts, tackles_total, tackles_interceptions, duels_won, duels_total, saves, etc.

ROLE FIELD (CRITICAL - determines how player entered each match):
- role='startXI' → Player STARTED the match (was in the starting eleven)
- role='substitutes' → Player was a SUBSTITUTE (came off the bench OR was unused sub if minutes=0)
- role=null/None → Player was NOT in the matchday squad (injured, suspended, not selected)
- Use this to accurately describe: "Started vs Arsenal", "Came off the bench vs City", "Was not in the squad"
- If role='startXI' but minutes are low (e.g., 15-20), player was likely subbed off early (injury/tactical change)

WRITING COMPREHENSIVE SUMMARIES (CRITICAL):
Your week_summary for each player MUST be in-depth and use ALL available data:

⚠️ CRITICAL: ONLY write about stats that ACTUALLY EXIST in the stats object for THIS player_id!
   - If stats.assists = 0, DO NOT mention any assists
   - If stats.goals = 0, DO NOT mention any goals
   - ALWAYS check the stats object before writing any performance claims
   - NEVER assume a player contributed something based on match context

1. START with match-by-match narrative using match_notes:
   - Match notes are PRE-VERIFIED and tie stats to specific opponents
   - "Started and scored vs Arsenal (Rating: 8.2, 3/5 shots on target, 4 key passes)"
   - "Came off the bench vs City to provide the assist in added time"
   - If match_notes say "Assisted vs Real Madrid" but stats.assists = 0, DO NOT MENTION THE ASSIST
   
2. INCLUDE specific performance metrics (ONLY IF THEY EXIST IN STATS):
   - Goals/assists with opponent names from match_notes
   - Ratings when notable (7.5+)
   - Shot accuracy for attackers (e.g., "3/7 shots on target")
   - Key passes and creativity metrics (e.g., "created 6 chances")
   - Dribbles for wingers (e.g., "completed 8/12 dribbles")
   - Defensive work (e.g., "won 12/15 duels, 5 tackles, 3 interceptions")
   - Goalkeeper stats (e.g., "made 8 saves in the 2-1 win")

3. ADD SEASON CONTEXT for depth (CRITICAL - use season_context data):
   - Season totals: "brings his tally to 8 goals in 15 appearances"
   - Recent form: "his fourth goal in the last 5 games" or "ended a 6-game goalless drought"
   - Trends: "now averaging 0.7 goals per 90 minutes this season"
   - Comparisons: "his best performance of the season" or "matching his season average rating of 7.2"
   - Milestones: "reached 10 assists for the season" or "first goal since September"
   - Clean sheets: "his 6th clean sheet in 12 games"
   - Consistency: "scored in 3 consecutive matches" or "yet to score this season"
   
4. TELL A STORY across the week:
   - Contrast between performances (e.g., "quiet against Brighton but dominated vs Leeds")
   - Emerging patterns (e.g., "continues his scoring run", "fourth clean sheet in five games")
   - Position-specific insights (e.g., "patrolled the midfield", "terrorized the left flank")
   - Season progression (e.g., "finding his rhythm after a slow start", "maintaining excellent form")

5. USE COMPARATIVE LANGUAGE:
   - "man of the match performance"
   - "dominated physically"
   - "orchestrated attacks"
   - "solid defensively"
   - "clinical finishing"

EXAMPLE GOOD SUMMARY (with season context):
"Started both matches. Scored the opener vs Arsenal (Rating: 8.5, 2/4 shots on target, 5 key passes) in Saturday's 3-1 win, then assisted vs Brighton (Rating: 7.3, 3 key passes, 7/10 dribbles completed). Created 8 chances across the week, completed 74% of dribbles, and won 15/19 duels. This brings his season tally to 7 goals and 9 assists in 14 appearances, now averaging 0.6 goals per 90 minutes. His fourth goal contribution in the last 5 games, establishing himself as a key creative outlet."

EXAMPLE BAD SUMMARY (too simple, no context):
"Played two games this week. Scored one goal and had one assist."

Identity & naming (CRITICAL - MUST FOLLOW):
- **ALWAYS include player_id** from the source data on each item - this is MANDATORY
- The player_id field is the PRIMARY KEY that ties stats to the correct player
- Use first-initial + last-name for player_name (e.g., "H. Mejbri", "Á. Fernández")
- NEVER mix up players or stats between different player_ids

Manual/Untracked Players (can_fetch_stats=False):
- These are manually added players where our data provider (API-Football) doesn't track them yet
- Write: "This player is not currently tracked by our data provider. We've requested they be added to improve future coverage."
- If any news links/articles were found, ALWAYS include them - they provide valuable context
- Example: "This player is not currently tracked by our data provider. We've requested they be added to improve future coverage. [Player] remains on loan with [Team]."

Limited Stats Coverage (has_limited_stats=True or stats_coverage='limited' on a match):
- Some competitions (FA Cup, EFL Trophy, etc.) only provide basic stats (goals, assists, cards) without detailed metrics
- When a match has stats_coverage='limited', we have goals/assists/cards but NOT: minutes, rating, shots, passes, tackles, dribbles
- The limited_competitions field lists which competitions had limited data (e.g., ['FA Cup', 'EFL Trophy'])
- TASTEFUL HANDLING:
  - DO lead with the key stats we have: "Scored twice in the FA Cup tie against Luton"
  - DO NOT apologize or over-explain: avoid "unfortunately we don't have detailed stats"
  - If mixing full and limited matches, prioritize detail on full-coverage matches
  - For limited matches, focus on the outcome: goals, assists, result, and context from match_notes
  - Example (good): "E. Ennis netted twice in the FA Cup draw with Luton, then started against Tranmere in the EFL Trophy."
  - Example (bad): "Detailed statistics are not available for the FA Cup match, but E. Ennis scored 2 goals."
- At the end of a player's summary, you MAY add a brief note ONLY if most matches were limited:
  "Note: Cup competitions provide limited match data."

Quality rules (STRICT):
- ROLE-BASED LANGUAGE (check role field for each match):
  - role='startXI' AND minutes > 60 → "started" (full game or most of it)
  - role='startXI' AND minutes 1-60 → "started but was substituted off" (subbed out early - could be injury/tactical)
  - role='startXI' AND minutes == 0 → unusual, treat as "named in starting XI but did not feature"
  - role='substitutes' AND minutes > 0 → "came off the bench", "was introduced as a substitute"
  - role='substitutes' AND minutes == 0 → "unused substitute"
  - role is null/None AND minutes == 0 → "was not in the matchday squad" (injured, suspended, not selected)
- If text says "started", the role field MUST be 'startXI'; otherwise check and correct
- Highlights must come from the same week's stats
- ALWAYS reference the specific opponent when mentioning goals/assists/performances
- Use display_name (e.g., "Charlie Wellens") not full legal/middle names

Scoring (for highlights):
score = goals*5 + assists*3 + (minutes/90)*1 - yellow*1 - red*3
Use top 3 for "highlights". Always include a "Loanee of the Week" in the summary.

Overall newsletter summary:
Write 3-4 sentences highlighting:
- Top performer(s) with specific stats
- Notable team performances (e.g., "Three loanees found the net")
- Standout individual performance details
- Any concerning trends (injuries, red cards, losing runs)

Output JSON ONLY:
{
  "title": "...",
  "summary": "3-4 sentences: top performers with specific stats, notable moments, narrative threads",
  "season": "YYYY-YY",
  "range": ["YYYY-MM-DD","YYYY-MM-DD"],
  "highlights": ["Player: detailed stats and performance summary"],
  "sections": [{"title":"Active Loans","items":[{
    "player_id": 12345,  // REQUIRED - must match source data
    "player_name": "H. Player",
    "week_summary": "IN-DEPTH multi-sentence summary using ALL stats and match_notes",
    "stats": {...},  // Must match source data for this player_id exactly
    "match_notes": [...],
    "has_limited_stats": false,  // true if any match lacked detailed stats
    "limited_competitions": []  // e.g., ["FA Cup"] - competitions with basic stats only
  }]}],
  "by_numbers": {"minutes_leaders":[...], "ga_leaders":[...]},
  "fan_pulse": [{"player":"...","forum":"...","quote":"...","url":"..."}]
}
Respond with JSON only, no extra prose.
"""

# ---------- Python-native Tools (exposed to Agent) ----------

async def fetch_weekly_report(ctx, args) -> Dict[str, Any]:
    """
    SDK hands tool args either as a dict or a JSON‐encoded string.
    Normalize, extract expected fields, and run the weekly summary.
    """
    # Accept raw JSON string as well
    if isinstance(args, str):
        args = json.loads(args)

    parent_team_db_id = int(args["parent_team_db_id"])
    target_date = str(args["target_date"])

    tdate = date.fromisoformat(target_date)
    week_start, week_end = monday_range(tdate)

    team = Team.query.get(parent_team_db_id)
    if not team:
        raise ValueError(f"Team DB id {parent_team_db_id} not found")

    # Sync season to target date's season (European season starts Aug 1)
    season_start_year = tdate.year if tdate.month >= 8 else tdate.year - 1
    api_client.set_season_year(season_start_year)
    api_client._prime_team_cache(season_start_year)

    report = api_client.summarize_parent_loans_week(
        parent_team_db_id=team.id,
        parent_team_api_id=team.team_id,
        season=season_start_year,
        week_start=week_start,
        week_end=week_end,
        include_team_stats=False,
        db_session=db.session,
    )
    # normalize parent team payload shape
    report["parent_team"] = {"db_id": team.id, "id": team.team_id, "name": team.name}
    db.session.commit()
    return report

async def persist_newsletter(ctx, args) -> Dict[str, Any]:
    """
    Persist a generated JSON newsletter. Accepts a dict or JSON string payload.
    """
    if isinstance(args, str):
        args = json.loads(args)

    team_db_id = int(args["team_db_id"])
    # Robustly parse content_json which may be JSON text or already a dict.
    raw_content = args.get("content_json")
    search_context = args.get("search_context") if isinstance(args, dict) else None
    player_lookup_payload = args.get("player_lookup") if isinstance(args, dict) else None
    if search_context is None:
        # fallback to latest captured context from orchestrator
        try:
            global _LATEST_SEARCH_CONTEXT
            if isinstance(_LATEST_SEARCH_CONTEXT, dict):
                search_context = _LATEST_SEARCH_CONTEXT
        except Exception:
            pass
    if isinstance(player_lookup_payload, str):
        try:
            player_lookup_payload = json.loads(player_lookup_payload)
        except Exception:
            player_lookup_payload = None
    if isinstance(player_lookup_payload, dict):
        _set_latest_player_lookup(player_lookup_payload)
    else:
        player_lookup_payload = None
    if isinstance(raw_content, str):
        try:
            content_json = json.loads(raw_content)
        except Exception:
            # Attempt to extract a JSON object block from the string
            try:
                import re
                blocks = re.findall(r"\{(?:.|\n)*\}", raw_content)
                if blocks:
                    content_json = json.loads(blocks[0])
                else:
                    # Coerce to a minimal valid payload instead of raising
                    content_json = {"title": "Weekly Loan Update", "summary": "", "sections": []}
            except Exception:
                # Coerce to a minimal valid payload instead of raising
                content_json = {"title": "Weekly Loan Update", "summary": "", "sections": []}
    else:
        content_json = raw_content

    # Sanitize early, unwrap cases where summary accidentally contains JSON
    content_json, removed_a = _sanitize_with_count(content_json)
    try:
        if isinstance(content_json, dict) and isinstance(content_json.get("summary"), str):
            m = re.search(r"\{(?:.|\n)*\}", content_json["summary"])  # extract JSON block if embedded
            if m:
                content_json["summary"] = json.dumps(json.loads(m.group(0)))
    except Exception:
        pass
    issue_date = str(args["issue_date"])

    # If summary field contains an embedded JSON string, prefer its inner summary
    try:
        if isinstance(content_json, dict) and isinstance(content_json.get("summary"), str):
            s = content_json["summary"].strip()
            if s.startswith('{') and s.endswith('}'):
                inner = json.loads(s)
                if isinstance(inner, dict) and inner.get("summary"):
                    content_json["summary"] = inner["summary"]
    except Exception:
        pass

    # Sanitize all strings to strip control characters (e.g., \u0000)
    content_json = _sanitize(content_json)

    try:
        content_json, _ = _apply_player_lookup(content_json, player_lookup_payload)
    except Exception:
        pass

    t = Team.query.get(team_db_id)
    if not t:
        raise ValueError(f"Team DB id {team_db_id} not found")

    issue = date.fromisoformat(issue_date)
    week_start, week_end = monday_range(issue)

    # Finalize only after the range closes (Sunday). Otherwise save as draft.
    is_final = issue >= week_end

    # Inject links/fan_pulse if available and missing
    try:
        updated, injected, added = _inject_links_from_search_context(content_json, search_context, max_links=3)
        content_json = updated
        if injected:
            logging.getLogger(__name__).info(f"Injected links from search_context: yes (+{added})")
        # Always append internet section if any web items exist
        content_json = _append_internet_section(content_json, search_context, max_items_per_player=2)
    except Exception:
        pass

    # Attach debug snapshot so we can "see it regardless" when MCP_DEBUG=1
    try:
        if DEBUG_MCP:
            def _trim_ctx(ctx: dict | None) -> dict:
                if not isinstance(ctx, dict):
                    return {}
                def take(lst, n):
                    try:
                        return list(lst)[:n]
                    except Exception:
                        return []
                return {
                    'web': take(ctx.get('web') or [], MCP_LOG_SAMPLE_N),
                    'news': take(ctx.get('news') or [], MCP_LOG_SAMPLE_N),
                    'discussions': take(ctx.get('discussions') or [], MCP_LOG_SAMPLE_N),
                    'videos': take(ctx.get('videos') or [], MCP_LOG_SAMPLE_N),
                }
            dbg_ctx: dict[str, dict] = {}
            if isinstance(search_context, dict):
                for k, v in list(search_context.items())[:10]:
                    dbg_ctx[k] = _trim_ctx(v if isinstance(v, dict) else {})
            content_json.setdefault('debug', {})
            content_json['debug'].update({
                'range': [week_start.isoformat(), week_end.isoformat()],
                'search_context_samples': dbg_ctx,
            })
    except Exception:
        pass

    # Lint + enrich before persisting
    try:
        content_json = lint_and_enrich(content_json)
    except Exception:
        # Non-fatal; continue with original
        pass

    try:
        team_logo_url = _team_logo_for_team(t.team_id if t else None, fallback_name=(t.name if t else None))
        if team_logo_url:
            content_json["team_logo"] = team_logo_url
    except Exception:
        pass

    # Sanitize again before serializing
    content_json = _sanitize(content_json)

    # Validate shape; if bad, raise to let orchestrator fallback persist a clean copy
    def _valid_content(payload: dict) -> bool:
        return isinstance(payload, dict) and payload.get("title") is not None and isinstance(payload.get("sections"), list)

    # Serialize content JSON for storage
    # Final sanitize before storage; guard against control chars
    content_json, removed_b = _sanitize_with_count(content_json)
    if (removed_a + removed_b) > 0:
        logging.getLogger(__name__).info(f"Sanitized strings: yes ({removed_a + removed_b} chars removed)")
    if not _valid_content(content_json):
        # Coerce to minimal valid payload instead of raising
        content_json = {"title": content_json.get("title") or "Weekly Loan Update", "summary": content_json.get("summary") or "", "sections": content_json.get("sections") or []}
    content_str = json.dumps(content_json, ensure_ascii=False)

    # Render and embed variants for convenience
    try:
        team_name = t.name if t else None
        variants = _render_variants(content_json, team_name)
        content_json['rendered'] = variants
        content_str = json.dumps(content_json, ensure_ascii=False)
    except Exception:
        pass

    placeholder_slug = f"tmp-{uuid.uuid4().hex}"
    nl = Newsletter(
        team_id=team_db_id,
        newsletter_type="weekly",
        title=content_json.get("title") or f"{t.name} Loan Update",
        content=content_str,
        structured_content=content_str,
        public_slug=placeholder_slug,
        week_start_date=week_start,
        week_end_date=week_end,
        issue_date=issue,
        generated_date=issue,
        published=is_final,
        published_date=issue if is_final else None,
    )
    db.session.add(nl)
    db.session.flush()
    team_name_for_slug = (t.name if t else None)
    nl.public_slug = compose_newsletter_public_slug(
        team_name=team_name_for_slug,
        newsletter_type=nl.newsletter_type,
        week_start=nl.week_start_date,
        week_end=nl.week_end_date,
        issue_date=nl.issue_date,
        identifier=nl.id,
    )
    db.session.commit()
    return nl.to_dict()
# ------------------------
# Lint + enrichment helpers
# ------------------------
def _pick_links_from_ctx(ctx: dict, max_links: int = 3) -> list[dict]:
    if not isinstance(ctx, dict):
        return []
    buckets = [ctx.get('web') or [], ctx.get('discussions') or []]
    out = []
    for bucket in buckets:
        for r in bucket:
            url = (r or {}).get('url')
            title = (r or {}).get('title')
            if not url or not title:
                continue
            out.append({
                'title': title,
                'url': url,
                'publisher': (r or {}).get('publisher'),
                'sentiment': (r or {}).get('sentiment'),
                'description': (r or {}).get('snippet') or (r or {}).get('description')
            })
            if len(out) >= max_links:
                return out
    return out

def _inject_links_from_search_context(news: dict, search_context: dict, max_links: int = 3) -> dict:
    if not isinstance(news, dict) or not isinstance(search_context, dict):
        return news
    # Build a lowercase key map for robust lookups
    sc_map = { (k or '').strip().lower(): v for k, v in search_context.items() }

    # Attach per-player links
    for sec in news.get('sections', []) or []:
        for it in sec.get('items', []) or []:
            pname = (it.get('player_name') or it.get('player') or '').strip()
            key = pname.lower()
            ctx = sc_map.get(key)
            if not ctx:
                # try a relaxed match without diacritics/extra spaces
                for k in sc_map.keys():
                    if k.replace(' ', '') == key.replace(' ', ''):
                        ctx = sc_map.get(k)
                        break
            if not ctx:
                continue
            links = it.get('links') or []
            if not links:
                picked = _pick_links_from_ctx(ctx, max_links=max_links)
                if picked:
                    it['links'] = picked

    # Build fan_pulse from discussions if missing
    if not news.get('fan_pulse'):
        pulse = []
        for player_name, ctx in search_context.items():
            disc = (ctx or {}).get('discussions') or []
            for r in disc[:2]:  # at most 2 per player
                url = (r or {}).get('url')
                if not url:
                    continue
                host = ''
                try:
                    host = urlparse(url).netloc
                except Exception:
                    pass
                pulse.append({
                    'player': player_name,
                    'forum': host,
                    'quote': (r or {}).get('description') or (r or {}).get('snippet') or (r or {}).get('title') or '',
                    'url': url,
                })
        news['fan_pulse'] = pulse[:8]
    return news

def _append_internet_section(news: dict, search_context: dict, max_items_per_player: int = 2) -> dict:
    try:
        items = []
        for player_name, ctx in (search_context or {}).items():
            # Prefer web links. Fall back to news/discussions if web is empty
            candidates = list(ctx.get('web') or [])
            if not candidates:
                candidates = list(ctx.get('news') or []) + list(ctx.get('discussions') or [])
            links: list[str] = []
            for r in candidates:
                try:
                    u = (r or {}).get('url')
                except Exception:
                    u = None
                if not u:
                    continue
                links.append(u)
                if len(links) >= max_items_per_player:
                    break
            if links:
                items.append({'player_name': to_initial_last(player_name), 'links': links})
        if items:
            sections = news.get('sections') or []
            sections.append({'title': 'What the Internet is Saying', 'items': items})
            news['sections'] = sections
    except Exception:
        pass
    return news

# Wrap python tools for Agents SDK
fetch_weekly_report_tool = FunctionTool(
    name="fetch_weekly_report",
    description="Get the weekly loans performance summary for a parent club for the week containing target_date.",
    params_json_schema=FetchWeeklyReportArgs.model_json_schema(),
    on_invoke_tool=fetch_weekly_report,
)

persist_newsletter_tool = FunctionTool(
    name="persist_newsletter",
    description="Persist a generated JSON newsletter for a team and issue_date.",
    params_json_schema=PersistNewsletterArgs.model_json_schema(),
    on_invoke_tool=persist_newsletter,
)

# ---------- Agent factory (API-only) ----------

def build_weekly_agent() -> Agent:
    return Agent(
        name="Weekly Loans Newsletter Agent",
        instructions=SYSTEM_INSTRUCTIONS,
        model="gpt-4.1-mini",
        tools=[fetch_weekly_report_tool, persist_newsletter_tool],
    )

# ---------- Orchestration entrypoint ----------

async def generate_weekly_newsletter(team_db_id: int, target_date: date, force_refresh: bool = False) -> Dict[str, Any]:
    # Precompute week window and report
    week_start, week_end = monday_range(target_date)
    news_end = week_end + timedelta(days=1)
    
    if force_refresh:
        api_client.clear_stats_cache()
        
    report = await fetch_weekly_report(ctx=None, args={
        "parent_team_db_id": team_db_id,
        "target_date": target_date.isoformat(),
    })
    # Build queries and gather web+news
    # Build both id- and name-indexed search contexts for deterministic merging
    run_context = RunContextWrapper(context=None)
    agent = build_weekly_agent()
    search_context: dict[str, dict[str, list[dict]]] = {}
    search_context_by_id: dict[str, dict[str, list[dict]]] = {}
    loanees = (report.get("loanees") or []) if isinstance(report, dict) else []
    if len(loanees) == 0:
        raise NoActiveLoaneesError(team_db_id, week_start, week_end)
    full_name_cache: dict[str, str] = {}
    player_lookup: dict[str, list[dict[str, Any]]] = {}

    # Get team info for localization
    team = Team.query.get(team_db_id)
    # Use related League if available; fall back to default localization
    league_name = (team.league.name if (team and getattr(team, 'league', None)) else "Premier League")
    localization = get_league_localization(league_name)

    # Compute freshness range once for this run
    freshness_range = freshness_range_str(week_start, news_end)

    for loanee in loanees:
        player = loanee.get("player_name") or loanee.get("name") or ""
        pid = str(loanee.get("player_api_id") or loanee.get("player_id") or "")
        full_name = loanee.get("player_full_name") or player
        if pid and not full_name:
            try:
                # Fetch once per player for better queries
                if pid not in full_name_cache:
                    pdata = api_client.get_player_by_id(int(pid))
                    nm = (pdata or {}).get('player', {}).get('name') if isinstance(pdata, dict) else None
                    if nm:
                        full_name_cache[pid] = nm
                full_name = full_name_cache.get(pid) or player
            except Exception:
                full_name = player
        loan_team = loanee.get("loan_team_name") or loanee.get("loan_team") or ""
        if not player:
            continue
        try:
            player_id_entry = int(pid) if pid else None
        except Exception:
            player_id_entry = None

        if player_id_entry is not None:
            entry = {
                'player_id': player_id_entry,
                'loan_team_api_id': loanee.get('loan_team_api_id') or loanee.get('loan_team_id'),
                'loan_team_id': loanee.get('loan_team_db_id') or loanee.get('loan_team_id'),
                'loan_team_name': loan_team,
            }

            def _register_alias(alias: str | None) -> None:
                key = _normalize_player_key(alias or '')
                if key:
                    player_lookup.setdefault(key, []).append(entry)

            _register_alias(player)
            _register_alias(full_name)
            _register_alias(to_initial_last(player))
            _register_alias(to_initial_last(full_name or player))
        items_web: list[dict] = []
        items_news: list[dict] = []

        # Enhanced per-player queries with localization
        # Strategy:
        #  - Prefer Full Name; fall back to display name
        #  - Query both web and news
        #  - Do not require opponent; add a weekly player+team query regardless
        #  - Widen freshness if strict pass yields no results
        intents_expr = "player ratings OR match reaction OR match report OR fan reaction OR analysis"

        # Build strict queries (week window)
        qname = (full_name or player).strip()
        match_queries: list[str] = []
        for m in loanee.get("matches", []) or []:
            opp = (m.get("opponent") or "").strip()
            comp = (m.get("competition") or "").strip()
            if opp and comp:
                match_queries.append(f'"{qname}" {loan_team} {opp} {comp} ({intents_expr})')
        # Weekly fallback queries (even if no matches/opponents present)
        weekly_queries = [
            f'"{qname}" {loan_team} player ratings',
            f'"{qname}" {loan_team} match report',
            f'{qname} {loan_team} fan reaction',
        ]

        # Strict pass (API-only): week freshness, discussions+web for web; include news
        strict_queries = (match_queries[:3] or []) + weekly_queries[:2]
        for query in strict_queries:
            # Convert freshness range to since/until
            try:
                since, until = freshness_range.split("to", 1)
            except Exception:
                since, until = week_start.isoformat(), news_end.isoformat()
            merged = brave_api.brave_search(
                query,
                since,
                until,
                country=localization.get('country', 'GB'),
                search_lang=localization.get('search_lang', 'en'),
                ui_lang=localization.get('ui_lang', 'en-GB'),
                result_filter=["discussions", "web"],
            )
            _log_sample("strict", pid, query, merged)
            # Split back into web/news buckets
            web_results = [r for r in merged if r.get("source") == "web"]
            news_results = [r for r in merged if r.get("source") == "news"]
            items_web.extend(web_results)
            items_news.extend(news_results)

        # Widened pass: if still empty, broaden freshness and drop result_filter
        if not (items_web or items_news) and (ALLOW_WIDE_FRESHNESS or (not STRICT_FRESHNESS)):
            wide_range = freshness_range_str(week_start - timedelta(days=14), week_end + timedelta(days=3))
            wide_queries = weekly_queries[:2] or [f'"{qname}" {loan_team}']
            for query in wide_queries:
                try:
                    s2, u2 = wide_range.split("to", 1)
                except Exception:
                    s2, u2 = (week_start - timedelta(days=14)).isoformat(), (week_end + timedelta(days=3)).isoformat()
                merged_wide = brave_api.brave_search(
                    query,
                    s2,
                    u2,
                    country=localization.get('country', 'GB'),
                    search_lang=localization.get('search_lang', 'en'),
                    ui_lang=localization.get('ui_lang', 'en-GB'),
                    result_filter=["discussions", "web"],
                )
                _log_sample("wide", pid, query, merged_wide)
                items_web.extend([r for r in merged_wide if r.get("source") == "web"])
                items_news.extend([r for r in merged_wide if r.get("source") == "news"])

        # Categorize and deduplicate results
        categorized_results = categorize_and_deduplicate_results(items_web, items_news)
        # Post-filter to remove out-of-window/off-topic/noisy hits
        categorized_results = _filter_hits_for_player(
            categorized_results,
            player_name=full_name or player,
            loan_team=loan_team,
            week_start=week_start,
            week_end=week_end,
        )
        if DEBUG_MCP:
            logging.getLogger(__name__).info(
                "BRAVE categorized | pid=%s | web=%d news=%d disc=%d vids=%d",
                pid,
                len(categorized_results["web"]),
                len(categorized_results["news"]),
                len(categorized_results["discussions"]),
                len(categorized_results["videos"]),
            )

        display = to_initial_last(player).strip()
        ctx_row = {
            "web": categorized_results["web"],
            "news": categorized_results["news"],
            "discussions": categorized_results["discussions"],
            "videos": categorized_results["videos"],
            "summaries": categorized_results["summaries"],
            "sentiment_breakdown": categorized_results["sentiment_breakdown"]
        }
        if pid:
            search_context_by_id[pid] = {"display": display, **ctx_row}
        search_context[display] = ctx_row

    # Cache latest context for the persist tool (in case the agent omits it)
    try:
        global _LATEST_SEARCH_CONTEXT
        _LATEST_SEARCH_CONTEXT = search_context
    except Exception:
        pass
    _set_latest_player_lookup(player_lookup)

    # High-level instruction payload (add What the Internet is Saying section seed)
    user_msg = {
        "task": "compose_and_persist_weekly_newsletter",
        "team_db_id": team_db_id,
        "target_date": target_date.isoformat(),
        "report": report,
        "search_context": search_context,
        "search_context_by_id": search_context_by_id if DEBUG_MCP else None,
        "guidance": {
            "search_context_precomputed": True,
            "max_links_per_player": 3
        }
    }

    # Run with brief retries to handle API hiccups
    def _has_rate_limit(items) -> bool:
        try:
            text = "\n".join(str(getattr(i, "raw_item", i)) for i in items)
        except Exception:
            text = "\n".join(str(i) for i in items)
        return ("Rate limit" in text) or ("429" in text)

    max_attempts = 3
    delay = 0.6
    for attempt in range(max_attempts):
        result = await Runner.run(
            starting_agent=agent,
            input=json.dumps(user_msg),
            context=run_context,
        )
        if not _has_rate_limit(result.new_items):
            break
        if attempt < max_attempts - 1:
            await asyncio.sleep(delay * (2 ** attempt) + random.random()*0.4)

    # last_response_id and final_output are the modern equivalents of run_id/output
    run_id = result.last_response_id
    raw_final_output = result.final_output
    final = _to_jsonable(raw_final_output)

    # collect tool call events; result.new_items is a list of RunItem instances
    tool_events = []
    for item in result.new_items:
        if isinstance(item, ToolCallItem):
            tool_events.append(_to_jsonable(item.raw_item))
        elif isinstance(item, ToolCallOutputItem):
            tool_events.append(_to_jsonable(item.output))

    # If the agent did not invoke persist_newsletter, persist as a safety net
    invoked_tool_names = set()
    for ev in tool_events:
        if isinstance(ev, dict) and ev.get("name"):
            invoked_tool_names.add(ev["name"])

    persisted_row: Dict[str, Any] | None = None
    if "persist_newsletter" not in invoked_tool_names:
        try:
            # Parse final content as JSON if it's a string-like content
            content_json: Any
            if isinstance(raw_final_output, str):
                try:
                    content_json = json.loads(raw_final_output)
                except Exception:
                    import re
                    blocks = re.findall(r"\{(?:.|\n)*\}", raw_final_output)
                    content_json = json.loads(blocks[0]) if blocks else {}
            else:
                content_json = raw_final_output
            # Merge Brave search links and fan pulse if missing
            try:
                content_json = _inject_links_from_search_context(content_json, search_context, max_links=3)
            except Exception:
                pass
            # Sanitize strings before further processing
            content_json = _sanitize(content_json)
            # Lint/enrich even on fallback
            try:
                content_json = lint_and_enrich(content_json)
            except Exception:
                pass
            # Validate player stats match source data
            try:
                validation_warnings = _validate_player_stats_match(content_json, report)
                if validation_warnings:
                    logger.warning(f"⚠️  Player stats validation warnings:")
                    for warning in validation_warnings:
                        logger.warning(f"   {warning}")
                else:
                    logger.info("✅ Player stats validation passed - all stats match source data")
            except Exception as e:
                logger.warning(f"Failed to validate player stats: {e}")
            args = {
                "team_db_id": team_db_id,
                "content_json": content_json,
                "issue_date": target_date.isoformat(),
                "search_context": search_context,
                "player_lookup": player_lookup,
            }
            persisted_row = await persist_newsletter(ctx=None, args=args)
        except Exception:
            persisted_row = None

    return _to_jsonable({
        "last_response_id": run_id,
        "final_output": final,
        "tool_events": tool_events,
        "persisted_via_fallback": persisted_row is not None,
        "persisted_newsletter": persisted_row,
    })
    # end generate_weekly_newsletter

# Compatibility wrappers (legacy names)
async def generate_weekly_newsletter_with_mcp(team_db_id: int, target_date: date, force_refresh: bool = False) -> Dict[str, Any]:
    return await generate_weekly_newsletter(team_db_id, target_date, force_refresh)

def generate_weekly_newsletter_with_mcp_sync(team_db_id: int, target_date: date, force_refresh: bool = False) -> Dict[str, Any]:
    return asyncio.run(generate_weekly_newsletter(team_db_id, target_date, force_refresh))

# ------------------------
# Lint + enrichment helpers
# ------------------------
def _display_name(name: str) -> str:
    """Return first-initial + last-name when possible, preserving diacritics."""
    return to_initial_last(name)


def _player_profile_store() -> tuple[Any | None, type[Player] | None]:
    try:
        return db.session, Player
    except Exception:
        return None, Player


def _team_profile_store() -> tuple[Any | None, type[TeamProfile] | None]:
    try:
        return db.session, TeamProfile
    except Exception:
        return None, TeamProfile


def _persist_player_profile(payload: dict | None) -> None:
    if not isinstance(payload, dict):
        return
    player_block = payload.get('player') or {}
    player_id = player_block.get('id')
    if not player_id:
        return
    session, player_model = _player_profile_store()
    if session is None or player_model is None:
        return

    try:
        record = session.query(player_model).filter_by(player_id=player_id).one_or_none()
        if record is None:
            record = player_model(player_id=player_id)
            session.add(record)

        def _set(attr: str, value):
            if value is not None and value != '':
                setattr(record, attr, value)

        _set('name', player_block.get('name'))
        _set('firstname', player_block.get('firstname'))
        _set('lastname', player_block.get('lastname'))
        _set('nationality', player_block.get('nationality'))
        _set('age', player_block.get('age'))
        _set('height', player_block.get('height'))
        _set('weight', player_block.get('weight'))
        _set('photo_url', player_block.get('photo'))

        stats = payload.get('statistics') or []
        if stats:
            games = (stats[0] or {}).get('games') or {}
            _set('position', games.get('position'))

        if record.created_at is None:
            record.created_at = datetime.now(timezone.utc)

        session.commit()
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass


def _player_photo_for(player_id: Any) -> str | None:
    """Lookup and cache a player's headshot URL by API-Football id."""
    if player_id is None:
        return None
    try:
        key = int(player_id)
    except (TypeError, ValueError):
        return None

    if key in _PLAYER_PHOTO_CACHE:
        return _PLAYER_PHOTO_CACHE[key]

    session, player_model = _player_profile_store()
    if session is not None and player_model is not None:
        try:
            existing = session.query(player_model).filter_by(player_id=key).one_or_none()
        except Exception:
            existing = None
        if existing and existing.photo_url:
            _PLAYER_PHOTO_CACHE[key] = existing.photo_url
            return existing.photo_url

    payload = None
    photo_url = None
    try:
        payload = api_client.get_player_by_id(key)
        photo_url = ((payload or {}).get('player') or {}).get('photo')
    except Exception:
        photo_url = None

    if payload:
        _persist_player_profile(payload)
        if photo_url is None:
            session, player_model = _player_profile_store()
            if session is not None and player_model is not None:
                try:
                    refreshed = session.query(player_model).filter_by(player_id=key).one_or_none()
                except Exception:
                    refreshed = None
                if refreshed and refreshed.photo_url:
                    photo_url = refreshed.photo_url

    _PLAYER_PHOTO_CACHE[key] = photo_url
    return photo_url


def _persist_team_profile(payload: dict | None) -> TeamProfile | None:
    if not isinstance(payload, dict):
        return None
    team_block = payload.get('team') or {}
    team_id = team_block.get('id')
    if not team_id:
        return None
    session, profile_model = _team_profile_store()
    if session is None or profile_model is None:
        return None

    try:
        record = session.query(profile_model).filter_by(team_id=team_id).one_or_none()
        if record is None:
            record = profile_model(team_id=team_id, created_at=datetime.now(timezone.utc))
            session.add(record)

        def _set(attr: str, value):
            if value is not None and value != '':
                setattr(record, attr, value)

        _set('name', team_block.get('name'))
        _set('code', team_block.get('code'))
        _set('country', team_block.get('country'))
        _set('founded', team_block.get('founded'))
        _set('is_national', team_block.get('national'))
        _set('logo_url', team_block.get('logo'))

        venue_block = payload.get('venue') or {}
        _set('venue_id', venue_block.get('id'))
        _set('venue_name', venue_block.get('name'))
        _set('venue_address', venue_block.get('address'))
        _set('venue_city', venue_block.get('city'))
        _set('venue_capacity', venue_block.get('capacity'))
        _set('venue_surface', venue_block.get('surface'))
        _set('venue_image', venue_block.get('image'))

        record.updated_at = datetime.now(timezone.utc)

        session.commit()

        # Also keep Team table in sync when possible
        try:
            team_row = session.query(Team).filter_by(team_id=team_id).one_or_none()
            if team_row and team_block.get('logo') and not team_row.logo:
                team_row.logo = team_block.get('logo')
                session.commit()
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass

        _TEAM_LOGO_CACHE[team_id] = record.logo_url
        return record
    except Exception:
        try:
            session.rollback()
        except Exception:
            pass
    return None


def _resolve_team_name_central(team_api_id: int) -> str:
    """Resolve team name via centralized resolver (Team → TeamProfile → API)."""
    from src.utils.team_resolver import resolve_team_name
    return resolve_team_name(team_api_id)


def _team_logo_for_team(team_api_id: Any, *, fallback_name: str | None = None) -> str | None:
    if team_api_id is None:
        return None
    try:
        key = int(team_api_id)
    except (TypeError, ValueError):
        return None

    if key in _TEAM_LOGO_CACHE:
        return _TEAM_LOGO_CACHE[key]

    session, profile_model = _team_profile_store()
    if session is not None and profile_model is not None:
        try:
            existing = session.query(profile_model).filter_by(team_id=key).one_or_none()
        except Exception:
            existing = None
        if existing and existing.logo_url:
            _TEAM_LOGO_CACHE[key] = existing.logo_url
            return existing.logo_url

    # If Team row already has a logo, use it (and persist profile if missing)
    try:
        team_row = db.session.query(Team).filter_by(team_id=key).one_or_none()
    except Exception:
        team_row = None
    if team_row and team_row.logo:
        if session is not None and profile_model is not None:
            existing = session.query(profile_model).filter_by(team_id=key).one_or_none()
            if existing is None:
                try:
                    record = profile_model(
                        team_id=key,
                        name=team_row.name or fallback_name or _resolve_team_name_central(key),
                        code=team_row.code,
                        country=team_row.country,
                        founded=team_row.founded,
                        is_national=team_row.national,
                        logo_url=team_row.logo,
                        venue_name=team_row.venue_name,
                        venue_address=team_row.venue_address,
                        venue_city=team_row.venue_city,
                        venue_capacity=team_row.venue_capacity,
                        created_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                    )
                    session.add(record)
                    session.commit()
                except Exception:
                    try:
                        session.rollback()
                    except Exception:
                        pass
        _TEAM_LOGO_CACHE[key] = team_row.logo
        return team_row.logo

    payload = None
    try:
        payload = api_client.get_team_by_id(key)
    except Exception:
        payload = None

    logo = None
    if payload:
        record = _persist_team_profile(payload)
        if record and record.logo_url:
            logo = record.logo_url

    _TEAM_LOGO_CACHE[key] = logo
    return logo


def _team_logo_for_player(player_id: Any, loan_team_name: str | None = None) -> str | None:
    if player_id is None:
        return None
    try:
        pid = int(player_id)
    except (TypeError, ValueError):
        return None

    tp: TrackedPlayer | None = None
    try:
        tp = (
            db.session.query(TrackedPlayer)
            .filter(TrackedPlayer.player_api_id == pid, TrackedPlayer.is_active == True)
            .order_by(TrackedPlayer.updated_at.desc())
            .first()
        )
    except Exception:
        tp = None

    team_api_id = None
    if tp and tp.current_club_api_id:
        team_api_id = tp.current_club_api_id

    if team_api_id is None and loan_team_name:
        try:
            team_row = (
                db.session.query(Team)
                .filter(Team.name == loan_team_name)
                .order_by(Team.updated_at.desc())
                .first()
            )
            if team_row and team_row.team_id:
                team_api_id = team_row.team_id
        except Exception:
            pass

    return _team_logo_for_team(team_api_id, fallback_name=loan_team_name)

def _fix_minutes_language(item: dict) -> None:
    """Normalize phrasing based on minutes to avoid contradictions.
    
    Note: If the summary already contains "not in the matchday squad" or 
    similar language, we preserve it - don't blindly replace with "unused substitute".
    """
    s = item.get("stats", {}) or {}
    mins = int(s.get("minutes", 0) or 0)
    wsum = item.get("week_summary", "") or ""
    notes = item.get("match_notes", []) or []

    if mins == 0:
        # Check if summary already indicates player was not in squad
        # If so, don't replace with "unused substitute"
        not_in_squad_phrases = [
            "not in the matchday squad",
            "not in matchday squad",
            "not selected",
            "not in the squad",
            "unavailable",
            "injured",
            "out injured",
        ]
        already_indicates_not_in_squad = any(phrase in wsum.lower() for phrase in not_in_squad_phrases)
        
        if not already_indicates_not_in_squad:
            # Only replace misleading phrases if we haven't already indicated non-selection
            for token in ["Appeared", "Used as substitute", "Came on", "Substitute in"]:
                if token in wsum:
                    wsum = wsum.replace(token, "Unused substitute")
        
        # Always fix "Started" claims when minutes=0
        if "Started" in wsum or "Started and played" in wsum:
            wsum = wsum.replace("Started and played", "Did not play")
            wsum = wsum.replace("Started", "Did not play")
        
        # Fix notes too
        new_notes = []
        for n in notes:
            n2 = n
            for token in ["Came on", "Substitute in"]:
                if token in n2:
                    n2 = n2.replace(token, "Unused substitute")
            new_notes.append(n2)
        notes = new_notes

    item["week_summary"] = wsum
    item["match_notes"] = notes

def strip_diacritics(s: str) -> str:
    try:
        return ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    except Exception:
        return s

def to_initial_last(full: str) -> str:
    if not full:
        return full
    parts = str(full).split()
    if len(parts) == 1:
        return parts[0]
    first, last = parts[0], parts[-1]
    if not first:
        return last
    return f"{first[0]}. {last}"

def name_variants(full_name: str | None, display: str) -> list[str]:
    """Return name variants prioritized for search: full name, display, last name, plus ASCII forms."""
    import unicodedata as _ud
    def _ascii(s: str) -> str:
        try:
            return ''.join(c for c in _ud.normalize('NFKD', s) if not _ud.combining(c))
        except Exception:
            return s
    last = ((full_name or display or '').split()[-1] if (full_name or display) else '').strip()
    base = []
    for n in [full_name or '', display or '', last or '']:
        n = n.strip()
        if not n:
            continue
        base.append(n)
        base.append(_ascii(n))
    out: list[str] = []
    seen: set[str] = set()
    for n in base:
        if n and n not in seen:
            out.append(n)
            seen.add(n)
    return out

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

def _sanitize_value_with_count(text: str) -> tuple[str, int]:
    if not isinstance(text, str):
        return text, 0
    cleaned = _CONTROL_CHARS_RE.sub('', text)
    return cleaned, len(text) - len(cleaned)

def _sanitize_with_count(obj: Any) -> tuple[Any, int]:
    removed = 0
    if obj is None:
        return obj, 0
    if isinstance(obj, str):
        return _sanitize_value_with_count(obj)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            vv, rr = _sanitize_with_count(v)
            out[k] = vv
            removed += rr
        return out, removed
    if isinstance(obj, list):
        out_list = []
        for v in obj:
            vv, rr = _sanitize_with_count(v)
            out_list.append(vv)
            removed += rr
        return out_list, removed
    return obj, 0

def _canonicalize_name(name: str) -> str:
    """
    Canonicalize player names to fix common misidentifications.
    Maps incorrect/alternate names to the correct canonical names.
    """
    mapping = {
        "Ellis Galbraith": "Ethan Galbraith",
        "Harry Mejbri": "Hannibal Mejbri",
        "Hakeem Amass": "Harry Amass",  # Fix AI hallucination of "Hakeem" from "H. Amass"
    }
    return mapping.get(name, name)

def _score_player(item: dict) -> float:
    s = item.get("stats", {}) or {}
    return 5*(s.get("goals",0) or 0) + 3*(s.get("assists",0) or 0) + (s.get("minutes",0) or 0)/90.0 - 1*(s.get("yellows",0) or 0) - 3*(s.get("reds",0) or 0)

def _validate_player_stats_match(news: dict, report: dict) -> list[str]:
    """
    Validate that each player's stats in the newsletter match the source data.
    Returns list of validation warnings.
    """
    warnings = []
    
    # Build lookup of source stats by player_id
    source_stats = {}
    for loanee in report.get("loanees", []) or []:
        pid = loanee.get("player_api_id")
        if pid:
            source_stats[int(pid)] = {
                "player_name": loanee.get("player_name"),
                "totals": loanee.get("totals", {}),
            }
    
    # Track stats to detect duplicates (same stats for different players)
    stats_signatures = {}  # signature -> list of player_ids
    
    # Check each item in newsletter
    for sec in news.get("sections", []) or []:
        for it in sec.get("items", []) or []:
            pid = it.get("player_id")
            if not pid:
                warnings.append(f"Player '{it.get('player_name')}' missing player_id - cannot validate")
                continue
            
            try:
                pid_int = int(pid)
            except (TypeError, ValueError):
                warnings.append(f"Player '{it.get('player_name')}' has invalid player_id: {pid}")
                continue
            
            # Check if stats match source
            source = source_stats.get(pid_int)
            if source:
                item_stats = it.get("stats", {})
                source_totals = source["totals"]
                
                # Validate key metrics
                for key in ["goals", "assists", "minutes"]:
                    item_val = item_stats.get(key, 0)
                    source_val = source_totals.get(key, 0)
                    if item_val != source_val:
                        warnings.append(
                            f"MISMATCH: Player '{it.get('player_name')}' (ID:{pid}) has {key}={item_val} "
                            f"but source has {key}={source_val}"
                        )
                
                # Check if match_notes mention stats that don't exist
                match_notes = it.get("match_notes", [])
                for note in match_notes:
                    note_lower = note.lower()
                    # Check for assist mentions when assists = 0
                    if "assist" in note_lower and item_stats.get("assists", 0) == 0:
                        warnings.append(
                            f"CONTRADICTION: '{it.get('player_name')}' (ID:{pid}) match_notes say '{note}' "
                            f"but stats show 0 assists"
                        )
                    # Check for goal mentions when goals = 0
                    if "goal" in note_lower and "conceded" not in note_lower and item_stats.get("goals", 0) == 0:
                        warnings.append(
                            f"CONTRADICTION: '{it.get('player_name')}' (ID:{pid}) match_notes say '{note}' "
                            f"but stats show 0 goals"
                        )
            
            # Check for duplicate stats (identical stats for different players)
            item_stats = it.get("stats", {})
            if item_stats and item_stats.get("minutes", 0) > 0:
                # Create signature from key stats
                sig = (
                    item_stats.get("minutes", 0),
                    item_stats.get("goals", 0),
                    item_stats.get("assists", 0),
                    item_stats.get("shots_total", 0),
                    item_stats.get("passes_total", 0),
                )
                if sig != (0, 0, 0, 0, 0):  # Ignore all-zero stats
                    player_name = it.get("player_name", "Unknown")
                    if sig in stats_signatures:
                        stats_signatures[sig].append((pid_int, player_name))
                    else:
                        stats_signatures[sig] = [(pid_int, player_name)]
    
    # Report duplicate stats
    for sig, players in stats_signatures.items():
        if len(players) > 1:
            player_list = ", ".join([f"{name} (ID:{pid})" for pid, name in players])
            warnings.append(
                f"DUPLICATE STATS: Multiple players have identical stats {sig}: {player_list}. "
                f"This likely indicates a data error where one player's stats were assigned to another."
            )
    
    return warnings

def lint_and_enrich(news: dict) -> dict:
    if not isinstance(news, dict):
        return news

    player_ids: set[int] = set()

    def _lint_item_list(item_list: list, seen: set[str]) -> list:
        """Normalize, enrich, and dedup a list of player items."""
        out = []
        for it in item_list or []:
            nm = _display_name(it.get("player_name"))
            it["player_name"] = nm
            try:
                st = it.get("stats")
                if isinstance(st, str):
                    games = int(re.search(r"(\d+)\s*game", st) .group(1)) if re.search(r"(\d+)\s*game", st) else 0
                    minutes = int(re.search(r"(\d+)\s*minute", st).group(1)) if re.search(r"(\d+)\s*minute", st) else 0
                    goals = int(re.search(r"(\d+)\s*goal", st) .group(1)) if re.search(r"(\d+)\s*goal", st) else 0
                    assists = int(re.search(r"(\d+)\s*assist", st).group(1)) if re.search(r"(\d+)\s*assist", st) else 0
                    yellows = int(re.search(r"(\d+)\s*yellow", st).group(1)) if re.search(r"(\d+)\s*yellow", st) else 0
                    reds = int(re.search(r"(\d+)\s*red", st) .group(1)) if re.search(r"(\d+)\s*red", st) else 0
                    it["stats"] = {
                        "games": games, "minutes": minutes, "goals": goals,
                        "assists": assists, "yellows": yellows, "reds": reds,
                    }
            except Exception:
                pass
            _fix_minutes_language(it)
            pid = it.get("player_id")
            if pid is not None:
                try:
                    player_ids.add(int(pid))
                except (TypeError, ValueError):
                    pass
            if not it.get("player_photo"):
                photo_url = _player_photo_for(pid)
                if photo_url:
                    it["player_photo"] = photo_url
            team_logo = _team_logo_for_player(pid, loan_team_name=it.get("loan_team") or it.get("loan_team_name"))
            if team_logo:
                it["loan_team_logo"] = team_logo
            name_key = strip_diacritics(to_initial_last(it.get("player_name", ""))).lower().replace(' ', '')
            key = f"pid:{pid}" if pid else f"name:{name_key}"
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out

    # normalize display names and de-dupe within each section by stable identity
    for sec in news.get("sections", []) or []:
        seen: set[str] = set()
        # Handle subsectioned sections (On Loan, Academy Rising)
        if "subsections" in sec and isinstance(sec.get("subsections"), list):
            for sub in sec["subsections"]:
                if isinstance(sub.get("items"), list):
                    sub["items"] = _lint_item_list(sub["items"], seen)
            continue
        sec["items"] = _lint_item_list(sec.get("items", []), seen)

    sofascore_lookup: dict[int, int] = {}
    if player_ids:
        try:
            records = Player.query.filter(Player.player_id.in_(player_ids)).all()
            sofascore_lookup = {
                int(rec.player_id): int(rec.sofascore_id)
                for rec in records
                if getattr(rec, "sofascore_id", None)
            }
        except Exception:
            sofascore_lookup = {}

    if sofascore_lookup:
        def _enrich_sofascore(items: list) -> None:
            for it in items or []:
                pid = it.get("player_id")
                if pid is None or it.get("sofascore_player_id"):
                    continue
                try:
                    pid_int = int(pid)
                except (TypeError, ValueError):
                    continue
                sofascore_value = sofascore_lookup.get(pid_int)
                if sofascore_value:
                    it["sofascore_player_id"] = sofascore_value

        for sec in news.get("sections", []) or []:
            if "subsections" in sec and isinstance(sec.get("subsections"), list):
                for sub in sec["subsections"]:
                    _enrich_sofascore(sub.get("items", []))
            else:
                _enrich_sofascore(sec.get("items", []))

    # Fallback (opt-in): attach Sofascore via exact name match when player_id is missing
    if ENABLE_SOFA_NAME_FALLBACK:
        try:
            names_needed: set[str] = set()
            for sec in news.get("sections", []) or []:
                for it in sec.get("items", []) or []:
                    if it.get("sofascore_player_id"):
                        continue
                    if it.get("player_id") is not None:
                        continue
                    name = (it.get("player_name") or "").strip()
                    if name:
                        names_needed.add(name)
            name_map: dict[str, int] = {}
            for nm in names_needed:
                try:
                    rec = (
                        db.session.query(Player)
                        .filter(func.lower(Player.name) == nm.lower())
                        .filter(Player.sofascore_id.isnot(None))
                        .first()
                    )
                except Exception:
                    rec = None
                if rec and getattr(rec, "sofascore_id", None):
                    name_map[nm] = int(rec.sofascore_id)
            if name_map:
                for sec in news.get("sections", []) or []:
                    for it in sec.get("items", []) or []:
                        if it.get("sofascore_player_id"):
                            continue
                        if it.get("player_id") is not None:
                            continue
                        nm = (it.get("player_name") or "").strip()
                        sv = name_map.get(nm)
                        if sv:
                            it["sofascore_player_id"] = sv
        except Exception:
            pass

    # recompute highlights from actual stats
    items = [it for sec in news.get("sections", []) or [] for it in sec.get("items", []) or []]
    top = sorted(items, key=_score_player, reverse=True)[:3]
    news["highlights"] = [
        f"{_display_name(it.get('player_name',''))}: {int(it.get('stats',{}).get('goals',0))}G {int(it.get('stats',{}).get('assists',0))}A, {int(it.get('stats',{}).get('minutes',0))}'"
        for it in top
        if it.get('stats')  # Only include items that have stats
    ]

    # by-numbers blocks
    mins_leaders = sorted(items, key=lambda x: int(x.get('stats',{}).get('minutes',0) or 0), reverse=True)[:3]
    ga_leaders = sorted(items, key=lambda x: (int(x.get('stats',{}).get('goals',0) or 0) + int(x.get('stats',{}).get('assists',0) or 0)), reverse=True)[:3]
    news["by_numbers"] = {
        "minutes_leaders": [{"player": _display_name(i.get("player_name")), "minutes": int(i.get("stats",{}).get("minutes",0) or 0)} for i in mins_leaders],
        "ga_leaders": [{"player": _display_name(i.get("player_name")), "g": int(i.get("stats",{}).get("goals",0) or 0), "a": int(i.get("stats",{}).get("assists",0) or 0)} for i in ga_leaders],
    }

    return news

def _inject_links_from_search_context(content_json: dict, search_context: dict | None, max_links: int = 3) -> tuple[dict, bool, int]:
    """Inject up to max_links per player from search_context if links are missing.
    Returns (updated_json, injected_any, total_links_added)."""
    if not isinstance(content_json, dict) or not isinstance(search_context, dict):
        return content_json, False, 0
    added_total = 0
    injected_any = False
    # Build a simple accessor for context lists
    def _ctx_for(name: str) -> dict | None:
        if not name:
            return None
        # Try exact, then initial-last without diacritics
        if name in search_context:
            return search_context.get(name)
        alt = to_initial_last(name)
        return search_context.get(alt)

    for sec in content_json.get("sections", []) or []:
        for it in sec.get("items", []) or []:
            links = it.get("links") or []
            if isinstance(links, list) and len(links) >= max_links:
                continue
            ctx = _ctx_for(it.get("player_name") or "")
            if not isinstance(ctx, dict):
                continue
            urls: list[str] = []
            for bucket in ("web", "news", "discussions", "videos"):
                for r in ctx.get(bucket) or []:
                    url = (r.get("url") if isinstance(r, dict) else None) or None
                    if url and url not in urls:
                        urls.append(url)
                    if len(urls) >= max_links:
                        break
                if len(urls) >= max_links:
                    break
            if urls:
                it["links"] = urls[:max_links]
                added_total += len(urls[:max_links])
                injected_any = True
    return content_json, injected_any, added_total

# ------------------------
# Render helpers (web/email/txt)
# ------------------------

def _render_env() -> Environment:
    templates_path = os.path.join(os.path.dirname(__file__), '..', 'templates')
    templates_path = os.path.abspath(templates_path)
    env = Environment(
        loader=FileSystemLoader(templates_path),
        autoescape=select_autoescape(['html', 'xml'])
    )
    return env

def _default_manage_url() -> str | None:
    base = os.getenv('PUBLIC_BASE_URL', '').rstrip('/')
    if not base:
        return None
    manage_path = os.getenv('PUBLIC_MANAGE_PATH', '/manage')
    return f"{base}{manage_path}"


def _build_template_context(news: dict, team_name: str | None, **kwargs) -> dict:
    ctx = {
        'team_name': team_name or '',
        'team_logo': news.get('team_logo'),
        'title': news.get('title'),
        'range': news.get('range'),
        'summary': news.get('summary'),
        'highlights': news.get('highlights') or [],
        'sections': news.get('sections') or [],
        'toc': news.get('toc') or [],
        'by_numbers': news.get('by_numbers') or {},
        'fan_pulse': news.get('fan_pulse') or [],
        'sofascore_image_template': os.getenv('SOFASCORE_IMAGE_TEMPLATE') or '',
        'manage_url': _default_manage_url(),
        'meta': {},
        # Passthrough for preview/web renders — no base64 embedding needed
        'embed_image': lambda path: path,
    }
    ctx.update(kwargs)
    return ctx

def _render_variants_custom(news: dict, team_name: str | None, commentaries: list, use_snippets: bool = False, render_mode: str = 'web') -> dict:
    """
    Custom renderer that injects specific commentaries into the context.
    Supports 'snippet' mode for emails to keep them short.
    """
    intro = []
    summary = []
    player_map = {}
    headlines = []
    
    # Process commentaries
    for c in commentaries:
        c_dict = c.to_dict()
        if use_snippets and render_mode == 'email':
            # Create snippet
            from src.utils.sanitize import sanitize_plain_text
            # Strip HTML for the excerpt
            plain = sanitize_plain_text(c.content or "")
            snippet = (plain[:280] + '...') if len(plain) > 280 else plain
            
            headlines.append({
                'id': c.id,
                'title': c.title or f"{c.commentary_type.title()} Commentary",
                'author_name': c.author_name,
                'snippet': snippet,
                'type': c.commentary_type,
                # We'll need a proper URL builder eventually, but for now:
                'read_more_url': f"{_default_manage_url() or ''}/newsletters/{news.get('public_slug', 'preview')}#commentary-{c.id}"
            })
        else:
            # Full content
            if c.commentary_type == 'intro':
                intro.append(c_dict)
            elif c.commentary_type == 'summary':
                summary.append(c_dict)
            elif c.commentary_type == 'player' and c.player_id:
                if c.player_id not in player_map:
                    player_map[c.player_id] = []
                player_map[c.player_id].append(c_dict)

    extra_ctx = {
        'intro_commentary': intro,
        'summary_commentary': summary,
        'player_commentary_map': player_map,
        'headlines_commentary': headlines,
        'is_preview': True
    }

    try:
        env = _render_env()
        ctx = _build_template_context(news, team_name, **extra_ctx)
        
        if render_mode == 'email':
            tmpl = env.get_template('newsletter_email.html')
            html = tmpl.render(**ctx)
            return {'email_html': html}
        else:
            tmpl = env.get_template('newsletter_web.html')
            html = tmpl.render(**ctx)
            return {'web_html': html}
            
    except Exception as e:
        logging.getLogger(__name__).error(f"Render custom failed: {e}", exc_info=True)
        return {f'{render_mode}_html': ''}

def _plain_text_from_news_only(news: dict) -> str:
    lines = []
    title = news.get('title') or 'Weekly Loan Update'
    rng = news.get('range') or [None, None]
    summary = news.get('summary') or ''
    lines.append(title)
    if rng and rng[0] and rng[1]:
        lines.append(f"Week: {rng[0]} – {rng[1]}")
    if summary:
        lines.append("")
        lines.append(summary)
    for sec in (news.get('sections') or []):
        st = sec.get('title') or ''
        items = sec.get('items') or []
        if st:
            lines.append("")
            lines.append(st)
        for it in items:
            pname = it.get('player_name') or ''
            loan_team = it.get('loan_team') or it.get('loan_team_name') or ''
            wsum = it.get('week_summary') or ''
            lines.append(f"• {pname} ({loan_team}) – {wsum}")
    return "\n".join(lines).strip() + "\n"

def _render_variants(news: dict, team_name: str | None) -> dict:
    try:
        env = _render_env()
        ctx = _build_template_context(news, team_name)
        # NOTE: Standard _render_variants does NOT inject commentaries from DB.
        # Commentaries are usually injected by the API endpoint or caller if needed.
        # If we want default newsletters to have commentaries, we should modify this 
        # or rely on the caller to pass them via kwargs if we extended the signature.
        # For now, we keep legacy behavior (no auto-fetch here).
        
        web_t = env.get_template('newsletter_web.html')
        email_t = env.get_template('newsletter_email.html')
        web_html = web_t.render(**ctx)
        email_html = email_t.render(**ctx)
    except Exception:
        web_html = ''
        email_html = ''

    # plain-text
    try:
        text_body = _plain_text_from_news_only(news)
    except Exception:
        text_body = ''

    return {
        'web_html': web_html,
        'email_html': email_html,
        'text': text_body,
    }

# Synchronous convenience wrapper (for cron or Flask endpoint)
def generate_weekly_newsletter_with_mcp_sync(team_db_id: int, target_date: date, force_refresh: bool = False) -> Dict[str, Any]:
    return asyncio.run(generate_weekly_newsletter_with_mcp(team_db_id, target_date, force_refresh))
