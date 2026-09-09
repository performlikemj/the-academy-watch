"""Pydantic v2 meaning-only contract; geometry remains owned by the tracker."""

from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

try:
    from .adapters.common import qwen_match_analysis
except ImportError:  # pragma: no cover
    from adapters.common import qwen_match_analysis

ACTION_TYPES = tuple(
    dict.fromkeys((*qwen_match_analysis.ACTION_TYPES, "none", "unclear"))
)
PHASES = qwen_match_analysis.PHASES
CONFIDENCE = qwen_match_analysis.CLAIM_CONFIDENCE_LEVELS  # low is the honest exit
PLAYER_VISIBLE = ("yes", "partially", "no", "unclear")
KIT_COLORS = ("red", "blue", "white", "black", "yellow", "green", "other", "unclear")
OUTCOMES = ("completed", "incomplete", "unclear")
VOCABULARIES = {
    "event_type": ACTION_TYPES,
    "phase": PHASES,
    "outcome": OUTCOMES,
    "confidence": CONFIDENCE,
    "player_visible": PLAYER_VISIBLE,
    "kit_color_seen": KIT_COLORS,
}


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)


class SemanticEvent(Strict):
    event_type: Literal[*ACTION_TYPES]
    phase: Literal[*PHASES]
    t0: float
    t1: float
    outcome: Literal[*OUTCOMES]
    confidence: Literal[*CONFIDENCE]

    @model_validator(mode="after")
    def ordered(self) -> SemanticEvent:
        if self.t1 < self.t0:
            raise ValueError("event times must be ordered")
        return self


class SemanticRead(Strict):
    events: list[SemanticEvent] = Field(max_length=3)
    player_visible: Literal[*PLAYER_VISIBLE]
    kit_color_seen: Literal[*KIT_COLORS]
    sentence: str = Field(min_length=1, max_length=200)

    @field_validator("sentence")
    @classmethod
    def one_sentence(cls, value: str) -> str:
        # Decimal timestamps are allowed; multiple prose sentences/newlines are not.
        if (
            not value.strip()
            or "\n" in value
            or "\r" in value
            or re.search(r"[.!?]\s+\S", value)
        ):
            raise ValueError("sentence must contain one nonempty sentence")
        return value


def parse_read(content: str) -> SemanticRead:
    return SemanticRead.model_validate_json(content)


def response_schema() -> dict:
    return qwen_match_analysis.inline_local_json_schema_refs(
        SemanticRead.model_json_schema()
    )
