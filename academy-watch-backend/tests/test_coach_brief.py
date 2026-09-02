"""Shared coach-brief normalization stays identical at API and worker boundaries."""

import pytest
from src.services.coach_brief import MAX_BRIEF_LINES, brief_payload
from src.workers.vision_worker import _brief_payload


@pytest.mark.parametrize(
    "body",
    [
        "Hold width\r\nRecover inside",
        "\n\nHold width\nRecover inside",
        "Hold width   \n  Recover inside  ",
        "幅を保つ\n内側へ戻る",
        "Hold width\u2028Recover inside",
        "Hold width\x0bRecover inside\x0cScan early\x1dReset",
        "\n".join(f"Expectation {index}" for index in range(1, 10)),
        " \t\r\n\x0b\x0c\x1d ",
    ],
    ids=(
        "crlf",
        "leading-blank-lines",
        "trailing-spaces",
        "unicode",
        "unicode-line-separator",
        "vertical-separators",
        "nine-lines",
        "whitespace-only",
    ),
)
def test_shared_and_worker_brief_payloads_are_identical(body):
    worker_payload, _line_count = _brief_payload(body, max_lines=MAX_BRIEF_LINES)

    assert worker_payload == brief_payload(body, max_lines=MAX_BRIEF_LINES)
