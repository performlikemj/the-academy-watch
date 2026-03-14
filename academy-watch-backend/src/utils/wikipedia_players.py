"""Utilities for extracting loan information from Wikipedia wikitext."""

from __future__ import annotations

import re
import logging
import os
import time
from functools import lru_cache
from typing import Callable, Dict, Iterable, List, Optional

import requests
from src.mcp.brave import brave_search
from src.services.wikipedia_classifier import classify_loan_row


logger = logging.getLogger(__name__)


WIKITABLE_ROW_PATTERN = re.compile(r"^\|")
DASH_PATTERN = re.compile(r"[\u2012-\u2015]")
REF_PATTERN = re.compile(r"<ref[^>]*>.*?</ref>", re.IGNORECASE)
TEMPLATE_PATTERN = re.compile(r"{{.*?}}", re.DOTALL)
LINK_PATTERN = re.compile(r"\[\[(.*?)]]")
SECTION_PATTERN = re.compile(r"^={2,}\s*(.*?)\s*={2,}$", re.MULTILINE)
FALLBACK_LOAN_PATTERN = re.compile(
    r"(?P<prefix>\d{4}(?:\s*[-/]\s*\d{2})?)\s*-\s*→\s*(?P<club>[^\(\n]+)\s*\(loan\)",
    re.IGNORECASE,
)


@lru_cache(maxsize=1)
def _http() -> requests.Session:
    """Return a shared HTTP session with a polite User-Agent for Wikipedia."""

    session = requests.Session()
    user_agent = os.getenv(
        'WIKIPEDIA_USER_AGENT',
        'AcademyWatchBot/1.0 (+https://theacademywatch.com)'
    )
    session.headers.update({
        'User-Agent': user_agent,
        'Accept': 'application/json',
    })
    return session


def _strip_markup(value: str) -> str:
    value = REF_PATTERN.sub("", value)
    value = TEMPLATE_PATTERN.sub("", value)
    value = LINK_PATTERN.sub(lambda m: m.group(1).split('|')[-1], value)
    value = value.replace("''", "")
    return value.strip()


def _parse_table_rows(wikitext: str) -> Iterable[List[str]]:
    for line in wikitext.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('{') or stripped.startswith('!'):
            continue
        if stripped.startswith('|-'):
            continue
        if not stripped.startswith('|'):
            continue
        cells = [cell.strip() for cell in stripped.lstrip('|').split('||')]
        yield cells


def _parse_season_year(value: str) -> int | None:
    clean = DASH_PATTERN.sub('-', value)
    match = re.search(r"(\d{4})", clean)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _clean_team_cell(value: str) -> str:
    value = value.strip()
    if value.startswith('→'):
        value = value[1:]
    value = value.replace('(loan)', '').strip()
    return _strip_markup(value)


def extract_wikipedia_players(
    wikitext: str,
    season_year: int,
    *,
    player_name: str = 'Unknown Player',
    parent_club_hint: str | None = None,
) -> List[Dict[str, object]]:
    """Extract loan rows from a player's Wikipedia wikitext."""

    parent_club = parent_club_hint or 'Unknown Club'
    results: List[Dict[str, object]] = []

    logger.debug(
        "[wiki-loans] parsing senior career table for player=%s season=%s",
        player_name,
        season_year,
    )

    for cells in _parse_table_rows(wikitext):
        if len(cells) < 2:
            continue
        season_cell, team_cell = cells[0], cells[1]

        season_value = _parse_season_year(season_cell)
        if season_value != season_year:
            # Update parent context even if not in season
            if not team_cell.startswith('→'):
                parent_club = _clean_team_cell(team_cell) or parent_club
            continue

        if team_cell.lstrip().startswith('→'):
            loan_team = _clean_team_cell(team_cell)
            results.append(
                {
                    'player_name': player_name,
                    'parent_club': parent_club,
                    'loan_team': loan_team,
                    'season_year': season_year,
                    'raw_row': ' || '.join(cells),
                }
            )
        else:
            parent_club = _clean_team_cell(team_cell) or parent_club

    normalized_text = DASH_PATTERN.sub('-', wikitext)
    for match in FALLBACK_LOAN_PATTERN.finditer(normalized_text):
        prefix = match.group('prefix') or ''
        prefix_year = _parse_season_year(prefix)
        if prefix_year != season_year:
            continue
        loan_team = _clean_team_cell(match.group('club'))
        results.append(
            {
                'player_name': player_name,
                'parent_club': parent_club,
                'loan_team': loan_team,
                'season_year': season_year,
                'raw_row': match.group(0).strip(),
            }
        )

    # Deduplicate by (player, loan_team, season)
    dedup: Dict[tuple, Dict[str, object]] = {}
    for row in results:
        key = (row['player_name'], row['loan_team'], row['season_year'])
        dedup[key] = row
    if results:
        logger.info(
            "[wiki-loans] extracted %d loan rows for player=%s season=%s",
            len(dedup),
            player_name,
            season_year,
        )
    return list(dedup.values())


@lru_cache(maxsize=64)
def fetch_wikitext(title: str) -> str:
    """Fetch raw wikitext for a given Wikipedia page title."""

    endpoint = "https://en.wikipedia.org/w/api.php"
    params = {
        'action': 'parse',
        'page': title,
        'prop': 'wikitext',
        'format': 'json',
    }

    response = _http().get(endpoint, params=params, timeout=10)
    response.raise_for_status()
    payload = response.json()
    if 'error' in payload:
        raise RuntimeError(f"Wikipedia error for '{title}': {payload['error']}")
    wikitext = payload.get('parse', {}).get('wikitext', {}).get('*', '')
    if not isinstance(wikitext, str):
        logger.warning("[wiki-loans] empty wikitext for title=%s", title)
        return ''
    logger.debug("[wiki-loans] fetched wikitext for title=%s (len=%d)", title, len(wikitext))
    return wikitext


@lru_cache(maxsize=256)
def search_wikipedia_title(query: str, *, context: str = '') -> Optional[str]:
    """Return the best matching Wikipedia page title for a query."""

    if not query:
        return None

    endpoint = "https://en.wikipedia.org/w/api.php"
    search_query = f"{query} {context}".strip()
    params = {
        'action': 'query',
        'list': 'search',
        'srsearch': search_query,
        'srlimit': 1,
        'format': 'json',
        'origin': '*',
    }

    logger.info("[wiki-loans] Wikipedia search query='%s' context='%s'", query, context)
    try:
        response = _http().get(endpoint, params=params, timeout=10)
        if response.status_code in (429, 403):
            # simple backoff retry once
            time.sleep(0.2)
            response = _http().get(endpoint, params=params, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except requests.HTTPError as exc:
        status = getattr(exc.response, 'status_code', None) if getattr(exc, 'response', None) is not None else None
        logger.warning(
            "[wiki-loans] Wikipedia search HTTPError status=%s query='%s' context='%s'", status, query, context
        )
        return None
    except Exception as exc:  # pragma: no cover - unexpected network issues
        logger.warning(
            "[wiki-loans] Wikipedia search error for query='%s' context='%s': %s", query, context, exc
        )
        return None
    matches = payload.get('query', {}).get('search', [])
    if not matches:
        logger.info("[wiki-loans] no Wikipedia match for '%s'", search_query)
        return None
    title = matches[0].get('title')
    logger.debug("[wiki-loans] search match title='%s'", title)
    return title


def _extract_section(wikitext: str, headings: List[str]) -> str:
    """Return the text inside the first matching section title."""

    matches = list(SECTION_PATTERN.finditer(wikitext))
    if not matches:
        return ''

    heading_indices = {m.group(1).strip().lower(): i for i, m in enumerate(matches)}
    target_index = None
    for heading in headings:
        h_lower = heading.lower()
        if h_lower in heading_indices:
            target_index = heading_indices[h_lower]
            break
    if target_index is None:
        logger.debug("[wiki-loans] no matching section for headings=%s", headings)
        return ''

    start_pos = matches[target_index].end()
    end_pos = len(wikitext)
    for m in matches[target_index + 1:]:
        if len(m.group(0)) == len(matches[target_index].group(0)):
            end_pos = m.start()
            break
    section_text = wikitext[start_pos:end_pos]
    logger.debug("[wiki-loans] extracted section '%s' length=%d", headings[target_index], len(section_text))
    return section_text


def extract_team_loan_candidates(wikitext: str, season_year: int) -> List[Dict[str, object]]:
    """Extract loan candidates from a team's Wikipedia page."""

    section = _extract_section(
        wikitext,
        headings=[
            'Out on loan',
            'Players out on loan',
            'Loaned out players',
            'Loan players',
        ],
    )
    if not section:
        section = wikitext

    rows = list(_parse_table_rows(section))
    results: List[Dict[str, object]] = []

    for cells in rows:
        if not cells:
            continue
        combined = ' || '.join(cells)
        if 'loan' not in combined.lower():
            continue

        season_value = _parse_season_year(cells[0]) if cells else None
        if season_value is not None and season_value != season_year:
            continue

        player_name = None
        loan_club = None
        for cell in cells[1:4]:
            if player_name is None and '[[' in cell:
                player_name = _strip_markup(cell)
            if '→' in cell or '(loan' in cell.lower():
                loan_club = _clean_team_cell(cell)
        if player_name and loan_club:
            results.append({
                'player_name': player_name,
                'loan_team': loan_club,
                'season_year': season_year,
            })

    if not results:
        # fallback regex on bullet list
        bullet_pattern = re.compile(
            rf"\*\s*\[\[(?P<player>[^]]+)]].*?(?P<year>{season_year})?.*?\[\[(?P<club>[^]]+)]]\s*\(loan",
            re.IGNORECASE,
        )
        for match in bullet_pattern.finditer(section):
            if match.group('year') and int(match.group('year')) != season_year:
                continue
            results.append({
                'player_name': match.group('player').split('|')[-1],
                'loan_team': match.group('club').split('|')[-1],
                'season_year': season_year,
            })

    logger.info(
        "[wiki-loans] extracted %d loan candidates from team page for season %s",
        len(results),
        season_year,
    )
    return results


def collect_player_loans_from_wikipedia(
    players: Iterable[Dict[str, object]],
    season_year: int,
    *,
    search_context: str = 'footballer',
    on_error: Optional[Callable[[Dict[str, object], Exception], None]] = None,
) -> List[Dict[str, object]]:
    """Collect loan rows for the provided players using their Wikipedia pages.

    Parameters
    ----------
    players:
        Iterable of dictionaries describing players. Keys ``name``, ``player_name``
        or ``full_name`` are inspected in that order to determine the player's
        display name. ``parent_club`` (or ``team_name``) is used as the expected
        owning club when interpreting Wikipedia rows.
    season_year:
        The starting year of the target season (e.g. 2025 for the 2025–26 season).
    search_context:
        Optional context string appended to Wikipedia searches (defaults to
        ``"footballer"``).
    on_error:
        Optional callback invoked when fetching a player's page fails.
    """

    aggregated: List[Dict[str, object]] = []

    for player in players:
        if not isinstance(player, dict):
            logger.debug("[wiki-loans] skipping non-dict player payload: %r", player)
            continue

        player_name = (
            player.get('name')
            or player.get('player_name')
            or player.get('full_name')
        )
        if not player_name:
            logger.debug("[wiki-loans] skipping player with missing name: %r", player)
            continue

        parent_club = (
            player.get('parent_club')
            or player.get('team_name')
            or 'Unknown Club'
        )

        wiki_title = player.get('wiki_title')
        if not wiki_title:
            # Try primary search with provided context (e.g. "footballer {team}")
            wiki_title = search_wikipedia_title(player_name, context=search_context)
        if not wiki_title:
            # Fallback 1: Append (footballer)
            wiki_title = search_wikipedia_title(f"{player_name} (footballer)")
        if not wiki_title and parent_club and parent_club != 'Unknown Club':
            # Fallback 2: Add club to context
            wiki_title = search_wikipedia_title(player_name, context=f"footballer {parent_club}")
        if not wiki_title:
            # Fallback 3: Last name + club (helps with ambiguous names)
            parts = str(player_name).split()
            if parts:
                last_name = parts[-1]
                if parent_club and parent_club != 'Unknown Club':
                    wiki_title = search_wikipedia_title(f"{last_name}", context=f"footballer {parent_club}")
        if not wiki_title:
            logger.info("[wiki-loans] no Wikipedia title resolved for player=%s", player_name)
            continue

        try:
            wikitext = fetch_wikitext(wiki_title)
        except Exception as exc:  # pragma: no cover - network issues simulated via tests
            if on_error:
                on_error(player, exc)
            else:
                logger.exception(
                    "[wiki-loans] unable to fetch wikitext for player=%s title=%s",
                    player_name,
                    wiki_title,
                )
            continue

        rows = extract_wikipedia_players(
            wikitext,
            season_year,
            player_name=player_name,
            parent_club_hint=parent_club,
        )
        
        # Fallback: If no loans found on Wikipedia, try Brave Search
        if not rows:
            try:
                logger.info("[wiki-loans] No Wikipedia loans found for %s, trying Brave Search...", player_name)
                # Search query: "Player Name loan {season_year}"
                # We pass empty strings for since/until to ignore date filtering for now, 
                # relying on the snippet content and classifier.
                search_results = brave_search(f"{player_name} loan {season_year}", "", "", count=3)
                
                for res in search_results:
                    snippet = res.get('snippet', '')
                    if not snippet:
                        continue
                        
                    # Classify the snippet
                    # We use the classifier designed for Wiki rows, but it works on text snippets too.
                    data = classify_loan_row(
                        snippet,
                        default_player=player_name,
                        default_parent=parent_club,
                        season_year=season_year
                    )
                    
                    if data.get('valid') and data.get('loan_club'):
                        # Map classifier output to our expected format
                        rows.append({
                            'player_name': data.get('player_name') or player_name,
                            'parent_club': data.get('parent_club') or parent_club,
                            'loan_team': data.get('loan_club'),
                            'season_year': data.get('season_start_year') or season_year,
                            'raw_row': snippet[:200], # Store snippet as raw row for reference
                            'source': 'brave_search',
                            'source_url': res.get('url')
                        })
                        logger.info(f"✅ Found loan via Brave: {player_name} -> {data.get('loan_club')}")
                        
            except Exception as e:
                logger.warning(f"[wiki-loans] Brave search fallback failed for {player_name}: {e}")

        for row in rows:
            row.setdefault('player_name', player_name)
            row['parent_club'] = parent_club
            row['wiki_title'] = wiki_title
            row.setdefault('season_year', season_year)
            aggregated.append(row)

    dedup: Dict[tuple, Dict[str, object]] = {}
    for row in aggregated:
        key = (
            row.get('player_name'),
            row.get('loan_team'),
            row.get('season_year'),
        )
        dedup[key] = row

    return list(dedup.values())
