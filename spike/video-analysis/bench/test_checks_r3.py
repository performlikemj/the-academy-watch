"""Regeneration artifacts come from data; crop/temporal limits stay attached."""

import copy
import hashlib
import json

import pytest

from checks_contract import CONTRACT_VERSION
from checks_score import score_run, write_report
from checks_truth import derive_truth
from compare_checks import compare, main, markdown
from test_checks_r2 import SAVED, saved_truths


def fixture(tmp_path):
    truths = saved_truths()
    entries = []
    for cid, truth in truths.items():
        path = tmp_path / f"{cid}.json"
        path.write_text(json.dumps(truth))
        entries.append({"clip_id": cid, "truth": path.name})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"clips": entries, "frozen_set_id": "fixture"}))
    for name, crop in (("wide", False), ("crop", True)):
        directory = tmp_path / name
        (directory / "claims").mkdir(parents=True)
        settings = {
            "adapter": "qwen3vl_checks_crop" if crop else "qwen3vl_checks",
            "model": "qwen3-vl:8b",
            "frozen_set_id": "fixture",
            "clips": list(truths),
            "contract_version": CONTRACT_VERSION,
        }
        (directory / "run.json").write_text(json.dumps(settings))
        rows = copy.deepcopy(SAVED["runs"]["e1d-checks-dense"])
        for row in rows:
            row["contract_version"] = CONTRACT_VERSION
            if crop:
                for frame in row["sent_frames"]:
                    frame.update(
                        image_kind="crop",
                        crop_side_px=384,
                        crop_scale=2,
                        sent_w=768,
                        sent_h=768,
                    )
            (directory / "claims" / f"{row['clip_id']}.json").write_text(
                json.dumps(row)
            )
        write_report(score_run(rows, truths), directory)
    return manifest, {"wide": "wide", "crop": "crop"}, truths


def test_geometry_deltas_touch_table_and_decision_react_to_saved_data(tmp_path):
    manifest, runs, truths = fixture(tmp_path)
    before = compare(tmp_path, runs, manifest, allow_mixed=True, baseline_run="wide")
    assert before["decision_32b"]["run"] is False
    assert len(before["true_touch_clips"]) == 6
    assert before["true_touch_clips"] == before["touch_clips"]
    assert before["crop_geometry"]["crop"]["crop_side_px_max"] == 384
    positives = [
        cid
        for cid, t in truths.items()
        if derive_truth(t)["expected"]["player_touches_ball"] == "yes"
    ]
    for cid in positives[:2]:
        path = tmp_path / "crop" / "claims" / f"{cid}.json"
        row = json.loads(path.read_text())
        row["checks"]["player_touches_ball"]["answer"] = "yes"
        row["sent_frames"][0].update(crop_side_px=512, crop_scale=1.5)
        path.write_text(json.dumps(row))
    after = compare(tmp_path, runs, manifest, allow_mixed=True, baseline_run="wide")
    assert after["decision_32b"]["run"] is True
    assert after["decision_32b"]["recalls"]["crop"]["count"] == 2
    assert after["crop_geometry"]["crop"]["crop_side_px_max"] == 512
    assert after["per_question_deltas_pp"]["crop"]["player_touches_ball"][
        "accuracy"
    ] == pytest.approx(100 * 2 / 15)
    assert after["touch_recall"]["crop"]["touch_recall"] is None
    assert "not a measured detector bound" in after["decision_32b"]["confound"]
    (tmp_path / "crop" / "claims" / f"{positives[0]}.json").unlink()
    incomplete = compare(tmp_path, runs, manifest, allow_mixed=True)
    assert incomplete["decision_32b"]["run"] is None


def test_headline_excludes_crop_and_tables_carry_confounds(tmp_path):
    manifest, runs, _ = fixture(tmp_path)
    result = compare(tmp_path, runs, manifest, allow_mixed=True, baseline_run="wide")
    assert "crop (qwen" not in result["headline"]
    assert "wide (qwen" in result["headline"]
    assert result["comparison_metadata"]["gate1_excluded_runs"].keys() == {"crop"}
    assert (
        result["comparison_metadata"]["threshold_results"]["crop"][
            "off_pitch_false_yes_rate"
        ]["status"]
        == "WITHHELD"
    )
    assert "sideline" in result["question_caveats"]["crop"]["player_on_pitch"]
    assert "ball" in result["question_caveats"]["crop"]["ball_near_player"]
    text = markdown(result)
    for line in text.splitlines():
        if line.startswith(
            (
                "| wide | player_touches_ball |",
                "| crop | player_touches_ball |",
                "| wide | player_running |",
                "| crop | player_running |",
            )
        ):
            assert "Temporal confound" in line and "2.49 s" in line
    assert "32B crop run: NO" in text
    assert "unattainable by construction" in text
    assert "1.58 s" in text and "6.62 s" in text


def test_cli_named_diagnostics_examples_and_execution_are_reproducible(tmp_path):
    manifest, runs, _ = fixture(tmp_path)
    execution = tmp_path / "execution.json"
    execution.write_text(
        json.dumps(
            {
                "review_headline": "Requested review wording",
                "artifacts": {"known_truth_error": "explicit correction status"},
            }
        )
    )
    examples = tmp_path / "examples"
    examples.mkdir()
    image = examples / "crop.png"
    image.write_bytes(b"fixture image hash only")
    (examples / "examples.json").write_text(
        json.dumps(
            [
                {
                    "path": str(image),
                    "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                }
            ]
        )
    )
    diag = tmp_path / "diagnostic.json"
    diag.write_text(json.dumps({"calls": [], "marker": "saved diagnostic"}))
    output, md = tmp_path / "output.json", tmp_path / "output.md"
    args = [
        "--reports-root",
        str(tmp_path),
        "--manifest",
        str(manifest),
        "--runs",
        *[f"{k}={v}" for k, v in runs.items()],
        "--allow-mixed",
        "--execution",
        str(execution),
        "--baseline-run",
        "wide",
        "--touch-clips",
        "--example-crops",
        str(examples),
        "--diagnostic",
        f"8b={diag}",
        "--diagnostic",
        f"32b={diag}",
        "--extra-caveat",
        "explicit input caveat",
        "--out-json",
        str(output),
        "--out-md",
        str(md),
    ]
    main(args)
    first = output.read_bytes(), md.read_bytes()
    main(args)
    assert first == (output.read_bytes(), md.read_bytes())
    result = json.loads(output.read_text())
    assert set(result["thinking_channel_diagnostics"]) == {"8b", "32b"}
    assert result["known_truth_error"] == "explicit correction status"
    assert md.read_text().startswith("Requested review wording\n")
    assert "explicit input caveat" in result["caveats"]
    image.write_bytes(b"changed")
    with pytest.raises(ValueError, match="hash mismatch"):
        main(args)
    with pytest.raises(ValueError, match="baseline-run"):
        compare(tmp_path, runs, manifest, allow_mixed=True, baseline_run="missing")
