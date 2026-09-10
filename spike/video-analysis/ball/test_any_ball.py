"""Rule A contract, queue and provisional scoring; synthetic fixtures only."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from any_ball_review import review_queue
from ball_truth_kit import import_labels
from label_rule import N21, REVIEW_TOTAL, banner_tables, migrate_row, rule_metadata
from human_score import score, markdown
from compare_ball import load_measurements
from human_loop import frame_catalog
from round5_report import saved_rule_markdown

HERE = Path(__file__).parent


@pytest.mark.parametrize("visible", [True, False])
@pytest.mark.parametrize("version", [1, 2])
def test_v1_v2_roundtrip(tmp_path, visible, version):
    frame = {"clip": "test", "t": 1.0, "sample_index": 0, "source_size": [100, 100]}
    row = {
        "clip": "test",
        "t": 1.0,
        "x": 10 if visible else None,
        "y": 20 if visible else None,
        "visible": visible,
    }
    if visible:
        row.update(source_accepted=True, accepted_source="saved", accepted_score=0.8)
    if version == 2:
        row.update(schema_version=2, match_ball=False if visible else None)
    path = tmp_path / "labels.jsonl"
    path.write_text(json.dumps(row))
    migrated = list(import_labels(path, [frame]).values())[0]
    assert (
        migrated["match_ball"] is (visible and version == 1)
        if visible
        else migrated["match_ball"] is None
    )
    out = subprocess.check_output(
        [
            "node",
            "-e",
            "const a=require(process.argv[1]);process.stdout.write(a.serialize([JSON.parse(process.argv[2])],JSON.parse(process.argv[3])))",
            str(HERE / "truth_io.js"),
            json.dumps(row),
            json.dumps([frame]),
        ],
        text=True,
    )
    assert json.loads(out) == migrated
    path.write_text(out)
    assert list(import_labels(path, [frame]).values()) == [migrated]
    if version == 1 and not visible:
        assert migrated["needs_any_ball_review"] and not migrated["review_confirmed"]
    if visible:
        assert migrated["accepted_source"] == "saved"


def test_n21_presets_and_exact_queue_order():
    frames = [{"clip": "test", "t": i / 2, "sample_index": i} for i in range(182)]
    frames += [{"clip": N21, "t": 4000 + i / 2, "sample_index": i} for i in range(6)]
    labels = {}
    for frame in frames:
        visible = frame["clip"] == N21
        row = {
            "clip": frame["clip"],
            "t": frame["t"],
            "visible": visible,
            "x": 5 if visible else None,
            "y": 5 if visible else None,
        }
        labels[(frame["clip"], frame["t"])] = migrate_row(row, frame)
    assert all(
        r["match_ball"] is False and r["needs_confirmation"]
        for r in labels.values()
        if r["visible"]
    )

    def output(scores, box=True):
        return {
            "test": {
                "frames": [
                    {
                        "t": t,
                        "detections": [
                            {
                                "confidence": s,
                                "xy": [5, 5],
                                "box": [4, 4, 6, 6] if box else None,
                            }
                        ],
                    }
                    for t, s in scores
                ]
            }
        }

    queue = review_queue(
        frames,
        labels,
        {
            "b": output([(0, 0.3), (1, 0.9), (2, 0.29)]),
            "a": output([(0, 0.8), (1, 0.9)]),
            "point": output([(2, 1)], False),
        },
    )
    assert len(queue) == REVIEW_TOTAL
    assert [(r["t"], r["suggestion"]["source"]) for r in queue if r["suggestion"]] == [
        (1, "a"),
        (0, "a"),
    ]
    assert all(r["suggestion"] is None for r in queue[2:])
    assert (
        rule_metadata(labels, "any_ball")["provisional"]
        == "PROVISIONAL: 0 of 188 review frames confirmed"
    )
    for row in labels.values():
        row.update(
            review_confirmed=True, needs_any_ball_review=False, needs_confirmation=False
        )
    assert len(review_queue(frames, labels, {})) == 188
    assert rule_metadata(labels, "any_ball")["provisional"] is None
    labels.pop(next(iter(labels)))
    assert (
        rule_metadata(labels, "any_ball")["provisional"]
        == "PROVISIONAL: 187 of 188 review frames confirmed"
    )


def test_rules_use_visibility_not_match_ball():
    m = load_measurements()
    frames = frame_catalog(m)
    labels = {
        (f["clip"], f["t"]): {"visible": True, "x": 100, "y": 100, "match_ball": False}
        for f in frames
    }
    a = score(m, labels, {}, label_rule="as_labelled")
    b = score(m, labels, {}, label_rule="any_ball")
    assert a["results"] == b["results"]
    assert b["labels"]["visible"] == len(frames)
    assert a["provisional"] is None
    report = markdown(b)
    headers = [
        line
        for line, following in zip(report.splitlines(), report.splitlines()[1:])
        if following.startswith("|---")
    ]
    assert len(headers) == 3
    assert all("PROVISIONAL: 0 of 188 review frames confirmed" in h for h in headers)
    assert "unused by detector metrics" in report
    for row in labels.values():
        row["match_ball"] = True
    assert score(m, labels, {}, label_rule="any_ball")["results"] == b["results"]
    labels[next(iter(labels))].update(visible=False, x=None, y=None, match_ball=None)
    assert score(m, labels, {}, label_rule="any_ball")["labels"]["no_ball"] == 1


def test_round5_provisional_headers():
    metadata = rule_metadata({}, "any_ball")
    report = saved_rule_markdown({**metadata, "models": {}})
    assert "| PROVISIONAL: 0 of 188 review frames confirmed" in report
    assert "unused by detector metrics" in report
    assert banner_tables("| A |\n|---|", {"provisional": None}) == "| A |\n|---|\n"


@pytest.mark.parametrize("bad_index", [0, 1, 2])
def test_throughput_mismatch_before_runtime_or_load(tmp_path, monkeypatch, bad_index):
    import throughput_round5

    home = tmp_path
    from common import sha256

    paths = []
    for i, name in enumerate(("mj-r2-b", "mj-r4-rf-b", "mj-r5-rf-a")):
        folder = home / "models/tinyball" / name
        folder.mkdir(parents=True)
        weights = folder / "weights.pt"
        weights.write_bytes(b"expected")
        (folder / "fit_summary.json").write_text(
            json.dumps({"weights_sha256": sha256(weights)})
        )
        if i == bad_index:
            weights.write_bytes(b"wrong")
        paths.append(weights)
    weights = paths[-1]
    monkeypatch.setattr(throughput_round5.Path, "home", lambda: home)
    monkeypatch.setattr(
        sys, "argv", ["throughput", "--new", str(weights), "--out", str(home / "out")]
    )
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setitem(sys.modules, "cv2", None)
    monkeypatch.setattr(
        throughput_round5, "load_model", lambda *a, **kw: pytest.fail("model loaded")
    )
    monkeypatch.setattr(
        throughput_round5, "Activity", lambda: pytest.fail("wait started")
    )
    with pytest.raises(ValueError, match="checkpoint hash mismatch"):
        throughput_round5.main()
    assert not (home / "out").exists()


def test_browser_review_contract(tmp_path):
    pytest.importorskip("playwright.sync_api")
    from urllib.parse import quote
    from ball_truth_kit import PAGE
    from check_any_ball_kit import check

    # Synthetic vector generated in memory; no source frames or private labels.
    picture = "data:image/svg+xml," + quote(
        '<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="1080"><rect width="1920" height="1080" fill="green"/></svg>'
    )
    frames = [
        {
            "clip": f"test-{i // 94}",
            "t": float(i),
            "sample_index": i % 94,
            "source_size": [1920, 1080],
            "path": picture,
        }
        for i in range(188)
    ]
    rows = [
        {
            "clip": f["clip"],
            "t": f["t"],
            "visible": False,
            "x": None,
            "y": None,
            "schema_version": 2,
            "match_ball": None,
            "review_frame": True,
            "review_confirmed": False,
            "needs_any_ball_review": True,
        }
        for f in frames
    ]
    suggestions = [
        {
            "clip": f["clip"],
            "t": f["t"],
            "x": 200,
            "y": 200,
            "score": 0.9,
            "source": "synthetic-test",
        }
        for f in frames
    ]
    queue = [
        {"clip": f["clip"], "t": f["t"], "suggestion": s}
        for f, s in zip(frames, suggestions)
    ]
    page = PAGE.replace("__IO__", (HERE / "truth_io.js").read_text())
    for key, value in {
        "FRAMES": frames,
        "LABELS": rows,
        "QUEUE": queue,
        "SUGGESTIONS": suggestions,
        "TARGETS": [],
        "KEY": "test-v1-storage",
    }.items():
        page = page.replace(f"__{key}__", json.dumps(value))
    (tmp_path / "index.html").write_text(page)
    check(tmp_path)


@pytest.mark.parametrize(
    "patch",
    [
        {"schema_version": None},
        {"schema_version": True},
        {"match_ball": 1},
        {"review_confirmed": True},
        {"needs_confirmation": "yes"},
        {"review_frame": True, "review_confirmed": True, "needs_confirmation": True},
    ],
)
def test_invalid_v2_rejected_in_both_importers(tmp_path, patch):
    frame = {"clip": "test", "t": 1.0, "source_size": [100, 100]}
    row = {
        "clip": "test",
        "t": 1.0,
        "x": 10,
        "y": 10,
        "visible": True,
        "schema_version": 2,
        "match_ball": None,
        **patch,
    }
    path = tmp_path / "bad.jsonl"
    path.write_text(json.dumps(row))
    with pytest.raises(ValueError):
        import_labels(path, [frame])
    result = subprocess.run(
        [
            "node",
            "-e",
            "require(process.argv[1]).validate(JSON.parse(process.argv[2]),JSON.parse(process.argv[3]))",
            str(HERE / "truth_io.js"),
            json.dumps(row),
            json.dumps([frame]),
        ],
        capture_output=True,
    )
    assert result.returncode != 0


def test_n21_browser_migration_matches_python():
    frames = [
        {"clip": N21, "t": float(i), "sample_index": i, "source_size": [100, 100]}
        for i in range(6)
    ]
    rows = [
        {"clip": f["clip"], "t": f["t"], "x": 10, "y": 10, "visible": True}
        for f in frames
    ]
    result = subprocess.check_output(
        [
            "node",
            "-e",
            "const a=require(process.argv[1]);process.stdout.write(a.serialize(JSON.parse(process.argv[2]),JSON.parse(process.argv[3])))",
            str(HERE / "truth_io.js"),
            json.dumps(rows),
            json.dumps(frames),
        ],
        text=True,
    )
    assert [json.loads(line) for line in result.splitlines()] == [
        migrate_row(r, f) for r, f in zip(rows, frames)
    ]
