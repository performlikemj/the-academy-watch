"""G1–G3: isolated output planning and rendering; synthetic inputs only."""

import importlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from output_guard import guard_outputs

HERE = Path(__file__).parent


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("symlink", [False, True])
def test_nested_outputs_refused_without_writes(tmp_path, reverse, symlink):
    parent = tmp_path / "real"
    parent.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(parent, target_is_directory=True)
    outer = parent / "result"
    inner = (alias if symlink else parent) / "result/copy.json"
    with pytest.raises(SystemExit, match="outputs"):
        guard_outputs(*(reversed([outer, inner]) if reverse else [outer, inner]))
    assert not outer.exists()


@pytest.mark.parametrize("exists", [False, True])
def test_output_below_input_file_refused(tmp_path, exists):
    source = tmp_path / "labels.jsonl"
    if exists:
        source.write_text("KEEP\n")
    with pytest.raises(SystemExit, match="input"):
        guard_outputs(source / "result", inputs=[source])
    assert not (source / "result").exists()


@pytest.mark.parametrize("reverse", [False, True])
def test_human_loop_nested_cli_has_no_partial_run(tmp_path, reverse):
    outer = tmp_path / "result"
    inner = outer / "copy.json"
    out, copy = (inner, outer) if reverse else (outer, inner)
    result = subprocess.run(
        [
            sys.executable,
            str(HERE / "human_loop.py"),
            "--out",
            str(out),
            "--copy-to",
            str(copy),
        ],
        env=dict(os.environ, HOME=str(tmp_path)),
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Refusing output" in result.stderr
    assert not outer.exists()
    assert not out.with_suffix(".plan.json").exists()


@pytest.mark.parametrize(
    "module,parameter",
    [
        ("review_round3", "out"),
        ("review_round4", "out"),
        ("round2_analysis", "out"),
        ("compare_ball", "out"),
        ("build_human_report", "out_prefix"),
    ],
)
def test_library_destination_required(module, parameter):
    name = (
        "update_saved"
        if module == "compare_ball"
        else "generate"
        if module == "build_human_report"
        else "capture"
    )
    fn = getattr(importlib.import_module(module), name)
    assert (
        inspect.signature(fn).parameters[parameter].default is inspect.Parameter.empty
    )


@pytest.mark.parametrize(
    "module,args,artifact",
    [
        ("inspect_n21_adjudication", [], "adjudicate-s6-s10.png"),
        ("inspect_n21_adjudication", ["--all-frames"], "adjudicate-s0-s10.png"),
        ("inspect_round5_distractor", [], "contact-sheet.png"),
    ],
)
def test_inspections_have_independent_destinations(
    tmp_path, monkeypatch, module, args, artifact
):
    import numpy as np

    m = importlib.import_module(module)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    old = tmp_path / "codex-runs/ball-r5-n21"
    old.mkdir(parents=True)
    (old / "KEEP").write_bytes(b"prior evidence")
    cid = "synthetic-n21-t3011"
    frames = [
        dict(
            t=i,
            sample_index=i,
            detections=[dict(box=[100, 100, 110, 110], xy=[105, 105], confidence=0.9)],
        )
        for i in range(11)
    ]
    labels = [dict(clip=cid, t=i, visible=False, x=None, y=None) for i in range(11)]
    (tmp_path / "codex-runs/ball-human-truth.jsonl").write_text(
        "".join(json.dumps(r) + "\n" for r in labels)
    )
    for folder in (
        "r5-yolo-low",
        "r5-rfb-low",
        "r5-rf-a-final-low",
        "r5-rf-b-final-low",
    ):
        p = tmp_path / "models/tinyball" / folder / "detections.json"
        p.parent.mkdir(parents=True)
        p.write_text(json.dumps({"outputs": {cid: {"frames": frames}}}))
    monkeypatch.setattr(m, "load_dataset", lambda *a: ({}, [dict(clip_id=cid)]))
    image = np.zeros((1080, 1920, 3), np.uint8)
    monkeypatch.setattr(m, "samples", lambda c: ((f, [image]) for f in frames))
    if module == "inspect_round5_distractor":
        monkeypatch.setattr(m, "load_measurements", lambda: {})
        monkeypatch.setattr(m, "frame_catalog", lambda data: [])
        monkeypatch.setattr(
            m, "import_labels", lambda *a: {(r["clip"], r["t"]): r for r in labels}
        )
    for name in ("one", "two"):
        out = tmp_path / name
        monkeypatch.setattr(sys, "argv", [module, "--out", str(out), *args])
        m.main()
        assert (out / artifact).is_file()
    assert (old / "KEEP").read_bytes() == b"prior evidence"
    assert list(old.iterdir()) == [old / "KEEP"]


@pytest.mark.parametrize(
    "module,option",
    [
        ("annotate_examples", "--out"),
        ("track_overlays", "--out"),
        ("n21_rule_sensitivity", "--out"),
        *[(f"check_build{v}_private", "--out") for v in range(10, 14)],
        ("score_from_saved", "--out-prefix"),
        ("compare_ball", "--out-prefix"),
        ("build_human_report", "--out-prefix"),
        ("round2_people", "--out"),
        ("run_ball", "--report-dir"),
        ("ball_truth_kit", "--out"),
        ("any_ball_review", "--output"),
        ("any_ball_review", "--kit"),
        ("any_ball_review", "--sync"),
    ],
)
def test_sweep_repeatable_cli_requires_destination(module, option):
    # Inspect parser declarations without launching models, browsers or old kits.
    import ast

    tree = ast.parse((HERE / (module + ".py")).read_text())
    calls = [
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "add_argument"
        and any(isinstance(a, ast.Constant) and a.value == option for a in n.args)
    ]
    assert len(calls) == 1
    assert any(
        k.arg == "required"
        and isinstance(k.value, ast.Constant)
        and k.value.value is True
        for k in calls[0].keywords
    )


def test_existing_input_directory_may_contain_new_outputs(tmp_path):
    source_dir = tmp_path / "source-dir"
    source_dir.mkdir()
    guard_outputs(source_dir / "new-file.json", inputs=[source_dir])
    assert not (source_dir / "new-file.json").exists()


def test_nested_input_symlink_refused(tmp_path):
    source = tmp_path / "labels.jsonl"
    source.write_text("KEEP")
    alias = tmp_path / "alias"
    alias.symlink_to(source)
    with pytest.raises(SystemExit, match="input file"):
        guard_outputs(alias / "child.json", inputs=[source])
    assert source.read_text() == "KEEP"


def test_sensitivity_writes_fresh_files(tmp_path, monkeypatch):
    import gzip
    import n21_rule_sensitivity as m
    from common import sha256

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(m, "HERE", tmp_path / "ball")
    cid = "synthetic"
    monkeypatch.setattr(m, "CID", cid)
    label_path = tmp_path / "codex-runs/ball-human-truth.jsonl"
    label_path.parent.mkdir()
    labels = [
        dict(
            clip=cid,
            t=i,
            visible=(i < 6 or i == 11),
            x=105,
            y=105,
            source_accepted=False,
        )
        for i in range(12)
    ]
    label_path.write_text("".join(json.dumps(r) + "\n" for r in labels))
    frames = [
        dict(t=i, sample_index=i, detections=[dict(xy=[105, 105], confidence=0.9)] * 2)
        for i in range(12)
    ]
    evidence = dict(
        labels_sha256=sha256(label_path),
        protocol={"split": {"held_out": [cid]}},
        models={},
    )
    for name, folder in m.DEFINITIONS.items():
        p = tmp_path / "models/tinyball" / folder / "detections.json"
        p.parent.mkdir(parents=True)
        p.write_text(
            json.dumps({"threshold": 0.01, "outputs": {cid: {"frames": frames}}})
        )
        evidence["models"][name] = dict(
            detections_sha256=sha256(p),
            operating_points={
                "1": {
                    "threshold": 0.3,
                    "held": {
                        "groups": {
                            "all": dict(
                                top1_matched=7,
                                visible=7,
                                no_ball_predictions=10,
                                no_ball_frames=5,
                            ),
                            "on_ball": {"top1_recall": 1},
                        }
                    },
                }
            },
        )
    fixture = m.HERE / "fixtures/round5_scored_output.json.gz"
    fixture.parent.mkdir(parents=True)
    fixture.write_bytes(gzip.compress(json.dumps(evidence).encode()))
    before = fixture.read_bytes()
    for name in ("one.json", "two.json"):
        monkeypatch.setattr(
            sys, "argv", ["n21_rule_sensitivity", "--out", str(tmp_path / name)]
        )
        m.main()
    assert (tmp_path / "one.json").read_bytes() == (tmp_path / "two.json").read_bytes()
    assert fixture.read_bytes() == before
    with pytest.raises(SystemExit):
        m.main()


@pytest.mark.parametrize("module", ["annotate_examples", "track_overlays"])
def test_visualization_cli_targets_own_new_directory(tmp_path, monkeypatch, module):
    m = importlib.import_module(module)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.setattr(m, "load_measurements", lambda: {})

    def generate(data, out):
        out.mkdir(parents=True)
        (out / "result.png").write_bytes(b"synthetic render")
        return []

    monkeypatch.setattr(m, "generate", generate)
    for name in ("first", "second"):
        monkeypatch.setattr(sys, "argv", [module, "--out", str(tmp_path / name)])
        m.main()
        assert (tmp_path / name / "result.png").read_bytes() == b"synthetic render"
    with pytest.raises(SystemExit):
        m.main()


def test_measurement_serializer_requires_destination():
    from compare_ball import save_measurements

    assert (
        inspect.signature(save_measurements).parameters["path"].default
        is inspect.Parameter.empty
    )


@pytest.mark.parametrize("kind", ["file", "file-symlink", "dangling-symlink", "fifo"])
def test_g4_non_directory_ancestor(tmp_path, kind):
    ancestor = tmp_path / "ancestor"
    target = tmp_path / "target"
    if kind == "file":
        ancestor.write_bytes(b"KEEP")
    elif kind == "file-symlink":
        target.write_bytes(b"KEEP")
        ancestor.symlink_to(target)
    elif kind == "dangling-symlink":
        ancestor.symlink_to(target)
    else:
        os.mkfifo(ancestor)
    with pytest.raises(SystemExit, match="ancestor"):
        guard_outputs(
            tmp_path / "other-output", ancestor / "missing/deeper/result.json"
        )
    assert not (tmp_path / "other-output").exists()
    assert not (ancestor / "missing").exists()
    if kind == "file":
        assert ancestor.read_bytes() == b"KEEP"
    elif kind == "file-symlink":
        assert target.read_bytes() == b"KEEP"
    elif kind == "dangling-symlink":
        assert ancestor.is_symlink() and not target.exists()
    else:
        assert ancestor.is_fifo()


@pytest.mark.parametrize("symlink", [False, True])
def test_g4_fresh_nested_directory_passes(tmp_path, symlink):
    parent = tmp_path / "real-directory"
    parent.mkdir()
    if symlink:
        alias = tmp_path / "alias"
        alias.symlink_to(parent, target_is_directory=True)
        parent = alias
    out = parent / "new/nested/rf_full"
    assert guard_outputs(out) == (out.resolve(),)
    assert not (parent / "new").exists()


def test_g4_runner_refuses_before_model_load(tmp_path, monkeypatch, capsys):
    from types import SimpleNamespace
    import run_ball

    report = tmp_path / "report.json"
    report.write_bytes(b"KEEP")
    calls = []
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_ball",
            "--report-dir",
            str(report),
            "--candidate",
            "rf_full",
            "--manifest",
            str(tmp_path / "manifest.json"),
            "--source",
            str(tmp_path / "source.mp4"),
        ],
    )

    def dataset(*args):
        calls.append("dataset")
        return {}, [dict(clip_id="synthetic", video=str(tmp_path / "source.mp4"))]

    def model(*args, **kwargs):
        calls.append("model")
        raise RuntimeError("stub reached: model would be loaded before mkdir")

    monkeypatch.setattr(run_ball, "load_dataset", dataset)
    monkeypatch.setattr(run_ball, "probe", lambda *a: dict(width=1920, height=1080))
    monkeypatch.setattr(run_ball, "RFDetector", model)
    monkeypatch.setitem(
        sys.modules, "cv2", SimpleNamespace(setNumThreads=lambda n: None)
    )
    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(set_num_threads=lambda n: None)
    )
    try:
        run_ball.main()
    except (SystemExit, RuntimeError):
        pass
    assert calls == [], f"work before refusal: {calls}"
    assert "ancestor" in capsys.readouterr().err
    assert report.read_bytes() == b"KEEP"
