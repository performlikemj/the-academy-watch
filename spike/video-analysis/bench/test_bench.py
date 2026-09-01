import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from adapters import common as adapter_common  # noqa: E402
from adapters.common import sample_timestamps  # noqa: E402
from adapters.qwen3vl_mlx import STUB_ERROR, run as run_mlx  # noqa: E402
from contract import parse_claims  # noqa: E402
from score import (  # noqa: E402
    box_matches,
    fabricated_event_classes,
    interpolate_truth_box,
    render_markdown,
    score_claim,
    score_clip,
    score_run,
    write_report,
)


def _truth(note=None):
    return {
        "clip_id": "clip-1",
        "window": {"start_s": 10.0, "end_s": 20.0},
        "box_track": [[10.0, 100, 100, 200, 200], [20.0, 200, 200, 300, 300]],
        "human_note": note,
    }


def _claim(**overrides):
    claim = {
        "claim": "The player holds position.",
        "t0": 14.0,
        "t1": 16.0,
        "box": [145, 145, 255, 255],
        "confidence": "high",
        "visibility": "clear",
    }
    claim.update(overrides)
    return claim


def test_contract_accepts_exact_valid_shape():
    parsed = parse_claims(json.dumps({"claims": [_claim()]}))

    assert len(parsed) == 1
    assert parsed[0]["malformed"] is False
    assert parsed[0]["t0"] == 14.0


def test_contract_keeps_missing_and_invalid_fields_as_malformed():
    parsed = parse_claims(
        {"claims": [{"claim": "Maybe", "t0": True, "box": [0, 0, 0, 2]}]}
    )

    assert len(parsed) == 1
    assert parsed[0]["claim"] == "Maybe"
    assert parsed[0]["malformed"] is True
    assert {
        "t0",
        "box_order",
        "missing:t1",
        "missing:confidence",
        "missing:visibility",
    } <= set(parsed[0]["malformed_fields"])


def test_contract_keeps_non_json_response_as_one_malformed_claim():
    parsed = parse_claims("not json")

    assert parsed[0]["claim"] == "not json"
    assert parsed[0]["malformed_fields"] == ["response_json"]


def test_contract_flags_unexpected_top_level_and_claim_fields():
    top = parse_claims({"claims": [], "commentary": "done"})
    claim = parse_claims({"claims": [{**_claim(), "player_name": "forbidden"}]})

    assert top[0]["malformed"] is True
    assert "unexpected:commentary" in top[0]["malformed_fields"]
    assert claim[0]["malformed"] is True
    assert "unexpected:player_name" in claim[0]["malformed_fields"]


def test_truth_box_is_interpolated_at_claim_midpoint():
    assert interpolate_truth_box(_truth()["box_track"], 15.0) == [
        150.0,
        150.0,
        250.0,
        250.0,
    ]
    assert interpolate_truth_box(_truth()["box_track"], 9.99) is None


def test_sampling_starts_where_the_truth_track_actually_begins():
    truth = {
        "window": {"start_s": 10.0, "end_s": 20.0},
        "box_track": [[10.1, 0, 0, 1, 1], [20.0, 0, 0, 1, 1]],
    }

    assert sample_timestamps(truth)[0] == (0.1, 10.1)


def test_shared_ollama_call_receives_capped_generation_options(monkeypatch, tmp_path):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"message":{"content":"{\\"claims\\":[]}"}}'

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(
        adapter_common.qwen_match_analysis.urllib.request, "urlopen", fake_urlopen
    )
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"frame")

    content = adapter_common.ollama_chat_with_options(
        "prompt",
        ollama_url="http://ollama.test",
        model="qwen3-vl:8b",
        timeout_s=12,
        image_paths=[image],
        options={"num_predict": 400, "repeat_penalty": 1.15},
    )

    assert content == '{"claims":[]}'
    assert captured["timeout"] == 12
    assert captured["body"]["format"] == "json"
    assert captured["body"]["options"] == {
        "temperature": 0,
        "num_predict": 400,
        "repeat_penalty": 1.15,
    }


def test_box_grounding_accepts_iou_threshold():
    grounded, iou, containment = box_matches([100, 100, 200, 200], [100, 100, 200, 200])

    assert grounded is True
    assert iou == 1.0
    assert containment == 1.0


def test_box_grounding_accepts_small_claim_contained_in_truth():
    grounded, iou, containment = box_matches([120, 120, 130, 130], [100, 100, 200, 200])

    assert grounded is True
    assert iou == 0.01
    assert containment == 1.0


def test_box_grounding_rejects_low_iou_and_containment():
    grounded, _iou, containment = box_matches([50, 50, 150, 150], [100, 100, 200, 200])

    assert grounded is False
    assert containment == 0.25


def test_time_grounding_allows_half_second_window_tolerance():
    scored = score_claim(_claim(t0=9.5, t1=10.5, box=[95, 95, 205, 205]), _truth())

    assert scored["time_grounded"] is True
    assert scored["box_grounded"] is True
    assert scored["supported"] is True


def test_time_grounding_rejects_interval_beyond_tolerance():
    scored = score_claim(_claim(t0=9.49, t1=10.5), _truth())

    assert scored["time_grounded"] is False
    assert scored["supported"] is False
    assert scored["unsupported"] is True


@pytest.mark.parametrize("overrides", [{"box": None}, {"t0": None}, {"t1": None}])
def test_hollow_when_time_or_box_is_absent(overrides):
    assert score_claim(_claim(**overrides), _truth())["hollow"] is True


def test_malformed_claim_cannot_be_supported_even_when_grounded():
    claim = {**_claim(), "malformed": True, "malformed_fields": ["source_schema"]}
    scored = score_claim(claim, _truth())

    assert scored["time_grounded"] is True
    assert scored["box_grounded"] is True
    assert scored["malformed"] is True
    assert scored["supported"] is False


def test_fabrication_is_conservative_keyword_class_match_only_with_note():
    assert fabricated_event_classes(
        "The player shoots and scores.", "The player takes a shot."
    ) == ["goal"]
    assert fabricated_event_classes("The player passes.", None) is None
    assert (
        score_claim(_claim(claim="The player shoots."), _truth("The player passes."))[
            "fabricated"
        ]
        is True
    )


def test_mechanical_error_forces_failed_and_discards_text():
    result = {
        "clip_id": "clip-1",
        "claims": [_claim()],
        "error": "timeout",
        "wall_s": 3,
        "tokens": 8,
    }
    scored = score_clip(result, _truth())

    assert scored["status"] == "failed"
    assert scored["claims"] == []


def test_missing_truth_is_observed_not_scored():
    result = {
        "clip_id": "unknown",
        "claims": [_claim()],
        "error": None,
        "wall_s": 1,
        "tokens": None,
    }
    scored = score_clip(result, None)

    assert scored["status"] == "observed"
    assert scored["metrics"] is None


def test_overall_rates_exclude_failed_and_observed_clips():
    results = [
        {
            "clip_id": "clip-1",
            "claims": [_claim()],
            "error": None,
            "wall_s": 2,
            "tokens": 10,
        },
        {
            "clip_id": "failed",
            "claims": [_claim()],
            "error": "decode",
            "wall_s": 4,
            "tokens": 20,
        },
        {
            "clip_id": "observed",
            "claims": [_claim()],
            "error": None,
            "wall_s": 6,
            "tokens": None,
        },
    ]
    report = score_run(results, {"clip-1": _truth()})

    assert report["overall"]["supported_rate"] == 1.0
    assert report["overall"]["claims_per_clip"] == 1.0
    assert report["overall"]["failed_clips"] == 1
    assert report["overall"]["observed_clips"] == 1
    assert report["overall"]["wall_s_per_clip"] == 4.0
    assert report["overall"]["tokens_per_clip"] == 15.0


def test_time_only_and_hollow_rates_capture_boxless_baseline():
    result = {
        "clip_id": "clip-1",
        "claims": [_claim(box=None)],
        "error": None,
        "wall_s": 1,
        "tokens": None,
    }
    report = score_run([result], {"clip-1": _truth()}, adapter="baseline")

    assert report["overall"]["supported_rate"] == 0.0
    assert report["overall"]["time_only_rate"] == 1.0
    assert report["overall"]["unsupported_rate"] == 1.0
    assert report["overall"]["hollow_rate"] == 1.0


def test_report_writers_produce_json_and_explain_conservative_fabrication(tmp_path):
    report = score_run(
        [
            {
                "clip_id": "clip-1",
                "claims": [_claim()],
                "error": None,
                "wall_s": 1,
                "tokens": 2,
            }
        ],
        {"clip-1": _truth()},
    )
    json_path, markdown_path = write_report(report, tmp_path)

    assert json.loads(json_path.read_text())["overall"]["supported_rate"] == 1.0
    assert "conservative explicit keyword-class" in markdown_path.read_text()
    assert "Per clip" in render_markdown(report)


def test_mlx_adapter_fails_fast_with_actionable_message():
    result = run_mlx("clip.mp4", _truth(), {})

    assert result["wall_s"] == 0.0
    assert result["error"] == STUB_ERROR
    assert "native-video" in result["error"]
