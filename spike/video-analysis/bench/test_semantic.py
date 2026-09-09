"""Semantic contract, honesty scoring, actual request/drawing and note intake fixtures."""

import base64
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from adapters import common, qwen3vl_annotated as adapter  # noqa: E402
from apply_notes import apply_notes, template  # noqa: E402
from compare_runs import anchor_only_attempt  # noqa: E402
from compare_semantic import compare, markdown  # noqa: E402
from run_bench import _parser, _resolve_inference_settings, run_benchmark  # noqa: E402
from semantic_contract import (  # noqa: E402
    ACTION_TYPES,
    PHASES,
    VOCABULARIES,
    SemanticRead,
    parse_read,
    response_schema,
)
from semantic_score import score_clip, score_read, score_run  # noqa: E402


def truth(note=None):
    return {
        "clip_id": "fixture",
        "window": {"start_s": 10.0, "end_s": 20.0},
        "jersey_number": 12,
        "kit_color": "red",
        "frame_size": [100, 80],
        "box_track": [[10.0, 10, 10, 40, 60], [20.0, 20, 10, 50, 60]],
        "human_note": note,
    }


def event(**changes):
    return {
        "event_type": "pass",
        "phase": "attack",
        "t0": 12.0,
        "t1": 14.0,
        "outcome": "unclear",
        "confidence": "low",
        **changes,
    }


def read(**changes):
    return {
        "events": [],
        "player_visible": "yes",
        "kit_color_seen": "red",
        "sentence": "The marked player is visible.",
        **changes,
    }


def raw(**changes):
    return {
        "clip_id": "fixture",
        "semantic_raw": json.dumps(read(**changes)),
        "wall_s": 2.0,
        "error": None,
        "sent_frames": [],
        "anchored_frames": [],
    }


def frozen(tmp_path):
    (tmp_path / "truth").mkdir()
    (tmp_path / "truth/fixture.json").write_text(json.dumps(truth()))
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "frozen_set_id": "fixture-set",
                "clips": [
                    {
                        "clip_id": "fixture",
                        "truth": "truth/fixture.json",
                        "clip": "clips/fixture.mp4",
                    }
                ],
            }
        )
    )
    return manifest


def test_contract_and_vocab_are_one_source():
    assert isinstance(parse_read(json.dumps(read(events=[event()]))), SemanticRead)
    assert set(ACTION_TYPES) == set(common.qwen_match_analysis.ACTION_TYPES) | {
        "none",
        "unclear",
    }
    assert PHASES == common.qwen_match_analysis.PHASES
    schema = response_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["events"]["maxItems"] == 3
    item = schema["properties"]["events"]["items"]
    assert item["additionalProperties"] is False
    prompt = adapter.build_prompt(truth(), [10.05, 19.95])
    for key, values in VOCABULARIES.items():
        prop = schema["properties"].get(key) or item["properties"][key]
        assert prop["enum"] == list(values)
        assert f"{key} must be exactly one of: {', '.join(values)}." in prompt


@pytest.mark.parametrize(
    "changes",
    [
        {"box": [1, 2, 3, 4]},
        {"player_visible": "maybe"},
        {"events": [event(event_type="goal")]},
        {"events": [event(box=[1, 2, 3, 4])]},
        {"events": [event()] * 4},
        {"events": [event(t0=True)]},
        {"events": [event(t0="12.0")]},
        {"events": [event(t0=float("nan"))]},
        {"events": [event(t1=1.0)]},
        {"sentence": "x" * 201},
        {"sentence": "First sentence. Second sentence."},
        {"sentence": " "},
    ],
)
def test_invalid_contract(changes):
    with pytest.raises(ValidationError):
        parse_read(json.dumps(read(**changes)))


def test_time_window_is_evidence_gate_not_parse_failure():
    result = raw(events=[event(t0=9.5, t1=20.5), event(t0=9.499), event(t1=20.501)])
    clip = score_clip(result, truth())
    assert clip["status"] == "scored"
    assert clip["metrics"]["event_time_in_window"] == [True, False, False]
    assert clip["metrics"]["time_in_window"] is False
    report = score_run([result], {"fixture": truth()})
    assert report["overall"]["time_in_window_event_rate"] == 0.3333


@pytest.mark.parametrize(
    "sentence,invented",
    [
        ("#12 is visible.", False),
        ("#9 is visible.", True),
        ("The player wears jersey 9.", True),
        ("The player wears number 9.", True),
        ("At 12.5 seconds the player is visible.", False),
    ],
)
def test_number_rule_rejects_any_unsupplied_number(sentence, invented):
    assert (
        score_read(SemanticRead(**read(sentence=sentence)), truth())["number_invented"]
        is invented
    )


def test_empty_presence_colour_and_live_notes():
    empty = score_read(
        SemanticRead(**read(player_visible="unclear", kit_color_seen="unclear")),
        truth(),
    )
    assert empty["empty"] and empty["presence_only_read"]
    assert empty["kit_color_match"] is None
    assert empty["kit_color_abstain"] and not empty["kit_color_wrong"]
    assert empty["fabricated_event_classes"] is None
    action = score_read(
        SemanticRead(**read(events=[event()], kit_color_seen="blue")),
        truth("The player stands still."),
    )
    assert not action["presence_only_read"] and not action["empty"]
    assert action["fabricated_event_classes"] == ["pass"]
    assert action["kit_color_wrong"] and action["kit_color_match"] is False
    matching = score_read(
        SemanticRead(**read(events=[event()])), truth("The player passes.")
    )
    assert matching["fabricated_event_classes"] == []


def test_failed_denominators_do_not_hide_invalid_attempts():
    failed = {**raw(), "clip_id": "invalid", "semantic_raw": "bad JSON", "wall_s": 10.0}
    report = score_run(
        [raw(), raw(kit_color_seen="unclear"), failed],
        {"fixture": truth(), "invalid": truth()},
    )
    m = report["overall"]
    assert (m["scored_clips"], m["failed_clips"]) == (2, 1)
    assert m["valid_rate"] == 1 and m["valid_attempt_rate"] == 0.6667
    assert m["wall_s_per_clip"] == 4.667
    assert m["kit_color_match_rate"] == m["kit_color_abstain_rate"] == 0.5
    assert m["kit_color_match_when_asserted_rate"] == 1
    assert m["fabricated_rate"] is None
    assert m["time_in_window_event_rate"] is None


def test_dense_sampling_covers_window_and_sparse_control():
    for duration, count in [(4.0, 8), (10.0, 12), (73.0, 12)]:
        t = {**truth(), "window": {"start_s": 10.0, "end_s": 10 + duration}}
        samples = adapter.spread_timestamps(t)
        assert len(samples) == count
        assert samples[0][0] == 0.05
        assert samples[-1][0] == duration - 0.05
        gaps = [round(b[0] - a[0], 3) for a, b in zip(samples, samples[1:])]
        assert max(gaps) - min(gaps) <= 0.0011
        assert all(abs(absolute - local - 10) < 0.001 for local, absolute in samples)
    assert adapter.spread_timestamps(truth(), 30, 3) == [(0.05, 10.05)]


def fake_transport(monkeypatch, content, *, thinking=False):
    captured = []

    def extract(_clip, output, *_args):
        Image.new("RGB", (100, 80), (0, 0, 0)).save(output)

    def urlopen(request, **_kwargs):
        body = json.loads(request.data)
        captured.append(body)
        return io.BytesIO(
            json.dumps(
                {
                    "message": {
                        "content": "" if thinking else content,
                        "thinking": content if thinking else "",
                    },
                    "done_reason": "stop",
                }
            ).encode()
        )

    monkeypatch.setattr(common.qwen_match_analysis, "extract_frame", extract)
    monkeypatch.setattr(common.shutil, "which", lambda name: f"/fake/{name}")
    monkeypatch.setattr(common.qwen_match_analysis.urllib.request, "urlopen", urlopen)
    monkeypatch.setenv("BENCH_NUM_CTX", "65536")
    return captured


@pytest.mark.parametrize("thinking", [False, True])
def test_adapter_actual_extraction_drawing_schema_and_transport(
    monkeypatch, tmp_path, thinking
):
    captured = fake_transport(
        monkeypatch, json.dumps(read(events=[event()])), thinking=thinking
    )
    result = adapter.run(tmp_path / "clip.mp4", truth(), {})
    assert result["error"] is None
    assert result["done_reason"] == "stop" and result["from_thinking"] is thinking
    assert len(result["sent_frames"]) == len(result["anchored_frames"]) == 12
    body = captured[0]
    assert body["format"] == response_schema()
    assert body["options"]["num_ctx"] == 65536
    assert body["options"]["num_predict"] == 400
    assert body["think"] is False
    assert len(body["messages"][0]["images"]) == 12
    for encoded in body["messages"][0]["images"]:
        image = Image.open(io.BytesIO(base64.b64decode(encoded)))
        assert image.size == (100, 80)
        assert any(
            r > 100 and r > g * 1.5
            for r, g, b in [
                image.getpixel((x, y))
                for y in range(image.height)
                for x in range(image.width)
            ]
        )
    prompt = body["messages"][0]["content"]
    assert "[10.000, 20.000]" in prompt and "10.050" in prompt and "19.950" in prompt
    assert "wearing red" not in prompt
    for frame, anchor in zip(result["sent_frames"], result["anchored_frames"]):
        assert anchor["box_source_space"] == common.interpolated_box(
            truth()["box_track"], frame["t"]
        )


def test_adapter_schema_failure_safe_error_and_no_geometry_fallback(
    monkeypatch, tmp_path
):
    captured = fake_transport(monkeypatch, json.dumps(read(secret="PRIVATE-SENTINEL")))
    result = adapter.run(tmp_path / "clip.mp4", truth(), {})
    assert result["error"] == "semantic schema validation failed"
    assert result["semantic"] is None
    assert "PRIVATE-SENTINEL" in result["semantic_raw"]  # Local raw evidence only.
    captured.clear()
    result = adapter.run(tmp_path / "clip.mp4", {**truth(), "box_track": []}, {})
    assert "truth box is unavailable" in result["error"]
    assert not captured and result["sent_frames"] == []


def test_context_cannot_be_lowered(monkeypatch):
    monkeypatch.setenv("BENCH_NUM_CTX", "4096")
    with pytest.raises(ValueError, match="65536"):
        adapter.call_model("", [], {}, {})


def test_note_roundtrip_and_scoring_becomes_live(tmp_path):
    manifest = frozen(tmp_path)
    form = tmp_path / "notes.md"
    form.write_text(template([truth()]))
    original = (tmp_path / "truth/fixture.json").read_bytes()
    assert apply_notes(form, manifest) == 0
    assert (tmp_path / "truth/fixture.json").read_bytes() == original
    form.write_text(
        form.read_text().replace("| note:", "| note: The player stands still.")
    )
    assert apply_notes(form, manifest) == 1
    updated = json.loads((tmp_path / "truth/fixture.json").read_text())
    assert updated == {**truth(), "human_note": "The player stands still."}
    assert (
        score_run([raw(events=[event()])], {"fixture": updated})["overall"][
            "fabricated_rate"
        ]
        == 1
    )


@pytest.mark.parametrize(
    "change",
    [
        lambda s: s.replace("#12", "#9"),
        lambda s: s.replace("10.00", "11.00"),
        lambda s: s.replace("`fixture`", "`unknown`"),
        lambda s: s + s,
        lambda s: "",
    ],
)
def test_bad_notes_fail_before_writes(tmp_path, change):
    manifest = frozen(tmp_path)
    form = tmp_path / "notes.md"
    form.write_text(change(template([truth()]).replace("| note:", "| note: A pass.")))
    original = (tmp_path / "truth/fixture.json").read_bytes()
    with pytest.raises(ValueError):
        apply_notes(form, manifest)
    assert (tmp_path / "truth/fixture.json").read_bytes() == original


def test_tracked_truth_refused(tmp_path):
    manifest = frozen(tmp_path)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        ["git", "-C", str(tmp_path), "add", "truth/fixture.json"], check=True
    )
    form = tmp_path / "notes.md"
    form.write_text(template([truth()]).replace("| note:", "| note: A pass."))
    with pytest.raises(ValueError, match="tracked or nonignored"):
        apply_notes(form, manifest)


def test_runner_and_comparison_roundtrip(monkeypatch, tmp_path):
    manifest = frozen(tmp_path)
    captured = []

    def run(_clip, _truth, cfg):
        captured.append(cfg)
        return raw()

    monkeypatch.setattr(adapter, "run", run)
    for name, flags in [
        ("dense", []),
        ("prod30", ["--sample-interval", "30", "--sample-limit", "3"]),
    ]:
        args = _parser().parse_args(
            [
                "--adapter",
                "qwen3vl_annotated",
                "--manifest",
                str(manifest),
                "--report-root",
                str(tmp_path),
                "--run-id",
                name,
                *flags,
            ]
        )
        report, directory = run_benchmark(args)
        assert report["overall"]["scored_clips"] == 1
        assert (
            (directory / "report.md")
            .read_text()
            .startswith("The frozen clips have no human notes")
        )
        before = len(captured)
        run_benchmark(args)
        assert len(captured) == before
    assert captured[0]["sample_interval"] == 0.5 and captured[0]["sample_limit"] == 12
    assert captured[1]["sample_interval"] == 30 and captured[1]["sample_limit"] == 3
    assert all(
        c["anchor_mode"] == "all" and c["format_mode"] == "schema" for c in captured
    )
    result = compare(tmp_path, {"dense": "dense", "prod30": "prod30"}, manifest)
    assert result == compare(tmp_path, {"dense": "dense", "prod30": "prod30"}, manifest)
    assert result["lanes"]["dense"]["five_sentences"] == [
        {"clip_id": "fixture", "sentence": read()["sentence"]}
    ]
    assert read()["sentence"] in markdown(result)
    for lane in result["lanes"].values():
        assert lane["report"]["overall"]["fabricated_rate"] is None
    args.sample_interval = 5
    args.sample_limit = 6
    assert (
        _resolve_inference_settings(args, {"frozen_set_id": "fixture-set"})[
            "sample_interval"
        ]
        == 5
    )


def test_anchor_only_means_exact_anchor_not_nearby_video():
    assert anchor_only_attempt(
        {"sent_frames": [{"t": 10.05}], "anchored_frames": [{"t": 10.05}]}
    )
    assert not anchor_only_attempt({"sent_frames": []})
    assert not anchor_only_attempt(
        {"sent_frames": [{"t": 10.0}, {"t": 10.5}], "anchored_frames": [{"t": 10.05}]}
    )
    assert not anchor_only_attempt(
        {
            "sent_frames": [{"t": 10.05}],
            "anchored_frames": [{"t": 10.05}],
            "error": "truth box is unavailable",
        }
    )


def test_gap_sampling_snaps_time_not_geometry_and_records_it(monkeypatch, tmp_path):
    t = truth()
    t["box_track"] = [
        [10 + i / 10, 10, 10, 40, 60] for i in range(101) if i not in {1, 2, 3, 4, 5}
    ]
    targets = adapter.spread_timestamps(t)
    shifted = adapter.annotated_timestamps(t, targets)
    assert shifted[0] == (0.0, 10.0)
    assert all(
        common.interpolated_box(t["box_track"], absolute) is not None
        for _, absolute in shifted
    )
    fake_transport(monkeypatch, json.dumps(read()))
    result = adapter.run(tmp_path / "clip.mp4", t, {})
    assert result["error"] is None
    assert result["sent_frames"][0]["target_t"] == 10.05
    assert result["sent_frames"][0]["sampling_shift_s"] == -0.05
    with pytest.raises(RuntimeError, match="within 0.5s"):
        adapter.annotated_timestamps(
            {
                **t,
                "box_track": [
                    [10, 1, 1, 2, 2],
                    [10.1, 1, 1, 2, 2],
                    [19, 1, 1, 2, 2],
                    [19.1, 1, 1, 2, 2],
                ],
            },
            [(5, 15)],
        )


@pytest.mark.parametrize(
    "sentence,presence,consistent",
    [
        ("Player in red kit visible on field throughout sequence.", True, False),
        (
            "Player #12 in red kit is visible on the field throughout the sequence.",
            True,
            False,
        ),
        (
            "Player #21 in red kit is visible on the field with other players.",
            True,
            False,
        ),
        ("Player in red kit visible moving across field during play.", True, False),
        ("Player in red kit visible on right sideline holding ball.", True, False),
        ("Player in red kit visible on field carrying ball.", False, False),
        (
            "Player #12 in red kit is visible running with the ball during play.",
            False,
            False,
        ),
        (
            "The marked player in red carries the ball and passes it during build-up play.",
            False,
            True,
        ),
    ],
)
def test_real_presence_sentences_are_checked_independently_of_events(
    sentence, presence, consistent
):
    result = score_read(
        SemanticRead(**read(sentence=sentence, events=[event(event_type="carry")])),
        truth(),
    )
    assert result["presence_only_sentence"] is presence
    assert result["sentence_event_consistency"] is consistent
    assert result["presence_only_read"] is False


def test_consistency_requires_every_event_class_and_preserves_keyword_rule():
    value = read(
        sentence="Player in red kit carries ball and engages in duel with opponent.",
        events=[event(event_type="carry"), event(event_type="duel")],
    )
    assert score_read(SemanticRead(**value), truth())["sentence_event_consistency"]
    value["events"].append(event(event_type="pass"))
    result = score_read(SemanticRead(**value), truth())
    assert not result["sentence_event_consistency"]
    assert result["sentence_event_unmatched_classes"] == ["pass"]
    value["events"] = [event(event_type="off_ball")]
    assert score_read(SemanticRead(**value), truth())[
        "sentence_event_unmatched_classes"
    ] == ["off_ball"]
    value["events"] = []
    assert score_read(SemanticRead(**value), truth())["sentence_event_consistency"]
    legacy = score_read(SemanticRead(**read()), truth())
    assert legacy["presence_only_read"] and legacy["presence_only_sentence"]
    assert legacy["zero_duration_event_rate"] is None
    assert legacy["window_filling_event_rate"] is None


def test_real_single_still_and_full_window_event_shapes():
    still_truth = {**truth(), "window": {"start_s": 3074.17, "end_s": 3103.07}}
    still = raw(
        sentence="A player in red kit is visible running on the field.",
        events=[
            event(
                event_type="carry",
                t0=3074.22,
                t1=3074.22,
                confidence="high",
                outcome="completed",
            )
        ],
    )
    still["sent_frames"] = [{"t": 3074.22}]
    metric = score_clip(still, still_truth)["metrics"]
    assert metric["zero_duration_event_rate"] == 1
    assert metric["window_filling_event_rate"] == 0
    assert metric["events_per_sent_frame"] == 1
    assert metric["high_confidence_completed_from_one_frame_count"] == 1
    long_truth = {**truth(), "window": {"start_s": 2371.07, "end_s": 2421.45}}
    dense = raw(
        events=[
            event(
                event_type="carry",
                t0=2371.12,
                t1=2421.45,
                confidence="high",
                outcome="completed",
            )
        ]
    )
    dense["sent_frames"] = [{"t": 2371.12 + i} for i in range(12)]
    metric = score_clip(dense, long_truth)["metrics"]
    assert metric["zero_duration_event_rate"] == 0
    assert metric["window_filling_event_rate"] == 1
    assert metric["events_per_sent_frame"] == 0.0833
    assert metric["high_confidence_completed_from_one_frame_count"] == 0
    boundary = score_read(
        SemanticRead(**read(events=[event(t0=9.5, t1=20.5), event(t0=9.499, t1=20.0)])),
        truth(),
    )
    assert boundary["window_filling_events"] == [True, False]


def test_new_event_rates_use_events_and_frame_counts_not_clip_means():
    one = {
        **raw(events=[event(t0=10.0, t1=10.0), event(t0=10.0, t1=20.0)]),
        "sent_frames": [{"t": 10.0}],
    }
    many = {**raw(events=[event()]), "sent_frames": [{"t": 10.0}] * 12}
    report = score_run([one, many], {"fixture": truth()})
    assert report["overall"]["zero_duration_event_rate"] == 0.3333
    assert report["overall"]["window_filling_event_rate"] == 0.3333
    assert report["overall"]["events_per_sent_frame"] == 0.2308


def test_semantic_kit_detail_and_thinking_rates_include_failed_attempts():
    kit = {
        **raw(
            sentence="Player in red jersey with number 9 visible on field moving and interacting."
        ),
        "from_thinking": True,
    }
    label = raw(sentence="Player marked #9 is visible.")
    failed = {**raw(), "semantic_raw": "invalid", "from_thinking": True}
    report = score_run(
        [kit, label, failed], {"fixture": {**truth(), "jersey_number": 9}}
    )
    assert report["overall"]["supplied_number_asserted_as_kit_detail_rate"] == 0.5
    assert report["overall"]["from_thinking_rate"] == 0.6667
    from score import score_run as score_geometry

    legacy = score_geometry(
        [
            {"clip_id": "x", "from_thinking": True, "error": "failed"},
            {"clip_id": "y", "error": "failed"},
        ],
        {},
    )
    assert legacy["overall"]["from_thinking_rate"] == 0.5


def test_truth_provenance_tracks_bytes_and_notes_without_changing_frozen_id(
    tmp_path, capsys
):
    from apply_notes import main as apply_main
    from provenance import load_truth_snapshot

    manifest = frozen(tmp_path)
    original_manifest = manifest.read_bytes()
    _, before = load_truth_snapshot(manifest)
    notes = tmp_path / "notes.md"
    notes.write_text(
        template([truth()]).replace("| note:", "| note: The player holds position.")
    )
    assert apply_main(["--manifest", str(manifest), "--notes", str(notes)]) == 0
    _, after = load_truth_snapshot(manifest)
    assert all(before[key] != after[key] for key in before)
    printed = capsys.readouterr().out
    assert all(key in printed and value in printed for key, value in after.items())
    assert manifest.read_bytes() == original_manifest
    path = tmp_path / "truth/fixture.json"
    path.write_text(json.dumps(json.loads(path.read_text()), separators=(",", ":")))
    _, reformatted = load_truth_snapshot(manifest)
    assert (
        reformatted["truth_set_sha256_after_notes"]
        != after["truth_set_sha256_after_notes"]
    )
    assert reformatted["human_notes_sha256"] == after["human_notes_sha256"]


@pytest.mark.parametrize("adapter_name", ["baseline", "qwen3vl_annotated"])
def test_both_runners_record_snapshot_hashes_and_refuse_stale_resume(
    monkeypatch, tmp_path, adapter_name
):
    from types import SimpleNamespace
    import run_bench
    from provenance import load_truth_snapshot

    manifest = frozen(tmp_path)
    fake = SimpleNamespace(
        DEFAULT_MODEL="fake", run=lambda *_: {**raw(), "claims": [], "error": None}
    )
    monkeypatch.setattr(run_bench, "_adapter_module", lambda _: fake)
    args = _parser().parse_args(
        [
            "--adapter",
            adapter_name,
            "--manifest",
            str(manifest),
            "--report-root",
            str(tmp_path / "runs"),
            "--run-id",
            "snapshot",
        ]
    )
    report, directory = run_benchmark(args)
    metadata = json.loads((directory / "run.json").read_text())
    _, hashes = load_truth_snapshot(manifest)
    for key, value in hashes.items():
        assert metadata[key] == report[key] == value
    run_benchmark(args)
    path = tmp_path / "truth/fixture.json"
    value = json.loads(path.read_text())
    value["human_note"] = "The player passes."
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        run_benchmark(args)


def test_lane_a_magenta_preserves_shared_red_default(tmp_path, monkeypatch):
    from grounding import draw_anchor_box
    from adapters.qwen3vl_ollama import apply_anchors

    paths = [tmp_path / "red.png", tmp_path / "magenta.png"]
    for path in paths:
        Image.new("RGB", (100, 80)).save(path)
    draw_anchor_box(paths[0], [10, 10, 40, 60], "#12")
    frames = [{"path": str(paths[1]), "t": 10.0, "sent_w": 100, "sent_h": 80}]
    apply_anchors(frames, truth(), "all", color=adapter.ANCHOR_COLOR)
    assert Image.open(paths[0]).getpixel((10, 30)) == (255, 40, 40)
    assert Image.open(paths[1]).getpixel((10, 30)) == (255, 0, 255)
    assert "magenta rectangle" in adapter.build_prompt(truth(), [10.0])
