"""Acceptance audit, clip leakage, point supervision, saved model scoring."""

from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys
import pytest
from ball_truth_kit import import_labels
from common import dump
from compare_ball import load_measurements, compare
from extra_detections import load_extra
from human_loop import (
    frame_catalog,
    review_plan,
    saved_suggestions,
    load_suggestions,
    write_jsonl,
)
from train_tiny_ball import split_clips, box_recipe, tile_bounds, tile_labels, evaluate

HERE = Path(__file__).parent


@pytest.fixture(scope="module")
def measured():
    return load_measurements()


def test_review_targets_and_suggestions(measured, tmp_path):
    frames = frame_catalog(measured)
    plan = review_plan(frames)
    assert len(plan["on_ball"]) == 540
    assert len(plan["every_third_offpitch"]) == 74
    assert len(plan["offpitch_topup"]) == 26
    assert len(plan["offpitch_clips"]) == 7
    assert plan["target"] == 640
    assert (
        len({(f["clip"], f["t"]) for f in plan["on_ball"] + plan["off_pitch"]}) == 640
    )
    # Deterministic and grounded in real saved rows, no human labels created.
    suggested = saved_suggestions(measured)
    assert len(suggested) == 1041
    for s in suggested:
        rows = measured["outputs"][s["source"]][s["clip"]]["frames"]
        r = next(r for r in rows if r["t"] == s["t"])
        assert any(
            d["xy"] == [s["x"], s["y"]] and d["confidence"] == s["score"]
            for d in r["detections"]
        )
    p = tmp_path / "suggestions.jsonl"
    write_jsonl(p, suggested)
    assert load_suggestions(p, frames) == suggested
    with pytest.raises(ValueError):
        import_labels(p, frames)  # Suggestions are never accepted as human truth.
    for bad in [
        suggested + [suggested[0]],
        [{**suggested[0], "x": 1920}],
        [{**suggested[0], "score": float("nan")}],
    ]:
        p.write_text("\n".join(json.dumps(r) for r in bad))
        with pytest.raises(ValueError):
            load_suggestions(p, frames)


def test_accepted_provenance_browser_python_roundtrip(tmp_path):
    frames = [{"clip": "c", "t": 1.0, "source_size": [1920, 1080]}]
    old = {"clip": "c", "t": 1.0, "x": 4.0, "y": 5.0, "visible": True}
    accepted = {
        **old,
        "source_accepted": True,
        "accepted_source": "model:run1",
        "accepted_score": 0.8,
    }
    for row in (old, accepted, {**old, "source_accepted": False}):
        out = subprocess.check_output(
            [
                "node",
                "-e",
                "const a=require(process.argv[1]);process.stdout.write(a.serialize([JSON.parse(process.argv[2])],JSON.parse(process.argv[3])));",
                str(HERE / "truth_io.js"),
                json.dumps(row),
                json.dumps(frames),
            ],
            text=True,
        )
        p = tmp_path / "labels.jsonl"
        p.write_text(out)
        assert import_labels(p, frames)[("c", 1.0)] == row
    for bad in [
        {**old, "source_accepted": True},
        {**accepted, "visible": False, "x": None, "y": None},
        {**accepted, "source_accepted": False},
        {**accepted, "accepted_score": 1.1},
    ]:
        p.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            import_labels(p, frames)
        r = subprocess.run(
            [
                "node",
                "-e",
                "require(process.argv[1]).validate(JSON.parse(process.argv[2]),JSON.parse(process.argv[3]));",
                str(HERE / "truth_io.js"),
                json.dumps(bad),
                json.dumps(frames),
            ],
            capture_output=True,
        )
        assert r.returncode != 0


def test_clip_split_and_training_only_sizes(measured):
    frames = frame_catalog(measured)
    labels = {
        (f["clip"], f["t"]): {"visible": True, "x": 500, "y": 500}
        for f in frames
        if f["class"] == "on_ball"
    }
    split = split_clips(measured, labels)
    assert len(split["train"]) == 4 and len(split["held_out"]) == 2
    assert not set(split["train"]) & set(split["held_out"])
    recipe = box_recipe(measured, labels, split["train"])
    for key, row in labels.items():
        if key[0] in split["held_out"]:
            row.update(x=0, y=0)
    assert recipe == box_recipe(measured, labels, split["train"])
    one = {k: v for k, v in labels.items() if k[0] == split["train"][0]}
    with pytest.raises(ValueError):
        split_clips(measured, one)
    assert split_clips(measured, one, True)["held_out"] == []


def test_point_tiles_seams_negatives_and_explicit_pseudo():
    label = {"x": 960.0, "y": 540.0, "visible": True}
    bounds = tile_bounds()
    assert [bool(tile_labels(label, b, 18.0)) for b in bounds] == [
        False,
        False,
        False,
        True,
    ]
    assert all(tile_labels({"visible": False}, b, 18.0) == [] for b in bounds)
    # Distinct small RF box 19 px away is included ONLY with --pseudo.
    rf = [{"xy": [979.0, 540.0], "confidence": 0.2, "box": [977, 538, 981, 542]}]
    assert len(tile_labels(label, bounds[-1], 18.0, rf)) == 1
    assert len(tile_labels(label, bounds[-1], 18.0, rf, True)) == 2
    rf[0]["xy"] = [981.0, 540.0]
    assert len(tile_labels(label, bounds[-1], 18.0, rf, True)) == 1


def test_20px_matching_precision_and_offpitch_unlabelled():
    ds = [{"xy": [20, 0]}, {"xy": [20, 0]}, {"xy": [20.001, 0]}]
    outputs = {
        "held": {
            "wall_s": 2,
            "frames": [{"t": 0.0, "detections": ds}, {"t": 0.5, "detections": ds}],
        },
        "off": {
            "wall_s": 1,
            "frames": [{"t": 0.0, "detections": ds}, {"t": 0.5, "detections": ds}],
        },
    }
    labels = {
        ("held", 0.0): {"visible": True, "x": 0.0, "y": 0.0},
        ("off", 0.0): {"visible": True, "x": 0.0, "y": 0.0},
    }
    r = evaluate(
        outputs,
        labels,
        ["held"],
        [{"clip": "off", "t": 0.0}, {"clip": "off", "t": 0.5}],
    )
    assert r["held_out"]["recall"] == 1
    assert r["held_out"]["precision"] == pytest.approx(1 / 3)
    assert r["off_pitch_sample"]["false_per_frame"] == 2
    assert r["off_pitch_sample"]["labelled_frames"] == 1


def test_extra_candidate_validation_and_scoring(measured, tmp_path):
    data = {
        "schema_version": 1,
        "frozen_set_id": measured["frozen_set_id"],
        "source_sha256": measured["runs"]["rf_full"]["source_sha256"],
        "source_size": [1920, 1080],
        "synthetic_smoke": True,
        "threshold": 0.1,
        "outputs": copy.deepcopy(measured["outputs"]["rf_full"]),
    }
    for raw in data["outputs"].values():
        for row in raw["frames"]:
            row["detections"] = [
                {
                    "xy": [100.0, 100.0],
                    "box": [95.0, 95.0, 105.0, 105.0],
                    "confidence": 0.8,
                    "size_px": 10.0,
                }
            ]
    p = tmp_path / "extra.json"
    dump(p, data)
    extras = load_extra([f"tiny={p}"], measured)
    execution = json.loads((HERE / "fixtures/execution.json").read_text())
    r = compare(measured, execution, extra_detections=extras)
    extra = next(r for r in r["results"] if r["candidate"] == "tiny")
    assert extra["overall"]["gate_proxy"] == "UNMEASURABLE (proxy)"
    assert extra["overall"]["human"]["gate"] == "SYNTHETIC SMOKE — NOT RESULTS"
    # Exercise the actual command, without any model or media dependencies.
    f = frame_catalog(measured)[0]
    human_path = tmp_path / "test-only-synthetic-label.jsonl"
    write_jsonl(
        human_path,
        [{"clip": f["clip"], "t": f["t"], "x": 100.0, "y": 100.0, "visible": True}],
    )
    prefix = tmp_path / "score"
    subprocess.run(
        [
            sys.executable,
            str(HERE / "score_from_saved.py"),
            "--human-jsonl",
            str(human_path),
            "--extra-detections",
            f"tiny={p}",
            "--out-prefix",
            str(prefix),
        ],
        check=True,
        capture_output=True,
    )
    scored = json.loads(prefix.with_suffix(".json").read_text())
    assert scored["extra_candidates"]["tiny"]["synthetic_smoke"]
    assert any(r["candidate"] == "tiny" for r in scored["results"])
    for spec in [f"rf_full={p}", f"invalid/name={p}"]:
        with pytest.raises(ValueError):
            load_extra([spec], measured)
    for field, value in [("source_sha256", "wrong"), ("threshold", float("nan"))]:
        bad = {**data, field: value}
        p.write_text(json.dumps(bad))
        with pytest.raises(ValueError):
            load_extra([f"tiny={p}"], measured)
    cid = next(iter(data["outputs"]))
    data["outputs"][cid]["frames"].pop()
    dump(p, data)
    with pytest.raises(ValueError):
        load_extra([f"tiny={p}"], measured)
