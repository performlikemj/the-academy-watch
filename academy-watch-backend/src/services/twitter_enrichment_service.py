"""Twitter/X enrichment service for Academy Watch newsletters.

Searches Twitter API v2 for tweets about tracked players and persists
candidates as pending CommunityTake records for human/agent review.

The harness casts a wide net with minimal hard gates (wrong sport, no club
match, spam accounts). Quality judgment belongs with the reviewer, not the
code — better to surface a few false positives for a human to reject than
to silently drop real content through over-filtering.

Auth: Bearer token (app-only OAuth2) via TWITTER_BEARER_TOKEN env var.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

_BASE = "https://api.twitter.com/2"
_SEARCH_RECENT = f"{_BASE}/tweets/search/recent"
_SEARCH_ALL = f"{_BASE}/tweets/search/all"

_DEBUG = os.getenv("TWITTER_DEBUG", "0").lower() in ("1", "true", "yes", "on")


def _dbg(msg: str) -> None:
    if _DEBUG:
        try:
            print(f"[TWITTER] {msg}")
        except Exception:
            pass


class TwitterApiError(Exception):
    pass


# ── Data classes ─────────────────────────────────────────────────────────────


@dataclass
class PlayerContext:
    """Search context for a player, derived from newsletter content."""

    player_name: str
    player_api_id: int
    full_name: str
    club: str
    club_aliases: list[str] = field(default_factory=list)
    minutes: int = 0
    match_notes: list[str] = field(default_factory=list)
    opponents: list[str] = field(default_factory=list)
    parent_team: str = ""


@dataclass
class ScoredTweet:
    """A candidate tweet with a relevance score."""

    tweet_id: str
    text: str
    created_at: str
    url: str
    author_username: str
    author_name: str
    likes: int = 0
    retweets: int = 0
    quotes: int = 0
    score: int = 0
    score_reasons: str = ""


# ── Constants ────────────────────────────────────────────────────────────────

_TEAM_SUFFIXES = re.compile(
    r"\s+(FC|AFC|Town|City|United|Rovers|Wanderers|Albion|Athletic|County|Hotspur)$",
    re.I,
)

# Hard gate: obviously wrong domain (broad categories only)
_WRONG_DOMAIN = re.compile(
    r"\b(NHL|NBA|NFL|MLB|hockey|baseball|basketball|cricket|tennis|"
    r"rugby\s(?:league|union))\b",
    re.I,
)

# Known spam / AI bot accounts
_SPAM_ACCOUNTS = {"grok", "chatgpt", "aisportpredicts", "bettingtips", "oddschecker"}

# Scoring signals
_FOOTBALL_CONTEXT = re.compile(
    r"\b(goal|assist|sub|substitut|yellow|red\scard|penalty|half[\s-]?time|"
    r"full[\s-]?time|debut|scores?|winner|clean\ssheet|MOTM|"
    r"\d+'|\d+-\d+|League\s(?:One|Two)|Championship|EFL|FA\sCup|"
    r"Carabao|Trophy|match|loan|academy)\b",
    re.I,
)

_OFFICIAL_ACCOUNT = re.compile(
    r"(?:FC|Town|City|United|Rovers|Wanderers|Albion|County|official)$",
    re.I,
)

_MEDIA_SUBSTRINGS = {
    "bbc",
    "skysports",
    "talksport",
    "theathletic",
    "espn",
    "efl",
    "premierleague",
    "guardian",
    "telegraph",
}


# ── Service ──────────────────────────────────────────────────────────────────


class TwitterEnrichmentService:
    """Search → hard gates → score → persist as pending."""

    def __init__(self, bearer_token: str | None = None):
        self._token = (bearer_token or os.getenv("TWITTER_BEARER_TOKEN", "")).strip()
        self._max_per_player = int(os.getenv("TWITTER_MAX_PER_PLAYER", "3"))
        self._use_archive = os.getenv("TWITTER_USE_ARCHIVE", "true").lower() in (
            "1",
            "true",
            "yes",
        )

    def is_configured(self) -> bool:
        return bool(self._token) and len(self._token) > 20

    # ── Main entry point ─────────────────────────────────────────────────

    def enrich_newsletter(self, newsletter_id: int, team_db_id: int) -> dict:
        """Search Twitter for each player in a newsletter, persist candidates
        as pending CommunityTake rows for review."""
        from src.models.league import Newsletter, Team

        newsletter = Newsletter.query.get(newsletter_id)
        if not newsletter:
            return {"error": f"Newsletter {newsletter_id} not found"}

        content = newsletter.content
        if isinstance(content, str):
            content = json.loads(content)

        team = Team.query.get(team_db_id)
        parent_team = team.name if team else ""

        if not newsletter.week_start_date or not newsletter.week_end_date:
            return {"error": "Newsletter has no date range"}

        start = f"{newsletter.week_start_date.isoformat()}T00:00:00Z"
        end = f"{newsletter.week_end_date.isoformat()}T23:59:59Z"

        contexts = self._extract_player_contexts(content, parent_team)
        _dbg(f"{len(contexts)} players in newsletter {newsletter_id}")

        total_persisted = 0
        for ctx in contexts:
            raw = self._search(ctx, start, end)
            candidates = self._gate_and_score(raw, ctx)
            _dbg(f"  {ctx.player_name}: {len(raw)} raw → {len(candidates)} candidates")

            if candidates:
                n = self._persist(candidates, newsletter_id, team_db_id, ctx)
                total_persisted += n

        return {
            "newsletter_id": newsletter_id,
            "players_searched": len(contexts),
            "candidates_persisted": total_persisted,
        }

    def search_player_tweets(
        self,
        player_name: str,
        club: str,
        start: str,
        end: str,
    ) -> list[dict]:
        """Ad-hoc search for scripts and tests."""
        ctx = PlayerContext(
            player_name=player_name,
            player_api_id=0,
            full_name=player_name,
            club=club,
            club_aliases=self._club_aliases(club),
        )
        raw = self._search(ctx, start, end)
        return [
            {"text": t.text, "url": t.url, "author": t.author_username, "score": t.score, "reasons": t.score_reasons}
            for t in self._gate_and_score(raw, ctx)
        ]

    # ── Context extraction ───────────────────────────────────────────────

    def _extract_player_contexts(
        self,
        content: dict,
        parent_team: str,
    ) -> list[PlayerContext]:
        contexts: list[PlayerContext] = []
        for section in content.get("sections") or []:
            for items in self._iter_item_lists(section):
                for item in items:
                    ctx = self._item_to_ctx(item, parent_team)
                    if ctx:
                        contexts.append(ctx)
        return contexts

    @staticmethod
    def _iter_item_lists(section: dict):
        if section.get("items"):
            yield section["items"]
        for sub in section.get("subsections") or []:
            if sub.get("items"):
                yield sub["items"]

    def _item_to_ctx(self, item: dict, parent_team: str) -> PlayerContext | None:
        name = (item.get("player_name") or "").strip()
        if not name:
            return None
        club = (item.get("loan_team_name") or item.get("loan_team") or parent_team).strip()
        full = (item.get("player_full_name") or item.get("full_name") or name).strip()
        stats = item.get("stats") or {}
        notes = item.get("match_notes") or []
        return PlayerContext(
            player_name=name,
            player_api_id=item.get("player_api_id") or item.get("player_id") or 0,
            full_name=full,
            club=club,
            club_aliases=self._club_aliases(club),
            minutes=stats.get("minutes", 0) if isinstance(stats, dict) else 0,
            match_notes=notes,
            opponents=[m.group(1).strip() for n in notes for m in [re.search(r"vs\s+([^:]+)", n, re.I)] if m],
            parent_team=parent_team,
        )

    @staticmethod
    def _club_aliases(club: str) -> list[str]:
        aliases = [club]
        short = _TEAM_SUFFIXES.sub("", club).strip()
        if short and short != club:
            aliases.insert(0, short)
        return aliases

    # ── Twitter search ───────────────────────────────────────────────────

    def _search(self, ctx: PlayerContext, start: str, end: str) -> list[dict]:
        last = ctx.full_name.split()[-1] if ctx.full_name else ctx.player_name
        short_club = ctx.club_aliases[0] if ctx.club_aliases else ctx.club

        queries = [
            f'"{last}" "{short_club}" -is:retweet lang:en',
            f'"{ctx.full_name}" -is:retweet lang:en',
        ]

        seen: set[str] = set()
        tweets: list[dict] = []

        for q in queries:
            data = self._api_call(q, start, end)
            if not data:
                time.sleep(1.0)
                continue
            users = {u["id"]: u for u in data.get("includes", {}).get("users", [])}
            for t in data.get("data") or []:
                tid = t.get("id", "")
                if tid not in seen:
                    seen.add(tid)
                    t["_user"] = users.get(t.get("author_id"), {})
                    tweets.append(t)
            time.sleep(1.2)
            if len(tweets) >= 25:
                break

        return tweets

    def _api_call(self, query: str, start: str, end: str) -> dict | None:
        endpoint = _SEARCH_ALL if self._use_archive else _SEARCH_RECENT
        params = urllib.parse.urlencode(
            {
                "query": query,
                "max_results": 25,
                "tweet.fields": "created_at,public_metrics,author_id",
                "expansions": "author_id",
                "user.fields": "username,name,description,verified",
                "start_time": start,
                "end_time": end,
            }
        )
        req = urllib.request.Request(
            f"{endpoint}?{params}",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        _dbg(f"query: {query[:80]}...")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.loads(resp.read())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                logger.warning("Twitter rate limit — pausing 15s")
                time.sleep(15)
                return None
            if e.code == 403 and self._use_archive:
                self._use_archive = False
                return self._api_call(query, start, end)
            logger.warning("Twitter API %d: %s", e.code, e.read().decode()[:200])
            return None
        except Exception as exc:
            logger.warning("Twitter API error: %s", exc)
            return None

    # ── Hard gates + scoring ─────────────────────────────────────────────

    def _gate_and_score(
        self,
        raw: list[dict],
        ctx: PlayerContext,
    ) -> list[ScoredTweet]:
        candidates: list[ScoredTweet] = []
        for t in raw:
            text = t.get("text", "")
            user = t.get("_user", {})
            username = user.get("username", "")

            # Gate 1: wrong domain (NHL, NBA, etc.)
            if _WRONG_DOMAIN.search(text):
                _dbg(f"  GATE wrong_domain: {text[:50]}")
                continue

            # Gate 2: club name must appear
            if not any(a.lower() in text.lower() for a in ctx.club_aliases):
                _dbg(f"  GATE no_club: {text[:50]}")
                continue

            # Gate 3: known spam account
            if username.lower() in _SPAM_ACCOUNTS:
                _dbg(f"  GATE spam: @{username}")
                continue

            # Score
            metrics = t.get("public_metrics") or {}
            score, reasons = self._score(text, user, metrics, ctx)

            candidates.append(
                ScoredTweet(
                    tweet_id=t.get("id", ""),
                    text=text,
                    created_at=t.get("created_at", ""),
                    url=f"https://x.com/{username}/status/{t.get('id', '')}",
                    author_username=username,
                    author_name=user.get("name", ""),
                    likes=metrics.get("like_count", 0),
                    retweets=metrics.get("retweet_count", 0),
                    quotes=metrics.get("quote_count", 0),
                    score=score,
                    score_reasons=reasons,
                )
            )

        candidates.sort(key=lambda c: c.score, reverse=True)
        return candidates[: self._max_per_player]

    @staticmethod
    def _score(text: str, user: dict, metrics: dict, ctx: PlayerContext) -> tuple[int, str]:
        s = 0
        r: list[str] = []
        uname = user.get("username", "")
        bio = (user.get("description") or "").lower()
        tl = text.lower()

        if _OFFICIAL_ACCOUNT.search(uname):
            s += 5
            r.append(f"official (@{uname})")
        if any(m in uname.lower() for m in _MEDIA_SUBSTRINGS):
            s += 4
            r.append("media")
        if any(w in bio for w in ("football", "soccer", "efl", "journalist", "sport")):
            s += 2
            r.append("football bio")

        last = ctx.full_name.split()[-1].lower() if ctx.full_name else ""
        if last and last in tl:
            s += 3
            r.append("player named")

        fc = _FOOTBALL_CONTEXT.findall(text)
        if len(fc) >= 2:
            s += 2
            r.append(f"match context ({len(fc)})")

        for opp in ctx.opponents:
            if opp.lower() in tl:
                s += 2
                r.append(f"opponent ({opp})")
                break

        eng = (metrics.get("like_count") or 0) + (metrics.get("retweet_count") or 0) * 2
        bonus = min(5, eng // 10)
        if bonus:
            s += bonus
            r.append(f"engagement ({eng})")

        return s, " + ".join(r) if r else "base"

    # ── Persistence ──────────────────────────────────────────────────────

    def _persist(
        self,
        tweets: list[ScoredTweet],
        newsletter_id: int,
        team_db_id: int,
        ctx: PlayerContext,
    ) -> int:
        from src.models.league import CommunityTake, db

        created = 0
        for tw in tweets:
            if CommunityTake.query.filter_by(
                newsletter_id=newsletter_id,
                source_url=tw.url,
            ).first():
                continue

            posted_at = None
            if tw.created_at:
                try:
                    posted_at = datetime.fromisoformat(tw.created_at.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    pass

            db.session.add(
                CommunityTake(
                    source_type="twitter",
                    source_author=f"@{tw.author_username}",
                    source_url=tw.url,
                    source_platform="Twitter/X",
                    content=tw.text,
                    player_id=ctx.player_api_id or None,
                    player_name=ctx.player_name,
                    team_id=team_db_id,
                    newsletter_id=newsletter_id,
                    status="pending",
                    upvotes=tw.score,
                    original_posted_at=posted_at,
                    scraped_at=datetime.now(UTC),
                )
            )
            created += 1

        if created:
            db.session.commit()
            logger.info("Twitter: %s → %d candidates (newsletter %d)", ctx.player_name, created, newsletter_id)
        return created
