"""Twitter/X API v2 enrichment for The Academy Watch newsletters.

Searches public tweets about tracked players within a date range and
returns ranked, de-duplicated results for injection into newsletter items
as a `social_buzz` block.

Auth: Bearer token (app-only OAuth2) via TAW_TWITTER_BEARER env var.
API tier: Free / Basic — uses /2/tweets/search/recent (last 7 days only).
          Full-archive search (/2/tweets/search/all) requires Academic or
          Pro access; if the date range is older than 7 days the module
          returns an empty list rather than erroring.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

_BASE = "https://api.twitter.com/2"
_SEARCH_RECENT = f"{_BASE}/tweets/search/recent"

# How many tweets to request per query (API min=10, max=100)
_MAX_RESULTS = 15

# Minimum engagement score to include a tweet in the output
# score = likes + retweets*2 + quotes*2
_MIN_SCORE = 0

# Cap on tweets returned per player
_TOP_N = 5

# Recent-search window: Twitter free tier only covers last 7 days
_RECENT_WINDOW_DAYS = 7

_DEBUG = os.getenv("TWITTER_DEBUG", "0").lower() in ("1", "true", "yes", "on")


def _dbg(msg: str) -> None:
    if _DEBUG:
        try:
            print(f"[TWITTER DBG] {msg}")
        except Exception:
            pass


def _bearer() -> str:
    token = os.getenv("TAW_TWITTER_BEARER", "").strip()
    if not token:
        raise RuntimeError("TAW_TWITTER_BEARER is not set")
    return token


def _headers() -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {_bearer()}",
        "Accept": "application/json",
    }


def _engagement_score(metrics: Dict[str, Any]) -> int:
    """Simple engagement score: likes + retweets*2 + quotes*2."""
    likes = metrics.get("like_count", 0) or 0
    rts = metrics.get("retweet_count", 0) or 0
    quotes = metrics.get("quote_count", 0) or 0
    return likes + rts * 2 + quotes * 2


def _within_window(date_str: str) -> bool:
    """Return True if the ISO date string is within the recent 7-day window."""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=_RECENT_WINDOW_DAYS)
        return dt >= cutoff
    except Exception:
        return False


def search_tweets_for_player(
    player_name: str,
    loan_team: str,
    start_date: str,
    end_date: str,
    *,
    max_results: int = _MAX_RESULTS,
    top_n: int = _TOP_N,
) -> List[Dict[str, Any]]:
    """Search recent tweets about a player within a date range.

    Args:
        player_name: Full player name e.g. "Ethan Nwaneri"
        loan_team:   Current loan/parent club e.g. "Arsenal"
        start_date:  ISO date string "YYYY-MM-DD" (start of newsletter period)
        end_date:    ISO date string "YYYY-MM-DD" (end of newsletter period)
        max_results: How many raw tweets to fetch (10–100)
        top_n:       How many to return after ranking

    Returns:
        List of tweet dicts with keys: id, text, created_at, url,
        author_id, likes, retweets, quotes, score
    """
    # Twitter free tier only covers last 7 days — bail gracefully if older
    if not _within_window(end_date):
        _dbg(f"Skipping {player_name} — date range {start_date}→{end_date} outside 7-day window")
        return []

    # Build query: exact player name + optional team context, exclude retweets.
    # We try a tight query first (name + team); if that yields nothing we fall
    # back to name-only so we still capture commentary about the player.
    queries = [
        f'"{player_name}" "{loan_team}" -is:retweet lang:en',
        f'"{player_name}" -is:retweet lang:en',
    ]

    base_params: Dict[str, Any] = {
        "max_results": max(10, min(100, max_results)),
        "tweet.fields": "created_at,public_metrics,author_id,text",
        "sort_order": "relevancy",
    }

    # Add time bounds — Twitter expects RFC 3339
    time_params: Dict[str, str] = {}
    try:
        start_dt = datetime.fromisoformat(start_date)
        time_params["start_time"] = start_dt.strftime("%Y-%m-%dT00:00:00Z")
    except ValueError:
        pass
    try:
        end_dt = datetime.fromisoformat(end_date)
        time_params["end_time"] = end_dt.strftime("%Y-%m-%dT23:59:59Z")
    except ValueError:
        pass

    raw_tweets: List[Dict[str, Any]] = []
    for query in queries:
        _dbg(f"Query: {query} | {start_date} → {end_date}")
        params = {**base_params, "query": query, **time_params}
        try:
            resp = requests.get(
                _SEARCH_RECENT,
                headers=_headers(),
                params=params,
                timeout=10,
            )
        except requests.RequestException as exc:
            logger.warning("Twitter search network error for %s: %s", player_name, exc)
            return []

        if resp.status_code == 429:
            logger.warning("Twitter rate limit hit for player %s — skipping", player_name)
            return []

        if resp.status_code != 200:
            logger.warning(
                "Twitter search returned %s for %s: %s",
                resp.status_code, player_name, resp.text[:200],
            )
            continue

        raw_tweets = resp.json().get("data") or []
        _dbg(f"Got {len(raw_tweets)} raw tweets for {player_name} (query: {query[:60]}...)") 
        if raw_tweets:
            break  # tight query worked; no need for fallback
        time.sleep(0.2)  # small pause between fallback attempts

    results: List[Dict[str, Any]] = []
    for tweet in raw_tweets:
        metrics = tweet.get("public_metrics") or {}
        score = _engagement_score(metrics)
        if score < _MIN_SCORE:
            continue
        tweet_id = tweet.get("id", "")
        results.append({
            "id": tweet_id,
            "text": tweet.get("text", ""),
            "created_at": tweet.get("created_at", ""),
            "url": f"https://x.com/i/web/status/{tweet_id}",
            "author_id": tweet.get("author_id", ""),
            "likes": metrics.get("like_count", 0),
            "retweets": metrics.get("retweet_count", 0),
            "quotes": metrics.get("quote_count", 0),
            "score": score,
        })

    # Sort by engagement, return top N
    results.sort(key=lambda t: t["score"], reverse=True)
    return results[:top_n]


def twitter_context_for_newsletter(
    report: Dict[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    """Fetch tweets for all tracked players in a newsletter report.

    Args:
        report: The newsletter report dict (same shape used by brave_context_for_team_and_loans).
                Expected keys: range (list of 2 ISO date strings), groups (dict with
                on_loan / first_team / academy lists).

    Returns:
        Dict keyed by normalised player name → list of tweet dicts.
        Empty dict if bearer token is missing or all dates out of window.
    """
    try:
        start, end = report.get("range", [None, None])
        if not start or not end:
            return {}
    except (TypeError, ValueError):
        return {}

    groups = report.get("groups", {})
    # Search loans + first-team; skip academy (minimal social coverage)
    players = groups.get("on_loan", []) + groups.get("first_team", [])

    results: Dict[str, List[Dict[str, Any]]] = {}

    for player in players:
        player_name = (player.get("player_name") or "").strip()
        loan_team = (
            player.get("loan_team_name")
            or player.get("loan_team")
            or player.get("parent_team_name")
            or ""
        ).strip()

        if not player_name or not loan_team:
            continue

        try:
            tweets = search_tweets_for_player(
                player_name, loan_team, start, end
            )
            if tweets:
                results[player_name] = tweets
                _dbg(f"{player_name}: {len(tweets)} tweets")
            # Respect rate limits — small sleep between players
            time.sleep(0.3)
        except RuntimeError as exc:
            # Bearer token missing — bail entirely
            logger.warning("Twitter enrichment disabled: %s", exc)
            return {}
        except Exception as exc:
            logger.warning("Twitter enrichment failed for %s: %s", player_name, exc)
            continue

    return results


def inject_social_buzz(
    player_item: Dict[str, Any],
    tweets_by_player: Dict[str, List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Inject matching tweets into a player newsletter item as `social_buzz`.

    Args:
        player_item:      A single player item dict from the newsletter sections.
        tweets_by_player: Output of twitter_context_for_newsletter().

    Returns:
        The player_item dict with a `social_buzz` key added (list of tweet dicts,
        may be empty).
    """
    player_name = (player_item.get("player_name") or "").strip()
    tweets = tweets_by_player.get(player_name, [])
    player_item["social_buzz"] = tweets
    return player_item
