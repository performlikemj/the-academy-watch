"""Guardrails AI integration for GOL chatbot safety.

Provides input validation (prompt injection, topic restriction) and
output validation (toxicity, PII redaction) using guardrails-ai validators.

Install validators:
    guardrails hub install hub://guardrails/detect_jailbreak
    guardrails hub install hub://guardrails/toxic_language
    guardrails hub install hub://guardrails/detect_pii
    guardrails hub install hub://guardrails/profanity_free
    guardrails hub install hub://guardrails/restrict_to_topic
"""

import logging
import os

logger = logging.getLogger(__name__)

_ENABLED = None
_input_guard = None
_output_guard = None

REJECTION_MESSAGE = (
    "I can only help with football and academy-related questions. "
    "Try asking about players, loans, academies, or match stats!"
)


def _is_enabled() -> bool:
    """Check if guardrails is enabled and available."""
    global _ENABLED
    if _ENABLED is not None:
        return _ENABLED

    if not os.getenv('GUARDRAILS_ENABLED', '').lower() in ('1', 'true', 'yes'):
        logger.info("Guardrails disabled (set GUARDRAILS_ENABLED=true to enable)")
        _ENABLED = False
        return False

    try:
        import guardrails  # noqa: F401
        _ENABLED = True
        logger.info("Guardrails AI enabled")
    except ImportError:
        logger.warning("guardrails-ai not installed — guardrails disabled")
        _ENABLED = False

    return _ENABLED


def _get_input_guard():
    """Lazy-init the input guard (validates user messages)."""
    global _input_guard
    if _input_guard is not None:
        return _input_guard

    from guardrails import Guard
    from guardrails.hub import DetectJailbreak, RestrictToTopic

    _input_guard = Guard(name="gol_input").use_many(
        DetectJailbreak(on_fail="exception"),
        RestrictToTopic(
            valid_topics=[
                "football", "soccer", "players", "academies",
                "loans", "transfers", "premier league", "statistics",
                "teams", "managers", "coaches", "matches", "fixtures",
                "goals", "assists", "ratings", "performance",
                "career", "youth development", "scouting",
            ],
            disable_llm=True,
            on_fail="exception",
        ),
    )
    return _input_guard


def _get_output_guard():
    """Lazy-init the output guard (validates LLM responses)."""
    global _output_guard
    if _output_guard is not None:
        return _output_guard

    from guardrails import Guard
    from guardrails.hub import ToxicLanguage, ProfanityFree, DetectPII

    _output_guard = Guard(name="gol_output").use_many(
        ToxicLanguage(threshold=0.7, on_fail="fix"),
        ProfanityFree(on_fail="fix"),
        DetectPII(
            pii_entities=["EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD"],
            on_fail="fix",
        ),
    )
    return _output_guard


def validate_input(message: str) -> tuple[bool, str | None]:
    """Validate user input before sending to LLM.

    Returns:
        (is_safe, rejection_reason) — if is_safe is False, rejection_reason
        contains a user-friendly message to return instead of calling the LLM.
    """
    if not _is_enabled():
        return True, None

    try:
        guard = _get_input_guard()
        result = guard.parse(message)
        if result.validation_passed:
            return True, None
        logger.info(f"Input guard rejected message: {message[:80]}")
        return False, REJECTION_MESSAGE
    except Exception as e:
        logger.warning(f"Input guard triggered: {e}")
        return False, REJECTION_MESSAGE


def validate_output(text: str) -> str:
    """Validate and sanitize LLM output.

    Returns the cleaned text. If the guard can't run or errors,
    returns the original text (fail-open for output).
    """
    if not _is_enabled():
        return text

    if not text or not text.strip():
        return text

    try:
        guard = _get_output_guard()
        result = guard.parse(text)
        cleaned = result.validated_output
        if cleaned and cleaned != text:
            logger.info("Output guard modified LLM response")
        return cleaned or text
    except Exception as e:
        logger.warning(f"Output guard error (fail-open): {e}")
        return text
