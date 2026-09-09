"""Lane B closed contract, MJ truth fixtures, error rates and real request boundary."""

import copy
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))

from adapters import qwen3vl_checks as adapter  # noqa: E402
from checks_contract import CONTRACT_VERSION, QUESTIONS, parse_read, response_schema  # noqa: E402
from checks_score import score_run, threshold_results  # noqa: E402
from checks_truth import derive_truth  # noqa: E402
from run_bench import (
    _parser,
    _resolve_inference_settings,
    _settings_fingerprint,
    run_benchmark,
)  # noqa: E402
from test_semantic import fake_transport, frozen, truth  # noqa: E402

FIXTURES = json.loads(
    (Path(__file__).parent / "fixtures/checks_notes.json").read_text()
)


def read(answer="no", **changes):
    return {
        **{
            q: {
                "answer": "red" if q == "kit_color_seen" else answer,
                "confidence": "high",
            }
            for q in QUESTIONS
        },
        **changes,
    }


def raw(cid="fixture", **changes):
    return {
        "clip_id": cid,
        "checks_raw": json.dumps(read(**changes)),
        "wall_s": 2.0,
        "error": None,
        "sent_frames": [],
        "anchored_frames": [],
    }


def test_contract():
    parsed = parse_read(json.dumps(read()))
    assert parsed.player_on_pitch.answer == "no"
    schema = response_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == set(QUESTIONS)
    for q in QUESTIONS:
        prop = schema["properties"][q]
        assert prop["additionalProperties"] is False
        assert prop["properties"]["confidence"]["enum"] == ["low", "medium", "high"]
    assert parse_read(
        json.dumps(
            read(
                player_running={
                    "answer": "yes",
                    "confidence": "low",
                    "reason": "x" * 80,
                }
            )
        )
    )


@pytest.mark.parametrize(
    "question",
    [
        {"answer": True, "confidence": "high"},
        {"answer": 1, "confidence": "high"},
        {"answer": "maybe", "confidence": "high"},
        {"answer": "yes", "confidence": 0.9},
        {"answer": "yes", "confidence": "high", "extra": 1},
        {"answer": "yes", "confidence": "high", "reason": "x" * 81},
        {"answer": "yes", "confidence": "high", "reason": 12},
        {"answer": "yes"},
    ],
)
def test_invalid_question(question):
    with pytest.raises(ValidationError):
        parse_read(json.dumps(read(player_running=question)))


def test_extra_top_level_and_bad_kit():
    for payload in [
        read(extra="x"),
        read(kit_color_seen={"answer": "pink", "confidence": "low"}),
    ]:
        with pytest.raises(ValidationError):
            parse_read(json.dumps(payload))


@pytest.mark.parametrize(
    "fixture", FIXTURES, ids=[f["truth"]["clip_id"] for f in FIXTURES]
)
def test_twenty_real_notes(fixture):
    expected = derive_truth(fixture["truth"])["expected"]
    assert [expected[q] for q in QUESTIONS] == fixture["expected"]


def test_receive_without_running_is_ungraded_independent_of_clip_id():
    fixture = FIXTURES[15]["truth"]
    for cid in (fixture["clip_id"], "another-clip"):
        assert (
            derive_truth({**fixture, "clip_id": cid})["expected"]["player_running"]
            is None
        )


def test_scoring_false_yes_no_abstention_and_high_confidence():
    negative = truth("on the sideline")
    positive = truth("runs and passes")
    results = [raw("a", answer="yes"), raw("b"), raw("c", answer="unclear")]
    results[0]["from_thinking"] = True
    m = score_run(results, {"a": negative, "b": positive, "c": negative})["overall"]
    q = m["questions"]["player_touches_ball"]
    assert q["accuracy"] == 0 and q["abstain_rate"] == 1 / 3 and q["coverage"] == 2 / 3
    assert q["false_yes_rate"] == 1 / 2 and q["false_no_rate"] == 1
    assert q["confident_wrong_count"] == 2
    assert (
        m["off_pitch_false_yes_rate"]
        == m["off_pitch_idle_touch_false_yes_rate"]
        == 1 / 2
    )
    assert m["from_thinking_rate"] == 0.3333
    assert threshold_results(m)["off_pitch_false_yes_rate"]["status"] == "FAIL"
    assert (
        threshold_results(m, complete=False)["macro_accuracy"]["status"] == "WITHHELD"
    )


def test_gate_denominators_mixed_idle_excluded_and_reason_not_scored():
    truths = {f["truth"]["clip_id"]: f["truth"] for f in FIXTURES}
    results = [raw(cid) for cid in truths]
    report = score_run(results, truths)
    m = report["overall"]
    assert m["gates"]["off_pitch"]["truth_no_count"] == 14
    assert m["gates"]["off_pitch_idle_touch"]["truth_no_count"] == 9
    assert m["questions"]["kit_color_seen"]["abstain_count"] == 2
    assert m["questions"]["kit_color_seen"]["confident_wrong_count"] == 1
    altered = copy.deepcopy(results)
    for r in altered:
        payload = json.loads(r["checks_raw"])
        for q in QUESTIONS:
            payload[q]["reason"] = "Player scores, runs, passes, and is on the pitch."
        r["checks_raw"] = json.dumps(payload)
    assert score_run(altered, truths)["overall"] == m
    assert m["questions"]["player_on_pitch"]["eligible_count"] == 19


def test_invalid_raw_cannot_hide_behind_cached_parsed_data():
    r = {**raw(), "checks_raw": "bad JSON", "checks": read(), "from_thinking": True}
    m = score_run([r], {"fixture": truth()})["overall"]
    assert m["failed_clips"] == 1 and m["scored_clips"] == 0
    assert m["from_thinking_rate"] == 1 and m["macro_accuracy"] is None
    assert (
        score_run([{**raw(), "error": "transport failed"}], {"fixture": truth()})[
            "overall"
        ]["failed_clips"]
        == 1
    )


@pytest.mark.parametrize("thinking", [False, True])
def test_adapter_actual_transport_schema_and_shared_drawing(
    monkeypatch, tmp_path, thinking
):
    captured = fake_transport(monkeypatch, json.dumps(read()), thinking=thinking)
    result = adapter.run(tmp_path / "clip.mp4", truth(), {})
    assert result["error"] is None and result["from_thinking"] is thinking
    assert len(result["sent_frames"]) == len(result["anchored_frames"]) == 12
    body = captured[0]
    assert body["format"] == response_schema() and body["think"] is False
    assert body["options"]["num_ctx"] == 65536
    assert "magenta" in body["messages"][0]["content"]
    assert "not evidence of a jersey number" in body["messages"][0]["content"]
    from adapters.qwen3vl_annotated import prepare_frames

    assert adapter.prepare_frames is prepare_frames


def test_runner_schema_defaults_and_fingerprint(monkeypatch, tmp_path):
    manifest = frozen(tmp_path)
    fake_transport(monkeypatch, json.dumps(read()))
    args = _parser().parse_args(
        [
            "--adapter",
            "qwen3vl_checks",
            "--manifest",
            str(manifest),
            "--report-root",
            str(tmp_path / "reports"),
        ]
    )
    settings = _resolve_inference_settings(args, json.loads(manifest.read_text()))
    assert settings["sample_interval"] == 0.5 and settings["sample_limit"] == 12
    assert (
        settings["contract_version"] == CONTRACT_VERSION
        and settings["num_ctx"] == 65536
    )
    assert _settings_fingerprint(settings, ["fixture"]) != _settings_fingerprint(
        {**settings, "contract_version": "v2"}, ["fixture"]
    )
    report, _ = run_benchmark(args)
    assert report["overall"]["scored_clips"] == 1
    monkeypatch.setenv("BENCH_NUM_CTX", "4096")
    with pytest.raises(ValueError, match="num_ctx"):
        _resolve_inference_settings(args, json.loads(manifest.read_text()))


def comparison_fixture(tmp_path):
    from checks_score import write_report

    manifests = []
    truths = {}
    for fixture in (FIXTURES[2], FIXTURES[4], FIXTURES[10], FIXTURES[18]):
        t = fixture["truth"]
        cid = t["clip_id"]
        truths[cid] = t
        path = tmp_path / f"{cid}.json"
        path.write_text(json.dumps(t))
        manifests.append({"clip_id": cid, "truth": path.name, "clip": f"{cid}.mp4"})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(
        json.dumps({"clips": manifests, "frozen_set_id": "fixture-set"})
    )
    for name, count in (("dense", 12), ("sparse", 1)):
        directory = tmp_path / name
        (directory / "claims").mkdir(parents=True)
        (directory / "run.json").write_text(
            json.dumps(
                {
                    "adapter": "qwen3vl_checks",
                    "model": "fixture-model:3b",
                    "frozen_set_id": "fixture-set",
                    "clips": list(truths),
                    "contract_version": CONTRACT_VERSION,
                    "sample_interval": 0.5 if count == 12 else 30,
                    "sample_limit": count,
                    "anchor_color": "magenta",
                }
            )
        )
        rows = []
        for cid in truths:
            r = {
                **raw(cid, answer="yes" if name == "dense" else "no"),
                "contract_version": CONTRACT_VERSION,
                "sent_frames": [{"t": 1}] * count,
                "anchored_frames": [{}] * count,
            }
            rows.append(r)
            (directory / "claims" / f"{cid}.json").write_text(json.dumps(r))
        write_report(score_run(rows, truths), directory)
    return manifest, {"dense": "dense", "prod30": "sparse"}, list(truths)


def edit_json(path, fn):
    obj = json.loads(path.read_text())
    fn(obj)
    path.write_text(json.dumps(obj))


def test_compare_complete_model_frame_facts_and_determinism(tmp_path):
    from compare_checks import compare, markdown

    manifest, runs, ids = comparison_fixture(tmp_path)
    result = compare(tmp_path, runs, manifest)
    assert result == compare(tmp_path, runs, manifest)
    meta = result["comparison_metadata"]
    assert meta["complete"] and meta["shared_scored_clip_ids"] == ids
    assert meta["frame_facts"]["dense"]["mean_boxed_frames_per_clip"] == 12
    assert meta["frame_facts"]["prod30"]["single_frame_attempts"] == 4
    assert "fixture-model:3b" in result["headline"]
    assert (
        "12 boxed frames" in result["headline"]
        and "1 boxed frames" in result["headline"]
    )
    assert "qwen3-vl:8b" not in result["headline"]
    assert markdown(result).startswith(result["headline"])
    reversed_result = compare(
        tmp_path, {"prod30": "sparse", "dense": "dense"}, manifest
    )
    assert result["headline"] == reversed_result["headline"]
    assert "Full truth table" in markdown(result)


@pytest.mark.parametrize(
    "missing", ["report_file", "report_row", "raw", "not_attempted"]
)
def test_compare_missing_withholds_thresholds(tmp_path, missing):
    from compare_checks import compare

    manifest, runs, ids = comparison_fixture(tmp_path)
    report = tmp_path / "sparse/report.json"
    if missing == "report_file":
        report.unlink()
    elif missing == "raw":
        (tmp_path / "sparse/claims" / f"{ids[0]}.json").unlink()
    elif missing == "report_row":
        edit_json(report, lambda d: d["clips"].pop(0))
    else:
        edit_json(report, lambda d: d["clips"][0].update(status="not_attempted"))
    result = compare(tmp_path, runs, manifest)
    assert result["headline"] == "INCOMPLETE COMPARISON — headline withheld"
    meta = result["comparison_metadata"]
    assert ids[0] in meta["coverage"]["prod30"]["missing_clip_ids"]
    assert all(
        r["status"] == "WITHHELD"
        for run in meta["threshold_results"].values()
        for r in run.values()
    )


@pytest.mark.parametrize("source", ["run", "report"])
@pytest.mark.parametrize("key", ["stopped_early", "wall_cap_exceeded"])
def test_compare_stop_markers_even_empty_objects(tmp_path, source, key):
    from compare_checks import compare

    manifest, runs, _ = comparison_fixture(tmp_path)
    edit_json(tmp_path / "dense" / f"{source}.json", lambda d: d.update({key: {}}))
    result = compare(tmp_path, runs, manifest)
    assert not result["comparison_metadata"]["complete"]
    assert result["comparison_metadata"]["coverage"]["dense"]["stop_markers"] == {
        f"{source}.{key}": {}
    }


def test_compare_failed_counts_as_covered_and_pairs_saved_and_rescored(tmp_path):
    from compare_checks import compare

    manifest, runs, ids = comparison_fixture(tmp_path)
    edit_json(tmp_path / "dense/run.json", lambda d: d.update(wall_cap_s=120))
    edit_json(
        tmp_path / "dense/report.json", lambda d: d["clips"][0].update(status="failed")
    )
    edit_json(
        tmp_path / "sparse/claims" / f"{ids[1]}.json",
        lambda d: d.update(checks_raw="bad JSON"),
    )
    result = compare(tmp_path, runs, manifest)
    meta = result["comparison_metadata"]
    assert meta["complete"] and meta["shared_scored_clip_ids"] == ids[2:]
    assert meta["paired_overall"]["dense"]["attempted_clips"] == 2
    assert result["lanes"]["prod30"]["report"]["overall"]["failed_clips"] == 1
    assert meta["frame_facts"]["prod30"]["attempted_clips"] == 4
    assert meta["paired_overall"]["dense"]["off_pitch_false_yes_rate"] is None
    assert (
        meta["threshold_results"]["dense"]["off_pitch_false_yes_rate"]["status"]
        == "WITHHELD"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("adapter", "different"),
        ("model", "another-model:9b"),
        ("frozen_set_id", "different-set"),
    ],
)
def test_compare_mixed_identity_requires_explicit_override(tmp_path, field, value):
    from compare_checks import compare

    manifest, runs, _ = comparison_fixture(tmp_path)
    edit_json(tmp_path / "sparse/run.json", lambda d: d.update({field: value}))
    with pytest.raises(ValueError, match="must match"):
        compare(tmp_path, runs, manifest)
    result = compare(tmp_path, runs, manifest, allow_mixed=True)
    assert result["comparison_metadata"]["mixed_settings"]["prod30"][field] == value


@pytest.mark.parametrize(
    "problem",
    [
        "selection",
        "contract",
        "model_missing",
        "duplicate",
        "raw_id",
        "raw_contract",
        "report_contract",
    ],
)
def test_compare_non_overridable_guards(tmp_path, problem):
    from compare_checks import compare

    manifest, runs, ids = comparison_fixture(tmp_path)
    if problem == "raw_id":
        edit_json(
            tmp_path / "dense/claims" / f"{ids[0]}.json",
            lambda d: d.update(clip_id="wrong"),
        )
    elif problem == "raw_contract":
        edit_json(
            tmp_path / "dense/claims" / f"{ids[0]}.json",
            lambda d: d.update(contract_version="old"),
        )
    elif problem == "report_contract":
        edit_json(
            tmp_path / "dense/report.json", lambda d: d.update(contract_version="old")
        )
    else:

        def change(d):
            if problem == "selection":
                d["clips"].reverse()
            elif problem == "duplicate":
                d["clips"].append(d["clips"][0])
            elif problem == "contract":
                d["contract_version"] = "old"
            else:
                del d["model"]

        edit_json(tmp_path / "sparse/run.json", change)
    with pytest.raises(ValueError):
        compare(tmp_path, runs, manifest, allow_mixed=True)


def test_diagnostic_three_calls_identical_frames_only_format_varies(
    monkeypatch, tmp_path
):
    from diag_format_channel import diagnose

    manifest = frozen(tmp_path)
    captured = fake_transport(monkeypatch, json.dumps(read()), thinking=True)
    result = diagnose(manifest, clip_id="fixture")
    assert len(captured) == 3
    assert (
        captured[0]["format"] == response_schema() and captured[1]["format"] == "json"
    )
    assert "format" not in captured[2]
    assert [{k: v for k, v in body.items() if k != "format"} for body in captured] == [
        captured[2]
    ] * 3
    assert all(
        row["content_empty"]
        and row["validated"]
        and row["json_field"] == "message.thinking"
        for row in result["calls"]
    )
    assert len(result["sent_frames"]) == 12


def test_diagnostic_malformed_and_content_precedence():
    from diag_format_channel import inspect_payload

    valid = json.dumps(read())
    both = inspect_payload({"message": {"content": valid, "thinking": valid}})
    assert (
        both["json_fields"] == ["message.content", "message.thinking"]
        and both["validated"]
    )
    malformed = inspect_payload({"message": {"content": "not json", "thinking": valid}})
    assert (
        not malformed["validated"] and malformed["selected_field"] == "message.content"
    )
    missing = inspect_payload({"message": {"thinking": valid}})
    assert missing["content_missing"] and not missing["validated"]
    invalid = inspect_payload({"message": {"content": "{}"}})
    assert invalid["json_field"] == "message.content" and not invalid["validated"]


def test_macro_accuracy_is_question_mean_and_threshold_boundaries():
    from checks_score import THRESHOLDS

    truths = {"a": truth("on the sideline"), "b": truth("passes")}
    # Binary accuracies differ in their answered denominators; kit stays correct.
    first = raw(
        "a", answer="no", player_running={"answer": "unclear", "confidence": "low"}
    )
    second = raw(
        "b", answer="no", player_on_pitch={"answer": "yes", "confidence": "high"}
    )
    m = score_run([first, second], truths)["overall"]
    accuracies = [
        q["accuracy"] for q in m["questions"].values() if q["accuracy"] is not None
    ]
    assert m["macro_accuracy"] == sum(accuracies) / len(accuracies)
    values = {k: v["threshold"] for k, v in THRESHOLDS.items()}
    assert all(r["status"] == "PASS" for r in threshold_results(values).values())
    values["macro_accuracy"] -= 0.0001
    values["off_pitch_false_yes_rate"] += 0.0001
    assert threshold_results(values)["macro_accuracy"]["status"] == "FAIL"
    assert threshold_results(values)["off_pitch_false_yes_rate"]["status"] == "FAIL"


def test_kit_override_uncertainty_and_disputed_unavailable():
    from checks_score import score_read

    parsed = parse_read(
        json.dumps(read(kit_color_seen={"answer": "black", "confidence": "high"}))
    )
    t = {**truth(), "truth_label_disputed": True, "kit_color_truth_override": "black"}
    q = score_read(parsed, t)["questions"]["kit_color_seen"]
    assert q["correct"] and q["answered"]
    q = score_read(parsed, {**t, "kit_color_uncertain": True})["questions"][
        "kit_color_seen"
    ]
    assert q["abstain"] and not q["confident_wrong"] and not q["answered"]
    del t["kit_color_truth_override"]
    assert not score_read(parsed, t)["questions"]["kit_color_seen"]["eligible"]


def test_compare_no_shared_scores_withholds_all_thresholds(tmp_path):
    from compare_checks import compare

    manifest, runs, _ = comparison_fixture(tmp_path)

    def fail_all(d):
        for c in d["clips"]:
            c["status"] = "failed"

    edit_json(tmp_path / "dense/report.json", fail_all)
    result = compare(tmp_path, runs, manifest)
    assert result["comparison_metadata"]["complete"]
    assert result["headline"] == "No shared scored clips — headline withheld"
    assert all(
        rule["status"] == "WITHHELD"
        for rules in result["comparison_metadata"]["threshold_results"].values()
        for rule in rules.values()
    )


def test_diagnostic_request_failure_does_not_block_other_modes(monkeypatch, tmp_path):
    from adapters import common
    from diag_format_channel import diagnose

    manifest = frozen(tmp_path)
    fake_transport(monkeypatch, json.dumps(read()))
    original = common.qwen_match_analysis.urllib.request.urlopen
    count = 0

    def failing(request, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            raise TimeoutError("fixture timeout")
        return original(request, **kwargs)

    monkeypatch.setattr(common.qwen_match_analysis.urllib.request, "urlopen", failing)
    result = diagnose(manifest, clip_id="fixture")
    assert count == 3 and len(result["calls"]) == 3
    assert result["calls"][0]["error"] == "TimeoutError: fixture timeout"
    assert all(row["validated"] for row in result["calls"][1:])
