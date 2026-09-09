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
from adapters.common import sample_timestamps, scale_box  # noqa: E402
from adapters import qwen3vl_mlx as mlx_adapter  # noqa: E402
from contract import CONFIDENCE_VALUES, VISIBILITY_VALUES, parse_claims  # noqa: E402
from run_bench import (  # noqa: E402
    _find_resume_dir,
    _resolve_inference_settings,
    _run_metadata,
    _write_run_metadata,
    run_benchmark,
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
    parsed = parse_claims(json.dumps({"claims": [_claim(box_t=15.0)]}))

    assert len(parsed) == 1
    assert parsed[0]["malformed"] is False
    assert parsed[0]["t0"] == 14.0
    assert parsed[0]["box_t"] == 15.0
    assert parsed[0]["box_t_source"] == "provided"


def test_missing_box_t_falls_back_to_t0_with_source_recorded():
    parsed = parse_claims({"claims": [_claim(t0=12.25, t1=13.0)]})

    assert parsed[0]["malformed"] is False
    assert parsed[0]["box_t"] == 12.25
    assert parsed[0]["box_t_source"] == "fallback_t0"


def test_box_t_outside_claim_span_is_malformed():
    parsed = parse_claims({"claims": [_claim(box_t=16.51)]})

    assert parsed[0]["malformed"] is True
    assert "box_t outside claim span" in parsed[0]["malformed_fields"]


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


def test_box_t_in_tracking_gap_has_no_truth_at_time():
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

    scored = score_claim(
        _claim(t0=10.0, t1=13.3, box_t=11.7, box=[100, 100, 200, 200]),
        truth,
    )

    assert scored["truth_box_at_box_t"] is None
    assert scored["no_truth_at_time"] is True
    assert scored["supported"] is False


def test_sampling_starts_where_the_truth_track_actually_begins():
    truth = {
        "window": {"start_s": 10.0, "end_s": 20.0},
        "box_track": [[10.1, 0, 0, 1, 1], [20.0, 0, 0, 1, 1]],
    }

    assert sample_timestamps(truth)[0] == (0.1, 10.1)


def test_box_conversion_scales_x_and_y_independently_and_preserves_raw_box():
    claims = [{"box": [100.0, 200.0, 1100.0, 400.0]}]

    converted = qwen_adapter.convert_claim_boxes(
        claims,
        source_size=(1920, 1080),
        sent_size=(1280, 800),
        box_space="image_pixels",
    )

    assert converted[0]["box_model_space"] == [100.0, 200.0, 1100.0, 400.0]
    assert converted[0]["box"] == [150.0, 270.0, 1650.0, 540.0]
    assert converted[0]["box_space"] == "image_pixels"
    assert converted[0].get("box_sanity_reason") is None


def test_box_conversion_is_unchanged_when_sent_size_equals_source_size():
    box = [101.25, 202.5, 303.75, 405.0]

    assert scale_box(box, (800, 800), (800, 800)) == box
    converted = qwen_adapter.convert_claim_boxes(
        [{"box": box.copy()}],
        source_size=(800, 800),
        sent_size=(800, 800),
        box_space="image_pixels",
    )
    assert converted[0]["box_model_space"] == box
    assert converted[0]["box"] == box


def test_normalized_1000_conversion_uses_source_dimensions():
    converted = qwen_adapter.convert_claim_boxes(
        [{"box": [100, 200, 300, 400]}],
        source_size=(1920, 1080),
        sent_size=(1280, 720),
        box_space="normalized_1000",
    )[0]

    assert converted["box_model_space"] == [100, 200, 300, 400]
    assert converted["box"] == [192.0, 216.0, 576.0, 432.0]
    assert converted["box_space"] == "normalized_1000"


def test_worked_normalized_example_is_grounded_against_truth():
    converted = qwen_adapter.convert_claim_boxes(
        [_claim(t0=10.0, t1=10.0, box=[942, 481, 999, 663])],
        source_size=(1920, 1080),
        sent_size=(1280, 720),
        box_space="normalized_1000",
    )[0]
    truth = {
        "clip_id": "worked-example",
        "window": {"start_s": 10.0, "end_s": 10.0},
        "box_track": [[10.0, 1828, 519, 1919, 735]],
        "human_note": None,
    }

    scored = score_claim(converted, truth)

    assert converted["box"] == pytest.approx([1808.64, 519.48, 1918.08, 716.04])
    assert scored["box_grounded"] is True
    assert scored["supported"] is True


def test_out_of_frame_box_is_malformed_and_counted():
    claim = qwen_adapter.convert_claim_boxes(
        [_claim(t0=10.0, t1=10.0, box=[1100, 100, 1200, 200])],
        source_size=(1920, 1080),
        sent_size=(1280, 720),
        box_space="normalized_1000",
    )[0]
    reason = "box outside frame after conversion (space=normalized_1000)"

    assert claim["malformed"] is True
    assert claim["box_sanity_reason"] == reason
    assert reason in claim["malformed_fields"]
    report = score_run(
        [{"clip_id": "clip-1", "claims": [claim], "error": None}],
        {"clip-1": _truth()},
    )
    assert report["overall"]["box_sanity_guard_count"] == 1
    assert report["clips"][0]["metrics"]["box_sanity_guard_count"] == 1


@pytest.mark.parametrize(
    ("model_box", "box_space", "expected_reason"),
    [
        (
            [0, 0, 1001, 1001],
            "normalized_1000",
            "box area exceeds source frame after conversion (space=normalized_1000)",
        ),
        (
            [100, 100, 200, 200],
            "image_pixels",
            "image-pixel box uses only coordinates <=1000 while sent image is "
            "larger (space=image_pixels)",
        ),
    ],
)
def test_other_box_sanity_guards_mark_claim_malformed(
    model_box, box_space, expected_reason
):
    converted = qwen_adapter.convert_claim_boxes(
        [{"box": model_box, "malformed": False, "malformed_fields": []}],
        source_size=(1920, 1080),
        sent_size=(1280, 720),
        box_space=box_space,
    )[0]

    assert converted["malformed"] is True
    assert converted["box_sanity_reason"] == expected_reason


def test_extracted_frames_record_exact_sent_dimensions(monkeypatch, tmp_path):
    image_module = pytest.importorskip("PIL.Image")

    monkeypatch.setattr(
        adapter_common.shutil,
        "which",
        lambda command: f"/usr/bin/{command}",
    )

    def fake_extract(_clip, output, *_args):
        image_module.new("RGB", (1280, 720)).save(output)

    monkeypatch.setattr(
        adapter_common.qwen_match_analysis, "extract_frame", fake_extract
    )
    truth = {
        "window": {"start_s": 10.0, "end_s": 11.0},
        "box_track": [[10.0, 0, 0, 1, 1], [11.0, 0, 0, 1, 1]],
    }

    frames = adapter_common.extract_sample_frames(
        tmp_path / "clip.mp4", truth, tmp_path / "frames"
    )

    assert frames == [
        {
            "path": str(tmp_path / "frames" / "frame-00.jpg"),
            "t": 10.05,
            "sent_w": 1280,
            "sent_h": 720,
        }
    ]


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

    monkeypatch.delenv("BENCH_NUM_CTX", raising=False)
    monkeypatch.delenv("QWEN_NUM_CTX", raising=False)
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
    assert captured["body"]["think"] is False
    assert captured["body"]["format"] == "json"
    assert captured["body"]["options"] == {
        "temperature": 0,
        "num_predict": 400,
        "repeat_penalty": 1.15,
        "num_ctx": 65536,
    }


def test_bench_claim_schema_matches_contract_and_serializes():
    schema = qwen_adapter.bench_claim_schema()
    claim_schema = schema["properties"]["claims"]["items"]

    assert schema["additionalProperties"] is False
    assert "maxItems" not in schema["properties"]["claims"]
    assert claim_schema["additionalProperties"] is False
    assert claim_schema["properties"]["confidence"]["enum"] == sorted(CONFIDENCE_VALUES)
    assert claim_schema["properties"]["visibility"]["enum"] == sorted(VISIBILITY_VALUES)
    box_array = claim_schema["properties"]["box"]["anyOf"][0]
    assert box_array["minItems"] == box_array["maxItems"] == 4
    json.dumps(schema)


def test_bench_claim_schema_inlines_refs_and_requires_every_object_property():
    schema = qwen_adapter.bench_claim_schema()
    serialized = json.dumps(schema)

    assert "$ref" not in serialized
    assert "$defs" not in serialized

    def walk(value):
        yield value
        if isinstance(value, dict):
            for item in value.values():
                yield from walk(item)
        elif isinstance(value, list):
            for item in value:
                yield from walk(item)

    for value in walk(schema):
        if isinstance(value, dict) and value.get("type") == "object":
            assert value["required"] == list(value["properties"])


def test_shared_ollama_call_sends_schema_object_when_requested(monkeypatch, tmp_path):
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
        return Response()

    monkeypatch.setattr(
        adapter_common.qwen_match_analysis.urllib.request, "urlopen", fake_urlopen
    )
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"frame")
    schema = qwen_adapter.bench_claim_schema()

    adapter_common.ollama_chat_with_options(
        "prompt",
        ollama_url="http://ollama.test",
        model="qwen3-vl:8b",
        timeout_s=12,
        image_paths=[image],
        options={"num_predict": 400, "repeat_penalty": 1.15},
        response_schema=schema,
    )

    assert captured["body"]["format"] == schema


def test_shared_ollama_call_omits_num_ctx_when_disabled(monkeypatch, tmp_path):
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"message":{"content":"{}"}}'

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data)
        return Response()

    monkeypatch.setenv("BENCH_NUM_CTX", "0")
    monkeypatch.setenv("QWEN_NUM_CTX", "32768")
    monkeypatch.setattr(
        adapter_common.qwen_match_analysis.urllib.request, "urlopen", fake_urlopen
    )
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"frame")

    adapter_common.ollama_chat_with_options(
        "prompt",
        ollama_url="http://ollama.test",
        model="qwen3-vl:8b",
        timeout_s=12,
        image_paths=[image],
        options={"num_predict": 400},
    )

    assert "num_ctx" not in captured["body"]["options"]


def test_qwen_adapter_parses_claims_from_thinking_and_records_origin(
    monkeypatch, tmp_path
):
    claim = _claim(t0=10.0, t1=10.0, box=[100, 100, 200, 200])

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "message": {
                        "content": "",
                        "thinking": json.dumps({"claims": [claim]}),
                    }
                }
            ).encode()

    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"frame")
    monkeypatch.setattr(
        qwen_adapter,
        "extract_sample_frames",
        lambda *_args, **_kwargs: [
            {"path": str(frame), "t": 10.0, "sent_w": 1280, "sent_h": 720}
        ],
    )
    monkeypatch.setattr(
        qwen_adapter,
        "apply_anchors",
        lambda *_args: [{"t": 10.0, "box": [100, 100, 200, 200]}],
    )
    monkeypatch.setattr(
        adapter_common.qwen_match_analysis.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: Response(),
    )

    result = qwen_adapter.run(
        tmp_path / "clip.mp4",
        {
            **_truth(),
            "jersey_number": 12,
            "frame_size": [1920, 1080],
        },
        {"model": "qwen3-vl:8b"},
    )

    assert result["error"] is None
    assert result["from_thinking"] is True
    assert len(result["claims"]) == 1
    assert result["claims"][0]["claim"] == claim["claim"]
    assert result["claims"][0]["malformed"] is False
    assert result["claims"][0]["box_model_space"] == [100.0, 100.0, 200.0, 200.0]
    assert result["claims"][0]["box_space"] == "normalized_1000"
    assert result["claims"][0]["box"] == [192.0, 108.0, 384.0, 216.0]
    assert result["sent_frames"] == [
        {"path": str(frame), "t": 10.0, "sent_w": 1280, "sent_h": 720}
    ]


def test_claims_file_carries_model_and_source_space_boxes(monkeypatch, tmp_path):
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"frame")
    truth = {
        "clip_id": "clip-1",
        "jersey_number": 12,
        "frame_size": [1920, 1080],
        "window": {"start_s": 10.0, "end_s": 20.0},
        "box_track": [
            [10.0, 150, 150, 300, 300],
            [20.0, 150, 150, 300, 300],
        ],
        "human_note": None,
    }
    manifest = {
        "frozen_set_id": "frozen-1",
        "clips": [{"clip_id": "clip-1", "clip": "clip.mp4", "truth": "truth.json"}],
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    (tmp_path / "truth.json").write_text(json.dumps(truth))
    monkeypatch.setattr(
        qwen_adapter,
        "extract_sample_frames",
        lambda *_args, **_kwargs: [
            {"path": str(frame), "t": 10.0, "sent_w": 1280, "sent_h": 720}
        ],
    )
    monkeypatch.setattr(qwen_adapter, "apply_anchors", lambda *_args: [])
    monkeypatch.setattr(
        qwen_adapter,
        "ollama_chat_with_options",
        lambda *_args, **_kwargs: json.dumps(
            {"claims": [_claim(t0=10.0, t1=10.0, box=[100, 100, 200, 200])]}
        ),
    )
    args = SimpleNamespace(
        adapter="qwen3vl_ollama",
        clips="all",
        ollama_url="http://ollama.test",
        model="qwen3-vl:8b",
        anchor_mode="first",
        manifest=manifest_path,
        report_root=tmp_path / "report",
        run_id="coordinate-test",
        timeout=12.0,
        num_predict=400,
        repeat_penalty=1.15,
        force=False,
    )

    report, output_dir = run_benchmark(args)
    persisted = json.loads((output_dir / "claims" / "clip-1.json").read_text())[
        "claims"
    ][0]

    assert persisted["box_model_space"] == [100.0, 100.0, 200.0, 200.0]
    assert persisted["box_space"] == "normalized_1000"
    assert persisted["box"] == [192.0, 108.0, 384.0, 216.0]
    assert report["clips"][0]["claims"][0]["box_model_space"] == [
        100.0,
        100.0,
        200.0,
        200.0,
    ]
    metadata = json.loads((output_dir / "run.json").read_text())
    assert metadata["box_space"] == "normalized_1000"


@pytest.mark.parametrize(
    "raw",
    [
        '{"claims":[]}',
        '{"claims":[{"claim":"missing contract fields"}]}',
    ],
)
def test_qwen_adapter_flags_responses_with_no_parseable_claims(
    monkeypatch, tmp_path, raw
):
    frame = tmp_path / "frame.jpg"
    monkeypatch.setattr(
        qwen_adapter,
        "extract_sample_frames",
        lambda *_args, **_kwargs: [
            {"path": str(frame), "t": 10.0, "sent_w": 1280, "sent_h": 720}
        ],
    )
    monkeypatch.setattr(qwen_adapter, "apply_anchors", lambda *_args: [])
    monkeypatch.setattr(
        qwen_adapter,
        "ollama_chat_with_options",
        lambda *_args, **_kwargs: raw,
    )

    result = qwen_adapter.run(
        tmp_path / "clip.mp4",
        {
            **_truth(),
            "jersey_number": 12,
            "frame_size": [1920, 1080],
        },
        {"model": "qwen3-vl:8b"},
    )

    assert result["error"] == "no parseable claims"
    assert result["from_thinking"] is False


@pytest.mark.parametrize(
    ("format_mode", "expected_schema"),
    (("json", None), ("schema", "schema")),
)
def test_qwen_adapter_routes_format_mode(
    monkeypatch, tmp_path, format_mode, expected_schema
):
    frame = tmp_path / "frame.jpg"
    captured = {}
    monkeypatch.setattr(
        qwen_adapter,
        "extract_sample_frames",
        lambda *_args, **_kwargs: [
            {"path": str(frame), "t": 10.0, "sent_w": 1280, "sent_h": 720}
        ],
    )
    monkeypatch.setattr(qwen_adapter, "apply_anchors", lambda *_args: [])

    def fake_chat(*_args, **kwargs):
        captured.update(kwargs)
        return json.dumps({"claims": [_claim(box_t=15.0)]})

    monkeypatch.setattr(qwen_adapter, "ollama_chat_with_options", fake_chat)

    result = qwen_adapter.run(
        tmp_path / "clip.mp4",
        {**_truth(), "jersey_number": 12, "frame_size": [1920, 1080]},
        {"model": "qwen3-vl:8b", "format_mode": format_mode},
    )

    expected = (
        qwen_adapter.bench_claim_schema() if expected_schema == "schema" else None
    )
    assert captured["response_schema"] == expected
    assert result["format_mode"] == format_mode


def test_anchor_first_draws_only_on_frame_zero(monkeypatch, tmp_path):
    frames = [
        {
            "path": str(tmp_path / "frame-0.jpg"),
            "t": 10.0,
            "sent_w": 1280,
            "sent_h": 720,
        },
        {
            "path": str(tmp_path / "frame-1.jpg"),
            "t": 15.0,
            "sent_w": 1280,
            "sent_h": 720,
        },
        {
            "path": str(tmp_path / "frame-2.jpg"),
            "t": 20.0,
            "sent_w": 1280,
            "sent_h": 720,
        },
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
        lambda frame, box, jersey: drawn.append((frame, box, jersey)),
    )

    anchors = qwen_adapter.apply_anchors(frames, truth, "first")

    assert [call[0] for call in drawn] == [Path(frames[0]["path"])]
    assert anchors == [
        {
            "t": 10.0,
            "box": pytest.approx([66.667, 66.667, 133.333, 133.333], abs=0.001),
            "box_source_space": [100.0, 100.0, 200.0, 200.0],
            "sent_w": 1280,
            "sent_h": 720,
        }
    ]
    prompt = qwen_adapter.build_prompt(
        {**truth, "window": {"start_s": 10, "end_s": 20}},
        [10.0, 15.0, 20.0],
        (1280, 720),
        "first",
        "normalized_1000",
    )
    assert (
        "the first image identifies the player with a red rectangle; the other images are "
        "unlabelled — find that same player yourself and box the evidence region in those frames"
        in prompt
    )
    all_prompt = qwen_adapter.build_prompt(
        {**truth, "window": {"start_s": 10, "end_s": 20}},
        [10.0, 15.0, 20.0],
        (1280, 720),
        "all",
        "image_pixels",
    )
    assert (
        "Every frame contains a thin red\nrectangle labelled #12. Describe ONLY the boxed player."
        in all_prompt
    )
    assert "images provided are exactly\n1280x720 pixels" in prompt
    assert "integers from 0 to 1000 relative to the image" in prompt
    assert "coordinates of the IMAGE PROVIDED (1280x720)" in all_prompt
    box_t_instruction = (
        "box_t must be the timestamp of the frame your box came from; t0..t1 may "
        "cover the whole action"
    )
    assert box_t_instruction in prompt
    assert box_t_instruction in all_prompt
    assert "SOURCE pixel coordinates" not in prompt
    drawn.clear()
    all_anchors = qwen_adapter.apply_anchors(frames, truth, "all")
    assert [call[0] for call in drawn] == [Path(frame["path"]) for frame in frames]
    assert [anchor["t"] for anchor in all_anchors] == [10.0, 15.0, 20.0]


def test_anchor_is_drawn_at_scaled_location_on_resized_frame(tmp_path):
    image_module = pytest.importorskip("PIL.Image")
    frame_path = tmp_path / "frame.png"
    image_module.new("RGB", (1280, 720), (0, 0, 0)).save(frame_path)
    frames = [
        {
            "path": str(frame_path),
            "t": 10.0,
            "sent_w": 1280,
            "sent_h": 720,
        }
    ]
    truth = {
        "jersey_number": 12,
        "frame_size": [1920, 1080],
        "box_track": [[10.0, 960, 270, 1440, 810]],
    }

    anchors = qwen_adapter.apply_anchors(frames, truth, "first")

    assert anchors[0]["box"] == [640.0, 180.0, 960.0, 540.0]
    with image_module.open(frame_path) as image:
        assert image.getpixel((640, 400)) == (255, 40, 40)
        assert image.getpixel((639, 400)) == (0, 0, 0)
        assert image.getpixel((960, 400)) == (255, 40, 40)


def test_boxed_frame_tagging_uses_box_t_and_half_second_tolerance():
    claims = [
        _claim(box_t=9.5),
        _claim(box_t=10.5),
        _claim(box_t=10.501),
        _claim(box_t=None),
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
        "box_space": "normalized_1000",
        "format_mode": "json",
        "num_predict": 400,
        "repeat_penalty": 1.15,
        "frozen_set_id": "frozen-1",
    }
    first = _run_metadata(first_settings, ["clip-1"])
    changed = _run_metadata({**first_settings, "format_mode": "schema"}, ["clip-1"])
    run_dir = tmp_path / "run-1"
    _write_run_metadata(run_dir, first)

    assert _find_resume_dir(tmp_path, changed) is None
    with pytest.raises(ValueError, match="fingerprint mismatch.*--force.*--run-id"):
        _write_run_metadata(run_dir, changed)


def test_run_metadata_records_model_resolved_from_environment(monkeypatch):
    monkeypatch.setenv("BENCH_MODEL", "qwen3-vl:env-fallback")
    monkeypatch.delenv("BENCH_BOX_SPACE", raising=False)
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
    assert metadata["box_space"] == "normalized_1000"
    assert metadata["format_mode"] == "json"
    assert metadata["num_predict"] == 350
    assert metadata["repeat_penalty"] == 1.2
    assert metadata["adapter"] == "qwen3vl_ollama"
    assert metadata["frozen_set_id"] == "frozen-1"


def test_box_space_resolves_from_environment_and_cli_wins(monkeypatch):
    monkeypatch.setenv("BENCH_BOX_SPACE", "image_pixels")
    args = SimpleNamespace(
        adapter="qwen3vl_ollama",
        model="qwen3-vl:8b",
        ollama_url="http://ollama.test",
        timeout=123.0,
        anchor_mode="first",
        box_space=None,
        num_predict=350,
        repeat_penalty=1.2,
    )

    assert (
        _resolve_inference_settings(args, {"frozen_set_id": "frozen-1"})["box_space"]
        == "image_pixels"
    )
    args.box_space = "normalized_1000"
    assert (
        _resolve_inference_settings(args, {"frozen_set_id": "frozen-1"})["box_space"]
        == "normalized_1000"
    )


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
    scored = score_claim(
        _claim(t0=9.5, t1=10.5, box_t=10.0, box=[95, 95, 205, 205]),
        _truth(),
    )

    assert scored["time_grounded"] is True
    assert scored["box_grounded"] is True
    assert scored["supported"] is True


def test_long_claim_is_supported_at_box_t_but_not_at_midpoint():
    truth = {
        "clip_id": "moving-player",
        "window": {"start_s": 10.0, "end_s": 35.0},
        "box_track": [
            [10.0, 100, 100, 200, 200],
            [35.0, 600, 100, 700, 200],
        ],
        "human_note": None,
    }
    scored = score_claim(
        _claim(
            t0=10.0,
            t1=35.0,
            box_t=10.0,
            box=[100, 100, 200, 200],
        ),
        truth,
    )

    assert scored["time_grounded"] is True
    assert scored["box_grounded"] is True
    assert scored["box_grounded_at_midpoint"] is False
    assert scored["supported"] is True
    assert scored["truth_box_at_box_t"] == [100.0, 100.0, 200.0, 200.0]
    assert scored["truth_box_at_midpoint"] == [350.0, 100.0, 450.0, 200.0]

    report = score_run(
        [{"clip_id": "moving-player", "claims": [scored], "error": None}],
        {"moving-player": truth},
    )
    assert report["overall"]["box_grounded_rate"] == 1.0
    assert report["overall"]["box_grounded_at_midpoint_rate"] == 0.0


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
    assert metrics["box_grounded_rate"] == pytest.approx(2 / 3, abs=0.0001)
    assert metrics["box_grounded_at_midpoint_rate"] == pytest.approx(2 / 3, abs=0.0001)
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


def test_echo_suspect_compares_model_box_with_sent_space_anchor():
    truth = {
        "clip_id": "clip-1",
        "window": {"start_s": 10.0, "end_s": 20.0},
        "box_track": [
            [10.0, 150, 150, 300, 300],
            [20.0, 150, 150, 300, 300],
        ],
        "human_note": None,
    }
    claim = _claim(
        t0=10.0,
        t1=10.0,
        box=[150, 150, 300, 300],
        box_model_space=[100, 100, 200, 200],
        boxed_frame=True,
    )

    scored = score_claim(
        claim,
        truth,
        [{"t": 10.0, "box": [100, 100, 200, 200]}],
    )

    assert scored["box_grounded"] is True
    assert scored["echo_suspect"] is True
    assert scored["drawn_anchor_box"] == [100.0, 100.0, 200.0, 200.0]


def test_echo_suspect_converts_normalized_box_to_sent_image_pixels():
    claim = _claim(
        t0=10.0,
        t1=10.0,
        box=[150, 150, 300, 300],
        box_model_space=[100, 100, 200, 200],
        box_space="normalized_1000",
        boxed_frame=True,
    )
    anchor = {
        "t": 10.0,
        "box": [128, 72, 256, 144],
        "sent_w": 1280,
        "sent_h": 720,
    }

    scored = score_claim(claim, _truth(), [anchor])

    assert scored["echo_suspect"] is True
    assert scored["drawn_anchor_box"] == [128.0, 72.0, 256.0, 144.0]


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


def _fake_mlx(monkeypatch, tmp_path, *, error=None, raw=None):
    truth = {**_truth(), "frame_size": [1920, 1080], "jersey_number": 12}
    anchor = {
        "path": str(tmp_path / "anchor.jpg"),
        "t": 10.05,
        "sent_w": 1280,
        "sent_h": 720,
    }
    monkeypatch.setattr(
        mlx_adapter,
        "prepare_anchor",
        lambda *_: (anchor, [{**anchor, "box": [100, 100, 200, 200]}]),
    )
    captured = {}

    def fake_worker(argv, **kwargs):
        captured.update(
            argv=argv, request=json.loads(kwargs["input"]), env=kwargs["env"]
        )
        payload = {
            "text": raw or json.dumps({"claims": [_claim(box_t=15.0)]}),
            "model": mlx_adapter.DEFAULT_MODEL,
            "prompt_tokens": 500,
            "generation_tokens": 80,
            "wall_s": 1.0,
            "sampled_frame_times": [0.0, 0.5, 1.0],
            "sent_w": 960,
            "sent_h": 544,
            "anchor_sent_w": 1280,
            "anchor_sent_h": 736,
        }
        if error:
            payload = {"error": error}
        return SimpleNamespace(returncode=1 if error else 0, stdout=json.dumps(payload))

    monkeypatch.setattr(mlx_adapter.subprocess, "run", fake_worker)
    result = mlx_adapter.run(
        tmp_path / "clip.mp4",
        truth,
        {
            "fps": 4.0,
            "mlx_python": "/worker/python",
            "num_predict": 350,
            "repeat_penalty": 1.2,
        },
    )
    return result, captured, truth


def test_mlx_fake_worker_success_and_absolute_frame_provenance(monkeypatch, tmp_path):
    result, captured, _ = _fake_mlx(monkeypatch, tmp_path)
    assert result["error"] is None
    assert result["claims"][0]["box"] == pytest.approx([278.4, 156.6, 489.6, 275.4])
    assert (
        result["claims"][0]["box_t"] == 15.0
    )  # Already absolute: never shift claims heuristically.
    assert result["claims"][0]["boxed_frame"] is False
    assert [frame["t"] for frame in result["sent_frames"]] == [10.0, 10.5, 11.0]
    assert all(
        (frame["sent_w"], frame["sent_h"]) == (960, 544)
        for frame in result["sent_frames"]
    )
    assert result["tokens"] == 80
    assert result["prompt_tokens"] == 500
    assert captured["argv"][0] == "/worker/python"
    assert captured["request"]["fps"] == 4.0
    assert captured["request"]["max_tokens"] == 350
    assert captured["request"]["repetition_penalty"] == 1.2
    assert "__VIDEO_TIMESTAMPS__" in captured["request"]["prompt"]


def test_mlx_worker_error_is_failed(monkeypatch, tmp_path):
    result, _, truth = _fake_mlx(monkeypatch, tmp_path, error="native video failure")
    assert "native video failure" in result["error"]
    assert score_clip(result, truth)["status"] == "failed"


@pytest.mark.parametrize(
    "raw", ['{"claims":[]}', "not json", '{"claims":[{"claim":"incomplete"}]}']
)
def test_mlx_never_relaxes_claim_contract(monkeypatch, tmp_path, raw):
    result, _, truth = _fake_mlx(monkeypatch, tmp_path, raw=raw)
    assert result["error"] == "no parseable claims"
    assert score_clip(result, truth)["status"] == "failed"


def test_mlx_settings_fingerprint_fps_model_and_worker(monkeypatch, tmp_path):
    from run_bench import _parser

    monkeypatch.setenv("BENCH_MLX_FPS", "2")
    monkeypatch.setenv("BENCH_MLX_MODEL", "model-one")
    monkeypatch.setenv("BENCH_MLX_PYTHON", "/venv-one/bin/python")
    args = _parser().parse_args(["--adapter", "qwen3vl_mlx"])
    manifest = {"frozen_set_id": "frozen-1"}
    first = _run_metadata(_resolve_inference_settings(args, manifest), ["clip-1"])
    _write_run_metadata(tmp_path, first)
    assert first["fps"] == 2.0
    assert first["model"] == "model-one"
    assert first["mlx_python"] == "/venv-one/bin/python"
    for env, value in [
        ("BENCH_MLX_FPS", "4"),
        ("BENCH_MLX_MODEL", "model-two"),
        ("BENCH_MLX_PYTHON", "/venv-two/bin/python"),
        ("BENCH_MLX_PYTHONPATH", "/different/worker/dependencies"),
    ]:
        with monkeypatch.context() as context:
            context.setenv(env, value)
            changed = _run_metadata(
                _resolve_inference_settings(args, manifest), ["clip-1"]
            )
            with pytest.raises(ValueError, match="fingerprint mismatch"):
                _write_run_metadata(tmp_path, changed)
    args.fps = 4.0
    assert _resolve_inference_settings(args, manifest)["fps"] == 4.0


@pytest.mark.parametrize("fps", [0.0, -1.0, float("nan"), float("inf")])
def test_mlx_rejects_invalid_fps(fps):
    from run_bench import _parser

    args = _parser().parse_args(["--adapter", "qwen3vl_mlx"])
    args.fps = fps
    with pytest.raises(ValueError, match="fps must be a positive finite"):
        _resolve_inference_settings(args, {"frozen_set_id": "frozen-1"})


def test_native_loader_records_actual_reads_without_another_sampler(monkeypatch):
    from adapters.mlx_worker import load_native_video

    class Capture:
        index = 0

        def __init__(self, path):
            assert path == "native.mp4"

        def get(self, prop):
            return {1: 25.0, 2: 100, 3: self.index}[prop]

        def read(self):
            return True, "frame"

        def set(self, _prop, value):
            self.index = value

    cv2 = SimpleNamespace(
        VideoCapture=Capture,
        CAP_PROP_FPS=1,
        CAP_PROP_FRAME_COUNT=2,
        CAP_PROP_POS_FRAMES=3,
    )

    def library_load(path, *, fps, max_frames):
        assert fps == 2.0 and max_frames == 768
        cap = cv2.VideoCapture(path)
        # The library owns selection; the worker must observe these indices.
        for index in [0, 33, 66, 99]:
            cap.set(3, index)
            cap.read()
        return ["frame"] * 4, 1.0

    monkeypatch.setitem(sys.modules, "cv2", cv2)
    monkeypatch.setitem(sys.modules, "mlx_vlm", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules, "mlx_vlm.utils", SimpleNamespace(load_video=library_load)
    )
    video, fps, metadata = load_native_video("native.mp4", 2.0)
    assert len(video) == 4 and fps == 1.0
    assert metadata == {
        "fps": 25.0,
        "total_num_frames": 100,
        "frames_indices": [0, 33, 66, 99],
    }
    assert cv2.VideoCapture is Capture


def test_mlx_timeout_is_failed_without_fallback(monkeypatch, tmp_path):
    result, _, truth = _fake_mlx(monkeypatch, tmp_path)
    assert result["error"] is None

    def timeout(argv, **kwargs):
        raise mlx_adapter.subprocess.TimeoutExpired(argv, kwargs["timeout"])

    monkeypatch.setattr(mlx_adapter.subprocess, "run", timeout)
    result = mlx_adapter.run(tmp_path / "clip.mp4", truth, {"timeout_s": 1})
    assert "TimeoutExpired" in result["error"]
    assert score_clip(result, truth)["status"] == "failed"
    assert result["claims"] == []


def test_mlx_worker_sends_native_video_tensors_and_reports_processor_sizes(
    monkeypatch, tmp_path
):
    import numpy as np
    from PIL import Image
    from adapters import mlx_worker

    anchor = tmp_path / "anchor.jpg"
    Image.new("RGB", (1280, 720)).save(anchor)
    video = np.zeros((4, 3, 1080, 1920), dtype=np.uint8)
    monkeypatch.setattr(
        mlx_worker,
        "load_native_video",
        lambda *_: (video, 2.0, {"fps": 25.0, "frames_indices": [0, 12, 25, 37]}),
    )
    captured = {}

    class Processor:
        video_processor = SimpleNamespace(patch_size=16, temporal_patch_size=2)
        image_processor = SimpleNamespace(patch_size=16)

        def apply_chat_template(self, messages, **_kwargs):
            captured["content"] = messages[0]["content"]
            return "formatted-native-video-prompt"

        def __call__(self, **kwargs):
            assert kwargs["videos"][0] is video
            assert len(kwargs["images"]) == 1
            return {
                "input_ids": np.array([[1, 2]]),
                "attention_mask": np.array([[1, 1]]),
                "video_grid_thw": np.array([[2, 18, 32]]),
                "image_grid_thw": np.array([[1, 46, 80]]),
                "pixel_values_videos": np.array([[7]]),
                "pixel_values": np.array([[8]]),
            }

    def generate(_model, _processor, _prompt, **kwargs):
        captured["generate"] = kwargs
        return SimpleNamespace(
            text='{"claims":[]}', prompt_tokens=120, generation_tokens=8
        )

    core = SimpleNamespace(array=lambda value: value)
    monkeypatch.setitem(sys.modules, "mlx", SimpleNamespace(core=core))
    monkeypatch.setitem(sys.modules, "mlx.core", core)
    monkeypatch.setitem(
        sys.modules,
        "mlx_vlm",
        SimpleNamespace(load=lambda _: ("model", Processor()), generate=generate),
    )
    result = mlx_worker.run(
        {
            "clip": "clip.mp4",
            "fps": 2.0,
            "model": "native",
            "start_s": 100.0,
            "prompt": "Times: __VIDEO_TIMESTAMPS__",
            "anchor_image": str(anchor),
            "max_tokens": 400,
            "temperature": 0.0,
            "repetition_penalty": 1.15,
            "repetition_context_size": 64,
        }
    )
    assert [item["type"] for item in captured["content"]] == ["image", "video", "text"]
    assert (
        captured["content"][-1]["text"] == "Times: 100.000, 100.480, 101.000, 101.480"
    )
    assert "pixel_values_videos" in captured["generate"]
    assert captured["generate"]["max_tokens"] == 400
    assert (result["sent_w"], result["sent_h"]) == (512, 288)
    assert (result["anchor_sent_w"], result["anchor_sent_h"]) == (1280, 736)
    assert result["sampled_frame_times"] == [0.0, 0.48, 1.0, 1.48]


@pytest.mark.parametrize("error", [None, "worker could not decode native video"])
def test_mlx_runner_persists_worker_result_and_failure_status(
    monkeypatch, tmp_path, error
):
    from run_bench import _parser

    _, _, truth = _fake_mlx(monkeypatch, tmp_path, error=error)
    manifest = {
        "frozen_set_id": "frozen-test",
        "clips": [{"clip_id": "clip-1", "clip": "clip.mp4", "truth": "truth.json"}],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "truth.json").write_text(json.dumps(truth))
    args = _parser().parse_args(
        [
            "--adapter",
            "qwen3vl_mlx",
            "--fps",
            "4",
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--report-root",
            str(tmp_path / "reports"),
            "--run-id",
            "worker-test",
        ]
    )
    report, output = run_benchmark(args)
    persisted = json.loads((output / "claims" / "clip-1.json").read_text())
    assert report["clips"][0]["status"] == ("failed" if error else "scored")
    assert json.loads((output / "run.json").read_text())["fps"] == 4.0
    if not error:
        assert [frame["t"] for frame in persisted["sent_frames"]] == [10.0, 10.5, 11.0]
        assert persisted["sent_frames"][0]["sent_w"] == 960
        assert persisted["claims"][0]["box_t"] == 15.0


@pytest.mark.parametrize(("wall", "attempts"), [(121.0, 5), (119.0, 6)])
def test_slow_lane_cap_writes_partial_report_after_five_attempts(
    monkeypatch, tmp_path, wall, attempts
):
    from run_bench import _parser

    ids = [f"clip-{i}" for i in range(6)]
    manifest = {
        "frozen_set_id": "frozen-test",
        "clips": [
            {"clip_id": cid, "clip": "clip.mp4", "truth": "truth.json"} for cid in ids
        ],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "truth.json").write_text(json.dumps(_truth()))
    monkeypatch.setattr(
        mlx_adapter,
        "run",
        lambda *_: {"claims": [_claim()], "error": None, "wall_s": wall},
    )
    args = _parser().parse_args(
        [
            "--adapter",
            "qwen3vl_mlx",
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--report-root",
            str(tmp_path / "reports"),
            "--wall-cap",
            "120",
        ]
    )
    report, output = run_benchmark(args)
    assert len(report["clips"]) == attempts
    assert len(list((output / "claims").glob("*.json"))) == attempts
    assert json.loads((output / "run.json").read_text())["wall_cap_s"] == 120.0
    if attempts == 5:
        assert report["stopped_early"]["unrun_clips"] == ["clip-5"]
        assert (
            json.loads((output / "report.json").read_text())["stopped_early"]
            == report["stopped_early"]
        )
    else:
        assert "stopped_early" not in report


def test_legacy_v5_default_fingerprint_golden(monkeypatch):
    from run_bench import _parser

    # Captured from unedited 5d646c8c before adding sampling options, all 20 IDs.
    clips = """m04-n02-t3005-474114-478131 m04-n03-t1406-157170-158922
    m04-n03-t1406-385962-387137 m04-n04-t3006-243433-247994
    m04-n04-t3006-307417-310307 m04-n05-t3007-284945-287898
    m04-n09-t1409-143096-143834 m04-n09-t1409-297601-298865
    m04-n09-t1409-385922-386603 m04-n10-t711-186553-188161
    m04-n12-t1411-237107-242145 m04-n12-t1411-679986-681985
    m04-n15-t3010-164698-170777 m04-n17-t717-253073-260377
    m04-n17-t717-304624-307834 m04-n17-t717-416826-418915
    m04-n21-t3011-390297-390800 m04-n22-t3012-070707-074371
    m04-n24-t3013-679939-681217 m04-n25-t3014-530600-532465""".split()
    args = _parser().parse_args(
        [
            "--adapter",
            "qwen3vl_ollama",
            "--anchor-mode",
            "first",
            "--box-space",
            "normalized_1000",
            "--model",
            "qwen3-vl:8b",
            "--num-predict",
            "400",
            "--repeat-penalty",
            "1.15",
            "--ollama-url",
            "http://127.0.0.1:11434",
        ]
    )
    manifest = {
        "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f"
    }
    default = _run_metadata(_resolve_inference_settings(args, manifest), clips)
    assert (
        default["fingerprint"]
        == "2426f5e86cfe705347cd1fc5ff0e59bdff9555e7d2f01aec814d395e86132df8"
    )
    assert "sample_interval" not in default and "sample_limit" not in default
    for interval, limit in [(30, 6), (5, 3), (30, 3)]:
        args.sample_interval, args.sample_limit = interval, limit
        changed = _run_metadata(_resolve_inference_settings(args, manifest), clips)
        assert changed["fingerprint"] != default["fingerprint"]
        assert changed["sample_interval"] == interval
        assert changed["sample_limit"] == limit


@pytest.mark.parametrize("duration", [0.5, 7.0, 73.0])
def test_production_sampling_real_anchor_and_tagging(monkeypatch, tmp_path, duration):
    from PIL import Image

    truth = {
        **_truth(),
        "frame_size": [1280, 720],
        "jersey_number": 12,
        "window": {"start_s": 10.0, "end_s": 10.0 + duration},
        "box_track": [
            [10.0, 100, 100, 200, 200],
            [10.0 + duration, 100, 100, 200, 200],
        ],
    }
    extracted = []

    def extract(_clip, output, local_s, *_args):
        extracted.append(local_s)
        Image.new("RGB", (1280, 720)).save(output)

    def chat(_prompt, *, image_paths, **_kwargs):
        assert len(image_paths) == (1 if duration < 30 else 3)
        # Actual shared grounding.draw_anchor_box modifies the first image.
        with Image.open(image_paths[0]) as image:
            assert image.getbbox() is not None
        return json.dumps(
            {
                "claims": [
                    _claim(t0=10.05, t1=10.05, box_t=10.05, box=[78, 139, 156, 278])
                ]
            }
        )

    monkeypatch.setattr(
        adapter_common.shutil, "which", lambda command: f"/usr/bin/{command}"
    )
    monkeypatch.setattr(adapter_common.qwen_match_analysis, "extract_frame", extract)
    monkeypatch.setattr(qwen_adapter, "ollama_chat_with_options", chat)
    result = qwen_adapter.run(
        tmp_path / "clip.mp4", truth, {"sample_interval": 30, "sample_limit": 3}
    )
    assert result["error"] is None
    assert extracted == ([0.05] if duration < 30 else [0.05, 30.05, 60.05])
    assert len(result["anchored_frames"]) == 1
    assert result["claims"][0]["boxed_frame"] is True
    assert qwen_adapter.sent_frame_size(result["sent_frames"]) == (1280, 720)
    assert score_clip(result, truth)["status"] == "scored"


@pytest.mark.parametrize(
    "option,value",
    [("--sample-interval", "0"), ("--sample-interval", "nan"), ("--sample-limit", "0")],
)
def test_invalid_still_sampling_rejected(option, value):
    from run_bench import _parser

    args = _parser().parse_args(["--adapter", "qwen3vl_ollama", option, value])
    with pytest.raises(ValueError, match="sample-"):
        _resolve_inference_settings(args, {"frozen_set_id": "test"})


def test_comparison_fixture_is_complete_and_deterministic(tmp_path):
    from compare_runs import main

    truth = {**_truth(), "jersey_number": 3, "kit_color": "red"}
    (tmp_path / "truth.json").write_text(json.dumps(truth))
    manifest = {
        "frozen_set_id": "fixture",
        "clips": [{"clip_id": "clip-1", "truth": "truth.json"}],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    metrics = []
    for index, name in enumerate(["frames", "video"]):
        path = tmp_path / name
        (path / "claims").mkdir(parents=True)
        claim = _claim(
            box_t=15.0,
            boxed_frame=True,
            box=[145, 145, 255, 255] if index == 0 else [0, 0, 1, 1],
            claim=(
                "Player wearing red jersey number 3 is visible."
                if index == 0
                else "Player wearing a blue jersey with the number 3 is visible."
            ),
        )
        raw = {
            "clip_id": "clip-1",
            "claims_raw": json.dumps({"claims": [claim]}),
            "claims": [claim],
            "wall_s": 1.0 + index,
            "error": None,
            "sent_frames": [
                {"t": 15.0, "sent_w": 1280 // (index + 1), "sent_h": 720 // (index + 1)}
            ],
        }
        (path / "claims/clip-1.json").write_text(json.dumps(raw))
        report = score_run([raw], {"clip-1": truth}, adapter=name)
        report["generated_at"] = "2026-09-09T00:00:00Z"
        metrics.append(report["overall"])
        (path / "report.json").write_text(json.dumps(report))
        (path / "run.json").write_text(
            json.dumps(
                {
                    "frozen_set_id": "fixture",
                    "clips": ["clip-1"],
                    "model": name,
                    "adapter": name,
                }
            )
        )
    args = [
        "--reports-root",
        str(tmp_path),
        "--runs",
        "frames=frames",
        "video=video",
        "--manifest",
        str(tmp_path / "manifest.json"),
        "--out-json",
        str(tmp_path / "out.json"),
        "--out-md",
        str(tmp_path / "out.md"),
    ]
    assert main(args) == 0
    output = (tmp_path / "out.json").read_bytes(), (tmp_path / "out.md").read_bytes()
    assert main(args) == 0
    assert output == (
        (tmp_path / "out.json").read_bytes(),
        (tmp_path / "out.md").read_bytes(),
    )
    result = json.loads(output[0])
    for index, name in enumerate(["frames", "video"]):
        assert result[name]["metrics"] == metrics[index]
        assert result[name]["sent_frames_per_clip"] == 1
        review = result["jersey_review"][name]["clip-1"]
        assert review["supplied_number_asserted_as_kit_detail"] is True
        assert review["invented_jersey_number_kill"] is False
        assert review["kit_colour_mismatch"] is bool(index)
    assert result["frames"]["sent_resolution_min"] == [1280, 720]
    assert result["video"]["sent_resolution_max"] == [640, 360]
    flip = result["per_clip_flips"]["video"][0]
    assert flip["winner"] == "frames"
    assert flip["kind"] == "supported_clip"
    assert flip["compared"]["claims"][0]["box_grounded"] is False
    assert "blue jersey" in flip["compared"]["raw_claim_texts"][0]


def test_jersey_review_includes_failed_claims_and_separates_labels_from_kit():
    from compare_runs import jersey_review

    raw = {
        "error": "no parseable claims",
        "claims_raw": json.dumps(
            {
                "claims": [
                    {
                        "claim": "Player marked #12 at frame 2371.120 wears a red jersey and black shorts."
                    },
                    {
                        "claim": "Player wearing jersey #9, identified by the number 9 on his back."
                    },
                ]
            }
        ),
    }
    review = jersey_review(raw, {"jersey_number": 12, "kit_color": "red"})
    first, second = review["claims"]
    assert first["jersey_mentions"] == [
        {
            "text": "#12",
            "number": 12,
            "matches_supplied": True,
            "asserted_as_kit_detail": False,
        }
    ]
    assert first["kit_colours_mentioned"] == ["red"]
    assert [m["number"] for m in second["jersey_mentions"]] == [9, 9]
    assert all(m["asserted_as_kit_detail"] for m in second["jersey_mentions"])
    assert review["unsupplied_numbers"] == [9]
    assert review["invented_jersey_number_kill"] is True


def test_mlx_does_not_inherit_pythonpath(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHONPATH", "/unrelated/project/dependencies")
    monkeypatch.delenv("BENCH_MLX_PYTHONPATH", raising=False)
    from run_bench import _parser

    args = _parser().parse_args(["--adapter", "qwen3vl_mlx"])
    assert (
        _resolve_inference_settings(args, {"frozen_set_id": "test"})["mlx_pythonpath"]
        == ""
    )
    result, captured, _truth_value = _fake_mlx(monkeypatch, tmp_path)
    assert result["error"] is None
    assert captured["env"]["PYTHONPATH"] == ""


def test_runner_fingerprints_and_passes_production_sampling(monkeypatch, tmp_path):
    from run_bench import _parser

    manifest = {
        "frozen_set_id": "fixture",
        "clips": [{"clip_id": "clip-1", "clip": "clip.mp4", "truth": "truth.json"}],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    (tmp_path / "truth.json").write_text(json.dumps(_truth()))
    captured = {}

    def adapter(_clip, _truth_value, cfg):
        captured.update(cfg)
        return {"claims": [_claim()], "error": None, "wall_s": 1.0}

    monkeypatch.setattr(qwen_adapter, "run", adapter)
    args = _parser().parse_args(
        [
            "--adapter",
            "qwen3vl_ollama",
            "--sample-interval",
            "30",
            "--sample-limit",
            "3",
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--report-root",
            str(tmp_path / "runs"),
        ]
    )
    report, output = run_benchmark(args)
    assert report["overall"]["scored_clips"] == 1
    assert captured["sample_interval"] == 30.0
    assert captured["sample_limit"] == 3
    metadata = json.loads((output / "run.json").read_text())
    assert metadata["sample_interval"] == 30.0
    assert metadata["sample_limit"] == 3


def _comparison_guard_fixture(tmp_path, *, completed=19, stop_marker=None):
    """Synthetic historical-shaped reports; no adapters or model calls."""
    names = ["frames", "frames_prod30", "video_fps2", "video_fps4"]
    ids = [f"clip-{i}" for i in range(20)]
    for name in names:
        path = tmp_path / name
        (path / "claims").mkdir(parents=True)
        raw = [
            {
                "clip_id": cid,
                "claims": [_claim(box_t=15.0, boxed_frame=True)],
                "wall_s": 1.0,
                "error": None,
            }
            for cid in ids
        ]
        count = completed if name == "video_fps4" else 20
        report = score_run(raw[:count], {cid: _truth() for cid in ids})
        report["generated_at"] = "2026-09-09T00:00:00Z"
        config = {
            "frozen_set_id": "1f68e2755002b3598c763532e95c212de9261ffa638c2943ad3769a1be77503f",
            "clips": ids,
            "model": "fixture",
            "adapter": name,
            "wall_cap_s": 120.0,
        }
        if name == "video_fps4" and stop_marker:
            source, key, value = stop_marker
            (report if source == "report" else config)[key] = value
        (path / "report.json").write_text(json.dumps(report))
        (path / "run.json").write_text(json.dumps(config))
        # Even leftover raw files must not mask a gap in scored report coverage.
        for row in raw:
            (path / "claims" / f"{row['clip_id']}.json").write_text(json.dumps(row))
    return names


@pytest.mark.parametrize("partial_first", [True, False])
def test_incomplete_comparison_with_partial_lane_in_either_order(
    tmp_path, partial_first
):
    from compare_runs import HEADLINE, VERDICT, compare, markdown

    names = _comparison_guard_fixture(tmp_path)
    if partial_first:
        names = [names[-1], *names[:-1]]
    result = compare(tmp_path, {name: name for name in names})
    assert result["headline"].startswith("INCOMPLETE COMPARISON")
    assert result["headline"] != HEADLINE
    assert result["verdict"] != VERDICT
    assert "withheld" in result["verdict"]
    assert result["incomplete_lanes"]["video_fps4"]["missing_clip_ids"] == ["clip-19"]
    rows = (
        next(iter(result["per_clip_flips"].values()))
        if partial_first
        else result["per_clip_flips"]["video_fps4"]
    )
    missing = next(row for row in rows if row["clip_id"] == "clip-19")
    side = "control" if partial_first else "compared"
    assert missing[side]["status"] == "not_attempted"
    assert missing["kind"] == "not_attempted"
    assert missing["winner"] is None
    text = markdown(result)
    assert text.startswith("INCOMPLETE COMPARISON")
    assert "missing clip IDs: clip-19" in text
    assert "not_attempted" in text
    assert HEADLINE not in text and VERDICT not in text


@pytest.mark.parametrize(
    "marker",
    [
        ("report", "stopped_early", {"reason": "wall cap", "unrun_clips": []}),
        ("run", "stopped_early", {}),
        ("report", "wall_cap_exceeded", True),
    ],
)
def test_stop_marker_blocks_verdict_even_with_full_coverage(tmp_path, marker):
    from compare_runs import compare, markdown

    names = _comparison_guard_fixture(tmp_path, completed=20, stop_marker=marker)
    result = compare(tmp_path, {name: name for name in names})
    assert result["headline"].startswith("INCOMPLETE COMPARISON")
    assert result["incomplete_lanes"]["video_fps4"]["missing_clip_ids"] == []
    assert result["incomplete_lanes"]["video_fps4"]["stop_markers"] == {
        f"{marker[0]}.{marker[1]}": marker[2]
    }
    assert "missing clip IDs: none" in markdown(result)


def test_configured_wall_cap_without_stop_is_complete(tmp_path):
    from compare_runs import HEADLINE, VERDICT, compare

    names = _comparison_guard_fixture(tmp_path, completed=20)
    result = compare(tmp_path, {name: name for name in names})
    assert "incomplete_lanes" not in result
    assert result["headline"] == HEADLINE and result["verdict"] == VERDICT


@pytest.mark.parametrize("value", [None, 42, {"nested": "claim"}])
def test_non_string_claims_are_reviewed_as_malformed(value):
    from compare_runs import claim_evidence, evidence_summary, jersey_review

    raw = {
        "claims_raw": json.dumps({"claims": [{"claim": value}]}),
        "error": "no parseable claims",
    }
    review = jersey_review(raw, {"jersey_number": 12, "kit_color": "red"})
    assert review["malformed_claim_text_count"] == 1
    claim = review["claims"][0]
    assert claim["claim"] == ""
    assert claim["malformed"] is True and claim["malformed_fields"] == ["claim"]
    assert claim["jersey_mentions"] == []
    assert review["invented_jersey_number_kill"] is False
    evidence = claim_evidence(
        {"status": "failed", "claims": [], "error": raw["error"]}, raw
    )
    assert "(no claims)" in evidence_summary(evidence)


@pytest.mark.parametrize(
    "text",
    [
        "Player #12 is visible in frame number 2.",
        "Player wearing a red jersey is seen at frame #2 and tracking number 8.",
        "At time number 2, track #8 identifies the player.",
    ],
)
def test_non_jersey_numbers_do_not_trigger_jersey_kill(text):
    from compare_runs import jersey_review

    review = jersey_review({"claims": [{"claim": text}]}, {"jersey_number": 12})
    assert review["invented_jersey_number_kill"] is False
    assert 2 in review["non_jersey_numbers"]
    assert (
        2 in review["unsupplied_numbers"]
    )  # Legacy candidate-number audit is retained.


@pytest.mark.parametrize(
    "text", ["Wearing jersey #9.", "Wearing shirt number 9.", "Player in kit 9."]
)
def test_unsupplied_kit_number_still_triggers_jersey_kill(text):
    from compare_runs import jersey_review

    review = jersey_review({"claims": [{"claim": text}]}, {"jersey_number": 12})
    assert review["invented_jersey_number_kill"] is True
    assert review["non_jersey_numbers"] == []
    assert review["claims"][0]["jersey_mentions"][0]["asserted_as_kit_detail"] is True


def test_review_kit_renders_every_frame_and_offline_note_template(tmp_path):
    import html
    import shutil
    import subprocess

    cv2 = pytest.importorskip("cv2")
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("review kit needs ffmpeg and ffprobe")
    from apply_notes import template
    from review_kit import build_kit, probe_video

    frozen = tmp_path / "frozen"
    (frozen / "clips").mkdir(parents=True)
    (frozen / "truth").mkdir()
    source = frozen / "clips/marked.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=64x64:r=10:d=2",
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            str(source),
        ],
        check=True,
    )
    truths, entries = [], []
    for cid in ("marked", "not-exported"):
        truth = {
            "clip_id": cid,
            "window": {"start_s": 100.0, "end_s": 102.0},
            "jersey_number": 12,
            "kit_color": "red",
            "frame_size": [64, 64],
            "box_track": [
                [100.2, 12, 20, 28, 42],
                [101.0, 20, 20, 36, 42],
                [101.7, 28, 20, 44, 42],
            ],
            "human_note": None,
        }
        truths.append(truth)
        (frozen / f"truth/{cid}.json").write_text(json.dumps(truth))
        entries.append(
            {"clip_id": cid, "clip": "clips/marked.mp4", "truth": f"truth/{cid}.json"}
        )
    (frozen / "manifest.json").write_text(
        json.dumps({"frozen_set_id": "review-fixture", "clips": entries})
    )
    out = tmp_path / "review"
    report = build_kit(frozen, out, clips="marked", scale=64)
    output = out / "clips/marked.mp4"
    assert output.is_file()
    assert (
        abs(
            int(probe_video(output)["nb_frames"])
            - int(probe_video(source)["nb_frames"])
        )
        <= 1
    )
    assert report["clips"][0]["frames"] == 20
    assert report["clips"][0]["no_track_frames"] >= 3
    capture = cv2.VideoCapture(str(output), cv2.CAP_FFMPEG)

    def red_pixels(image):
        b, g, r = cv2.split(image)
        return (
            (r > 130)
            & (r.astype("int16") > g.astype("int16") + 60)
            & (r.astype("int16") > b.astype("int16") + 60)
        )

    try:
        capture.set(cv2.CAP_PROP_POS_FRAMES, 10)
        ok, middle = capture.read()
        assert ok
        red = red_pixels(middle)
        assert red[18:45, 18:40].any()
        assert not red[48:64, 48:64].any()
        capture.set(cv2.CAP_PROP_POS_FRAMES, 19)
        ok, last = capture.read()
        assert ok
        assert not red_pixels(last).any()  # No stale box after the track ends.
        assert last[:27, :].max() > 100  # Visible grayscale "no track" marker.
    finally:
        capture.release()
    page = (out / "index.html").read_text()
    assert all(truth["clip_id"] in page for truth in truths)
    for line in template(truths).splitlines():
        if line.startswith("- `"):
            assert line in html.unescape(page)
    assert 'preload="metadata" playsinline src="clips/marked.mp4"' in page
    assert "localStorage.setItem" in page and "document.execCommand('copy')" in page
    assert "https://" not in page and "http://" not in page
    assert len((out / "README.txt").read_text().splitlines()) == 5
