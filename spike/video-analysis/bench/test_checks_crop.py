"""Lane C crop geometry, identity, unchanged questions and runner integration."""

import base64
import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
from adapters import qwen3vl_checks, qwen3vl_checks_crop as adapter  # noqa: E402
from adapters.common import crop_player_frame  # noqa: E402
from checks_contract import response_schema  # noqa: E402
from run_bench import (
    _parser,
    _resolve_inference_settings,
    _settings_fingerprint,
    run_benchmark,
)  # noqa: E402
from test_checks import read  # noqa: E402
from test_semantic import fake_transport, frozen, truth  # noqa: E402


@pytest.mark.parametrize(
    "size,box,rect",
    [
        ((800, 600), [390, 270, 410, 330], [208, 108, 592, 492]),
        ((800, 600), [0, 0, 20, 60], [0, 0, 384, 384]),
        ((800, 600), [780, 540, 800, 600], [416, 216, 800, 600]),
        ((320, 240), [140, 100, 180, 140], [40, 0, 280, 240]),
        ((800, 600), [275, 100, 525, 500], [100, 0, 700, 600]),
    ],
)
def test_square_center_and_edge_clamping(tmp_path, size, box, rect):
    src = tmp_path / "frame.png"
    out = tmp_path / "crop.png"
    im = Image.new("RGB", size, "green")
    im.save(src)
    g = crop_player_frame(src, out, box)
    assert g["crop_rect"] == rect
    side = rect[2] - rect[0]
    assert side == rect[3] - rect[1] == g["crop_side_px"]
    assert g["crop_scale"] == 768 / side
    with Image.open(out) as cropped:
        assert cropped.size == (768, 768)
        assert cropped.getpixel((384, 384)) == (0, 128, 0)
    assert g["box"][0] == pytest.approx((box[0] - rect[0]) * 768 / side)


@pytest.mark.parametrize("context", [False, True])
def test_prompt_is_base_plus_one_sentence(context):
    base = qwen3vl_checks.build_prompt(truth(), [10.05, 19.95])
    prompt = adapter.build_prompt(truth(), [10.05, 19.95], context=context)
    lines = prompt.splitlines()
    sentence = lines.pop(1)
    assert "\n".join(lines) == base
    assert (
        sentence
        == "Each image is a close crop centred on the marked player"
        + (", followed by the full frame for context" if context else "")
        + "."
    )
    assert adapter.PROMPT_VERSION == qwen3vl_checks.PROMPT_VERSION + "-crop"


@pytest.mark.parametrize("context", [False, True])
def test_schema_transport_image_order_and_identity(monkeypatch, tmp_path, context):
    captured = fake_transport(monkeypatch, json.dumps(read()))
    result = adapter.run(
        tmp_path / "clip.mp4", truth(), {"sample_limit": 2, "crop_context": context}
    )
    assert result["error"] is None
    body = captured[0]
    assert body["format"] == response_schema()
    assert body["options"]["num_ctx"] == 65536
    expected = ["crop", "context"] * 2 if context else ["crop"] * 2
    assert [f["image_kind"] for f in result["sent_frames"]] == expected
    assert len(body["messages"][0]["images"]) == len(expected)
    for encoded, kind in zip(body["messages"][0]["images"], expected):
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as im:
            assert im.size == ((768, 768) if kind == "crop" else (512, 410))
            assert any(
                r > 200 and b > 200 and g < 60
                for r, g, b in list(im.convert("RGB").get_flattened_data())
            )
    assert result["sent_frames"][0]["t"] == result["anchored_frames"][0]["t"]
    assert len(result["anchored_frames"]) == len(expected)


def test_runner_scores_and_fingerprints_crop(monkeypatch, tmp_path):
    fake_transport(monkeypatch, json.dumps(read()))
    manifest = frozen(tmp_path)
    args = _parser().parse_args(
        [
            "--adapter",
            "qwen3vl_checks_crop",
            "--manifest",
            str(manifest),
            "--report-root",
            str(tmp_path / "reports"),
            "--run-id",
            "crop",
            "--timeout",
            "900",
        ]
    )
    settings = _resolve_inference_settings(args, json.loads(manifest.read_text()))
    assert settings["format_mode"] == "schema" and settings["prompt_version"].endswith(
        "-crop"
    )
    assert settings["timeout_s"] == 900 and settings["crop_context"] is False
    args.crop_context = True
    context = _resolve_inference_settings(args, json.loads(manifest.read_text()))
    assert _settings_fingerprint(settings, ["fixture"]) != _settings_fingerprint(
        context, ["fixture"]
    )
    report, directory = run_benchmark(args)
    assert report["overall"]["scored_clips"] == 1
    assert json.loads((directory / "run.json").read_text())["crop_context"] is True
    args.adapter = "qwen3vl_checks"
    with pytest.raises(ValueError, match="requires qwen3vl_checks_crop"):
        _resolve_inference_settings(args, json.loads(manifest.read_text()))
