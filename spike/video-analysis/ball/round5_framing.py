"""Aggregate-only interpretation of the unchanged round-5 detections and fits."""

from copy import deepcopy
import re

HEADLINE = "On these recipe-selected m04 clips no detector wins: RF-DETR and YOLO swap the lead every one or two false boxes, the unselected RF fit matches YOLO at equal held-out false rates, the large-ball result rests on one 12-second sequence, three of the n21 'false' boxes may be mislabelled real balls, and RF-DETR Nano@960 is about 8x slower at 2 fps (about 36 min per match) and 10-11x at native rate (about 8-9 h)."
DENOMINATOR = "The cited 2.17 / 1.30 / 2.61 / 3.04 rates DO reproduce as groups.on_ball.false_per_10s: 5 / 3 / 6 / 7 false boxes ×20/46, using the 46 no-ball frames in the two n17 on-ball clips. Strict selection uses groups.all and all 60 held-out no-ball frames. At TRAIN-1 A has 6/60×20=2.000 and B 4/60×20=1.333. The earlier claim that these rates did not reproduce was wrong: it confused denominators."
SELECTION = "Selection is a knife-edge tie-break: rf-r5-a stays selected correctly at the exact ceiling (6/60×20=2.000), with 76 hits versus r5-b's 75. One more false box would select r5-b. At every attainable matched false-count budget from 0 through 10 boxes (3.33/10s), r5-b is at or above r5-a. This rule output is a kit-source choice, not evidence of superiority."
BIG_BALL = "Zoom fits recover more large balls only at the looser threshold, within one 12-second sequence; run-to-run noise is as large as the effect. All 22 held-out ≥24px labels belong to m04-n17-t717-253073-260377, in relative intervals 0–1.5s, 3.0–3.5s and 4.5–12.0s. At TRAIN-1 selected A has 9 hits, below no-zoom RF b's 11; A and B share zoom yet differ by 3 frames. These are teacher-estimated sizes, not independent human box measurements."
EPOCHS = "No evidence more epochs help at strict budgets; do not plan longer m04 training. Epoch-2 curves are censored at confidence0.01: TRAIN false/10s reaches only1.48 (A) and1.64 (B), not the requested2.0 budget. Their H endpoints are3.00 and2.00 respectively (the approximate2/10s censoring description applies to B). At TRAIN-2 H hits ROSE epoch-2→FINAL: A84→93 with false/10s3.00→3.33; B87→94 with2.00→4.00. Only the first of the two declared LR decays took effect: epoch3 uses0.1× LR, and training stops during epoch4 before the epoch5 0.01× stage. Intermediate checkpoints remain diagnostic, never selected."
COUNTERFACTUAL = "Fit A launched under a TRAIN-only rule; it was amended to the held-out ≤2 ceiling after old rf-b's held-out false rates were known (before any new-fit held-out evaluation); under the original rule rf-b (95.00% TRAIN top-1 at TRAIN-1) would have won, changing the kit suggestion source."
COMPUTE = "Equal wall time was unequal compute: A received1,233 optimizer steps /9,852 tile-views; B1,325 /10,586 (+7.5% views) in the same90-minute budget. A ComfyUI job was active at some point; its effect on fitting time is unconfirmed. Future fits must be budgeted by optimizer steps, not wall clock."
SPEED = "On this M4 Max, RF-DETR Nano@960 is about 7.6-7.8x slower than YOLO11n at 2 fps sampling and 10.0-10.9x at native rate. The ratio is conservative: YOLO ran FP32 eager on a ~960x544 letterbox with the GPU 40-58% busy; RF ran FP16 JIT on 960x960. YOLO native55.2 exceeds sampled37.7 FPS because common.samples decodes and RGB-converts approximately14 skipped frames per2fps sample inside the timer. The GPU40–58% characterization is approximate; measured per-repeat GPU means/ranges remain below. Historical11.5-vs51FPS cause remains unconfirmed."
FUTURE = "Calibrate thresholds on TRAIN-disjoint clips; budget fits by optimizer steps; always show matched-false-rate curves and per-clip counts beside TRAIN operating points. No further m04 training. The next real evidence is a fresh labelled match from a different venue and day."
N21 = "N21 is scorer class off_pitch, based on MJ's note. Source crops for every model at both TRAIN budgets show a visible background football: each r5 fit's single TRAIN-1 n21 box is the sample-9 ball (within2px of the old RF box); at TRAIN-2, two of three r5 boxes sit on the ball and one on footwear. MJ's preceding clicks at t3903.0–3905.47 move toward the flagged spot (about86→77px), then s6–s10 are no-ball despite visible football. This conflicts with an any-visible-ball reading unless the intended rule is match-ball only. Pending MJ adjudication of n21 frames s6-s10 and a match-ball versus any-ball rule. No labels, thresholds, selection or strict gate were changed."


def enrich(e):
    e = deepcopy(e)
    models = e["models"]
    matched = []
    for boxes in range(11):
        matched.append(
            {
                "false_boxes_budget": boxes,
                "false_per_10s": boxes * 20 / 60,
                "hits": {
                    n: max(
                        p["top1_hits"]
                        for p in row["held_curve_diagnostic_only"]
                        if p["false_boxes"] <= boxes
                    )
                    for n, row in models.items()
                },
            }
        )
    # Visual source-pixel review, not algorithmic path interpolation or relabelling.
    credits = {
        "yolo-r2-b": {"1": 0, "2": 0},
        "rf-b": {"1": 2, "2": 3},
        "rf-r5-a": {"1": 1, "2": 2},
        "rf-r5-b": {"1": 1, "2": 2},
    }
    sensitivity = []
    for name, row in models.items():
        for budget, op in row["operating_points"].items():
            g = op["held"]["groups"]["all"]
            credit = credits[name][budget]
            sensitivity.append(
                {
                    "model": name,
                    "train_budget": budget,
                    "no_ball_frames": g["no_ball_frames"],
                    "strict_false_boxes": g["no_ball_predictions"],
                    "n21_visible_ball_boxes": credit,
                    "strict_false_per_10s": g["false_per_10s"],
                    "without_visible_ball_boxes_per_10s": 20
                    * (g["no_ball_predictions"] - credit)
                    / g["no_ball_frames"],
                }
            )
    e["framing"] = {
        "headline": HEADLINE,
        "matched_false_rate_diagnostic_only": matched,
        "n21_sensitivity": sensitivity,
        "n21_note": N21,
        "calibration_false_ratios": {
            n: row["operating_points"]["1"]["held"]["groups"]["all"]["false_per_10s"]
            / row["operating_points"]["1"]["train"]["groups"]["all"]["false_per_10s"]
            for n, row in models.items()
        },
        "selection": SELECTION,
        "big_ball": BIG_BALL,
        "epochs": EPOCHS,
        "counterfactual": COUNTERFACTUAL,
        "unequal_compute": COMPUTE,
        "speed": SPEED,
        "future_method": FUTURE,
    }
    e["selection_audit"]["preview_discrepancy"] = DENOMINATOR
    t = e["throughput"]
    for row in t["models"].values():
        for key in ("repeats", "native_repeats"):
            for repeat in row[key]:
                if "background_caveat_samples" in repeat:
                    samples = repeat.pop("background_caveat_samples")

                    def summary(field):
                        values = [s[field] for s in samples if s[field] is not None]
                        return {
                            "mean": sum(values) / len(values),
                            "min": min(values),
                            "max": max(values),
                        }

                    repeat["mediaanalysisd_cpu_percent"] = summary(
                        "mediaanalysisd_cpu_percent"
                    )
                    repeat["agx_gpu_utilisation_percent"] = summary(
                        "agx_gpu_utilisation_percent"
                    )
                repeat["media_cpu_ge30"] = (
                    repeat["mediaanalysisd_cpu_percent"]["mean"] >= 30
                )
                repeat["timing_status"] = (
                    "contended (mediaanalysisd mean CPU >=30%)"
                    if repeat["media_cpu_ge30"]
                    else (
                        "contended (detected competing activity)"
                        if repeat["busy_polls"]
                        else "no flagged contention (background load recorded)"
                    )
                )
                repeat.pop("activity_before", None)
            row[key + "_fps_range"] = [
                min(r["fps"] for r in row[key]),
                max(r["fps"] for r in row[key]),
            ]
        row["match_2fps_minutes_range"] = [
            10800 / f / 60 for f in reversed(row["repeats_fps_range"])
        ]
        row["match_native_minutes_range"] = [
            5400 * t["native_fps"] / f / 60
            for f in reversed(row["native_repeats_fps_range"])
        ]
    t.pop("idle_preflight", None)
    t["timing_status"] = (
        "mixed contention: four repeats flagged by mediaanalysisd mean CPU >=30%"
    )
    t["protocol"] = t["protocol"].replace(
        "Every repeat records mediaanalysisd CPU percent and ioreg AGXAccelerator GPU utilization samples.",
        "Every repeat records mediaanalysisd CPU and ioreg AGX GPU summaries; per-second process samples remain private. Retrospective flags mark mean mediaanalysisd CPU >=30% as contended, without changing the nonblocking wait policy or excluding any timing repeat.",
    )

    # Process identifiers and resident model memory have no place in aggregate evidence.
    def clean(value):
        if isinstance(value, dict):
            return {
                k: clean(v)
                for k, v in value.items()
                if k
                not in {
                    "pid",
                    "pids",
                    "resident_ollama_bytes",
                    "new_clients",
                    "clients",
                    "busy_samples",
                    "background_caveat_samples",
                }
            }
        if isinstance(value, list):
            return [clean(v) for v in value]
        if isinstance(value, str):
            return re.sub(r"\bPID\s*\d+\b", "[process identifier omitted]", value)
        return value

    return clean(e)
