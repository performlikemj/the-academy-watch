"""Provider-bound history must retain only complete tool exchanges after trimming."""

from copy import deepcopy
from unittest.mock import Mock

import pytest
from src.services.gol_service import GolService


def _calls(*ids):
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {"id": call_id, "type": "function", "function": {"name": "search_web", "arguments": "{}"}}
            for call_id in ids
        ],
    }


def _result(call_id):
    return {"role": "tool", "tool_call_id": call_id, "content": "result"}


USER = {"role": "user", "content": "Question"}
ANSWER = {"role": "assistant", "content": "Answer"}


@pytest.mark.parametrize(
    ("history", "expected"),
    [
        pytest.param(
            [_calls("a", "b"), _result("a"), _result("b")] + [ANSWER] * 18,
            [ANSWER] * 18,
            id="cap-leaves-leading-orphan-tools",
        ),
        pytest.param([USER, _calls("a")], [USER], id="missing-all-results"),
        pytest.param(
            [USER, _calls("a", "b"), _result("a"), ANSWER],
            [USER, ANSWER],
            id="missing-one-result-also-removes-new-orphan",
        ),
        pytest.param(
            [USER, _calls("a"), ANSWER, _result("a")],
            [USER, ANSWER],
            id="result-must-follow-call",
        ),
        pytest.param(
            [USER, _calls("a", "b"), _result("b"), _result("a"), ANSWER],
            [USER, _calls("a", "b"), _result("b"), _result("a"), ANSWER],
            id="complete-tool-history-unchanged",
        ),
        pytest.param([USER, ANSWER] * 12, [USER, ANSWER] * 10, id="normal-history-capped-unchanged"),
    ],
)
def test_chat_sends_complete_trimmed_history(history, expected):
    original = deepcopy(history)
    # Exercise chat's actual provider boundary without a model client or database.
    service = GolService.__new__(GolService)
    service._run_completion = Mock(return_value=iter([{"event": "done", "data": {}}]))

    assert list(service.chat("Next", history, "test-session")) == [{"event": "done", "data": {}}]

    sent = service._run_completion.call_args.args[0]
    assert sent[0]["role"] == "system"
    assert sent[1:-1] == expected
    assert sent[-1] == {"role": "user", "content": "Next"}
    assert history == original
