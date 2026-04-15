"""Helpers for gathering loan data via Brave Search."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass
from urllib.parse import unquote, urlparse

from pydantic import BaseModel, Field
from pydantic.config import ConfigDict
from src.mcp.brave import BraveApiError, brave_search

logger = logging.getLogger(__name__)

# Groq SDK is lazy-loaded in _get_groq_client() to reduce cold start time


def _get_groq_client():
    """Get Groq client with lazy import to reduce cold start time."""
    try:
        from groq import Groq  # Lazy import - only loaded when actually needed

        api_key = os.getenv("GROQ_API_KEY")
        if api_key:
            return Groq(api_key=api_key)
    except ImportError:  # pragma: no cover - optional dependency
        pass
    except Exception:
        pass
    return None


@dataclass(slots=True)
class BravePlayerCollection:
    """Normalized payload returned after querying Brave."""

    rows: list[dict[str, str]]
    results: list[dict[str, str]]
    query: str


def _read_output_text(resp) -> str:
    """Extract text from an OpenAI Responses API result."""
    txt = getattr(resp, "output_text", None)
    if txt:
        return txt
    chunks: list[str] = []
    for item in getattr(resp, "output", []) or []:
        for part in getattr(item, "content", []) or []:
            text = getattr(part, "text", None)
            if text:
                chunks.append(text)
    return "".join(chunks)


def _extract_wikipedia_title(url: str) -> str | None:
    if not url or "wikipedia.org/wiki/" not in url:
        return None
    try:
        path = urlparse(url).path
    except Exception:
        return None
    if not path:
        return None
    try:
        title = path.split("/wiki/", 1)[1]
    except IndexError:
        return None
    title = title.split("#", 1)[0]
    title = title.replace("_", " ")
    return unquote(title).strip() or None


def _default_query(team_name: str, season_year: int) -> str:
    return f"{team_name} loaned players {season_year}"


def _fallback_query(team_name: str, season_year: int) -> str:
    return f"{team_name} out on loan {season_year}"


def collect_players_from_brave(
    team_name: str,
    season_year: int,
    *,
    query: str | None = None,
    result_limit: int = 8,
    strict_range: bool = False,
    since: str | None = None,
    until: str | None = None,
) -> BravePlayerCollection:
    """Use Brave Search to discover pages containing loan information.

    At the moment we prioritise Wikipedia hits and reuse the wiki parser.
    Returns the extracted loan rows along with the raw Brave result metadata.
    """
    if not team_name or not season_year:
        return BravePlayerCollection(rows=[], results=[], query=query or "")

    effective_query = (query or _default_query(team_name, season_year)).strip()
    if not effective_query:
        return BravePlayerCollection(rows=[], results=[], query="")

    if result_limit <= 0:
        result_limit = 1
    result_limit = min(result_limit, 20)

    # Brave freshness works with a YYYY-MM-DDtoYYYY-MM-DD string. Provide defaults if not supplied.
    if not since:
        since = f"{season_year}-06-01"
    if not until:
        until = f"{season_year + 1}-06-30"

    logger.info(
        "[brave-loans] query='%s' since=%s until=%s limit=%s strict=%s",
        effective_query,
        since,
        until,
        result_limit,
        strict_range,
    )
    try:
        search_results = brave_search(
            effective_query,
            since,
            until,
            count=result_limit,
            strict_range=strict_range,
            result_filter=["web"],
        )
    except BraveApiError:
        raise
    except Exception as exc:  # pragma: no cover - defensive
        raise BraveApiError(str(exc)) from exc

    # Adaptive retry if we got no rows from wikipedia
    if not search_results:
        logger.info("[brave-loans] empty results; retrying with fallback query")
        try:
            search_results = brave_search(
                _fallback_query(team_name, season_year),
                since,
                until,
                count=min(result_limit * 2, 20),
                strict_range=strict_range,
                result_filter=["web"],
            )
        except Exception:
            search_results = []

    wiki_titles: list[str] = []
    unique_titles: set[str] = set()
    normalized_results: list[dict[str, str]] = []
    for item in search_results:
        title = (item.get("title") or "").strip()
        url = (item.get("url") or "").strip()
        snippet = (item.get("snippet") or "").strip()
        if title or url or snippet:
            normalized_results.append(
                {
                    "title": title,
                    "url": url,
                    "snippet": snippet,
                }
            )
        # Collect potential candidates directly from the web (non-Wikipedia)
        # We will parse titles/snippets for loan phrases and extract (player, loan_team)
        # Examples: "Club sign Player on loan", "Player joins Club on loan", "Player loaned to Club"
        lowered = f"{title}. {snippet}".lower()
        if "loan" not in lowered:
            continue
        # Basic heuristics to avoid false positives not involving the target team
        team_lower = team_name.lower()
        if team_lower not in lowered:
            # still consider if the URL contains the team name
            if team_lower not in (url.lower()):
                continue
        unique_titles.add(url)  # reuse set for dedupe of result URLs
        wiki_titles.append(url)

    logger.info(
        "[brave-loans] brave_results=%s candidates_to_parse=%s",
        len(search_results),
        len(wiki_titles),
    )

    # Heuristic patterns
    patterns = [
        re.compile(
            r"^(?P<player>[A-Z][\w'\-]+(?:\s[A-Z][\w'\-]+){0,3})\s+(joins|signs for|signs with|moves to)\s+(?P<club>[^\.,]+)\s+(on\s+a?\s*)?loan",
            re.IGNORECASE,
        ),
        re.compile(
            r"(?P<player>[A-Z][\w'\-]+(?:\s[A-Z][\w'\-]+){0,3}).{0,40}?loan(?:ed)?\s+to\s+(?P<club>[^\.,]+)",
            re.IGNORECASE,
        ),
        re.compile(
            r"(sign|loan)(?:s|ed)?\s+(?P<player>[A-Z][\w'\-]+(?:\s[A-Z][\w'\-]+){0,3}).{0,40}?on\s+loan\s+to\s+(?P<club>[^\.,]+)",
            re.IGNORECASE,
        ),
    ]

    def _extract_player_club(title_text: str, snippet_text: str) -> tuple[str | None, str | None]:
        combined = f"{title_text}. {snippet_text}"
        for pat in patterns:
            m = pat.search(combined)
            if m:
                player = (m.group("player") or "").strip()
                club = (m.group("club") or "").strip()
                if player and club:
                    return player, club
        # fallback: try simple "Player - Club on loan" in title
        m = re.search(r"^(?P<player>[^\-\|]+?)\s+[-|]\s+(?P<club>.+?)\s+on\s+loan", title_text, re.IGNORECASE)
        if m:
            return m.group("player").strip(), m.group("club").strip()
        return None, None

    # --- Pydantic schemas for structured output ---
    class TitleScoreModel(BaseModel):
        model_config = ConfigDict(extra="forbid")
        relevant: bool = Field(...)
        confidence: float = Field(...)
        reason: str = Field(...)

    class ExtractedRowModel(BaseModel):
        model_config = ConfigDict(extra="forbid")
        player_name: str
        loan_team: str
        season_year: int = Field(...)
        confidence: float = Field(...)
        evidence: str = Field(...)

    class ExtractedRowsModel(BaseModel):
        model_config = ConfigDict(extra="forbid")
        rows: list[ExtractedRowModel] = Field(default_factory=list)

    # --- Stage 1: LLM scoring of titles/snippets (cheap filter) ---
    try:
        from openai import OpenAI  # type: ignore
    except Exception:  # pragma: no cover - library missing in some environments
        OpenAI = None  # type: ignore

    def _get_client():
        if OpenAI is None:
            return None
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return None
        try:
            return OpenAI(api_key=api_key)
        except Exception:
            return None

    def _score_title_detail(client, title: str, snippet: str, team: str, season: int) -> tuple[bool, float, str]:
        if client is None:
            return False, 0.0, "openai client unavailable"
        system = (
            "You are an assistant that filters football news for specific team loan information. "
            "Given a page title and snippet, decide if the page likely contains explicit mentions of players going on loan, "
            "from or to the given team in the given season."
        )
        user = (
            f"Team: {team}\nSeason: {season}\nTitle: {title}\nSnippet: {snippet}\n"
            "Respond as JSON with fields: relevant (bool), confidence (0-1), reason."
        )
        # Prefer Responses API if available (OpenAI)
        if hasattr(client, "responses"):
            try:
                model_name = os.getenv("BRAVE_LLM_MODEL", "gpt-4.1-mini")
                resp = client.responses.create(
                    model=model_name,
                    input=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {
                            "name": "loan_title_score",
                            "schema": TitleScoreModel.model_json_schema(),
                        },
                    },
                )
                content = _read_output_text(resp)
                if content.strip():
                    parsed = TitleScoreModel.model_validate(json.loads(content))
                    conf = float(parsed.confidence or 0)
                    rel = bool(parsed.relevant)
                    reason = (parsed.reason or "").strip()
                    return rel, (conf if rel else 0.0), reason
            except Exception as exc:
                logger.debug("[brave-loans] title score via Responses failed: %s", exc)

        # Groq-style chat client
        if hasattr(client, "chat"):
            try:
                resp = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": "loan_title_score", "schema": TitleScoreModel.model_json_schema()},
                    },
                    max_tokens=200,
                )
                content = resp.choices[0].message.content
                logger.debug(
                    "[brave-loans] Responses(title-score) raw output=%s",
                    (content[:400] + "…") if len(content) > 400 else content,
                )
                if content.strip():
                    video_data = json.loads(content)
                    parsed = TitleScoreModel.model_validate(video_data)
                    conf = float(parsed.confidence or 0)
                    rel = bool(parsed.relevant)
                    reason = (parsed.reason or "").strip()
                    logger.info(
                        "[brave-loans] title score parsed rel=%s conf=%.2f reason=%s",
                        rel,
                        conf,
                        (reason[:160] + "…") if len(reason) > 160 else reason,
                    )
                    return rel, (conf if rel else 0.0), reason
            except TypeError as exc:
                logger.info("[brave-loans] Responses schema unsupported; falling back to plain JSON parse: %s", exc)
                try:
                    resp = client.chat.completions.create(
                        model="openai/gpt-oss-120b",
                        messages=[
                            {"role": "system", "content": system + " Always answer with a single JSON object."},
                            {"role": "user", "content": user},
                        ],
                        response_format={
                            "type": "json_schema",
                            "json_schema": {"name": "loan_title_score", "schema": TitleScoreModel.model_json_schema()},
                        },
                        max_tokens=200,
                    )
                    content = resp.choices[0].message.content
                    logger.debug(
                        "[brave-loans] Responses(title-score:fallback) raw output=%s",
                        (content[:400] + "…") if len(content) > 400 else content,
                    )
                    if content.strip():
                        m = re.search(r"\{[\s\S]*\}", content)
                        raw = m.group(0) if m else content
                        video_data = json.loads(raw)
                        parsed = TitleScoreModel.model_validate(video_data)
                        conf = float(parsed.confidence or 0)
                        rel = bool(parsed.relevant)
                        reason = (parsed.reason or "").strip()
                        logger.info(
                            "[brave-loans] title score fallback parsed rel=%s conf=%.2f reason=%s",
                            rel,
                            conf,
                            (reason[:160] + "…") if len(reason) > 160 else reason,
                        )
                        return rel, (conf if rel else 0.0), reason
                except Exception as inner:
                    logger.debug("[brave-loans] title score fallback failed: %s", inner)
            except Exception as exc:
                logger.debug("[brave-loans] title score failed via Groq: %s", exc)

        if client is None:
            return False, 0.0, "openai client unavailable"
        try:
            # Fallback: client exposes a Groq-like interface but was not caught above
            model_name = "openai/gpt-oss-120b"
            chat = getattr(client, "chat", None)
            if chat and hasattr(chat, "completions"):
                resp = chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": "loan_title_score", "schema": TitleScoreModel.model_json_schema()},
                    },
                )
                content = resp.choices[0].message.content or ""
                logger.debug(
                    "[brave-loans] OpenAI(title-score) raw output=%s",
                    (content[:400] + "…") if len(content) > 400 else content,
                )
                if not content.strip():
                    return False, 0.0, "empty response from model"
                data = json.loads(content)
                parsed = TitleScoreModel.model_validate(data)
                conf = float(parsed.confidence or 0)
                rel = bool(parsed.relevant)
                reason = (parsed.reason or "").strip()
                logger.info(
                    "[brave-loans] title score parsed (OpenAI) rel=%s conf=%.2f reason=%s",
                    rel,
                    conf,
                    (reason[:160] + "…") if len(reason) > 160 else reason,
                )
                return rel, (conf if rel else 0.0), reason
        except Exception as exc:
            logger.debug("[brave-loans] title score OpenAI fallback failed: %s", exc)
            return False, 0.0, f"error: {exc}"

    def _extract_from_text_with_llm(client, text: str, team: str, season: int) -> list[dict[str, str]]:
        if client is None:
            return []
        # Trim input aggressively
        trimmed = text
        if len(trimmed) > 4000:
            # keep first chunk and lines that contain keywords
            head = trimmed[:2500]
            tail_lines = [
                line
                for line in re.split(r"[\r\n]+", trimmed)
                if any(k in line.lower() for k in (" loan", "loaned", " loanee", team.lower()))
            ]
            tail = "\n".join(tail_lines)[:1500]
            trimmed = head + "\n" + tail

        system = (
            "Extract explicit football loan mentions from the provided article text. "
            "Return rows with player_name, loan_team, season_year (if visible, otherwise infer from provided season), "
            "confidence (0-1), and a short evidence span."
        )
        user = f"Team: {team}\nSeason: {season}\nText:\n{trimmed}\nRespond with JSON matching the schema."
        if hasattr(client, "responses"):
            try:
                model_name = os.getenv("BRAVE_LLM_MODEL", "gpt-4.1-mini")
                resp = client.responses.create(
                    model=model_name,
                    input=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": "loan_rows", "schema": ExtractedRowsModel.model_json_schema()},
                    },
                )
                content = _read_output_text(resp)
                if content.strip():
                    parsed = ExtractedRowsModel.model_validate(json.loads(content))
                    out: list[dict[str, str]] = []
                    for r in parsed.rows:
                        player = (r.player_name or "").strip()
                        club = (r.loan_team or "").strip()
                        if not player or not club:
                            continue
                        out.append(
                            {
                                "player_name": player,
                                "loan_team": club,
                                "season_year": int(r.season_year or season),
                                "confidence": float(r.confidence or 0.0),
                                "evidence": (r.evidence or "").strip(),
                            }
                        )
                    logger.info(
                        "[brave-loans] page extract parsed rows (Responses)=%s",
                        len(out),
                    )
                    return out
            except Exception as exc:
                logger.debug("[brave-loans] page extract via Responses failed: %s", exc)

        if hasattr(client, "chat"):
            try:
                resp = client.chat.completions.create(
                    model="openai/gpt-oss-120b",
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    response_format={
                        "type": "json_schema",
                        "json_schema": {"name": "loan_rows", "schema": ExtractedRowsModel.model_json_schema()},
                    },
                    max_tokens=600,
                )
                content = resp.choices[0].message.content or ""
                logger.debug(
                    "[brave-loans] page extract raw output=%s",
                    (content[:600] + "…") if len(content) > 600 else content,
                )
                if content.strip():
                    data = json.loads(content)
                    parsed = ExtractedRowsModel.model_validate(data)
                    out: list[dict[str, str]] = []
                    for r in parsed.rows:
                        player = (r.player_name or "").strip()
                        club = (r.loan_team or "").strip()
                        if not player or not club:
                            continue
                        out.append(
                            {
                                "player_name": player,
                                "loan_team": club,
                                "season_year": int(r.season_year or season),
                                "confidence": float(r.confidence or 0.0),
                                "evidence": (r.evidence or "").strip(),
                            }
                        )
                    logger.info(
                        "[brave-loans] page extract parsed rows (Chat)=%s",
                        len(out),
                    )
                    return out
            except Exception as exc:
                logger.debug("[brave-loans] page extract via Chat failed: %s", exc)

        return []

    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    openai_client = _get_client()
    groq_client = _get_groq_client()
    llm_client = openai_client or groq_client
    if llm_client is None:
        logger.info("[brave-loans] OPENAI client not available; LLM scoring/extract disabled")
    # Domain allowlist disabled; accept all domains for deep read (user-approved risk)
    allow: tuple[str, ...] = ()
    regex_rows = 0
    llm_rows_total = 0
    for item in normalized_results:
        title = item.get("title") or ""
        snippet = item.get("snippet") or ""
        url = item.get("url") or ""
        if "loan" not in (title.lower() + " " + snippet.lower()):
            continue
        player, club = _extract_player_club(title, snippet)
        if not player or not club:
            # Stage 1: score title/snippet and shortlisting
            rel, score, reason = _score_title_detail(llm_client, title, snippet, team_name, season_year)
            host = ""
            try:
                host = urlparse(url).netloc.lower()
            except Exception:
                host = ""
            is_allowed = True
            logger.info(
                "[brave-loans] LLM score title=%s host=%s rel=%s score=%.2f allowed=%s reason=%s",
                (title[:80] + "…") if len(title) > 80 else title,
                host,
                rel,
                score,
                is_allowed,
                (reason[:120] + "…") if len(reason) > 120 else reason,
            )
            if (not rel) or score < 0.40:
                logger.info("[brave-loans] skip: low score or not relevant")
                continue
            # Stage 2: fetch page text and extract via LLM (cap pages per team)
            try:
                import requests  # local import

                session = requests.Session()
                ua = os.getenv("BRAVE_CRAWL_USER_AGENT") or "AcademyWatchBot/1.0 (+https://theacademywatch.com)"
                session.headers.update({"User-Agent": ua, "Accept": "text/html,application/xhtml+xml"})
                logger.info("[brave-loans] fetching article url=%s", url)
                resp = session.get(url, timeout=10)
                if resp.status_code in (429, 403):
                    time.sleep(0.25)
                    resp = session.get(url, timeout=10)
                resp.raise_for_status()
                html = resp.text
                text = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
                text = re.sub(r"<style[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
                text = re.sub(r"<[^>]+>", " ", text)
                text = re.sub(r"\s+", " ", text)
                # guard band
                text = text.strip()[:12000]
                logger.info("[brave-loans] fetched bytes=%s trimmed_len=%s", len(html or ""), len(text))
            except Exception as exc:
                logger.debug("[brave-loans] fetch error for %s: %s", url, exc)
                continue
            llm_rows = _extract_from_text_with_llm(llm_client, text, team_name, season_year)
            logger.info("[brave-loans] LLM extracted rows=%s from url=%s", len(llm_rows), url)
            for r in llm_rows:
                key = (r["player_name"].lower(), r["loan_team"].lower())
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        "player_name": r["player_name"],
                        "loan_team": r["loan_team"],
                        "season_year": int(r.get("season_year") or season_year),
                        "parent_club": team_name,
                        "source": url,
                        "source_title": title,
                        "source_snippet": snippet,
                        "confidence": float(r.get("confidence") or 0.0),
                        "evidence": r.get("evidence") or "",
                    }
                )
                llm_rows_total += 1
            # small delay between article fetches
            time.sleep(0.15)
            continue
        # Deduplicate
        key = (player.lower(), club.lower())
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "player_name": player,
                "loan_team": club,
                "season_year": season_year,
                "parent_club": team_name,
                "source": url,
                "source_title": title,
                "source_snippet": snippet,
            }
        )
        regex_rows += 1

    logger.info(
        "[brave-loans] extracted_rows=%s (regex=%s, llm=%s) for query='%s'",
        len(rows),
        regex_rows,
        llm_rows_total,
        effective_query,
    )
    return BravePlayerCollection(rows=rows, results=normalized_results, query=effective_query)


__all__ = ["collect_players_from_brave", "BravePlayerCollection"]
