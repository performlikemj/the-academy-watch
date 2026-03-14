"""OpenAI Responses-based classifier for Wikipedia loan snippets."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Dict
from pydantic import BaseModel, Field
from pydantic.config import ConfigDict
try:  # Optional Groq dependency (used when API key configured)
    from groq import Groq
except ImportError:  # pragma: no cover
    Groq = None

@lru_cache(maxsize=1)
def _get_groq_client() -> Groq:
    try:
        api_key = os.getenv('GROQ_API_KEY')
        if api_key and Groq is not None:
            return Groq(api_key=api_key)
        raise RuntimeError('GROQ_API_KEY is not configured')
    except Exception:
        pass
    raise RuntimeError('GROQ_API_KEY is not configured')

class LoanMappingModel(BaseModel):
    model_config = ConfigDict(extra='forbid')
    valid: bool = Field(...)
    player_name: str = Field(...)
    parent_club: str = Field(...)
    loan_club: str = Field(...)
    season_start_year: int = Field(...)
    reason: str = Field(...)
    confidence: float = Field(...)

JSON_SCHEMA = {
    "name": "loan_mapping",
    "schema": LoanMappingModel.model_json_schema(),
}


SYSTEM_PROMPT = (
    "You are a data classifier that extracts structured loan information from short snippets "
    "of Wikipedia text describing football player loans. Respond strictly in JSON that matches the provided schema."
)


@lru_cache(maxsize=1)
def _get_groq_client() -> Groq:
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        raise RuntimeError('GROQ_API_KEY is not configured')
    return Groq(api_key=api_key)


def classify_loan_row(
    raw_text: str,
    *,
    default_player: str = '',
    default_parent: str = '',
    season_year: int | None = None,
) -> Dict[str, object]:
    """Classify a Wikipedia loan snippet using GPT-oss-120b responses API."""


    user_prompt = (
        f"Season: {season_year or 'unknown'}\n"
        f"Default player name: {default_player or 'unknown'}\n"
        f"Default parent club: {default_parent or 'unknown'}\n"
        f"Snippet: {raw_text.strip()}"
    )

    groq_client = _get_groq_client()
    response = groq_client.chat.completions.create(
        model="openai/gpt-oss-120b",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "loan_mapping",
                "schema": LoanMappingModel.model_json_schema(),
            }
        },
        max_tokens=300,
    )

    try:
        content = response.choices[0].message.content
        print(f'classifier response: {content}')
    except (AttributeError, IndexError) as exc:
        raise RuntimeError(f"Unexpected Groq response format: {response}") from exc

    data = json.loads(content)
    if season_year and not data.get('season_start_year'):
        data['season_start_year'] = season_year
    if default_player and not data.get('player_name'):
        data['player_name'] = default_player
    if default_parent and not data.get('parent_club'):
        data['parent_club'] = default_parent
    return data
