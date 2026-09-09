"""Geometry, gaps, proxy scoring, and actual browser JSONL contract regressions."""

from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path
import numpy as np
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from ball_track import track  # noqa: E402
from ball_truth_kit import import_labels  # noqa: E402
from common import samples  # noqa: E402
from detectors import merge_tiles  # noqa: E402
from metrics import agreement, clip_metrics, overall  # noqa: E402


def detection(x, y, confidence=0.8, width=10.0):
    return {
        "xy": [x, y],
        "confidence": confidence,
        "size_px": width,
        "box": [x - width / 2, y - width / 2, x + width / 2, y + width / 2],
    }


def test_tiling_nms_merge():
    # Same ball in overlapping tiles after restoring tile origin offsets.
    first = detection(100, 80, 0.7)
    duplicate = detection(101, 80, 0.9)
    separate = detection(125, 80, 0.6)
    assert merge_tiles([first, separate, duplicate]) == [duplicate, separate]
    assert merge_tiles([duplicate, first, separate]) == [duplicate, separate]
    assert merge_tiles([]) == []


def test_kalman_parabola_short_and_long_gaps():
    rows = []
    for i in range(31):
        t = i / 10
        xy = (100 + 20 * t, 100 + 12 * t * t)
        missing = i in {5, 6, 7} or 13 <= i <= 25
        rows.append({"t": t, "detections": [] if missing else [detection(*xy)]})
    result = track(rows, 3.1, sample_fps=10)
    assert result["fragments"] == 2
    assert result["continuity"] == pytest.approx(1.3 / 3.1)
    assert all(
        np.linalg.norm(np.array(p["xy"]) - [100 + 20 * p["t"], 100 + 12 * p["t"] ** 2])
        < 4
        for p in result["points"]
    )
    assert len(result["points"]) == 15
    # No fabricated tail continuity from missing observations.
    tail = track(
        [
            {"t": 0.0, "detections": [detection(10, 10)]},
            {"t": 0.5, "detections": []},
            {"t": 1.0, "detections": []},
        ],
        1.5,
    )
    assert tail["continuity"] == pytest.approx(1 / 3)


def test_kalman_jump_and_timestamp_guard():
    rows = [
        {"t": 0.0, "detections": [detection(0, 0)]},
        {"t": 0.5, "detections": [detection(301, 0)]},
    ]
    assert track(rows, 1.0)["fragments"] == 2
    rows[1]["t"] = 0
    with pytest.raises(ValueError):
        track(rows, 1.0)


def test_proxy_requires_distinct_voters_and_inclusive_40px():
    a = detection(10, 20)
    assert agreement({"a": [a, a], "b": [], "c": []}) == []
    assert agreement({"a": [a], "b": [detection(50, 20)], "c": []}) == [[30.0, 20.0]]
    assert agreement({"a": [a], "b": [detection(50.01, 20)], "c": []}) == []
    with pytest.raises(ValueError):
        agreement({"a": [a], "b": [a]})


def fixture_clip(note="passes the ball"):
    return {
        "clip_id": "test",
        "duration_s": 2.0,
        "truth_data": {
            "human_note": note,
            "box_track": [
                [0.0, 0, 0, 20, 20],
                [0.5, 0, 0, 20, 20],
                [1.0, 0, 0, 20, 20],
                [1.5, 0, 0, 20, 20],
            ],
        },
    }


def test_metrics_fixture_and_human_separation():
    raw = {
        "wall_s": 1.0,
        "frames": [
            {"t": i * 0.5, "detections": ds}
            for i, ds in enumerate(
                [
                    [detection(10, 20)],
                    [detection(500, 500)],
                    [],
                    [detection(10, 20, 0.2)],
                ]
            )
        ],
    }
    proxy = {0.0: [[10, 20]], 0.5: [[10, 20]], 1.0: [], 1.5: [[10, 20]]}
    human = {("test", 0.0): {"visible": True, "x": 10, "y": 20}}
    row = clip_metrics(fixture_clip(), raw, proxy, 0.1, human)
    assert row["self_agreement_rate_proxy"] == pytest.approx(2 / 3)
    assert row["human"]["detection_rate"] == 1
    assert row["human"]["labelled_frames"] == 1
    assert row["touch_preview_frames"] == 2
    assert row["fps"] == 4
    high = clip_metrics(fixture_clip(), raw, proxy, 0.5)
    assert high["proxy_agreement_frames"] == row["proxy_agreement_frames"]
    assert high["proxy_matched_frames"] == 1
    off = clip_metrics(fixture_clip("on the sideline"), raw, proxy, 0.1)
    assert off["boxes_per_10s_offpitch"] == 15
    assert overall([row, off])["gate_proxy"] == "UNMEASURABLE (proxy)"
    assert overall([row, off])["human"]["false_per_10s"] is None
    assert overall([row, off])["human"]["gate"] == "PARTIAL_HUMAN_REVIEW"
    assert overall([high])["gate_proxy"] == "UNMEASURABLE (proxy)"


def test_empty_visibility_never_passes():
    raw = {"wall_s": 1.0, "frames": [{"t": 0.0, "detections": []}]}
    a = clip_metrics(fixture_clip(), raw, {0.0: []}, 0.1)
    b = clip_metrics(fixture_clip("sideline"), raw, {0.0: []}, 0.1)
    assert overall([a, b])["gate_proxy"] == "UNMEASURABLE (proxy)"
    assert a["box_px_min"] is None


def test_browser_export_python_import_roundtrip(tmp_path):
    frames = [
        {"clip": "test", "t": 0.5, "source_size": [1920, 1080]},
        {"clip": "test", "t": 1.0, "source_size": [1920, 1080]},
    ]
    rows = [
        {"clip": "test", "t": 0.5, "x": 123.25, "y": 18.5, "visible": True},
        {"clip": "test", "t": 1.0, "x": None, "y": None, "visible": False},
    ]
    payload = {"frames": frames, "rows": rows}
    script = "const api=require(process.argv[1]),fs=require('fs'),d=JSON.parse(fs.readFileSync(0,'utf8'));const s=api.serialize(d.rows,d.frames);if(api.serialize(api.parse(s,d.frames),d.frames)!==s)throw Error('roundtrip');process.stdout.write(s);"
    text = subprocess.check_output(
        ["node", "-e", script, str(HERE / "truth_io.js")],
        input=json.dumps(payload),
        text=True,
    )
    path = tmp_path / "human.jsonl"
    path.write_text(text)
    assert list(import_labels(path, frames).values()) == rows
    for bad in [
        text + text,
        text.replace("123.25", "1920"),
        text.replace('"t":0.5', '"t":99'),
        text.replace('"x":null', '"x":3'),
    ]:
        path.write_text(bad)
        with pytest.raises(ValueError):
            import_labels(path, frames)
        result = subprocess.run(
            [
                "node",
                "-e",
                "const api=require(process.argv[1]);api.parse(process.argv[2],JSON.parse(process.argv[3]));",
                str(HERE / "truth_io.js"),
                bad,
                json.dumps(frames),
            ],
            capture_output=True,
        )
        assert result.returncode != 0


def test_samples_full_window_and_native_stack(tmp_path):
    cv2 = pytest.importorskip("cv2")

    video = tmp_path / "test.avi"
    writer = cv2.VideoWriter(
        str(video), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (64, 32)
    )
    assert writer.isOpened()
    for i in range(20):
        writer.write(np.full((32, 64, 3), i * 10, np.uint8))
    writer.release()
    clip = {
        "clip_id": "test",
        "video": str(video),
        "native_source": True,
        "window": {"start_s": 0.13, "end_s": 1.8},
    }
    output = list(samples(clip))
    assert [r["frame_index"] for r, _ in output] == [2, 6, 11, 16]
    assert [r["t"] for r, _ in output] == [0.2, 0.6, 1.1, 1.6]
    assert [round(float(f.mean())) for f in output[1][1]] == [40, 50, 60]
    assert all(np.array_equal(f, output[0][1][0]) for f in output[0][1])


def test_human_gate_uses_human_negatives_not_proxy():
    raw = {
        "wall_s": 1.0,
        "frames": [
            {"t": i * 0.5, "detections": [detection(10, 20)] if i == 0 else []}
            for i in range(4)
        ],
    }
    proxy = {i * 0.5: [[10, 20]] for i in range(4)}
    labels = {
        ("test", i * 0.5): {
            "visible": i == 0,
            "x": 10 if i == 0 else None,
            "y": 20 if i == 0 else None,
        }
        for i in range(4)
    }
    on = clip_metrics(fixture_clip(), raw, proxy, 0.1, labels)
    off = clip_metrics(fixture_clip("sideline"), raw, proxy, 0.1, labels)
    result = overall([on, off])
    assert result["gate_proxy"] == "UNMEASURABLE (proxy)"
    assert result["human"]["gate"] == "PARTIAL_HUMAN_REVIEW"
    assert result["human"]["false_per_10s"] == 0
    assert result["human"]["detection_rate"] == 1


def test_committed_measurements_regenerate_and_refuse_partial(tmp_path):
    from compare_ball import compare, load_measurements, markdown

    # This test runs once real measurements are captured, not invented data.
    measurements = load_measurements()
    execution = json.loads((HERE / "fixtures/execution.json").read_text())
    first = compare(measurements, execution)
    second = compare(load_measurements(), execution)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert markdown(first) == markdown(second)
    assert first["human_truth"]["labelled_frames"] == 0
    assert all(
        r["overall"]["on_ball_clips"] == 6 and r["overall"]["off_pitch_clips"] == 7
        for r in first["results"]
    )
    cid = measurements["clips"][0]["clip_id"]
    for name in measurements["outputs"]:
        measurements["outputs"][name][cid]["frames"].pop()
    with pytest.raises(ValueError, match="sample schedule"):
        compare(measurements, execution)


def test_kicked_ball_fast_segment_and_gap():
    # 25 m/s under 20 px/m: 250 px every 0.5 s, with one missing sample.
    rows = [
        {"t": i * 0.5, "detections": [] if i == 3 else [detection(100 + 250 * i, 300)]}
        for i in range(8)
    ]
    old_equivalent = track(rows, 4.0, max_speed_m_s=6.0)
    result = track(rows, 4.0)
    assert old_equivalent["fragments"] > 1
    assert result["fragments"] == 1
    assert result["continuity"] == 1
    assert result["longest_track_s"] == 4
    assert len(result["points"]) == 7


def test_pair_decomposition_disjoint_counts():
    from metrics import pair_decomposition

    votes = {"rf_full": [detection(10, 20)], "rf_2x2": [detection(20, 20)], "wasb": []}
    assert pair_decomposition(votes) == {
        "rf_pair_only": True,
        "with_wasb": False,
        "rf_pair": True,
        "any_pair": True,
    }
    votes["wasb"] = [detection(30, 20)]
    assert pair_decomposition(votes) == {
        "rf_pair_only": False,
        "with_wasb": True,
        "rf_pair": True,
        "any_pair": True,
    }


def test_tiled_wasb_geometry_and_duplicate_merge():
    cv2 = pytest.importorskip("cv2")
    assert cv2 is not None
    from detectors import WASBDetector, tile_bounds, merge_points

    assert len(tile_bounds(1920, 1080, 2)) == 4
    model = object.__new__(WASBDetector)

    def maps(stack):
        out = []
        for x, y, _, _ in tile_bounds(1920, 1080, 2):
            heatmap = np.zeros((3, 288, 512), np.float32)
            heatmap[2, 144, 256] = 0.9
            out.append(((x, y, 512 / 960, 0), heatmap))
        return out

    model.heatmaps = maps
    rows = model([np.zeros((1080, 1920, 3), np.uint8)] * 3, [1920, 1080])
    assert sorted(d["xy"] for d in rows) == [
        [480.0, 270.0],
        [480.0, 810.0],
        [1440.0, 270.0],
        [1440.0, 810.0],
    ]
    assert (
        len(
            merge_points(
                [
                    {"xy": [1.0, 2.0], "heatmap_mass": 2.0},
                    {"xy": [3.0, 2.0], "heatmap_mass": 1.0},
                ]
            )
        )
        == 1
    )


def test_human_scoring_640_labels_no_models_no_media(tmp_path):
    from compare_ball import load_measurements

    measurements = load_measurements()
    plan = measurements["human_label_plan"]
    assert len(plan["on_ball"]) == 540
    assert len(plan["off_pitch"]) == 100
    labels = [
        {
            **f,
            "x": 1.0 if group == "on_ball" else None,
            "y": 1.0 if group == "on_ball" else None,
            "visible": group == "on_ball",
        }
        for group in ("on_ball", "off_pitch")
        for f in plan[group]
    ]
    truth = tmp_path / "synthetic-test-only.jsonl"
    truth.write_text("".join(json.dumps(r) + "\n" for r in labels))
    output = tmp_path / "human-result"
    subprocess.run(
        [
            sys.executable,
            str(HERE / "score_from_saved.py"),
            "--human-jsonl",
            str(truth),
            "--out-prefix",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = json.loads(output.with_suffix(".json").read_text())
    assert {r["candidate"] for r in result["results"]} == {
        "rf_full",
        "rf_2x2",
        "rf_3x3",
        "wasb",
        "wasb_2x2",
    }
    assert result["human_truth"]["labelled_frames"] == 640
    for r in result["results"]:
        h = r["overall"]["human"]
        assert h["all_onball_labelled"]
        assert h["labelled_offpitch_frames"] == 100
        assert h["gate"] in {"PASS (human sample)", "FAIL (human sample)"}
        assert r["overall"]["gate_proxy"] == "UNMEASURABLE (proxy)"


def test_proxy_perfect_agreement_cannot_pass_gate():
    raw = {"wall_s": 1.0, "frames": [{"t": 0.0, "detections": [detection(10, 20)]}]}
    on = clip_metrics(fixture_clip(), raw, {0.0: [[10, 20]]}, 0.1)
    off = clip_metrics(
        fixture_clip("sideline"),
        {"wall_s": 1.0, "frames": [{"t": 0.0, "detections": []}]},
        {0.0: []},
        0.1,
    )
    result = overall([on, off])
    assert result["self_agreement_rate_proxy"] == 1
    assert result["boxes_per_10s_offpitch"] == 0
    assert result["gate_proxy"] == "UNMEASURABLE (proxy)"


def test_human_visible_offpitch_frame_counts_unmatched_and_duplicates():
    raw = {
        "wall_s": 1.0,
        "frames": [
            {
                "t": 0.0,
                "detections": [
                    detection(10, 20),
                    detection(11, 20),
                    detection(500, 500),
                ],
            }
        ],
    }
    label = {("test", 0.0): {"visible": True, "x": 10, "y": 20}}
    row = clip_metrics(fixture_clip("sideline"), raw, {0.0: []}, 0.1, label)
    assert row["human"]["unmatched_detections"] == 2
    assert overall([row])["human"]["false_per_10s"] == 40
