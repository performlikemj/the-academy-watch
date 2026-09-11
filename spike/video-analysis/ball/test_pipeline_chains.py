"""Stage-boundary tests: real orchestration, guards and writers, stub computation.

All artifacts are synthetic in tmp_path. Trainer export statements are executed
from the frozen trainer AST, so the stub cannot hide a trainer-created file.
"""

import ast
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from common import dump, sha256

HERE = Path(__file__).parent


def trainer_export(out, fit):
    """Execute the actual trainer's final fit/metrics writes, without training."""
    tree = ast.parse((HERE / "train_round5.py").read_text())
    main = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main"
    )
    exports = [
        n
        for n in main.body
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id == "dump"
        and any(
            isinstance(v, ast.Constant)
            and v.value in {"fit_summary.json", "metrics.json"}
            for v in ast.walk(n)
        )
    ]
    assert len(exports) == 2
    exec(
        compile(ast.Module(body=exports, type_ignores=[]), "trainer-export", "exec"),
        {"dump": dump, "a": SimpleNamespace(out=out), "fit": fit},
    )


@pytest.fixture
def sandbox(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    root = tmp_path / "models/tinyball"
    root.mkdir(parents=True)
    labels = tmp_path / "codex-runs/ball-human-truth.jsonl"
    dump(labels, {})
    return root, labels


def test_train_finish_review_report_chain(sandbox, tmp_path, monkeypatch):
    import finish_round5 as finish
    import review_round5 as review
    import round5_inference as inference
    from checkpoint_provenance import FIT_DIRECTORIES, FINAL_PASSES

    root, labels = sandbox
    protocol = json.loads((HERE / "fixtures/round5_execution.json").read_text())
    evidence = {
        "labels_sha256": sha256(labels),
        "protocol": protocol,
        "evaluation_label": "synthetic",
        "label_rule": "as_labelled",
        "match_ball_note": "unused",
        "selection_rule": "synthetic",
        "best_rf_final_selected": "rf-r5-a",
        "models": {},
        "provisional": None,
    }
    for name, folder in FIT_DIRECTORIES.items():
        out = root / folder
        out.mkdir()
        (out / "weights.pt").write_bytes(b"stub weights")
        fit = {
            "weights_sha256": sha256(out / "weights.pt"),
            "labels_sha256": sha256(labels),
            "checkpoints": [],
            "protocol_sha256": sha256(HERE / "fixtures/round5_execution.json"),
        }
        trainer_export(out, fit)
        dump(out / "dataset.json", {"labels_sha256": sha256(labels)})
        dump(
            root / FINAL_PASSES[name] / "detections.json",
            {"weights_sha256": fit["weights_sha256"], "outputs": {}},
        )
        group = {
            "on_ball": {"top1_recall": 0.5},
            "all": {"false_per_10s": 1, "visible": 1, "no_ball_frames": 0},
        }
        evidence["models"][name] = {
            "saved_pass_provenance": {"weights_sha256": fit["weights_sha256"]},
            "operating_points": {
                "1": {
                    "threshold": 0.3,
                    "train": {"groups": group},
                    "held": {"groups": group},
                    "mcnemar_vs_yolo": {},
                }
            },
        }
    inference.evaluation_marker(root)
    originals = {p: p.read_bytes() for p in root.glob("mj-*/metrics.json")}
    monkeypatch.setattr(finish, "capture", lambda paths: deepcopy(evidence))
    monkeypatch.setattr(finish, "load_measurements", lambda: {})
    monkeypatch.setattr(finish, "frame_catalog", lambda m: [])
    monkeypatch.setattr(finish, "import_labels", lambda *a: {})
    finish.main()
    assert all(p.read_bytes() == raw for p, raw in originals.items())
    for letter in "ab":
        scored = root / f"mj-r5-rf-{letter}/metrics-scored.json"
        assert (
            json.loads(scored.read_text())["fair_protocol"]
            == evidence["models"][f"rf-r5-{letter}"]
        )
    assert (root / "round5-evidence.json").is_file()
    assert (root / "round5-kit-suggestions.jsonl").is_file()
    monkeypatch.setattr(review, "capture", lambda *a, **k: deepcopy(evidence))
    import sys

    monkeypatch.setattr(
        sys, "argv", ["review_round5.py", "--out", str(tmp_path / "review.json")]
    )
    review.main()
    assert (
        json.loads((tmp_path / "review.json").read_text())["models"]
        == evidence["models"]
    )

    import round5_report

    invoke(
        monkeypatch,
        round5_report,
        "--human-jsonl",
        labels,
        "--out-prefix",
        tmp_path / "report",
    )
    assert (
        json.loads((tmp_path / "report.json").read_text())["models"]
        == evidence["models"]
    )
    assert "Round 5 saved scoring" in (tmp_path / "report.md").read_text()
    with pytest.raises(SystemExit):
        finish.main()


def invoke(monkeypatch, module, *args):
    import sys

    monkeypatch.setattr(
        sys, "argv", [str(HERE / (module.__name__ + ".py")), *map(str, args)]
    )
    module.main()


@pytest.fixture
def runtime_stubs(monkeypatch):
    """Never import model runtimes or touch hardware in stage-boundary tests."""
    import sys

    monkeypatch.setitem(
        sys.modules,
        "torch",
        SimpleNamespace(
            set_num_threads=lambda n: None,
            mps=SimpleNamespace(empty_cache=lambda: None),
        ),
    )
    monkeypatch.setitem(
        sys.modules, "cv2", SimpleNamespace(setNumThreads=lambda n: None)
    )
    monkeypatch.setitem(
        sys.modules, "ultralytics", SimpleNamespace(YOLO=lambda path: path)
    )
    monkeypatch.setitem(
        sys.modules, "rfdetr", SimpleNamespace(RFDETRNano=lambda **kwargs: kwargs)
    )


def stub_fit(out, labels, resolution=960):
    from output_guard import guard_outputs

    guard_outputs(out, inputs=[labels])
    out.mkdir(parents=True)
    (out / "weights.pt").write_bytes(b"stub checkpoint")
    fit = dict(
        weights_sha256=sha256(out / "weights.pt"),
        labels_sha256=sha256(labels),
        split={"train": ["synthetic"], "held_out": []},
        model_input_px=resolution,
        resolution=resolution,
        training_s=1,
        best_train_loss=1,
        checkpoints=[],
        licence="synthetic",
        licence_url="synthetic",
        protocol_sha256=sha256(HERE / "fixtures/round5_execution.json"),
    )
    trainer_export(out, fit)
    dump(out / "dataset.json", {"labels_sha256": sha256(labels)})
    return fit


def stub_prediction(model, clips, out, *args):
    # Prediction computation is stubbed, but its caller's guard and subsequent
    # provenance enrichment execute normally (including repeat writes within run).
    dump(out / "detections.json", {"outputs": {}})
    (out / "suggestions.jsonl").write_text("")
    return {}, 0


def capture_writer_stub(module, root, labels, out, folders):
    """Run actual capture export statements with synthetic numeric results.

    This keeps destinations under test while bypassing historical scoring and
    private inputs. It would detect writes back to a trainer's metrics file.
    """
    from review_round3 import freeze

    out.mkdir(parents=True)
    tree = ast.parse(Path(module.__file__).read_text())
    capture = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "capture"
    )
    calls = [
        n
        for n in ast.walk(capture)
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id in {"dump", "freeze"}
    ]
    results = [{"candidate": name} for name in folders]
    for name, folder in folders.items():
        directory = root / folder
        saved = json.loads((directory / "detections.json").read_text())
        fit = json.loads((directory / "fit_summary.json").read_text())
        assert saved["weights_sha256"] == fit["weights_sha256"]
        env = dict(
            module.__dict__,
            out=out,
            destination=out,
            root=root,
            dump=dump,
            freeze=freeze,
            directory=directory,
            model_dirs=folders,
            name=name,
            fit=fit,
            row={},
            paired={},
            evidence={},
            e={},
            r1={},
            r2={},
            results=results,
            letter=folder[-1],
            selection={"fits": {folder[-1]: fit}},
            errors={name: {}},
            sensitivity={name: {}},
        )
        for call in calls:
            exec(
                compile(
                    ast.Module(body=[call], type_ignores=[]), "capture-export", "exec"
                ),
                env,
            )
    # round2's gzip output is an attribute-call write, unlike freeze().
    if module.__name__ == "round2_analysis":
        calls = [
            n
            for n in ast.walk(capture)
            if isinstance(n, ast.Expr)
            and isinstance(n.value, ast.Call)
            and isinstance(n.value.func, ast.Attribute)
            and n.value.func.attr == "write_bytes"
        ]
        env["payload"] = "{}\n"
        for call in calls:
            exec(
                compile(
                    ast.Module(body=[call], type_ignores=[]), "capture-export", "exec"
                ),
                env,
            )


@pytest.mark.parametrize("round_number", [2, 3, 4], ids=["round2", "round3", "round4"])
def test_historical_fit_evaluate_review_chain(
    sandbox, tmp_path, monkeypatch, runtime_stubs, round_number
):
    import importlib
    import subprocess

    run = importlib.import_module(f"run_round{round_number}")
    evaluate = importlib.import_module(f"evaluate_round{round_number}")
    review = importlib.import_module(
        "round2_analysis" if round_number == 2 else f"review_round{round_number}"
    )
    root, labels = sandbox
    letters = "abcd" if round_number == 2 else "ab"

    def train(cmd, **kwargs):
        out = Path(cmd[cmd.index("--out") + 1])
        stub_fit(out, labels)

    monkeypatch.setattr(subprocess, "run", train)
    invoke(monkeypatch, run)
    originals = {p: p.read_bytes() for p in root.glob("mj-*/metrics.json")}
    monkeypatch.setattr(
        evaluate, "load_measurements", lambda: {"frozen_set_id": "synthetic"}
    )
    monkeypatch.setattr(evaluate, "load_dataset", lambda *a: ({}, []))
    monkeypatch.setattr(evaluate, "predict_all", stub_prediction)
    # RF writes provenance inside predict_all; YOLO adds it after predict_all.
    if round_number == 4:

        def rf_predict(model, clips, out, frozen_set_id, fit):
            stub_prediction(model, clips, out)
            dump(
                out / "detections.json",
                {"outputs": {}, "weights_sha256": fit["weights_sha256"]},
            )

        monkeypatch.setattr(evaluate, "predict_all", rf_predict)
    invoke(monkeypatch, evaluate)
    if round_number == 2:
        import round2_people

        monkeypatch.setattr(round2_people, "load_dataset", lambda *a: ({}, []))
        source = root / "synthetic.mp4"
        source.write_bytes(b"stub source")
        (root / "yolo11n.pt").write_bytes(b"stub person checkpoint")
        monkeypatch.setattr(round2_people, "DEFAULT_SOURCE", source)
        invoke(monkeypatch, round2_people, "--out", root / "round2-people.json")
        assert (root / "round2-people.json").is_file()
    marker = root / f"round{round_number}-evaluation-start.json"
    marker_bytes = marker.read_bytes()
    # The evaluation stage must preserve its marker and saved passes on rerun.
    with pytest.raises(SystemExit):
        invoke(monkeypatch, evaluate)
    assert marker.read_bytes() == marker_bytes
    folders = {
        f"tinyball-r{round_number}-"
        + ("rf-" if round_number == 4 else "")
        + c: f"mj-r{round_number}-" + ("rf-" if round_number == 4 else "") + c
        for c in letters
    }
    out = tmp_path / "review"
    monkeypatch.setattr(
        review,
        "capture",
        lambda root, labels, *a, out=None: capture_writer_stub(
            review, root, labels, out, folders
        ),
    )
    invoke(monkeypatch, review, "--out", out)
    assert all(p.read_bytes() == raw for p, raw in originals.items())
    assert len(list(out.glob("*metrics-scored.json"))) == len(letters)
    assert (out / f"round{round_number}-evidence.json").is_file()
    assert len(list(out.glob("*.gz"))) >= 1
    with pytest.raises(SystemExit):
        invoke(monkeypatch, review, "--out", out)


def test_run_round5_marker_and_pass_chain(sandbox, monkeypatch, runtime_stubs):
    import subprocess
    import run_round5 as run
    import round5_inference as inference

    root, labels = sandbox
    stub_fit(root / "mj-r5-rf-a", labels)
    events = []

    def dispatch(cmd, **kwargs):
        if Path(cmd[1]).name == "train_round5.py":
            stub_fit(Path(cmd[cmd.index("--out") + 1]), labels)
            events.append("train-b")
        else:
            invoke(monkeypatch, inference, *cmd[2:])
            events.append("pass")

    monkeypatch.setattr(subprocess, "run", dispatch)
    monkeypatch.setattr(inference, "load_model", lambda *a: None)
    monkeypatch.setattr(
        inference, "load_measurements", lambda: {"frozen_set_id": "synthetic"}
    )
    monkeypatch.setattr(inference, "load_dataset", lambda *a: ({}, []))

    def predict(model, clips, out, frozen_set_id, fit, digest):
        assert (root / "round5-evaluation-start.json").exists()
        dump(out / "detections.json", {"weights_sha256": digest, "outputs": {}})
        (out / "suggestions.jsonl").write_text("")

    monkeypatch.setattr(inference, "predict_all", predict)
    invoke(monkeypatch, run, "--first-pid", 1)
    assert events == ["train-b", "pass", "pass"]
    marker = (root / "round5-evaluation-start.json").read_bytes()
    inference.evaluation_marker(root)
    assert (root / "round5-evaluation-start.json").read_bytes() == marker
    with pytest.raises(SystemExit):
        invoke(monkeypatch, run, "--first-pid", 1)


def test_smoke_train_saved_score_chain(sandbox, tmp_path, monkeypatch):
    import subprocess
    import smoke_tiny_ball as smoke
    import score_from_saved as score

    root, _ = sandbox
    measurements = {
        "clips": [{"clip_id": "synthetic"}],
        "outputs": {
            n: {"synthetic": {"frames": [{"t": 0, "detections": []}]}}
            for n in ("rf_full", "rf_2x2")
        },
    }
    monkeypatch.setattr(smoke, "load_measurements", lambda: measurements)
    monkeypatch.setattr(smoke, "clip_class", lambda c: "on_ball")

    def train(cmd, **kwargs):
        labels = Path(cmd[cmd.index("--human-jsonl") + 1])
        out = Path(cmd[cmd.index("--out") + 1])
        assert json.loads(labels.read_text())["visible"] is False
        assert "--synthetic-smoke" in cmd
        stub_fit(out, labels)
        stub_prediction(None, [], out)

    monkeypatch.setattr(subprocess, "run", train)
    out = root / "smoke"
    invoke(monkeypatch, smoke, "--out", out)
    labels = out.with_name("smoke-SYNTHETIC-labels.jsonl")
    monkeypatch.setattr(score, "load_measurements", lambda *a: measurements)
    monkeypatch.setattr(score, "frame_catalog", lambda m: [])
    monkeypatch.setattr(score, "import_labels", lambda *a: {})

    def extra(specs, m, allow_synthetic):
        assert allow_synthetic
        assert Path(specs[0].split("=", 1)[1]).is_file()
        return {}

    monkeypatch.setattr(score, "load_extra", extra)
    monkeypatch.setattr(
        score,
        "score",
        lambda *a: dict(
            labels={}, results=[], match_ball_note="SYNTHETIC", provisional=None
        ),
    )
    monkeypatch.setattr(score, "markdown", lambda d: "SYNTHETIC\n")
    invoke(
        monkeypatch,
        score,
        "--human-jsonl",
        labels,
        "--extra-detections",
        f"smoke={out}/detections.json",
        "--allow-synthetic",
        "--out-prefix",
        tmp_path / "scores",
    )
    assert (tmp_path / "scores.md").read_text() == "SYNTHETIC\n"


def test_suggestions_kit_refresh_chain(tmp_path, monkeypatch):
    import runpy
    import sys
    import compare_ball
    import human_loop
    import ball_truth_kit as kit

    frames = [
        {
            "clip": "synthetic",
            "t": 0,
            "sample_index": 0,
            "frame_index": 0,
            "source_size": [10, 10],
            "class": "on_ball",
            "path": "frame.jpg",
        }
    ]
    measurements = {"frozen_set_id": "synthetic"}
    monkeypatch.setattr(compare_ball, "load_measurements", lambda: measurements)
    monkeypatch.setattr(human_loop, "frame_catalog", lambda m: frames)
    monkeypatch.setattr(
        human_loop, "review_plan", lambda f: {"on_ball": [], "off_pitch": []}
    )
    shared = tmp_path / "frames"
    shared.mkdir()
    (shared / "frame.jpg").write_bytes(b"synthetic shared frame placeholder")
    dump(shared / "frames.json", frames)
    source = tmp_path / "source.mp4"
    dump(shared / "build.json", {"frozen_set_id": "synthetic", "source": str(source)})
    kit.build(source, tmp_path / "first-build14", frames_dir=shared)
    # CLI module execution retains its real writers; only saved numeric loading
    # is replaced. Empty detections are a supported suggestion result.
    m = {"clips": [], "frozen_set_id": "synthetic", "outputs": {}}
    monkeypatch.setattr(compare_ball, "load_measurements", lambda: m)

    # review_plan is module-local under runpy: enough synthetic off-pitch frames.
    def patched_run(path):
        tree = ast.parse(path.read_text())
        block = next(
            n
            for n in tree.body
            if isinstance(n, ast.If) and "__name__" in ast.unparse(n.test)
        )
        env = dict(human_loop.__dict__, __name__="__main__")
        exec(
            compile(ast.Module(body=block.body, type_ignores=[]), str(path), "exec"),
            env,
        )

    suggestions = tmp_path / "suggestions.jsonl"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "human_loop.py",
            "--out",
            str(suggestions),
            "--copy-to",
            str(tmp_path / "copy.jsonl"),
        ],
    )
    patched_run(HERE / "human_loop.py")
    assert suggestions.read_bytes() == (tmp_path / "copy.jsonl").read_bytes() == b""
    monkeypatch.setattr(compare_ball, "load_measurements", lambda: measurements)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ball_truth_kit.py",
            "--out",
            str(tmp_path / "second-build14"),
            "--source",
            str(source),
            "--frames-dir",
            str(shared),
            "--suggestions",
            str(suggestions),
        ],
    )
    runpy.run_path(str(HERE / "ball_truth_kit.py"), run_name="__main__")
    assert (
        json.loads((tmp_path / "second-build14/build.json").read_text())["suggestions"]
        == 0
    )
    assert (tmp_path / "first-build14/index.html").is_file()
    assert (shared / "frame.jpg").read_bytes() == b"synthetic shared frame placeholder"


def test_saved_update_compare_chain(tmp_path, monkeypatch):
    import compare_ball as compare

    measurements = tmp_path / "input.gz"
    compare.save_measurements(
        {"clips": [], "frozen_set_id": "synthetic", "runs": {}, "outputs": {}},
        measurements,
    )
    before = measurements.read_bytes()
    report = tmp_path / "runner"
    dump(report / "wasb_2x2/run.json", {"frozen_set_id": "synthetic", "clips": []})
    execution = tmp_path / "execution.json"
    dump(execution, {})
    monkeypatch.setattr(compare, "retrack_saved", lambda m: {})
    monkeypatch.setattr(compare, "label_plan", lambda m: {})
    monkeypatch.setattr(
        compare, "compare", lambda m, *a: {"headline": "synthetic", "runs": m["runs"]}
    )
    monkeypatch.setattr(compare, "markdown", lambda data: data["headline"])
    invoke(
        monkeypatch,
        compare,
        "--update-saved",
        "--measurements",
        measurements,
        "--measurements-out",
        tmp_path / "updated.gz",
        "--report-dir",
        report,
        "--execution",
        execution,
        "--out-prefix",
        tmp_path / "comparison",
    )
    assert measurements.read_bytes() == before
    assert "wasb_2x2" in json.loads((tmp_path / "comparison.json").read_text())["runs"]
    invoke(
        monkeypatch,
        compare,
        "--measurements",
        tmp_path / "updated.gz",
        "--execution",
        execution,
        "--out-prefix",
        tmp_path / "second",
    )
    assert (tmp_path / "comparison.json").read_bytes() == (
        tmp_path / "second.json"
    ).read_bytes()


def test_capture_report_and_freeze_bundle_chain(sandbox, tmp_path, monkeypatch):
    import gzip
    import build_human_report as report
    import freeze_round5 as freeze

    root, _ = sandbox
    captured = tmp_path / "captured.json"
    captured.write_bytes(
        gzip.decompress((HERE / "fixtures/human_measurements.json.gz").read_bytes())
    )
    invoke(
        monkeypatch,
        report,
        "--capture",
        captured,
        "--capture-out",
        tmp_path / "capture.gz",
        "--out-prefix",
        tmp_path / "human",
    )
    assert (
        gzip.decompress((tmp_path / "capture.gz").read_bytes()) == captured.read_bytes()
    )
    evidence = json.loads(
        gzip.decompress((HERE / "fixtures/round5_scored_output.json.gz").read_bytes())
    )
    dump(root / "round5-evidence.json", evidence)
    dump(root / "round5-throughput.json", evidence["throughput"])
    # Historical build metadata is aggregate-only fixture data, staged in tmp.
    kit = evidence["kit"]
    build = dict(
        kit["build"],
        build_version=8,
        confirmed_seed_labels=1057,
        suggestions_by_source={kit["source"]: kit["suggestions"]},
    )
    dump(tmp_path / "ball-truth-review/build.json", build)
    (tmp_path / "ball-truth-review/index.html").write_text("synthetic page")
    (tmp_path / "codex-runs/ball-r5-kit-check.log").write_text("stub browser check")
    bundle = tmp_path / "bundle"
    invoke(monkeypatch, freeze, "--out", bundle)
    invoke(
        monkeypatch,
        report,
        "--fixtures",
        bundle,
        "--out-prefix",
        tmp_path / "regenerated",
    )
    for suffix in (".md", ".json"):
        assert (bundle / ("human" + suffix)).read_bytes() == (
            tmp_path / ("regenerated" + suffix)
        ).read_bytes()
    with pytest.raises(SystemExit):
        invoke(monkeypatch, freeze, "--out", bundle)


@pytest.mark.parametrize("script", ["human_loop.py", "check_build14_private.py"])
def test_repeat_run_requires_explicit_destination(tmp_path, script):
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, str(HERE / script)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "--out" in result.stderr


def test_proxy_ledger_regenerates_byte_identical(tmp_path, monkeypatch):
    import compare_ball

    invoke(monkeypatch, compare_ball, "--out-prefix", tmp_path / "proxy")
    ledger = HERE.parents[2] / "ledgers/research/evidence-bench-2026-09-10-ball-detect"
    for suffix in (".md", ".json"):
        assert (tmp_path / ("proxy" + suffix)).read_bytes() == ledger.with_suffix(
            suffix
        ).read_bytes()
