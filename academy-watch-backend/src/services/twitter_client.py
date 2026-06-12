"""X (Twitter) API v2 client for ingesting real tweets into community takes.

Why this exists: the Forest demo needs *real* tweets attached to its
newsletters, not fabricated commentary. This module wraps the X API v2
recent-search endpoint with a small surface area focused on:

  - Authentication via TWITTER_BEARER_TOKEN secret (Key Vault → env fallback)
  - Recent search (last 7 days) with sensible default filters that exclude
    retweets, replies, and non-English junk
  - Author username + display name expansion via the `expansions=author_id`
    + `user.fields` query parameters so each tweet carries human-readable
    attribution without a follow-up lookup
  - Conversion to a flat dict shape that maps directly onto the
    `CommunityTake` row fields used by the rest of the system

There is intentionally no caching or persistence here — that lives in the
admin route that calls this client. This module only knows how to ask the
X API a question and shape the answer.
"""

from __future__ import annotations

import logging
import os
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import requests
from src.utils.keyvault import load_secret

logger = logging.getLogger(__name__)


X_API_BASE = "https://api.x.com/2"
RECENT_SEARCH_PATH = "/tweets/search/recent"

# Default tweet fields fetched per result. Keep this list small — the X API
# free/basic tiers have aggressive rate caps and we want to minimise payload
# size. The fields below are the minimum needed to render a tweet card and
# attribute it correctly.
DEFAULT_TWEET_FIELDS = "id,text,author_id,created_at,public_metrics,lang,conversation_id"
DEFAULT_USER_FIELDS = "id,username,name,verified,profile_image_url"
DEFAULT_EXPANSIONS = "author_id"

# Conservative max — the X API recent-search endpoint accepts up to 100
# but each call also costs against a tight quota. Most newsletter ingests
# only need 5-10 tweets per query.
MAX_RESULTS_HARD_CAP = 100
MAX_RESULTS_DEFAULT = 10


class TwitterAuthError(RuntimeError):
    """Raised when no bearer token is configured."""


class TwitterAPIError(RuntimeError):
    """Raised when the X API returns a non-2xx response."""

    def __init__(self, status_code: int, body: str):
        super().__init__(f"X API HTTP {status_code}: {body[:300]}")
        self.status_code = status_code
        self.body = body


@dataclass(frozen=True)
class IngestedTweet:
    """A tweet shaped for direct insertion as a CommunityTake.

    All fields are real values returned by the X API — no field is
    fabricated or inferred. `source_url` is constructed from the
    `username` + `id` pair which the API guarantees are stable.
    """

    tweet_id: str
    text: str
    author_id: str
    author_username: str
    author_display_name: str
    created_at: str
    like_count: int
    retweet_count: int
    reply_count: int
    quote_count: int
    lang: str | None
    source_url: str

    def to_take_payload(
        self,
        *,
        team_id: int,
        newsletter_id: int | None,
        player_id: int | None,
        player_name: str | None,
    ) -> dict[str, Any]:
        """Shape the tweet as a CommunityTake-ready dict.

        The caller still needs to wrap this in `CommunityTake(**payload)`
        and persist it. We separate the two so the route layer can run
        dedupe / preview logic before committing.
        """
        return {
            "source_type": "twitter",
            "source_author": f"@{self.author_username}",
            "source_url": self.source_url,
            "source_platform": "Twitter/X",
            "content": self.text,
            "player_id": player_id,
            "player_name": player_name,
            "team_id": team_id,
            "newsletter_id": newsletter_id,
            "status": "approved",
            # X-API-only metadata for transparency / audit. The route layer
            # decides whether to persist these into the upvotes column etc.
            "_x_metadata": {
                "tweet_id": self.tweet_id,
                "created_at": self.created_at,
                "like_count": self.like_count,
                "retweet_count": self.retweet_count,
                "lang": self.lang,
            },
        }


def _bearer_token() -> str:
    """Resolve the X API bearer token via the standard secret loader.

    Order: Key Vault (if AZURE_KEY_VAULT_URL set) → env var.
    Raises TwitterAuthError if neither path produces a value.
    """
    token = load_secret("TWITTER_BEARER_TOKEN") or os.getenv("TWITTER_BEARER_TOKEN")
    if not token:
        raise TwitterAuthError(
            "TWITTER_BEARER_TOKEN is not configured. Set it in the local "
            ".env, in Key Vault, or as a Container Apps secret."
        )
    return token.strip()


def _build_user_index(includes: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Build a {author_id: user_dict} index from the API includes block.

    The X API returns expanded users in a flat list — we need to look them
    up by id when iterating tweets, so an index makes that O(1).
    """
    users_by_id: dict[str, dict[str, Any]] = {}
    for user in (includes or {}).get("users", []) or []:
        if isinstance(user, dict) and user.get("id"):
            users_by_id[str(user["id"])] = user
    return users_by_id


def _shape_tweet(tweet: dict[str, Any], users_by_id: dict[str, dict[str, Any]]) -> IngestedTweet | None:
    """Convert a raw API tweet dict + user index into an IngestedTweet.

    Returns None if the tweet is missing required fields (e.g. author
    not found in the includes block, which can happen for deleted users).
    """
    tweet_id = tweet.get("id")
    text = tweet.get("text")
    author_id = tweet.get("author_id")
    if not tweet_id or not text or not author_id:
        return None

    user = users_by_id.get(str(author_id)) or {}
    username = user.get("username")
    display_name = user.get("name") or username or "Unknown"
    if not username:
        # No username = can't construct a real source_url, so skip rather
        # than emit a tweet we can't link back to. Better to drop than to
        # invent.
        return None

    metrics = tweet.get("public_metrics") or {}

    return IngestedTweet(
        tweet_id=str(tweet_id),
        text=text,
        author_id=str(author_id),
        author_username=username,
        author_display_name=display_name,
        created_at=tweet.get("created_at") or "",
        like_count=int(metrics.get("like_count") or 0),
        retweet_count=int(metrics.get("retweet_count") or 0),
        reply_count=int(metrics.get("reply_count") or 0),
        quote_count=int(metrics.get("quote_count") or 0),
        lang=tweet.get("lang"),
        source_url=f"https://x.com/{username}/status/{tweet_id}",
    )


class TwitterClient:
    """Thin synchronous wrapper around the X API v2.

    Constructed with a bearer token (resolved via the standard secret
    loader by default). Exposes a single high-level method —
    `search_recent` — that returns shaped IngestedTweet objects.
    """

    def __init__(self, bearer_token: str | None = None, *, timeout: float = 10.0):
        self._token = bearer_token or _bearer_token()
        self._timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "TheAcademyWatch/1.0 (https://theacademywatch.com)",
            }
        )

    # ---- Public API -----------------------------------------------------

    def search_recent(
        self,
        query: str,
        *,
        max_results: int = MAX_RESULTS_DEFAULT,
        exclude_retweets: bool = True,
        exclude_replies: bool = True,
        lang: str | None = "en",
    ) -> list[IngestedTweet]:
        """Run a recent-search query (last ~7 days).

        Args:
            query: Free-form X search query. Can include operators like
                `from:`, `to:`, `OR`, parentheses. The default filters
                below append `-is:retweet -is:reply lang:en` unless
                disabled, so callers can keep their query focused on the
                content terms (player names, handles).
            max_results: 1..100. The X API minimum is actually 10 — values
                below 10 are silently rounded up by the API.
            exclude_retweets: Adds `-is:retweet` to the query.
            exclude_replies: Adds `-is:reply` to the query.
            lang: If set, adds `lang:<code>` to the query. Pass None to
                allow all languages.

        Returns:
            List of IngestedTweet objects (may be empty).

        Raises:
            TwitterAPIError on HTTP failure.
        """
        full_query = self._build_query(
            query,
            exclude_retweets=exclude_retweets,
            exclude_replies=exclude_replies,
            lang=lang,
        )
        # X API recent-search rejects max_results < 10. Round up but track
        # the caller's intent so we can trim the response below.
        api_max = max(10, min(max_results, MAX_RESULTS_HARD_CAP))

        params = {
            "query": full_query,
            "max_results": api_max,
            "tweet.fields": DEFAULT_TWEET_FIELDS,
            "user.fields": DEFAULT_USER_FIELDS,
            "expansions": DEFAULT_EXPANSIONS,
        }

        url = f"{X_API_BASE}{RECENT_SEARCH_PATH}"
        logger.info("X API search: query=%r max=%d", full_query, api_max)
        resp = self._session.get(url, params=params, timeout=self._timeout)
        if resp.status_code != 200:
            raise TwitterAPIError(resp.status_code, resp.text)

        body = resp.json()
        tweets_raw = body.get("data") or []
        users_by_id = _build_user_index(body.get("includes") or {})

        shaped: list[IngestedTweet] = []
        for tw in tweets_raw:
            ingested = _shape_tweet(tw, users_by_id)
            if ingested is not None:
                shaped.append(ingested)

        # Honour the caller's requested cap even though we asked the API
        # for at least 10 (its minimum).
        return shaped[:max_results]

    # ---- Internals ------------------------------------------------------

    @staticmethod
    def _build_query(
        base: str,
        *,
        exclude_retweets: bool,
        exclude_replies: bool,
        lang: str | None,
    ) -> str:
        parts: list[str] = [base.strip()]
        if exclude_retweets:
            parts.append("-is:retweet")
        if exclude_replies:
            parts.append("-is:reply")
        if lang:
            parts.append(f"lang:{lang}")
        return " ".join(p for p in parts if p)


def filter_quality(
    tweets: Iterable[IngestedTweet],
    *,
    min_likes: int = 0,
    min_engagement: int = 0,
) -> list[IngestedTweet]:
    """Drop tweets that don't meet a minimum engagement bar.

    Defaults are 0 / 0 so by default nothing is filtered — callers opt in
    to a quality threshold via explicit args. Useful for discarding spam
    accounts that match the search terms but have no traction.
    """
    out: list[IngestedTweet] = []
    for t in tweets:
        if t.like_count < min_likes:
            continue
        engagement = t.like_count + t.retweet_count + t.quote_count
        if engagement < min_engagement:
            continue
        out.append(t)
    return out
