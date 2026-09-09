"""Regenerate evidence byte-for-byte from recorded runs and execution fixture."""

from __future__ import annotations
import argparse
import json
import gzip
from fractions import Fraction
from pathlib import Path
from ball_truth_kit import import_labels
from common import (
    DEFAULT_MANIFEST,
    DEFAULT_REPORT,
    DEFAULT_SOURCE,
    HERE,
    ROOT,
    dump,
    load_dataset,
    sha256,
    sample_indices,
)
from metrics import agreement, clip_metrics, overall

CANDIDATES = ["rf_full", "rf_2x2", "rf_3x3", "wasb"]


def collect(manifest_path, report_dir):
    manifest, clips = load_dataset(manifest_path, DEFAULT_SOURCE)
    runs, outputs = {}, {}
    for candidate in CANDIDATES:
        folder = report_dir / candidate
        runs[candidate] = json.loads((folder / "run.json").read_text())
        if runs[candidate]["frozen_set_id"] != manifest["frozen_set_id"]:
            raise ValueError("frozen set mismatch")
        if set(runs[candidate]["clips"]) != {c["clip_id"] for c in clips}:
            raise ValueError("incomplete candidate")
        outputs[candidate] = {
            c["clip_id"]: json.loads((folder / f"{c['clip_id']}.json").read_text())
            for c in clips
        }
    return {
        "manifest_sha256": sha256(manifest_path),
        "frozen_set_id": manifest["frozen_set_id"],
        "clips": clips,
        "runs": runs,
        "outputs": outputs,
    }


def compare(measurements, execution, human_path=None):
    clips = measurements["clips"]
    outputs = measurements["outputs"]
    for c in clips:
        for name in CANDIDATES:
            run = measurements["runs"][name]
            rate = float(Fraction(run["source_probe"]["avg_frame_rate"]))
            offset = 0 if c["native_source"] else c["window"]["start_s"]
            _, _, expected = sample_indices(
                c["window"]["start_s"], c["window"]["end_s"], rate, 2.0, offset
            )
            raw = outputs[name][c["clip_id"]]
            actual = raw["frames"]
            if (
                raw["wall_s"] <= 0
                or [f["frame_index"] for f in actual] != expected
                or [f["t"] for f in actual]
                != [round(offset + i / rate, 6) for i in expected]
            ):
                raise ValueError("incomplete or invalid sample schedule")
    frames = [
        {"clip": c["clip_id"], "t": f["t"], "source_size": c["source_size"]}
        for c in clips
        for f in outputs["rf_full"][c["clip_id"]]["frames"]
    ]
    human = import_labels(human_path, frames) if human_path else {}
    proxies = {}
    for c in clips:
        cid = c["clip_id"]
        schedule = [f["t"] for f in outputs["rf_full"][cid]["frames"]]
        if any(
            [f["t"] for f in outputs[n][cid]["frames"]] != schedule for n in CANDIDATES
        ):
            raise ValueError("candidate sample schedules differ")
        proxies[cid] = {
            t: agreement(
                {
                    n: outputs[n][cid]["frames"][i]["detections"]
                    for n in ["rf_full", "rf_2x2", "wasb"]
                }
            )
            for i, t in enumerate(schedule)
        }
    results = []
    for candidate in CANDIDATES:
        for threshold in [0.1, 0.2, 0.3, 0.4, 0.5] if candidate != "wasb" else [0.5]:
            rows = [
                clip_metrics(
                    c,
                    outputs[candidate][c["clip_id"]],
                    proxies[c["clip_id"]],
                    threshold,
                    human,
                )
                for c in clips
            ]
            total = overall(rows)
            for row in rows:
                row.pop("_sizes")
                row.pop("_confidence")
            results.append(
                {
                    "candidate": candidate,
                    "threshold": threshold,
                    "overall": total,
                    "per_clip": rows,
                }
            )
    winners = [r for r in results if r["overall"]["gate_proxy"] == "PASS"]
    verdict = (
        ", ".join(
            f"{r['candidate']} @{r['threshold']:.1f} ({r['overall']['fps']:.2f} FPS)"
            for r in winners
        )
        if winners
        else "No candidate"
    )
    speeds = ", ".join(
        f"{n} {next(r['overall']['fps'] for r in results if r['candidate'] == n):.2f} FPS"
        for n in CANDIDATES
    )
    headline = f"{verdict} passes the proxy gate (measured: {speeds}); MJ must click ball centres or mark no ball visible in ~/ball-truth-review/index.html to establish human-labelled results."
    return {
        "headline": headline,
        "execution": execution,
        "environment": measurements["runs"],
        "frozen_set_id": measurements["frozen_set_id"],
        "manifest_sha256": measurements["manifest_sha256"],
        "ball_visible_proxy": {
            cid: [
                {"t": t, "visible": bool(centres), "pair_midpoints_source_px": centres}
                for t, centres in frames.items()
            ]
            for cid, frames in proxies.items()
        },
        "proxy_voters": {"rf_full": 0.1, "rf_2x2": 0.1, "wasb": 0.5},
        "proxy_rule": "At least two of three fixed candidate voters agree within 40 source px; detection must fall within 40 px of a qualifying pair midpoint. Denominator fixed across threshold sweeps.",
        "human_truth": {
            "status": "partial_or_complete_labels_supplied"
            if human
            else "not_labelled",
            "labelled_frames": len(human),
            "total_frames": len(frames),
            "sha256": sha256(human_path) if human_path else None,
        },
        "results": results,
        "examples": execution.get("examples", []),
        "click_kit": execution["click_kit"],
    }


def number(value, percent=False):
    if value is None:
        return "N/A"
    return f"{value * 100:.1f}%" if percent else f"{value:.2f}"


def markdown(data):
    lines = [
        data["headline"],
        "",
        "Proxy results are not human ball truth. Both proxy visibility and off-pitch false-ball counts are surrogates; the fixed RF voters share weights. The 2 fps sample spans every window, not every native frame. FPS includes sequential video decode and inference, excludes one-time model load/warmup, report serialization and tracking. Continuity is duration-weighted; confidence is not calibrated across architectures. Ball pixels are the shortest detected box side, not measured ball diameter; WASB has no size estimate.",
        "",
        "## Environment",
        "",
        "```json",
        json.dumps(data["environment"], indent=2, sort_keys=True),
        "```",
        "",
        "## Overall — PROXY",
        "",
        "| Candidate | Threshold | Detection proxy | False/10s proxy | Ball px min/median | Mean confidence | FPS | Wall s/clip | Continuity | Fragments | Gate proxy |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in data["results"]:
        o = r["overall"]
        lines.append(
            f"| {r['candidate']} | {r['threshold']} | {number(o['detection_rate_proxy'], True)} | {number(o['false_per_10s_proxy'])} | {number(o['ball_px_min'])}/{number(o['ball_px_median'])} | {number(o['mean_confidence'])} | {number(o['fps'])} | {number(o['wall_s_per_clip'])} | {number(o['continuity'], True)} | {o['track_fragments']} | {o['gate_proxy']} |"
        )
    ref = data["results"][0]["overall"]
    lines += [
        "",
        f"Proxy-visible on-ball denominator: {ref['proxy_visible_on_ball_frames']} frames ({number(ref['proxy_coverage_on_ball'], True)} of all sampled on-ball frames); six on-ball and seven off-pitch clips. Gate pools visible-frame hits and off-pitch exposure across the relevant clips.",
        "",
        "## Touch proximity PREVIEW — PROXY detections, not touch events",
        "",
        "| Candidate | Threshold | On-ball near/box frames | Off-pitch near/box frames |",
        "|---|---:|---:|---:|",
    ]
    for r in data["results"]:
        t = r["overall"]["touch_preview"]
        lines.append(
            f"| {r['candidate']} | {r['threshold']} | {t['on_ball']['near_frames']}/{t['on_ball']['box_available_frames']} | {t['off_pitch']['near_frames']}/{t['off_pitch']['box_available_frames']} |"
        )
    lines += [
        "",
        "## Human truth — separate from proxy",
        "",
        f"Status: {data['human_truth']['status']}; {data['human_truth']['labelled_frames']}/{data['human_truth']['total_frames']} labelled. No unlabelled frame becomes a negative. Human false-ball rate uses only explicitly invisible labelled frame exposure; full human gate requires all relevant samples labelled.",
        "",
        "| Candidate | Threshold | Human visible hits/frames | Human detection | Human false/10s | Human gate |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in data["results"]:
        h = r["overall"]["human"]
        lines.append(
            f"| {r['candidate']} | {r['threshold']} | {h['detected_on_ball_frames']}/{h['visible_on_ball_frames']} | {number(h['detection_rate'], True)} | {number(h['false_per_10s'])} | {h['gate']} |"
        )
    lines += ["", "## Per clip — PROXY and proximity PREVIEW", ""]
    for r in data["results"]:
        lines += [
            f"### {r['candidate']} threshold {r['threshold']}",
            "",
            "| Clip | Group | Proxy hits/visible | Detection proxy | False/10s proxy | Mean confidence | Ball px min/median | FPS | Wall s | Continuity | Fragments | Near/box PREVIEW |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for c in r["per_clip"]:
            group = (
                "on-ball"
                if c["on_ball"]
                else "off-pitch"
                if c["off_pitch"]
                else "other"
            )
            lines.append(
                f"| {c['clip']} | {group} | {c['proxy_detected_frames']}/{c['proxy_visible_frames']} | {number(c['detection_rate_proxy'], True)} | {number(c['false_per_10s_proxy'])} | {number(c['mean_confidence'])} | {number(c['ball_px_min'])}/{number(c['ball_px_median'])} | {number(c['fps'])} | {number(c['wall_s'])} | {number(c['continuity'], True)} | {c['track_fragments']} | {c['touch_preview_frames']}/{c['touch_preview_eligible_frames']} |"
            )
        lines.append("")
    lines += ["## Example PNGs", ""] + [f"- {p}" for p in data["examples"]]
    lines += [
        "",
        "## Execution (committed fixture)",
        "",
        "```json",
        json.dumps(data["execution"], indent=2, sort_keys=True),
        "```",
        "",
        "Regenerate: `.loan/bin/python spike/video-analysis/ball/compare_ball.py` (use the repository parent .loan interpreter). Optional `--human-jsonl ~/ball-human-truth.jsonl` computes a separate human section. All measured inputs and the execution block are committed fixtures; PNGs, media, weights and cloned upstream code stay outside git.",
        "",
        "WASB model and MIT licence: https://github.com/nttcom/WASB-SBDT ; soccer weights linked by its MODEL_ZOO.md.",
        "",
    ]
    return "\n".join(lines)


def load_measurements(path=HERE / "fixtures/measurements.json.gz"):
    return json.loads(gzip.decompress(Path(path).read_bytes()))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--capture",
        action="store_true",
        help="Capture local recorded runs into committed measurement fixture",
    )
    p.add_argument("--report-dir", type=Path, default=DEFAULT_REPORT)
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument(
        "--measurements", type=Path, default=HERE / "fixtures/measurements.json.gz"
    )
    p.add_argument("--execution", type=Path, default=HERE / "fixtures/execution.json")
    p.add_argument("--human-jsonl", type=Path)
    p.add_argument(
        "--out-prefix",
        type=Path,
        default=ROOT / "ledgers/research/evidence-bench-2026-09-10-ball-detect",
    )
    a = p.parse_args()
    if a.capture:
        payload = json.dumps(
            collect(a.manifest, a.report_dir),
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode()
        a.measurements.write_bytes(gzip.compress(payload, mtime=0))
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
