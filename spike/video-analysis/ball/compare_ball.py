"""Deterministic diagnostics and separate human-labelled scores from saved outputs."""

from __future__ import annotations
import argparse
import gzip
import json
import math
from fractions import Fraction
from pathlib import Path
from ball_truth_kit import import_labels
from common import DEFAULT_REPORT, HERE, ROOT, dump, sha256, sample_indices
from metrics import (
    agreement,
    pair_decomposition,
    clip_class,
    clip_metrics,
    overall,
    retrack_saved,
    label_plan,
)

CANDIDATES = ["rf_full", "rf_2x2", "rf_3x3", "wasb", "wasb_2x2"]
RF_CANDIDATES = CANDIDATES[:3]
MEASUREMENTS = HERE / "fixtures/measurements.json.gz"


def same_retracking(actual, saved):
    """Allow only roundoff in duration-weighted group continuity, not track changes."""
    if actual.keys() != saved.keys():
        return False
    for name, row in actual.items():
        old = saved[name]
        if {k: v for k, v in row.items() if k != "groups"} != {
            k: v for k, v in old.items() if k != "groups"
        }:
            return False
        if row["groups"].keys() != old["groups"].keys():
            return False
        for group, values in row["groups"].items():
            before = old["groups"][group]
            if values.keys() != before.keys():
                return False
            for key, value in values.items():
                if key == "continuity":
                    if not math.isclose(
                        value, before[key], rel_tol=1e-12, abs_tol=1e-12
                    ):
                        return False
                elif value != before[key]:
                    return False
    return True


def load_measurements(path=MEASUREMENTS):
    return json.loads(gzip.decompress(Path(path).read_bytes()))


def save_measurements(data, path=MEASUREMENTS):
    payload = json.dumps(
        data, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode()
    Path(path).write_bytes(gzip.compress(payload, mtime=0))


def update_saved(report_dir=DEFAULT_REPORT, path=MEASUREMENTS):
    """Append only wasb_2x2 and derived tracks; preserve all original run records."""
    data = load_measurements(path)
    folder = report_dir / "wasb_2x2"
    run = json.loads((folder / "run.json").read_text())
    ids = [c["clip_id"] for c in data["clips"]]
    if run["frozen_set_id"] != data["frozen_set_id"] or set(run["clips"]) != set(ids):
        raise ValueError("new candidate dataset mismatch")
    data["runs"]["wasb_2x2"] = run
    data["outputs"]["wasb_2x2"] = {
        cid: json.loads((folder / f"{cid}.json").read_text()) for cid in ids
    }
    data["retracking"] = retrack_saved(data)
    data["human_label_plan"] = label_plan(data)
    save_measurements(data, path)


def validate(measurements):
    for c in measurements["clips"]:
        for name in CANDIDATES:
            run = measurements["runs"][name]
            if run["frozen_set_id"] != measurements["frozen_set_id"]:
                raise ValueError("frozen set mismatch")
            rate = float(Fraction(run["source_probe"]["avg_frame_rate"]))
            offset = 0 if c["native_source"] else c["window"]["start_s"]
            _, _, expected = sample_indices(
                c["window"]["start_s"], c["window"]["end_s"], rate, 2.0, offset
            )
            raw = measurements["outputs"][name][c["clip_id"]]
            actual = raw["frames"]
            if (
                raw["wall_s"] <= 0
                or [f["frame_index"] for f in actual] != expected
                or [f["t"] for f in actual]
                != [round(offset + i / rate, 6) for i in expected]
            ):
                raise ValueError("incomplete or invalid sample schedule")


def effective_resolution():
    sources = {
        "rf_full": [1920, 1080],
        "rf_2x2": [1010, 590],
        "rf_3x3": [707, 427],
        "wasb": [1920, 1080],
        "wasb_2x2": [960, 540],
    }
    return {
        name: {
            "source_tile_wh": size,
            "model_input_wh": [576, 576] if name.startswith("rf") else [512, 288],
            "effective_ball_px_seen_by_model": [
                24 * target / source
                for target, source in zip(
                    [576, 576] if name.startswith("rf") else [512, 288], size
                )
            ],
            "reference": "Hypothetical 24x24 source-pixel ball, not measured ball truth",
            "transform": "anisotropic squash to 576x576"
            if name.startswith("rf")
            else "aspect-preserving affine to 512x288",
        }
        for name, size in sources.items()
    }


def compare(measurements, execution, human_path=None, extra_detections=None):
    validate(measurements)
    clips, outputs = measurements["clips"], measurements["outputs"]
    extras = extra_detections or {}
    outputs = {
        **outputs,
        **{name: payload["outputs"] for name, payload in extras.items()},
    }
    frames = [
        {"clip": c["clip_id"], "t": f["t"], "source_size": c["source_size"]}
        for c in clips
        for f in outputs["rf_full"][c["clip_id"]]["frames"]
    ]
    human = import_labels(human_path, frames) if human_path else {}
    proxies: dict[str, dict] = {}
    pairs = []
    for c in clips:
        cid = c["clip_id"]
        proxies[cid] = {}
        counts = dict.fromkeys(
            ["frames", "any_pair", "rf_pair_only", "with_wasb", "rf_pair"], 0
        )
        for i, row in enumerate(outputs["rf_full"][cid]["frames"]):
            votes = {
                n: outputs[n][cid]["frames"][i]["detections"]
                for n in ("rf_full", "rf_2x2", "wasb")
            }
            proxies[cid][row["t"]] = agreement(votes)
            counts["frames"] += 1
            for key, value in pair_decomposition(votes).items():
                counts[key] += value
        pairs.append({"clip": cid, "class": clip_class(c), **counts})
    groups = {
        group: {
            key: sum(c[key] for c in pairs if c["class"] == group)
            for key in ["frames", "any_pair", "rf_pair_only", "with_wasb", "rf_pair"]
        }
        for group in ("on_ball", "off_pitch", "other")
    }
    results = []
    for name in [*CANDIDATES, *extras]:
        thresholds = (
            [extras[name]["threshold"]]
            if name in extras
            else [0.1, 0.2, 0.3, 0.4, 0.5]
            if name in RF_CANDIDATES
            else [0.5]
        )
        for threshold in thresholds:
            rows = [
                clip_metrics(
                    c,
                    outputs[name][c["clip_id"]],
                    proxies[c["clip_id"]],
                    threshold,
                    human,
                )
                for c in clips
            ]
            total = overall(rows)
            if extras.get(name, {}).get("synthetic_smoke"):
                total["human"]["gate"] = "SYNTHETIC SMOKE — NOT RESULTS"
            synthetic = bool(extras.get(name, {}).get("synthetic_smoke"))
            for row in rows:
                if synthetic:
                    row["synthetic_smoke"] = True
                row.pop("_sizes")
                row.pop("_confidence")
            results.append(
                {
                    "candidate": name,
                    **({"synthetic_smoke": True} if synthetic else {}),
                    "threshold": threshold,
                    "overall": total,
                    "per_clip": rows,
                }
            )
    rf_counts = ", ".join(
        f"{r['candidate']} {r['overall']['boxes_per_frame']:.2f}"
        for r in results
        if r["candidate"] in RF_CANDIDATES and r["threshold"] == 0.1
    )
    g = groups["on_ball"]
    headline = f"UNMEASURABLE (proxy): this bench measures detector self-agreement and box counts ({rf_counts} boxes/frame at 0.1); {g['rf_pair_only']}/{g['any_pair']} on-ball agreement frames are RF-pair-only. Recall against the real match ball is unmeasured until MJ labels frames."
    if human:
        headline = headline.replace(
            "Recall against the real match ball is unmeasured until MJ labels frames.",
            f"Separate human scores use {len(human)} labels; coverage and sample gate are reported below.",
        )
    retracking = retrack_saved(measurements)
    if not same_retracking(retracking, measurements["retracking"]):
        raise ValueError(
            "saved retracking fixture differs from current tracker; update derived fixture"
        )
    # Keep byte-stable canonical aggregates after validating track identity.
    retracking = measurements["retracking"]
    return {
        "headline": headline,
        "execution": execution,
        "human_loop": execution.get("human_loop"),
        "extra_candidates": {
            name: {k: v for k, v in payload.items() if k != "outputs"}
            for name, payload in extras.items()
        },
        "environment": measurements["runs"],
        "frozen_set_id": measurements["frozen_set_id"],
        "manifest_sha256": measurements["manifest_sha256"],
        "proxy_voters": {"rf_full": 0.1, "rf_2x2": 0.1, "wasb": 0.5},
        "proxy_rule": "Two of three fixed voters within 40 source px. This is endogenous self-agreement, never visibility truth or a recall/false-positive gate. New tiled WASB is scored without changing the diagnostic denominator.",
        "agreement_proxy_frames": {
            cid: [
                {
                    "t": t,
                    "agreement": bool(centres),
                    "pair_midpoints_source_px": centres,
                }
                for t, centres in rows.items()
            ]
            for cid, rows in proxies.items()
        },
        "pair_decomposition": {
            "groups": groups,
            "per_clip": pairs,
            "definition": "RF-pair-only = rf_full/rf_2x2 agree and neither RF agrees with WASB; with-WASB = either RF agrees with WASB; disjoint counts sum to any_pair. rf_pair is also reported, overlapping with with-WASB.",
        },
        "resolution": effective_resolution(),
        "human_truth": {
            "status": "labels_supplied" if human else "not_labelled",
            "labelled_frames": len(human),
            "suggestions_accepted": sum(
                r.get("source_accepted", False) for r in human.values()
            ),
            "accepted_sources": {
                source: sum(
                    r.get("source_accepted", False)
                    and r.get("accepted_source") == source
                    for r in human.values()
                )
                for source in sorted(
                    {
                        r["accepted_source"]
                        for r in human.values()
                        if r.get("source_accepted")
                    }
                )
            },
            "total_frames": len(frames),
            "sha256": sha256(human_path) if human_path else None,
        },
        "human_label_plan": measurements["human_label_plan"],
        "results": results,
        "retracking": retracking,
        "track_examples": execution.get("track_examples", []),
        "click_kit": execution["click_kit"],
    }


def number(value, percent=False):
    return (
        "N/A" if value is None else f"{value * 100:.1f}%" if percent else f"{value:.2f}"
    )


def candidate_label(result):
    return result["candidate"] + (
        " [SYNTHETIC]" if result.get("synthetic_smoke") else ""
    )


def markdown(data):
    lines = [
        data["headline"],
        "",
        "The match ball is usually in frame in these off-pitch clips: the marked player is off pitch, not the entire scene. `boxes_per_10s_offpitch` counts candidate outputs; it is NOT false-ball rate. Heatmap candidates emit points rather than boxes. All proxy verdicts remain UNMEASURABLE (proxy), even with perfect agreement. Only separate human labels can measure recall and unmatched match-ball predictions.",
        "",
        "## Self-agreement decomposition — PROXY, not truth",
        "",
        "| Clip class | Frames | Any pair | RF-pair-only | With WASB | RF pair (overlapping) |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for group, c in data["pair_decomposition"]["groups"].items():
        lines.append(
            f"| {group} | {c['frames']} | {c['any_pair']} | {c['rf_pair_only']} | {c['with_wasb']} | {c['rf_pair']} |"
        )
    lines += [
        "",
        data["pair_decomposition"]["definition"],
        "",
        "| Clip | Class | Any pair/frames | RF-pair-only | With WASB |",
        "|---|---|---:|---:|---:|",
    ]
    for c in data["pair_decomposition"]["per_clip"]:
        lines.append(
            f"| {c['clip']} | {c['class']} | {c['any_pair']}/{c['frames']} | {c['rf_pair_only']} | {c['with_wasb']} |"
        )
    lines += [
        "",
        "## All candidates and thresholds — diagnostic PROXY only",
        "",
        "| Candidate | Threshold | Self-agreement proxy | Boxes/frame | boxes_per_10s_offpitch | Confidence | Box px min/median | FPS | Wall s/clip | Verdict |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in data["results"]:
        o = r["overall"]
        lines.append(
            f"| {candidate_label(r)} | {r['threshold']} | {number(o['self_agreement_rate_proxy'], True)} | {number(o['boxes_per_frame'])} | {number(o['boxes_per_10s_offpitch'])} | {number(o['mean_confidence'])} | {number(o['box_px_min'])}/{number(o['box_px_median'])} | {number(o['fps'])} | {number(o['wall_s_per_clip'])} | {o['gate_proxy']} |"
        )
    lines += [
        "",
        "FPS counts sampled 2 fps outputs including sequential decode of intervening native frames, excludes model startup/warmup, parity, serialization and tracking. RF sweep filters saved 0.1 boxes; no new RF inference. Three-frame WASB inputs are consecutive native frames. RF 3x3 timing variance is retained from the original run. Box dimensions do not establish actual ball size.",
        "",
        "## Effective ball px seen by model — resolution calculation",
        "",
        "Reference is a hypothetical 24x24 px ball in the 1920x1080 source, not a ground-truth measurement. RF medium squashes each input anisotropically to 576x576. These are not 1080p model inputs.",
        "",
    ]
    for name, r in data["resolution"].items():
        x, y = r["effective_ball_px_seen_by_model"]
        lines.append(
            f"- {name}: source tile {r['source_tile_wh']}, model {r['model_input_wh']}, effective ball **{x:.1f}x{y:.1f} px**; {r['transform']}."
        )
    lines += [
        "",
        "`run_ball.py --resolution <side>` now overrides RF resolution. No resolution-override run was made.",
        "",
        "## Saved RF 0.1 boxes re-tracked — unverified trajectories",
        "",
        "Kalman association now uses 30 m/s x elapsed seconds x 20 source px/metre: 300 px in 0.5 s, 600 px across a 1.0 s gap. This is an uncalibrated pixel convention, not measured physical speed. Max gap is 1.0 s. Longest duration includes one 0.5 s observation bin; short gaps can be bridged; trailing extrapolation is not counted.",
        "",
        "A single speed-bounded hypothesis means exactly one fragment covering at least 80% of a clip. Even that is NOT evidence it is the ball: slow/static false boxes and identity switches can satisfy the speed cap. Human review is required.",
        "",
        "| RF candidate @0.1 | Scope | Fragments | Weighted continuity | Longest track s | Single hypothesis clips/total |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for name, r in data["retracking"].items():
        for group in ("on_ball", "all"):
            o = r["groups"][group]
            lines.append(
                f"| {name} | {group} | {o['fragments']} | {number(o['continuity'], True)} | {number(o['longest_track_s'])} | {o['single_hypothesis_clips']}/{o['clips']} |"
            )
    lines += [
        "",
        "| Candidate @0.1 | On-ball clip | Fragments | Continuity | Longest s | One speed-bounded hypothesis? |",
        "|---|---|---:|---:|---:|---|",
    ]
    for name, r in data["retracking"].items():
        for c in r["per_clip"]:
            if c["class"] == "on_ball":
                lines.append(
                    f"| {name} | {c['clip']} | {c['fragments']} | {number(c['continuity'], True)} | {number(c['longest_track_s'])} | {c['single_speed_bounded_hypothesis']} (not ball-confirmed) |"
                )
    lines += [
        "",
        "## Touch proximity PREVIEW — no separation",
        "",
        "RF near-rates overlap between on-ball and off-pitch clips: **no separation** demonstrated by this preview. These rates are from unverified detector outputs, not touch counts. WASB rates do not establish touch detection either.",
        "",
        "| Candidate | Threshold | On-ball near/box frames | On-ball near-rate | Off-pitch near/box frames | Off-pitch near-rate |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for r in data["results"]:
        t = r["overall"]["touch_preview"]
        a, b = t["on_ball"], t["off_pitch"]
        lines.append(
            f"| {candidate_label(r)} | {r['threshold']} | {a['near_frames']}/{a['box_available_frames']} | {number(a['rate'], True)} | {b['near_frames']}/{b['box_available_frames']} | {number(b['rate'], True)} |"
        )
    lines += [
        "",
        "## Human-label scoring from saved detections",
        "",
        "MJ: label the six on-ball clips (**540 frames**) plus approximately **100 off-pitch frames**, spread across seven clips. The 100-frame, model-independent sample plan (at least 10 per off-pitch clip, with evenly spaced frames and balanced clip quotas) is in JSON `human_label_plan`. Click the match ball centre or explicitly mark not visible; leave uncertainty unlabelled. This is enough to score ALL five candidates and every saved threshold without inference, models, cv2, or source video.",
        "",
        "```sh",
        "~/Projects/loanarmy/.loan/bin/python spike/video-analysis/ball/score_from_saved.py --human-jsonl ~/Downloads/ball-human-truth.jsonl",
        "```",
        "",
        "The sampled human gate requires all on-ball samples labelled and >=100 off-pitch labels. Recall uses visible on-ball labels; unmatched predictions on ALL labelled off-pitch frames are counted (at most one match within 40 source px; duplicates are unmatched), with 0.5 s exposure per labelled frame. It is an estimate on the selected sample, not an exhaustive full-match gate. Unlabelled frames never become negatives. Proxy verdicts stay UNMEASURABLE regardless of labels.",
        "",
        f"Current human status: {data['human_truth']['status']}; {data['human_truth']['labelled_frames']} labels.",
        "",
        "| Candidate | Threshold | Human matched/visible | Human recall | Human unmatched/10 s | Human gate |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in data["results"]:
        h = r["overall"]["human"]
        lines.append(
            f"| {candidate_label(r)} | {r['threshold']} | {h['detected_on_ball_frames']}/{h['visible_on_ball_frames']} | {number(h['detection_rate'], True)} | {number(h['false_per_10s'])} | {h['gate']} |"
        )
    lines += ["", "## Per clip — diagnostic PROXY and track/proximity preview", ""]
    for r in data["results"]:
        lines += [
            f"### {candidate_label(r)} @{r['threshold']}",
            "",
            "| Clip | Group | Proxy matches/agreement | Self-agreement | Boxes/frame | boxes_per_10s_offpitch | Confidence | Box px min/median | FPS | Wall s | Fragments | Continuity | Longest s | Near-rate |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for c in r["per_clip"]:
            group = (
                "on_ball"
                if c["on_ball"]
                else "off_pitch"
                if c["off_pitch"]
                else "other"
            )
            lines.append(
                f"| {c['clip']}{' [SYNTHETIC]' if r.get('synthetic_smoke') else ''} | {group} | {c['proxy_matched_frames']}/{c['proxy_agreement_frames']} | {number(c['self_agreement_rate_proxy'], True)} | {number(c['boxes_per_frame'])} | {number(c['boxes_per_10s_offpitch'])} | {number(c['mean_confidence'])} | {number(c['box_px_min'])}/{number(c['box_px_median'])} | {number(c['fps'])} | {number(c['wall_s'])} | {c['track_fragments']} | {number(c['continuity'], True)} | {number(c['longest_track_s'])} | {number(c['touch_preview_rate'], True)} |"
            )
        lines.append("")
    lines += ["## Three track overlays (unverified hypotheses)", ""] + [
        f"- {p}" for p in data["track_examples"]
    ]
    lines += [
        "",
        "## Environment and WASB 2x2 parity",
        "",
        "```json",
        json.dumps(data["environment"], indent=2, sort_keys=True),
        "```",
        "",
        "## Execution fixture",
        "",
        "```json",
        json.dumps(data["execution"], indent=2, sort_keys=True),
        "```",
        "",
        "Regenerate byte-for-byte: `.loan/bin/python spike/video-analysis/ball/compare_ball.py` using the parent repository interpreter. All numeric inputs, re-tracks and execution metadata are committed fixtures. Original four candidate run records remain unchanged; round 2 added WASB 2x2; round 3 adds only the explicitly synthetic training smoke and its trained-model pre-fill pass, kept outside this evidence table.",
        "",
    ]
    if data.get("extra_candidates"):
        lines += [
            "## Additional saved model candidates",
            "",
            "These candidates use the same labels and 40 px bench matching as the originals. Scores including training clips are in-sample, not held-out generalisation. The training metrics.json separately reports held-out 20 px scores. Synthetic smoke candidates are never accuracy results.",
            "",
            "```json",
            json.dumps(data["extra_candidates"], indent=2, sort_keys=True),
            "```",
            "",
        ]
    if data.get("human_loop"):
        lines += [
            "## Human loop",
            "",
            *data["human_loop"]["instructions"],
            "",
            "Recorded build and training smoke (synthetic; no accuracy result):",
            "",
            "```json",
            json.dumps(
                {k: v for k, v in data["human_loop"].items() if k != "instructions"},
                indent=2,
                sort_keys=True,
            ),
            "```",
            "",
        ]
    return "\n".join(lines)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--update-saved",
        action="store_true",
        help="Append only local wasb_2x2 outputs and recomputed RF tracks to fixture",
    )
    p.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--measurements", type=Path, default=MEASUREMENTS)
    p.add_argument("--execution", type=Path, default=HERE / "fixtures/execution.json")
    p.add_argument("--human-jsonl", type=Path)
    p.add_argument(
        "--out-prefix",
        type=Path,
        default=ROOT / "ledgers/research/evidence-bench-2026-09-10-ball-detect",
    )
    a = p.parse_args()
    if a.update_saved:
        update_saved(a.report_dir, a.measurements)
    data = compare(
        load_measurements(a.measurements),
        json.loads(a.execution.read_text()),
        a.human_jsonl,
    )
    dump(a.out_prefix.with_suffix(".json"), data)
    a.out_prefix.with_suffix(".md").write_text(markdown(data))
    print(data["headline"])


if __name__ == "__main__":
    main()
