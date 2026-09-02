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
from adapters.qwen3vl_mlx import STUB_ERROR, run as run_mlx  # noqa: E402
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
        lambda *_args: [{"path": str(frame), "t": 10.0, "sent_w": 1280, "sent_h": 720}],
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
        lambda *_args: [{"path": str(frame), "t": 10.0, "sent_w": 1280, "sent_h": 720}],
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
        lambda *_args: [{"path": str(frame), "t": 10.0, "sent_w": 1280, "sent_h": 720}],
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
        lambda *_args: [{"path": str(frame), "t": 10.0, "sent_w": 1280, "sent_h": 720}],
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


def test_mlx_adapter_fails_fast_with_actionable_message():
    result = run_mlx("clip.mp4", _truth(), {})

    assert result["wall_s"] == 0.0
    assert result["error"] == STUB_ERROR
    assert "native-video" in result["error"]
