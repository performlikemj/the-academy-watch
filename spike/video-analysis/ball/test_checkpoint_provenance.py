"""Wrong weights must fail before runtime loading, scoring or artifact writes."""

import json
import gzip
import sys
from types import SimpleNamespace

import pytest

from checkpoint_provenance import (
    FIT_DIRECTORIES,
    audit_saved_passes,
    declared_passes,
    validate_model,
    validate_saved_passes,
)
from common import HERE, sha256
import finish_round5
import review_round5
import round5_inference


PASS_IDS = list(FIT_DIRECTORIES) + [f"rf-r5-{c} / epoch-2" for c in "ab"]


@pytest.fixture
def saved(tmp_path):
    root = tmp_path / "models/tinyball"
    for candidate, directory in FIT_DIRECTORIES.items():
        folder = root / directory
        folder.mkdir(parents=True)
        (folder / "weights.pt").write_bytes(candidate.encode())
        fit = {"weights_sha256": sha256(folder / "weights.pt")}
        if candidate.startswith("rf-r5-"):
            weights = folder / "epoch-02.pt"
            weights.write_bytes(f"{candidate} diagnostic".encode())
            fit["checkpoints"] = [
                {"epoch": 2, "path": str(weights), "sha256": sha256(weights)}
            ]
        (folder / "fit_summary.json").write_text(json.dumps(fit))
    paths = declared_passes(root)
    for name, path in paths.items():
        candidate = name.split(" / ")[0]
        filename = "epoch-02.pt" if "epoch" in name else "weights.pt"
        path.parent.mkdir()
        path.write_text(
            json.dumps(
                {"weights_sha256": sha256(root / FIT_DIRECTORIES[candidate] / filename)}
            )
        )
    return root, paths


@pytest.mark.parametrize("name", PASS_IDS)
def test_wrong_cli_weights_fail_before_model_or_runtime_load(saved, name, monkeypatch):
    root, _ = saved
    directory = root / FIT_DIRECTORIES[name.split(" / ")[0]]
    weights = directory / ("epoch-02.pt" if "epoch" in name else "weights.pt")
    epoch = 2 if "epoch" in name else None
    _, expected = validate_model(weights, epoch)
    weights.write_bytes(b"wrong checkpoint")
    actual = sha256(weights)
    out = root / "must-not-exist"
    monkeypatch.setattr(
        sys,
        "argv",
        ["inference", "--model", str(weights), "--out", str(out)]
        + (["--checkpoint-epoch", str(epoch)] if epoch is not None else []),
    )
    monkeypatch.setitem(sys.modules, "cv2", None)
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setattr(
        round5_inference, "load_model", lambda *a: pytest.fail("model loaded")
    )
    monkeypatch.setattr(
        round5_inference, "evaluation_marker", lambda *a: pytest.fail("marker written")
    )
    with pytest.raises(ValueError) as error:
        round5_inference.main()
    assert expected in str(error.value) and actual in str(error.value)
    assert not out.exists()


@pytest.mark.parametrize("name", PASS_IDS)
@pytest.mark.parametrize("entry", ["capture", "finish"])
def test_forged_envelope_rejected_by_both_entry_points(saved, name, entry, monkeypatch):
    root, paths = saved
    original = json.loads(paths[name].read_text())["weights_sha256"]
    forged = "f" * 64
    paths[name].write_text(json.dumps({"weights_sha256": forged}))
    monkeypatch.setattr(finish_round5.Path, "home", lambda: root.parent.parent)
    monkeypatch.setattr(
        review_round5, "load_measurements", lambda: pytest.fail("scoring started")
    )
    monkeypatch.setattr(
        finish_round5, "capture", lambda *a: pytest.fail("capture started")
    )
    with pytest.raises(ValueError) as error:
        if entry == "capture":
            review_round5.capture(paths, root)
        else:
            finish_round5.main()
    assert original in str(error.value) and forged in str(error.value)


def test_correct_hashes_pass_both_scoring_preflights_and_audit(saved, monkeypatch):
    root, paths = saved
    validate_saved_passes(paths, root)
    audit = audit_saved_passes(root)
    assert {r["pass_id"] for r in audit} == set(PASS_IDS)
    assert all(r["status"] == "MATCH" for r in audit)

    class ReachedScoring(Exception):
        pass

    def stop(*args):
        raise ReachedScoring

    monkeypatch.setattr(finish_round5.Path, "home", lambda: root.parent.parent)
    monkeypatch.setattr(review_round5, "load_measurements", stop)
    monkeypatch.setattr(finish_round5, "capture", stop)
    with pytest.raises(ReachedScoring):
        review_round5.capture(paths, root)
    with pytest.raises(ReachedScoring):
        finish_round5.main()


def test_diagnostic_uses_own_hash_without_mutating_final_declaration(
    saved, monkeypatch
):
    root, _ = saved
    directory = root / "mj-r5-rf-a"
    fit_bytes = (directory / "fit_summary.json").read_bytes()
    final_hash = json.loads(fit_bytes)["weights_sha256"]
    weights = directory / "epoch-02.pt"
    fit, digest = validate_model(weights, 2)
    assert fit["weights_sha256"] == final_hash != digest == sha256(weights)
    fit.update(split={}, labels_sha256="test")
    monkeypatch.setattr(round5_inference, "validate_model", lambda *args: (fit, digest))
    monkeypatch.setattr(round5_inference, "evaluation_marker", lambda _: None)
    monkeypatch.setitem(
        sys.modules, "cv2", SimpleNamespace(setNumThreads=lambda _: None)
    )
    monkeypatch.setitem(
        sys.modules, "torch", SimpleNamespace(set_num_threads=lambda _: None)
    )
    monkeypatch.setattr(round5_inference, "load_dataset", lambda *a: (None, []))
    monkeypatch.setattr(
        round5_inference, "load_measurements", lambda: {"frozen_set_id": "test"}
    )
    monkeypatch.setattr(round5_inference, "load_model", lambda *a: "model")
    calls = []
    monkeypatch.setattr(
        round5_inference, "predict_all", lambda *args: calls.append(args)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "inference",
            "--model",
            str(weights),
            "--out",
            str(root / "new"),
            "--checkpoint-epoch",
            "2",
        ],
    )
    round5_inference.main()
    assert calls[0][-1] == digest
    assert calls[0][-2]["weights_sha256"] == final_hash
    assert (directory / "fit_summary.json").read_bytes() == fit_bytes


def test_missing_declarations_fail_closed(saved):
    root, paths = saved
    with pytest.raises(ValueError, match="no registered fit"):
        validate_saved_passes({"unregistered": paths["rf-b"]}, root)
    with pytest.raises(ValueError, match="one declared checkpoint"):
        validate_saved_passes({"rf-r5-a / epoch-99": paths["rf-b"]}, root)
    with pytest.raises(ValueError, match="one declared checkpoint"):
        validate_model(root / "mj-r5-rf-a/epoch-99.pt", 99)


def test_committed_retroactive_audit_covers_all_passes():
    execution = json.loads((HERE / "fixtures/round5_execution.json").read_text())
    audit = execution["checkpoint_integrity_review"]["passes"]
    evidence = json.loads(
        gzip.decompress((HERE / "fixtures/round5_scored_output.json.gz").read_bytes())
    )
    assert {r["pass_id"] for r in audit} == set(PASS_IDS)
    for row in audit:
        assert row["status"] == "MATCH"
        assert row["declared_sha256"] == row["recorded_sha256"] == row["on_disk_sha256"]
        name = row["pass_id"]
        if "epoch" in name:
            assert (
                row["recorded_sha256"]
                == evidence["learning_curve"][name]["checkpoint_sha256"]
            )
        else:
            assert (
                row["recorded_sha256"]
                == evidence["models"][name]["saved_pass_provenance"]["weights_sha256"]
            )


def test_final_pass_cannot_silently_switch_to_diagnostic_weights(saved):
    root, _ = saved
    directory = root / "mj-r5-rf-a"
    final_hash = sha256(directory / "weights.pt")
    epoch_hash = sha256(directory / "epoch-02.pt")
    with pytest.raises(ValueError) as error:
        validate_model(directory / "epoch-02.pt")
    assert final_hash in str(error.value) and epoch_hash in str(error.value)
    with pytest.raises(ValueError):
        validate_model(directory / "weights.pt", 2)
