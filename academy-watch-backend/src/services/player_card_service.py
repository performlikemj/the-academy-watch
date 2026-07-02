"""Player card generation — the ONLY LLM step in the digest pipeline.

For each ``player_pulse`` row above threshold that has no cached card yet, this
generates a 2-3 sentence editorial card ONCE and writes it to
``player_card_cache``. Every user following that player reuses the same cached
card, so LLM cost scales with the newsworthy slice of the content universe, never
with audience size.

Honesty contract: the prompt receives ONLY verified structured numbers pulled
from the pulse row's ``delta_json`` (never free text, never fabricated stats).
Every number in a card comes from that payload.

The LLM client + model + call shape mirror the Groq chat-completions helpers in
``agents/weekly_newsletter_agent.py`` (``_summarize_player_with_groq``), but the
client is built lazily so importing this module triggers NO network / no client
construction. Failures skip the player (no cache row) so the next run retries.
"""

import html
import json
import logging
import os
from datetime import UTC, date, datetime

from sqlalchemy import func
from src.models.league import db
from src.models.pulse import PlayerCardCache, PlayerPulse

logger = logging.getLogger(__name__)

# Env-tunable, mirroring the contract + the newsletter Groq conventions.
_DEFAULT_MODEL = "openai/gpt-oss-120b"
DEFAULT_CARD_THRESHOLD = float(os.getenv("PULSE_CARD_THRESHOLD", "3.0"))
DEFAULT_CARD_LIMIT = int(os.getenv("PULSE_CARD_LIMIT", "100"))

_GROQ_CLIENT = None

CARD_SYSTEM_PROMPT = (
    "You are a football scout writing a terse card for an academy-player digest. "
    "You receive a JSON payload of VERIFIED stats and highlights for one player over "
    "a recent window. Write 2-3 sentences that read like a scout's notebook entry.\n\n"
    "STRICT RULES (never break these):\n"
    "- Use ONLY the numbers and facts in the payload. Never invent goals, assists, "
    "minutes, appearances, milestones, clubs, opponents, dates, or context.\n"
    "- Keep every number exactly as given.\n"
    "- Only claim a debut / first goal / first start / promotion if it appears in "
    "'highlights'.\n"
    "- No weather, crowd, scorelines, or match narrative that is not in the payload.\n"
    "- Plain prose only: NO markdown, NO headings, NO bullet points, NO emoji.\n\n"
    "Aim for 2-3 sentences, warm but factual."
)


def _get_groq_client():
    """Lazy Groq client (mirrors weekly_newsletter_agent._get_groq_client).

    Built on first use only, so importing this module never constructs a client
    or touches the network."""
    global _GROQ_CLIENT
    if _GROQ_CLIENT is not None:
        return _GROQ_CLIENT
    try:
        from groq import Groq
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("groq package is not installed") from exc
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured")
    _GROQ_CLIENT = Groq(api_key=api_key)
    return _GROQ_CLIENT


def _resolve_model() -> str:
    model = os.getenv("PULSE_CARD_MODEL") or os.getenv("NEWSLETTER_GROQ_MODEL") or _DEFAULT_MODEL
    return model[:40]  # player_card_cache.model is VARCHAR(40)


def _coerce_window_end(window_end) -> date:
    if window_end is None:
        return datetime.now(UTC).date()
    if isinstance(window_end, datetime):
        return window_end.date()
    if isinstance(window_end, date):
        return window_end
    return date.fromisoformat(str(window_end))


def _ensure_period(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return ""
    if stripped[-1] in ".!?":
        return stripped
    if stripped[-1] in ",;:":
        stripped = stripped[:-1].rstrip()
        if not stripped:
            return ""
    return stripped + "."


def _clean_card_text(content: str) -> str:
    """Trim to the last complete sentence and ensure terminal punctuation —
    matches the newsletter agent's post-processing."""
    content = (content or "").strip()
    if not content:
        return ""
    last_stop = max(content.rfind("."), content.rfind("!"), content.rfind("?"))
    if last_stop != -1:
        content = content[: last_stop + 1].strip()
    return _ensure_period(content)


def _build_card_payload(pulse_row: PlayerPulse) -> dict:
    """Verified-only payload for the prompt, from the pulse row's delta_json."""
    delta = pulse_row.delta_json or {}
    context = delta.get("context") or {}
    totals = delta.get("window_totals") or {}
    signals = delta.get("signals") or {}
    highlights = [sig["label"] for sig in signals.values() if isinstance(sig, dict) and sig.get("label")]
    return {
        "player": {
            "name": context.get("name"),
            "position": context.get("position"),
            "parent_club": context.get("parent_club"),
            "current_club": context.get("current_club"),
            "status": context.get("status"),
            "level": context.get("current_level"),
        },
        "window": {
            "start": delta.get("window_start"),
            "end": delta.get("window_end"),
            "days": delta.get("window_days"),
        },
        "stats": {
            "goals": totals.get("goals", 0),
            "assists": totals.get("assists", 0),
            "appearances": totals.get("appearances", 0),
            "starts": totals.get("starts", 0),
            "minutes": totals.get("minutes", 0),
        },
        "highlights": highlights,
    }


def _generate_card_text(payload: dict, model: str) -> str:
    """THE ONLY function that calls the LLM. Tests monkeypatch this by name so a
    live call never runs. Returns the RAW model content; ``generate_cards`` trims
    it to whole sentences (so the trim/empty-skip logic runs on mocked output
    too)."""
    client = _get_groq_client()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": CARD_SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
        ],
        temperature=0.3,
        max_tokens=200,
    )
    return response.choices[0].message.content if response.choices else ""


def _to_card_html(text: str) -> str:
    """Outlook-safe fragment: a single escaped ``<p>`` (plain <p>/<strong> only)."""
    return f"<p>{html.escape(text)}</p>" if text else ""


def generate_cards(window_end, threshold=None, limit=None, *, dry_run: bool = False) -> dict:
    """Generate + cache cards for the highest-scoring uncached pulse rows.

    Selects ``player_pulse`` rows for ``window_end`` with ``score >= threshold``
    that have no ``player_card_cache`` row yet, ordered by score, capped at
    ``limit``. Each generates ONE card via the LLM (mocked in tests) and writes a
    cache row. Cache reuse is automatic: a second run for the same window finds
    every card already cached and generates 0. ``dry_run`` lists candidates and
    makes ZERO LLM calls / writes nothing.

    Returns ``{generated, skipped_cached, candidates, ...}``.
    """
    window_end = _coerce_window_end(window_end)
    threshold = DEFAULT_CARD_THRESHOLD if threshold is None else float(threshold)
    limit = DEFAULT_CARD_LIMIT if limit is None else int(limit)
    limit = max(limit, 0)
    model = _resolve_model()

    above = (
        PlayerPulse.query.filter(PlayerPulse.window_end == window_end, PlayerPulse.score >= threshold)
        .order_by(PlayerPulse.score.desc(), PlayerPulse.player_api_id.asc())
        .all()
    )
    cached_ids = {
        pid for (pid,) in db.session.query(PlayerCardCache.player_api_id).filter_by(window_end=window_end).all()
    }
    eligible = [row for row in above if row.player_api_id not in cached_ids]
    skipped_cached = len(above) - len(eligible)
    batch = eligible[:limit]
    candidates = [{"player_api_id": row.player_api_id, "score": row.score} for row in batch]

    generated = 0
    failed = 0
    if not dry_run:
        for row in batch:
            payload = _build_card_payload(row)
            try:
                raw = _generate_card_text(payload, model)
            except Exception as exc:
                logger.warning("Card generation failed for player %s: %s", row.player_api_id, exc)
                failed += 1
                continue
            text = _clean_card_text(raw)
            if not text:
                failed += 1
                continue
            db.session.add(
                PlayerCardCache(
                    player_api_id=row.player_api_id,
                    window_end=window_end,
                    card_html=_to_card_html(text),
                    card_text=text,
                    model=model,
                )
            )
            generated += 1
        if generated:
            db.session.commit()

    return {
        "window_end": window_end.isoformat(),
        "threshold": threshold,
        "limit": limit,
        "model": model,
        "dry_run": dry_run,
        "candidates_total": len(eligible),
        "skipped_cached": skipped_cached,
        "generated": generated,
        "failed": failed,
        "candidates": candidates,
    }


def latest_card_window() -> date | None:
    """Most recent window_end with any cached card — the render seam's default
    window for the digest lookup."""
    return db.session.query(func.max(PlayerCardCache.window_end)).scalar()


def get_cards_for_window(window_end, player_api_ids=None) -> dict[int, dict]:
    """Batch render lookup: ``{player_api_id: {card_html, card_text, model}}`` for
    a window. Empty dict when nothing is cached (so the digest falls through to
    its byte-identical legacy output). This is the additive seam Builder B reads
    at render time."""
    window_end = _coerce_window_end(window_end)
    query = PlayerCardCache.query.filter_by(window_end=window_end)
    if player_api_ids is not None:
        ids = [int(pid) for pid in player_api_ids]
        if not ids:
            return {}
        query = query.filter(PlayerCardCache.player_api_id.in_(ids))
    return {
        row.player_api_id: {"card_html": row.card_html, "card_text": row.card_text, "model": row.model}
        for row in query.all()
    }
