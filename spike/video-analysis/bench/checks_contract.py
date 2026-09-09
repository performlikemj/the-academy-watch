"""Strict closed-answer contract. Reasons are audit-only, never scoring inputs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

try:
    from .semantic_contract import KIT_COLORS
    from .adapters.common import qwen_match_analysis
except ImportError:  # pragma: no cover
    from semantic_contract import KIT_COLORS
    from adapters.common import qwen_match_analysis

CONTRACT_VERSION = "film-room-checks-v1"
BINARY_QUESTIONS = (
    "player_on_pitch",
    "play_in_progress",
    "ball_near_player",
    "player_touches_ball",
    "player_running",
)
QUESTIONS = (*BINARY_QUESTIONS, "kit_color_seen")


class Strict(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class Answer(Strict):
    answer: Literal["yes", "no", "unclear"]
    confidence: Literal["low", "medium", "high"]
    reason: str | None = Field(default=None, max_length=80)


class KitAnswer(Strict):
    answer: Literal[*KIT_COLORS]
    confidence: Literal["low", "medium", "high"]
    reason: str | None = Field(default=None, max_length=80)


class ChecksRead(Strict):
    player_on_pitch: Answer
    play_in_progress: Answer
    ball_near_player: Answer
    player_touches_ball: Answer
    player_running: Answer
    kit_color_seen: KitAnswer


def parse_read(content: str) -> ChecksRead:
    return ChecksRead.model_validate_json(content)


def response_schema() -> dict:
    return qwen_match_analysis.inline_local_json_schema_refs(
        ChecksRead.model_json_schema()
    )
