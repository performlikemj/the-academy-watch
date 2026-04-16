"""
Service to parse unstructured text (match reports, stats pages) into structured stats using Groq/LLM.
"""

import json
import logging
import os
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)

try:
    from groq import Groq
except ImportError:
    Groq = None


class FixturePlayerStats(BaseModel):
    """Structured stats for a player in a fixture."""

    model_config = ConfigDict(extra="ignore")

    minutes: int | None = Field(None, description="Minutes played")
    goals: int | None = Field(None, description="Goals scored")
    assists: int | None = Field(None, description="Assists made")
    shots_total: int | None = Field(None, description="Total shots")
    shots_on: int | None = Field(None, description="Shots on target")
    passes_total: int | None = Field(None, description="Total passes")
    passes_key: int | None = Field(None, description="Key passes")
    tackles_total: int | None = Field(None, description="Total tackles")
    duels_total: int | None = Field(None, description="Total duels")
    duels_won: int | None = Field(None, description="Duels won")
    dribbles_attempts: int | None = Field(None, description="Dribble attempts")
    dribbles_success: int | None = Field(None, description="Successful dribbles")
    rating: str | None = Field(None, description="Match rating (e.g. '7.5')")
    position: str | None = Field(None, description="Position played (e.g. 'F', 'M', 'D', 'G')")


SYSTEM_PROMPT = (
    "You are a sports data extractor. Extract detailed football player statistics from the provided text snippet "
    "(match report, live commentary, or stats summary). "
    "Return ONLY a JSON object matching the schema. "
    "If a stat is not explicitly mentioned, omit it or set to null. "
    "Be conservative: do not hallucinate stats."
)


@lru_cache(maxsize=1)
def _get_groq_client() -> Groq | None:
    api_key = os.getenv("GROQ_API_KEY")
    if api_key and Groq is not None:
        return Groq(api_key=api_key)
    return None


def parse_stats_from_text(
    text: str,
    player_name: str,
    team_name: str,
) -> dict[str, Any]:
    """
    Parse unstructured text to extract stats for a specific player.
    """
    client = _get_groq_client()
    if not client:
        logger.warning("Groq client not available for stats parsing")
        return {}

    user_prompt = (
        f"Extract stats for player: {player_name}\n"
        f"Team: {team_name}\n"
        f"Text:\n{text[:4000]}"  # Truncate to avoid token limits if necessary
    )

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # Using a capable model for extraction
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,  # Low temperature for factual extraction
        )

        content = response.choices[0].message.content
        if not content:
            return {}

        data = json.loads(content)
        # Validate with Pydantic (optional, but good for sanitization)
        stats = FixturePlayerStats(**data)
        return stats.model_dump(exclude_none=True)

    except Exception as e:
        logger.error(f"Error parsing stats with Groq: {e}")
        return {}
