import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from adapters import common as adapter_common  # noqa: E402
from adapters import qwen3vl_ollama as qwen_adapter  # noqa: E402
from adapters.common import sample_timestamps  # noqa: E402
from adapters.qwen3vl_mlx import STUB_ERROR, run as run_mlx  # noqa: E402
from contract import parse_claims  # noqa: E402
from run_bench import (  # noqa: E402
    _find_resume_dir,
    _resolve_inference_settings,
    _run_metadata,
    _write_run_metadata,
)
from score import (  # noqa: E402
    box_matches,
    fabricated_event_classes,
    interpolate_truth_box,
    max_interpolation_gap_s,
    render_markdown,
    score_claim,
    score_clip,
    score_run,
    tracking_cadence_s,
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


def test_tracking_cadence_uses_median_positive_sample_gap():
    track = [
        [10.0, 0, 0, 10, 10],
        [10.1, 0, 0, 10, 10],
        [10.2, 0, 0, 10, 10],
        [13.2, 0, 0, 10, 10],
        [13.3, 0, 0, 10, 10],
    ]

    assert tracking_cadence_s(track) == pytest.approx(0.1)
    assert max_interpolation_gap_s(track) == 0.25


def test_tracking_gap_has_no_truth_and_cannot_support_claim():
    truth = {
        "clip_id": "gap-clip",
        "window": {"start_s": 10.0, "end_s": 14.0},
        "box_track": [
            [10.0, 100, 100, 200, 200],
            [10.1, 100, 100, 200, 200],
            [10.2, 100, 100, 200, 200],
            [13.2, 100, 100, 200, 200],
            [13.3, 100, 100, 200, 200],
        ],
        "human_note": None,
    }
    in_gap = score_claim(_claim(t0=11.7, t1=11.7, box=[100, 100, 200, 200]), truth)
    just_outside = score_claim(
        _claim(t0=13.25, t1=13.25, box=[100, 100, 200, 200]), truth
    )

    assert interpolate_truth_box(truth["box_track"], 11.7) is None
    assert in_gap["truth_box_at_midpoint"] is None
    assert in_gap["no_truth_at_time"] is True
    assert in_gap["supported"] is False
    assert just_outside["no_truth_at_time"] is False
    assert just_outside["supported"] is True

    result = {
        "clip_id": "gap-clip",
        "claims": [
            _claim(t0=11.7, t1=11.7, box=[100, 100, 200, 200]),
            _claim(t0=13.25, t1=13.25, box=[100, 100, 200, 200]),
        ],
        "error": None,
    }
    report = score_run([result], {"gap-clip": truth})
    assert report["clips"][0]["metrics"]["untracked_gap"] == 1
    assert report["overall"]["untracked_gap"] == 1
    assert report["overall"]["untracked_gap_rate"] == 0.5
    assert report["overall"]["unsupported_rate"] == 0.5


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


def test_anchor_first_draws_only_on_frame_zero(monkeypatch, tmp_path):
    frames = [
        (tmp_path / "frame-0.jpg", 10.0),
        (tmp_path / "frame-1.jpg", 15.0),
        (tmp_path / "frame-2.jpg", 20.0),
    ]
    truth = {
        "jersey_number": 12,
        "frame_size": [1920, 1080],
        "box_track": [
            [10.0, 100, 100, 200, 200],
            [20.0, 200, 200, 300, 300],
        ],
    }
    drawn = []
    monkeypatch.setattr(
        qwen_adapter,
        "draw_truth_box",
        lambda frame, box, frame_size, jersey: drawn.append(
            (frame, box, frame_size, jersey)
        ),
    )

    anchors = qwen_adapter.apply_anchors(frames, truth, "first")

    assert [call[0] for call in drawn] == [frames[0][0]]
    assert anchors == [{"t": 10.0, "box": [100.0, 100.0, 200.0, 200.0]}]
    prompt = qwen_adapter.build_prompt(
        {**truth, "window": {"start_s": 10, "end_s": 20}},
        [10.0, 15.0, 20.0],
        "first",
    )
    assert (
        "the first image identifies the player with a red rectangle; the other images are "
        "unlabelled — find that same player yourself and box the evidence region in those frames"
        in prompt
    )
    all_prompt = qwen_adapter.build_prompt(
        {**truth, "window": {"start_s": 10, "end_s": 20}},
        [10.0, 15.0, 20.0],
        "all",
    )
    assert (
        "Every frame contains a thin red\nrectangle labelled #12. Describe ONLY the boxed player."
        in all_prompt
    )
    drawn.clear()
    all_anchors = qwen_adapter.apply_anchors(frames, truth, "all")
    assert [call[0] for call in drawn] == [frame[0] for frame in frames]
    assert [anchor["t"] for anchor in all_anchors] == [10.0, 15.0, 20.0]


def test_boxed_frame_tagging_uses_t0_and_half_second_tolerance():
    claims = [
        _claim(t0=9.5),
        _claim(t0=10.5),
        _claim(t0=10.501),
        _claim(t0=None),
    ]

    tagged = qwen_adapter.tag_boxed_frames(
        claims, [{"t": 10.0, "box": [100, 100, 200, 200]}]
    )

    assert [claim["boxed_frame"] for claim in tagged] == [True, True, False, False]


def test_resume_fingerprint_mismatch_is_not_resumed_and_is_refused(tmp_path):
    first_settings = {
        "adapter": "qwen3vl_ollama",
        "model": "qwen3-vl:8b",
        "ollama_url": "http://ollama.test",
        "timeout_s": 300.0,
        "anchor_mode": "first",
        "num_predict": 400,
        "repeat_penalty": 1.15,
        "frozen_set_id": "frozen-1",
    }
    first = _run_metadata(first_settings, ["clip-1"])
    changed = _run_metadata({**first_settings, "timeout_s": 301.0}, ["clip-1"])
    run_dir = tmp_path / "run-1"
    _write_run_metadata(run_dir, first)

    assert _find_resume_dir(tmp_path, changed) is None
    with pytest.raises(ValueError, match="fingerprint mismatch.*--force.*--run-id"):
        _write_run_metadata(run_dir, changed)


def test_run_metadata_records_model_resolved_from_environment(monkeypatch):
    monkeypatch.setenv("BENCH_MODEL", "qwen3-vl:env-fallback")
    args = SimpleNamespace(
        adapter="qwen3vl_ollama",
        model=None,
        ollama_url="http://ollama.test",
        timeout=123.0,
        anchor_mode="first",
        num_predict=350,
        repeat_penalty=1.2,
    )

    settings = _resolve_inference_settings(args, {"frozen_set_id": "frozen-1"})
    metadata = _run_metadata(settings, ["clip-1"])

    assert metadata["model"] == "qwen3-vl:env-fallback"
    assert metadata["model"] is not None
    assert metadata["ollama_url"] == "http://ollama.test"
    assert metadata["timeout_s"] == 123.0
    assert metadata["anchor_mode"] == "first"
    assert metadata["num_predict"] == 350
    assert metadata["repeat_penalty"] == 1.2
    assert metadata["adapter"] == "qwen3vl_ollama"
    assert metadata["frozen_set_id"] == "frozen-1"


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


def test_metrics_split_boxed_and_unboxed_grounding():
    truth = {
        "clip_id": "clip-1",
        "window": {"start_s": 10.0, "end_s": 20.0},
        "box_track": [
            [10.0, 100, 100, 200, 200],
            [20.0, 100, 100, 200, 200],
        ],
        "human_note": None,
    }
    result = {
        "clip_id": "clip-1",
        "claims": [
            _claim(t0=10.0, t1=10.0, box=[100, 100, 200, 200], boxed_frame=True),
            _claim(t0=15.0, t1=15.0, box=[100, 100, 200, 200], boxed_frame=False),
            _claim(t0=18.0, t1=18.0, box=[0, 0, 20, 20], boxed_frame=False),
        ],
        "anchored_frames": [{"t": 10.0, "box": [100, 100, 200, 200]}],
        "error": None,
        "wall_s": 1,
        "tokens": None,
    }

    report = score_run([result], {"clip-1": truth}, adapter="qwen3vl_ollama")
    metrics = report["overall"]

    assert metrics["boxed_claim_count"] == 1
    assert metrics["unboxed_claim_count"] == 2
    assert metrics["supported_rate_boxed"] == 1.0
    assert metrics["supported_rate_unboxed"] == 0.5
    assert metrics["box_grounded_rate_boxed"] == 1.0
    assert metrics["box_grounded_rate_unboxed"] == 0.5
    assert metrics["echo_suspect_count"] == 1


def test_echo_suspect_requires_boxed_frame_and_all_sides_within_two_pixels():
    anchors = [{"t": 10.0, "box": [100, 100, 200, 200]}]

    boundary = score_claim(
        _claim(
            t0=10,
            t1=10,
            box=[98, 102, 202, 198],
            boxed_frame=True,
        ),
        _truth(),
        anchors,
    )
    outside = score_claim(
        _claim(
            t0=10,
            t1=10,
            box=[97.99, 102, 202, 198],
            boxed_frame=True,
        ),
        _truth(),
        anchors,
    )
    unboxed = score_claim(
        _claim(
            t0=10,
            t1=10,
            box=[100, 100, 200, 200],
            boxed_frame=False,
        ),
        _truth(),
        anchors,
    )

    assert boundary["echo_suspect"] is True
    assert outside["echo_suspect"] is False
    assert unboxed["echo_suspect"] is False


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
