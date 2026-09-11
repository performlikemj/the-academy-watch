"""CLI overwrite regressions: copied source, synthetic files, stubbed capture only."""

import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

HERE = Path(__file__).parent


@pytest.fixture
def copied_cli(tmp_path):
    ball = tmp_path / "copy/ball"
    ball.mkdir(parents=True)
    for path in HERE.iterdir():
        if path.suffix in {".py", ".js", ".html"}:
            shutil.copy2(path, ball / path.name)
    shutil.copytree(
        HERE.parent / "bench",
        ball.parent / "bench",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    for path in HERE.parent.glob("*.py"):
        shutil.copy2(path, ball.parent / path.name)
    home = tmp_path / "home"
    labels = home / "codex-runs/ball-human-truth.jsonl"
    labels.parent.mkdir(parents=True)
    labels.write_text("synthetic labels\n")
    models = {}
    for name, folder in {
        "yolo-r2-b": "r5-yolo-low",
        "rf-b": "r5-rfb-low",
        "rf-r5-a": "r5-rf-a-final-low",
        "rf-r5-b": "r5-rf-b-final-low",
    }.items():
        path = home / "models/tinyball" / folder / "detections.json"
        path.parent.mkdir(parents=True)
        path.write_text(name)
        models[name] = {
            "detections_sha256": hashlib.sha256(path.read_bytes()).hexdigest()
        }
    fixture = ball / "fixtures/round5_scored_output.json.gz"
    shutil.copytree(HERE / "fixtures", fixture.parent)
    fixture.write_bytes(
        gzip.compress(
            json.dumps(
                {
                    "labels_sha256": hashlib.sha256(labels.read_bytes()).hexdigest(),
                    "models": models,
                }
            ).encode()
        )
    )
    return ball, home, labels, fixture


def run_cli(copied_cli, args):
    ball, home, _, _ = copied_cli
    driver = """
import json,sys
from pathlib import Path
home=Path(sys.argv[1])
Path.home=classmethod(lambda cls:home)
import review_round5 as r
from common import sha256
calls=[]
def fake(paths,root=None,label_path=None,label_rule='as_labelled'):
    calls.append(sorted(paths))
    return {'labels_sha256':sha256(label_path),'provisional':None,'models':{k:{'detections_sha256':sha256(v) if v.exists() else 'rogue','operating_points':{}} for k,v in paths.items()}}
r.capture=fake
sys.argv=['review_round5.py']+json.loads(sys.argv[2])
try:r.main();code=0
except SystemExit as e:code=e.code
print(json.dumps({'code':code,'capture_calls':calls}))
"""
    result = subprocess.run(
        [sys.executable, "-c", driver, str(home), json.dumps([str(a) for a in args])],
        cwd=ball,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout.splitlines()[-1])


@pytest.mark.parametrize(
    "case",
    [
        "rogue",
        "fixture",
        "explicit_label",
        "default_label",
        "symlink",
        "dotdot",
        "existing",
        "protected_new",
        "fixture_new",
        "swapped",
    ],
)
def test_refuses_before_capture_and_preserves_files(copied_cli, case):
    ball, home, labels, fixture = copied_cli
    out = ball / "fresh.json"
    args = ["--human-jsonl", labels]
    if case == "rogue":
        args += ["--freeze", "--extra", "rogue=/missing.json"]
    elif case == "fixture":
        out = fixture
    elif case in {"explicit_label", "default_label"}:
        out = labels
        if case == "default_label":
            args = []
    elif case == "symlink":
        out.symlink_to(labels)
    elif case == "dotdot":
        directory = labels.parent / "empty"
        directory.mkdir()
        out = directory / ".." / labels.name
    elif case == "existing":
        out.write_text("KEEP\n")
    elif case == "protected_new":
        out = labels.with_name("ball-human-truth-never-created.jsonl")
    elif case == "fixture_new":
        out = fixture.parent / "never-created.json"
    elif case == "swapped":
        (home / "models/tinyball/r5-yolo-low/detections.json").write_text("swapped")
        args += ["--freeze"]
    before = {
        p: p.read_bytes()
        for p in ball.rglob("*")
        if p.is_file() and "__pycache__" not in str(p)
    }
    before[labels] = labels.read_bytes()
    result = run_cli(copied_cli, [*args, "--out", out])
    assert result["code"] != 0
    assert not result["capture_calls"]
    assert all(p.read_bytes() == content for p, content in before.items())
    if out not in before and not out.is_symlink() and case != "dotdot":
        assert not out.exists()


def test_legitimate_new_output_still_works(copied_cli):
    ball, _, labels, fixture = copied_cli
    before = fixture.read_bytes()
    out = ball / "new/result.json"
    result = run_cli(copied_cli, ["--out", out, "--human-jsonl", labels])
    assert result["code"] == 0 and len(result["capture_calls"]) == 1
    assert json.loads(out.read_text())["labels_sha256"]
    assert fixture.read_bytes() == before


def test_freeze_records_exact_inputs_in_new_artifact(copied_cli):
    ball, _, labels, fixture = copied_cli
    original = fixture.read_bytes()
    out = ball / "new/frozen.json.gz"
    result = run_cli(copied_cli, ["--out", out, "--human-jsonl", labels, "--freeze"])
    assert result["code"] == 0
    assert fixture.read_bytes() == original
    assert set(json.loads(gzip.decompress(out.read_bytes()))["models"]) == set(
        json.loads(gzip.decompress(original))["models"]
    )


@pytest.mark.parametrize(
    "kind",
    [
        "existing_file",
        "existing_directory",
        "fixture_new",
        "fixture_symlink",
        "fixture_dotdot",
        "input_missing",
        "input_symlink",
        "protected_new",
        "protected_parent_symlink",
        "duplicate_outputs",
        "dangling_symlink",
    ],
)
def test_shared_guard_resolves_paths_before_any_write(tmp_path, monkeypatch, kind):
    import output_guard

    monkeypatch.setattr(output_guard, "HERE", tmp_path / "ball")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    fixtures = tmp_path / "ball/fixtures"
    fixtures.mkdir(parents=True)
    labels_dir = tmp_path / "home/codex-runs"
    labels_dir.mkdir(parents=True)
    source = tmp_path / "unread-input.jsonl"
    out = tmp_path / "new.json"
    outputs = [out]
    if kind == "existing_file":
        out.write_text("KEEP")
    elif kind == "existing_directory":
        out.mkdir()
    elif kind == "fixture_new":
        outputs = [fixtures / "new.json"]
    elif kind == "fixture_symlink":
        (tmp_path / "alias").symlink_to(fixtures, target_is_directory=True)
        outputs = [tmp_path / "alias/new.json"]
    elif kind == "fixture_dotdot":
        (fixtures / "child").mkdir()
        outputs = [fixtures / "child/../new.json"]
    elif kind == "input_missing":
        outputs = [source]
    elif kind == "input_symlink":
        source.symlink_to(out)
    elif kind == "protected_new":
        outputs = [labels_dir / "ball-human-truth-future.jsonl"]
    elif kind == "protected_parent_symlink":
        (tmp_path / "alias").symlink_to(labels_dir, target_is_directory=True)
        outputs = [tmp_path / "alias/ball-human-truth-future.jsonl"]
    elif kind == "duplicate_outputs":
        outputs += [out]
    elif kind == "dangling_symlink":
        out.symlink_to(tmp_path / "missing")
    before = {p: p.read_bytes() for p in tmp_path.rglob("*") if p.is_file()}
    with pytest.raises(SystemExit):
        output_guard.guard_outputs(*outputs, inputs=[source])
    assert all(p.read_bytes() == content for p, content in before.items())
    assert not (fixtures / "new.json").exists()


@pytest.mark.parametrize(
    "script,option",
    [
        ("score_from_saved", "--out-prefix"),
        ("human_score", "--out-prefix"),
        ("compare_ball", "--out-prefix"),
        ("build_human_report", "--out-prefix"),
        ("round5_report", "--out-prefix"),
        ("human_loop", "--out"),
        ("ball_truth_kit", "--out"),
        ("throughput_round5", "--out"),
        ("round5_inference", "--out"),
        ("round2_people", "--out"),
        ("smoke_tiny_ball", "--out"),
        ("check_build10_private", "--out"),
        ("check_build11_private", "--out"),
        ("check_build12_private", "--out"),
        ("check_build13_private", "--out"),
        ("check_build14_private", "--out"),
        ("train_tiny_ball", "--out"),
        ("train_tiny_ball_rfdetr", "--out"),
        ("train_round5", "--out"),
    ],
)
def test_other_clis_refuse_before_loading_inputs(tmp_path, script, option):
    # Missing inputs make proceeding past the guard fail for a different reason.
    # No model/capture function may run. All output victims are temporary.
    out = tmp_path / "victim.json"
    out.write_text("KEEP\n")
    target = out.with_suffix("") if option == "--out-prefix" else out
    args = [sys.executable, str(HERE / (script + ".py")), option, str(target)]
    if script in {
        "score_from_saved",
        "human_score",
        "round5_report",
        "train_tiny_ball",
        "train_tiny_ball_rfdetr",
    }:
        args += ["--human-jsonl", str(tmp_path / "MISSING.jsonl")]
    if script == "throughput_round5":
        args += ["--new", str(tmp_path / "MISSING.pt")]
    if script == "round5_inference":
        args += ["--model", str(tmp_path / "MISSING.pt")]
    result = subprocess.run(args, text=True, capture_output=True)
    assert result.returncode != 0
    assert "Refusing output" in result.stderr, result.stderr
    assert out.read_text() == "KEEP\n"


def test_later_output_collision_blocks_report_capture(tmp_path, monkeypatch):
    import score_from_saved

    prefix = tmp_path / "report"
    prefix.with_suffix(".md").write_text("KEEP")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "score",
            "--out-prefix",
            str(prefix),
            "--human-jsonl",
            str(tmp_path / "missing.jsonl"),
        ],
    )
    monkeypatch.setattr(
        score_from_saved,
        "load_measurements",
        lambda *a: pytest.fail("capture before output preflight"),
    )
    with pytest.raises(SystemExit):
        score_from_saved.main()
    assert not prefix.with_suffix(".json").exists()
    assert prefix.with_suffix(".md").read_text() == "KEEP"


def test_audit_lists_every_cli_and_its_guard():
    import ast
    import re

    actual = {
        p.name
        for p in HERE.glob("*.py")
        if any(
            isinstance(n, ast.If) and "__main__" in ast.unparse(n.test)
            for n in ast.parse(p.read_text()).body
        )
    }
    audit = (HERE / "CLI_WRITE_AUDIT.md").read_text()
    listed = set(re.findall(r"\| `([^`]+\.py)` \|", audit))
    assert listed == actual
    exceptions = {
        "compare_label_exports.py",
        "any_ball_review.py",
        "human_score.py",
        "run_round3.py",
        "train_tiny_ball.py",
        "train_tiny_ball_rfdetr.py",
        "train_round5.py",
    }
    for name in actual - exceptions:
        assert "guard_outputs(" in (HERE / name).read_text(), name


def test_frozen_cli_preflight_preserves_source_and_checks_cache(
    tmp_path, monkeypatch, capsys
):
    import output_guard

    monkeypatch.setattr(output_guard, "HERE", tmp_path / "ball")
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    fixtures = tmp_path / "ball/fixtures"
    fixtures.mkdir(parents=True)
    (home / "models").mkdir(parents=True)
    (home / "models/tinyball").symlink_to(fixtures, target_is_directory=True)
    monkeypatch.setattr(
        sys,
        "argv",
        [str(tmp_path / "ball/train_tiny_ball.py"), "--out", str(tmp_path / "new-fit")],
    )
    with pytest.raises(SystemExit) as error:
        output_guard.guard_frozen_entrypoint()
    assert error.value.code == 2
    assert "fixture paths are read-only" in capsys.readouterr().err
    assert not (fixtures / "yolo11n.pt").exists()


def test_quoted_tilde_is_resolved_like_the_actual_writer(tmp_path, monkeypatch):
    import output_guard

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(output_guard, "HERE", tmp_path / "ball")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    fixture = tmp_path / "ball/fixtures"
    fixture.mkdir(parents=True)
    (tmp_path / "~").symlink_to(fixture, target_is_directory=True)
    with pytest.raises(SystemExit, match="fixture paths are read-only"):
        output_guard.guard_outputs(Path("~/new.json"))
    assert not (fixture / "new.json").exists()


@pytest.mark.parametrize("option", ["--split-json", "--manifest", "--source", "--init"])
def test_frozen_cli_protects_every_jsonl_input_even_if_missing(
    tmp_path, monkeypatch, option
):
    import output_guard

    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    target = tmp_path / "missing-input.jsonl"
    monkeypatch.setattr(
        sys,
        "argv",
        [str(HERE / "train_tiny_ball.py"), "--out", str(target), option, str(target)],
    )
    with pytest.raises(SystemExit):
        output_guard.guard_frozen_entrypoint()
    assert not target.exists()
